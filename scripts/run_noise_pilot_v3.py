"""Probe 2 v3 diagnostic pilot for a controllable 0--100 decay dial.

This is not a certification run and can never emit PASS.  It first measures
the unchanged beta=1 weight-noise family on a dense low-alpha grid.  Only if
that arm fails the frozen promotion screen does it try beta=.1 on a wider
grid.  The v2 ruler, scalar weights, prompts, judge, tokenizer and ladder are
all reused byte-for-byte from the sealed failed v2 primary archive.
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
    spearman,
    support_file_hashes,
    validate_ladder_artifact,
    validate_scalar_artifact,
)
from finalize_probe2_impossible import (
    CERTIFICATE_NAME as V2_CERTIFICATE_NAME,
    SUMMARY_NAME as V2_SUMMARY_NAME,
    validate_sealed_failure,
)


PILOT_VERSION = "probe2_weight_noise_dial_pilot_v3"
PILOT_SEED = 11
ARM_A_BETA = 1.0
ARM_A_ALPHAS = (
    0.0025, 0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.055, 0.06,
    0.065, 0.07, 0.075, 0.08, 0.085, 0.09, 0.095, 0.1, 0.12,
)
ARM_B_BETA = 0.1
ARM_B_ALPHAS = (
    0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40,
    0.45, 0.50, 0.55, 0.60, 0.70, 0.85, 1.0,
)
TARGET_BRACKETS = (10.0, 28.0, 45.0, 65.0, 90.0)
PUBLIC_CONTROLLER_U = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0)
HEAVY_PARENT_U = 0.65
MAPPING_SCHEMA = {
    "version": "probe2_v3_controller_mapping_v1",
    "coordinate": "u",
    "target_scalar": "100*u",
    "fit_ordinates": "raw_seed11_scalars_after_running_max",
    "interpolator": "run_noise_sweep.monotone_fritsch_carlson_pchip",
    "inverse": "leftmost_generalized_inverse_80_bisections",
    "physical_alpha_decimal_places": 8,
    "raw_point_provenance": (
        "reference artifact path+sha256, or seed11 scalar and dose-sidecar path+sha256"
    ),
    "fixed_endpoints": {"g(0)": 0.0, "g(1)": 1.0},
    "certification_u": list(PUBLIC_CONTROLLER_U),
    "heavy_parent_u": HEAVY_PARENT_U,
}
EXPECTED_V2_MEANS = {0.05: 9.6020107277, 0.1: 95.1455064481}
OUTCOMES = {
    "PROMOTE_ARM_A",
    "PROMOTE_ARM_B",
    "FAIL_WEIGHT_NOISE",
    "INCOMPLETE",
}
EXECUTED_SOURCE_PATHS = (
    "scripts/run_noise_pilot_v3.py",
    "scripts/apply_decay_noise.py",
    "scripts/eval_decay_scalar.py",
    "scripts/decay_scalar_normalization.py",
    "scripts/run_noise_sweep.py",
    "scripts/finalize_probe2_impossible.py",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-model", required=True)
    parser.add_argument("--v2-summary", required=True)
    parser.add_argument("--baseline-json", required=True)
    parser.add_argument("--anchor-json", required=True)
    parser.add_argument("--ladder-json", required=True)
    parser.add_argument("--root", default="derisk/probe2_noise_v3_pilot")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=256)
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


MAPPING_SCHEMA_SHA256 = fingerprint(MAPPING_SCHEMA)


def expected_pilot_rules():
    return {
        "scalar_basis": "raw_seed11_scalar_before_isotonic_fit",
        "adjacent_decrease_max": 3.0,
        "smallest_scheduled_alpha_scalar_max_inclusive": 5.0,
        "target_brackets": list(TARGET_BRACKETS),
        "target_bracket_policy": (
            "raw adjacent alpha points with left<=target<=right inclusive; "
            "decreasing pairs do not count"
        ),
        "terminal_scalar_min": 97.0,
        "local_jump_max": 20.0,
        "arm_a_local_width": 0.005,
        "arm_b_local_width": 0.05,
        "pilot_loo_max": 6.0,
        "spearman_min": 0.95,
        "spearman_points": "raw scheduled points with 0<alpha<1; endpoints excluded",
        "loo_policy": (
            "hold_raw_interior_y; fit_running_max_of_remaining_raw_y; "
            "baseline_and_alpha1_are_support_points_never_held"
        ),
        "historical_endpoint_seed_exceptions": {
            "alpha0": None,
            "arm_a_beta1_alpha1": 0,
            "arm_b_beta0.1_alpha1": PILOT_SEED,
        },
    }


def validate_pilot_scalar_execution(payload, label="pilot scalar"):
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
        raise RuntimeError(f"{label} violates the frozen execution policy")
    return payload


def committed_source_identity(repo, relative_paths, expected_commit=None):
    repo = Path(repo).resolve()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise RuntimeError("pilot cannot bind to a valid Git HEAD")
    if expected_commit is not None and commit != expected_commit:
        raise RuntimeError("pilot Git HEAD changed")
    hashes = {}
    for relative in relative_paths:
        try:
            committed = subprocess.run(
                ["git", "show", f"{commit}:{relative}"],
                cwd=repo,
                check=True,
                capture_output=True,
            ).stdout
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"pilot source is not committed at HEAD: {relative}") from error
        committed_oid = subprocess.check_output(
            ["git", "rev-parse", f"{commit}:{relative}"], cwd=repo, text=True
        ).strip()
        current_oid = subprocess.check_output(
            ["git", "hash-object", "--path", relative, relative],
            cwd=repo,
            text=True,
        ).strip()
        if current_oid != committed_oid:
            raise RuntimeError(f"pilot source differs from its HEAD blob: {relative}")
        hashes[relative] = hashlib.sha256(committed).hexdigest()
    return {"commit": commit, "sha256": hashes}


def validate_recorded_source_identity(repo, commit, hashes):
    if (
        re.fullmatch(r"[0-9a-f]{40}", str(commit)) is None
        or set(hashes or {}) != set(EXECUTED_SOURCE_PATHS)
    ):
        raise RuntimeError("sealed pilot has malformed committed-source identity")
    for relative in EXECUTED_SOURCE_PATHS:
        try:
            blob = subprocess.run(
                ["git", "show", f"{commit}:{relative}"],
                cwd=repo,
                check=True,
                capture_output=True,
            ).stdout
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"sealed pilot source commit lacks {relative}") from error
        if hashlib.sha256(blob).hexdigest() != hashes[relative]:
            raise RuntimeError(f"sealed pilot source hash changed: {relative}")


def model_identity(path):
    path = Path(path).expanduser().resolve()
    identity = {
        "source_model": str(path),
        "weight_file_sha256": model_weight_hashes(path),
        "support_file_sha256": support_file_hashes(path),
    }
    identity["fingerprint"] = fingerprint(identity)
    return identity


def paths_overlap(left, right):
    left, right = Path(left).resolve(), Path(right).resolve()
    return left == right or left in right.parents or right in left.parents


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


def validate_config(args):
    actual = {"batch_size": args.batch_size, "max_new_tokens": args.max_new_tokens}
    expected = {"batch_size": 8, "max_new_tokens": 256}
    if actual != expected:
        raise ValueError(f"v3 pilot configuration is frozen: {expected}; got {actual}")


def exact_hash_map(payload, label):
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


def require_scalar(value, label):
    try:
        scalar = float(value)
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"{label} is not a numeric scalar") from error
    if not math.isfinite(scalar) or not 0.0 <= scalar <= 100.0:
        raise RuntimeError(f"{label} is outside the finite 0--100 scalar range")
    return scalar


def validate_failed_v2_summary(summary, certificate, policy_fp):
    gates = summary.get("gates", {})
    proof = certificate.get("loo_impossibility_proof", {})
    if (
        summary.get("certification_scope") != "clean_parent_primary_only"
        or summary.get("normalisation_version") != V2_POLICY
        or summary.get("normalisation_policy_fingerprint") != policy_fp
        or gates.get("failure_stage") != "noise_calibration"
        or gates.get("sweep_completed") is not False
        or gates.get("primary_verdict") != "FAIL"
        or gates.get("probe2_verdict") != "FAIL"
        or gates.get("loo_gate_pass") is not False
        or gates.get("loo_gate_mathematically_impossible") is not True
        or gates.get("ladder_gate_pass") is not True
        or certificate.get("certificate_version")
        != "probe2_v2_loo_impossibility_v1"
        or certificate.get("conclusion") != "PROBE2_PRIMARY_FAIL"
        or certificate.get("never_pass_capable") is not True
        or certificate.get("normalisation_version") != V2_POLICY
        or certificate.get("normalisation_policy_fingerprint") != policy_fp
        or proof.get("gate_mathematically_impossible") is not True
        or require_scalar(proof.get("loo_error_limit"), "v2 LOO error limit") != 3.0
    ):
        raise RuntimeError(
            "sealed v2 summary/certificate is not the expected failed-LOO primary"
        )
    partial_curve = summary.get("partial_curve", {})
    if set(partial_curve) != {str(alpha) for alpha in EXPECTED_V2_MEANS}:
        raise RuntimeError("sealed v2 partial curve has the wrong dose grid")
    for alpha, expected in EXPECTED_V2_MEANS.items():
        try:
            actual = require_scalar(
                partial_curve[str(alpha)]["mean"], f"v2 alpha={alpha} mean"
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(f"v2 observed mean is missing at alpha={alpha}") from error
        if abs(actual - expected) > 1e-9:
            raise RuntimeError(f"v2 observed mean changed at alpha={alpha}")
    if (
        abs(
            require_scalar(proof.get("observed_alpha0.05_mean"), "v2 proof alpha=.05")
            - EXPECTED_V2_MEANS[0.05]
        )
        > 1e-9
        or abs(
            require_scalar(proof.get("observed_alpha0.1_mean"), "v2 proof alpha=.1")
            - EXPECTED_V2_MEANS[0.1]
        )
        > 1e-9
        or abs(
            require_scalar(
                gates.get("loo_impossibility_error_lower_bound"),
                "v2 summary LOO lower bound",
            )
            - require_scalar(
                proof.get("minimum_possible_absolute_error"),
                "v2 proof LOO lower bound",
            )
        )
        > 1e-9
    ):
        raise RuntimeError("sealed v2 PCHIP failure proof changed")


def validate_v2_inputs(args, parent, baseline, positive, negative, sources):
    summary_path = Path(args.v2_summary).resolve()
    v2_root = summary_path.parent
    if summary_path.name != V2_SUMMARY_NAME:
        raise RuntimeError("pilot requires the canonical finalized v2 summary")
    seal = validate_sealed_failure(v2_root)
    expected_paths = {
        "baseline": v2_root / "baseline" / "scalar.json",
        "anchor": v2_root / "anchor" / "scalar.json",
        "ladder": v2_root / "ladder" / "corruption_ladder.json",
    }
    supplied = {
        "baseline": Path(args.baseline_json).resolve(),
        "anchor": Path(args.anchor_json).resolve(),
        "ladder": Path(args.ladder_json).resolve(),
    }
    if supplied != {key: value.resolve() for key, value in expected_paths.items()}:
        raise RuntimeError("pilot ruler paths are not the canonical sealed v2 members")
    summary = read_json(summary_path)
    certificate_path = v2_root / V2_CERTIFICATE_NAME
    certificate = read_json(certificate_path)
    if (
        Path(summary.get("failure_certificate", "")).resolve()
        != certificate_path.resolve()
        or summary.get("failure_certificate_sha256")
        != sha256_of_file(certificate_path)
    ):
        raise RuntimeError("v2 summary is not bound to its sealed failure certificate")
    policy_fp = bidirectional_policy_fingerprint(baseline, positive, negative, sources)
    validate_failed_v2_summary(summary, certificate, policy_fp)
    identity_path = v2_root / "parent_identity.json"
    recorded_parent = read_json(identity_path)
    if recorded_parent != parent:
        raise RuntimeError("pilot parent differs from the sealed v2 clean parent")
    prompt_paths = {
        "battery": Path("data/decay_scalar_prompts.json"),
        "capability": Path("data/rehearsal_capability_prompts.json"),
        "survival": Path("data/conversational_survival_generations.json"),
    }
    prompt_hashes = {
        key: sha256_of_file(path) for key, path in prompt_paths.items()
    }
    validate_scalar_artifact(
        supplied["baseline"],
        expected_model=parent["source_model"],
        expected_judge=parent["source_model"],
        expected_tokenizer=parent["source_model"],
        expected_prompt_sha256=prompt_hashes,
        expected_weight_sha256=parent["weight_file_sha256"],
        expected_model_support_sha256=parent["support_file_sha256"],
        expected_tokenizer_support_sha256=parent["support_file_sha256"],
        expected_judge_support_sha256=parent["support_file_sha256"],
        expected_judge_weight_sha256=parent["weight_file_sha256"],
        expected_policy=None,
        expected_policy_fingerprint=None,
    )
    anchor_sidecar_path = v2_root / "anchor" / "decay_dose.json"
    anchor_sidecar = read_json(anchor_sidecar_path)
    validate_scalar_artifact(
        supplied["anchor"],
        expected_model=str(v2_root / "anchor" / "checkpoint"),
        expected_judge=parent["source_model"],
        expected_tokenizer=parent["source_model"],
        expected_prompt_sha256=prompt_hashes,
        expected_weight_sha256=exact_hash_map(
            anchor_sidecar.get("weight_file_sha256"), "anchor weight"
        ),
        expected_model_support_sha256=exact_hash_map(
            anchor_sidecar.get("support_file_sha256"), "anchor support"
        ),
        expected_tokenizer_support_sha256=parent["support_file_sha256"],
        expected_judge_support_sha256=parent["support_file_sha256"],
        expected_judge_weight_sha256=parent["weight_file_sha256"],
        expected_policy=None,
        expected_policy_fingerprint=None,
    )
    anchor_expected = {
        "alpha": 1.0,
        "beta": 1.0,
        "seed": 0,
        "source_model": parent["source_model"],
        "source_identity_fingerprint": parent["fingerprint"],
    }
    if {key: anchor_sidecar.get(key) for key in anchor_expected} != anchor_expected:
        raise RuntimeError("v2 alpha=1 reference endpoint semantics changed")
    validate_ladder_artifact(
        supplied["ladder"],
        supplied["baseline"],
        parent["source_model"],
        parent["support_file_sha256"],
        parent["weight_file_sha256"],
    )
    baseline_norm, baseline_scalar, _ = normalise_components_bidirectional(
        read_json(supplied["baseline"])["components"], baseline, positive, negative
    )
    terminal_norm, terminal_scalar, _ = normalise_components_bidirectional(
        read_json(supplied["anchor"])["components"], baseline, positive, negative
    )
    baseline_scalar = require_scalar(baseline_scalar, "sealed v2 baseline scalar")
    terminal_scalar = require_scalar(terminal_scalar, "sealed v2 terminal scalar")
    if abs(float(summary["baseline_scalar"]) - baseline_scalar) > 1e-9:
        raise RuntimeError("v2 baseline scalar/reference mismatch")
    if abs(float(summary["terminal_weight_noise_scalar"]) - terminal_scalar) > 1e-9:
        raise RuntimeError("v2 alpha=1 scalar/reference mismatch")
    return {
        "root": str(v2_root),
        "seal": {key: value for key, value in seal.items() if key != "entries"},
        "summary_sha256": sha256_of_file(summary_path),
        "failure_certificate_sha256": sha256_of_file(certificate_path),
        "parent_identity_sha256": sha256_of_file(identity_path),
        "anchor_sidecar_sha256": sha256_of_file(anchor_sidecar_path),
        "policy_fingerprint": policy_fp,
        "prompt_sha256": prompt_hashes,
        "baseline_scalar": baseline_scalar,
        "terminal_scalar": terminal_scalar,
        "baseline_normalised_components": baseline_norm,
        "terminal_normalised_components": terminal_norm,
    }


def stage_marker(root, name):
    return Path(root) / "stages" / f"{name}.json"


def ensure_stage(root, name, config_fp, inputs, outputs, action):
    marker = stage_marker(root, name)
    stage_fp = fingerprint(
        {"version": PILOT_VERSION, "stage": name, "config": config_fp, "inputs": inputs}
    )
    outputs = [Path(path) for path in outputs]
    if marker.exists():
        payload = read_json(marker)
        actual = {str(path): sha256_of_file(path) for path in outputs if path.is_file()}
        if (
            payload.get("status") != "complete"
            or payload.get("fingerprint") != stage_fp
            or actual != payload.get("outputs")
            or len(actual) != len(outputs)
        ):
            raise RuntimeError(f"pilot stage provenance mismatch: {name}")
        return
    if all(path.is_file() for path in outputs):
        # Recover the narrow crash window after both immutable outputs were
        # written but before their atomic completion marker. The caller still
        # performs the full semantic/provenance validation before use.
        write_json(
            marker,
            {
                "status": "complete",
                "fingerprint": stage_fp,
                "inputs": inputs,
                "outputs": {str(path): sha256_of_file(path) for path in outputs},
            },
        )
        return
    if any(path.exists() for path in outputs):
        raise RuntimeError(f"pilot stage has unmarked outputs: {name}")
    action()
    if not all(path.is_file() for path in outputs):
        raise RuntimeError(f"pilot stage did not finish: {name}")
    write_json(
        marker,
        {
            "status": "complete",
            "fingerprint": stage_fp,
            "inputs": inputs,
            "outputs": {str(path): sha256_of_file(path) for path in outputs},
        },
    )


def safe_remove_checkpoint(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if root not in path.parents or path.name != "checkpoint":
        raise RuntimeError(f"unsafe checkpoint cleanup target: {path}")
    if path.exists():
        shutil.rmtree(path)


def remove_checkpoint_after_validation(path, root, validation_complete):
    if validation_complete is not True:
        raise RuntimeError("refusing checkpoint cleanup before semantic validation")
    safe_remove_checkpoint(path, root)


def leftmost_inverse(xs, ys, target):
    """Invert the frozen monotone PCHIP with a deterministic 80-step search."""
    if target <= ys[0]:
        return round(float(xs[0]), 8)
    if target > ys[-1]:
        return None
    low, high = float(xs[0]), float(xs[-1])
    for _ in range(80):
        mid = (low + high) / 2.0
        if pchip_eval(xs, ys, mid) >= target:
            high = mid
        else:
            low = mid
    return round(high, 8)


def require_artifact_pointer(path, digest, label):
    if not isinstance(path, str) or not path or not isinstance(digest, str):
        raise RuntimeError(f"controller mapping lacks {label} provenance")
    try:
        if len(digest) != 64:
            raise ValueError
        try:
            int(digest, 16)
        except ValueError as error:
            raise RuntimeError(f"malformed pilot manifest digest: {digest!r}") from error
    except ValueError as error:
        raise RuntimeError(f"controller mapping has malformed {label} hash") from error
    return {"path": path, "sha256": digest.lower()}


def build_controller_mapping(points, arm):
    """Freeze physical alpha=g(u) from this arm's seed-11 pilot only."""
    ordered = sorted(points, key=lambda record: float(record["alpha"]))
    xs = [float(record["alpha"]) for record in ordered]
    raw = [
        require_scalar(record.get("scalar"), f"Arm {arm} alpha={record.get('alpha')}")
        for record in ordered
    ]
    if len(xs) < 2 or xs[0] != 0.0 or xs[-1] != 1.0:
        return None, "controller_mapping_missing_endpoints"
    if any(right <= left for left, right in zip(xs, xs[1:])):
        return None, "controller_mapping_duplicate_alpha"
    fitted = isotonic_running_max(raw)
    entries = []
    for u in PUBLIC_CONTROLLER_U:
        if u == 0.0:
            alpha = 0.0
        elif u == 1.0:
            alpha = 1.0
        else:
            alpha = leftmost_inverse(xs, fitted, 100.0 * u)
        if alpha is None:
            return None, "controller_mapping_target_unreachable"
        entries.append(
            {
                "u": u,
                "target_scalar": 100.0 * u,
                "physical_alpha": alpha,
            }
        )
    heavy_alpha = leftmost_inverse(xs, fitted, 100.0 * HEAVY_PARENT_U)
    if heavy_alpha is None:
        return None, "controller_mapping_heavy_target_unreachable"
    interior = [
        record["physical_alpha"] for record in entries if 0.0 < record["u"] < 1.0
    ]
    if (
        len(interior) != 8
        or len(set(interior)) != len(interior)
        or any(not 0.0 < alpha < 1.0 for alpha in interior)
    ):
        return None, "controller_mapping_interior_not_distinct"
    raw_points = []
    for record, alpha, scalar in zip(ordered, xs, raw):
        raw_record = {
            "physical_alpha": alpha,
            "raw_scalar": scalar,
            "seed": record.get("seed"),
            "scheduled": record.get("scheduled") is True,
            "historical_seed_exception": record.get("historical_seed_exception")
            is True,
        }
        if record.get("scheduled") is True:
            raw_record["scalar_artifact"] = require_artifact_pointer(
                record.get("scalar_json"), record.get("scalar_sha256"), "scalar"
            )
            raw_record["dose_sidecar"] = require_artifact_pointer(
                record.get("dose_sidecar"),
                record.get("dose_sidecar_sha256"),
                "dose sidecar",
            )
        else:
            raw_record["reference_artifact"] = require_artifact_pointer(
                record.get("reference_artifact"),
                record.get("reference_artifact_sha256"),
                "reference artifact",
            )
            raw_record["reference"] = record.get("reference")
        raw_points.append(raw_record)
    mapping = {
        "schema": MAPPING_SCHEMA,
        "schema_sha256": MAPPING_SCHEMA_SHA256,
        "source_arm": arm,
        "beta": ARM_A_BETA if arm == "A" else ARM_B_BETA,
        "seed_used_to_fit": PILOT_SEED,
        "raw_points": raw_points,
        "fit_points": [
            {"physical_alpha": alpha, "isotonic_scalar": scalar}
            for alpha, scalar in zip(xs, fitted)
        ],
        "controller": entries,
        "heavy_parent": {
            "u": HEAVY_PARENT_U,
            "target_scalar": 100.0 * HEAVY_PARENT_U,
            "physical_alpha": heavy_alpha,
        },
    }
    mapping["fingerprint"] = fingerprint(mapping)
    return mapping, None


