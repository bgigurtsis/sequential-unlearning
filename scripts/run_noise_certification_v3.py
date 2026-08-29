"""Probe 2 v3 fresh primary certification on the frozen public controller.

The promoted seed-11 pilot is an immutable input.  This runner evaluates only
the eight precommitted interior controller doses with fresh noise seeds 0/1/2.
It never refits the controller, bisects physical alpha, or inserts a dose.
"""

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from decay_scalar_normalization import (
    V2_POLICY,
    WEIGHTS,
    bidirectional_policy_fingerprint,
    load_bidirectional_anchors,
    normalise_components_bidirectional,
)
from run_noise_sweep import (
    isotonic_running_max,
    model_weight_hashes,
    pchip_eval,
    read_ladder_gate,
    spearman,
    support_file_hashes,
    validate_ladder_artifact,
    validate_scalar_artifact,
)
from run_noise_pilot_v3 import (
    MAPPING_SCHEMA,
    MAPPING_SCHEMA_SHA256,
    fingerprint,
    model_identity,
    read_json,
    require_scalar,
    sha256_of_file,
    validate_sealed_pilot,
)


CERTIFICATION_VERSION = "probe2_weight_noise_primary_certification_v3"
SUMMARY_NAME = "primary_summary_v3.json"
CONFIG_NAME = "run_config.json"
COMPLETE_NAME = "COMPLETE.json"
MANIFEST_NAME = "MANIFEST.sha256"
INTERIOR_U = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.75, 0.9)
CONTROLLER_U = (0.0, *INTERIOR_U, 1.0)
CERTIFICATION_SEEDS = (0, 1, 2)
EXECUTED_SOURCE_PATHS = (
    "scripts/run_noise_certification_v3.py",
    "scripts/apply_decay_noise.py",
    "scripts/eval_decay_scalar.py",
    "scripts/decay_scalar_normalization.py",
    "scripts/run_noise_sweep.py",
    "scripts/run_noise_pilot_v3.py",
    "scripts/finalize_probe2_impossible.py",
)


def reject_nonfinite(payload, label="JSON payload"):
    """Reject NaN/Inf recursively before comparison, hashing, or serialization."""
    if isinstance(payload, bool) or payload is None or isinstance(payload, str):
        return payload
    if isinstance(payload, (int, float)):
        if not math.isfinite(float(payload)):
            raise RuntimeError(f"{label} contains a nonfinite numeric value")
        return payload
    if isinstance(payload, dict):
        for key, value in payload.items():
            reject_nonfinite(value, f"{label}.{key}")
        return payload
    if isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            reject_nonfinite(value, f"{label}[{index}]")
        return payload
    raise RuntimeError(f"{label} contains a non-JSON value")


def finite_safe_equal(left, right):
    """Deep equality which can never treat a non-finite numeric as acceptable."""
    try:
        reject_nonfinite(left, "left comparison value")
        reject_nonfinite(right, "right comparison value")
    except RuntimeError:
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(
            finite_safe_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            finite_safe_equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def write_json(path, payload):
    reject_nonfinite(payload, f"JSON output {path}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        rendered = json.dumps(
            payload, indent=2, ensure_ascii=False, allow_nan=False
        ) + "\n"
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"refusing non-canonical JSON output: {path}") from error
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def validate_finite_scalar_payload(payload, label="scalar artifact"):
    reject_nonfinite(payload, label)
    components = payload.get("components")
    if not isinstance(components, dict) or set(components) != set(WEIGHTS):
        raise RuntimeError(f"{label} has wrong raw component keys")
    for key, value in components.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuntimeError(f"{label} raw component {key} is not numeric")
        if not math.isfinite(float(value)):
            raise RuntimeError(f"{label} raw component {key} is nonfinite")
    require_scalar(payload.get("scalar_0_100"), f"{label} scalar_0_100")
    reject_nonfinite(payload.get("normalised_components"), f"{label} normalised components")
    return payload


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-model", required=True)
    parser.add_argument("--pilot-summary", required=True)
    parser.add_argument("--root", default="derisk/probe2_noise_v3_primary")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    return parser.parse_args()


def expected_certification_rules():
    return {
        "coordinate": "public_controller_u_not_physical_alpha",
        "interior_u": list(INTERIOR_U),
        "seeds": list(CERTIFICATION_SEEDS),
        "scalar_decode_seed": 0,
        "spearman_min_inclusive": 0.95,
        "spearman_points": "eight_interior_seed_means_only",
        "loo_max_inclusive": 3.0,
        "loo_policy": (
            "hold_raw_interior_mean; fit_running_max_of_remaining_raw_means; "
            "u0_and_u1_are_supports_never_held"
        ),
        "raw_mean_policy": "nondecreasing_including_u0_and_u1_supports",
        "per_dose_raw_seed_range_max_inclusive": 6.0,
        "range_points": "eight_interior_doses_only",
        "ladder_gate": "unchanged_four_component_v2_ladder",
        "dose_policy": "exact_grid_only_no_bisection_refit_or_new_points",
        "checkpoint_deletion": (
            "verify_live_weight_and_support_hashes_and_internal_sidecar_byte_equality; "
            "write_durable_receipt_before_validated_deletion"
        ),
        "pass_probe2_verdict": "INCOMPLETE_PENDING_HEAVY_PARENT",
    }


def validate_config_args(args):
    actual = {
        "batch_size": args.batch_size,
        "max_new_tokens": args.max_new_tokens,
    }
    expected = {"batch_size": 8, "max_new_tokens": 256}
    if actual != expected:
        raise ValueError(
            f"v3 primary certification configuration is frozen: {expected}; got {actual}"
        )


def validate_certification_scalar_execution(payload, label="certification scalar"):
    expected_decoding = {
        "method": "greedy",
        "max_new_tokens": 256,
        "batch_size": 8,
        "padding_side": "left",
    }
    if (
        payload.get("seed") != 0
        or payload.get("decoding") != expected_decoding
        or payload.get("limit") is not None
        or payload.get("weights") != WEIGHTS
        or payload.get("judge_parse_complete") is not True
        or payload.get("judge_unparsed_count") != 0
        or payload.get("normalisation_policy_requested") != V2_POLICY
        or payload.get("normalisation_policy") != V2_POLICY
    ):
        raise RuntimeError(f"{label} violates strict seed-0 scalar provenance")
    return payload


def committed_source_identity(repo, relative_paths, expected_commit=None):
    repo = Path(repo).resolve()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise RuntimeError("certification cannot bind a valid Git HEAD")
    if expected_commit is not None and commit != expected_commit:
        raise RuntimeError("certification Git HEAD changed")
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
                f"certification source is not committed at HEAD: {relative}"
            ) from error
        current_oid = subprocess.check_output(
            ["git", "hash-object", "--path", relative, relative],
            cwd=repo,
            text=True,
        ).strip()
        committed_oid = subprocess.check_output(
            ["git", "rev-parse", f"{commit}:{relative}"], cwd=repo, text=True
        ).strip()
        if current_oid != committed_oid:
            raise RuntimeError(
                f"certification source differs from its HEAD blob: {relative}"
            )
        hashes[relative] = hashlib.sha256(blob).hexdigest()
    return {"commit": commit, "sha256": hashes}


