"""Seal an interrupted canonical Probe 2 v2 primary as a proven FAIL.

This is an inference-free terminalizer for one precise interrupted state: all
three seeds at alpha 0.05 and 0.1 are complete, while the alpha 0.2 seed-0
checkpoint was drawn and evaluation reached 32/196 generations but produced
no scalar artifact.  It validates the complete frozen
instrument and artifacts, proves that the alpha-0.1 leave-one-out gate cannot
possibly meet the three-point bar, archives the interrupted checkpoint's dose
provenance, deletes only that redrawable checkpoint, and atomically seals the
canonical primary root.  It has no PASS path.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from decay_scalar_normalization import (
    V2_POLICY,
    WEIGHTS,
    bidirectional_policy_fingerprint,
    load_bidirectional_anchors,
    normalise_components_bidirectional,
)
from run_noise_sweep import (
    DEFAULT_ALPHAS,
    DEFAULT_SEEDS,
    fingerprint,
    model_weight_hashes,
    pchip_eval,
    read_ladder_gate,
    sha256_of_file,
    support_file_hashes,
    validate_ladder_artifact,
    validate_scalar_artifact,
)


COMPLETED_ALPHAS = (0.05, 0.1)
PARTIAL_ALPHA = 0.2
PARTIAL_SEED = 0
LOO_HELD_ALPHA = 0.1
SCALAR_MIN = 0.0
SCALAR_MAX = 100.0
LOO_ERROR_LIMIT = 3.0
SUMMARY_NAME = "sweep_summary_bidirectional_v2.json"
CERTIFICATE_NAME = "probe2_impossibility_certificate.json"
ABORTED_RECORD_NAME = "aborted_alpha0.2_seed0.json"
ABORTED_SIDECAR_NAME = "aborted_checkpoint_decay_dose.json"
FINALIZER_ARCHIVE = Path("source") / "finalize_probe2_impossible.py"
EXPECTED_INSTRUMENT_PATHS = (
    "scripts/apply_decay_noise.py",
    "scripts/build_corruption_ladder.py",
    "scripts/decay_scalar_normalization.py",
    "scripts/eval_decay_scalar.py",
    "scripts/run_noise_sweep.py",
    "data/decay_scalar_prompts.json",
    "data/rehearsal_capability_prompts.json",
    "data/conversational_survival_generations.json",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-model", required=True)
    parser.add_argument("--root", default="derisk/probe2_noise_v2")
    parser.add_argument(
        "--source-commit",
        help=(
            "commit whose scripts/finalize_probe2_impossible.py blob must "
            "exactly equal the executing source (defaults to HEAD)"
        ),
    )
    return parser.parse_args()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json_atomic(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def copy_file_atomic(source, destination):
    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    with source.open("rb") as input_handle, temporary.open("wb") as output_handle:
        shutil.copyfileobj(input_handle, output_handle)
        output_handle.flush()
    temporary.replace(destination)
    if sha256_of_file(source) != sha256_of_file(destination):
        raise RuntimeError(f"atomic archive copy verification failed: {destination}")


def discard_atomic_copy_temp(destination):
    temporary = Path(destination).with_name(Path(destination).name + ".tmp")
    if temporary.is_file():
        temporary.unlink()


def parse_manifest_line(line):
    digest, separator, relative = line.partition("  ")
    relative_path = Path(relative)
    if (
        not separator
        or len(digest) != 64
        or relative_path.is_absolute()
        or ".." in relative_path.parts
    ):
        raise RuntimeError(f"malformed manifest line: {line!r}")
    try:
        int(digest, 16)
    except ValueError as error:
        raise RuntimeError(f"malformed manifest digest: {digest!r}") from error
    return digest.lower(), relative_path


def verify_manifest(root):
    root = Path(root).resolve()
    manifest = root / "MANIFEST.sha256"
    if not manifest.is_file():
        raise RuntimeError(f"archive is not sealed: {root}")
    entries = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        digest, relative = parse_manifest_line(line)
        key = relative.as_posix()
        if key in entries:
            raise RuntimeError(f"duplicate manifest entry: {key}")
        entries[key] = digest
    actual = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and path != manifest
    }
    if set(entries) != set(actual):
        raise RuntimeError("manifest does not exactly cover the Probe 2 archive")
    for relative, expected in entries.items():
        if sha256_of_file(actual[relative]) != expected:
            raise RuntimeError(f"manifest hash mismatch: {relative}")
    return {
        "path": str(manifest),
        "sha256": sha256_of_file(manifest),
        "entry_count": len(entries),
    }


def write_manifest_atomic(root):
    root = Path(root).resolve()
    output = root / "MANIFEST.sha256"
    temporary = root / "MANIFEST.sha256.tmp"
    if temporary.exists():
        temporary.unlink()
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
    return verify_manifest(root)


def resolve_source_commit(repo, source_commit=None):
    result = subprocess.run(
        ["git", "rev-parse", source_commit or "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise RuntimeError("cannot bind finalizer to a committed repository revision")
    return commit


def read_committed_finalizer_blob(repo, commit):
    result = subprocess.run(
        ["git", "show", f"{commit}:scripts/finalize_probe2_impossible.py"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return result.stdout


def expected_finalizer_source_identity(repo, config, source_commit=None):
    source = Path(repo) / "scripts" / "finalize_probe2_impossible.py"
    if not source.is_file():
        raise RuntimeError("finalizer source file is missing")
    commit = resolve_source_commit(repo, source_commit)
    working_blob = source.read_bytes()
    committed_blob = read_committed_finalizer_blob(repo, commit)
    if working_blob != committed_blob:
        raise RuntimeError(
            "executing finalizer source is dirty, untracked, or differs from "
            f"git commit {commit}"
        )
    source_hash = hashlib.sha256(working_blob).hexdigest()
    return {
        "repository": str(Path(repo).resolve()),
        "repository_head_commit": resolve_source_commit(repo),
        "finalizer_source_commit": commit,
        "canonical_primary_source_commit": config["code_commit"],
        "finalizer_source": str(source),
        "finalizer_source_sha256": source_hash,
        "validated_primary_runner": "scripts/run_noise_sweep.py",
        "validated_primary_runner_sha256": config["instrument_file_sha256"][
            "scripts/run_noise_sweep.py"
        ],
    }


def archive_finalizer_source(root, repo, config, source_commit=None):
    identity = expected_finalizer_source_identity(repo, config, source_commit)
    source = Path(identity["finalizer_source"])
    archive = Path(root) / FINALIZER_ARCHIVE
    source_hash = identity["finalizer_source_sha256"]
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        if sha256_of_file(archive) != source_hash:
            raise RuntimeError("archived finalizer source conflicts with current source")
        discard_atomic_copy_temp(archive)
    else:
        copy_file_atomic(source, archive)
    identity["archived_finalizer_source"] = str(archive)
    identity["archived_finalizer_source_sha256"] = sha256_of_file(archive)
    if identity["archived_finalizer_source_sha256"] != source_hash:
        raise RuntimeError("finalizer source archive changed during creation")
    return identity


def validate_archived_finalizer_source(
    root, repo, config, source_identity, source_commit=None
):
    """Verify immutable source against its recorded commit, independent of HEAD."""
    recorded_commit = source_identity.get("finalizer_source_commit")
    selected_commit = resolve_source_commit(repo, source_commit or recorded_commit)
    archived_source = Path(root) / FINALIZER_ARCHIVE
    committed_blob = read_committed_finalizer_blob(repo, selected_commit)
    committed_hash = hashlib.sha256(committed_blob).hexdigest()
    historical_head = source_identity.get("repository_head_commit")
    if (
        recorded_commit != selected_commit
        or not isinstance(historical_head, str)
        or re.fullmatch(r"[0-9a-f]{40}", historical_head) is None
        or source_identity.get("canonical_primary_source_commit")
        != config["code_commit"]
        or source_identity.get("validated_primary_runner")
        != "scripts/run_noise_sweep.py"
        or source_identity.get("validated_primary_runner_sha256")
        != config["instrument_file_sha256"]["scripts/run_noise_sweep.py"]
        or source_identity.get("finalizer_source_sha256") != committed_hash
        or source_identity.get("archived_finalizer_source") != str(archived_source)
        or source_identity.get("archived_finalizer_source_sha256")
        != committed_hash
        or not archived_source.is_file()
        or archived_source.read_bytes() != committed_blob
    ):
        raise RuntimeError("sealed finalizer source identity is invalid")
    return selected_commit


def validate_canonical_config(config, root, parent_model, repo):
    expected_scalars = {
        "parent_model": str(parent_model),
        "beta": 1.0,
        "alphas": DEFAULT_ALPHAS,
        "seeds": DEFAULT_SEEDS,
        "batch_size": 8,
        "max_new_tokens": 256,
        "cliff_threshold": 20.0,
        "max_bisections": 8,
        "normalisation_version": V2_POLICY,
    }
    actual = {key: config.get(key) for key in expected_scalars}
    if actual != expected_scalars:
        raise RuntimeError(
            f"interrupted primary config is not canonical: {actual}"
        )
    body = {key: value for key, value in config.items() if key != "fingerprint"}
    if config.get("fingerprint") != fingerprint(body):
        raise RuntimeError("run-config fingerprint is invalid")
    if config.get("parent_weight_sha256") != model_weight_hashes(parent_model):
        raise RuntimeError("clean-parent weight hashes changed")
    if config.get("parent_support_sha256") != support_file_hashes(parent_model):
        raise RuntimeError("clean-parent support hashes changed")
    instruments = config.get("instrument_file_sha256", {})
    if set(instruments) != set(EXPECTED_INSTRUMENT_PATHS):
        raise RuntimeError("run config has the wrong instrument dependency set")
    for relative in EXPECTED_INSTRUMENT_PATHS:
        if instruments[relative] != sha256_of_file(repo / relative):
            raise RuntimeError(f"instrument dependency changed: {relative}")
    commit = config.get("code_commit")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-fA-F]{40}", commit) is None:
        raise RuntimeError("run config has no immutable source commit")
    config_path = root / "run_config.json"
    if not config_path.is_file():
        raise RuntimeError("interrupted primary lacks run_config.json")


def validate_parent_identity(root, parent_model, config):
    path = root / "parent_identity.json"
    identity = read_json(path)
    expected = {
        "source_model": str(parent_model),
        "weight_file_sha256": config["parent_weight_sha256"],
        "support_file_sha256": config["parent_support_sha256"],
    }
    expected["fingerprint"] = fingerprint(expected)
    if identity != expected:
        raise RuntimeError("parent identity does not match the canonical config/model")
    return identity, path


def expected_prompt_hashes(config):
    instruments = config["instrument_file_sha256"]
    return {
        "battery": instruments["data/decay_scalar_prompts.json"],
        "capability": instruments["data/rehearsal_capability_prompts.json"],
        "survival": instruments["data/conversational_survival_generations.json"],
    }


def validate_dose_sidecar(sidecar, *, alpha, seed, parent_model, parent_identity):
    expected = {
        "alpha": float(alpha),
        "beta": 1.0,
        "seed": int(seed),
        "source_model": str(parent_model),
        "tokenizer_source": str(parent_model),
        "source_identity_fingerprint": parent_identity["fingerprint"],
    }
    if {key: sidecar.get(key) for key in expected} != expected:
        raise RuntimeError(
            f"dose provenance mismatch for alpha={alpha} seed={seed}"
        )
    if sidecar.get("source_identity") != parent_identity:
        raise RuntimeError("dose sidecar has the wrong frozen source identity")
    for key in ("weight_file_sha256", "support_file_sha256"):
        if not isinstance(sidecar.get(key), dict) or not sidecar[key]:
            raise RuntimeError(f"dose sidecar lacks {key}")


def validate_reanalysis(
    path,
    scalar_path,
    policy_fingerprint,
    scalar,
    baseline,
    positive,
    negative,
    sources,
):
    payload = read_json(path)
    scalar_payload = read_json(scalar_path)
    normalised, recomputed_scalar, directions = normalise_components_bidirectional(
        scalar_payload["components"], baseline, positive, negative
    )
    expected = {
        "normalisation_version": V2_POLICY,
        "source_scalar_json": str(scalar_path),
        "source_scalar_sha256": sha256_of_file(scalar_path),
        "policy_fingerprint": policy_fingerprint,
        "components": scalar_payload["components"],
        "normalised_components": normalised,
        "normalisation_directions": directions,
        "scalar_0_100": recomputed_scalar,
        "baseline_components": baseline,
        "positive_component_anchor": positive,
        "negative_component_anchor": negative,
        "component_anchor_sources": sources,
    }
    if payload != expected or abs(recomputed_scalar - scalar) > 1e-9:
        raise RuntimeError(f"stale or invalid v2 scalar reanalysis: {path}")


def validate_scalar_and_value(
    scalar_path,
    *,
    model_path,
    sidecar,
    parent_model,
    config,
    prompt_hashes,
    policy_fingerprint,
    baseline,
    positive,
    negative,
):
    payload = validate_scalar_artifact(
        scalar_path,
        expected_model=str(model_path),
        expected_judge=str(parent_model),
        expected_tokenizer=str(parent_model),
        expected_prompt_sha256=prompt_hashes,
        expected_weight_sha256=sidecar["weight_file_sha256"],
        expected_model_support_sha256=sidecar["support_file_sha256"],
        expected_tokenizer_support_sha256=config["parent_support_sha256"],
        expected_judge_support_sha256=config["parent_support_sha256"],
        expected_judge_weight_sha256=config["parent_weight_sha256"],
        expected_policy=V2_POLICY,
        expected_policy_fingerprint=policy_fingerprint,
    )
    normalised, scalar, directions = normalise_components_bidirectional(
        payload["components"], baseline, positive, negative
    )
    if not SCALAR_MIN <= scalar <= SCALAR_MAX:
        raise RuntimeError(f"scalar outside its mathematical bounds: {scalar}")
    if abs(float(payload.get("scalar_0_100")) - scalar) > 1e-9:
        raise RuntimeError(f"scalar/components mismatch in {scalar_path}")
    return payload, scalar, normalised, directions


def pchip_max_prediction_at_point_one(alpha005_mean, baseline_scalar=0.0):
    """Exact upper bound for the frozen held-alpha-0.1 PCHIP prediction.

    On the [.05,.2] interval, the Hermite coefficient multiplying the left
    slope is positive and the coefficient multiplying the right slope is
    negative.  Monotone Fritsch-Carlson slopes are nonnegative.  Therefore the
    maximum sets y(.2) to its scalar upper bound and makes the right slope zero
    by setting y(.3)=y(.2).  The left slope increases with y(.2), so this same
    endpoint also maximizes its positive contribution.  All later values can
    remain at 100, making the bound achievable.
    """
    if not SCALAR_MIN <= baseline_scalar <= alpha005_mean <= SCALAR_MAX:
        raise ValueError("observed endpoints violate the monotone scalar bounds")
    xs = [0.0, 0.05, 0.2, 0.3, 0.45, 0.6, 0.75, 0.9, 1.0]
    ys = [baseline_scalar, alpha005_mean] + [SCALAR_MAX] * 7
    prediction = pchip_eval(xs, ys, LOO_HELD_ALPHA)
    delta_left = (alpha005_mean - baseline_scalar) / 0.05
    delta_right = (SCALAR_MAX - alpha005_mean) / 0.15
    left_slope = (
        0.0
        if delta_left * delta_right <= 0.0
        else 0.6 / (0.35 / delta_left + 0.25 / delta_right)
    )
    right_slope = 0.0
    closed_form = (
        20.0 * alpha005_mean / 27.0
        + 7.0 * SCALAR_MAX / 27.0
        + left_slope / 45.0
        - right_slope / 90.0
    )
    if abs(prediction - closed_form) > 1e-12:
        raise RuntimeError("closed-form PCHIP bound disagrees with the frozen runner")
    return {
        "held_alpha": LOO_HELD_ALPHA,
        "rest_xs": xs,
        "maximising_isotonic_ys": ys,
        "scalar_bounds": [SCALAR_MIN, SCALAR_MAX],
        "max_possible_prediction": prediction,
        "closed_form_prediction": closed_form,
        "extreme_slopes": {"m_at_0.05": left_slope, "m_at_0.2": right_slope},
        "hermite_formula": "20*a/27 + 7*b/27 + m1/45 - m2/90",
        "proof": (
            "For a=y(.05), b=y(.2), c=y(.3), the frozen runner evaluates "
            "p=20a/27+7b/27+m1(b)/45-m2(b,c)/90. Monotone "
            "Fritsch-Carlson slopes satisfy m2>=0, while m1 is nondecreasing "
            "in b. Thus b=100 maximizes both positive terms and c=b makes "
            "m2=0. All later ordinates may equal 100, so the bound is attained."
        ),
    }


def prove_loo_impossible(alpha005_mean, alpha01_mean, baseline_scalar=0.0):
    bound = pchip_max_prediction_at_point_one(alpha005_mean, baseline_scalar)
    minimum_error = alpha01_mean - bound["max_possible_prediction"]
    bound.update(
        {
            "observed_alpha0.05_mean": alpha005_mean,
            "observed_alpha0.1_mean": alpha01_mean,
            "minimum_possible_absolute_error": minimum_error,
            "loo_error_limit": LOO_ERROR_LIMIT,
            "gate_mathematically_impossible": minimum_error > LOO_ERROR_LIMIT,
        }
    )
    if minimum_error <= LOO_ERROR_LIMIT:
        raise RuntimeError(
            "available artifacts do not prove the LOO gate mathematically impossible"
        )
    return bound


def validate_completed_curve(
    root,
    parent_model,
    parent_identity,
    config,
    prompt_hashes,
    policy_fingerprint,
    baseline,
    positive,
    negative,
    sources,
):
    curve = {}
    records = []
    for alpha in COMPLETED_ALPHAS:
        per_seed = []
        for seed in DEFAULT_SEEDS:
            tag = f"alpha{alpha:g}_seed{seed}"
            dose_dir = root / "sweep" / tag
            scalar_path = dose_dir / "scalar.json"
            sidecar_path = dose_dir / "decay_dose.json"
            checkpoint = dose_dir / "checkpoint"
            reanalysis = dose_dir / "scalar_reanalysis_bidirectional_v2.json"
            if checkpoint.exists():
                raise RuntimeError(f"completed dose retained a redrawable checkpoint: {tag}")
            if not scalar_path.is_file() or not sidecar_path.is_file():
                raise RuntimeError(f"completed dose artifact is missing: {tag}")
            sidecar = read_json(sidecar_path)
            validate_dose_sidecar(
                sidecar,
                alpha=alpha,
                seed=seed,
                parent_model=parent_model,
                parent_identity=parent_identity,
            )
            payload, scalar, normalised, directions = validate_scalar_and_value(
                scalar_path,
                model_path=checkpoint,
                sidecar=sidecar,
                parent_model=parent_model,
                config=config,
                prompt_hashes=prompt_hashes,
                policy_fingerprint=policy_fingerprint,
                baseline=baseline,
                positive=positive,
                negative=negative,
            )
            if not reanalysis.is_file():
                raise RuntimeError(f"completed dose lacks its v2 reanalysis: {tag}")
            validate_reanalysis(
                reanalysis,
                scalar_path,
                policy_fingerprint,
                scalar,
                baseline,
                positive,
                negative,
                sources,
            )
            entry = {
                "seed": seed,
                "scalar": scalar,
                "raw_components": payload["components"],
                "normalised_components": normalised,
                "normalisation_directions": directions,
                "scalar_json": str(scalar_path),
                "scalar_sha256": sha256_of_file(scalar_path),
                "dose_sidecar": str(sidecar_path),
                "dose_sidecar_sha256": sha256_of_file(sidecar_path),
                "reanalysis_json": str(reanalysis),
                "reanalysis_sha256": sha256_of_file(reanalysis),
            }
            per_seed.append(entry)
            records.append({"alpha": alpha, **entry})
        curve[alpha] = {
            "per_seed": per_seed,
            "mean": sum(item["scalar"] for item in per_seed) / len(per_seed),
            "complete_seed_count": len(per_seed),
            "planned_seed_count": len(DEFAULT_SEEDS),
        }
    return curve, records


def expected_partial_paths(root):
    dose_dir = Path(root).resolve() / "sweep" / "alpha0.2_seed0"
    return {
        "dose_dir": dose_dir,
        "checkpoint": dose_dir / "checkpoint",
        "deletion_tombstone": dose_dir / "checkpoint.deleting",
        "checkpoint_sidecar": dose_dir / "checkpoint" / "decay_dose.json",
        "archived_sidecar": dose_dir / ABORTED_SIDECAR_NAME,
        "record": Path(root).resolve() / ABORTED_RECORD_NAME,
    }


def validate_interrupted_eval_log(root):
    log_path = Path(root).resolve() / "commands.log"
    if not log_path.is_file():
        raise RuntimeError("interrupted primary has no commands.log evidence")
    text = log_path.read_text(encoding="utf-8", errors="replace")
    command_matches = list(
        re.finditer(r"(?m)^\$ .*eval_decay_scalar\.py.*alpha0\.2_seed0.*$", text)
    )
    if not command_matches:
        raise RuntimeError("commands.log does not show alpha0.2 seed0 evaluation start")
    tail = text[command_matches[-1].start() :]
    if re.search(r"(?m)^\$ ", tail[1:]) or re.search(r"(?m)^exit=", tail):
        raise RuntimeError("alpha0.2 seed0 evaluation is not the interrupted final command")
    progress = [int(value) for value in re.findall(r"generated (\d+)/196", tail)]
    if not progress or progress[-1] != 32 or any(value > 32 for value in progress):
        raise RuntimeError("interrupted evaluation is not corroborated at 32/196")
    return {
        "log": str(log_path),
        "log_sha256": sha256_of_file(log_path),
        "evaluation_command_started": True,
        "last_generated_count": 32,
        "planned_generation_count": 196,
        "evaluation_completed": False,
        "scalar_artifact_absent": True,
        "used_for_gate": False,
    }


def validate_and_archive_partial_checkpoint(
    root,
    parent_model,
    parent_identity,
    interruption_evidence,
    fail_after_checkpoint_rename=False,
):
    root = Path(root).resolve()
    paths = expected_partial_paths(root)
    checkpoint = paths["checkpoint"]
    tombstone = paths["deletion_tombstone"]
    record_path = paths["record"]
    archived_sidecar = paths["archived_sidecar"]
    scalar_path = paths["dose_dir"] / "scalar.json"
    ordinary_sidecar = paths["dose_dir"] / "decay_dose.json"
    if scalar_path.exists() or ordinary_sidecar.exists():
        raise RuntimeError("alpha0.2 seed0 is not an interrupted pre-evaluation stage")
    expected_checkpoint = root / "sweep" / "alpha0.2_seed0" / "checkpoint"
    if checkpoint.resolve() != expected_checkpoint:
        raise RuntimeError("unexpected interrupted checkpoint path")
    expected_tombstone = root / "sweep" / "alpha0.2_seed0" / "checkpoint.deleting"
    if tombstone.resolve() != expected_tombstone:
        raise RuntimeError("unexpected interrupted-checkpoint tombstone path")
    if checkpoint.exists() and tombstone.exists():
        raise RuntimeError("checkpoint and deletion tombstone both exist")

    if checkpoint.is_dir():
        checkpoint_sidecar = paths["checkpoint_sidecar"]
        if not checkpoint_sidecar.is_file():
            raise RuntimeError("interrupted checkpoint has no completed dose sidecar")
        sidecar = read_json(checkpoint_sidecar)
        validate_dose_sidecar(
            sidecar,
            alpha=PARTIAL_ALPHA,
            seed=PARTIAL_SEED,
            parent_model=parent_model,
            parent_identity=parent_identity,
        )
        actual_weights = model_weight_hashes(checkpoint)
        actual_support = support_file_hashes(checkpoint)
        if actual_weights != sidecar["weight_file_sha256"]:
            raise RuntimeError("interrupted checkpoint weight hashes changed")
        if actual_support != sidecar["support_file_sha256"]:
            raise RuntimeError("interrupted checkpoint support hashes changed")
        archived_sidecar.parent.mkdir(parents=True, exist_ok=True)
        if archived_sidecar.exists():
            if sha256_of_file(archived_sidecar) != sha256_of_file(checkpoint_sidecar):
                raise RuntimeError("archived interrupted dose sidecar conflicts")
            discard_atomic_copy_temp(archived_sidecar)
        else:
            copy_file_atomic(checkpoint_sidecar, archived_sidecar)
        record = {
            "status": "provenance_preserved_pending_checkpoint_deletion",
            "stage": {"alpha": PARTIAL_ALPHA, "seed": PARTIAL_SEED},
            "checkpoint": str(checkpoint),
            "deletion_tombstone": str(tombstone),
            "redrawable": True,
            "archived_dose_sidecar": str(archived_sidecar),
            "archived_dose_sidecar_sha256": sha256_of_file(archived_sidecar),
            "canonical_completed_sidecar": str(ordinary_sidecar),
            "canonical_completed_sidecar_absent": True,
            "noncanonical_archive_reason": (
                "the evaluation never completed, so the preserved checkpoint "
                "sidecar must not masquerade as a completed dose artifact"
            ),
            "weight_file_sha256": actual_weights,
            "support_file_sha256": actual_support,
            "source_identity_fingerprint": parent_identity["fingerprint"],
            "interruption_evidence": interruption_evidence,
            "scientific_use": "non-gating provenance only",
        }
        write_json_atomic(record_path, record)
        if root not in checkpoint.resolve().parents or checkpoint.resolve() == root:
            raise RuntimeError("refusing to delete checkpoint outside the primary root")
        checkpoint.replace(tombstone)
        record["status"] = "checkpoint_renamed_for_deletion"
        write_json_atomic(record_path, record)
        if fail_after_checkpoint_rename:
            raise RuntimeError("injected failure after checkpoint deletion rename")
    else:
        if not record_path.is_file() or not archived_sidecar.is_file():
            raise RuntimeError("interrupted checkpoint vanished before provenance archival")
        record = read_json(record_path)
        if record.get("status") not in {
            "provenance_preserved_pending_checkpoint_deletion",
            "checkpoint_renamed_for_deletion",
            "checkpoint_deleted_after_provenance_archive",
        }:
            raise RuntimeError("invalid aborted-stage resume record")
        sidecar = read_json(archived_sidecar)
        validate_dose_sidecar(
            sidecar,
            alpha=PARTIAL_ALPHA,
            seed=PARTIAL_SEED,
            parent_model=parent_model,
            parent_identity=parent_identity,
        )
        if (
            record.get("archived_dose_sidecar_sha256")
            != sha256_of_file(archived_sidecar)
            or record.get("weight_file_sha256") != sidecar["weight_file_sha256"]
            or record.get("support_file_sha256") != sidecar["support_file_sha256"]
            or record.get("interruption_evidence") != interruption_evidence
            or record.get("canonical_completed_sidecar") != str(ordinary_sidecar)
            or record.get("canonical_completed_sidecar_absent") is not True
            or record.get("deletion_tombstone") != str(tombstone)
        ):
            raise RuntimeError("aborted-stage resume provenance mismatch")
    if tombstone.exists():
        if root not in tombstone.resolve().parents or tombstone.resolve() == root:
            raise RuntimeError("refusing to delete tombstone outside the primary root")
        shutil.rmtree(tombstone)
    if checkpoint.exists():
        raise RuntimeError("interrupted checkpoint still exists after deletion")
    if tombstone.exists():
        raise RuntimeError("interrupted checkpoint tombstone still exists after deletion")
    record["status"] = "checkpoint_deleted_after_provenance_archive"
    record["checkpoint_deleted"] = True
    write_json_atomic(record_path, record)
    return record, record_path, archived_sidecar


def validate_unsealed_interrupted_layout(root):
    root = Path(root).resolve()
    if (root / "MANIFEST.sha256").exists():
        raise RuntimeError("interrupted-layout validator received a sealed root")
    sweep = root / "sweep"
    if not sweep.is_dir():
        raise RuntimeError("interrupted root has no sweep directory")
    expected = {
        *(f"alpha{alpha:g}_seed{seed}" for alpha in COMPLETED_ALPHAS for seed in DEFAULT_SEEDS),
        "alpha0.2_seed0",
    }
    actual = {path.name for path in sweep.iterdir() if path.is_dir()}
    if actual != expected:
        raise RuntimeError(
            f"interrupted sweep layout mismatch: expected={sorted(expected)} actual={sorted(actual)}"
        )


def validate_failure_archive(
    root,
    parent_model=None,
    repo=None,
    source_commit=None,
    require_manifest=True,
):
    root = Path(root).resolve()
    seal = verify_manifest(root) if require_manifest else None
    if not require_manifest and (root / "MANIFEST.sha256").exists():
        raise RuntimeError("pre-seal validator received a sealed archive")
    config = read_json(root / "run_config.json")
    parent_model = Path(parent_model or config.get("parent_model", "")).resolve()
    repo = Path(repo or Path.cwd()).resolve()
    validate_canonical_config(config, root, parent_model, repo)
    parent_identity, parent_identity_path = validate_parent_identity(
        root, parent_model, config
    )
    prompts = expected_prompt_hashes(config)
    baseline_json = root / "baseline" / "scalar.json"
    anchor_json = root / "anchor" / "scalar.json"
    anchor_sidecar_path = root / "anchor" / "decay_dose.json"
    ladder_json = root / "ladder" / "corruption_ladder.json"
    validate_scalar_artifact(
        baseline_json,
        expected_model=str(parent_model),
        expected_judge=str(parent_model),
        expected_tokenizer=str(parent_model),
        expected_prompt_sha256=prompts,
        expected_weight_sha256=config["parent_weight_sha256"],
        expected_model_support_sha256=config["parent_support_sha256"],
        expected_tokenizer_support_sha256=config["parent_support_sha256"],
        expected_judge_support_sha256=config["parent_support_sha256"],
        expected_judge_weight_sha256=config["parent_weight_sha256"],
    )
    anchor_sidecar = read_json(anchor_sidecar_path)
    validate_dose_sidecar(
        anchor_sidecar,
        alpha=1.0,
        seed=0,
        parent_model=parent_model,
        parent_identity=parent_identity,
    )
    validate_scalar_artifact(
        anchor_json,
        expected_model=str(root / "anchor" / "checkpoint"),
        expected_judge=str(parent_model),
        expected_tokenizer=str(parent_model),
        expected_prompt_sha256=prompts,
        expected_weight_sha256=anchor_sidecar["weight_file_sha256"],
        expected_model_support_sha256=anchor_sidecar["support_file_sha256"],
        expected_tokenizer_support_sha256=config["parent_support_sha256"],
        expected_judge_support_sha256=config["parent_support_sha256"],
        expected_judge_weight_sha256=config["parent_weight_sha256"],
    )
    validate_ladder_artifact(
        ladder_json,
        baseline_json,
        parent_model,
        config["parent_support_sha256"],
        config["parent_weight_sha256"],
    )
    baseline, positive, negative, sources = load_bidirectional_anchors(
        baseline_json, anchor_json, ladder_json
    )
    policy_fingerprint = bidirectional_policy_fingerprint(
        baseline, positive, negative, sources
    )
    baseline_payload = read_json(baseline_json)
    terminal_payload = read_json(anchor_json)
    _, baseline_scalar, _ = normalise_components_bidirectional(
        baseline_payload["components"], baseline, positive, negative
    )
    _, terminal_scalar, _ = normalise_components_bidirectional(
        terminal_payload["components"], baseline, positive, negative
    )
    if abs(baseline_scalar) > 1e-9:
        raise RuntimeError("clean baseline does not reproduce scalar zero")
    baseline_reanalysis = root / "baseline" / "scalar_reanalysis_bidirectional_v2.json"
    terminal_reanalysis = root / "anchor" / "scalar_reanalysis_bidirectional_v2.json"
    for reanalysis_path, scalar_path, value in (
        (baseline_reanalysis, baseline_json, baseline_scalar),
        (terminal_reanalysis, anchor_json, terminal_scalar),
    ):
        validate_reanalysis(
            reanalysis_path,
            scalar_path,
            policy_fingerprint,
            value,
            baseline,
            positive,
            negative,
            sources,
        )
    ladder_gate, ladder_component_pass, ladder_gate_pass = read_ladder_gate(ladder_json)
    if not ladder_gate_pass:
        raise RuntimeError("sealed failure archive no longer passes its ladder")
    recomputed_curve, recomputed_records = validate_completed_curve(
        root,
        parent_model,
        parent_identity,
        config,
        prompts,
        policy_fingerprint,
        baseline,
        positive,
        negative,
        sources,
    )
    summary_path = root / SUMMARY_NAME
    certificate_path = root / CERTIFICATE_NAME
    complete_path = root / "COMPLETE.json"
    summary = read_json(summary_path)
    certificate = read_json(certificate_path)
    complete = read_json(complete_path)
    gates = summary.get("gates", {})
    if (
        gates.get("primary_verdict") != "FAIL"
        or gates.get("probe2_verdict") != "FAIL"
        or gates.get("sweep_completed") is not False
        or gates.get("spearman_seed_means") is not None
        or gates.get("spearman_gate_pass") is not None
        or gates.get("loo_interpolation_errors") is not None
        or gates.get("max_loo_error") is not None
        or gates.get("loo_gate_pass") is not False
        or gates.get("loo_gate_mathematically_impossible") is not True
        or gates.get("cliffs_bisected") is not None
        or gates.get("unresolved_cliffs") is not None
        or gates.get("cliff_resolution_complete") is not None
        or gates.get("fallback_dial_required") is not None
        or gates.get("heavy_parent_target_reachable") is not None
        or gates.get("failure_stage") != "noise_calibration"
        or summary.get("alpha_at_scalar") is not None
        or summary.get("diagnostic_alpha_at_scalar") is not None
        or "curve" in summary
        or certificate.get("conclusion") != "PROBE2_PRIMARY_FAIL"
        or certificate.get("never_pass_capable") is not True
        or not certificate.get("loo_impossibility_proof", {}).get(
            "gate_mathematically_impossible"
        )
        or complete.get("verdict") != "FAIL"
        or complete.get("status") != "failed"
        or complete.get("primary_verdict") != "FAIL"
        or complete.get("probe2_verdict") != "FAIL"
        or complete.get("summary_sha256") != sha256_of_file(summary_path)
        or complete.get("failure_certificate_sha256")
        != sha256_of_file(certificate_path)
        or complete.get("run_config_fingerprint") != config["fingerprint"]
        or summary.get("failure_certificate_sha256")
        != sha256_of_file(certificate_path)
        or summary.get("parent_model") != str(parent_model)
        or summary.get("beta") != 1.0
        or summary.get("normalisation_version") != V2_POLICY
        or certificate.get("run_config_sha256")
        != sha256_of_file(root / "run_config.json")
        or certificate.get("run_config_fingerprint") != config["fingerprint"]
        or certificate.get("parent_identity_sha256")
        != sha256_of_file(parent_identity_path)
        or certificate.get("normalisation_version") != V2_POLICY
        or certificate.get("normalisation_policy_fingerprint")
        != policy_fingerprint
        or summary.get("normalisation_policy_fingerprint") != policy_fingerprint
        or summary.get("baseline_components") != baseline
        or summary.get("terminal_weight_noise_components")
        != terminal_payload["components"]
        or summary.get("positive_component_anchor") != positive
        or summary.get("negative_component_anchor") != negative
        or summary.get("component_anchor_sources") != sources
        or summary.get("baseline_scalar") != baseline_scalar
        or summary.get("terminal_weight_noise_scalar") != terminal_scalar
        or summary.get("baseline_reanalysis_json") != str(baseline_reanalysis)
        or summary.get("terminal_reanalysis_json") != str(terminal_reanalysis)
        or summary.get("reference_artifact_sha256")
        != {
            "baseline_scalar": sha256_of_file(baseline_json),
            "terminal_scalar": sha256_of_file(anchor_json),
            "corruption_ladder": sha256_of_file(ladder_json),
        }
        or gates.get("ladder_monotonicity") != ladder_gate
        or gates.get("ladder_component_pass") != ladder_component_pass
        or gates.get("ladder_gate_pass") is not True
    ):
        raise RuntimeError("sealed root is not the mathematical-impossibility FAIL")
    state = read_json(root / "state.json")
    if (
        state.get("status") != "failed_primary"
        or state.get("failure_stage") != "noise_calibration"
        or state.get("termination_reason")
        != "alpha0.1_loo_mathematically_impossible"
    ):
        raise RuntimeError("sealed terminal state is not canonical")
    aborted_path = root / ABORTED_RECORD_NAME
    partial_dose_dir = root / "sweep" / "alpha0.2_seed0"
    archived_sidecar = partial_dose_dir / ABORTED_SIDECAR_NAME
    aborted = read_json(aborted_path)
    archived_sidecar_payload = read_json(archived_sidecar)
    validate_dose_sidecar(
        archived_sidecar_payload,
        alpha=PARTIAL_ALPHA,
        seed=PARTIAL_SEED,
        parent_model=parent_model,
        parent_identity=parent_identity,
    )
    expected_interruption = validate_interrupted_eval_log(root)
    expected_aborted = {
        "status": "checkpoint_deleted_after_provenance_archive",
        "stage": {"alpha": PARTIAL_ALPHA, "seed": PARTIAL_SEED},
        "checkpoint": str(partial_dose_dir / "checkpoint"),
        "deletion_tombstone": str(partial_dose_dir / "checkpoint.deleting"),
        "redrawable": True,
        "archived_dose_sidecar": str(archived_sidecar),
        "archived_dose_sidecar_sha256": sha256_of_file(archived_sidecar),
        "canonical_completed_sidecar": str(partial_dose_dir / "decay_dose.json"),
        "canonical_completed_sidecar_absent": True,
        "noncanonical_archive_reason": (
            "the evaluation never completed, so the preserved checkpoint "
            "sidecar must not masquerade as a completed dose artifact"
        ),
        "weight_file_sha256": archived_sidecar_payload["weight_file_sha256"],
        "support_file_sha256": archived_sidecar_payload["support_file_sha256"],
        "source_identity_fingerprint": parent_identity["fingerprint"],
        "interruption_evidence": expected_interruption,
        "scientific_use": "non-gating provenance only",
        "checkpoint_deleted": True,
    }
    if (
        (root / "sweep" / "alpha0.2_seed0" / "checkpoint").exists()
        or (root / "sweep" / "alpha0.2_seed0" / "checkpoint.deleting").exists()
        or (root / "sweep" / "alpha0.2_seed0" / "scalar.json").exists()
        or (root / "sweep" / "alpha0.2_seed0" / "decay_dose.json").exists()
        or aborted.get("status") != "checkpoint_deleted_after_provenance_archive"
        or aborted.get("checkpoint_deleted") is not True
        or aborted.get("archived_dose_sidecar_sha256")
        != sha256_of_file(archived_sidecar)
        or certificate.get("aborted_stage_record_sha256")
        != sha256_of_file(aborted_path)
        or certificate.get("archived_partial_dose_sidecar_sha256")
        != sha256_of_file(archived_sidecar)
        or aborted != expected_aborted
        or summary.get("aborted_stage") != aborted
        or certificate.get("aborted_stage_record") != str(aborted_path)
        or certificate.get("archived_partial_dose_sidecar")
        != str(archived_sidecar)
        or summary.get("failure_certificate") != str(certificate_path)
        or complete.get("failure_certificate") != str(certificate_path)
    ):
        raise RuntimeError("sealed aborted-stage provenance is invalid")
    source_identity = certificate.get("finalizer_source_identity", {})
    validate_archived_finalizer_source(
        root, repo, config, source_identity, source_commit
    )
    if certificate.get("commands_log_sha256") != sha256_of_file(
        root / "commands.log"
    ):
        raise RuntimeError("sealed finalizer source identity is invalid")
    if (
        aborted.get("interruption_evidence") != expected_interruption
        or expected_interruption["last_generated_count"] != 32
        or expected_interruption["planned_generation_count"] != 196
        or expected_interruption["evaluation_completed"] is not False
        or expected_interruption["scalar_artifact_absent"] is not True
        or expected_interruption["used_for_gate"] is not False
    ):
        raise RuntimeError("sealed interrupted-evaluation evidence is invalid")
    completed = certificate.get("completed_artifacts", [])
    expected_doses = {
        (alpha, seed) for alpha in COMPLETED_ALPHAS for seed in DEFAULT_SEEDS
    }
    if {(item.get("alpha"), item.get("seed")) for item in completed} != expected_doses:
        raise RuntimeError("sealed certificate does not cover the six completed doses")
    if completed != recomputed_records:
        raise RuntimeError("sealed completed artifacts fail semantic recomputation")
    for item in completed:
        for path_key, hash_key in (
            ("scalar_json", "scalar_sha256"),
            ("dose_sidecar", "dose_sidecar_sha256"),
            ("reanalysis_json", "reanalysis_sha256"),
        ):
            artifact = Path(item[path_key]).resolve()
            if root not in artifact.parents or item[hash_key] != sha256_of_file(artifact):
                raise RuntimeError("sealed completed-artifact provenance is invalid")
    partial_curve = summary.get("partial_curve", {})
    if set(partial_curve) != {"0.05", "0.1"}:
        raise RuntimeError("sealed summary has the wrong partial curve")
    expected_partial_curve = {
        str(alpha): recomputed_curve[alpha] for alpha in COMPLETED_ALPHAS
    }
    if partial_curve != expected_partial_curve:
        raise RuntimeError("partial curve fails semantic recomputation")
    for alpha in COMPLETED_ALPHAS:
        certificate_records = sorted(
            (item for item in completed if item["alpha"] == alpha),
            key=lambda item: item["seed"],
        )
        expected_per_seed = [
            {key: value for key, value in item.items() if key != "alpha"}
            for item in certificate_records
        ]
        expected_curve = {
            "per_seed": expected_per_seed,
            "mean": sum(item["scalar"] for item in certificate_records)
            / len(certificate_records),
            "complete_seed_count": len(DEFAULT_SEEDS),
            "planned_seed_count": len(DEFAULT_SEEDS),
        }
        if partial_curve[str(alpha)] != expected_curve:
            raise RuntimeError("partial curve disagrees with certified scalar records")
    recomputed_proof = prove_loo_impossible(
        float(partial_curve["0.05"]["mean"]),
        float(partial_curve["0.1"]["mean"]),
        float(summary.get("baseline_scalar")),
    )
    if (
        certificate.get("loo_impossibility_proof") != recomputed_proof
        or gates.get("loo_impossibility_error_lower_bound")
        != recomputed_proof["minimum_possible_absolute_error"]
    ):
        raise RuntimeError("sealed PCHIP impossibility proof is inconsistent")
    return seal


def validate_sealed_failure(root, parent_model=None, repo=None, source_commit=None):
    return validate_failure_archive(
        root,
        parent_model,
        repo,
        source_commit,
        require_manifest=True,
    )


def finalize(
    root,
    parent_model,
    repo=None,
    source_commit=None,
    fail_after_checkpoint_rename=False,
    fail_before_terminal_state=False,
    fail_before_manifest=False,
):
    root = Path(root).resolve()
    parent_model = Path(parent_model).expanduser().resolve()
    repo = Path(repo or Path.cwd()).resolve()
    if not root.is_dir() or not parent_model.is_dir():
        raise ValueError("root and parent model must be existing local directories")
    if (root / "MANIFEST.sha256").exists():
        return validate_sealed_failure(root, parent_model, repo, source_commit)
    terminal_paths = (
        root / SUMMARY_NAME,
        root / CERTIFICATE_NAME,
        root / "COMPLETE.json",
    )
    existing_state = read_json(root / "state.json")
    if (
        all(path.is_file() for path in terminal_paths)
        and existing_state.get("status") == "failed_primary"
    ):
        validate_failure_archive(
            root,
            parent_model,
            repo,
            source_commit,
            require_manifest=False,
        )
        seal = write_manifest_atomic(root)
        validate_sealed_failure(root, parent_model, repo, source_commit)
        return seal
    validate_unsealed_interrupted_layout(root)

    config = read_json(root / "run_config.json")
    validate_canonical_config(config, root, parent_model, repo)
    identity, identity_path = validate_parent_identity(root, parent_model, config)
    state_path = root / "state.json"
    state = read_json(state_path)
    if (
        state.get("run_config_fingerprint") != config["fingerprint"]
        or state.get("status") != "running"
        or state.get("alphas") != DEFAULT_ALPHAS
        or state.get("seeds") != DEFAULT_SEEDS
        or state.get("bisections") != []
        or state.get("normalisation_version") != V2_POLICY
    ):
        raise RuntimeError("state is not the canonical interrupted primary state")

    prompts = expected_prompt_hashes(config)
    baseline_json = root / "baseline" / "scalar.json"
    anchor_json = root / "anchor" / "scalar.json"
    anchor_sidecar_path = root / "anchor" / "decay_dose.json"
    ladder_json = root / "ladder" / "corruption_ladder.json"
    validate_scalar_artifact(
        baseline_json,
        expected_model=str(parent_model),
        expected_judge=str(parent_model),
        expected_tokenizer=str(parent_model),
        expected_prompt_sha256=prompts,
        expected_weight_sha256=config["parent_weight_sha256"],
        expected_model_support_sha256=config["parent_support_sha256"],
        expected_tokenizer_support_sha256=config["parent_support_sha256"],
        expected_judge_support_sha256=config["parent_support_sha256"],
        expected_judge_weight_sha256=config["parent_weight_sha256"],
    )
    anchor_sidecar = read_json(anchor_sidecar_path)
    validate_dose_sidecar(
        anchor_sidecar,
        alpha=1.0,
        seed=0,
        parent_model=parent_model,
        parent_identity=identity,
    )
    validate_scalar_artifact(
        anchor_json,
        expected_model=str(root / "anchor" / "checkpoint"),
        expected_judge=str(parent_model),
        expected_tokenizer=str(parent_model),
        expected_prompt_sha256=prompts,
        expected_weight_sha256=anchor_sidecar["weight_file_sha256"],
        expected_model_support_sha256=anchor_sidecar["support_file_sha256"],
        expected_tokenizer_support_sha256=config["parent_support_sha256"],
        expected_judge_support_sha256=config["parent_support_sha256"],
        expected_judge_weight_sha256=config["parent_weight_sha256"],
    )
    validate_ladder_artifact(
        ladder_json,
        baseline_json,
        parent_model,
        config["parent_support_sha256"],
        config["parent_weight_sha256"],
    )
    baseline, positive, negative, sources = load_bidirectional_anchors(
        baseline_json, anchor_json, ladder_json
    )
    policy_fingerprint = bidirectional_policy_fingerprint(
        baseline, positive, negative, sources
    )
    baseline_payload = read_json(baseline_json)
    _, baseline_scalar, _ = normalise_components_bidirectional(
        baseline_payload["components"], baseline, positive, negative
    )
    if abs(baseline_scalar) > 1e-9:
        raise RuntimeError("clean baseline does not reproduce scalar zero")
    terminal_payload = read_json(anchor_json)
    _, terminal_scalar, _ = normalise_components_bidirectional(
        terminal_payload["components"], baseline, positive, negative
    )
    baseline_reanalysis = root / "baseline" / "scalar_reanalysis_bidirectional_v2.json"
    terminal_reanalysis = root / "anchor" / "scalar_reanalysis_bidirectional_v2.json"
    for reanalysis_path, scalar_path, value in (
        (baseline_reanalysis, baseline_json, baseline_scalar),
        (terminal_reanalysis, anchor_json, terminal_scalar),
    ):
        validate_reanalysis(
            reanalysis_path,
            scalar_path,
            policy_fingerprint,
            value,
            baseline,
            positive,
            negative,
            sources,
        )
    ladder_gate, ladder_component_pass, ladder_gate_pass = read_ladder_gate(ladder_json)
    if not ladder_gate_pass:
        raise RuntimeError("this finalizer is only for the post-ladder LOO impossibility")

    curve, completed_records = validate_completed_curve(
        root,
        parent_model,
        identity,
        config,
        prompts,
        policy_fingerprint,
        baseline,
        positive,
        negative,
        sources,
    )
    proof = prove_loo_impossible(
        curve[0.05]["mean"], curve[0.1]["mean"], baseline_scalar
    )

    interruption_evidence = validate_interrupted_eval_log(root)
    finalizer_source_identity = archive_finalizer_source(
        root, repo, config, source_commit
    )
    aborted, aborted_path, archived_sidecar = validate_and_archive_partial_checkpoint(
        root,
        parent_model,
        identity,
        interruption_evidence,
        fail_after_checkpoint_rename=fail_after_checkpoint_rename,
    )
    certificate = {
        "certificate_version": "probe2_v2_loo_impossibility_v1",
        "conclusion": "PROBE2_PRIMARY_FAIL",
        "never_pass_capable": True,
        "root": str(root),
        "run_config": str(root / "run_config.json"),
        "run_config_sha256": sha256_of_file(root / "run_config.json"),
        "run_config_fingerprint": config["fingerprint"],
        "parent_identity": str(identity_path),
        "parent_identity_sha256": sha256_of_file(identity_path),
        "normalisation_version": V2_POLICY,
        "normalisation_policy_fingerprint": policy_fingerprint,
        "completed_artifacts": completed_records,
        "loo_impossibility_proof": proof,
        "aborted_stage_record": str(aborted_path),
        "aborted_stage_record_sha256": sha256_of_file(aborted_path),
        "archived_partial_dose_sidecar": str(archived_sidecar),
        "archived_partial_dose_sidecar_sha256": sha256_of_file(archived_sidecar),
        "commands_log_sha256": interruption_evidence["log_sha256"],
        "finalizer_source_identity": finalizer_source_identity,
    }
    certificate_path = root / CERTIFICATE_NAME
    write_json_atomic(certificate_path, certificate)
    summary = {
        "certification_scope": "clean_parent_primary_only",
        "parent_model": str(parent_model),
        "beta": 1.0,
        "normalisation_version": V2_POLICY,
        "normalisation_policy_fingerprint": policy_fingerprint,
        "baseline_components": baseline,
        "terminal_weight_noise_components": terminal_payload["components"],
        "positive_component_anchor": positive,
        "negative_component_anchor": negative,
        "component_anchor_sources": sources,
        "reference_artifact_sha256": {
            "baseline_scalar": sha256_of_file(baseline_json),
            "terminal_scalar": sha256_of_file(anchor_json),
            "corruption_ladder": sha256_of_file(ladder_json),
        },
        "baseline_scalar": baseline_scalar,
        "terminal_weight_noise_scalar": terminal_scalar,
        "baseline_reanalysis_json": str(baseline_reanalysis),
        "terminal_reanalysis_json": str(terminal_reanalysis),
        "partial_curve": {str(alpha): curve[alpha] for alpha in COMPLETED_ALPHAS},
        "aborted_stage": aborted,
        "failure_certificate": str(certificate_path),
        "failure_certificate_sha256": sha256_of_file(certificate_path),
        "gates": {
            "failure_stage": "noise_calibration",
            "sweep_completed": False,
            "spearman_seed_means": None,
            "spearman_gate_pass": None,
            "loo_interpolation_errors": None,
            "max_loo_error": None,
            "loo_impossibility_error_lower_bound": proof[
                "minimum_possible_absolute_error"
            ],
            "loo_gate_pass": False,
            "loo_gate_mathematically_impossible": True,
            "cliffs_bisected": None,
            "unresolved_cliffs": None,
            "cliff_resolution_complete": None,
            "fallback_dial_required": None,
            "ladder_monotonicity": ladder_gate,
            "ladder_component_pass": ladder_component_pass,
            "ladder_gate_pass": True,
            "heavy_parent_target_reachable": None,
            "heavy_parent_repeat_run": False,
            "primary_verdict": "FAIL",
            "probe2_verdict": "FAIL",
        },
        "alpha_at_scalar": None,
        "diagnostic_alpha_at_scalar": None,
    }
    if summary["gates"]["primary_verdict"] != "FAIL":
        raise RuntimeError("finalizer invariant violated: PASS is forbidden")
    summary_path = root / SUMMARY_NAME
    write_json_atomic(summary_path, summary)
    complete = {
        "status": "failed",
        "verdict": "FAIL",
        "primary_verdict": "FAIL",
        "probe2_verdict": "FAIL",
        "summary": str(summary_path),
        "summary_sha256": sha256_of_file(summary_path),
        "failure_certificate": str(certificate_path),
        "failure_certificate_sha256": sha256_of_file(certificate_path),
        "run_config_fingerprint": config["fingerprint"],
    }
    write_json_atomic(root / "COMPLETE.json", complete)
    if fail_before_terminal_state:
        raise RuntimeError("injected failure immediately before terminal state")
    state.update(
        {
            "status": "failed_primary",
            "failure_stage": "noise_calibration",
            "termination_reason": "alpha0.1_loo_mathematically_impossible",
            "corrected_summary": str(summary_path),
            "failure_certificate": str(certificate_path),
        }
    )
    write_json_atomic(state_path, state)
    if fail_before_manifest:
        raise RuntimeError("injected failure immediately before manifest seal")
    seal = write_manifest_atomic(root)
    validate_sealed_failure(root, parent_model, repo, source_commit)
    return seal


def main():
    args = parse_args()
    seal = finalize(
        args.root,
        args.parent_model,
        source_commit=args.source_commit,
    )
    print("PROBE 2 PRIMARY VERDICT: FAIL")
    print("PROBE 2 OVERALL VERDICT: FAIL")
    print(f"Sealed {seal['path']} ({seal['entry_count']} files)")


if __name__ == "__main__":
    main()