def loo_errors(points):
    xs = [float(record["alpha"]) for record in points]
    ys = [float(record["scalar"]) for record in points]
    errors = {}
    for index in range(1, len(points) - 1):
        rest_x = xs[:index] + xs[index + 1 :]
        rest_y = isotonic_running_max(ys[:index] + ys[index + 1 :])
        predicted = pchip_eval(rest_x, rest_y, xs[index])
        errors[str(xs[index])] = abs(predicted - ys[index])
    return errors


def raw_adjacent_brackets(points, target):
    ordered = sorted(points, key=lambda record: record["alpha"])
    return any(
        float(left["scalar"]) <= target <= float(right["scalar"])
        for left, right in zip(ordered, ordered[1:])
    )


def analyse_arm(points, arm, early_reasons=()):
    """Apply the frozen promotion screen to one seed-11 arm."""
    reasons = list(early_reasons)
    points = sorted(points, key=lambda record: record["alpha"])
    expected_alphas = (
        (0.0, *ARM_A_ALPHAS, 1.0)
        if arm == "A"
        else (0.0, *ARM_B_ALPHAS)
    )
    complete = tuple(float(record["alpha"]) for record in points) == expected_alphas
    if not complete:
        reasons.append("incomplete_grid")
    scalars = [
        require_scalar(record.get("scalar"), f"Arm {arm} alpha={record.get('alpha')}")
        for record in points
    ]
    alphas = [float(record["alpha"]) for record in points]
    deltas = [right - left for left, right in zip(scalars, scalars[1:])]
    if any(delta < -3.0 for delta in deltas):
        reasons.append("adjacent_decrease_gt_3")
    scheduled = sorted(
        (record for record in points if record.get("scheduled") is True),
        key=lambda record: record["alpha"],
    )
    first_scheduled = scheduled[0] if scheduled else None
    if first_scheduled is None or float(first_scheduled["scalar"]) > 5.0:
        reasons.append("low_end_not_resolved")
    missing_targets = [
        target
        for target in TARGET_BRACKETS
        if not raw_adjacent_brackets(points, target)
    ]
    if missing_targets:
        reasons.append("missing_target_brackets")
    endpoint = next((record for record in points if record["alpha"] == 1.0), None)
    if endpoint is None or float(endpoint["scalar"]) < 97.0:
        reasons.append("terminal_below_97")
    width_limit = 0.005 if arm == "A" else 0.05
    for left, right in zip(points, points[1:]):
        if (
            right["alpha"] - left["alpha"] <= width_limit + 1e-12
            and min(left["scalar"], right["scalar"]) < 95.0
            and max(left["scalar"], right["scalar"]) > 5.0
            and right["scalar"] - left["scalar"] > 20.0
        ):
            reasons.append("unresolved_local_jump_gt_20")
            break
    spearman_points = [
        record
        for record in points
        if record.get("scheduled") is True and 0.0 < float(record["alpha"]) < 1.0
    ]
    spearman_alphas = [float(record["alpha"]) for record in spearman_points]
    spearman_scalars = [float(record["scalar"]) for record in spearman_points]
    rho = (
        spearman(spearman_alphas, spearman_scalars)
        if len(spearman_points) >= 2
        else None
    )
    if rho is None or rho < 0.95:
        reasons.append("spearman_below_0_95")
    errors = loo_errors(points) if len(points) >= 3 else {}
    max_loo = max(errors.values()) if errors else None
    if max_loo is None or max_loo > 6.0:
        reasons.append("pilot_loo_above_6")
    mapping = None
    if complete:
        mapping, mapping_error = build_controller_mapping(points, arm)
        if mapping_error:
            reasons.append(mapping_error)
    reasons = sorted(set(reasons))
    promotion = not reasons
    if not promotion:
        mapping = None
    return {
        "arm": arm,
        "seed": PILOT_SEED,
        "complete_grid": complete,
        "points": points,
        "spearman": rho,
        "spearman_points": [
            {"alpha": record["alpha"], "raw_scalar": record["scalar"]}
            for record in spearman_points
        ],
        "loo_errors": errors,
        "max_loo_error": max_loo,
        "controller_mapping": mapping,
        "promotion_screen_pass": promotion,
        "failure_reasons": reasons,
        "screen_is_not_certification": True,
    }


