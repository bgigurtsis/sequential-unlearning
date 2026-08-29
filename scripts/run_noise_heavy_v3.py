"""Probe 2 v3 held-out heavy-parent certification.

This runner consumes, but never changes, a sealed promoted v3 pilot and a
sealed passing v3 clean-parent certification.  It creates the seed-7 parent
exactly once at the pilot mapping's stored ``g(.65)``.  There is deliberately
no parent search, mapping refit, dose insertion, or bisection path.
"""

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

from decay_scalar_normalization import (
    V2_POLICY,
    WEIGHTS,
    bidirectional_policy_fingerprint,
    load_bidirectional_anchors,
    normalise_components_bidirectional,
)
from run_noise_pilot_v3 import (
    HEAVY_PARENT_U,
    MAPPING_SCHEMA_SHA256,
    PUBLIC_CONTROLLER_U,
    fingerprint,
    validate_sealed_pilot,
)
from run_noise_certification_v3 import (
    CERTIFICATION_VERSION as PRIMARY_VERSION,
    validate_certification_scalar_execution,
    validate_finite_scalar_payload,
    validate_sealed_primary,
)
from run_noise_sweep import (
    component_curve_diagnostics,
    isotonic_running_max,
    model_weight_hashes,
    pchip_eval,
    run_command,
    safe_remove_tree,
    sha256_of_file,
    spearman,
    support_file_hashes,
    validate_scalar_artifact,
    write_scalar_reanalysis,
)


HEAVY_VERSION = "probe2_weight_noise_heavy_certification_v3"
SUMMARY_NAME = "sweep_summary_heavy_parent_v3.json"
HEAVY_PARENT_SEED = 7
HEAVY_PARENT_BAND = (60.0, 70.0)
INTERIOR_U = tuple(PUBLIC_CONTROLLER_U[1:-1])
CHILD_SEEDS = (0, 1, 2)
MAX_NEW_TOKENS = 256
EXECUTED_SOURCE_PATHS = (
    "scripts/run_noise_heavy_v3.py",
    "scripts/run_noise_certification_v3.py",
    "scripts/run_noise_pilot_v3.py",
    "scripts/apply_decay_noise.py",
    "scripts/eval_decay_scalar.py",
    "scripts/decay_scalar_normalization.py",
    "scripts/run_noise_sweep.py",
)
SCALAR_RECORD_KEYS = {
    "controller_u", "physical_alpha", "seed", "scalar", "raw_components",
    "normalised_components", "normalisation_directions", "scalar_json",
    "scalar_sha256", "reanalysis_json", "reanalysis_sha256",
    "decay_dose_json", "decay_dose_sha256",
}
CURVE_ROW_KEYS = {
    "physical_alpha", "per_seed", "mean", "raw_range", "raw_component_means",
    "normalised_component_means", "normalisation_direction_counts",
}
HEAVY_IDENTITY_KEYS = {
    "source_model", "weight_file_sha256", "support_file_sha256",
    "clean_parent_identity_fingerprint", "dose_sidecar_sha256",
    "scalar_json_sha256", "reanalysis_sha256", "administered_alpha",
    "controller_u", "beta", "dose_seed", "measured_global_scalar",
    "mapping_fingerprint", "construction", "fingerprint",
}
HEAVY_PARENT_KEYS = {
    "identity", "identity_json", "selection_history", "checkpoint", "measurement"
}
CONFIG_KEYS = {
    "version", "certification_scope", "clean_parent_identity",
    "pilot_archive", "primary_archive", "clean_ruler_paths", "clean_ruler",
    "prompt_sha256", "beta", "controller_mapping", "controller_coordinate",
    "controller_u", "physical_alpha_by_u", "heavy_parent", "child_seeds",
    "batch_size", "max_new_tokens", "rules", "code_commit", "code_sha256",
    "fingerprint",
}
SUMMARY_KEYS = {
    "certification_version", "certification_scope", "primary_archive",
    "pilot_archive", "clean_ruler", "normalisation_version",
    "normalisation_policy_fingerprint", "beta", "controller_mapping",
    "controller_coordinate", "controller_u", "physical_alpha_by_u",
    "heavy_parent", "incremental_alpha1_endpoint", "curve", "gates",
}
GATE_KEYS = {
    "spearman_seed_means", "spearman_gate_pass", "isotonic_policy",
    "isotonic_fitted_means_with_endpoints", "loo_interpolation_errors",
    "max_loo_error", "loo_gate_pass", "curve_raw_means_nondecreasing",
    "raw_mean_nondecrease_gate_pass", "per_dose_raw_ranges",
    "per_dose_range_gate_pass", "weight_noise_component_diagnostics",
    "ladder_monotonicity", "ladder_component_pass", "ladder_gate_pass",
    "primary_manifest_verified", "primary_verdict_verified",
    "heavy_parent_band", "heavy_parent_selection_pass",
    "no_refit_bisection_or_extra_points", "heavy_verdict", "probe2_verdict",
}
DOSE_SIDECAR_KEYS = {
    "source_model", "tokenizer_source", "source_identity",
    "source_identity_fingerprint", "alpha", "beta", "seed",
    "per_tensor_seed_rule", "transform", "dtype", "modified_tensors",
    "modified", "skipped", "weight_file_sha256", "support_file_sha256",
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean-parent-model", required=True)
    parser.add_argument("--pilot-root", required=True)
    parser.add_argument("--primary-root", required=True)
    parser.add_argument("--root", default="derisk/probe2_noise_v3_heavy_parent")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=MAX_NEW_TOKENS)
    return parser.parse_args()


def reject_nonfinite_constant(value):
    raise RuntimeError(f"non-finite JSON constant is forbidden: {value}")


def require_finite_tree(value, label="JSON payload"):
    if isinstance(value, float) and not math.isfinite(value):
        raise RuntimeError(f"{label} contains a non-finite number")
    if isinstance(value, dict):
        for key, child in value.items():
            require_finite_tree(child, f"{label}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            require_finite_tree(child, f"{label}[{index}]")
    return value


def require_exact_keys(payload, expected, label):
    if not isinstance(payload, dict) or set(payload) != set(expected):
        raise RuntimeError(f"{label} schema changed")
    return payload


def read_json(path):
    payload = json.loads(
        Path(path).read_text(encoding="utf-8"),
        parse_constant=reject_nonfinite_constant,
    )
    return require_finite_tree(payload, str(Path(path)))


def write_json(path, payload):
    require_finite_tree(payload)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def fingerprint(payload):
    require_finite_tree(payload)
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def require_scalar(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"{label} is not a scalar")
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 100.0:
        raise RuntimeError(f"{label} is outside [0,100]")
    return value


def validate_dose_sidecar_schema(sidecar, label="dose sidecar"):
    require_exact_keys(sidecar, DOSE_SIDECAR_KEYS, label)
    modified, skipped = sidecar.get("modified"), sidecar.get("skipped")
    if (
        sidecar.get("per_tensor_seed_rule")
        != "(seed * 1000003 + crc32(name)) % 2**63"
        or sidecar.get("transform")
        != "W' = (1-alpha)*W + alpha*beta*max_abs_per_output_channel(W)*N(0,1)"
        or sidecar.get("dtype") != "bfloat16 weights, fp32 transform arithmetic"
        or isinstance(sidecar.get("modified_tensors"), bool)
        or not isinstance(sidecar.get("modified_tensors"), int)
        or not isinstance(modified, list)
        or not isinstance(skipped, list)
        or sidecar.get("modified_tensors") != len(modified)
    ):
        raise RuntimeError(f"{label} transform metadata changed")
    for entry in modified:
        if (
            not isinstance(entry, dict)
            or set(entry)
            != {"name", "shape", "channel_scale_mean", "channel_scale_max"}
            or not isinstance(entry.get("name"), str)
            or not entry["name"]
            or not isinstance(entry.get("shape"), list)
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in entry["shape"]
            )
            or any(
                isinstance(entry.get(key), bool)
                or not isinstance(entry.get(key), (int, float))
                for key in ("channel_scale_mean", "channel_scale_max")
            )
        ):
            raise RuntimeError(f"{label} modified-tensor schema changed")
    for entry in skipped:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"name", "reason"}
            or not all(isinstance(entry.get(key), str) and entry[key] for key in entry)
        ):
            raise RuntimeError(f"{label} skipped-tensor schema changed")
    names = [entry["name"] for entry in (*modified, *skipped)]
    if len(names) != len(set(names)):
        raise RuntimeError(f"{label} tensor coverage contains duplicates")
    exact_hash_map(sidecar.get("weight_file_sha256"), f"{label} weight")
    exact_hash_map(sidecar.get("support_file_sha256"), f"{label} support")
    return sidecar


def paths_overlap(left, right):
    left, right = Path(left).resolve(), Path(right).resolve()
    return left == right or left in right.parents or right in left.parents


def exact_hash_map(value, label):
    if not isinstance(value, dict) or not value:
        raise RuntimeError(f"{label} hash map is missing")
    if any(
        not isinstance(key, str)
        or not key
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        for key, digest in value.items()
    ):
        raise RuntimeError(f"{label} hash map is malformed")
    return value


def model_identity(path):
    path = Path(path).resolve()
    identity = {
        "source_model": str(path),
        "weight_file_sha256": model_weight_hashes(path),
        "support_file_sha256": support_file_hashes(path),
    }
    identity["fingerprint"] = fingerprint(identity)
    return identity