def validate_recorded_source_identity(repo, commit, hashes):
    if (
        re.fullmatch(r"[0-9a-f]{40}", str(commit)) is None
        or set(hashes or {}) != set(EXECUTED_SOURCE_PATHS)
    ):
        raise RuntimeError("sealed primary has malformed committed-source identity")
    for relative in EXECUTED_SOURCE_PATHS:
        try:
            blob = subprocess.run(
                ["git", "show", f"{commit}:{relative}"],
                cwd=repo,
                check=True,
                capture_output=True,
            ).stdout
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"sealed primary source commit lacks {relative}"
            ) from error
        if hashlib.sha256(blob).hexdigest() != hashes[relative]:
            raise RuntimeError(f"sealed primary source hash changed: {relative}")


def _u_key(value):
    return str(float(value))


def validate_controller_mapping(mapping):
    body = {key: value for key, value in mapping.items() if key != "fingerprint"}
    if (
        mapping.get("schema") != MAPPING_SCHEMA
        or mapping.get("schema_sha256") != MAPPING_SCHEMA_SHA256
        or mapping.get("fingerprint") != fingerprint(body)
        or mapping.get("source_arm") not in {"A", "B"}
        or mapping.get("seed_used_to_fit") != 11
    ):
        raise RuntimeError("promoted pilot controller mapping is malformed")
    controller = mapping.get("controller")
    if not isinstance(controller, list) or [row.get("u") for row in controller] != list(
        CONTROLLER_U
    ):
        raise RuntimeError("controller mapping does not contain the exact v3 u grid")
    alphas = []
    for row, u in zip(controller, CONTROLLER_U):
        alpha = float(row.get("physical_alpha"))
        if (
            not math.isfinite(alpha)
            or row.get("target_scalar") != 100.0 * u
            or round(alpha, 8) != alpha
        ):
            raise RuntimeError("controller mapping has invalid physical alpha")
        alphas.append(alpha)
    if (
        alphas[0] != 0.0
        or alphas[-1] != 1.0
        or len(set(alphas[1:-1])) != 8
        or any(not 0.0 < alpha < 1.0 for alpha in alphas[1:-1])
        or any(right <= left for left, right in zip(alphas, alphas[1:]))
    ):
        raise RuntimeError("controller mapping interior alphas are not frozen/distinct")
    expected_beta = 1.0 if mapping["source_arm"] == "A" else 0.1
    if float(mapping.get("beta")) != expected_beta:
        raise RuntimeError("controller mapping beta/arm mismatch")
    return {_u_key(u): alpha for u, alpha in zip(CONTROLLER_U, alphas)}


def validate_promoted_pilot(pilot_summary_path, parent):
    pilot_summary_path = Path(pilot_summary_path).resolve()
    if pilot_summary_path.name != "pilot_summary.json":
        raise RuntimeError("certification requires the canonical pilot summary")
    pilot_root = pilot_summary_path.parent
    summary = validate_sealed_pilot(pilot_root)
    if summary is None:
        raise RuntimeError("certification pilot is not sealed")
    if summary.get("outcome") not in {"PROMOTE_ARM_A", "PROMOTE_ARM_B"}:
        raise RuntimeError("certification requires a promoted v3 pilot")
    config = read_json(pilot_root / "run_config.json")
    if config.get("parent_identity") != parent:
        raise RuntimeError("certification clean parent differs from promoted pilot")
    mapping_path = Path(summary.get("controller_mapping", "")).resolve()
    if mapping_path != (pilot_root / "controller_mapping.json").resolve():
        raise RuntimeError("pilot mapping path is not canonical")
    mapping = read_json(mapping_path)
    physical = validate_controller_mapping(mapping)
    if (
        summary.get("controller_mapping_sha256") != sha256_of_file(mapping_path)
        or summary.get("controller_mapping_fingerprint") != mapping.get("fingerprint")
    ):
        raise RuntimeError("pilot summary does not bind the controller mapping")
    arm_key = "arm_a" if mapping["source_arm"] == "A" else "arm_b"
    endpoint = next(
        (
            row
            for row in summary[arm_key]["points"]
            if float(row.get("alpha")) == 1.0
        ),
        None,
    )
    if endpoint is None:
        raise RuntimeError("promoted pilot lacks its selected-beta endpoint")
    endpoint_path_key = (
        "scalar_json" if endpoint.get("scheduled") is True else "reference_artifact"
    )
    endpoint_hash_key = (
        "scalar_sha256"
        if endpoint.get("scheduled") is True
        else "reference_artifact_sha256"
    )
    endpoint_path = Path(endpoint.get(endpoint_path_key, "")).resolve()
    if endpoint.get(endpoint_hash_key) != sha256_of_file(endpoint_path):
        raise RuntimeError("promoted pilot terminal endpoint provenance changed")
    return {
        "root": str(pilot_root),
        "summary": summary,
        "config": config,
        "mapping": mapping,
        "mapping_path": str(mapping_path),
        "physical_alpha_by_u": physical,
        "beta": float(mapping["beta"]),
        "terminal_record": endpoint,
        "terminal_path": str(endpoint_path),
        "archive": {
            "root": str(pilot_root),
            "summary": str(pilot_summary_path),
            "summary_sha256": sha256_of_file(pilot_summary_path),
            "manifest_sha256": sha256_of_file(pilot_root / MANIFEST_NAME),
            "outcome": summary["outcome"],
        },
    }