def should_fail_early(points, arm):
    if len(points) < 2:
        return None
    for record in points:
        require_scalar(
            record.get("scalar"), f"Arm {arm} alpha={record.get('alpha')} early screen"
        )
    width_limit = 0.005 if arm == "A" else 0.05
    expected_first = ARM_A_ALPHAS[0] if arm == "A" else ARM_B_ALPHAS[0]
    first_scheduled = next(
        (
            record
            for record in points
            if record.get("scheduled") is True
            and abs(float(record["alpha"]) - expected_first) <= 1e-12
        ),
        None,
    )
    if first_scheduled is not None and float(first_scheduled["scalar"]) > 5.0:
        return "low_end_not_resolved"
    for left, right in zip(points, points[1:]):
        delta = right["scalar"] - left["scalar"]
        if delta < -3.0:
            return "adjacent_decrease_gt_3"
        if (
            right["alpha"] - left["alpha"] <= width_limit + 1e-12
            and min(left["scalar"], right["scalar"]) < 95.0
            and max(left["scalar"], right["scalar"]) > 5.0
            and delta > 20.0
        ):
            return "unresolved_local_jump_gt_20"
    return None


def outcome_for_arms(arm_a, arm_b=None):
    if arm_a.get("promotion_screen_pass") is True:
        if arm_b is not None:
            raise RuntimeError("Arm B must be suppressed after Arm A promotion")
        return "PROMOTE_ARM_A"
    if arm_b is None:
        return None
    return (
        "PROMOTE_ARM_B"
        if arm_b.get("promotion_screen_pass") is True
        else "FAIL_WEIGHT_NOISE"
    )