def committed_source_identity(repo, relative_paths=EXECUTED_SOURCE_PATHS):
    repo = Path(repo).resolve()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise RuntimeError("heavy certification cannot bind a valid Git HEAD")
    hashes = {}
    for relative in relative_paths:
        try:
            blob = subprocess.run(
                ["git", "show", f"{commit}:{relative}"],
                cwd=repo,
                check=True,
                capture_output=True,
            ).stdout
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"heavy certification source is not committed: {relative}"
            ) from error
        committed_oid = subprocess.check_output(
            ["git", "rev-parse", f"{commit}:{relative}"], cwd=repo, text=True
        ).strip()
        current_oid = subprocess.check_output(
            ["git", "hash-object", "--path", relative, relative],
            cwd=repo,
            text=True,
        ).strip()
        if current_oid != committed_oid:
            raise RuntimeError(
                f"heavy certification source differs from HEAD: {relative}"
            )
        hashes[relative] = hashlib.sha256(blob).hexdigest()
    return {"commit": commit, "sha256": hashes}


def validate_recorded_source_identity(repo, commit, hashes):
    if (
        re.fullmatch(r"[0-9a-f]{40}", str(commit)) is None
        or set(hashes or {}) != set(EXECUTED_SOURCE_PATHS)
    ):
        raise RuntimeError("sealed heavy source identity is malformed")
    for relative in EXECUTED_SOURCE_PATHS:
        try:
            blob = subprocess.run(
                ["git", "show", f"{commit}:{relative}"],
                cwd=repo,
                check=True,
                capture_output=True,
            ).stdout
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"sealed source commit lacks {relative}") from error
        if hashlib.sha256(blob).hexdigest() != hashes[relative]:
            raise RuntimeError(f"sealed source blob changed: {relative}")


def parse_manifest_line(line):
    digest, separator, relative = line.partition("  ")
    if (
        not separator
        or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise RuntimeError(f"malformed heavy manifest line: {line!r}")
    return digest.lower(), Path(relative)


def verify_manifest(root):
    root = Path(root).resolve()
    manifest = root / "MANIFEST.sha256"
    if not manifest.is_file():
        return None
    entries = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        digest, relative = parse_manifest_line(line)
        key = relative.as_posix()
        if key in entries:
            raise RuntimeError(f"duplicate heavy manifest member: {key}")
        entries[key] = digest
    actual = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and path != manifest
    }
    if set(entries) != set(actual):
        raise RuntimeError("heavy manifest coverage changed")
    for relative, path in actual.items():
        if sha256_of_file(path) != entries[relative]:
            raise RuntimeError(f"heavy manifest member changed: {relative}")
    return {
        "path": str(manifest),
        "sha256": sha256_of_file(manifest),
        "entry_count": len(entries),
    }