def analyse_certification(points, ladder_gate=None):
    """Pure implementation of every frozen fresh-primary numeric gate."""
    reject_nonfinite(points, "certification points")
    if not isinstance(points, list) or [row.get("u") for row in points] != list(
        CONTROLLER_U
    ):
        raise RuntimeError("certification analysis requires the exact ordered u grid")
    raw_means = []
    ranges = {}
    for index, (row, u) in enumerate(zip(points, CONTROLLER_U)):
        if index in {0, len(points) - 1}:
            if row.get("support") is not True or row.get("per_seed") is not None:
                raise RuntimeError("certification endpoint is not a fit-only support")
            mean = require_scalar(row.get("mean"), f"u={u} support")
        else:
            records = row.get("per_seed")
            if (
                row.get("support") is not False
                or not isinstance(records, list)
                or [record.get("seed") for record in records]
                != list(CERTIFICATION_SEEDS)
            ):
                raise RuntimeError(f"u={u} does not have exact seeds 0/1/2")
            scalars = [
                require_scalar(record.get("scalar"), f"u={u} seed scalar")
                for record in records
            ]
            mean = sum(scalars) / 3.0
            raw_range = max(scalars) - min(scalars)
            stored_mean = require_scalar(row.get("mean"), f"u={u} stored mean")
            stored_range = row.get("raw_range")
            if (
                isinstance(stored_range, bool)
                or not isinstance(stored_range, (int, float))
                or not math.isfinite(float(stored_range))
                or not 0.0 <= float(stored_range) <= 100.0
            ):
                raise RuntimeError(f"u={u} stored raw range is not finite in [0,100]")
            if abs(stored_mean - mean) > 1e-12:
                raise RuntimeError(f"u={u} stored mean is not reproducible")
            if abs(float(stored_range) - raw_range) > 1e-12:
                raise RuntimeError(f"u={u} stored raw range is not reproducible")
            ranges[_u_key(u)] = raw_range
        raw_means.append(mean)
    interior_means = raw_means[1:-1]
    rho = spearman(list(INTERIOR_U), interior_means)
    loo = {}
    for index, u in enumerate(CONTROLLER_U[1:-1], start=1):
        rest_x = list(CONTROLLER_U[:index] + CONTROLLER_U[index + 1 :])
        rest_y = isotonic_running_max(raw_means[:index] + raw_means[index + 1 :])
        predicted = pchip_eval(rest_x, rest_y, u)
        loo[_u_key(u)] = abs(predicted - raw_means[index])
    max_loo = max(loo.values())
    nondecreasing = all(
        right >= left for left, right in zip(raw_means, raw_means[1:])
    )
    range_pass = all(value <= 6.0 for value in ranges.values())
    ladder_monotonicity = None
    ladder_component_pass = None
    ladder_pass = None
    if ladder_gate is not None:
        ladder_monotonicity, ladder_component_pass, ladder_pass = ladder_gate
    gates = {
        "spearman_seed_means": rho,
        "spearman_gate_pass": rho is not None and rho >= 0.95,
        "isotonic_policy": "running maximum (SYNTHESIS section 4)",
        "isotonic_fitted_means_with_endpoints": isotonic_running_max(raw_means),
        "loo_interpolation_errors": loo,
        "max_loo_error": max_loo,
        "loo_gate_pass": max_loo <= 3.0,
        "curve_raw_means_nondecreasing": nondecreasing,
        "raw_mean_nondecrease_gate_pass": nondecreasing,
        "per_dose_raw_ranges": ranges,
        "per_dose_range_gate_pass": range_pass,
        "ladder_monotonicity": ladder_monotonicity,
        "ladder_component_pass": ladder_component_pass,
        "ladder_gate_pass": ladder_pass,
        "no_refit_bisection_or_extra_points": True,
    }
    numeric_pass = all(
        (
            gates["spearman_gate_pass"],
            gates["loo_gate_pass"],
            gates["raw_mean_nondecrease_gate_pass"],
            gates["per_dose_range_gate_pass"],
            gates["ladder_gate_pass"],
        )
    )
    gates["primary_verdict"] = "PASS" if numeric_pass else "FAIL"
    gates["probe2_verdict"] = (
        "INCOMPLETE_PENDING_HEAVY_PARENT" if numeric_pass else "FAIL"
    )
    return gates


def stage_marker(root, u, seed):
    return Path(root) / "stages" / f"u{u:g}_seed{seed}.json"


def ensure_stage(
    root, u, seed, config_fp, outputs, action, resumable_unmarked_outputs=()
):
    marker = stage_marker(root, u, seed)
    stage_fp = fingerprint(
        {
            "version": CERTIFICATION_VERSION,
            "u": u,
            "seed": seed,
            "config": config_fp,
        }
    )
    outputs = [Path(path) for path in outputs]
    if marker.is_file():
        payload = read_json(marker)
        actual = {str(path): sha256_of_file(path) for path in outputs if path.is_file()}
        if (
            payload.get("status") != "complete"
            or payload.get("fingerprint") != stage_fp
            or payload.get("outputs") != actual
            or len(actual) != len(outputs)
        ):
            raise RuntimeError(f"primary stage provenance mismatch: u={u} seed={seed}")
        return
    if all(path.is_file() for path in outputs):
        write_json(
            marker,
            {
                "status": "complete",
                "fingerprint": stage_fp,
                "outputs": {str(path): sha256_of_file(path) for path in outputs},
            },
        )
        return
    existing = {path.resolve() for path in outputs if path.exists()}
    resumable = {Path(path).resolve() for path in resumable_unmarked_outputs}
    if existing and not existing <= resumable:
        raise RuntimeError(f"primary stage has unmarked outputs: u={u} seed={seed}")
    action()
    if not all(path.is_file() for path in outputs):
        raise RuntimeError(f"primary stage did not finish: u={u} seed={seed}")
    write_json(
        marker,
        {
            "status": "complete",
            "fingerprint": stage_fp,
            "outputs": {str(path): sha256_of_file(path) for path in outputs},
        },
    )


