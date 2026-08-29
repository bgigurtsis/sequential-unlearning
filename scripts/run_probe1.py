"""Probe 1 driver: forget -> heal -> recheck on one concept, with gates.

Stage order (each stage skipped when its output exists, so the run resumes):
  1. compile the concept day (diversified training prompts + conjugate probes)
  2. build the filtered healing corpus
  3. pre-eval the parent: rehearsal eval, decay scalar, drift
  4. on-policy forget answers from the parent
  5. bounded-objective erasure with early stopping
  6. merge the erasure adapter
  7. post-forget: rehearsal eval + judge + conjugate probes + scalar + drift
  8. heal (retain-only LoRA r=16)
  9. merge the healing adapter
 10. post-heal: the same battery again
 11. gate verdicts, written as JSON and printed

Gates (SYNTHESIS section 7, probe 1):
  - forgetting: judge ABSENT on core and all required-neighbour groups
  - persistence: still ABSENT after healing, on both the original and the
    conjugate probes
  - repair: (post_forget - post_heal) / (post_forget - pre) >= 0.5 on the
    decay scalar
  - leakage: post_heal - pre scalar, recorded; > 1 point puts H4 in trouble
  - regime: PCA drift stays in the reversible band
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from decay_scalar_normalization import (
    V2_POLICY,
    bidirectional_policy_fingerprint,
    load_bidirectional_anchors,
    normalise_components_bidirectional,
)
from run_noise_sweep import (
    validate_scalar_artifact,
)


CANONICAL_CERTIFICATION = {
    "concept_index": 21,
    "heal_steps": 60,
    "forget_steps": 120,
    "batch_size": 8,
    "max_new_tokens": 256,
    "seed": 0,
}
EXPECTED_FORGET_SNAPSHOT_STEPS = tuple(range(10, 121, 10))
CANONICAL_REPO_INPUTS = {
    "concepts": "data/rehearsal_concepts.json",
    "heal_corpus": "data/heal_corpus.json",
}
CANONICAL_CONCEPT_ID = "nightmares"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-model", default="google/gemma-3-4b-it")
    parser.add_argument("--root", default="derisk/probe1_forget_heal")
    parser.add_argument("--concepts", default="data/rehearsal_concepts.json")
    parser.add_argument(
        "--concept-index",
        type=int,
        default=21,
        help="one-based index into the concept file (21 = nightmares)",
    )
    parser.add_argument(
        "--probe2-aggregate",
        default=(
            "derisk/probe2_noise_v2_heavy_parent/"
            "sweep_summary_heavy_parent_v2.json"
        ),
        help="final sealed Probe 2 aggregate; overall probe2_verdict must be PASS",
    )
    parser.add_argument(
        "--scalar-baseline",
        default="derisk/probe2_noise_v2/baseline/scalar.json",
        help="sealed Probe 2 v2 clean baseline",
    )
    parser.add_argument(
        "--scalar-anchor",
        default="derisk/probe2_noise_v2/anchor/scalar.json",
        help="sealed Probe 2 v2 alpha=1 token-salad endpoint",
    )
    parser.add_argument(
        "--scalar-ladder",
        default="derisk/probe2_noise_v2/ladder/corruption_ladder.json",
        help="sealed Probe 2 v2 dual-track ladder",
    )
    parser.add_argument("--heal-corpus", default="data/heal_corpus.json")
    parser.add_argument("--heal-steps", type=int, default=60)
    parser.add_argument("--forget-steps", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--skip-scalar",
        action="store_true",
        help="smoke only: skip scalar stages and force an INCOMPLETE verdict",
    )
    return parser.parse_args()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def sha256_of_file(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def paths_overlap(left, right):
    left = Path(left).resolve()
    right = Path(right).resolve()
    return left == right or left in right.parents or right in left.parents


def validate_certification_args(args):
    actual = {
        key: getattr(args, key) for key in CANONICAL_CERTIFICATION
    }
    if actual != CANONICAL_CERTIFICATION:
        raise ValueError(
            "Probe 1 certification configuration is frozen: "
            f"expected={CANONICAL_CERTIFICATION} actual={actual}"
        )


def validate_certification_inputs(args, repo, concept):
    repo = Path(repo).resolve()
    actual = {
        key: Path(getattr(args, key)).resolve()
        for key in CANONICAL_REPO_INPUTS
    }
    expected = {
        key: (repo / relative).resolve()
        for key, relative in CANONICAL_REPO_INPUTS.items()
    }
    if actual != expected:
        raise ValueError(
            "Probe 1 certification inputs are frozen to repository canonical "
            f"paths: expected={expected} actual={actual}"
        )
    if concept.get("id") != CANONICAL_CONCEPT_ID:
        raise ValueError(
            "Probe 1 certification concept must be "
            f"{CANONICAL_CONCEPT_ID!r}, found {concept.get('id')!r}"
        )


def validate_heal_trainer_config(payload, model_id, heal_data, output_dir):
    expected = {
        "model_id": str(model_id),
        "heal_data": str(heal_data),
        "output_dir": str(output_dir),
        "num_steps": 60,
        "save_every": 30,
        "batch_size": 4,
        "max_length": 384,
        "rank": 16,
        "lora_alpha": 32,
        "learning_rate": 2e-5,
        "seed": 0,
        "objective": "retain-only CE on the filtered healing corpus",
        "master_weight_dtype": "float32",
    }
    projection = {key: payload.get(key) for key in expected}
    if projection != expected:
        raise RuntimeError("healing trainer configuration mismatch")
    return expected


def validate_forget_snapshot_grid(adapter_root, stop_state):
    adapter_root = Path(adapter_root).resolve()
    actual = []
    for path in adapter_root.glob("step*"):
        match = re.fullmatch(r"step(\d+)", path.name)
        if match and path.is_dir():
            actual.append(int(match.group(1)))
    actual.sort()
    if tuple(actual) != EXPECTED_FORGET_SNAPSHOT_STEPS:
        raise RuntimeError(
            "forget snapshot grid mismatch: "
            f"expected={EXPECTED_FORGET_SNAPSHOT_STEPS} actual={tuple(actual)}"
        )
    expected_final = adapter_root / "step120"
    if (
        stop_state.get("external_semantic_selection") is not True
        or stop_state.get("stopped_at_step") != 120
        or stop_state.get("stop_reason") != "step_budget_exhausted"
        or Path(stop_state.get("final_adapter", "")).resolve() != expected_final
    ):
        raise RuntimeError("forget trainer terminal state is not the frozen full grid")
    return [(step, adapter_root / f"step{step:03d}") for step in actual]


def model_file_hashes(model_dir):
    model_dir = Path(model_dir)
    files = sorted(
        path
        for path in model_dir.iterdir()
        if path.is_file() and path.name != "decay_dose.json"
    )
    if not files:
        raise RuntimeError(f"model directory has no files: {model_dir}")
    return {path.name: sha256_of_file(path) for path in files}


def split_model_file_hashes(files):
    weights = {
        name: digest
        for name, digest in files.items()
        if Path(name).suffix in {".safetensors", ".bin"}
    }
    if not weights:
        raise RuntimeError("model identity contains no weight files")
    support = {
        name: digest
        for name, digest in files.items()
        if Path(name).suffix not in {".safetensors", ".bin"}
    }
    return weights, support


def tree_file_hashes(root, exclude_names=()):
    root = Path(root)
    excluded = set(exclude_names)
    return {
        path.relative_to(root).as_posix(): sha256_of_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name not in excluded
    }


def hash_paths(paths):
    return {str(Path(path)): sha256_of_file(path) for path in paths}


def overall_probe2_verdict(payload):
    direct = payload.get("probe2_verdict")
    nested = payload.get("gates", {}).get("probe2_verdict")
    if direct is not None and nested is not None and direct != nested:
        raise RuntimeError("Probe 2 aggregate contains conflicting verdict fields")
    return direct if direct is not None else nested


def verify_archive(root):
    """Verify exact coverage and hashes for a manifest-sealed archive."""
    root = Path(root).resolve()
    manifest = root / "MANIFEST.sha256"
    if not manifest.is_file():
        raise RuntimeError(f"Probe 2 archive is not sealed: {root}")
    entries = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        relative_path = Path(relative)
        if (
            not separator
            or len(digest) != 64
            or relative_path.is_absolute()
            or ".." in relative_path.parts
        ):
            raise RuntimeError(f"malformed Probe 2 manifest line: {line!r}")
        try:
            int(digest, 16)
        except ValueError as error:
            raise RuntimeError(
                f"malformed Probe 2 manifest digest: {digest!r}"
            ) from error
        key = relative_path.as_posix()
        if key in entries:
            raise RuntimeError(f"duplicate Probe 2 manifest entry: {key}")
        entries[key] = digest.lower()
    actual_files = {
        candidate.relative_to(root).as_posix(): candidate
        for candidate in root.rglob("*")
        if candidate.is_file() and candidate != manifest
    }
    if set(entries) != set(actual_files):
        raise RuntimeError("Probe 2 manifest does not exactly cover its archive")
    for relative, expected in entries.items():
        if sha256_of_file(actual_files[relative]) != expected:
            raise RuntimeError(f"Probe 2 manifest hash mismatch: {relative}")
    return {
        "manifest_path": str(manifest),
        "manifest_sha256": sha256_of_file(manifest),
        "entry_count": len(entries),
        "entries": entries,
    }


def verify_sealed_member(path):
    """Require *path* to be covered by an exact, valid archive manifest."""
    path = Path(path).resolve()
    seal = verify_archive(path.parent)
    relative = path.relative_to(path.parent).as_posix()
    if relative not in seal["entries"]:
        raise RuntimeError("Probe 2 aggregate is not covered by its manifest")
    return {key: value for key, value in seal.items() if key != "entries"}


def validate_probe2_aggregate(
    path, expected_policy, parent_model, scalar_inputs
):
    seal = verify_sealed_member(path)
    payload = read_json(path)
    if overall_probe2_verdict(payload) != "PASS":
        raise RuntimeError("Probe 1 requires final overall Probe 2 PASS")
    if payload.get("certification_scope") != (
        "heavy_parent_repeat_and_probe2_aggregate"
    ):
        raise RuntimeError("only the final two-parent Probe 2 aggregate is valid")
    gates = payload.get("gates", {})
    for gate in (
        "primary_manifest_verified",
        "primary_verdict_verified",
    ):
        if gates.get(gate) is not True:
            raise RuntimeError(f"Probe 2 aggregate did not establish {gate}")
    if gates.get("heavy_verdict") != "PASS":
        raise RuntimeError("Probe 2 aggregate heavy-parent verdict is not PASS")
    if gates.get("heavy_parent_selection_pass") is not True:
        raise RuntimeError("Probe 2 aggregate heavy-parent selection did not pass")
    if payload.get("normalisation_version") != V2_POLICY:
        raise RuntimeError("Probe 2 aggregate is not bidirectional v2")
    if payload.get("normalisation_policy_fingerprint") != expected_policy:
        raise RuntimeError("Probe 2 aggregate/pinned scalar policy mismatch")
    clean_ruler = payload.get("clean_ruler", {})
    if clean_ruler.get("policy_fingerprint") != expected_policy:
        raise RuntimeError("Probe 2 clean-ruler policy fingerprint mismatch")
    identity = payload.get("primary_archive", {})
    scalar_paths = tuple(Path(value).resolve() for value in scalar_inputs)
    primary_roots = {value.parent.parent for value in scalar_paths}
    if len(primary_roots) != 1:
        raise RuntimeError("Probe 2 scalar ruler files are not in one primary archive")
    primary_root = primary_roots.pop()
    primary_seal = verify_archive(primary_root)
    if Path(identity.get("root", "")).resolve() != primary_root:
        raise RuntimeError("Probe 2 aggregate references a different primary root")
    if identity.get("manifest_sha256") != primary_seal["manifest_sha256"]:
        raise RuntimeError("Probe 2 aggregate references a different primary seal")
    for label, scalar_path in zip(
        ("baseline", "terminal", "ladder"), scalar_paths
    ):
        relative = scalar_path.relative_to(primary_root).as_posix()
        if (
            relative not in primary_seal["entries"]
            or clean_ruler.get(label) != sha256_of_file(scalar_path)
        ):
            raise RuntimeError(f"Probe 2 {label} ruler provenance mismatch")
    for label, filename in (
        ("summary_sha256", "sweep_summary_bidirectional_v2.json"),
        ("run_config_sha256", "run_config.json"),
        ("parent_identity_sha256", "parent_identity.json"),
    ):
        primary_path = primary_root / filename
        if not primary_path.is_file() or identity.get(label) != sha256_of_file(
            primary_path
        ):
            raise RuntimeError(f"Probe 2 primary {filename} provenance mismatch")
    primary_summary = read_json(primary_root / "sweep_summary_bidirectional_v2.json")
    primary_config = read_json(primary_root / "run_config.json")
    primary_identity = read_json(primary_root / "parent_identity.json")
    if (
        primary_summary.get("certification_scope") != "clean_parent_primary_only"
        or primary_summary.get("gates", {}).get("primary_verdict") != "PASS"
        or primary_summary.get("gates", {}).get("probe2_verdict")
        != "INCOMPLETE_PENDING_HEAVY_PARENT"
        or primary_summary.get("normalisation_version") != V2_POLICY
        or primary_summary.get("normalisation_policy_fingerprint")
        != expected_policy
    ):
        raise RuntimeError("sealed Probe 2 primary record is not the certified PASS")
    clean_identity = payload.get("clean_parent_identity")
    # The aggregate summary currently carries the clean identity through its
    # run configuration rather than duplicating it at the top level.  The
    # primary summary reference is not sufficient: Probe 1 must bind to the
    # exact clean bytes that established the ruler.
    if clean_identity is None:
        run_config_path = Path(path).resolve().parent / "run_config.json"
        run_config = read_json(run_config_path)
        clean_identity = run_config.get("clean_parent_identity")
    if not isinstance(clean_identity, dict):
        raise RuntimeError("Probe 2 aggregate lacks the clean-parent identity")
    recorded_fingerprint = clean_identity.get("fingerprint")
    identity_body = {
        key: value for key, value in clean_identity.items() if key != "fingerprint"
    }
    if recorded_fingerprint != fingerprint(identity_body):
        raise RuntimeError("Probe 2 clean-parent identity fingerprint is invalid")
    parent_model = Path(parent_model).resolve()
    if Path(clean_identity.get("source_model", "")).resolve() != parent_model:
        raise RuntimeError("Probe 1 parent path differs from Probe 2 clean parent")
    if (
        primary_identity != clean_identity
        or Path(primary_summary.get("parent_model", "")).resolve() != parent_model
        or Path(primary_config.get("parent_model", "")).resolve() != parent_model
    ):
        raise RuntimeError("Probe 2 primary clean-parent provenance conflicts")
    recorded_files = {
        **clean_identity.get("weight_file_sha256", {}),
        **clean_identity.get("support_file_sha256", {}),
    }
    if recorded_files != model_file_hashes(parent_model):
        raise RuntimeError("Probe 1 parent bytes differ from Probe 2 clean parent")
    primary_identity_fingerprint = identity.get("parent_identity_sha256")
    if not primary_identity_fingerprint:
        raise RuntimeError("Probe 2 aggregate lacks primary-identity provenance")
    payload["_verified_archive"] = seal
    payload["_verified_primary_archive"] = {
        key: value for key, value in primary_seal.items() if key != "entries"
    }
    payload["_verified_parent_model_files"] = recorded_files
    return payload


def all_group_verdicts(judgement, expected, expected_group_ids):
    groups = judgement.get("groups", {})
    return set(groups) == set(expected_group_ids) and all(
        result.get("verdict") == expected for result in groups.values()
    )


def validate_judgement_payload(
    judgement, expected_judge_model, expected_concept_id, expected_group_ids
):
    judge_model = judgement.get("judge_model")
    if not judge_model or Path(judge_model).resolve() != Path(
        expected_judge_model
    ).resolve():
        raise RuntimeError("semantic judgement judge identity mismatch")
    if judgement.get("concept_id") != expected_concept_id:
        raise RuntimeError("semantic judgement concept identity mismatch")
    groups = judgement.get("groups", {})
    if set(groups) != set(expected_group_ids):
        raise RuntimeError("semantic judgement group coverage mismatch")
    for group_id, result in groups.items():
        if result.get("verdict") not in {"PRESENT", "ABSENT", "UNCLEAR"}:
            raise RuntimeError(
                f"invalid semantic verdict for group {group_id}: "
                f"{result.get('verdict')!r}"
            )
        if result.get("responses", 0) <= 0:
            raise RuntimeError(f"semantic group {group_id} has no judged responses")
    return {
        group_id: result["verdict"] for group_id, result in groups.items()
    }


def semantic_record_from_evidence(
    step, adapter, semantic_eval, semantic_judgement, judgement, expected_group_ids
):
    group_verdicts = {
        group_id: result["verdict"]
        for group_id, result in judgement.get("groups", {}).items()
    }
    return {
        "step": step,
        "adapter": str(adapter),
        "semantic_eval": str(semantic_eval),
        "semantic_eval_sha256": sha256_of_file(semantic_eval),
        "semantic_judgement": str(semantic_judgement),
        "semantic_judgement_sha256": sha256_of_file(semantic_judgement),
        "group_verdicts": group_verdicts,
        "pass": all_group_verdicts(
            judgement, "ABSENT", expected_group_ids
        ),
    }


def compute_probe1_verdict(gates, use_scalar):
    required = [
        "pre_erasure_present_pass",
        "forgetting_pass",
        "persistence_after_heal_pass",
        "drift_reversible_pass",
    ]
    if use_scalar:
        required.append("repair_pass")
    if not use_scalar:
        return "INCOMPLETE_SCALAR_SKIPPED", required
    return ("PASS" if all(gates.get(key) for key in required) else "FAIL"), required


def write_manifest(root):
    root = Path(root)
    output = root / "MANIFEST.sha256"
    temporary = output.with_name(output.name + ".tmp")
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path not in {output, temporary}
    )
    temporary.write_text(
        "\n".join(
            f"{sha256_of_file(path)}  {path.relative_to(root).as_posix()}"
            for path in files
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(output)
    return output, len(files)


def run_command(command, log_path, cwd):
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = " ".join(str(value) for value in command)
    print(f"\n$ {rendered}", flush=True)
    started = time.time()
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n$ {rendered}\n")
        log.flush()
        process = subprocess.Popen(
            [str(value) for value in command],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        code = process.wait()
        log.write(f"\nexit={code} duration_seconds={time.time() - started:.1f}\n")
    if code:
        raise subprocess.CalledProcessError(code, command)


def scalar_of(path, baseline, positive_anchor, negative_anchor):
    components = read_json(path)["components"]
    _, scalar, _ = normalise_components_bidirectional(
        components, baseline, positive_anchor, negative_anchor
    )
    return scalar


def validate_probe1_scalar_artifact(
    path,
    *,
    model_path,
    parent_model,
    model_weight_sha256,
    model_support_sha256,
    parent_weight_sha256,
    parent_support_sha256,
    prompt_sha256,
    baseline_json,
    anchor_json,
    ladder_json,
    policy_fingerprint,
    batch_size,
    max_new_tokens,
    baseline,
    positive_anchor,
    negative_anchor,
):
    model_path = str(Path(model_path).resolve())
    parent_model = str(Path(parent_model).resolve())
    payload = validate_scalar_artifact(
        path,
        expected_model=model_path,
        expected_judge=parent_model,
        expected_tokenizer=parent_model,
        expected_prompt_sha256=prompt_sha256,
        expected_weight_sha256=model_weight_sha256,
        expected_model_support_sha256=model_support_sha256,
        expected_tokenizer_support_sha256=parent_support_sha256,
        expected_judge_support_sha256=parent_support_sha256,
        expected_judge_weight_sha256=parent_weight_sha256,
        expected_policy=V2_POLICY,
        expected_policy_fingerprint=policy_fingerprint,
    )
    expected_decoding = {
        "method": "greedy",
        "max_new_tokens": max_new_tokens,
        "batch_size": batch_size,
        "padding_side": "left",
    }
    expected_anchor_paths = {
        "baseline_json": str(baseline_json),
        "anchor_json": str(anchor_json),
        "ladder_json": str(ladder_json),
    }
    if payload.get("seed") != 0 or payload.get("decoding") != expected_decoding:
        raise RuntimeError(f"scalar decoding configuration mismatch in {path}")
    if payload.get("judge_unparsed_count") != 0:
        raise RuntimeError(f"scalar judge parse count mismatch in {path}")
    if payload.get("normalisation_policy_requested") != V2_POLICY:
        raise RuntimeError(f"scalar requested policy mismatch in {path}")
    if any(payload.get(key) != value for key, value in expected_anchor_paths.items()):
        raise RuntimeError(f"scalar anchor path provenance mismatch in {path}")
    _, scalar, _ = normalise_components_bidirectional(
        payload["components"], baseline, positive_anchor, negative_anchor
    )
    reported = payload.get("scalar_0_100")
    if reported is None or abs(float(reported) - scalar) > 1e-9:
        raise RuntimeError(f"scalar value/components mismatch in {path}")
    return scalar


def main():
    args = parse_args()
    repo = Path.cwd().resolve()
    parent = Path(args.parent_model).expanduser()
    if not parent.is_dir():
        raise ValueError(
            "certified Probe 1 requires --parent-model to be the exact local "
            "clean-parent snapshot used by Probe 2"
        )
    args.parent_model = str(parent.resolve())
    root = Path(args.root).resolve()
    if (root / "MANIFEST.sha256").exists():
        verify_archive(root)
        raise RuntimeError(f"sealed Probe 1 archive is immutable: {root}")
    python = Path(sys.executable).absolute()
    log = root / "commands.log"
    day_dir = root / "day"
    concepts = read_json(args.concepts)
    if not 1 <= args.concept_index <= len(concepts):
        raise ValueError("concept-index is outside the one-based concept list")
    concept = concepts[args.concept_index - 1]
    print(f"Probe 1 concept: {concept['id']} ({concept['concept']})")

    use_scalar = not args.skip_scalar
    if use_scalar:
        validate_certification_args(args)
        validate_certification_inputs(args, repo, concept)
    scalar_inputs = (
        Path(args.scalar_baseline),
        Path(args.scalar_anchor),
        Path(args.scalar_ladder),
    )
    if use_scalar and not all(path.is_file() for path in scalar_inputs):
        raise FileNotFoundError(
            "sealed Probe 2 v2 baseline, endpoint, and ladder are required"
        )

    scalar_policy = None
    probe2_payload = None
    if use_scalar:
        baseline, positive_anchor, negative_anchor, anchor_sources = (
            load_bidirectional_anchors(*scalar_inputs)
        )
        scalar_policy = bidirectional_policy_fingerprint(
            baseline, positive_anchor, negative_anchor, anchor_sources
        )
        if not Path(args.probe2_aggregate).is_file():
            raise FileNotFoundError(
                "final overall Probe 2 aggregate is required before Probe 1"
            )
        probe2_payload = validate_probe2_aggregate(
            args.probe2_aggregate,
            scalar_policy,
            args.parent_model,
            scalar_inputs,
        )
    else:
        baseline = positive_anchor = negative_anchor = anchor_sources = None
    aggregate_root = Path(args.probe2_aggregate).resolve().parent
    primary_roots = {
        path.resolve().parent.parent for path in scalar_inputs
    }
    protected_roots = [Path(args.parent_model).resolve(), aggregate_root]
    protected_roots.extend(primary_roots)
    if any(paths_overlap(root, protected) for protected in protected_roots):
        raise ValueError(
            "Probe 1 output root must not overlap the clean parent or sealed "
            "Probe 2 archives"
        )
    root.mkdir(parents=True, exist_ok=True)
    parent_model_hashes = (
        probe2_payload["_verified_parent_model_files"]
        if probe2_payload
        else model_file_hashes(args.parent_model)
    )
    parent_weight_hashes, parent_support_hashes = split_model_file_hashes(
        parent_model_hashes
    )

    # Healing data is a frozen input to certification. Building it remains a
    # convenience for smoke runs, but its exact bytes and config are pinned.
    if not Path(args.heal_corpus).is_file():
        if use_scalar:
            raise FileNotFoundError(
                "certification requires the prebuilt frozen healing corpus"
            )
        run_command(
            [
                python,
                "scripts/build_heal_corpus.py",
                args.heal_corpus,
                "--concepts",
                args.concepts,
                "--seed",
                str(args.seed),
            ],
            log,
            repo,
        )

    input_paths = {
        "concepts": Path(args.concepts),
        "heal_corpus": Path(args.heal_corpus),
        "retain_corpus": repo / "data/retain.json",
        "chat_retain_corpus": repo / "data/retain_chat.json",
        "frozen_sea_probes": repo / "data/probes.json",
        "frozen_perplexity_text": repo / "data/ppl_text.txt",
        "decay_scalar_prompts": repo / "data/decay_scalar_prompts.json",
        "rehearsal_capability_prompts": (
            repo / "data/rehearsal_capability_prompts.json"
        ),
        "conversational_survival_generations": (
            repo / "data/conversational_survival_generations.json"
        ),
    }
    heal_corpus_path = Path(args.heal_corpus)
    heal_config = heal_corpus_path.with_name(heal_corpus_path.stem + "_config.json")
    if not heal_config.is_file():
        raise FileNotFoundError(
            "healing corpus provenance sidecar is required: " + str(heal_config)
        )
    heal_config_payload = read_json(heal_config)
    if heal_config_payload.get("corpus_sha256") != sha256_of_file(heal_corpus_path):
        raise RuntimeError("healing corpus bytes do not match its provenance sidecar")
    input_paths["heal_config"] = heal_config
    if use_scalar:
        input_paths.update(
            {
                "probe2_aggregate": Path(args.probe2_aggregate),
                "scalar_baseline": Path(args.scalar_baseline),
                "scalar_anchor": Path(args.scalar_anchor),
                "scalar_ladder": Path(args.scalar_ladder),
            }
        )
    missing_inputs = [str(path) for path in input_paths.values() if not path.is_file()]
    if missing_inputs:
        raise FileNotFoundError(
            "Probe 1 certification inputs are missing: " + ", ".join(missing_inputs)
        )
    instrument_paths = [
        repo / "scripts/run_probe1.py",
        repo / "scripts/train_bounded_forget.py",
        repo / "scripts/train_heal.py",
        repo / "scripts/build_probe1_day.py",
        repo / "scripts/build_rehearsal_day.py",
        repo / "scripts/build_onpolicy_forget.py",
        repo / "scripts/build_heal_corpus.py",
        repo / "scripts/decay_scalar_normalization.py",
        repo / "scripts/eval_rehearsal_checkpoint.py",
        repo / "scripts/eval_decay_scalar.py",
        repo / "scripts/eval_drift.py",
        repo / "scripts/judge_rehearsal_generations.py",
        repo / "scripts/merge.py",
    ]
    run_config = {
        "args": vars(args),
        "concept_id": concept["id"],
        "normalisation_version": V2_POLICY if use_scalar else None,
        "normalisation_policy_fingerprint": scalar_policy,
        "probe2_verdict": (
            overall_probe2_verdict(probe2_payload) if probe2_payload else None
        ),
        "probe2_archive_seal": (
            probe2_payload.get("_verified_archive") if probe2_payload else None
        ),
        "probe2_primary_archive_seal": (
            probe2_payload.get("_verified_primary_archive")
            if probe2_payload
            else None
        ),
        "parent_model_files_sha256": parent_model_hashes,
        "input_sha256": {
            name: sha256_of_file(path) for name, path in input_paths.items()
        },
        "instrument_sha256": {
            path.relative_to(repo).as_posix(): sha256_of_file(path)
            for path in instrument_paths
        },
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip(),
        "gate_policy": {
            "pre_erasure": "PRESENT on core and every required neighbour, original and conjugate",
            "semantic_selection": "earliest saved held-out original-probe ABSENT",
            "repair_fraction_min": 0.5,
            "leakage_scalar_points_max": 1.0,
            "pca_drift_percent_max": 20.0,
            "drift_checkpoints": ["post_forget", "post_heal"],
            "skip_scalar_verdict": "INCOMPLETE_SCALAR_SKIPPED",
        },
    }
    run_config["fingerprint"] = fingerprint(run_config)
    config_path = root / "run_config.json"
    if config_path.exists():
        if read_json(config_path) != run_config:
            raise RuntimeError(
                f"Probe 1 configuration mismatch in {root}; use a new root"
            )
    else:
        write_json(config_path, run_config)
    state_path = root / "state.json"
    state = read_json(state_path) if state_path.exists() else {
        "status": "running",
        "run_config_fingerprint": run_config["fingerprint"],
    }
    if state.get("run_config_fingerprint") != run_config["fingerprint"]:
        raise RuntimeError("Probe 1 state/config fingerprint mismatch")
    write_json(state_path, state)
    expected_group_ids = tuple(group["id"] for group in concept["groups"])
    if not expected_group_ids or len(expected_group_ids) != len(set(expected_group_ids)):
        raise RuntimeError("concept has no groups or duplicate group ids")

    # 1. Compile the immutable day and write a completion marker.
    day_marker = day_dir / "stage_complete.json"
    if not day_marker.exists():
        if day_dir.exists() and any(day_dir.iterdir()):
            raise RuntimeError(f"partial day compilation needs inspection: {day_dir}")
        run_command(
            [
                python,
                "scripts/build_probe1_day.py",
                str(args.concept_index),
                day_dir,
                "--concepts",
                args.concepts,
                "--seed",
                str(args.seed),
            ],
            log,
            repo,
        )
        day_files = sorted(path for path in day_dir.iterdir() if path.is_file())
        write_json(
            day_marker,
            {
                "run_config_fingerprint": run_config["fingerprint"],
                "files_sha256": hash_paths(day_files),
            },
        )
    day_record = read_json(day_marker)
    if day_record.get("run_config_fingerprint") != run_config["fingerprint"]:
        raise RuntimeError("compiled day belongs to a different Probe 1 run")
    expected_day_hashes = day_record.get("files_sha256", {})
    for path_text, expected_hash in expected_day_hashes.items():
        if not Path(path_text).is_file() or sha256_of_file(path_text) != expected_hash:
            raise RuntimeError("compiled day artifact hash mismatch")

    def artifact_marker(path):
        path = Path(path)
        return path.with_name(path.name + ".complete.json")

    def mark_artifact(path, provenance):
        path = Path(path)
        write_json(
            artifact_marker(path),
            {
                "run_config_fingerprint": run_config["fingerprint"],
                "artifact_sha256": sha256_of_file(path),
                "provenance": provenance,
            },
        )

    def artifact_is_complete(path, provenance):
        path = Path(path)
        marker = artifact_marker(path)
        if not path.exists() and not marker.exists():
            return False
        if not path.is_file() or not marker.is_file():
            raise RuntimeError(f"partial artifact needs inspection: {path}")
        payload = read_json(marker)
        expected = {
            "run_config_fingerprint": run_config["fingerprint"],
            "artifact_sha256": sha256_of_file(path),
            "provenance": provenance,
        }
        if payload != expected:
            raise RuntimeError(f"artifact provenance mismatch: {path}")
        return True

    def eval_stage(name, model_path):
        """Rehearsal eval + conjugate probes + scalar + drift for one checkpoint."""
        stage = root / name
        stage.mkdir(parents=True, exist_ok=True)
        model_path = str(Path(model_path).resolve())
        model_files = model_file_hashes(model_path)
        model_weights, model_support = split_model_file_hashes(model_files)
        model_identity = fingerprint(
            {"path": model_path, "files_sha256": model_files}
        )
        rehearsal = stage / "rehearsal_eval.json"
        rehearsal_provenance = {
            "kind": "rehearsal_eval",
            "model_identity": model_identity,
            "day_marker_sha256": sha256_of_file(day_marker),
            "max_new_tokens": 64,
        }
        if not artifact_is_complete(rehearsal, rehearsal_provenance):
            run_command(
                [
                    python,
                    "scripts/eval_rehearsal_checkpoint.py",
                    model_path,
                    rehearsal,
                    "--day-dir",
                    day_dir,
                    "--tokenizer-model",
                    args.parent_model,
                    "--max-new-tokens",
                    "64",
                    "--skip-cumulative",
                ],
                log,
                repo,
            )
            mark_artifact(rehearsal, rehearsal_provenance)
        conjugate = stage / "conjugate_eval.json"
        conjugate_day = root / "day_conjugate"
        conjugate_marker = conjugate_day / "stage_complete.json"
        if not conjugate_marker.exists():
            # Same evaluator, pointed at a day dir whose probes.json is the
            # conjugate set, so the judge downstream sees the identical shape.
            if conjugate_day.exists() and any(conjugate_day.iterdir()):
                raise RuntimeError(
                    f"partial conjugate day needs inspection: {conjugate_day}"
                )
            if not conjugate_day.exists():
                conjugate_day.mkdir(parents=True, exist_ok=True)
            for filename in ("concept.json", "clozes.json"):
                shutil.copy2(day_dir / filename, conjugate_day / filename)
            shutil.copy2(
                day_dir / "probes_conjugate.json", conjugate_day / "probes.json"
            )
            write_json(
                conjugate_marker,
                {
                    "run_config_fingerprint": run_config["fingerprint"],
                    "source_day_marker_sha256": sha256_of_file(day_marker),
                    "files_sha256": hash_paths(
                        sorted(
                            path
                            for path in conjugate_day.iterdir()
                            if path.is_file()
                        )
                    ),
                },
            )
        conjugate_day_record = read_json(conjugate_marker)
        if (
            conjugate_day_record.get("run_config_fingerprint")
            != run_config["fingerprint"]
            or conjugate_day_record.get("source_day_marker_sha256")
            != sha256_of_file(day_marker)
        ):
            raise RuntimeError("conjugate day provenance mismatch")
        for path_text, expected_hash in conjugate_day_record.get(
            "files_sha256", {}
        ).items():
            if not Path(path_text).is_file() or sha256_of_file(path_text) != expected_hash:
                raise RuntimeError("conjugate day artifact hash mismatch")
        conjugate_provenance = {
            "kind": "conjugate_eval",
            "model_identity": model_identity,
            "conjugate_day_marker_sha256": sha256_of_file(conjugate_marker),
            "max_new_tokens": 64,
        }
        if not artifact_is_complete(conjugate, conjugate_provenance):
            run_command(
                [
                    python,
                    "scripts/eval_rehearsal_checkpoint.py",
                    model_path,
                    conjugate,
                    "--day-dir",
                    conjugate_day,
                    "--tokenizer-model",
                    args.parent_model,
                    "--max-new-tokens",
                    "64",
                    "--skip-capability",
                    "--skip-cumulative",
                    "--skip-perplexity",
                ],
                log,
                repo,
            )
            mark_artifact(conjugate, conjugate_provenance)
        drift = stage / "drift.json"
        drift_provenance = {
            "kind": "pca_cka_drift",
            "model_identity": model_identity,
            "batch_size": args.batch_size,
        }
        if not artifact_is_complete(drift, drift_provenance):
            run_command(
                [
                    python,
                    "scripts/eval_drift.py",
                    model_path,
                    drift,
                    "--reference-model",
                    args.parent_model,
                    "--tokenizer-model",
                    args.parent_model,
                    "--batch-size",
                    str(args.batch_size),
                ],
                log,
                repo,
            )
            mark_artifact(drift, drift_provenance)
        scalar = stage / "scalar.json"
        scalar_provenance = {
            "kind": "decay_scalar",
            "model_identity": model_identity,
            "policy_fingerprint": scalar_policy,
            "batch_size": args.batch_size,
            "max_new_tokens": args.max_new_tokens,
        }
        if use_scalar and not artifact_is_complete(scalar, scalar_provenance):
            run_command(
                [
                    python,
                    "scripts/eval_decay_scalar.py",
                    model_path,
                    scalar,
                    "--batch-size",
                    str(args.batch_size),
                    "--max-new-tokens",
                    str(args.max_new_tokens),
                    "--seed",
                    "0",
                    "--judge-model",
                    args.parent_model,
                    "--tokenizer-model",
                    args.parent_model,
                    "--baseline-json",
                    args.scalar_baseline,
                    "--anchor-json",
                    args.scalar_anchor,
                    "--ladder-json",
                    args.scalar_ladder,
                    "--normalisation-policy",
                    V2_POLICY,
                ],
                log,
                repo,
            )
            mark_artifact(scalar, scalar_provenance)
        if use_scalar:
            validate_probe1_scalar_artifact(
                scalar,
                model_path=model_path,
                parent_model=args.parent_model,
                model_weight_sha256=model_weights,
                model_support_sha256=model_support,
                parent_weight_sha256=parent_weight_hashes,
                parent_support_sha256=parent_support_hashes,
                prompt_sha256={
                    "battery": run_config["input_sha256"]["decay_scalar_prompts"],
                    "capability": run_config["input_sha256"][
                        "rehearsal_capability_prompts"
                    ],
                    "survival": run_config["input_sha256"][
                        "conversational_survival_generations"
                    ],
                },
                baseline_json=args.scalar_baseline,
                anchor_json=args.scalar_anchor,
                ladder_json=args.scalar_ladder,
                policy_fingerprint=scalar_policy,
                batch_size=args.batch_size,
                max_new_tokens=args.max_new_tokens,
                baseline=baseline,
                positive_anchor=positive_anchor,
                negative_anchor=negative_anchor,
            )
        return stage

    def judgement_provenance(source):
        return {
            "kind": "semantic_judgement",
            "source_sha256": sha256_of_file(source),
            "judge_model_identity": fingerprint(parent_model_hashes),
        }

    def judge_eval(source, target, scratch):
        source = Path(source)
        target = Path(target)
        provenance = judgement_provenance(source)
        if artifact_is_complete(target, provenance):
            validate_judgement_payload(
                read_json(target),
                args.parent_model,
                concept["id"],
                expected_group_ids,
            )
            return target
        step_dir = Path(scratch) / "step01_probe"
        step_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, step_dir / "post_eval.json")
        run_command(
            [
                python,
                "scripts/judge_rehearsal_generations.py",
                "--root",
                scratch,
                "--judge-model",
                args.parent_model,
                "--force",
            ],
            log,
            repo,
        )
        shutil.copy2(step_dir / "semantic_judgement.json", target)
        mark_artifact(target, provenance)
        validate_judgement_payload(
            read_json(target),
            args.parent_model,
            concept["id"],
            expected_group_ids,
        )
        return target

    def judge_stage(stage):
        """Run the pinned clean semantic judge over original and conjugate evals."""
        for source, output in (
            ("rehearsal_eval.json", "judgement.json"),
            ("conjugate_eval.json", "judgement_conjugate.json"),
        ):
            judge_eval(
                stage / source,
                stage / output,
                stage / f"judge_{Path(source).stem}",
            )

    def seal_terminal(summary, status):
        summary["run_config_fingerprint"] = run_config["fingerprint"]
        summary["archive_provenance"] = {
            "run_config": str(config_path),
            "run_config_sha256": sha256_of_file(config_path),
            "parent_model_files_sha256": parent_model_hashes,
            "input_sha256": run_config["input_sha256"],
            "instrument_sha256": run_config["instrument_sha256"],
            "probe2_archive_seal": run_config["probe2_archive_seal"],
            "probe2_primary_archive_seal": run_config[
                "probe2_primary_archive_seal"
            ],
        }
        write_json(root / "probe1_summary.json", summary)
        state["status"] = status
        write_json(state_path, state)
        manifest, manifest_count = write_manifest(root)
        seal = verify_archive(root)
        if seal["entry_count"] != manifest_count:
            raise RuntimeError("Probe 1 manifest verification count mismatch")
        print(f"Sealed {manifest} ({manifest_count} files)")

    # 3. Pre-evaluate and prove that the semantic target is initially present.
    pre = eval_stage("pre", args.parent_model)
    judge_stage(pre)
    pre_original = read_json(pre / "judgement.json")
    pre_conjugate = read_json(pre / "judgement_conjugate.json")
    pre_present_pass = all_group_verdicts(
        pre_original, "PRESENT", expected_group_ids
    ) and all_group_verdicts(
        pre_conjugate, "PRESENT", expected_group_ids
    )
    if not pre_present_pass:
        summary = {
            "certification_scope": "probe1_forget_heal",
            "concept": {"index": args.concept_index, **concept},
            "parent_model": args.parent_model,
            "normalisation_policy_fingerprint": scalar_policy,
            "gates": {
                "pre_erasure_present_pass": False,
                "pre_original_group_verdicts": {
                    key: value["verdict"]
                    for key, value in pre_original["groups"].items()
                },
                "pre_conjugate_group_verdicts": {
                    key: value["verdict"]
                    for key, value in pre_conjugate["groups"].items()
                },
                "probe1_verdict": (
                    "FAIL" if use_scalar else "INCOMPLETE_SCALAR_SKIPPED"
                ),
                "failure_stage": "pre_erasure_presence",
            },
        }
        seal_terminal(
            summary,
            (
                "failed_pre_erasure_presence"
                if use_scalar
                else "incomplete_scalar_skipped"
            ),
        )
        pre_verdict = "FAIL" if use_scalar else "INCOMPLETE_SCALAR_SKIPPED"
        print(f"PROBE 1 VERDICT: {pre_verdict} (target not PRESENT before erasure)")
        return

    # 4. On-policy forget answers, with an exact completion marker.
    onpolicy = day_dir / "forget_onpolicy.json"
    onpolicy_provenance = {
        "kind": "onpolicy_forget",
        "parent_identity": fingerprint(parent_model_hashes),
        "prompt_sha256": sha256_of_file(
            day_dir / "forget_prompts_diversified.json"
        ),
        "batch_size": 4,
        "max_new_tokens": 64,
    }
    if not artifact_is_complete(onpolicy, onpolicy_provenance):
        run_command(
            [
                python,
                "scripts/build_onpolicy_forget.py",
                "--model-id",
                args.parent_model,
                "--input",
                day_dir / "forget_prompts_diversified.json",
                "--output",
                onpolicy,
                "--batch-size",
                "4",
                "--max-new-tokens",
                "64",
            ],
            log,
            repo,
        )
        mark_artifact(onpolicy, onpolicy_provenance)

    # 5. Train the complete snapshot grid. Proxy loss gates are telemetry;
    # certification selects the earliest held-out semantic PASS below.
    adapter_root = root / "forget_adapter"
    stop_state = adapter_root / "stop_state.json"
    adapter_marker = root / "forget_adapter_complete.json"
    if not adapter_marker.exists():
        if adapter_root.exists():
            raise RuntimeError(
                f"partial erasure directory needs inspection: {adapter_root}"
            )
        run_command(
            [
                python,
                "scripts/train_bounded_forget.py",
                "--model-id",
                args.parent_model,
                "--forget-data",
                onpolicy,
                "--output-dir",
                adapter_root,
                "--num-steps",
                str(args.forget_steps),
                "--seed",
                str(args.seed),
                "--external-semantic-selection",
            ],
            log,
            repo,
        )
        if not stop_state.is_file() or not (adapter_root / "run_config.json").is_file():
            raise RuntimeError("forget trainer completed without terminal records")
        write_json(
            adapter_marker,
            {
                "run_config_fingerprint": run_config["fingerprint"],
                "trainer_run_config_sha256": sha256_of_file(
                    adapter_root / "run_config.json"
                ),
                "trainer_stop_state_sha256": sha256_of_file(stop_state),
                "adapter_tree_sha256": tree_file_hashes(adapter_root),
                "forget_data_sha256": sha256_of_file(onpolicy),
                "retain_data_sha256": sha256_of_file(repo / "data/retain.json"),
                "chat_retain_data_sha256": sha256_of_file(
                    repo / "data/retain_chat.json"
                ),
            },
        )
    if not stop_state.is_file() or not (adapter_root / "run_config.json").is_file():
        raise RuntimeError("forget adapter marker exists without terminal records")
    expected_adapter_marker = {
        "run_config_fingerprint": run_config["fingerprint"],
        "trainer_run_config_sha256": sha256_of_file(adapter_root / "run_config.json"),
        "trainer_stop_state_sha256": sha256_of_file(stop_state),
        "adapter_tree_sha256": tree_file_hashes(adapter_root),
        "forget_data_sha256": sha256_of_file(onpolicy),
        "retain_data_sha256": sha256_of_file(repo / "data/retain.json"),
        "chat_retain_data_sha256": sha256_of_file(repo / "data/retain_chat.json"),
    }
    if read_json(adapter_marker) != expected_adapter_marker:
        raise RuntimeError("forget adapter completion/provenance marker mismatch")
    trainer_state = read_json(stop_state)
    snapshots = validate_forget_snapshot_grid(adapter_root, trainer_state)
    trainer_config = read_json(adapter_root / "run_config.json")
    expected_trainer_config = {
        "model_id": args.parent_model,
        "forget_data": str(onpolicy),
        "retain_data": "data/retain.json",
        "chat_retain_data": "data/retain_chat.json",
        "output_dir": str(adapter_root),
        "num_steps": args.forget_steps,
        "save_every": 10,
        "eval_every": 10,
        "batch_forget": 4,
        "batch_retain": 2,
        "batch_chat_retain": 2,
        "max_length": 256,
        "rank": 4,
        "lora_alpha": 8,
        "train_layer_lo": 4,
        "train_layer_hi": 11,
        "learning_rate": 5e-5,
        "forget_weight": 1.0,
        "retain_weight": 1.0,
        "chat_retain_weight": 1.0,
        "stop_jsd": 0.02,
        "stop_answer_prob": 0.05,
        "audit_size": 24,
        "seed": args.seed,
        "fp32_base": False,
        "external_semantic_selection": True,
    }
    trainer_projection = {
        key: trainer_config.get(key) for key in expected_trainer_config
    }
    if trainer_projection != expected_trainer_config:
        raise RuntimeError("forget trainer configuration mismatch")

    # 6. Merge/evaluate snapshots in step order and select the first held-out
    # original-probe judgement that is ABSENT for every required group.
    semantic_root = root / "forget_semantic_selection"
    semantic_root.mkdir(parents=True, exist_ok=True)
    semantic_stop_state = semantic_root / "semantic_stop_state.json"
    forget_model = root / "forget_model"
    def snapshot_semantic_provenance(step, adapter):
        return {
            "kind": "snapshot_semantic_eval",
            "step": step,
            "adapter_sha256": fingerprint(tree_file_hashes(adapter)),
            "day_marker_sha256": sha256_of_file(day_marker),
            "evaluation_scope": "held-out current-concept semantics only",
        }

    if semantic_stop_state.exists():
        semantic_selection = read_json(semantic_stop_state)
        if (
            semantic_selection.get("run_config_fingerprint")
            != run_config["fingerprint"]
            or semantic_selection.get("selection_policy")
            != "earliest saved held-out semantic PASS"
            or semantic_selection.get("step_budget") != args.forget_steps
        ):
            raise RuntimeError("semantic selection/config marker mismatch")
        evaluated_steps = []
        snapshot_by_step = dict(snapshots)
        for record in semantic_selection.get("evaluated", []):
            step = record.get("step")
            evaluated_steps.append(step)
            adapter = snapshot_by_step.get(step)
            candidate = semantic_root / f"step{step:03d}" if adapter else None
            semantic_eval_path = candidate / "semantic_eval.json" if candidate else None
            semantic_judgement_path = (
                candidate / "semantic_judgement.json" if candidate else None
            )
            if adapter is None:
                raise RuntimeError("semantic selection names a non-grid snapshot")
            semantic_provenance = snapshot_semantic_provenance(step, adapter)
            if not artifact_is_complete(semantic_eval_path, semantic_provenance):
                raise RuntimeError("semantic selection eval lacks completion evidence")
            judgement_marker_provenance = judgement_provenance(semantic_eval_path)
            if not artifact_is_complete(
                semantic_judgement_path, judgement_marker_provenance
            ):
                raise RuntimeError(
                    "semantic selection judgement lacks completion evidence"
                )
            judgement_payload = read_json(semantic_judgement_path)
            validate_judgement_payload(
                judgement_payload,
                args.parent_model,
                concept["id"],
                expected_group_ids,
            )
            expected_record = semantic_record_from_evidence(
                step,
                adapter,
                semantic_eval_path,
                semantic_judgement_path,
                judgement_payload,
                expected_group_ids,
            )
            if record != expected_record:
                raise RuntimeError("semantic selection evidence/provenance mismatch")
        if evaluated_steps != sorted(evaluated_steps) or len(evaluated_steps) != len(
            set(evaluated_steps)
        ):
            raise RuntimeError("semantic selection steps are not strictly ordered")
        selected_value = semantic_selection.get("selected_adapter")
        selected_adapter = Path(selected_value) if selected_value else None
        if (selected_adapter is None) != (
            semantic_selection.get("selected_step") is None
        ) or semantic_selection.get("semantic_pass") != (selected_adapter is not None):
            raise RuntimeError("semantic selection terminal fields conflict")
        if selected_adapter is not None:
            selected_step = semantic_selection["selected_step"]
            if (
                selected_adapter.resolve().parent != adapter_root.resolve()
                or selected_adapter.name != f"step{selected_step:03d}"
                or not selected_adapter.is_dir()
                or not evaluated_steps
                or evaluated_steps[-1] != selected_step
                or not semantic_selection["evaluated"][-1].get("pass")
            ):
                raise RuntimeError("selected semantic adapter provenance mismatch")
            selected_index = [step for step, _ in snapshots].index(selected_step)
            if evaluated_steps != [
                step for step, _ in snapshots[: selected_index + 1]
            ] or any(
                record.get("pass")
                for record in semantic_selection["evaluated"][:-1]
            ):
                raise RuntimeError("semantic selection did not preserve earliest PASS")
        elif evaluated_steps != [step for step, _ in snapshots] or any(
            record.get("pass") for record in semantic_selection.get("evaluated", [])
        ):
            raise RuntimeError("failed semantic selection did not exhaust the grid")
        if selected_adapter is not None and not forget_model.is_dir():
            raise RuntimeError("semantic stop state exists without selected model")
    else:
        semantic_records = []
        selected_adapter = None
        for step, adapter in snapshots:
            candidate = semantic_root / f"step{step:03d}"
            candidate.mkdir(parents=True, exist_ok=True)
            candidate_model = candidate / "merged_model"
            merge_marker = candidate / "merge_complete.json"
            semantic_eval = candidate / "semantic_eval.json"
            if not merge_marker.exists():
                if candidate_model.exists():
                    raise RuntimeError(
                        f"partial candidate merge needs inspection: {candidate_model}"
                    )
                run_command(
                    [
                        python,
                        "scripts/merge.py",
                        adapter,
                        candidate_model,
                        args.parent_model,
                    ],
                    log,
                    repo,
                )
                write_json(
                    merge_marker,
                    {
                        "run_config_fingerprint": run_config["fingerprint"],
                        "adapter": str(adapter),
                        "adapter_sha256": tree_file_hashes(adapter),
                        "model_sha256": model_file_hashes(candidate_model),
                    },
                )
            elif not candidate_model.is_dir() and not artifact_marker(
                semantic_eval
            ).is_file():
                run_command(
                    [
                        python,
                        "scripts/merge.py",
                        adapter,
                        candidate_model,
                        args.parent_model,
                    ],
                    log,
                    repo,
                )
            merge_record = read_json(merge_marker)
            if (
                merge_record.get("run_config_fingerprint")
                != run_config["fingerprint"]
                or merge_record.get("adapter_sha256") != tree_file_hashes(adapter)
            ):
                raise RuntimeError("candidate merge provenance mismatch")
            if candidate_model.is_dir() and (
                merge_record.get("model_sha256") != model_file_hashes(candidate_model)
            ):
                raise RuntimeError("candidate merged-model hash mismatch")
            semantic_provenance = snapshot_semantic_provenance(step, adapter)
            if not artifact_is_complete(semantic_eval, semantic_provenance):
                run_command(
                    [
                        python,
                        "scripts/eval_rehearsal_checkpoint.py",
                        candidate_model,
                        semantic_eval,
                        "--day-dir",
                        day_dir,
                        "--tokenizer-model",
                        args.parent_model,
                        "--max-new-tokens",
                        "64",
                        "--skip-capability",
                        "--skip-cumulative",
                        "--skip-perplexity",
                        "--skip-sea",
                    ],
                    log,
                    repo,
                )
                mark_artifact(semantic_eval, semantic_provenance)
            semantic_judgement = candidate / "semantic_judgement.json"
            judge_eval(
                semantic_eval,
                semantic_judgement,
                candidate / "judge_scratch",
            )
            judgement_payload = read_json(semantic_judgement)
            passed = all_group_verdicts(
                judgement_payload, "ABSENT", expected_group_ids
            )
            semantic_records.append(
                semantic_record_from_evidence(
                    step,
                    adapter,
                    semantic_eval,
                    semantic_judgement,
                    judgement_payload,
                    expected_group_ids,
                )
            )
            if passed:
                selected_adapter = adapter
                if not forget_model.exists():
                    if not candidate_model.is_dir():
                        raise RuntimeError("passing candidate model is unavailable")
                    candidate_model.replace(forget_model)
                if model_file_hashes(forget_model) != merge_record.get("model_sha256"):
                    raise RuntimeError("selected merged-model hash mismatch")
                write_json(
                    root / "forget_model_complete.json",
                    {
                        "run_config_fingerprint": run_config["fingerprint"],
                        "selected_step": step,
                        "selected_adapter": str(adapter),
                        "model_sha256": model_file_hashes(forget_model),
                    },
                )
                break
            # The full model is redrawn exactly from the archived adapter and
            # clean parent; generations and judgement remain immutable.
            if candidate_model.is_dir():
                shutil.rmtree(candidate_model)
        semantic_selection = {
            "run_config_fingerprint": run_config["fingerprint"],
            "selection_policy": "earliest saved held-out semantic PASS",
            "step_budget": args.forget_steps,
            "evaluated": semantic_records,
            "selected_adapter": (
                str(selected_adapter) if selected_adapter is not None else None
            ),
            "selected_step": (
                int(re.search(r"(\d+)$", selected_adapter.name).group(1))
                if selected_adapter is not None
                else None
            ),
            "semantic_pass": selected_adapter is not None,
        }
        write_json(semantic_stop_state, semantic_selection)

    if selected_adapter is None:
        summary = {
            "certification_scope": "probe1_forget_heal",
            "concept": {"index": args.concept_index, **concept},
            "parent_model": args.parent_model,
            "normalisation_policy_fingerprint": scalar_policy,
            "forget_semantic_selection": semantic_selection,
            "gates": {
                "pre_erasure_present_pass": True,
                "forgetting_pass": False,
                "probe1_verdict": (
                    "FAIL" if use_scalar else "INCOMPLETE_SCALAR_SKIPPED"
                ),
                "failure_stage": "semantic_step_budget",
            },
        }
        seal_terminal(
            summary,
            (
                "failed_semantic_step_budget"
                if use_scalar
                else "incomplete_scalar_skipped"
            ),
        )
        budget_verdict = "FAIL" if use_scalar else "INCOMPLETE_SCALAR_SKIPPED"
        print(
            f"PROBE 1 VERDICT: {budget_verdict} "
            "(semantic bar not reached in budget)"
        )
        return

    forget_model_marker = root / "forget_model_complete.json"
    if not forget_model_marker.is_file():
        raise RuntimeError("selected forget model lacks a completion marker")
    forget_model_record = read_json(forget_model_marker)
    if (
        forget_model_record.get("run_config_fingerprint")
        != run_config["fingerprint"]
        or forget_model_record.get("selected_adapter") != str(selected_adapter)
        or forget_model_record.get("model_sha256")
        != model_file_hashes(forget_model)
    ):
        raise RuntimeError("selected forget model provenance mismatch")

    # 7. post-forget battery.
    post_forget = eval_stage("post_forget", forget_model)
    judge_stage(post_forget)

    # 8-9. heal, then merge.
    heal_root = root / "heal_adapter"
    heal_final = heal_root / f"step{args.heal_steps:03d}"
    heal_marker = root / "heal_adapter_complete.json"
    if not heal_marker.exists():
        if heal_root.exists():
            raise RuntimeError(f"partial healing directory needs inspection: {heal_root}")
        run_command(
            [
                python,
                "scripts/train_heal.py",
                "--model-id",
                forget_model,
                "--heal-data",
                args.heal_corpus,
                "--output-dir",
                heal_root,
                "--num-steps",
                str(args.heal_steps),
                "--seed",
                str(args.seed),
            ],
            log,
            repo,
        )
        if not heal_final.is_dir():
            raise RuntimeError("healing finished without its final adapter")
        write_json(
            heal_marker,
            {
                "run_config_fingerprint": run_config["fingerprint"],
                "final_adapter": str(heal_final),
                "adapter_tree_sha256": tree_file_hashes(heal_root),
                "source_forget_model_sha256": model_file_hashes(forget_model),
                "heal_corpus_sha256": sha256_of_file(args.heal_corpus),
            },
        )
    heal_record = read_json(heal_marker)
    if (
        heal_record.get("run_config_fingerprint") != run_config["fingerprint"]
        or heal_record.get("final_adapter") != str(heal_final)
        or heal_record.get("adapter_tree_sha256") != tree_file_hashes(heal_root)
        or heal_record.get("source_forget_model_sha256")
        != model_file_hashes(forget_model)
        or heal_record.get("heal_corpus_sha256")
        != sha256_of_file(args.heal_corpus)
    ):
        raise RuntimeError("healing adapter provenance mismatch")
    heal_trainer_config_path = heal_root / "run_config.json"
    if not heal_trainer_config_path.is_file():
        raise RuntimeError("healing adapter lacks its trainer configuration")
    heal_trainer_config = read_json(heal_trainer_config_path)
    validate_heal_trainer_config(
        heal_trainer_config,
        forget_model,
        args.heal_corpus,
        heal_root,
    )
    heal_model = root / "heal_model"
    heal_model_marker = root / "heal_model_complete.json"
    if not heal_model_marker.exists():
        if heal_model.exists():
            raise RuntimeError(f"partial healing merge needs inspection: {heal_model}")
        run_command(
            [python, "scripts/merge.py", heal_final, heal_model, forget_model],
            log,
            repo,
        )
        write_json(
            heal_model_marker,
            {
                "run_config_fingerprint": run_config["fingerprint"],
                "heal_adapter_tree_sha256": tree_file_hashes(heal_final),
                "base_forget_model_sha256": model_file_hashes(forget_model),
                "model_sha256": model_file_hashes(heal_model),
            },
        )
    heal_model_record = read_json(heal_model_marker)
    if (
        heal_model_record.get("run_config_fingerprint")
        != run_config["fingerprint"]
        or heal_model_record.get("heal_adapter_tree_sha256")
        != tree_file_hashes(heal_final)
        or heal_model_record.get("base_forget_model_sha256")
        != model_file_hashes(forget_model)
        or heal_model_record.get("model_sha256") != model_file_hashes(heal_model)
    ):
        raise RuntimeError("healed model provenance mismatch")

    # 10. post-heal battery.
    post_heal = eval_stage("post_heal", heal_model)
    judge_stage(post_heal)

    # 11. gates.
    def judged(stage, filename):
        payload = read_json(stage / filename)
        group_verdicts = {
            group_id: result["verdict"]
            for group_id, result in payload.get("groups", {}).items()
        }
        if set(group_verdicts) != set(expected_group_ids):
            raise RuntimeError(
                f"semantic judgement group coverage mismatch: {stage / filename}"
            )
        return {
            "core_unlearned": group_verdicts["core"] == "ABSENT",
            "required_neighbours_unlearned": all(
                group_verdicts[group_id] == "ABSENT"
                for group_id in expected_group_ids
                if group_id != "core"
            ),
            "groups": group_verdicts,
        }

    forget_judgement = judged(post_forget, "judgement.json")
    forget_conjugate = judged(post_forget, "judgement_conjugate.json")
    heal_judgement = judged(post_heal, "judgement.json")
    heal_conjugate = judged(post_heal, "judgement_conjugate.json")

    gates = {
        "pre_erasure_present_pass": pre_present_pass,
        "pre_original_group_verdicts": {
            key: value["verdict"] for key, value in pre_original["groups"].items()
        },
        "pre_conjugate_group_verdicts": {
            key: value["verdict"] for key, value in pre_conjugate["groups"].items()
        },
        "forgetting_pass": (
            semantic_selection["semantic_pass"]
            and semantic_selection["selected_step"] <= args.forget_steps
            and
            forget_judgement["core_unlearned"]
            and forget_judgement["required_neighbours_unlearned"]
        ),
        "persistence_after_heal_pass": (
            heal_judgement["core_unlearned"]
            and heal_judgement["required_neighbours_unlearned"]
            and heal_conjugate["core_unlearned"]
            and heal_conjugate["required_neighbours_unlearned"]
        ),
        "post_forget_judgement": forget_judgement,
        "post_forget_conjugate_judgement": forget_conjugate,
        "post_heal_judgement": heal_judgement,
        "post_heal_conjugate_judgement": heal_conjugate,
        "semantic_selection_step": semantic_selection["selected_step"],
        "semantic_step_budget": args.forget_steps,
    }

    drift_values = {
        name: read_json(root / name / "drift.json")[
            "pca_drift_percent_of_reference_spread"
        ]
        for name in ("pre", "post_forget", "post_heal")
    }
    gates["pca_drift"] = drift_values
    gates["drift_reversible_pass"] = (
        drift_values["post_forget"] <= 20.0
        and drift_values["post_heal"] <= 20.0
    )
    gates["drift_policy"] = {
        "maximum_percent": 20.0,
        "required_checkpoints": ["post_forget", "post_heal"],
    }

    if use_scalar:
        scalars = {
            name: scalar_of(
                root / name / "scalar.json",
                baseline,
                positive_anchor,
                negative_anchor,
            )
            for name in ("pre", "post_forget", "post_heal")
        }
        collateral = scalars["post_forget"] - scalars["pre"]
        recovered = scalars["post_forget"] - scalars["post_heal"]
        fraction = recovered / collateral if collateral > 1e-9 else None
        leakage = scalars["post_heal"] - scalars["pre"]
        gates.update(
            {
                "scalars": scalars,
                "collateral_from_forgetting": collateral,
                "recovered_by_healing": recovered,
                "repair_fraction": fraction,
                "repair_pass": (
                    fraction is not None and recovered >= 0.0 and fraction >= 0.5
                ),
                "leakage_scalar_points": leakage,
                "leakage_within_budget": leakage <= 1.0,
                "leakage_policy_max_scalar_points": 1.0,
                "normalisation_version": V2_POLICY,
                "normalisation_policy_fingerprint": scalar_policy,
                "probe2_archive_seal": (
                    probe2_payload.get("_verified_archive")
                    if probe2_payload
                    else None
                ),
                "positive_component_anchor": positive_anchor,
                "negative_component_anchor": negative_anchor,
                "component_anchor_sources": anchor_sources,
            }
        )
    else:
        gates.update(
            {
                "repair_fraction": None,
                "repair_pass": None,
                "leakage_scalar_points": None,
                "leakage_within_budget": None,
                "leakage_policy_max_scalar_points": 1.0,
            }
        )

    gates["probe1_verdict"], required = compute_probe1_verdict(gates, use_scalar)
    gates["required_gates"] = required

    summary = {
        "certification_scope": "probe1_forget_heal",
        "concept": {"index": args.concept_index, **concept},
        "parent_model": args.parent_model,
        "run_config_fingerprint": run_config["fingerprint"],
        "probe2_aggregate": (
            {
                "path": str(Path(args.probe2_aggregate).resolve()),
                "sha256": sha256_of_file(args.probe2_aggregate),
                "probe2_verdict": overall_probe2_verdict(probe2_payload),
                "normalisation_policy_fingerprint": scalar_policy,
                "archive_seal": probe2_payload.get("_verified_archive"),
                "primary_archive_seal": probe2_payload.get(
                    "_verified_primary_archive"
                ),
            }
            if use_scalar
            else None
        ),
        "forget_training_stop_state": read_json(stop_state),
        "forget_semantic_selection": semantic_selection,
        "models": {
            "forget_model": str(forget_model),
            "heal_model": str(heal_model),
            "forget_model_sha256": model_file_hashes(forget_model),
            "heal_model_sha256": model_file_hashes(heal_model),
        },
        "gates": gates,
    }
    terminal_status = {
        "PASS": "passed",
        "FAIL": "failed",
        "INCOMPLETE_SCALAR_SKIPPED": "incomplete_scalar_skipped",
    }[gates["probe1_verdict"]]
    seal_terminal(summary, terminal_status)
    print("\n" + "=" * 72)
    print("gates=" + json.dumps(gates, indent=2, default=str))
    print(f"PROBE 1 VERDICT: {gates['probe1_verdict']}")
    print(f"Wrote {root / 'probe1_summary.json'}")


if __name__ == "__main__":
    main()