def recompute_summary_arms(summary):
    arm_a = summary.get("arm_a")
    if not isinstance(arm_a, dict):
        raise RuntimeError("pilot has no Arm A analysis")
    recomputed_a = analyse_arm(arm_a.get("points", []), "A")
    if recomputed_a != arm_a:
        raise RuntimeError("stored Arm A analysis is not reproducible")
    arm_b = summary.get("arm_b")
    recomputed_b = None
    if arm_b is not None:
        if not isinstance(arm_b, dict):
            raise RuntimeError("stored Arm B analysis is malformed")
        recomputed_b = analyse_arm(arm_b.get("points", []), "B")
        if recomputed_b != arm_b:
            raise RuntimeError("stored Arm B analysis is not reproducible")
    outcome = outcome_for_arms(recomputed_a, recomputed_b)
    if summary.get("outcome") != outcome:
        raise RuntimeError("stored pilot outcome is not reproducible")
    return recomputed_a, recomputed_b, outcome


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
            f"{sha256_of_file(path)}  {path.relative_to(root).as_posix()}" for path in files
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(output)
    verify_pilot_manifest(root)


def verify_pilot_manifest(root):
    root = Path(root).resolve()
    manifest = root / "MANIFEST.sha256"
    if not manifest.is_file():
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
            raise RuntimeError(f"malformed pilot manifest line: {line!r}")
        int(digest, 16)
        key = relative_path.as_posix()
        if key in expected:
            raise RuntimeError(f"duplicate pilot manifest member: {key}")
        expected[key] = digest.lower()
    actual = {
        path.relative_to(root).as_posix(): sha256_of_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != manifest
    }
    if actual != expected:
        raise RuntimeError("sealed v3 pilot archive changed")
    return True


