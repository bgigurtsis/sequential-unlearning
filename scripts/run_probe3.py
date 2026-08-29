"""Probe 3: certify late-lineage erasure trainability, fail closed.

The input is a final, sealed overall Probe 2 PASS. A clean parent is dosed at
Probe 2's scalar-65 alpha; the measured dose must land in [60, 70], and the
chosen concept must be PRESENT before training. Every saved erasure adapter is
merged and judged in step order, selecting the earliest semantic pass. Its
decay-scalar increase must stay within the precommitted collateral ceiling.

If the BF16-base arm fails, the fp32-base control runs through the identical
merge, judge, selection, and scalar pipeline. A passing control certifies the
fp32-base mitigation; skipping a required control or using a smoke path can
only produce INCOMPLETE. Completed roots are sealed by SHA-256 manifest.
"""

import argparse
import hashlib
import json
import math
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
from run_noise_sweep import validate_scalar_artifact
from run_probe1 import validate_probe2_aggregate as validate_probe2_archive_chain


PROBE3_VERSION = "late_erasure_certification_v2"
EXPECTED_PROBE2_SCOPE = "heavy_parent_repeat_and_probe2_aggregate"
V3_HEAVY_VERSION = "probe2_weight_noise_heavy_certification_v3"
V3_CONTROLLER_U = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0)
DEFAULT_MAX_ERASURE_SCALAR_INCREASE = 5.0
CANONICAL_CONCEPT_INDEX = 23
CANONICAL_FORGET_STEPS = 120
CANONICAL_SNAPSHOT_EVERY = 10
CANONICAL_BATCH_SIZE = 8
CANONICAL_MAX_NEW_TOKENS = 256
CANONICAL_SEED = 0
CANONICAL_CONCEPT_ID = "horror_films"
SEMANTIC_ONLY_EVAL_FLAGS = (
    "--skip-capability",
    "--skip-cumulative",
    "--skip-perplexity",
    "--skip-sea",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-model", required=True)
    parser.add_argument("--root", default="derisk/probe3_late_erasure_v2")
    parser.add_argument("--probe2-summary", required=True)
    parser.add_argument("--concepts", default="data/rehearsal_concepts.json")
    parser.add_argument("--concept-index", type=int, default=23)
    parser.add_argument("--alpha", type=float)
    parser.add_argument("--scalar-baseline", required=True)
    parser.add_argument("--scalar-anchor", required=True)
    parser.add_argument("--scalar-ladder", required=True)
    parser.add_argument("--dose-seed", type=int, default=7)
    parser.add_argument("--forget-steps", type=int, default=120)
    parser.add_argument("--snapshot-every", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--max-erasure-scalar-increase",
        type=float,
        default=DEFAULT_MAX_ERASURE_SCALAR_INCREASE,
    )
    parser.add_argument("--skip-fp32-control", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    return parser.parse_args()


def read_json(path):
    return _require_finite_json(
        json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite_json_constant,
        ),
        str(Path(path)),
    )


def _reject_nonfinite_json_constant(value):
    raise RuntimeError(f"non-finite JSON constant is forbidden: {value}")


def _require_finite_json(value, label="JSON payload"):
    if isinstance(value, float) and not math.isfinite(value):
        raise RuntimeError(f"{label} contains a non-finite number")
    if isinstance(value, dict):
        for key, child in value.items():
            _require_finite_json(child, f"{label}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _require_finite_json(child, f"{label}[{index}]")
    return value


def write_json(path, payload):
    _require_finite_json(payload)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256_of_file(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(payload):
    _require_finite_json(payload)
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def directory_file_hashes(path, exclude_names=()):
    root = Path(path)
    excluded = set(exclude_names)
    return {
        item.relative_to(root).as_posix(): sha256_of_file(item)
        for item in sorted(root.rglob("*"))
        if item.is_file() and item.name not in excluded
    }


def artifact_digest(path):
    path = Path(path)
    if path.is_file():
        return {"kind": "file", "sha256": sha256_of_file(path)}
    if path.is_dir():
        return {"kind": "directory", "files": directory_file_hashes(path)}
    raise FileNotFoundError(path)


def model_identity(path):
    path = Path(path).expanduser().resolve()
    if not path.is_dir():
        raise ValueError("--parent-model must be an exact local snapshot directory")
    weights = {
        item.name: sha256_of_file(item)
        for item in sorted(
            list(path.glob("*.safetensors")) + list(path.glob("*.bin"))
        )
    }
    if not weights:
        raise ValueError(f"no model weights found in {path}")
    support = {
        item.name: sha256_of_file(item)
        for item in sorted(item for item in path.iterdir() if item.is_file())
        if item.suffix not in {".safetensors", ".bin"}
        and item.name != "decay_dose.json"
    }
    identity = {
        "source_model": str(path),
        "weight_file_sha256": weights,
        "support_file_sha256": support,
    }
    identity["fingerprint"] = fingerprint(identity)
    return identity


def paths_overlap(left, right):
    left = Path(left).resolve()
    right = Path(right).resolve()
    return left == right or left in right.parents or right in left.parents


def validate_output_root(root, protected_roots):
    if any(paths_overlap(root, protected) for protected in protected_roots):
        raise ValueError(
            "Probe 3 output root must not overlap the clean parent or sealed "
            "Probe 2 archives"
        )


def probe2_protected_roots(summary_path, summary, scalar_inputs, parent_model):
    primary_root = Path(summary["primary_archive"]["root"]).resolve()
    roots = [
        Path(summary_path).resolve().parent,
        primary_root,
        Path(summary["heavy_parent"]["identity"]["source_model"]).resolve(),
        Path(parent_model).resolve(),
    ]
    roots.extend(path.resolve().parent.parent for path in scalar_inputs)
    if summary.get("certification_version") == V3_HEAVY_VERSION:
        roots.append(Path(summary["pilot_archive"]["root"]).resolve())
    return tuple(dict.fromkeys(roots))


def validate_canonical_concept(args, repo, concept):
    if args.smoke:
        return
    expected_path = (Path(repo) / "data" / "rehearsal_concepts.json").resolve()
    if Path(args.concepts).resolve() != expected_path:
        raise ValueError("Probe 3 certification requires the canonical concepts file")
    if concept.get("id") != CANONICAL_CONCEPT_ID:
        raise ValueError(
            f"Probe 3 concept {CANONICAL_CONCEPT_INDEX} must be "
            f"{CANONICAL_CONCEPT_ID}"
        )


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


def stage_marker_path(root, name):
    return Path(root) / "stages" / f"{name}.json"


def ensure_stage(root, name, config_fingerprint, inputs, outputs, action):
    """Run an immutable stage or validate its existing completion marker."""
    marker = stage_marker_path(root, name)
    stage_fp = fingerprint(
        {
            "probe3_version": PROBE3_VERSION,
            "stage": name,
            "config_fingerprint": config_fingerprint,
            "inputs": inputs,
        }
    )
    outputs = [Path(path) for path in outputs]
    if marker.exists():
        payload = read_json(marker)
        if payload.get("status") != "complete" or payload.get("fingerprint") != stage_fp:
            raise RuntimeError(f"stale or mismatched stage marker: {marker}")
        actual = {str(path): artifact_digest(path) for path in outputs}
        if actual != payload.get("outputs"):
            raise RuntimeError(f"completed stage outputs changed: {name}")
        return
    if any(path.exists() for path in outputs):
        raise RuntimeError(
            f"stage {name} has outputs without a completion marker; move them "
            "aside before resuming"
        )
    action()
    missing = [str(path) for path in outputs if not path.exists()]
    if missing:
        raise RuntimeError(f"stage {name} did not create outputs: {missing}")
    write_json(
        marker,
        {
            "status": "complete",
            "stage": name,
            "fingerprint": stage_fp,
            "inputs": inputs,
            "outputs": {str(path): artifact_digest(path) for path in outputs},
        },
    )


def validate_probe2_aggregate(summary, expected_policy, expected_policy_fingerprint):
    _require_finite_json(summary, "Probe 2 aggregate")
    gates = summary.get("gates", {})
    if summary.get("certification_scope") != EXPECTED_PROBE2_SCOPE:
        raise ValueError("Probe 3 requires the clean+heavy Probe 2 aggregate")
    if gates.get("probe2_verdict") != "PASS":
        raise ValueError("Probe 3 requires final overall Probe 2 PASS")
    for key in (
        "primary_manifest_verified",
        "primary_verdict_verified",
        "heavy_parent_selection_pass",
    ):
        if gates.get(key) is not True:
            raise ValueError(f"Probe 2 aggregate did not establish {key}")
    if gates.get("heavy_verdict") != "PASS":
        raise ValueError("Probe 2 aggregate heavy-parent verdict is not PASS")
    if summary.get("normalisation_version") != expected_policy:
        raise ValueError("Probe 2 aggregate uses the wrong normalisation policy")
    if summary.get("normalisation_policy_fingerprint") != expected_policy_fingerprint:
        raise ValueError("Probe 2 aggregate policy fingerprint does not match anchors")
    primary = summary.get("primary_archive", {})
    for key in (
        "manifest_sha256",
        "summary_sha256",
        "run_config_sha256",
        "parent_identity_sha256",
    ):
        value = primary.get(key)
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"Probe 2 aggregate lacks sealed primary {key}")
        try:
            int(value, 16)
        except ValueError as error:
            raise ValueError(f"Probe 2 aggregate has invalid primary {key}") from error
    if not isinstance(primary.get("root"), str):
        raise ValueError("Probe 2 aggregate lacks the sealed primary root")
    clean_ruler = summary.get("clean_ruler", {})
    if clean_ruler.get("policy_fingerprint") != expected_policy_fingerprint:
        raise ValueError("Probe 2 aggregate clean ruler fingerprint changed")
    for key in ("baseline", "terminal", "ladder"):
        value = clean_ruler.get(key)
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"Probe 2 aggregate lacks clean-ruler {key} hash")
    heavy_identity = summary.get("heavy_parent", {}).get("identity", {})
    alpha = heavy_identity.get("administered_alpha")
    if alpha is None or not 0.0 < float(alpha) < 1.0:
        raise ValueError("Probe 2 aggregate does not provide the scalar-65 parent alpha")
    scalar = heavy_identity.get("measured_global_scalar")
    if scalar is None or not 60.0 <= float(scalar) <= 70.0:
        raise ValueError("Probe 2 aggregate heavy parent is outside scalar band")
    if heavy_identity.get("dose_seed") != 7:
        raise ValueError("Probe 2 aggregate heavy parent does not use held-out seed 7")
    recorded_fingerprint = heavy_identity.get("fingerprint")
    identity_body = {
        key: value for key, value in heavy_identity.items() if key != "fingerprint"
    }
    if recorded_fingerprint != fingerprint(identity_body):
        raise ValueError("Probe 2 aggregate heavy-parent fingerprint is invalid")
    for key in ("weight_file_sha256", "support_file_sha256"):
        if not isinstance(heavy_identity.get(key), dict) or not heavy_identity[key]:
            raise ValueError(f"Probe 2 aggregate heavy parent lacks {key}")
    if summary.get("certification_version") == V3_HEAVY_VERSION:
        beta = summary.get("beta")
        mapping = summary.get("controller_mapping", {})
        alpha_by_u = {
            float(key): float(value)
            for key, value in summary.get("physical_alpha_by_u", {}).items()
        }
        if (
            beta not in {0.1, 1.0}
            or summary.get("controller_coordinate") != "u"
            or tuple(float(value) for value in summary.get("controller_u", ()))
            != V3_CONTROLLER_U
            or set(alpha_by_u) != set(V3_CONTROLLER_U)
            or float(alpha_by_u[0.0]) != 0.0
            or float(alpha_by_u[1.0]) != 1.0
            or mapping.get("fingerprint") != heavy_identity.get("mapping_fingerprint")
            or float(heavy_identity.get("controller_u", -1.0)) != 0.65
            or float(heavy_identity.get("beta", -1.0)) != float(beta)
            or heavy_identity.get("construction") != "one_shot_no_search"
        ):
            raise ValueError("Probe 2 v3 heavy controller identity is invalid")
        for key in (
            "per_dose_range_gate_pass",
            "raw_mean_nondecrease_gate_pass",
            "no_refit_bisection_or_extra_points",
        ):
            if gates.get(key) is not True:
                raise ValueError(f"Probe 2 v3 heavy aggregate did not establish {key}")
    return float(alpha)


def validate_probe2_inputs(
    summary_path,
    expected_policy_fingerprint,
    parent_model,
    scalar_inputs,
):
    """Verify both Probe 2 archives and the final heavy-parent linkage."""
    summary_path = Path(summary_path).resolve()
    summary = validate_probe2_archive_chain(
        summary_path,
        expected_policy_fingerprint,
        parent_model,
        scalar_inputs,
    )
    alpha = validate_probe2_aggregate(
        summary, V2_POLICY, expected_policy_fingerprint
    )
    if summary.get("certification_version") == V3_HEAVY_VERSION:
        mapping = summary.get("_verified_controller_mapping", {})
        mapping_heavy = mapping.get("heavy_parent", {})
        heavy_identity = summary.get("heavy_parent", {}).get("identity", {})
        if (
            float(mapping_heavy.get("u", -1.0)) != 0.65
            or abs(
                float(mapping_heavy.get("physical_alpha", -1.0)) - float(alpha)
            )
            > 1e-12
            or mapping.get("fingerprint")
            != heavy_identity.get("mapping_fingerprint")
        ):
            raise ValueError("Probe 2 v3 heavy parent is not the frozen g(.65) dose")
    heavy = summary["heavy_parent"]
    identity = heavy["identity"]
    heavy_root = summary_path.parent
    identity_path = Path(heavy.get("identity_json", "")).resolve()
    checkpoint = Path(heavy.get("checkpoint", "")).resolve()
    if heavy_root not in identity_path.parents or not identity_path.is_file():
        raise ValueError("Probe 2 heavy-parent identity is outside its sealed archive")
    if read_json(identity_path) != identity:
        raise ValueError("Probe 2 heavy-parent identity JSON does not match summary")
    if Path(identity.get("source_model", "")).resolve() != checkpoint:
        raise ValueError("Probe 2 heavy-parent checkpoint/identity linkage changed")
    if heavy_root not in checkpoint.parents or not checkpoint.is_dir():
        raise ValueError("Probe 2 heavy-parent checkpoint is not retained in its archive")
    checkpoint_identity = model_identity(checkpoint)
    if (
        checkpoint_identity["weight_file_sha256"]
        != identity.get("weight_file_sha256")
        or checkpoint_identity["support_file_sha256"]
        != identity.get("support_file_sha256")
    ):
        raise ValueError("Probe 2 retained heavy-parent checkpoint bytes changed")
    clean_parent = model_identity(parent_model)
    if (
        identity.get("clean_parent_identity_fingerprint")
        != clean_parent["fingerprint"]
    ):
        raise ValueError("Probe 2 heavy parent is not linked to the clean parent")
    return summary, alpha


def semantic_result(
    judgement,
    expected_group_ids,
    expected_judge_model,
    expected_concept_id,
):
    if judgement.get("judge_model") != str(expected_judge_model):
        raise RuntimeError("semantic judgement used the wrong clean judge")
    if judgement.get("concept_id") != expected_concept_id:
        raise RuntimeError("semantic judgement names the wrong concept")
    groups = judgement.get("groups", {})
    if set(groups) != set(expected_group_ids):
        raise RuntimeError("semantic judgement group coverage mismatch")
    group_verdicts = {
        group_id: result.get("verdict") for group_id, result in groups.items()
    }
    if any(
        verdict not in {"PRESENT", "ABSENT", "UNCLEAR"}
        for verdict in group_verdicts.values()
    ):
        raise RuntimeError("semantic judgement contains an invalid verdict")
    return {
        "semantic_absent": all(
            group_verdicts[group_id] == "ABSENT"
            for group_id in expected_group_ids
        ),
        "semantic_present": all(
            group_verdicts[group_id] == "PRESENT"
            for group_id in expected_group_ids
        ),
        "group_verdicts": group_verdicts,
    }


def snapshot_step(path):
    name = Path(path).name
    if not name.startswith("step") or not name[4:].isdigit():
        raise ValueError(f"invalid adapter snapshot name: {name}")
    return int(name[4:])


def select_earliest_semantic_snapshot(records):
    passing = [record for record in records if record["semantic_absent"]]
    return min(passing, key=lambda record: record["step"]) if passing else None


def scalar_from_components(
    path,
    baseline,
    positive,
    negative,
    expected_policy_fingerprint,
    *,
    expected_model,
    expected_judge,
    expected_tokenizer,
    expected_prompt_sha256,
    expected_weight_sha256,
    expected_model_support_sha256,
    expected_clean_weight_sha256,
    expected_clean_support_sha256,
):
    payload = validate_scalar_artifact(
        path,
        expected_model=expected_model,
        expected_judge=expected_judge,
        expected_tokenizer=expected_tokenizer,
        expected_prompt_sha256=expected_prompt_sha256,
        expected_weight_sha256=expected_weight_sha256,
        expected_model_support_sha256=expected_model_support_sha256,
        expected_tokenizer_support_sha256=expected_clean_support_sha256,
        expected_judge_support_sha256=expected_clean_support_sha256,
        expected_judge_weight_sha256=expected_clean_weight_sha256,
        expected_policy=V2_POLICY,
        expected_policy_fingerprint=expected_policy_fingerprint,
    )
    normalised, scalar, directions = normalise_components_bidirectional(
        payload["components"], baseline, positive, negative
    )
    reported = payload.get("scalar_0_100")
    if reported is None or abs(float(reported) - scalar) > 1e-9:
        raise RuntimeError(f"scalar artifact does not match its components: {path}")
    return scalar, normalised, directions


def classify_probe3(bf16, fp32, *, skipped, smoke):
    if smoke:
        return "INCOMPLETE"
    if bf16["arm_pass"]:
        return "PASS"
    if skipped or fp32 is None:
        return "INCOMPLETE"
    return "PASS" if fp32["arm_pass"] else "FAIL"


def required_runtime_mode(bf16, fp32):
    if bf16["arm_pass"]:
        return "bf16_base"
    if fp32 is not None and fp32["arm_pass"]:
        return "fp32_base"
    return None


def validate_canonical_config(args):
    if args.batch_size <= 0 or args.max_new_tokens <= 0:
        raise ValueError("batch size and max-new-tokens must be positive")
    if args.smoke:
        return
    actual = {
        "concept_index": args.concept_index,
        "forget_steps": args.forget_steps,
        "snapshot_every": args.snapshot_every,
        "batch_size": args.batch_size,
        "max_new_tokens": args.max_new_tokens,
        "seed": args.seed,
    }
    expected = {
        "concept_index": CANONICAL_CONCEPT_INDEX,
        "forget_steps": CANONICAL_FORGET_STEPS,
        "snapshot_every": CANONICAL_SNAPSHOT_EVERY,
        "batch_size": CANONICAL_BATCH_SIZE,
        "max_new_tokens": CANONICAL_MAX_NEW_TOKENS,
        "seed": CANONICAL_SEED,
    }
    if actual != expected:
        raise ValueError(
            f"Probe 3 certification configuration mismatch: expected={expected} "
            f"actual={actual}"
        )


def validate_trainer_grid(
    adapter_root,
    *,
    model_id,
    forget_data,
    num_steps,
    snapshot_every,
    seed,
    fp32_base,
):
    adapter_root = Path(adapter_root).resolve()
    state = read_json(adapter_root / "stop_state.json")
    config = read_json(adapter_root / "run_config.json")
    expected_config = {
        "model_id": str(model_id),
        "forget_data": str(forget_data),
        "retain_data": "data/retain.json",
        "chat_retain_data": "data/retain_chat.json",
        "output_dir": str(adapter_root),
        "num_steps": num_steps,
        "save_every": snapshot_every,
        "eval_every": snapshot_every,
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
        "seed": seed,
        "external_semantic_selection": True,
        "fp32_base": fp32_base,
    }
    for key, value in expected_config.items():
        if config.get(key) != value:
            raise RuntimeError(f"trainer configuration mismatch for {key}")
    expected_steps = list(range(snapshot_every, num_steps + 1, snapshot_every))
    snapshots = sorted(
        (
            path
            for path in adapter_root.glob("step[0-9][0-9][0-9]")
            if path.is_dir()
        ),
        key=snapshot_step,
    )
    actual_steps = [snapshot_step(path) for path in snapshots]
    if actual_steps != expected_steps:
        raise RuntimeError(
            f"trainer snapshot grid mismatch: expected={expected_steps} "
            f"actual={actual_steps}"
        )
    final = adapter_root / f"step{num_steps:03d}"
    if (
        state.get("external_semantic_selection") is not True
        or state.get("stop_reason") != "step_budget_exhausted"
        or state.get("stopped_at_step") != num_steps
        or Path(state.get("final_adapter", "")).resolve() != final
    ):
        raise RuntimeError("trainer stop state does not certify the complete grid")
    return state, snapshots


def write_manifest(root):
    root = Path(root).resolve()
    output = root / "MANIFEST.sha256"
    temporary = output.with_name(output.name + ".tmp")
    if temporary.exists():
        temporary.unlink()
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path not in {output, temporary}
    )
    lines = [
        f"{sha256_of_file(path)}  {path.relative_to(root).as_posix()}"
        for path in files
    ]
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(output)
    if not verify_manifest(root):
        raise RuntimeError("Probe 3 archive did not seal")