def safe_remove_checkpoint(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if root not in path.parents or path.name != "checkpoint":
        raise RuntimeError(f"unsafe checkpoint cleanup target: {path}")
    if path.exists():
        shutil.rmtree(path)


_PREDELETE_VALIDATION_TOKEN = object()


def remove_checkpoint_after_validation(
    path, root, validation_token, pending_receipt_path
):
    if validation_token is not _PREDELETE_VALIDATION_TOKEN:
        raise RuntimeError("refusing checkpoint cleanup before semantic validation")
    pending = read_json(pending_receipt_path)
    if (
        not isinstance(pending, dict)
        or pending.get("status") != "validated_pending_delete"
        or pending.get("checkpoint_deleted") is not False
        or pending.get("evidence_fingerprint")
        != fingerprint(pending.get("evidence"))
    ):
        raise RuntimeError("refusing checkpoint cleanup without durable validation evidence")
    safe_remove_checkpoint(path, root)


DELETION_RECEIPT_VERSION = "probe2_v3_checkpoint_deletion_receipt_v1"


def _deletion_evidence_from_archives(
    checkpoint, scalar_path, sidecar_path, marker_path, config, u, seed
):
    sidecar = read_json(sidecar_path)
    reject_nonfinite(sidecar, f"u={u} seed={seed} archived dose sidecar")
    return {
        "version": DELETION_RECEIPT_VERSION,
        "u": u,
        "seed": seed,
        "physical_alpha": config["physical_alpha_by_u"][_u_key(u)],
        "beta": config["beta"],
        "config_fingerprint": config["fingerprint"],
        "checkpoint": str(Path(checkpoint).resolve()),
        "checkpoint_weight_file_sha256": sidecar.get("weight_file_sha256"),
        "checkpoint_support_file_sha256": sidecar.get("support_file_sha256"),
        "checkpoint_internal_sidecar_sha256": sha256_of_file(sidecar_path),
        "archived_sidecar": str(Path(sidecar_path).resolve()),
        "archived_sidecar_sha256": sha256_of_file(sidecar_path),
        "scalar_artifact": str(Path(scalar_path).resolve()),
        "scalar_artifact_sha256": sha256_of_file(scalar_path),
        "stage_marker": str(Path(marker_path).resolve()),
        "stage_marker_sha256": sha256_of_file(marker_path),
        "verified_before_deletion": {
            "actual_checkpoint_weight_hashes": True,
            "actual_checkpoint_support_hashes": True,
            "internal_sidecar_byte_equal_to_archive": True,
            "scalar_and_stage_bound": True,
        },
    }


def validate_deletion_receipt(
    receipt_path,
    checkpoint,
    scalar_path,
    sidecar_path,
    marker_path,
    config,
    u,
    seed,
    require_complete=True,
):
    receipt_path = Path(receipt_path)
    if not receipt_path.is_file():
        raise RuntimeError(f"u={u} seed={seed} checkpoint deletion has no receipt")
    receipt = read_json(receipt_path)
    reject_nonfinite(receipt, f"u={u} seed={seed} deletion receipt")
    evidence = _deletion_evidence_from_archives(
        checkpoint, scalar_path, sidecar_path, marker_path, config, u, seed
    )
    allowed_status = {"validated_pending_delete", "validated_checkpoint_deleted"}
    if (
        set(receipt) != {
            "status", "checkpoint_deleted", "evidence", "evidence_fingerprint"
        }
        or receipt.get("status") not in allowed_status
        or not finite_safe_equal(receipt.get("evidence"), evidence)
        or receipt.get("evidence_fingerprint") != fingerprint(evidence)
        or (
            receipt.get("status") == "validated_pending_delete"
            and receipt.get("checkpoint_deleted") is not False
        )
        or (
            receipt.get("status") == "validated_checkpoint_deleted"
            and receipt.get("checkpoint_deleted") is not True
        )
        or (require_complete and receipt.get("status") != "validated_checkpoint_deleted")
    ):
        raise RuntimeError(f"u={u} seed={seed} deletion receipt is not reproducible")
    return receipt


def delete_checkpoint_with_evidence(
    checkpoint,
    root,
    receipt_path,
    scalar_path,
    sidecar_path,
    marker_path,
    config,
    u,
    seed,
):
    """Verify live bytes, record evidence, then remove exactly one checkpoint."""
    checkpoint = Path(checkpoint).resolve()
    receipt_path = Path(receipt_path).resolve()
    scalar_path = Path(scalar_path).resolve()
    sidecar_path = Path(sidecar_path).resolve()
    marker_path = Path(marker_path).resolve()
    if not checkpoint.exists():
        receipt = validate_deletion_receipt(
            receipt_path,
            checkpoint,
            scalar_path,
            sidecar_path,
            marker_path,
            config,
            u,
            seed,
            require_complete=False,
        )
        if receipt["status"] == "validated_pending_delete":
            receipt["status"] = "validated_checkpoint_deleted"
            receipt["checkpoint_deleted"] = True
            write_json(receipt_path, receipt)
        return validate_deletion_receipt(
            receipt_path,
            checkpoint,
            scalar_path,
            sidecar_path,
            marker_path,
            config,
            u,
            seed,
        )
    internal_sidecar = checkpoint / "decay_dose.json"
    if not internal_sidecar.is_file():
        raise RuntimeError("refusing deletion without checkpoint-internal dose sidecar")
    if sha256_of_file(internal_sidecar) != sha256_of_file(sidecar_path):
        raise RuntimeError("checkpoint-internal and archived dose sidecars differ by bytes")
    sidecar = read_json(sidecar_path)
    reject_nonfinite(sidecar, f"u={u} seed={seed} dose sidecar")
    actual_weights = model_weight_hashes(checkpoint)
    actual_support = support_file_hashes(checkpoint)
    if not finite_safe_equal(actual_weights, sidecar.get("weight_file_sha256")):
        raise RuntimeError("actual checkpoint weight hashes differ from dose sidecar")
    if not finite_safe_equal(actual_support, sidecar.get("support_file_sha256")):
        raise RuntimeError("actual checkpoint support hashes differ from dose sidecar")
    evidence = _deletion_evidence_from_archives(
        checkpoint, scalar_path, sidecar_path, marker_path, config, u, seed
    )
    pending = {
        "status": "validated_pending_delete",
        "checkpoint_deleted": False,
        "evidence": evidence,
        "evidence_fingerprint": fingerprint(evidence),
    }
    # A preexisting/forged marker never bypasses the live byte verification
    # above. It is overwritten only after all actual checkpoint hashes match.
    write_json(receipt_path, pending)
    remove_checkpoint_after_validation(
        checkpoint, root, _PREDELETE_VALIDATION_TOKEN, receipt_path
    )
    pending["status"] = "validated_checkpoint_deleted"
    pending["checkpoint_deleted"] = True
    write_json(receipt_path, pending)
    return validate_deletion_receipt(
        receipt_path,
        checkpoint,
        scalar_path,
        sidecar_path,
        marker_path,
        config,
        u,
        seed,
    )


def run_resumable_dose_action(
    checkpoint, scalar_path, sidecar_path, apply_action, evaluate_action
):
    """Run apply/eval without ever discarding unvalidated checkpoint bytes.

    A checkpoint with its dose sidecar is a completed apply that may resume at
    evaluation.  A checkpoint without that sidecar is an interrupted/unknown
    apply and is preserved fail-closed for diagnosis rather than redrawn.
    """
    checkpoint = Path(checkpoint)
    scalar_path = Path(scalar_path)
    sidecar_path = Path(sidecar_path)
    checkpoint_sidecar = checkpoint / "decay_dose.json"
    if checkpoint.exists():
        if not checkpoint.is_dir() or not checkpoint_sidecar.is_file():
            raise RuntimeError(
                "interrupted apply checkpoint preserved; refusing unvalidated redraw"
            )
    else:
        apply_action()
        if not checkpoint.is_dir() or not checkpoint_sidecar.is_file():
            raise RuntimeError(
                "apply did not produce complete dose provenance; checkpoint preserved"
            )
    evaluate_action()
    if not scalar_path.is_file():
        raise RuntimeError("evaluation did not produce scalar; checkpoint preserved")
    shutil.copy2(checkpoint_sidecar, sidecar_path)


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


def write_primary_manifest(root):
    root = Path(root).resolve()
    output, temporary = root / MANIFEST_NAME, root / f"{MANIFEST_NAME}.tmp"
    if temporary.exists():
        temporary.unlink()
    validate_canonical_archive_members(root)
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
    return verify_primary_manifest(root)


def expected_primary_archive_members():
    members = {
        CONFIG_NAME,
        "parent_identity.json",
        "commands.log",
        SUMMARY_NAME,
        COMPLETE_NAME,
    }
    for u in INTERIOR_U:
        for seed in CERTIFICATION_SEEDS:
            tag = f"u{u:g}_seed{seed}"
            members.add(f"stages/{tag}.json")
            members.add(f"doses/{tag}/scalar.json")
            members.add(f"doses/{tag}/decay_dose.json")
            members.add(f"doses/{tag}/deletion_receipt.json")
    return members


def validate_canonical_archive_members(root):
    root = Path(root).resolve()
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.resolve() != (root / MANIFEST_NAME).resolve()
    }
    expected = expected_primary_archive_members()
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise RuntimeError(
            f"primary archive member set is non-canonical: missing={missing}, extra={extra}"
        )
    root_directories = {path.name for path in root.iterdir() if path.is_dir()}
    if root_directories != {"doses", "stages"}:
        raise RuntimeError("primary archive has non-canonical top-level directories")
    return True


def verify_primary_manifest(root):
    root = Path(root).resolve()
    manifest = root / MANIFEST_NAME
    if not manifest.is_file():
        return None
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
            raise RuntimeError(f"malformed primary manifest line: {line!r}")
        try:
            int(digest, 16)
        except ValueError as error:
            raise RuntimeError(f"malformed primary manifest digest: {digest!r}") from error
        key = relative_path.as_posix()
        if key in expected:
            raise RuntimeError(f"duplicate primary manifest member: {key}")
        expected[key] = digest.lower()
    actual = {
        path.relative_to(root).as_posix(): sha256_of_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != manifest
    }
    if actual != expected:
        raise RuntimeError("sealed v3 primary archive changed")
    validate_canonical_archive_members(root)
    return {"path": str(manifest), "sha256": sha256_of_file(manifest)}