def validate_sealed_arm_artifacts(
    root, config, arm_summary, arm, baseline, positive, negative
):
    parent = config["parent_identity"]
    parent_path = parent["source_model"]
    beta = ARM_A_BETA if arm == "A" else ARM_B_BETA
    for record in arm_summary.get("points", []):
        alpha = float(record["alpha"])
        if record.get("scheduled") is not True:
            expected_path = Path(config["v2"]["root"]) / (
                "baseline/scalar.json" if alpha == 0.0 else "anchor/scalar.json"
            )
            expected_scalar = (
                config["v2"]["baseline_scalar"]
                if alpha == 0.0
                else config["v2"]["terminal_scalar"]
            )
            expected_seed = None if alpha == 0.0 else 0
            if (
                arm == "B" and alpha != 0.0
                or alpha not in {0.0, 1.0}
                or record.get("seed") != expected_seed
                or record.get("historical_seed_exception") is not True
                or Path(record.get("reference_artifact", "")).resolve()
                != expected_path.resolve()
                or record.get("reference_artifact_sha256")
                != sha256_of_file(expected_path)
                or abs(require_scalar(record.get("scalar"), "reference scalar") - expected_scalar)
                > 1e-9
            ):
                raise RuntimeError(f"sealed Arm {arm} reference point changed")
            continue
        dose_dir = root / f"arm_{arm.lower()}" / f"alpha{alpha:g}"
        scalar_path = dose_dir / "scalar.json"
        sidecar_path = dose_dir / "decay_dose.json"
        if (
            Path(record.get("scalar_json", "")).resolve() != scalar_path.resolve()
            or record.get("scalar_sha256") != sha256_of_file(scalar_path)
            or Path(record.get("dose_sidecar", "")).resolve() != sidecar_path.resolve()
            or record.get("dose_sidecar_sha256") != sha256_of_file(sidecar_path)
            or record.get("seed") != PILOT_SEED
            or float(record.get("beta")) != beta
            or record.get("historical_seed_exception") is not False
            or record.get("checkpoint_deleted") is not True
        ):
            raise RuntimeError(f"sealed Arm {arm} dose pointer changed at alpha={alpha}")
        sidecar = read_json(sidecar_path)
        expected_sidecar = {
            "source_model": parent_path,
            "tokenizer_source": parent_path,
            "source_identity_fingerprint": parent["fingerprint"],
            "alpha": alpha,
            "beta": beta,
            "seed": PILOT_SEED,
        }
        if (
            {key: sidecar.get(key) for key in expected_sidecar} != expected_sidecar
            or sidecar.get("source_identity") != parent
        ):
            raise RuntimeError(f"sealed Arm {arm} sidecar changed at alpha={alpha}")
        validate_scalar_artifact(
            scalar_path,
            expected_model=str(dose_dir / "checkpoint"),
            expected_judge=parent_path,
            expected_tokenizer=parent_path,
            expected_prompt_sha256=config["v2"]["prompt_sha256"],
            expected_weight_sha256=exact_hash_map(
                sidecar.get("weight_file_sha256"), "sealed dose weight"
            ),
            expected_model_support_sha256=exact_hash_map(
                sidecar.get("support_file_sha256"), "sealed dose support"
            ),
            expected_tokenizer_support_sha256=parent["support_file_sha256"],
            expected_judge_support_sha256=parent["support_file_sha256"],
            expected_judge_weight_sha256=parent["weight_file_sha256"],
            expected_policy=V2_POLICY,
            expected_policy_fingerprint=config["v2"]["policy_fingerprint"],
        )
        payload = read_json(scalar_path)
        validate_pilot_scalar_execution(payload, f"sealed Arm {arm} alpha={alpha}")
        normalised, scalar, directions = normalise_components_bidirectional(
            payload["components"], baseline, positive, negative
        )
        scalar = require_scalar(scalar, f"sealed Arm {arm} alpha={alpha} scalar")
        if (
            abs(require_scalar(record.get("scalar"), "stored arm scalar") - scalar) > 1e-9
            or abs(require_scalar(payload.get("scalar_0_100"), "scalar artifact") - scalar)
            > 1e-9
            or record.get("components") != payload.get("components")
            or record.get("normalised_components") != normalised
            or record.get("normalisation_directions") != directions
        ):
            raise RuntimeError(f"sealed Arm {arm} scalar bundle changed at alpha={alpha}")