def verify_manifest(root):
    root = Path(root).resolve()
    manifest = root / "MANIFEST.sha256"
    if not manifest.exists():
        return False
    expected = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        relative_path = Path(relative)
        if (
            not separator
            or len(digest) != 64
            or relative_path.is_absolute()
            or ".." in relative_path.parts
        ):
            raise RuntimeError(f"malformed Probe 3 manifest line: {line!r}")
        try:
            int(digest, 16)
        except ValueError as error:
            raise RuntimeError(
                f"malformed Probe 3 manifest digest: {digest!r}"
            ) from error
        key = relative_path.as_posix()
        if key in expected:
            raise RuntimeError(f"duplicate Probe 3 manifest entry: {key}")
        expected[key] = digest.lower()
    actual = {
        path.relative_to(root).as_posix(): sha256_of_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != manifest
    }
    if actual != expected:
        raise RuntimeError(f"sealed Probe 3 archive changed: {root}")
    return True


def main():
    args = parse_args()
    repo = Path.cwd().resolve()
    root = Path(args.root).resolve()
    if verify_manifest(root):
        summary = read_json(root / "probe3_summary.json")
        print(f"Immutable Probe 3 archive: verdict={summary['gates']['probe3_verdict']}")
        return
    if args.forget_steps <= 0 or args.snapshot_every <= 0:
        raise ValueError("forget steps and snapshot interval must be positive")
    if args.forget_steps % args.snapshot_every:
        raise ValueError("forget steps must be divisible by snapshot interval")
    if args.max_erasure_scalar_increase != DEFAULT_MAX_ERASURE_SCALAR_INCREASE:
        raise ValueError("certification scalar-increase ceiling must be exactly 5.0")
    validate_canonical_config(args)
    parent = model_identity(args.parent_model)
    args.parent_model = parent["source_model"]
    baseline, positive, negative, anchor_sources = load_bidirectional_anchors(
        args.scalar_baseline, args.scalar_anchor, args.scalar_ladder
    )
    policy_fp = bidirectional_policy_fingerprint(
        baseline, positive, negative, anchor_sources
    )
    scalar_inputs = (
        Path(args.scalar_baseline),
        Path(args.scalar_anchor),
        Path(args.scalar_ladder),
    )
    probe2_summary, certified_alpha = validate_probe2_inputs(
        args.probe2_summary,
        policy_fp,
        args.parent_model,
        scalar_inputs,
    )
    heavy_identity = probe2_summary["heavy_parent"]["identity"]
    controller_beta = float(heavy_identity.get("beta", 1.0))
    controller_u = heavy_identity.get("controller_u")
    validate_output_root(
        root,
        probe2_protected_roots(
            args.probe2_summary,
            probe2_summary,
            scalar_inputs,
            args.parent_model,
        ),
    )
    if heavy_identity.get("clean_parent_identity_fingerprint") != parent["fingerprint"]:
        raise ValueError("Probe 2 aggregate and Probe 3 clean parent identities differ")
    alpha = certified_alpha if args.alpha is None else float(args.alpha)
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be inside (0,1)")
    if alpha != certified_alpha:
        raise ValueError("certification alpha must equal the sealed heavy-parent alpha")
    if args.dose_seed != 7:
        raise ValueError("certification dose seed must be the sealed held-out seed 7")
    concepts = read_json(args.concepts)
    if not 1 <= args.concept_index <= len(concepts):
        raise ValueError("concept index is out of range")
    concept = concepts[args.concept_index - 1]
    validate_canonical_concept(args, repo, concept)
    expected_group_ids = tuple(group["id"] for group in concept["groups"])
    if (
        not expected_group_ids
        or "core" not in expected_group_ids
        or len(expected_group_ids) != len(set(expected_group_ids))
    ):
        raise ValueError("concept semantic groups are empty, duplicated, or lack core")
    python = Path(sys.executable).absolute()
    log = root / "commands.log"
    input_paths = {
        "probe2_summary": Path(args.probe2_summary),
        "concepts": Path(args.concepts),
        "scalar_baseline": Path(args.scalar_baseline),
        "scalar_anchor": Path(args.scalar_anchor),
        "scalar_ladder": Path(args.scalar_ladder),
        "retain": repo / "data/retain.json",
        "chat_retain": repo / "data/retain_chat.json",
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
    missing_inputs = [str(path) for path in input_paths.values() if not path.is_file()]
    if missing_inputs:
        raise FileNotFoundError(
            "Probe 3 certification inputs are missing: " + ", ".join(missing_inputs)
        )
    input_files = {
        name: sha256_of_file(path) for name, path in input_paths.items()
    }
    code_files = {
        name: sha256_of_file(repo / "scripts" / name)
        for name in (
            "run_probe3.py",
            "build_probe1_day.py",
            "build_rehearsal_day.py",
            "build_onpolicy_forget.py",
            "train_bounded_forget.py",
            "merge.py",
            "eval_rehearsal_checkpoint.py",
            "judge_rehearsal_generations.py",
            "eval_decay_scalar.py",
            "decay_scalar_normalization.py",
            "run_noise_sweep.py",
            "run_probe1.py",
        )
    }
    config = {
        "probe3_version": PROBE3_VERSION,
        "parent_identity": parent,
        "sealed_heavy_parent_identity": heavy_identity,
        "concept_index": args.concept_index,
        "concept_id": concept["id"],
        "alpha": alpha,
        "certified_alpha_65": certified_alpha,
        "dose_seed": args.dose_seed,
        "beta": controller_beta,
        "controller_u": controller_u,
        "controller_mapping_fingerprint": heavy_identity.get(
            "mapping_fingerprint"
        ),
        "forget_steps": args.forget_steps,
        "snapshot_every": args.snapshot_every,
        "batch_size": args.batch_size,
        "max_new_tokens": args.max_new_tokens,
        "seed": args.seed,
        "max_erasure_scalar_increase": args.max_erasure_scalar_increase,
        "normalisation_policy": V2_POLICY,
        "normalisation_policy_fingerprint": policy_fp,
        "skip_fp32_control": args.skip_fp32_control,
        "smoke": args.smoke,
        "input_file_sha256": input_files,
        "code_file_sha256": code_files,
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip(),
    }
    config["fingerprint"] = fingerprint(config)
    expected_prompt_sha256 = {
        "battery": input_files["decay_scalar_prompts"],
        "capability": input_files["rehearsal_capability_prompts"],
        "survival": input_files["conversational_survival_generations"],
    }
    root.mkdir(parents=True, exist_ok=True)
    config_path = root / "run_config.json"
    if config_path.exists():
        if read_json(config_path) != config:
            raise RuntimeError("Probe 3 run configuration changed; use a new root")
    else:
        write_json(config_path, config)
    parent_identity_path = root / "parent_identity.json"
    if parent_identity_path.exists():
        if read_json(parent_identity_path) != parent:
            raise RuntimeError("Probe 3 parent identity changed")
    else:
        write_json(parent_identity_path, parent)

    day = root / "day"
    day_outputs = [
        day / name
        for name in (
            "concept.json",
            "clozes.json",
            "probes.json",
            "probes_conjugate.json",
            "forget_prompts_diversified.json",
        )
    ]
    ensure_stage(
        root,
        "compile_day",
        config["fingerprint"],
        {"concepts": input_files["concepts"], "concept_index": args.concept_index},
        day_outputs,
        lambda: run_command(
            [python, "scripts/build_probe1_day.py", str(args.concept_index), day,
             "--concepts", args.concepts, "--seed", str(args.seed)],
            log,
            repo,
        ),
    )
    # Reuse the exact sealed seed-7 heavy parent. Redrawing would add an
    # unnecessary model-serialization equivalence assumption to the probe.
    dosed = heavy_parent_path
    sealed_heavy_model = model_identity(dosed)
    if sealed_heavy_model["weight_file_sha256"] != heavy_identity.get(
        "weight_file_sha256"
    ):
        raise RuntimeError("sealed Probe 3 parent weight hashes changed")
    if sealed_heavy_model["support_file_sha256"] != heavy_identity.get(
        "support_file_sha256"
    ):
        raise RuntimeError("sealed Probe 3 parent support hashes changed")
    dosed_digest = artifact_digest(dosed)

    def eval_scalar(model_path, output):
        run_command(
            [python, "scripts/eval_decay_scalar.py", model_path, output,
             "--batch-size", str(args.batch_size), "--max-new-tokens",
             str(args.max_new_tokens), "--seed", "0", "--judge-model",
             args.parent_model, "--tokenizer-model", args.parent_model,
             "--baseline-json", args.scalar_baseline, "--anchor-json",
             args.scalar_anchor, "--ladder-json", args.scalar_ladder,
             "--normalisation-policy", V2_POLICY],
            log,
            repo,
        )

    dosed_scalar_path = root / "dosed_scalar.json"
    ensure_stage(
        root, "dosed_scalar", config["fingerprint"],
        {"dosed": dosed_digest, "policy": policy_fp},
        [dosed_scalar_path], lambda: eval_scalar(dosed, dosed_scalar_path),
    )
    administered, administered_components, administered_directions = (
        scalar_from_components(
            dosed_scalar_path,
            baseline,
            positive,
            negative,
            policy_fp,
            expected_model=str(dosed),
            expected_judge=args.parent_model,
            expected_tokenizer=args.parent_model,
            expected_prompt_sha256=expected_prompt_sha256,
            expected_weight_sha256=sealed_heavy_model["weight_file_sha256"],
            expected_model_support_sha256=sealed_heavy_model[
                "support_file_sha256"
            ],
            expected_clean_weight_sha256=parent["weight_file_sha256"],
            expected_clean_support_sha256=parent["support_file_sha256"],
        )
    )

    def judge_eval(eval_path, output_path, scratch_name):
        scratch = root / "scratch" / scratch_name
        step_dir = scratch / "step01_probe"
        if scratch.exists():
            raise RuntimeError(f"stale judge scratch directory: {scratch}")
        step_dir.mkdir(parents=True)
        shutil.copy2(eval_path, step_dir / "post_eval.json")
        run_command(
            [python, "scripts/judge_rehearsal_generations.py", "--root", scratch,
             "--judge-model", args.parent_model],
            log,
            repo,
        )
        shutil.copy2(step_dir / "semantic_judgement.json", output_path)
        shutil.rmtree(scratch)

    pre_dir = root / "pre_erasure"
    pre_eval = pre_dir / "rehearsal_eval.json"
    pre_judge = pre_dir / "judgement.json"

    def run_pre():
        pre_dir.mkdir(parents=True)
        run_command(
            [python, "scripts/eval_rehearsal_checkpoint.py", dosed, pre_eval,
             "--day-dir", day, "--max-new-tokens", "64",
             *SEMANTIC_ONLY_EVAL_FLAGS, "--tokenizer-model", args.parent_model],
            log,
            repo,
        )
        judge_eval(pre_eval, pre_judge, "pre_erasure")

    ensure_stage(
        root, "pre_erasure_semantics", config["fingerprint"],
        {"dosed": dosed_digest,
         "day": [artifact_digest(path) for path in day_outputs]},
        [pre_eval, pre_judge], run_pre,
    )
    pre_semantic = semantic_result(
        read_json(pre_judge),
        expected_group_ids,
        args.parent_model,
        concept["id"],
    )
    prerequisite_pass = 60.0 <= administered <= 70.0 and pre_semantic["semantic_present"]
    if not prerequisite_pass:
        gates = {
            "probe3_verdict": "INCOMPLETE",
            "incomplete_reason": "invalid_administered_parent_or_pre_erasure_absent",
            "administered_scalar": administered,
            "administered_in_band": 60.0 <= administered <= 70.0,
            "pre_erasure": pre_semantic,
        }
        summary = {
            "probe3_version": PROBE3_VERSION,
            "concept": {"index": args.concept_index, **concept},
            "config_fingerprint": config["fingerprint"],
            "normalisation_policy": V2_POLICY,
            "normalisation_policy_fingerprint": policy_fp,
            "gates": gates,
        }
        summary_path = root / "probe3_summary.json"
        write_json(summary_path, summary)
        write_json(
            root / "COMPLETE.json",
            {
                "status": "incomplete",
                "verdict": "INCOMPLETE",
                "summary_sha256": sha256_of_file(summary_path),
                "config_fingerprint": config["fingerprint"],
            },
        )
        write_manifest(root)
        print("PROBE 3 VERDICT: INCOMPLETE")
        return

    onpolicy = root / "forget_onpolicy.json"
    ensure_stage(
        root, "onpolicy_forget", config["fingerprint"],
        {"dosed": dosed_digest, "prompts": artifact_digest(day_outputs[-1])},
        [onpolicy],
        lambda: run_command(
            [python, "scripts/build_onpolicy_forget.py", "--model-id", dosed,
             "--input", day_outputs[-1], "--output", onpolicy, "--batch-size", "4",
             "--max-new-tokens", "64"],
            log,
            repo,
        ),
    )

    def run_arm(name, fp32_base):
        arm_root = root / name
        adapter_root = arm_root / "adapters"
        stop_state = adapter_root / "stop_state.json"

        def train():
            command = [python, "scripts/train_bounded_forget.py", "--model-id", dosed,
                       "--forget-data", onpolicy, "--output-dir", adapter_root,
                       "--num-steps", str(args.forget_steps), "--save-every",
                       str(args.snapshot_every), "--eval-every",
                       str(args.snapshot_every), "--seed", str(args.seed),
                       "--external-semantic-selection"]
            if fp32_base:
                command.append("--fp32-base")
            run_command(command, log, repo)

        ensure_stage(
            root, f"{name}_train", config["fingerprint"],
            {"dosed": dosed_digest, "onpolicy": artifact_digest(onpolicy)},
            [adapter_root], train,
        )
        state, snapshots = validate_trainer_grid(
            adapter_root,
            model_id=dosed,
            forget_data=onpolicy,
            num_steps=args.forget_steps,
            snapshot_every=args.snapshot_every,
            seed=args.seed,
            fp32_base=fp32_base,
        )
        records = []
        for snapshot in snapshots:
            step = snapshot_step(snapshot)
            evidence = arm_root / "snapshots" / f"step{step:03d}"
            rehearsal = evidence / "rehearsal_eval.json"
            judgement = evidence / "judgement.json"

            def evaluate_snapshot():
                evidence.mkdir(parents=True)
                temporary_model = arm_root / "temporary_models" / f"step{step:03d}"
                temporary_model.parent.mkdir(parents=True, exist_ok=True)
                if temporary_model.exists():
                    raise RuntimeError(f"stale temporary merge: {temporary_model}")
                run_command([python, "scripts/merge.py", snapshot, temporary_model, dosed], log, repo)
                run_command(
                    [python, "scripts/eval_rehearsal_checkpoint.py", temporary_model,
                     rehearsal, "--day-dir", day, "--max-new-tokens", "64",
                     *SEMANTIC_ONLY_EVAL_FLAGS,
                     "--tokenizer-model", args.parent_model],
                    log,
                    repo,
                )
                judge_eval(rehearsal, judgement, f"{name}_step{step:03d}")
                shutil.rmtree(temporary_model)

            ensure_stage(
                root, f"{name}_snapshot_{step:03d}", config["fingerprint"],
                {"adapter": artifact_digest(snapshot),
                 "day": artifact_digest(day / "concept.json")},
                [rehearsal, judgement], evaluate_snapshot,
            )
            records.append({
                "step": step,
                "adapter": str(snapshot),
                "rehearsal_eval": str(rehearsal),
                "judgement": str(judgement),
                **semantic_result(
                    read_json(judgement),
                    expected_group_ids,
                    args.parent_model,
                    concept["id"],
                ),
            })
        selected = select_earliest_semantic_snapshot(records)
        outcome = selected or records[-1]
        selected_model = arm_root / "outcome_model"
        scalar_path = arm_root / "outcome_scalar.json"

        def merge_and_scalar():
            run_command([python, "scripts/merge.py", outcome["adapter"], selected_model, dosed], log, repo)
            eval_scalar(selected_model, scalar_path)

        ensure_stage(
            root, f"{name}_outcome", config["fingerprint"],
            {"adapter": artifact_digest(outcome["adapter"]), "policy": policy_fp},
            [selected_model, scalar_path], merge_and_scalar,
        )
        outcome_identity = model_identity(selected_model)
        after, after_components, after_directions = scalar_from_components(
            scalar_path,
            baseline,
            positive,
            negative,
            policy_fp,
            expected_model=str(selected_model),
            expected_judge=args.parent_model,
            expected_tokenizer=args.parent_model,
            expected_prompt_sha256=expected_prompt_sha256,
            expected_weight_sha256=outcome_identity["weight_file_sha256"],
            expected_model_support_sha256=outcome_identity[
                "support_file_sha256"
            ],
            expected_clean_weight_sha256=parent["weight_file_sha256"],
            expected_clean_support_sha256=parent["support_file_sha256"],
        )
        increase = after - administered
        semantic_pass = selected is not None
        scalar_pass = increase <= args.max_erasure_scalar_increase
        within_budget = bool(selected and selected["step"] <= args.forget_steps)
        return {
            "name": name, "fp32_base": fp32_base, "trainer_stop_state": state,
            "snapshots": records, "selected_snapshot": selected,
            "outcome_snapshot": outcome, "post_erasure_scalar": after,
            "outcome_model_identity": outcome_identity,
            "post_erasure_normalised_components": after_components,
            "post_erasure_directions": after_directions,
            "scalar_increase_from_erasure": increase,
            "max_scalar_increase": args.max_erasure_scalar_increase,
            "semantic_pass": semantic_pass, "scalar_collateral_pass": scalar_pass,
            "within_step_budget": within_budget,
            "arm_pass": bool(semantic_pass and scalar_pass and within_budget),
        }

    bf16 = run_arm("bf16", False)
    fp32 = None
    if not bf16["arm_pass"] and not args.skip_fp32_control and not args.smoke:
        fp32 = run_arm("fp32", True)
    verdict = classify_probe3(bf16, fp32, skipped=args.skip_fp32_control, smoke=args.smoke)
    runtime_mode = required_runtime_mode(bf16, fp32) if verdict == "PASS" else None
    precision_artefact = bool(
        not bf16["arm_pass"] and fp32 is not None and fp32["arm_pass"]
    )
    gates = {
        "probe3_verdict": verdict,
        "required_runtime_mode": runtime_mode,
        "required_probe2_overall_pass": True,
        "administered_scalar": administered,
        "administered_in_band": True,
        "administered_normalised_components": administered_components,
        "administered_directions": administered_directions,
        "pre_erasure": pre_semantic,
        "bf16": bf16,
        "fp32_control": fp32,
        "failure_is_precision_artefact": precision_artefact,
        "skip_or_smoke_forced_incomplete": bool(
            args.smoke or (args.skip_fp32_control and not bf16["arm_pass"])
        ),
    }
    summary = {
        "probe3_version": PROBE3_VERSION,
        "concept": {"index": args.concept_index, **concept},
        "parent_model": args.parent_model,
        "parent_identity": parent,
        "administered_parent_identity": heavy_identity,
        "probe2_summary": args.probe2_summary,
        "probe2_summary_sha256": input_files["probe2_summary"],
        "config_fingerprint": config["fingerprint"],
        "normalisation_policy": V2_POLICY,
        "normalisation_policy_fingerprint": policy_fp,
        "component_anchor_sources": anchor_sources,
        "gates": gates,
    }
    summary_path = root / "probe3_summary.json"
    write_json(summary_path, summary)
    write_json(
        root / "COMPLETE.json",
        {"status": "complete" if verdict in {"PASS", "FAIL"} else "incomplete",
         "verdict": verdict, "summary_sha256": sha256_of_file(summary_path),
         "config_fingerprint": config["fingerprint"]},
    )
    write_manifest(root)
    print("\n" + "=" * 72)
    print("gates=" + json.dumps(gates, indent=2, default=str))
    print(f"PROBE 3 VERDICT: {verdict}")
    print(f"Sealed {root / 'MANIFEST.sha256'}")


if __name__ == "__main__":
    main()