def _exact_hash_map(payload, label):
    if not isinstance(payload, dict) or not payload:
        raise RuntimeError(f"missing {label} hashes")
    for digest in payload.values():
        if not isinstance(digest, str) or len(digest) != 64:
            raise RuntimeError(f"malformed {label} hash")
        try:
            int(digest, 16)
        except ValueError as error:
            raise RuntimeError(f"malformed {label} hash") from error
    return payload


def _validate_dose_record(
    root, config, record, u, seed, baseline, positive, negative
):
    dose_dir = root / "doses" / f"u{u:g}_seed{seed}"
    scalar_path = dose_dir / "scalar.json"
    sidecar_path = dose_dir / "decay_dose.json"
    receipt_path = dose_dir / "deletion_receipt.json"
    checkpoint = dose_dir / "checkpoint"
    parent = config["clean_parent_identity"]
    alpha = config["physical_alpha_by_u"][_u_key(u)]
    if (
        record.get("seed") != seed
        or record.get("u") != u
        or record.get("physical_alpha") != alpha
        or Path(record.get("scalar_json", "")).resolve() != scalar_path.resolve()
        or record.get("scalar_sha256") != sha256_of_file(scalar_path)
        or Path(record.get("dose_sidecar", "")).resolve() != sidecar_path.resolve()
        or record.get("dose_sidecar_sha256") != sha256_of_file(sidecar_path)
        or Path(record.get("deletion_receipt", "")).resolve()
        != receipt_path.resolve()
        or record.get("deletion_receipt_sha256") != sha256_of_file(receipt_path)
        or record.get("checkpoint_deleted") is not True
        or checkpoint.exists()
    ):
        raise RuntimeError(f"sealed primary dose pointer changed: u={u} seed={seed}")
    if {path.name for path in dose_dir.iterdir()} != {
        "scalar.json", "decay_dose.json", "deletion_receipt.json"
    }:
        raise RuntimeError(f"sealed primary dose has unexpected files: u={u} seed={seed}")
    marker = stage_marker(root, u, seed)
    expected_stage = {
        "status": "complete",
        "fingerprint": fingerprint(
            {
                "version": CERTIFICATION_VERSION,
                "u": u,
                "seed": seed,
                "config": config["fingerprint"],
            }
        ),
        "outputs": {
            str(scalar_path): sha256_of_file(scalar_path),
            str(sidecar_path): sha256_of_file(sidecar_path),
        },
    }
    if read_json(marker) != expected_stage:
        raise RuntimeError(f"sealed primary stage marker changed: u={u} seed={seed}")
    validate_deletion_receipt(
        receipt_path,
        checkpoint,
        scalar_path,
        sidecar_path,
        marker,
        config,
        u,
        seed,
    )
    sidecar = read_json(sidecar_path)
    expected_sidecar = {
        "source_model": parent["source_model"],
        "tokenizer_source": parent["source_model"],
        "source_identity_fingerprint": parent["fingerprint"],
        "alpha": alpha,
        "beta": config["beta"],
        "seed": seed,
    }
    if (
        {key: sidecar.get(key) for key in expected_sidecar} != expected_sidecar
        or sidecar.get("source_identity") != parent
    ):
        raise RuntimeError(f"sealed dose provenance changed: u={u} seed={seed}")
    payload = validate_finite_scalar_payload(
        read_json(scalar_path), f"sealed u={u} seed={seed}"
    )
    validate_certification_scalar_execution(payload, f"sealed u={u} seed={seed}")
    validate_scalar_artifact(
        scalar_path,
        expected_model=str(checkpoint),
        expected_judge=parent["source_model"],
        expected_tokenizer=parent["source_model"],
        expected_prompt_sha256=config["prompt_sha256"],
        expected_weight_sha256=_exact_hash_map(
            sidecar.get("weight_file_sha256"), "dose weight"
        ),
        expected_model_support_sha256=_exact_hash_map(
            sidecar.get("support_file_sha256"), "dose support"
        ),
        expected_tokenizer_support_sha256=parent["support_file_sha256"],
        expected_judge_support_sha256=parent["support_file_sha256"],
        expected_judge_weight_sha256=parent["weight_file_sha256"],
        expected_policy=V2_POLICY,
        expected_policy_fingerprint=config["normalisation_policy_fingerprint"],
    )
    normalised, scalar, directions = normalise_components_bidirectional(
        payload["components"], baseline, positive, negative
    )
    scalar = require_scalar(scalar, f"sealed u={u} seed={seed}")
    if (
        abs(float(payload.get("scalar_0_100")) - scalar) > 1e-9
        or abs(float(record.get("scalar")) - scalar) > 1e-9
        or not finite_safe_equal(record.get("components"), payload.get("components"))
        or not finite_safe_equal(record.get("normalised_components"), normalised)
        or not finite_safe_equal(record.get("normalisation_directions"), directions)
        or not finite_safe_equal(payload.get("normalised_components"), normalised)
        or not finite_safe_equal(payload.get("normalisation_directions"), directions)
    ):
        raise RuntimeError(f"sealed scalar bundle changed: u={u} seed={seed}")