def validate_sealed_pilot(root):
    root = Path(root).resolve()
    if not verify_pilot_manifest(root):
        return None
    config_path = root / "run_config.json"
    summary_path = root / "pilot_summary.json"
    complete_path = root / "COMPLETE.json"
    config, summary, complete = map(read_json, (config_path, summary_path, complete_path))
    config_body = {key: value for key, value in config.items() if key != "fingerprint"}
    outcome = summary.get("outcome")
    expected_config_keys = {
        "version", "outcomes", "parent_identity", "v2", "pilot_seed",
        "arm_a", "arm_b", "batch_size", "max_new_tokens", "rules",
        "controller_mapping_schema", "controller_mapping_schema_sha256",
        "input_sha256", "code_sha256", "code_commit", "fingerprint",
    }
    expected_summary_keys = {
        "pilot_version", "certification_scope", "outcome",
        "config_fingerprint", "v2_ruler", "arm_a", "arm_b",
        "controller_mapping", "controller_mapping_sha256",
        "controller_mapping_fingerprint", "controller_mapping_schema_sha256",
        "explicitly_not_a_pass_verdict", "next_step",
    }
    expected_complete_keys = {
        "status", "outcome", "summary_sha256", "config_fingerprint"
    }
    expected_next_step = (
        "freeze_a_separate_v3_certification_before_using_seeds_0_1_2"
        if isinstance(outcome, str) and outcome.startswith("PROMOTE_")
        else "stop_weight_noise_and_precommit_the_fallback_dial"
    )
    if (
        set(config) != expected_config_keys
        or set(summary) != expected_summary_keys
        or set(complete) != expected_complete_keys
        or config.get("version") != PILOT_VERSION
        or config.get("fingerprint") != fingerprint(config_body)
        or config.get("controller_mapping_schema_sha256") != MAPPING_SCHEMA_SHA256
        or config.get("controller_mapping_schema") != MAPPING_SCHEMA
        or config.get("outcomes") != sorted(OUTCOMES)
        or config.get("pilot_seed") != PILOT_SEED
        or config.get("arm_a")
        != {"beta": ARM_A_BETA, "alphas": list(ARM_A_ALPHAS)}
        or config.get("arm_b")
        != {"beta": ARM_B_BETA, "alphas": list(ARM_B_ALPHAS)}
        or config.get("batch_size") != 8
        or config.get("max_new_tokens") != 256
        or config.get("rules") != expected_pilot_rules()
        or summary.get("pilot_version") != PILOT_VERSION
        or summary.get("certification_scope")
        != "diagnostic_only_not_probe2_pass"
        or summary.get("config_fingerprint") != config.get("fingerprint")
        or summary.get("v2_ruler") != config.get("v2")
        or summary.get("next_step") != expected_next_step
        or summary.get("controller_mapping_schema_sha256")
        != MAPPING_SCHEMA_SHA256
        or summary.get("explicitly_not_a_pass_verdict") is not True
        or outcome not in OUTCOMES
        or outcome == "INCOMPLETE"
        or complete.get("status") != "complete"
        or complete.get("outcome") != outcome
        or complete.get("summary_sha256") != sha256_of_file(summary_path)
        or complete.get("config_fingerprint") != config.get("fingerprint")
    ):
        raise RuntimeError("sealed v3 pilot terminal semantics changed")
    validate_recorded_source_identity(
        Path.cwd(), config.get("code_commit"), config.get("code_sha256")
    )
    if any(path.is_dir() and path.name == "checkpoint" for path in root.rglob("*")):
        raise RuntimeError("sealed v3 pilot retained a redrawable checkpoint")
    parent = config.get("parent_identity", {})
    parent_source = parent.get("source_model")
    if (
        not isinstance(parent_source, str)
        or not parent_source
        or not Path(parent_source).is_dir()
        or model_identity(parent_source) != parent
        or read_json(root / "parent_identity.json") != parent
    ):
        raise RuntimeError("sealed v3 pilot clean parent changed")
    v2_root = Path(config["v2"]["root"])
    v2_paths = {
        "summary": v2_root / V2_SUMMARY_NAME,
        "baseline": v2_root / "baseline/scalar.json",
        "anchor": v2_root / "anchor/scalar.json",
        "ladder": v2_root / "ladder/corruption_ladder.json",
    }
    repo = Path.cwd()
    expected_inputs = {
        "v2_summary": v2_paths["summary"],
        "baseline": v2_paths["baseline"],
        "anchor": v2_paths["anchor"],
        "ladder": v2_paths["ladder"],
        "battery": repo / "data/decay_scalar_prompts.json",
        "capability": repo / "data/rehearsal_capability_prompts.json",
        "survival": repo / "data/conversational_survival_generations.json",
    }
    if config.get("input_sha256") != {
        key: sha256_of_file(path) for key, path in expected_inputs.items()
    }:
        raise RuntimeError("sealed v3 pilot input hashes changed")
    baseline, positive, negative, sources = load_bidirectional_anchors(
        v2_paths["baseline"], v2_paths["anchor"], v2_paths["ladder"]
    )
    v2_args = argparse.Namespace(
        v2_summary=str(v2_paths["summary"]),
        baseline_json=str(v2_paths["baseline"]),
        anchor_json=str(v2_paths["anchor"]),
        ladder_json=str(v2_paths["ladder"]),
    )
    if validate_v2_inputs(
        v2_args, parent, baseline, positive, negative, sources
    ) != config["v2"]:
        raise RuntimeError("sealed v3 pilot v2 dependency bundle changed")
    recomputed_a, recomputed_b, recomputed_outcome = recompute_summary_arms(summary)
    arm_a = summary["arm_a"]
    validate_sealed_arm_artifacts(
        root, config, arm_a, "A", baseline, positive, negative
    )
    arm_b = summary.get("arm_b")
    if arm_b is not None:
        validate_sealed_arm_artifacts(
            root, config, arm_b, "B", baseline, positive, negative
        )
    if recomputed_outcome != outcome:
        raise RuntimeError("sealed v3 pilot outcome changed")
    mapping_path = root / "controller_mapping.json"
    if outcome.startswith("PROMOTE_"):
        mapping = read_json(mapping_path)
        expected_mapping = (
            recomputed_a["controller_mapping"]
            if outcome == "PROMOTE_ARM_A"
            else recomputed_b["controller_mapping"]
        )
        mapping_body = {
            key: value for key, value in mapping.items() if key != "fingerprint"
        }
        if (
            summary.get("controller_mapping") != str(mapping_path)
            or summary.get("controller_mapping_sha256") != sha256_of_file(mapping_path)
            or summary.get("controller_mapping_fingerprint")
            != mapping.get("fingerprint")
            or mapping.get("schema_sha256") != MAPPING_SCHEMA_SHA256
            or mapping.get("fingerprint") != fingerprint(mapping_body)
            or mapping != expected_mapping
        ):
            raise RuntimeError("sealed v3 controller mapping changed")
    elif (
        mapping_path.exists()
        or summary.get("controller_mapping") is not None
        or summary.get("controller_mapping_sha256") is not None
        or summary.get("controller_mapping_fingerprint") is not None
    ):
        raise RuntimeError("failed v3 pilot unexpectedly contains a controller mapping")
    return summary