def write_manifest(root):
    root = Path(root).resolve()
    output, temporary = root / "MANIFEST.sha256", root / "MANIFEST.sha256.tmp"
    if temporary.exists():
        temporary.unlink()
    files = sorted(
        path for path in root.rglob("*") if path.is_file() and path not in {output, temporary}
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


def stage_marker(root, name):
    return Path(root) / "stages" / f"{name}.json"


def expected_stage_payload(name, config_fingerprint, inputs, outputs):
    require_finite_tree(inputs, "stage inputs")
    return {
        "stage": name,
        "config_fingerprint": config_fingerprint,
        "inputs": inputs,
        "outputs": {str(Path(path)): sha256_of_file(path) for path in outputs},
    }


def ensure_stage(root, name, config_fingerprint, inputs, outputs, action):
    """Run a stage once; a marker makes later resumes hash-exact."""
    marker = stage_marker(root, name)
    if marker.exists():
        payload = read_json(marker)
        expected = expected_stage_payload(name, config_fingerprint, inputs, outputs)
        if payload != expected:
            raise RuntimeError(f"resumable heavy stage changed: {name}")
        return False
    action()
    if not all(Path(path).is_file() for path in outputs):
        raise RuntimeError(f"heavy stage did not produce all outputs: {name}")
    write_json(marker, expected_stage_payload(name, config_fingerprint, inputs, outputs))
    return True


def cleanup_checkpoint(checkpoint, root, semantically_validated):
    if not semantically_validated:
        raise RuntimeError("refusing child cleanup before semantic validation")
    if Path(checkpoint).is_dir():
        safe_remove_tree(checkpoint, root)


def validate_checkpoint_file_layout(checkpoint, sidecar_path=None):
    """Require a complete, flat checkpoint whose live bytes match its sidecar."""
    checkpoint = Path(checkpoint)
    sidecar_path = Path(sidecar_path or checkpoint / "decay_dose.json")
    if not checkpoint.is_dir() or not sidecar_path.is_file():
        raise RuntimeError("dose checkpoint is incomplete")
    sidecar = validate_dose_sidecar_schema(read_json(sidecar_path), "checkpoint sidecar")
    weights = exact_hash_map(sidecar.get("weight_file_sha256"), "checkpoint weight")
    support = exact_hash_map(
        sidecar.get("support_file_sha256"), "checkpoint support"
    )
    expected_names = set(weights) | set(support) | {"decay_dose.json"}
    entries = list(checkpoint.iterdir())
    if (
        any(not entry.is_file() or entry.is_symlink() for entry in entries)
        or {entry.name for entry in entries} != expected_names
        or model_weight_hashes(checkpoint) != weights
        or support_file_hashes(checkpoint) != support
    ):
        raise RuntimeError("dose checkpoint live layout/hash provenance changed")
    return sidecar


def validate_checkpoint_resume_provenance(
    checkpoint, expected_source, alpha, beta, seed
):
    sidecar = validate_checkpoint_file_layout(checkpoint)
    expected = {
        "source_model": str(Path(expected_source["source_model"]).resolve()),
        "tokenizer_source": str(Path(expected_source["source_model"]).resolve()),
        "source_identity_fingerprint": expected_source["fingerprint"],
        "alpha": float(alpha),
        "beta": float(beta),
        "seed": int(seed),
    }
    if (
        {key: sidecar.get(key) for key in expected} != expected
        or sidecar.get("source_identity") != expected_source
    ):
        raise RuntimeError("complete checkpoint resume provenance changed")
    return sidecar


def dose_resume_requires_apply(checkpoint, scalar_path, sidecar_path):
    """Classify an unmarked dose without ever deleting or redrawing evidence."""
    checkpoint = Path(checkpoint)
    scalar_path, sidecar_path = Path(scalar_path), Path(sidecar_path)
    dose_dir = scalar_path.parent
    if sidecar_path.parent != dose_dir or checkpoint.parent != dose_dir:
        raise RuntimeError("dose resume paths are not in one canonical directory")
    if dose_dir.is_symlink() or (dose_dir.exists() and not dose_dir.is_dir()):
        raise RuntimeError("dose directory has an unsafe filesystem type")
    if checkpoint.is_symlink() or scalar_path.is_symlink() or sidecar_path.is_symlink():
        raise RuntimeError("dose resume artifact is a symbolic link")
    if checkpoint.exists():
        if not checkpoint.is_dir() or not (checkpoint / "decay_dose.json").is_file():
            raise RuntimeError(
                "incomplete dose checkpoint preserved for diagnosis; refusing redraw"
            )
        validate_checkpoint_file_layout(checkpoint)
        if (scalar_path.exists() and not scalar_path.is_file()) or (
            sidecar_path.exists() and not sidecar_path.is_file()
        ):
            raise RuntimeError("dose resume output path has the wrong filesystem type")
        allowed = {checkpoint}
        if scalar_path.exists():
            allowed.add(scalar_path)
        if sidecar_path.exists():
            allowed.add(sidecar_path)
        actual = set(dose_dir.iterdir())
        if actual != allowed:
            raise RuntimeError("unmarked dose directory contains unknown resume artifacts")
        if sidecar_path.exists() and not scalar_path.exists():
            raise RuntimeError("archived dose sidecar exists without its scalar output")
        return False
    orphaned = list(dose_dir.iterdir()) if dose_dir.is_dir() else []
    if orphaned:
        raise RuntimeError(
            "dose checkpoint is absent but orphaned outputs exist; refusing redraw"
        )
    return True


def recover_archived_sidecar(checkpoint, scalar_path, sidecar_path):
    """Recover only a missing sidecar; never replace existing evidence."""
    checkpoint = Path(checkpoint)
    scalar_path, sidecar_path = Path(scalar_path), Path(sidecar_path)
    if not scalar_path.is_file():
        raise RuntimeError("cannot recover a dose sidecar without a scalar output")
    if sidecar_path.exists():
        if not sidecar_path.is_file():
            raise RuntimeError("archived dose sidecar has the wrong filesystem type")
        return False
    internal = checkpoint / "decay_dose.json"
    if not internal.is_file():
        raise RuntimeError("scalar has no recoverable checkpoint dose sidecar")
    # Exclusive creation prevents a concurrent or resumed artifact from being
    # overwritten between classification and recovery.
    with sidecar_path.open("xb") as output:
        output.write(internal.read_bytes())
    return True


def checkpoint_snapshot(checkpoint, archived_sidecar):
    checkpoint, archived_sidecar = Path(checkpoint), Path(archived_sidecar)
    internal = checkpoint / "decay_dose.json"
    if not checkpoint.is_dir() or not internal.is_file() or not archived_sidecar.is_file():
        raise RuntimeError("child checkpoint or its dose sidecar disappeared prematurely")
    internal_sha = sha256_of_file(internal)
    archived_sha = sha256_of_file(archived_sidecar)
    if internal_sha != archived_sha or internal.read_bytes() != archived_sidecar.read_bytes():
        raise RuntimeError("checkpoint/internal and archived dose sidecars differ")
    validate_checkpoint_file_layout(checkpoint, archived_sidecar)
    return {
        "checkpoint_weight_sha256": model_weight_hashes(checkpoint),
        "checkpoint_support_file_sha256": support_file_hashes(checkpoint),
        "checkpoint_sidecar_sha256": internal_sha,
        "archived_sidecar_sha256": archived_sha,
    }


def expected_deletion_evidence(
    config_fingerprint, u, alpha, beta, seed, record, snapshot, status
):
    return {
        "version": HEAVY_VERSION,
        "status": status,
        "config_fingerprint": config_fingerprint,
        "controller_u": float(u),
        "physical_alpha": float(alpha),
        "beta": float(beta),
        "seed": int(seed),
        **snapshot,
        "scalar_sha256": record["scalar_sha256"],
        "reanalysis_sha256": record["reanalysis_sha256"],
    }


def delete_validated_child_checkpoint(
    checkpoint, dose_dir, root, config_fingerprint, u, alpha, beta, seed, record
):
    """Crash-safe proof that an exact validated checkpoint preceded deletion."""
    checkpoint, dose_dir = Path(checkpoint), Path(dose_dir)
    evidence_path = dose_dir / "checkpoint_deletion.json"
    archived_sidecar = Path(record["decay_dose_json"])
    if evidence_path.is_file():
        evidence = read_json(evidence_path)
        snapshot = {
            key: evidence.get(key)
            for key in (
                "checkpoint_weight_sha256", "checkpoint_support_file_sha256",
                "checkpoint_sidecar_sha256", "archived_sidecar_sha256",
            )
        }
        pending = expected_deletion_evidence(
            config_fingerprint, u, alpha, beta, seed, record, snapshot,
            "validated_checkpoint_pending_deletion",
        )
        deleted = {**pending, "status": "checkpoint_deleted_after_validation"}
        if evidence not in (pending, deleted):
            raise RuntimeError("child checkpoint deletion evidence changed")
        sidecar = read_json(archived_sidecar)
        archived_sha = sha256_of_file(archived_sidecar)
        if (
            snapshot["checkpoint_weight_sha256"]
            != sidecar.get("weight_file_sha256")
            or snapshot["checkpoint_support_file_sha256"]
            != sidecar.get("support_file_sha256")
            or snapshot["checkpoint_sidecar_sha256"] != archived_sha
            or snapshot["archived_sidecar_sha256"] != archived_sha
        ):
            raise RuntimeError("resumed child deletion evidence changed")
        if evidence["status"] == "checkpoint_deleted_after_validation":
            if checkpoint.exists():
                raise RuntimeError("deleted child checkpoint unexpectedly reappeared")
            return evidence_path
        if checkpoint.exists():
            if checkpoint_snapshot(checkpoint, archived_sidecar) != snapshot:
                raise RuntimeError("pending child checkpoint bytes changed")
            cleanup_checkpoint(checkpoint, root, True)
        write_json(evidence_path, deleted)
        return evidence_path
    if not checkpoint.is_dir():
        raise RuntimeError("child checkpoint absent before durable validation evidence")
    snapshot = checkpoint_snapshot(checkpoint, archived_sidecar)
    sidecar = read_json(archived_sidecar)
    if (
        snapshot["checkpoint_weight_sha256"] != sidecar.get("weight_file_sha256")
        or snapshot["checkpoint_support_file_sha256"]
        != sidecar.get("support_file_sha256")
    ):
        raise RuntimeError("child checkpoint bytes differ from its dose sidecar")
    pending = expected_deletion_evidence(
        config_fingerprint, u, alpha, beta, seed, record, snapshot,
        "validated_checkpoint_pending_deletion",
    )
    write_json(evidence_path, pending)
    cleanup_checkpoint(checkpoint, root, True)
    write_json(
        evidence_path,
        {**pending, "status": "checkpoint_deleted_after_validation"},
    )
    return evidence_path


def mapping_for_heavy(pilot_root, pilot_summary):
    pilot_root = Path(pilot_root).resolve()
    require_finite_tree(pilot_summary, "sealed pilot summary")
    if pilot_summary.get("outcome") not in {"PROMOTE_ARM_A", "PROMOTE_ARM_B"}:
        raise RuntimeError("heavy certification requires a promoted v3 pilot")
    path = Path(pilot_summary.get("controller_mapping", "")).resolve()
    if path.parent != pilot_root or path.name != "controller_mapping.json":
        raise RuntimeError("promoted mapping is outside the sealed pilot")
    mapping = read_json(path)
    body = {key: value for key, value in mapping.items() if key != "fingerprint"}
    controller = mapping.get("controller")
    expected_us = list(PUBLIC_CONTROLLER_U)
    if (
        sha256_of_file(path) != pilot_summary.get("controller_mapping_sha256")
        or mapping.get("fingerprint") != pilot_summary.get("controller_mapping_fingerprint")
        or mapping.get("fingerprint") != fingerprint(body)
        or mapping.get("schema_sha256") != MAPPING_SCHEMA_SHA256
        or not isinstance(mapping.get("beta"), (int, float))
        or mapping.get("seed_used_to_fit") != 11
        or not isinstance(controller, list)
        or [record.get("u") for record in controller] != expected_us
        or [record.get("target_scalar") for record in controller]
        != [100.0 * u for u in expected_us]
        or controller[0].get("physical_alpha") != 0.0
        or controller[-1].get("physical_alpha") != 1.0
    ):
        raise RuntimeError("promoted controller mapping semantics changed")
    alphas = [record.get("physical_alpha") for record in controller]
    if (
        any(not isinstance(alpha, (int, float)) for alpha in alphas)
        or any(not 0.0 < float(alpha) < 1.0 for alpha in alphas[1:-1])
        or len(set(alphas[1:-1])) != len(INTERIOR_U)
        or any(b <= a for a, b in zip(alphas, alphas[1:]))
    ):
        raise RuntimeError("promoted controller grid is not strictly interior")
    heavy = mapping.get("heavy_parent", {})
    heavy_alpha = heavy.get("physical_alpha")
    if (
        heavy.get("u") != HEAVY_PARENT_U
        or heavy.get("target_scalar") != 65.0
        or not isinstance(heavy_alpha, (int, float))
        or not 0.0 < float(heavy_alpha) < 1.0
    ):
        raise RuntimeError("stored g(.65) semantics changed")
    return path, mapping


def primary_archive_identity(bundle):
    return {
        "root": str(Path(bundle["root"]).resolve()),
        "manifest_sha256": bundle["seal"]["sha256"],
        "summary_sha256": sha256_of_file(bundle["summary_path"]),
        "run_config_sha256": sha256_of_file(bundle["config_path"]),
        "parent_identity_sha256": sha256_of_file(bundle["identity_path"]),
    }


def expected_heavy_rules(mapping):
    return {
        "heavy_parent": {
            "controller_u": HEAVY_PARENT_U,
            "physical_alpha": mapping["heavy_parent"]["physical_alpha"],
            "seed": HEAVY_PARENT_SEED,
            "scalar_band_inclusive": list(HEAVY_PARENT_BAND),
            "construction": "exactly_one_clean_parent_dose_no_search",
            "checkpoint_retention": "retain_exact_even_on_out_of_band_FAIL",
        },
        "children": {
            "interior_u": list(INTERIOR_U),
            "seeds": list(CHILD_SEEDS),
            "u0": "measured_retained_parent_support",
            "u1": "one_incremental_seed0_child_support",
        },
        "coordinate_for_spearman_and_loo": "u",
        "loo": "raw held interior; running-max remaining; endpoints fit supports",
        "raw_means_nondecreasing_including_supports": True,
        "per_interior_dose_raw_range_max_inclusive": 6.0,
        "spearman_min_inclusive": 0.95,
        "loo_error_max_inclusive": 3.0,
        "mapping_refit_bisection_search_extra_points": "forbidden",
    }


def validate_primary_for_heavy(bundle, pilot_root, pilot_summary, mapping_path, mapping):
    if bundle is None:
        raise RuntimeError("v3 primary archive is not sealed")
    config, summary = bundle["config"], bundle["summary"]
    require_finite_tree(config, "sealed primary config")
    require_finite_tree(summary, "sealed primary summary")
    gates = summary.get("gates", {})
    expected_mapping = {
        "path": str(mapping_path),
        "sha256": sha256_of_file(mapping_path),
        "fingerprint": mapping["fingerprint"],
        "schema_sha256": MAPPING_SCHEMA_SHA256,
    }
    if (
        config.get("version") != PRIMARY_VERSION
        or summary.get("certification_version") != PRIMARY_VERSION
        or summary.get("certification_scope") != "clean_parent_primary_only"
        or gates.get("primary_verdict") != "PASS"
        or gates.get("probe2_verdict") != "INCOMPLETE_PENDING_HEAVY_PARENT"
        or gates.get("no_refit_bisection_or_extra_points") is not True
        or gates.get("raw_mean_nondecrease_gate_pass") is not True
        or gates.get("per_dose_range_gate_pass") is not True
        or config.get("pilot_archive", {}).get("root") != str(Path(pilot_root).resolve())
        or config.get("pilot_archive", {}).get("outcome") != pilot_summary.get("outcome")
        or config.get("controller_mapping") != expected_mapping
        or summary.get("controller_mapping") != expected_mapping
        or float(config.get("beta", -1)) != float(mapping["beta"])
        or float(summary.get("beta", -1)) != float(mapping["beta"])
        or config.get("controller_coordinate") != "u"
        or summary.get("controller_coordinate") != "u"
        or config.get("controller_u") != list(PUBLIC_CONTROLLER_U)
        or summary.get("controller_u") != list(PUBLIC_CONTROLLER_U)
    ):
        raise RuntimeError("sealed v3 primary is not the promoted mapping PASS")
    expected_alphas = {str(record["u"]): record["physical_alpha"] for record in mapping["controller"]}
    if (
        config.get("physical_alpha_by_u") != expected_alphas
        or summary.get("physical_alpha_by_u") != expected_alphas
    ):
        raise RuntimeError("primary physical controller grid changed")
    return config, summary, primary_archive_identity(bundle)


def loo_errors(us, raw_means):
    errors = {}
    for index in range(1, len(us) - 1):
        rest_x = us[:index] + us[index + 1 :]
        rest_y = isotonic_running_max(raw_means[:index] + raw_means[index + 1 :])
        errors[str(us[index])] = abs(
            pchip_eval(rest_x, rest_y, us[index]) - raw_means[index]
        )
    return errors


def analyse_heavy_curve(
    curve, parent_scalar, endpoint_scalar, ladder_gates, physical_alpha_by_u=None
):
    """Recompute every numerical v3 heavy verdict from the immutable u grid."""
    if set(curve) != set(INTERIOR_U):
        raise RuntimeError("heavy curve is not the exact eight-point u grid")
    require_finite_tree(curve, "heavy curve")
    require_finite_tree(ladder_gates, "heavy ladder gates")
    for u in INTERIOR_U:
        entry = curve[u]
        if not isinstance(entry, dict) or set(entry) != CURVE_ROW_KEYS:
            raise RuntimeError(f"heavy u={u} aggregate schema changed")
        per_seed = entry.get("per_seed", [])
        if [item.get("seed") for item in per_seed] != list(CHILD_SEEDS):
            raise RuntimeError(f"heavy u={u} does not contain exact seeds 0/1/2")
        expected = aggregate_seed_entries(per_seed)
        if entry != expected:
            raise RuntimeError(f"heavy u={u} aggregate does not reproduce exactly")
        expected_alpha = (
            physical_alpha_by_u[str(u)]
            if physical_alpha_by_u is not None else per_seed[0]["physical_alpha"]
        )
        if entry["physical_alpha"] != expected_alpha:
            raise RuntimeError(f"heavy u={u} physical alpha changed")
    means = [float(curve[u]["mean"]) for u in INTERIOR_U]
    raw = [require_scalar(parent_scalar, "heavy parent scalar"), *means,
           require_scalar(endpoint_scalar, "heavy endpoint scalar")]
    us = list(PUBLIC_CONTROLLER_U)
    rho = spearman(list(INTERIOR_U), means)
    errors = loo_errors(us, raw)
    max_loo = max(errors.values())
    ranges = {str(u): float(curve[u]["raw_range"]) for u in INTERIOR_U}
    fitted = isotonic_running_max(raw)
    gates = {
        "spearman_seed_means": rho,
        "spearman_gate_pass": rho is not None and rho >= 0.95,
        "isotonic_policy": "running maximum in public u space against clean ruler",
        "isotonic_fitted_means_with_endpoints": fitted,
        "loo_interpolation_errors": errors,
        "max_loo_error": max_loo,
        "loo_gate_pass": max_loo <= 3.0,
        "curve_raw_means_nondecreasing": all(
            right >= left for left, right in zip(raw, raw[1:])
        ),
        "raw_mean_nondecrease_gate_pass": all(
            right >= left for left, right in zip(raw, raw[1:])
        ),
        "per_dose_raw_ranges": ranges,
        "per_dose_range_gate_pass": all(value <= 6.0 for value in ranges.values()),
        "weight_noise_component_diagnostics": component_curve_diagnostics(
            curve, list(INTERIOR_U)
        ),
        "ladder_monotonicity": ladder_gates["ladder_monotonicity"],
        "ladder_component_pass": ladder_gates["ladder_component_pass"],
        "ladder_gate_pass": ladder_gates["ladder_gate_pass"],
        "primary_manifest_verified": True,
        "primary_verdict_verified": True,
        "heavy_parent_band": list(HEAVY_PARENT_BAND),
        "heavy_parent_selection_pass": HEAVY_PARENT_BAND[0] <= raw[0] <= HEAVY_PARENT_BAND[1],
        "no_refit_bisection_or_extra_points": True,
    }
    gates["heavy_verdict"] = "PASS" if all(
        gates[key] is True
        for key in (
            "spearman_gate_pass", "loo_gate_pass",
            "raw_mean_nondecrease_gate_pass", "per_dose_range_gate_pass",
            "ladder_gate_pass", "heavy_parent_selection_pass",
            "no_refit_bisection_or_extra_points",
        )
    ) else "FAIL"
    gates["probe2_verdict"] = gates["heavy_verdict"]
    return gates


def parent_failure_gates(scalar, primary_gates):
    return {
        "spearman_seed_means": None,
        "spearman_gate_pass": None,
        "isotonic_policy": "running maximum in public u space against clean ruler",
        "isotonic_fitted_means_with_endpoints": None,
        "loo_interpolation_errors": None,
        "max_loo_error": None,
        "loo_gate_pass": None,
        "curve_raw_means_nondecreasing": None,
        "raw_mean_nondecrease_gate_pass": None,
        "per_dose_raw_ranges": None,
        "per_dose_range_gate_pass": None,
        "weight_noise_component_diagnostics": None,
        "ladder_monotonicity": primary_gates["ladder_monotonicity"],
        "ladder_component_pass": primary_gates["ladder_component_pass"],
        "ladder_gate_pass": primary_gates["ladder_gate_pass"],
        "primary_manifest_verified": True,
        "primary_verdict_verified": True,
        "heavy_parent_band": list(HEAVY_PARENT_BAND),
        "heavy_parent_selection_pass": HEAVY_PARENT_BAND[0] <= scalar <= HEAVY_PARENT_BAND[1],
        "no_refit_bisection_or_extra_points": True,
        "heavy_verdict": "FAIL",
        "probe2_verdict": "FAIL",
    }


def recompute_summary_semantics(summary):
    """Fail closed on altered stored analysis, including terminal parent FAIL."""
    identity = summary.get("heavy_parent", {}).get("identity", {})
    parent_scalar = require_scalar(identity.get("measured_global_scalar"), "stored heavy parent")
    require_finite_tree(summary, "heavy summary")
    curve_json = summary.get("curve", {})
    expected_curve_keys = [str(u) for u in INTERIOR_U]
    if curve_json and list(curve_json) != expected_curve_keys:
        raise RuntimeError("sealed heavy curve keys/order are not canonical")
    curve = {float(key): value for key, value in curve_json.items()}
    stored = summary.get("gates", {})
    if not isinstance(stored, dict) or set(stored) != GATE_KEYS:
        raise RuntimeError("sealed heavy gate schema changed")
    if stored.get("heavy_parent_selection_pass") is False:
        expected = parent_failure_gates(parent_scalar, stored)
        if curve or summary.get("incremental_alpha1_endpoint") is not None:
            raise RuntimeError("failed one-shot parent archive contains child work")
    else:
        endpoint = summary.get("incremental_alpha1_endpoint", {})
        if not isinstance(endpoint, dict) or set(endpoint) != SCALAR_RECORD_KEYS:
            raise RuntimeError("sealed heavy endpoint schema changed")
        expected = analyse_heavy_curve(
            curve, parent_scalar, endpoint.get("scalar"), stored,
            summary.get("physical_alpha_by_u"),
        )
    if stored != expected:
        raise RuntimeError("sealed heavy verdict semantics changed")
    return expected


def scalar_bundle(
    scalar_path,
    sidecar_path,
    checkpoint,
    expected_source,
    clean_parent,
    config,
    baseline,
    positive,
    negative,
    sources,
    u,
    alpha,
    seed,
):
    sidecar = validate_dose_sidecar_schema(
        read_json(sidecar_path), f"dose sidecar u={u} seed={seed}"
    )
    expected_sidecar = {
        "source_model": str(Path(expected_source["source_model"]).resolve()),
        "tokenizer_source": str(Path(expected_source["source_model"]).resolve()),
        "source_identity_fingerprint": expected_source["fingerprint"],
        "alpha": float(alpha),
        "beta": float(config["beta"]),
        "seed": int(seed),
    }
    if (
        {key: sidecar.get(key) for key in expected_sidecar} != expected_sidecar
        or sidecar.get("source_identity") != expected_source
    ):
        raise RuntimeError(f"dose provenance changed at u={u} seed={seed}")
    validate_scalar_artifact(
        scalar_path,
        expected_model=str(Path(checkpoint).resolve()),
        expected_judge=str(clean_parent),
        expected_tokenizer=str(clean_parent),
        expected_prompt_sha256=config["prompt_sha256"],
        expected_weight_sha256=exact_hash_map(
            sidecar.get("weight_file_sha256"), "dose weight"
        ),
        expected_model_support_sha256=exact_hash_map(
            sidecar.get("support_file_sha256"), "dose support"
        ),
        expected_tokenizer_support_sha256=config["clean_parent_identity"][
            "support_file_sha256"
        ],
        expected_judge_support_sha256=config["clean_parent_identity"][
            "support_file_sha256"
        ],
        expected_judge_weight_sha256=config["clean_parent_identity"][
            "weight_file_sha256"
        ],
        expected_policy=V2_POLICY,
        expected_policy_fingerprint=config["clean_ruler"]["policy_fingerprint"],
    )
    payload = validate_finite_scalar_payload(
        validate_certification_scalar_execution(
            read_json(scalar_path), f"heavy u={u} seed={seed}"
        ),
        f"heavy u={u} seed={seed}",
    )
    normalised, scalar, directions = normalise_components_bidirectional(
        payload["components"], baseline, positive, negative
    )
    scalar = require_scalar(scalar, f"heavy u={u} seed={seed}")
    if (
        abs(require_scalar(payload.get("scalar_0_100"), "stored scalar") - scalar) > 1e-9
        or payload.get("normalised_components") != normalised
        or payload.get("normalisation_directions") != directions
    ):
        raise RuntimeError(f"scalar normalisation changed at u={u} seed={seed}")
    value, reanalysis = write_scalar_reanalysis(
        scalar_path, baseline, positive, negative, sources
    )
    if abs(float(value) - scalar) > 1e-9:
        raise RuntimeError(f"reanalysis scalar changed at u={u} seed={seed}")
    expected_reanalysis = {
        "normalisation_version": V2_POLICY,
        "source_scalar_json": str(Path(scalar_path)),
        "source_scalar_sha256": sha256_of_file(scalar_path),
        "policy_fingerprint": config["clean_ruler"]["policy_fingerprint"],
        "components": payload["components"],
        "normalised_components": normalised,
        "normalisation_directions": directions,
        "scalar_0_100": scalar,
        "baseline_components": baseline,
        "positive_component_anchor": positive,
        "negative_component_anchor": negative,
        "component_anchor_sources": sources,
    }
    if read_json(reanalysis) != expected_reanalysis:
        raise RuntimeError(f"deep reanalysis semantics changed at u={u} seed={seed}")
    return {
        "controller_u": float(u),
        "physical_alpha": float(alpha),
        "seed": int(seed),
        "scalar": scalar,
        "raw_components": payload["components"],
        "normalised_components": normalised,
        "normalisation_directions": directions,
        "scalar_json": str(Path(scalar_path).resolve()),
        "scalar_sha256": sha256_of_file(scalar_path),
        "reanalysis_json": str(Path(reanalysis).resolve()),
        "reanalysis_sha256": sha256_of_file(reanalysis),
        "decay_dose_json": str(Path(sidecar_path).resolve()),
        "decay_dose_sha256": sha256_of_file(sidecar_path),
    }


def aggregate_seed_entries(per_seed):
    if (
        not isinstance(per_seed, list)
        or len(per_seed) != 3
        or [item.get("seed") for item in per_seed] != list(CHILD_SEEDS)
    ):
        raise RuntimeError("aggregate requires exact child seeds 0/1/2")
    for item in per_seed:
        if not isinstance(item, dict) or set(item) != SCALAR_RECORD_KEYS:
            raise RuntimeError("child scalar record schema changed")
        require_finite_tree(item, "child scalar record")
        if set(item["raw_components"]) != set(WEIGHTS):
            raise RuntimeError("child raw component schema changed")
        if set(item["normalised_components"]) != set(WEIGHTS):
            raise RuntimeError("child normalised component schema changed")
        if set(item["normalisation_directions"]) != set(WEIGHTS):
            raise RuntimeError("child direction schema changed")
        for label in ("raw_components", "normalised_components"):
            if any(
                isinstance(value, bool) or not isinstance(value, (int, float))
                for value in item[label].values()
            ):
                raise RuntimeError(f"child {label} values are not numeric")
        if any(
            not isinstance(value, str)
            for value in item["normalisation_directions"].values()
        ):
            raise RuntimeError("child direction values are not strings")
    if len({item["controller_u"] for item in per_seed}) != 1:
        raise RuntimeError("aggregate child u coordinates differ")
    if len({item["physical_alpha"] for item in per_seed}) != 1:
        raise RuntimeError("aggregate child physical alphas differ")
    values = [entry["scalar"] for entry in per_seed]
    for index, value in enumerate(values):
        require_scalar(value, f"aggregate child scalar {index}")
    return {
        "physical_alpha": per_seed[0]["physical_alpha"],
        "per_seed": per_seed,
        "mean": sum(values) / len(values),
        "raw_range": max(values) - min(values),
        "raw_component_means": {
            key: sum(item["raw_components"][key] for item in per_seed) / len(per_seed)
            for key in WEIGHTS
        },
        "normalised_component_means": {
            key: sum(item["normalised_components"][key] for item in per_seed)
            / len(per_seed)
            for key in WEIGHTS
        },
        "normalisation_direction_counts": {
            key: {
                direction: sum(
                    item["normalisation_directions"][key] == direction
                    for item in per_seed
                )
                for direction in sorted(
                    {item["normalisation_directions"][key] for item in per_seed}
                )
            }
            for key in WEIGHTS
        },
    }


def artifact_inside(root, path, label):
    root, path = Path(root).resolve(), Path(path).resolve()
    if root not in path.parents or not path.is_file():
        raise RuntimeError(f"sealed heavy {label} is outside the archive")
    return path


def validate_stored_scalar_record(
    root, record, expected_u, expected_alpha, expected_seed, expected_source,
    clean_parent, config, baseline, positive, negative, sources, expected_dir=None,
):
    if not isinstance(record, dict) or set(record) != SCALAR_RECORD_KEYS:
        raise RuntimeError("sealed heavy scalar record schema changed")
    if (
        record.get("controller_u") != float(expected_u)
        or record.get("physical_alpha") != float(expected_alpha)
        or record.get("seed") != int(expected_seed)
    ):
        raise RuntimeError("sealed heavy scalar coordinate/provenance changed")
    for key in ("scalar_sha256", "reanalysis_sha256", "decay_dose_sha256"):
        if re.fullmatch(r"[0-9a-f]{64}", str(record.get(key))) is None:
            raise RuntimeError("sealed heavy scalar record has malformed digest")
    scalar_path = artifact_inside(root, record.get("scalar_json", ""), "scalar")
    sidecar_path = artifact_inside(
        root, record.get("decay_dose_json", ""), "dose sidecar"
    )
    reanalysis = artifact_inside(
        root, record.get("reanalysis_json", ""), "scalar reanalysis"
    )
    if expected_dir is not None and scalar_path.parent != Path(expected_dir).resolve():
        raise RuntimeError("sealed heavy scalar record moved from its canonical dose")
    if (
        scalar_path.name != "scalar.json"
        or sidecar_path != scalar_path.parent / "decay_dose.json"
        or reanalysis != scalar_path.parent / "scalar_reanalysis_bidirectional_v2.json"
    ):
        raise RuntimeError("sealed heavy scalar filenames are not canonical")
    if (
        record.get("scalar_sha256") != sha256_of_file(scalar_path)
        or record.get("decay_dose_sha256") != sha256_of_file(sidecar_path)
        or record.get("reanalysis_sha256") != sha256_of_file(reanalysis)
    ):
        raise RuntimeError("sealed heavy scalar record hash changed")
    checkpoint = scalar_path.parent / "checkpoint"
    expected = scalar_bundle(
        scalar_path, sidecar_path, checkpoint, expected_source, clean_parent,
        config, baseline, positive, negative, sources, expected_u,
        expected_alpha, expected_seed,
    )
    if expected != record:
        raise RuntimeError("sealed heavy scalar record semantics changed")


def validate_stage_marker(
    root, name, config_fingerprint, source_fingerprint, u, alpha, beta, seed,
    scalar_path, sidecar_path,
):
    marker = stage_marker(root, name)
    if not marker.is_file():
        raise RuntimeError(f"sealed heavy stage marker missing: {name}")
    inputs = {
        "source_identity_fingerprint": source_fingerprint,
        "controller_u": float(u),
        "physical_alpha": float(alpha),
        "beta": float(beta),
        "seed": int(seed),
    }
    expected = expected_stage_payload(
        name, config_fingerprint, inputs, (scalar_path, sidecar_path)
    )
    if read_json(marker) != expected:
        raise RuntimeError(f"sealed heavy stage marker semantics changed: {name}")


def validate_deletion_evidence(config, dose_dir, u, alpha, seed, record):
    checkpoint = Path(dose_dir) / "checkpoint"
    if checkpoint.exists():
        raise RuntimeError("sealed heavy child checkpoint was not deleted")
    path = Path(dose_dir) / "checkpoint_deletion.json"
    if not path.is_file():
        raise RuntimeError("sealed heavy child lacks deletion evidence")
    evidence = read_json(path)
    snapshot = {
        key: evidence.get(key)
        for key in (
            "checkpoint_weight_sha256", "checkpoint_support_file_sha256",
            "checkpoint_sidecar_sha256", "archived_sidecar_sha256",
        )
    }
    expected = expected_deletion_evidence(
        config["fingerprint"], u, alpha, config["beta"], seed, record, snapshot,
        "checkpoint_deleted_after_validation",
    )
    sidecar_path = Path(record["decay_dose_json"])
    sidecar = read_json(sidecar_path)
    if (
        evidence != expected
        or snapshot["checkpoint_weight_sha256"] != sidecar.get("weight_file_sha256")
        or snapshot["checkpoint_support_file_sha256"]
        != sidecar.get("support_file_sha256")
        or snapshot["checkpoint_sidecar_sha256"] != sha256_of_file(sidecar_path)
        or snapshot["archived_sidecar_sha256"] != sha256_of_file(sidecar_path)
    ):
        raise RuntimeError("sealed heavy deletion evidence semantics changed")


def validate_exact_archive_layout(root, summary, parent_checkpoint):
    """Reject every unrecognised member, alias directory, and leftover checkpoint."""
    root = Path(root).resolve()
    allowed_files = {
        root / "run_config.json", root / SUMMARY_NAME, root / "COMPLETE.json",
        root / "commands.log", root / "heavy_parent_identity.json",
        root / "heavy_parent" / "scalar.json",
        root / "heavy_parent" / "decay_dose.json",
        root / "heavy_parent" / "scalar_reanalysis_bidirectional_v2.json",
    }
    allowed_dirs = {root / "stages", root / "heavy_parent", parent_checkpoint}
    identity = summary["heavy_parent"]["identity"]
    expected_checkpoint_names = (
        set(identity["weight_file_sha256"])
        | set(identity["support_file_sha256"])
        | {"decay_dose.json"}
    )
    checkpoint_files = {
        path.name for path in parent_checkpoint.iterdir() if path.is_file()
    }
    if (
        checkpoint_files != expected_checkpoint_names
        or any(path.is_dir() for path in parent_checkpoint.iterdir())
    ):
        raise RuntimeError("retained heavy checkpoint layout changed")
    allowed_files.update(path for path in parent_checkpoint.iterdir() if path.is_file())
    parent_pass = summary["gates"]["heavy_parent_selection_pass"] is True
    stage_names = {"heavy_parent_u0.65_seed7.json"}
    if parent_pass:
        stage_names |= {
            f"child_u{u:g}_seed{seed}.json"
            for u in INTERIOR_U for seed in CHILD_SEEDS
        } | {"child_u1_seed0.json"}
        for u in (*INTERIOR_U, 1.0):
            seeds = CHILD_SEEDS if u != 1.0 else (0,)
            for seed in seeds:
                dose_dir = root / "sweep" / f"u{u:g}_seed{seed}"
                allowed_dirs.add(dose_dir)
                allowed_files.update(
                    {
                        dose_dir / "scalar.json", dose_dir / "decay_dose.json",
                        dose_dir / "scalar_reanalysis_bidirectional_v2.json",
                        dose_dir / "checkpoint_deletion.json",
                    }
                )
        allowed_dirs.add(root / "sweep")
    allowed_files.update(root / "stages" / name for name in stage_names)
    actual_files = {
        path for path in root.rglob("*")
        if path.is_file() and path != root / "MANIFEST.sha256"
    }
    if actual_files != allowed_files:
        extras = sorted(str(path.relative_to(root)) for path in actual_files - allowed_files)
        missing = sorted(str(path.relative_to(root)) for path in allowed_files - actual_files)
        raise RuntimeError(f"sealed heavy archive layout changed: extras={extras} missing={missing}")
    actual_dirs = {path for path in root.rglob("*") if path.is_dir()}
    if actual_dirs != allowed_dirs:
        extras = sorted(str(path.relative_to(root)) for path in actual_dirs - allowed_dirs)
        missing = sorted(str(path.relative_to(root)) for path in allowed_dirs - actual_dirs)
        raise RuntimeError(
            f"sealed heavy directory layout changed: extras={extras} missing={missing}"
        )


def validate_sealed_heavy(root):
    root = Path(root).resolve()
    seal = verify_manifest(root)
    if seal is None:
        return None
    config_path = root / "run_config.json"
    summary_path = root / SUMMARY_NAME
    complete_path = root / "COMPLETE.json"
    config, summary, complete = map(read_json, (config_path, summary_path, complete_path))
    config_body = {key: value for key, value in config.items() if key != "fingerprint"}
    if (
        set(config) != CONFIG_KEYS
        or set(summary) != SUMMARY_KEYS
        or set(complete) != {"status", "outcome", "summary_sha256", "config_fingerprint"}
        or config.get("version") != HEAVY_VERSION
        or config.get("certification_scope") != "heavy_parent_repeat_and_probe2_aggregate"
        or config.get("fingerprint") != fingerprint(config_body)
        or summary.get("certification_version") != HEAVY_VERSION
        or summary.get("certification_scope") != config.get("certification_scope")
        or complete.get("status") != "complete"
        or complete.get("outcome") != summary.get("gates", {}).get("probe2_verdict")
        or complete.get("summary_sha256") != sha256_of_file(summary_path)
        or complete.get("config_fingerprint") != config.get("fingerprint")
    ):
        raise RuntimeError("sealed heavy terminal envelope changed")
    validate_recorded_source_identity(Path.cwd(), config["code_commit"], config["code_sha256"])
    pilot_root = Path(config["pilot_archive"]["root"]).resolve()
    primary_root = Path(config["primary_archive"]["root"]).resolve()
    pilot_summary = validate_sealed_pilot(pilot_root)
    mapping_path, mapping = mapping_for_heavy(pilot_root, pilot_summary)
    primary = validate_sealed_primary(primary_root)
    primary_config, primary_summary, primary_identity = validate_primary_for_heavy(
        primary, pilot_root, pilot_summary, mapping_path, mapping
    )
    expected_pilot = {
        "root": str(pilot_root),
        "summary": str(pilot_root / "pilot_summary.json"),
        "summary_sha256": sha256_of_file(pilot_root / "pilot_summary.json"),
        "manifest_sha256": sha256_of_file(pilot_root / "MANIFEST.sha256"),
        "outcome": pilot_summary["outcome"],
    }
    expected_mapping = {
        "path": str(mapping_path),
        "sha256": sha256_of_file(mapping_path),
        "fingerprint": mapping["fingerprint"],
        "schema_sha256": MAPPING_SCHEMA_SHA256,
    }
    expected_alphas = {
        str(record["u"]): record["physical_alpha"] for record in mapping["controller"]
    }
    if (
        config["primary_archive"] != primary_identity
        or summary["primary_archive"] != primary_identity
        or config["pilot_archive"] != expected_pilot
        or summary["pilot_archive"] != expected_pilot
        or config["clean_parent_identity"] != primary_config["clean_parent_identity"]
        or config["clean_ruler_paths"] != primary_config["clean_ruler_paths"]
        or config["clean_ruler"] != primary_summary["clean_ruler"]
        or summary["clean_ruler"] != config["clean_ruler"]
        or config["prompt_sha256"] != primary_config["prompt_sha256"]
        or summary["normalisation_version"] != V2_POLICY
        or summary["normalisation_policy_fingerprint"]
        != config["clean_ruler"]["policy_fingerprint"]
        or summary["beta"] != config["beta"]
        or config["beta"] != mapping["beta"]
        or config["controller_mapping"] != expected_mapping
        or summary["controller_mapping"] != expected_mapping
        or summary["controller_coordinate"] != "u"
        or config["controller_coordinate"] != "u"
        or summary["controller_u"] != list(PUBLIC_CONTROLLER_U)
        or config["controller_u"] != list(PUBLIC_CONTROLLER_U)
        or config["physical_alpha_by_u"] != expected_alphas
        or summary["physical_alpha_by_u"] != expected_alphas
        or config["child_seeds"] != list(CHILD_SEEDS)
        or config["batch_size"] != 8
        or config["max_new_tokens"] != MAX_NEW_TOKENS
        or config["rules"] != expected_heavy_rules(mapping)
        or config["heavy_parent"] != expected_heavy_rules(mapping)["heavy_parent"]
    ):
        raise RuntimeError("sealed heavy dependency provenance changed")
    clean_parent = Path(config["clean_parent_identity"]["source_model"]).resolve()
    if model_identity(clean_parent) != config["clean_parent_identity"]:
        raise RuntimeError("sealed heavy clean parent changed")
    ruler_paths = {key: Path(value).resolve() for key, value in config["clean_ruler_paths"].items()}
    if config["clean_ruler"] != {
        key: sha256_of_file(path) for key, path in ruler_paths.items()
    } | {"policy_fingerprint": config["clean_ruler"]["policy_fingerprint"]}:
        raise RuntimeError("sealed heavy clean ruler files changed")
    baseline, positive, negative, sources = load_bidirectional_anchors(
        ruler_paths["baseline"], ruler_paths["normalisation_anchor"], ruler_paths["ladder"]
    )
    policy = bidirectional_policy_fingerprint(baseline, positive, negative, sources)
    if policy != config["clean_ruler"]["policy_fingerprint"]:
        raise RuntimeError("sealed heavy clean ruler policy changed")
    heavy = summary["heavy_parent"]
    identity = heavy.get("identity", {})
    identity_path = artifact_inside(root, heavy.get("identity_json", ""), "parent identity")
    checkpoint = Path(heavy.get("checkpoint", "")).resolve()
    body = {key: value for key, value in identity.items() if key != "fingerprint"}
    if (
        set(heavy) != HEAVY_PARENT_KEYS
        or set(identity) != HEAVY_IDENTITY_KEYS
        or identity_path != root / "heavy_parent_identity.json"
        or checkpoint != root / "heavy_parent" / "checkpoint"
        or read_json(identity_path) != identity
        or identity.get("fingerprint") != fingerprint(body)
        or identity.get("source_model") != str(checkpoint)
        or not checkpoint.is_dir()
        or model_weight_hashes(checkpoint) != identity.get("weight_file_sha256")
        or support_file_hashes(checkpoint) != identity.get("support_file_sha256")
        or identity.get("controller_u") != HEAVY_PARENT_U
        or identity.get("dose_seed") != HEAVY_PARENT_SEED
        or identity.get("administered_alpha") != mapping["heavy_parent"]["physical_alpha"]
        or identity.get("beta") != mapping["beta"]
        or identity.get("construction") != "one_shot_no_search"
        or identity.get("mapping_fingerprint") != mapping["fingerprint"]
        or identity.get("clean_parent_identity_fingerprint")
        != config["clean_parent_identity"]["fingerprint"]
    ):
        raise RuntimeError("sealed exact heavy parent changed")
    exact_hash_map(identity["weight_file_sha256"], "heavy parent weight")
    exact_hash_map(identity["support_file_sha256"], "heavy parent support")
    parent_internal_sidecar = checkpoint / "decay_dose.json"
    parent_archived_sidecar = root / "heavy_parent" / "decay_dose.json"
    parent_sidecar_payload = read_json(parent_archived_sidecar)
    if (
        not parent_internal_sidecar.is_file()
        or parent_internal_sidecar.read_bytes() != parent_archived_sidecar.read_bytes()
        or sha256_of_file(parent_internal_sidecar) != identity["dose_sidecar_sha256"]
        or parent_sidecar_payload.get("weight_file_sha256")
        != identity["weight_file_sha256"]
        or parent_sidecar_payload.get("support_file_sha256")
        != identity["support_file_sha256"]
    ):
        raise RuntimeError("retained heavy parent internal sidecar changed")
    parent_record = heavy.get("measurement")
    validate_stored_scalar_record(
        root, parent_record, HEAVY_PARENT_U, identity["administered_alpha"],
        HEAVY_PARENT_SEED, config["clean_parent_identity"], clean_parent, config,
        baseline, positive, negative, sources, root / "heavy_parent",
    )
    if (
        parent_record["scalar"] != identity["measured_global_scalar"]
        or identity["scalar_json_sha256"] != parent_record["scalar_sha256"]
        or identity["dose_sidecar_sha256"] != parent_record["decay_dose_sha256"]
        or identity["reanalysis_sha256"] != parent_record["reanalysis_sha256"]
    ):
        raise RuntimeError("heavy parent identity/measurement linkage changed")
    validate_stage_marker(
        root, "heavy_parent_u0.65_seed7", config["fingerprint"],
        config["clean_parent_identity"]["fingerprint"], HEAVY_PARENT_U,
        identity["administered_alpha"], identity["beta"], HEAVY_PARENT_SEED,
        root / "heavy_parent" / "scalar.json", parent_archived_sidecar,
    )
    expected_curve_keys = [str(u) for u in INTERIOR_U]
    if summary["curve"] and list(summary["curve"]) != expected_curve_keys:
        raise RuntimeError("sealed heavy curve keys are not canonical")
    for key, entry in summary["curve"].items():
        u = float(key)
        alpha = config["physical_alpha_by_u"][str(u)]
        for record in entry["per_seed"]:
            validate_stored_scalar_record(
                root, record, u, alpha, record["seed"], identity, clean_parent,
                config, baseline, positive, negative, sources,
                root / "sweep" / f"u{u:g}_seed{record['seed']}",
            )
            dose_dir = root / "sweep" / f"u{u:g}_seed{record['seed']}"
            validate_stage_marker(
                root, f"child_u{u:g}_seed{record['seed']}", config["fingerprint"],
                identity["fingerprint"], u, alpha, config["beta"], record["seed"],
                dose_dir / "scalar.json", dose_dir / "decay_dose.json",
            )
            validate_deletion_evidence(config, dose_dir, u, alpha, record["seed"], record)
    endpoint = summary["incremental_alpha1_endpoint"]
    if endpoint is not None:
        validate_stored_scalar_record(
            root, endpoint, 1.0, 1.0, 0, identity, clean_parent, config,
            baseline, positive, negative, sources, root / "sweep" / "u1_seed0",
        )
        endpoint_dir = root / "sweep" / "u1_seed0"
        validate_stage_marker(
            root, "child_u1_seed0", config["fingerprint"], identity["fingerprint"],
            1.0, 1.0, config["beta"], 0, endpoint_dir / "scalar.json",
            endpoint_dir / "decay_dose.json",
        )
        validate_deletion_evidence(config, endpoint_dir, 1.0, 1.0, 0, endpoint)
    parent_pass = summary["gates"].get("heavy_parent_selection_pass") is True
    expected_doses = (
        {f"u{u:g}_seed{seed}" for u in INTERIOR_U for seed in CHILD_SEEDS}
        | {"u1_seed0"}
        if parent_pass else set()
    )
    doses_root = root / "sweep"
    actual_doses = (
        {path.name for path in doses_root.iterdir() if path.is_dir()}
        if doses_root.is_dir() else set()
    )
    expected_stages = {"heavy_parent_u0.65_seed7.json"} | (
        {f"child_u{u:g}_seed{seed}.json" for u in INTERIOR_U for seed in CHILD_SEEDS}
        | {"child_u1_seed0.json"}
        if parent_pass else set()
    )
    stages_root = root / "stages"
    actual_stages = (
        {path.name for path in stages_root.iterdir() if path.is_file()}
        if stages_root.is_dir() else set()
    )
    expected_history = [{
        "controller_u": HEAVY_PARENT_U,
        "physical_alpha": mapping["heavy_parent"]["physical_alpha"],
        "beta": mapping["beta"], "seed": HEAVY_PARENT_SEED,
        "scalar": identity["measured_global_scalar"],
        "reason": "stored_g(.65)_one_shot_no_search",
    }]
    if (
        actual_doses != expected_doses
        or actual_stages != expected_stages
        or heavy.get("selection_history") != expected_history
        or summary["gates"]["ladder_monotonicity"]
        != primary_summary["gates"]["ladder_monotonicity"]
        or summary["gates"]["ladder_component_pass"]
        != primary_summary["gates"]["ladder_component_pass"]
        or summary["gates"]["ladder_gate_pass"]
        != primary_summary["gates"]["ladder_gate_pass"]
    ):
        raise RuntimeError("sealed heavy exact grid/ladder semantics changed")
    if any(path.is_dir() and path.name == "checkpoint" and path != checkpoint
           for path in root.rglob("checkpoint")):
        raise RuntimeError("sealed heavy archive retained a redrawable child")
    recompute_summary_semantics(summary)
    validate_exact_archive_layout(root, summary, checkpoint)
    return {"root": root, "seal": seal, "config": config, "summary": summary}


def main():
    args = parse_args()
    if args.batch_size != 8 or args.max_new_tokens != MAX_NEW_TOKENS:
        raise ValueError("v3 heavy scalar execution is frozen at batch=8/tokens=256")
    repo, root = Path.cwd().resolve(), Path(args.root).resolve()
    sealed = validate_sealed_heavy(root)
    if sealed is not None:
        print(f"Immutable Probe 2 v3 verdict: {sealed['summary']['gates']['probe2_verdict']}")
        return
    pilot_root, primary_root = Path(args.pilot_root).resolve(), Path(args.primary_root).resolve()
    clean_parent = Path(args.clean_parent_model).expanduser().resolve()
    if not clean_parent.is_dir():
        raise ValueError("--clean-parent-model must be an exact local model directory")
    if any(paths_overlap(root, protected) for protected in (pilot_root, primary_root, clean_parent)):
        raise ValueError("heavy output must be disjoint from every sealed input")
    pilot_summary = validate_sealed_pilot(pilot_root)
    if pilot_summary is None:
        raise RuntimeError("v3 pilot archive is not sealed")
    mapping_path, mapping = mapping_for_heavy(pilot_root, pilot_summary)
    primary = validate_sealed_primary(primary_root)
    primary_config, primary_summary, primary_archive = validate_primary_for_heavy(
        primary, pilot_root, pilot_summary, mapping_path, mapping
    )
    clean_identity = primary_config["clean_parent_identity"]
    if model_identity(clean_parent) != clean_identity:
        raise RuntimeError("clean parent differs from sealed v3 primary")
    source = committed_source_identity(repo)
    pilot_archive = {
        "root": str(pilot_root),
        "summary": str(pilot_root / "pilot_summary.json"),
        "summary_sha256": sha256_of_file(pilot_root / "pilot_summary.json"),
        "manifest_sha256": sha256_of_file(pilot_root / "MANIFEST.sha256"),
        "outcome": pilot_summary["outcome"],
    }
    mapping_identity = {
        "path": str(mapping_path),
        "sha256": sha256_of_file(mapping_path),
        "fingerprint": mapping["fingerprint"],
        "schema_sha256": MAPPING_SCHEMA_SHA256,
    }
    alpha_by_u = {
        str(record["u"]): record["physical_alpha"] for record in mapping["controller"]
    }
    ruler_paths = primary_config["clean_ruler_paths"]
    rules = expected_heavy_rules(mapping)
    config = {
        "version": HEAVY_VERSION,
        "certification_scope": "heavy_parent_repeat_and_probe2_aggregate",
        "clean_parent_identity": clean_identity,
        "pilot_archive": pilot_archive,
        "primary_archive": primary_archive,
        "clean_ruler_paths": ruler_paths,
        "clean_ruler": primary_summary["clean_ruler"],
        "prompt_sha256": primary_config["prompt_sha256"],
        "beta": mapping["beta"],
        "controller_mapping": mapping_identity,
        "controller_coordinate": "u",
        "controller_u": list(PUBLIC_CONTROLLER_U),
        "physical_alpha_by_u": alpha_by_u,
        "heavy_parent": rules["heavy_parent"],
        "child_seeds": list(CHILD_SEEDS),
        "batch_size": args.batch_size,
        "max_new_tokens": args.max_new_tokens,
        "rules": rules,
        "code_commit": source["commit"],
        "code_sha256": source["sha256"],
    }
    config["fingerprint"] = fingerprint(config)
    if root.exists() and any(root.iterdir()) and not (root / "run_config.json").is_file():
        raise RuntimeError("v3 heavy certification needs a fresh or matching root")
    root.mkdir(parents=True, exist_ok=True)
    config_path = root / "run_config.json"
    if config_path.exists():
        if read_json(config_path) != config:
            raise RuntimeError("v3 heavy resume configuration changed")
    else:
        write_json(config_path, config)
    python, log = Path(sys.executable).absolute(), root / "commands.log"
    baseline_path = Path(ruler_paths["baseline"])
    normalisation_anchor = Path(ruler_paths["normalisation_anchor"])
    ladder_path = Path(ruler_paths["ladder"])
    baseline, positive, negative, sources = load_bidirectional_anchors(
        baseline_path, normalisation_anchor, ladder_path
    )
    if bidirectional_policy_fingerprint(baseline, positive, negative, sources) != config[
        "clean_ruler"
    ]["policy_fingerprint"]:
        raise RuntimeError("primary clean-ruler fingerprint does not reproduce")

    def execute_dose(stage, u, source_model, source_identity_path, source_identity,
                     alpha, seed, checkpoint, scalar_path, sidecar_path):
        def action():
            scalar_path.parent.mkdir(parents=True, exist_ok=True)
            requires_apply = dose_resume_requires_apply(
                checkpoint, scalar_path, sidecar_path
            )
            if requires_apply:
                run_command(
                    [python, "scripts/apply_decay_noise.py", "--model", source_model,
                     "--alpha", str(alpha), "--beta", str(mapping["beta"]),
                     "--seed", str(seed), "--output-dir", checkpoint,
                     "--source-identity-json", source_identity_path],
                    log, repo,
                )
            validate_checkpoint_resume_provenance(
                checkpoint, source_identity, alpha, mapping["beta"], seed
            )
            if not scalar_path.is_file():
                run_command(
                    [python, "scripts/eval_decay_scalar.py", checkpoint, scalar_path,
                     "--batch-size", str(args.batch_size), "--max-new-tokens",
                     str(args.max_new_tokens), "--seed", "0", "--judge-model",
                     clean_parent, "--tokenizer-model", clean_parent,
                     "--baseline-json", baseline_path, "--anchor-json",
                     normalisation_anchor, "--ladder-json", ladder_path,
                     "--normalisation-policy", V2_POLICY],
                    log, repo,
                )
            recover_archived_sidecar(checkpoint, scalar_path, sidecar_path)

        ensure_stage(
            root, stage, config["fingerprint"],
            {"source_identity_fingerprint": source_identity["fingerprint"],
             "controller_u": float(u),
             "physical_alpha": float(alpha), "beta": mapping["beta"], "seed": seed},
            (scalar_path, sidecar_path), action,
        )

    parent_alpha = mapping["heavy_parent"]["physical_alpha"]
    parent_dir = root / "heavy_parent"
    parent_checkpoint = parent_dir / "checkpoint"
    parent_scalar_path = parent_dir / "scalar.json"
    parent_sidecar_path = parent_dir / "decay_dose.json"
    execute_dose(
        "heavy_parent_u0.65_seed7", HEAVY_PARENT_U, clean_parent,
        primary["identity_path"],
        clean_identity, parent_alpha, HEAVY_PARENT_SEED, parent_checkpoint,
        parent_scalar_path, parent_sidecar_path,
    )
    parent_measurement = scalar_bundle(
        parent_scalar_path, parent_sidecar_path, parent_checkpoint, clean_identity,
        clean_parent, config, baseline, positive, negative, sources,
        HEAVY_PARENT_U, parent_alpha, HEAVY_PARENT_SEED,
    )
    parent_sidecar = read_json(parent_sidecar_path)
    if (
        model_weight_hashes(parent_checkpoint) != parent_sidecar["weight_file_sha256"]
        or support_file_hashes(parent_checkpoint) != parent_sidecar["support_file_sha256"]
        or not (parent_checkpoint / "decay_dose.json").is_file()
        or (parent_checkpoint / "decay_dose.json").read_bytes()
        != parent_sidecar_path.read_bytes()
    ):
        raise RuntimeError("retained heavy parent checkpoint bytes changed")
    heavy_identity = {
        "source_model": str(parent_checkpoint),
        "weight_file_sha256": parent_sidecar["weight_file_sha256"],
        "support_file_sha256": parent_sidecar["support_file_sha256"],
        "clean_parent_identity_fingerprint": clean_identity["fingerprint"],
        "dose_sidecar_sha256": parent_measurement["decay_dose_sha256"],
        "scalar_json_sha256": parent_measurement["scalar_sha256"],
        "reanalysis_sha256": parent_measurement["reanalysis_sha256"],
        "administered_alpha": parent_alpha,
        "controller_u": HEAVY_PARENT_U,
        "beta": mapping["beta"],
        "dose_seed": HEAVY_PARENT_SEED,
        "measured_global_scalar": parent_measurement["scalar"],
        "mapping_fingerprint": mapping["fingerprint"],
        "construction": "one_shot_no_search",
    }
    heavy_identity["fingerprint"] = fingerprint(heavy_identity)
    identity_path = root / "heavy_parent_identity.json"
    if identity_path.exists():
        if read_json(identity_path) != heavy_identity:
            raise RuntimeError("resumed heavy parent identity changed")
    else:
        write_json(identity_path, heavy_identity)
    selection_history = [{
        "controller_u": HEAVY_PARENT_U,
        "physical_alpha": parent_alpha,
        "beta": mapping["beta"],
        "seed": HEAVY_PARENT_SEED,
        "scalar": parent_measurement["scalar"],
        "reason": "stored_g(.65)_one_shot_no_search",
    }]

    def base_summary(curve, endpoint, gates):
        return {
            "certification_version": HEAVY_VERSION,
            "certification_scope": "heavy_parent_repeat_and_probe2_aggregate",
            "primary_archive": primary_archive,
            "pilot_archive": pilot_archive,
            "clean_ruler": config["clean_ruler"],
            "normalisation_version": V2_POLICY,
            "normalisation_policy_fingerprint": config["clean_ruler"]["policy_fingerprint"],
            "beta": mapping["beta"],
            "controller_mapping": mapping_identity,
            "controller_coordinate": "u",
            "controller_u": list(PUBLIC_CONTROLLER_U),
            "physical_alpha_by_u": alpha_by_u,
            "heavy_parent": {
                "identity": heavy_identity,
                "identity_json": str(identity_path),
                "selection_history": selection_history,
                "checkpoint": str(parent_checkpoint),
                "measurement": parent_measurement,
            },
            "incremental_alpha1_endpoint": endpoint,
            "curve": {str(u): curve[u] for u in sorted(curve)},
            "gates": gates,
        }

    if not HEAVY_PARENT_BAND[0] <= parent_measurement["scalar"] <= HEAVY_PARENT_BAND[1]:
        gates = parent_failure_gates(parent_measurement["scalar"], primary_summary["gates"])
        summary = base_summary({}, None, gates)
    else:
        curve = {}

        def child(u, seed):
            alpha = alpha_by_u[str(u)]
            tag = f"u{u:g}_seed{seed}"
            dose_dir = root / "sweep" / tag
            checkpoint = dose_dir / "checkpoint"
            scalar_path = dose_dir / "scalar.json"
            sidecar_path = dose_dir / "decay_dose.json"
            execute_dose(
                f"child_u{u:g}_seed{seed}", u, parent_checkpoint, identity_path,
                heavy_identity, alpha, seed, checkpoint, scalar_path, sidecar_path,
            )
            record = scalar_bundle(
                scalar_path, sidecar_path, checkpoint, heavy_identity, clean_parent,
                config, baseline, positive, negative, sources, u, alpha, seed,
            )
            delete_validated_child_checkpoint(
                checkpoint, dose_dir, root, config["fingerprint"], u, alpha,
                mapping["beta"], seed, record,
            )
            return record

        for u in INTERIOR_U:
            curve[u] = aggregate_seed_entries([child(u, seed) for seed in CHILD_SEEDS])
            print(f"heavy u={u:g}: mean={curve[u]['mean']:.2f}", flush=True)
        endpoint = child(1.0, 0)
        gates = analyse_heavy_curve(
            curve, parent_measurement["scalar"], endpoint["scalar"],
            primary_summary["gates"], alpha_by_u,
        )
        summary = base_summary(curve, endpoint, gates)
    summary_path = root / SUMMARY_NAME
    write_json(summary_path, summary)
    write_json(
        root / "COMPLETE.json",
        {"status": "complete", "outcome": summary["gates"]["probe2_verdict"],
         "summary_sha256": sha256_of_file(summary_path),
         "config_fingerprint": config["fingerprint"]},
    )
    seal = write_manifest(root)
    validate_sealed_heavy(root)
    print(f"PROBE 2 OVERALL VERDICT: {summary['gates']['probe2_verdict']}")
    print(f"Sealed {seal['path']} ({seal['entry_count']} files)")


if __name__ == "__main__":
    main()