def validate_sealed_primary(root):
    root = Path(root).resolve()
    seal = verify_primary_manifest(root)
    if seal is None:
        return None
    validate_canonical_archive_members(root)
    config_path = root / CONFIG_NAME
    summary_path = root / SUMMARY_NAME
    identity_path = root / "parent_identity.json"
    complete_path = root / COMPLETE_NAME
    config, summary, identity, complete = map(
        read_json, (config_path, summary_path, identity_path, complete_path)
    )
    reject_nonfinite(config, "sealed run_config")
    reject_nonfinite(summary, "sealed primary summary")
    reject_nonfinite(identity, "sealed parent identity")
    reject_nonfinite(complete, "sealed completion marker")
    expected_config_keys = {
        "version", "certification_scope", "clean_parent_identity",
        "pilot_archive", "v2_archive", "clean_ruler_paths", "clean_ruler",
        "prompt_sha256", "normalisation_version",
        "normalisation_policy_fingerprint", "beta", "controller_mapping",
        "controller_coordinate", "controller_u", "physical_alpha_by_u",
        "endpoint_records", "seeds", "batch_size", "max_new_tokens", "rules",
        "code_commit", "code_sha256", "fingerprint",
    }
    config_body = {key: value for key, value in config.items() if key != "fingerprint"}
    expected_complete = {
        "status": "complete",
        "outcome": summary.get("gates", {}).get("primary_verdict"),
        "summary_sha256": sha256_of_file(summary_path),
        "config_fingerprint": config.get("fingerprint"),
    }
    if (
        set(config) != expected_config_keys
        or config.get("version") != CERTIFICATION_VERSION
        or config.get("certification_scope") != "clean_parent_primary_only"
        or config.get("fingerprint") != fingerprint(config_body)
        or config.get("rules") != expected_certification_rules()
        or config.get("seeds") != list(CERTIFICATION_SEEDS)
        or config.get("controller_u") != list(CONTROLLER_U)
        or config.get("controller_coordinate") != "u"
        or config.get("batch_size") != 8
        or config.get("max_new_tokens") != 256
        or identity != config.get("clean_parent_identity")
        or complete != expected_complete
    ):
        raise RuntimeError("sealed v3 primary configuration changed")
    validate_recorded_source_identity(
        Path.cwd(), config.get("code_commit"), config.get("code_sha256")
    )
    if model_identity(identity.get("source_model", "")) != identity:
        raise RuntimeError("sealed primary clean parent changed")
    pilot = validate_promoted_pilot(config["pilot_archive"]["summary"], identity)
    if (
        pilot["archive"] != config["pilot_archive"]
        or config.get("v2_archive") != pilot["config"]["v2"]
        or config.get("prompt_sha256") != pilot["config"]["v2"]["prompt_sha256"]
    ):
        raise RuntimeError("sealed primary pilot dependency changed")
    mapping_path = Path(pilot["mapping_path"])
    mapping_descriptor = {
        "path": str(mapping_path),
        "sha256": sha256_of_file(mapping_path),
        "fingerprint": pilot["mapping"]["fingerprint"],
        "schema_sha256": MAPPING_SCHEMA_SHA256,
    }
    if (
        config.get("controller_mapping") != mapping_descriptor
        or config.get("physical_alpha_by_u") != pilot["physical_alpha_by_u"]
        or config.get("beta") != pilot["beta"]
    ):
        raise RuntimeError("sealed primary mapping/beta provenance changed")
    v2_root = Path(pilot["config"]["v2"]["root"]).resolve()
    expected_paths = {
        "baseline": (v2_root / "baseline/scalar.json").resolve(),
        "terminal": Path(pilot["terminal_path"]).resolve(),
        "normalisation_anchor": (v2_root / "anchor/scalar.json").resolve(),
        "ladder": (v2_root / "ladder/corruption_ladder.json").resolve(),
    }
    paths = {key: Path(value).resolve() for key, value in config["clean_ruler_paths"].items()}
    if paths != expected_paths:
        raise RuntimeError("sealed primary ruler paths changed")
    expected_ruler = {
        key: sha256_of_file(path) for key, path in paths.items()
    }
    baseline, positive, negative, sources = load_bidirectional_anchors(
        paths["baseline"], paths["normalisation_anchor"], paths["ladder"]
    )
    policy_fp = bidirectional_policy_fingerprint(
        baseline, positive, negative, sources
    )
    expected_ruler["policy_fingerprint"] = policy_fp
    if (
        config.get("clean_ruler") != expected_ruler
        or config.get("normalisation_policy_fingerprint") != policy_fp
        or config.get("normalisation_version") != V2_POLICY
    ):
        raise RuntimeError("sealed primary clean ruler changed")
    expected_endpoints = {
        "u0": {
            "u": 0.0,
            "physical_alpha": 0.0,
            "support": True,
            "per_seed": None,
            "mean": require_scalar(
                pilot["config"]["v2"]["baseline_scalar"], "sealed clean support"
            ),
            "reference": "sealed_clean_v2_baseline",
            "artifact": str(paths["baseline"]),
            "artifact_sha256": sha256_of_file(paths["baseline"]),
        },
        "u1": {
            "u": 1.0,
            "physical_alpha": 1.0,
            "support": True,
            "per_seed": None,
            "mean": require_scalar(
                pilot["terminal_record"]["scalar"], "sealed terminal support"
            ),
            "reference": "promoted_pilot_selected_beta_endpoint",
            "artifact": str(paths["terminal"]),
            "artifact_sha256": sha256_of_file(paths["terminal"]),
            "pilot_arm": pilot["mapping"]["source_arm"],
            "historical_seed": pilot["terminal_record"].get("seed"),
        },
    }
    if config.get("endpoint_records") != expected_endpoints:
        raise RuntimeError("sealed primary endpoint provenance changed")
    validate_ladder_artifact(
        paths["ladder"],
        paths["baseline"],
        identity["source_model"],
        identity["support_file_sha256"],
        identity["weight_file_sha256"],
    )
    curve = summary.get("curve")
    if not isinstance(curve, dict) or list(curve) != [_u_key(u) for u in INTERIOR_U]:
        raise RuntimeError("sealed primary curve grid changed")
    expected_dose_names = {
        f"u{u:g}_seed{seed}" for u in INTERIOR_U for seed in CERTIFICATION_SEEDS
    }
    doses_root = root / "doses"
    actual_dose_names = (
        {path.name for path in doses_root.iterdir() if path.is_dir()}
        if doses_root.is_dir()
        else set()
    )
    expected_stage_names = {
        f"u{u:g}_seed{seed}.json" for u in INTERIOR_U for seed in CERTIFICATION_SEEDS
    }
    stages_root = root / "stages"
    actual_stage_names = (
        {path.name for path in stages_root.iterdir() if path.is_file()}
        if stages_root.is_dir()
        else set()
    )
    if actual_dose_names != expected_dose_names or actual_stage_names != expected_stage_names:
        raise RuntimeError("sealed primary contains a missing or extra controller dose")
    points = [summary["endpoints"]["u0"]]
    expected_curve_keys = {
        "u", "physical_alpha", "support", "per_seed", "mean", "raw_range",
        "raw_component_means", "normalised_component_means",
        "normalisation_direction_counts",
    }
    expected_seed_record_keys = {
        "u", "physical_alpha", "seed", "scalar", "components",
        "normalised_components", "normalisation_directions", "scalar_json",
        "scalar_sha256", "dose_sidecar", "dose_sidecar_sha256",
        "deletion_receipt", "deletion_receipt_sha256", "checkpoint_deleted",
    }
    for u in INTERIOR_U:
        row = curve[_u_key(u)]
        if (
            set(row) != expected_curve_keys
            or row.get("u") != u
            or row.get("physical_alpha")
            != config["physical_alpha_by_u"][_u_key(u)]
            or not isinstance(row.get("per_seed"), list)
            or any(set(record) != expected_seed_record_keys for record in row["per_seed"])
        ):
            raise RuntimeError(f"sealed primary curve coordinate changed at u={u}")
        for seed, record in zip(CERTIFICATION_SEEDS, row.get("per_seed", [])):
            _validate_dose_record(
                root, config, record, u, seed, baseline, positive, negative
            )
        points.append(row)
    points.append(summary["endpoints"]["u1"])
    if set(summary.get("endpoints", {})) != {"u0", "u1"}:
        raise RuntimeError("sealed primary endpoint schema changed")
    if summary["endpoints"]["u0"] != config["endpoint_records"]["u0"]:
        raise RuntimeError("sealed primary clean support changed")
    if summary["endpoints"]["u1"] != config["endpoint_records"]["u1"]:
        raise RuntimeError("sealed primary terminal support changed")
    recomputed_gates = analyse_certification(points, read_ladder_gate(paths["ladder"]))
    if recomputed_gates != summary.get("gates"):
        raise RuntimeError("sealed primary gates are not reproducible")
    expected_summary_fixed = {
        "certification_version": CERTIFICATION_VERSION,
        "certification_scope": "clean_parent_primary_only",
        "parent_model": identity["source_model"],
        "beta": config["beta"],
        "normalisation_version": V2_POLICY,
        "normalisation_policy_fingerprint": policy_fp,
        "clean_ruler": config["clean_ruler"],
        "primary_archive": {
            "root": str(root),
            "run_config": str(config_path),
            "summary": str(summary_path),
            "manifest": str(root / MANIFEST_NAME),
        },
        "pilot_archive": config["pilot_archive"],
        "controller_mapping": config["controller_mapping"],
        "controller_coordinate": "u",
        "controller_u": list(CONTROLLER_U),
        "physical_alpha_by_u": config["physical_alpha_by_u"],
        "baseline_scalar": points[0]["mean"],
        "terminal_weight_noise_scalar": points[-1]["mean"],
        "endpoints": summary["endpoints"],
        "curve": curve,
        "gates": recomputed_gates,
    }
    if summary != expected_summary_fixed:
        raise RuntimeError("sealed primary summary schema changed")
    if any(path.is_dir() and path.name == "checkpoint" for path in root.rglob("*")):
        raise RuntimeError("sealed primary retained a redrawable checkpoint")
    return {
        "root": root,
        "seal": seal,
        "config": config,
        "config_path": config_path,
        "summary": summary,
        "summary_path": summary_path,
        "identity": identity,
        "identity_path": identity_path,
        "complete_path": complete_path,
    }