def main():
    args = parse_args()
    validate_config(args)
    repo = Path.cwd().resolve()
    root = Path(args.root).resolve()
    sealed_summary = validate_sealed_pilot(root)
    if sealed_summary is not None:
        summary = sealed_summary
        print(f"Immutable v3 pilot outcome: {summary['outcome']}")
        return
    source_identity = committed_source_identity(repo, EXECUTED_SOURCE_PATHS)
    parent_path = Path(args.parent_model).expanduser().resolve()
    if not parent_path.is_dir():
        raise ValueError("pilot parent must be an exact local model directory")
    parent = model_identity(parent_path)
    args.parent_model = parent["source_model"]
    baseline, positive, negative, sources = load_bidirectional_anchors(
        args.baseline_json, args.anchor_json, args.ladder_json
    )
    v2 = validate_v2_inputs(args, parent, baseline, positive, negative, sources)
    if any(paths_overlap(root, protected) for protected in (parent_path, v2["root"])):
        raise ValueError("v3 pilot root must not overlap its sealed inputs")
    input_paths = {
        "v2_summary": Path(args.v2_summary),
        "baseline": Path(args.baseline_json),
        "anchor": Path(args.anchor_json),
        "ladder": Path(args.ladder_json),
        "battery": repo / "data/decay_scalar_prompts.json",
        "capability": repo / "data/rehearsal_capability_prompts.json",
        "survival": repo / "data/conversational_survival_generations.json",
    }
    config = {
        "version": PILOT_VERSION,
        "outcomes": sorted(OUTCOMES),
        "parent_identity": parent,
        "v2": v2,
        "pilot_seed": PILOT_SEED,
        "arm_a": {"beta": ARM_A_BETA, "alphas": list(ARM_A_ALPHAS)},
        "arm_b": {"beta": ARM_B_BETA, "alphas": list(ARM_B_ALPHAS)},
        "batch_size": args.batch_size,
        "max_new_tokens": args.max_new_tokens,
        "rules": expected_pilot_rules(),
        "controller_mapping_schema": MAPPING_SCHEMA,
        "controller_mapping_schema_sha256": MAPPING_SCHEMA_SHA256,
        "input_sha256": {key: sha256_of_file(path) for key, path in input_paths.items()},
        "code_sha256": source_identity["sha256"],
        "code_commit": source_identity["commit"],
    }
    config["fingerprint"] = fingerprint(config)
    if root.exists() and any(root.iterdir()) and not (root / "run_config.json").is_file():
        raise RuntimeError("v3 pilot requires a fresh root or its matching run_config")
    root.mkdir(parents=True, exist_ok=True)
    config_path = root / "run_config.json"
    if config_path.exists():
        if read_json(config_path) != config:
            raise RuntimeError("v3 pilot configuration changed; use a fresh root")
    else:
        write_json(config_path, config)
    identity_path = root / "parent_identity.json"
    if identity_path.exists():
        if read_json(identity_path) != parent:
            raise RuntimeError("v3 pilot parent identity changed")
    else:
        write_json(identity_path, parent)
    python, log = Path(sys.executable).absolute(), root / "commands.log"

    def run_dose(arm, beta, alpha):
        tag = f"alpha{alpha:g}"
        dose_dir = root / f"arm_{arm.lower()}" / tag
        checkpoint = dose_dir / "checkpoint"
        scalar_path = dose_dir / "scalar.json"
        sidecar_path = dose_dir / "decay_dose.json"
        stage_name = f"arm_{arm.lower()}_{tag}"
        marker = stage_marker(root, stage_name)

        # Recover a crash after scalar evaluation but before the retained
        # sidecar copy. A scalar without either sidecar remains fail-closed.
        if (
            not marker.exists()
            and scalar_path.is_file()
            and not sidecar_path.exists()
            and (checkpoint / "decay_dose.json").is_file()
        ):
            shutil.copy2(checkpoint / "decay_dose.json", sidecar_path)

        def action():
            dose_dir.mkdir(parents=True, exist_ok=True)
            if checkpoint.exists():
                safe_remove_checkpoint(checkpoint, root)
            run_command(
                [python, "scripts/apply_decay_noise.py", "--model", parent_path,
                 "--alpha", str(alpha), "--beta", str(beta), "--seed",
                 str(PILOT_SEED), "--output-dir", checkpoint,
                 "--source-identity-json", identity_path],
                log,
                repo,
            )
            run_command(
                [python, "scripts/eval_decay_scalar.py", checkpoint, scalar_path,
                 "--batch-size", str(args.batch_size), "--max-new-tokens",
                 str(args.max_new_tokens), "--seed", "0", "--judge-model",
                 parent_path, "--tokenizer-model", parent_path,
                 "--baseline-json", args.baseline_json, "--anchor-json",
                 args.anchor_json, "--ladder-json", args.ladder_json,
                 "--normalisation-policy", V2_POLICY],
                log,
                repo,
            )
            shutil.copy2(checkpoint / "decay_dose.json", sidecar_path)

        ensure_stage(
            root,
            stage_name,
            config["fingerprint"],
            {"arm": arm, "alpha": alpha, "beta": beta, "seed": PILOT_SEED},
            (scalar_path, sidecar_path),
            action,
        )
        sidecar = read_json(sidecar_path)
        expected_sidecar = {
            "source_model": str(parent_path),
            "tokenizer_source": str(parent_path),
            "source_identity_fingerprint": parent["fingerprint"],
            "alpha": float(alpha),
            "beta": float(beta),
            "seed": PILOT_SEED,
        }
        if {key: sidecar.get(key) for key in expected_sidecar} != expected_sidecar:
            raise RuntimeError(f"dose provenance mismatch: {arm} {alpha}")
        if sidecar.get("source_identity") != parent:
            raise RuntimeError(f"dose source identity mismatch: {arm} {alpha}")
        validate_scalar_artifact(
            scalar_path,
            expected_model=str(checkpoint),
            expected_judge=str(parent_path),
            expected_tokenizer=str(parent_path),
            expected_prompt_sha256=v2["prompt_sha256"],
            expected_weight_sha256=exact_hash_map(
                sidecar.get("weight_file_sha256"), "dose weight"
            ),
            expected_model_support_sha256=exact_hash_map(
                sidecar.get("support_file_sha256"), "dose support"
            ),
            expected_tokenizer_support_sha256=parent["support_file_sha256"],
            expected_judge_support_sha256=parent["support_file_sha256"],
            expected_judge_weight_sha256=parent["weight_file_sha256"],
            expected_policy=V2_POLICY,
            expected_policy_fingerprint=v2["policy_fingerprint"],
        )
        payload = read_json(scalar_path)
        validate_pilot_scalar_execution(payload, f"Arm {arm} alpha={alpha}")
        normalised, scalar, directions = normalise_components_bidirectional(
            payload["components"], baseline, positive, negative
        )
        scalar = require_scalar(scalar, f"dose scalar Arm {arm} alpha={alpha}")
        if abs(float(payload["scalar_0_100"]) - scalar) > 1e-9:
            raise RuntimeError(f"scalar/components mismatch: {arm} {alpha}")
        if (
            payload.get("normalised_components") != normalised
            or payload.get("normalisation_directions") != directions
        ):
            raise RuntimeError(f"scalar normalisation bundle mismatch: {arm} {alpha}")
        # The checkpoint remains available for diagnosis/retry until every
        # scalar, sidecar, identity and normalisation check above has passed.
        remove_checkpoint_after_validation(checkpoint, root, True)
        return {
            "alpha": float(alpha),
            "beta": float(beta),
            "seed": PILOT_SEED,
            "scheduled": True,
            "historical_seed_exception": False,
            "scalar": scalar,
            "components": payload["components"],
            "normalised_components": normalised,
            "normalisation_directions": directions,
            "scalar_json": str(scalar_path),
            "scalar_sha256": sha256_of_file(scalar_path),
            "dose_sidecar": str(sidecar_path),
            "dose_sidecar_sha256": sha256_of_file(sidecar_path),
            "checkpoint_deleted": not checkpoint.exists(),
        }

    def collect_arm(arm, beta, alphas, references):
        points = list(references)
        early = []
        for alpha in alphas:
            points.append(run_dose(arm, beta, alpha))
            points.sort(key=lambda record: record["alpha"])
            reason = should_fail_early(points, arm)
            if reason:
                early.append(reason)
                break
        return analyse_arm(points, arm, early)

    baseline_reference = {
        "alpha": 0.0,
        "beta": None,
        "seed": None,
        "scheduled": False,
        "historical_seed_exception": True,
        "scalar": v2["baseline_scalar"],
        "reference": "sealed_v2_baseline",
        "reference_artifact": str(Path(args.baseline_json).resolve()),
        "reference_artifact_sha256": config["input_sha256"]["baseline"],
    }
    terminal_reference = {
        "alpha": 1.0,
        "beta": 1.0,
        "seed": 0,
        "scheduled": False,
        "historical_seed_exception": True,
        "scalar": v2["terminal_scalar"],
        "reference": "sealed_v2_beta1_alpha1_endpoint",
        "reference_artifact": str(Path(args.anchor_json).resolve()),
        "reference_artifact_sha256": config["input_sha256"]["anchor"],
    }
    arm_a = collect_arm(
        "A", ARM_A_BETA, ARM_A_ALPHAS, (baseline_reference, terminal_reference)
    )
    arm_b = None
    if arm_a["promotion_screen_pass"]:
        outcome = outcome_for_arms(arm_a)
    else:
        arm_b = collect_arm(
            "B", ARM_B_BETA, ARM_B_ALPHAS, (baseline_reference,)
        )
        outcome = outcome_for_arms(arm_a, arm_b)
    if outcome not in OUTCOMES or outcome == "INCOMPLETE":
        raise RuntimeError("invalid terminal pilot outcome")
    promoted_arm = arm_a if outcome == "PROMOTE_ARM_A" else arm_b
    mapping_path = None
    mapping_sha256 = None
    mapping_fingerprint = None
    if outcome.startswith("PROMOTE_"):
        mapping = promoted_arm.get("controller_mapping") if promoted_arm else None
        if (
            not mapping
            or mapping.get("schema_sha256") != MAPPING_SCHEMA_SHA256
            or mapping.get("fingerprint")
            != fingerprint({key: value for key, value in mapping.items() if key != "fingerprint"})
        ):
            raise RuntimeError("promoted arm has no valid frozen controller mapping")
        mapping_path = root / "controller_mapping.json"
        write_json(mapping_path, mapping)
        mapping_sha256 = sha256_of_file(mapping_path)
        mapping_fingerprint = mapping["fingerprint"]
    summary = {
        "pilot_version": PILOT_VERSION,
        "certification_scope": "diagnostic_only_not_probe2_pass",
        "outcome": outcome,
        "config_fingerprint": config["fingerprint"],
        "v2_ruler": v2,
        "arm_a": arm_a,
        "arm_b": arm_b,
        "controller_mapping": str(mapping_path) if mapping_path else None,
        "controller_mapping_sha256": mapping_sha256,
        "controller_mapping_fingerprint": mapping_fingerprint,
        "controller_mapping_schema_sha256": MAPPING_SCHEMA_SHA256,
        "explicitly_not_a_pass_verdict": True,
        "next_step": (
            "freeze_a_separate_v3_certification_before_using_seeds_0_1_2"
            if outcome.startswith("PROMOTE_")
            else "stop_weight_noise_and_precommit_the_fallback_dial"
        ),
    }
    summary_path = root / "pilot_summary.json"
    write_json(summary_path, summary)
    write_json(
        root / "COMPLETE.json",
        {
            "status": "complete",
            "outcome": outcome,
            "summary_sha256": sha256_of_file(summary_path),
            "config_fingerprint": config["fingerprint"],
        },
    )
    write_manifest(root)
    validate_sealed_pilot(root)
    print(f"PROBE 2 V3 PILOT OUTCOME: {outcome}")


if __name__ == "__main__":
    main()