def _paths_overlap(left, right):
    left, right = Path(left).resolve(), Path(right).resolve()
    return left == right or left in right.parents or right in left.parents


def main():
    args = parse_args()
    validate_config_args(args)
    repo = Path.cwd().resolve()
    root = Path(args.root).resolve()
    sealed = validate_sealed_primary(root)
    if sealed is not None:
        print(
            "Immutable Probe 2 v3 primary verdict: "
            + sealed["summary"]["gates"]["primary_verdict"]
        )
        return
    source = committed_source_identity(repo, EXECUTED_SOURCE_PATHS)
    parent_path = Path(args.parent_model).expanduser().resolve()
    if not parent_path.is_dir():
        raise ValueError("v3 primary parent must be an exact local model directory")
    parent = model_identity(parent_path)
    pilot = validate_promoted_pilot(args.pilot_summary, parent)
    v2_root = Path(pilot["config"]["v2"]["root"]).resolve()
    baseline_path = v2_root / "baseline/scalar.json"
    normalisation_anchor_path = v2_root / "anchor/scalar.json"
    ladder_path = v2_root / "ladder/corruption_ladder.json"
    terminal_path = Path(pilot["terminal_path"]).resolve()
    if any(_paths_overlap(root, protected) for protected in (parent_path, pilot["root"], v2_root)):
        raise ValueError("v3 primary root must not overlap its sealed inputs")
    baseline, positive, negative, sources = load_bidirectional_anchors(
        baseline_path, normalisation_anchor_path, ladder_path
    )
    policy_fp = bidirectional_policy_fingerprint(
        baseline, positive, negative, sources
    )
    if policy_fp != pilot["config"]["v2"]["policy_fingerprint"]:
        raise RuntimeError("promoted pilot clean ruler no longer reproduces")
    validate_ladder_artifact(
        ladder_path,
        baseline_path,
        parent["source_model"],
        parent["support_file_sha256"],
        parent["weight_file_sha256"],
    )
    prompt_sha256 = pilot["config"]["v2"]["prompt_sha256"]
    clean_ruler_paths = {
        "baseline": str(baseline_path.resolve()),
        "terminal": str(terminal_path),
        "normalisation_anchor": str(normalisation_anchor_path.resolve()),
        "ladder": str(ladder_path.resolve()),
    }
    clean_ruler = {
        key: sha256_of_file(path) for key, path in clean_ruler_paths.items()
    }
    clean_ruler["policy_fingerprint"] = policy_fp
    mapping_descriptor = {
        "path": pilot["mapping_path"],
        "sha256": sha256_of_file(pilot["mapping_path"]),
        "fingerprint": pilot["mapping"]["fingerprint"],
        "schema_sha256": MAPPING_SCHEMA_SHA256,
    }
    baseline_scalar = require_scalar(
        pilot["config"]["v2"]["baseline_scalar"], "clean u=0 support"
    )
    terminal_scalar = require_scalar(
        pilot["terminal_record"]["scalar"], "promoted u=1 support"
    )
    endpoint_records = {
        "u0": {
            "u": 0.0,
            "physical_alpha": 0.0,
            "support": True,
            "per_seed": None,
            "mean": baseline_scalar,
            "reference": "sealed_clean_v2_baseline",
            "artifact": str(baseline_path.resolve()),
            "artifact_sha256": sha256_of_file(baseline_path),
        },
        "u1": {
            "u": 1.0,
            "physical_alpha": 1.0,
            "support": True,
            "per_seed": None,
            "mean": terminal_scalar,
            "reference": "promoted_pilot_selected_beta_endpoint",
            "artifact": str(terminal_path),
            "artifact_sha256": sha256_of_file(terminal_path),
            "pilot_arm": pilot["mapping"]["source_arm"],
            "historical_seed": pilot["terminal_record"].get("seed"),
        },
    }
    config = {
        "version": CERTIFICATION_VERSION,
        "certification_scope": "clean_parent_primary_only",
        "clean_parent_identity": parent,
        "pilot_archive": pilot["archive"],
        "v2_archive": pilot["config"]["v2"],
        "clean_ruler_paths": clean_ruler_paths,
        "clean_ruler": clean_ruler,
        "prompt_sha256": prompt_sha256,
        "normalisation_version": V2_POLICY,
        "normalisation_policy_fingerprint": policy_fp,
        "beta": pilot["beta"],
        "controller_mapping": mapping_descriptor,
        "controller_coordinate": "u",
        "controller_u": list(CONTROLLER_U),
        "physical_alpha_by_u": pilot["physical_alpha_by_u"],
        "endpoint_records": endpoint_records,
        "seeds": list(CERTIFICATION_SEEDS),
        "batch_size": args.batch_size,
        "max_new_tokens": args.max_new_tokens,
        "rules": expected_certification_rules(),
        "code_commit": source["commit"],
        "code_sha256": source["sha256"],
    }
    config["fingerprint"] = fingerprint(config)
    if root.exists() and any(root.iterdir()) and not (root / CONFIG_NAME).is_file():
        raise RuntimeError("v3 primary requires a fresh root or matching run_config")
    root.mkdir(parents=True, exist_ok=True)
    config_path = root / CONFIG_NAME
    if config_path.exists():
        if read_json(config_path) != config:
            raise RuntimeError("v3 primary configuration changed; use a fresh root")
    else:
        write_json(config_path, config)
    identity_path = root / "parent_identity.json"
    if identity_path.exists():
        if read_json(identity_path) != parent:
            raise RuntimeError("v3 primary parent identity changed")
    else:
        write_json(identity_path, parent)
    python = Path(sys.executable).absolute()
    log = root / "commands.log"

    def run_dose(u, seed):
        alpha = config["physical_alpha_by_u"][_u_key(u)]
        dose_dir = root / "doses" / f"u{u:g}_seed{seed}"
        checkpoint = dose_dir / "checkpoint"
        scalar_path = dose_dir / "scalar.json"
        sidecar_path = dose_dir / "decay_dose.json"
        receipt_path = dose_dir / "deletion_receipt.json"
        marker = stage_marker(root, u, seed)
        def action():
            dose_dir.mkdir(parents=True, exist_ok=True)
            def apply_action():
                run_command(
                    [
                        python,
                        "scripts/apply_decay_noise.py",
                        "--model",
                        parent_path,
                        "--alpha",
                        str(alpha),
                        "--beta",
                        str(config["beta"]),
                        "--seed",
                        str(seed),
                        "--output-dir",
                        checkpoint,
                        "--source-identity-json",
                        identity_path,
                    ],
                    log,
                    repo,
                )

            def evaluate_action():
                run_command(
                    [
                        python,
                        "scripts/eval_decay_scalar.py",
                        checkpoint,
                        scalar_path,
                        "--batch-size",
                        "8",
                        "--max-new-tokens",
                        "256",
                        "--seed",
                        "0",
                        "--judge-model",
                        parent_path,
                        "--tokenizer-model",
                        parent_path,
                        "--baseline-json",
                        baseline_path,
                        "--anchor-json",
                        normalisation_anchor_path,
                        "--ladder-json",
                        ladder_path,
                        "--normalisation-policy",
                        V2_POLICY,
                    ],
                    log,
                    repo,
                )

            run_resumable_dose_action(
                checkpoint,
                scalar_path,
                sidecar_path,
                apply_action,
                evaluate_action,
            )

        ensure_stage(
            root,
            u,
            seed,
            config["fingerprint"],
            (scalar_path, sidecar_path),
            action,
            resumable_unmarked_outputs=(scalar_path,),
        )
        sidecar = read_json(sidecar_path)
        expected_sidecar = {
            "source_model": parent["source_model"],
            "tokenizer_source": parent["source_model"],
            "source_identity_fingerprint": parent["fingerprint"],
            "alpha": alpha,
            "beta": config["beta"],
            "seed": seed,
        }
        if (
            {key: sidecar.get(key) for key in expected_sidecar} != expected_sidecar
            or sidecar.get("source_identity") != parent
        ):
            raise RuntimeError(f"dose provenance mismatch: u={u} seed={seed}")
        payload = validate_finite_scalar_payload(
            read_json(scalar_path), f"u={u} seed={seed}"
        )
        validate_certification_scalar_execution(payload, f"u={u} seed={seed}")
        validate_scalar_artifact(
            scalar_path,
            expected_model=str(checkpoint),
            expected_judge=parent["source_model"],
            expected_tokenizer=parent["source_model"],
            expected_prompt_sha256=prompt_sha256,
            expected_weight_sha256=_exact_hash_map(
                sidecar.get("weight_file_sha256"), "dose weight"
            ),
            expected_model_support_sha256=_exact_hash_map(
                sidecar.get("support_file_sha256"), "dose support"
            ),
            expected_tokenizer_support_sha256=parent["support_file_sha256"],
            expected_judge_support_sha256=parent["support_file_sha256"],
            expected_judge_weight_sha256=parent["weight_file_sha256"],
            expected_policy=V2_POLICY,
            expected_policy_fingerprint=policy_fp,
        )
        normalised, scalar, directions = normalise_components_bidirectional(
            payload["components"], baseline, positive, negative
        )
        scalar = require_scalar(scalar, f"u={u} seed={seed}")
        if (
            abs(float(payload.get("scalar_0_100")) - scalar) > 1e-9
            or not finite_safe_equal(payload.get("normalised_components"), normalised)
            or not finite_safe_equal(payload.get("normalisation_directions"), directions)
        ):
            raise RuntimeError(f"scalar normalisation mismatch: u={u} seed={seed}")
        delete_checkpoint_with_evidence(
            checkpoint,
            root,
            receipt_path,
            scalar_path,
            sidecar_path,
            marker,
            config,
            u,
            seed,
        )
        return {
            "u": u,
            "physical_alpha": alpha,
            "seed": seed,
            "scalar": scalar,
            "components": payload["components"],
            "normalised_components": normalised,
            "normalisation_directions": directions,
            "scalar_json": str(scalar_path),
            "scalar_sha256": sha256_of_file(scalar_path),
            "dose_sidecar": str(sidecar_path),
            "dose_sidecar_sha256": sha256_of_file(sidecar_path),
            "deletion_receipt": str(receipt_path),
            "deletion_receipt_sha256": sha256_of_file(receipt_path),
            "checkpoint_deleted": not checkpoint.exists(),
        }

    curve = {}
    for u in INTERIOR_U:
        records = [run_dose(u, seed) for seed in CERTIFICATION_SEEDS]
        scalars = [row["scalar"] for row in records]
        raw_components = {
            key: sum(row["components"][key] for row in records) / 3.0
            for key in WEIGHTS
        }
        normalised_components = {
            key: sum(row["normalised_components"][key] for row in records) / 3.0
            for key in WEIGHTS
        }
        direction_counts = {
            key: {
                direction: sum(
                    row["normalisation_directions"][key] == direction
                    for row in records
                )
                for direction in sorted(
                    {row["normalisation_directions"][key] for row in records}
                )
            }
            for key in WEIGHTS
        }
        curve[_u_key(u)] = {
            "u": u,
            "physical_alpha": config["physical_alpha_by_u"][_u_key(u)],
            "support": False,
            "per_seed": records,
            "mean": sum(scalars) / 3.0,
            "raw_range": max(scalars) - min(scalars),
            "raw_component_means": raw_components,
            "normalised_component_means": normalised_components,
            "normalisation_direction_counts": direction_counts,
        }
    points = [endpoint_records["u0"], *curve.values(), endpoint_records["u1"]]
    gates = analyse_certification(points, read_ladder_gate(ladder_path))
    summary_path = root / SUMMARY_NAME
    summary = {
        "certification_version": CERTIFICATION_VERSION,
        "certification_scope": "clean_parent_primary_only",
        "parent_model": parent["source_model"],
        "beta": config["beta"],
        "normalisation_version": V2_POLICY,
        "normalisation_policy_fingerprint": policy_fp,
        "clean_ruler": clean_ruler,
        "primary_archive": {
            "root": str(root),
            "run_config": str(config_path),
            "summary": str(summary_path),
            "manifest": str(root / MANIFEST_NAME),
        },
        "pilot_archive": pilot["archive"],
        "controller_mapping": mapping_descriptor,
        "controller_coordinate": "u",
        "controller_u": list(CONTROLLER_U),
        "physical_alpha_by_u": config["physical_alpha_by_u"],
        "baseline_scalar": baseline_scalar,
        "terminal_weight_noise_scalar": terminal_scalar,
        "endpoints": endpoint_records,
        "curve": curve,
        "gates": gates,
    }
    write_json(summary_path, summary)
    write_json(
        root / COMPLETE_NAME,
        {
            "status": "complete",
            "outcome": gates["primary_verdict"],
            "summary_sha256": sha256_of_file(summary_path),
            "config_fingerprint": config["fingerprint"],
        },
    )
    validate_canonical_archive_members(root)
    write_primary_manifest(root)
    validate_sealed_primary(root)
    print(f"PROBE 2 PRIMARY VERDICT: {gates['primary_verdict']}")
    print(f"PROBE 2 OVERALL VERDICT: {gates['probe2_verdict']}")


if __name__ == "__main__":
    main()
