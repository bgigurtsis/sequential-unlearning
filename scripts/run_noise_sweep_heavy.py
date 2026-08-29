"""Probe 2 heavy-parent repeat against a sealed clean-parent v2 ruler.

This driver is intentionally separate from ``run_noise_sweep.py``.  It first
verifies the sealed clean-parent primary archive, constructs one held-out
seed-7 parent in the global scalar band [60, 70], and then calibrates the
same eight incremental noise doses by three seeds on top of that exact
checkpoint.  Every child is scored against the clean primary baseline,
anchors, and policy; the heavy parent is never redefined as scalar zero.

The selected heavy checkpoint is retained for Probe 3.  Search candidates
outside the target band and all incremental child checkpoints are deleted
after their scalar and dose sidecars have been archived.  The output root is
sealed atomically, and overall Probe 2 PASS is emitted only in that sealed
aggregate record after both the primary and heavy gates pass.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from decay_scalar_normalization import (
    V2_POLICY,
    WEIGHTS,
    bidirectional_policy_fingerprint,
    load_bidirectional_anchors,
)
from run_noise_sweep import (
    DEFAULT_ALPHAS,
    DEFAULT_SEEDS,
    component_curve_diagnostics,
    fingerprint,
    isotonic_running_max,
    model_weight_hashes,
    pchip_eval,
    read_json,
    run_command,
    safe_remove_tree,
    sha256_of_file,
    spearman,
    support_file_hashes,
    validate_scalar_artifact,
    write_json,
    write_scalar_reanalysis,
)


HEAVY_PARENT_SEED = 7
HEAVY_TARGET = 65.0
HEAVY_BAND = (60.0, 70.0)
MAX_PARENT_BISECTIONS = 8
CLIFF_THRESHOLD = 20.0
MAX_CLIFF_BISECTIONS = 8
MAX_NEW_TOKENS = 256
NORMALISATION_VERSION = V2_POLICY
SUMMARY_NAME = "sweep_summary_heavy_parent_v2.json"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--clean-parent-model",
        required=True,
        help="exact local clean-parent snapshot used by the sealed primary",
    )
    parser.add_argument("--primary-root", default="derisk/probe2_noise_v2")
    parser.add_argument(
        "--root", default="derisk/probe2_noise_v2_heavy_parent"
    )
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=MAX_NEW_TOKENS)
    parser.add_argument("--beta", type=float, default=1.0)
    parser.add_argument(
        "--alphas", default=",".join(str(value) for value in DEFAULT_ALPHAS)
    )
    parser.add_argument(
        "--seeds", default=",".join(str(value) for value in DEFAULT_SEEDS)
    )
    parser.add_argument("--parent-seed", type=int, default=HEAVY_PARENT_SEED)
    parser.add_argument("--parent-target", type=float, default=HEAVY_TARGET)
    parser.add_argument("--parent-band-low", type=float, default=HEAVY_BAND[0])
    parser.add_argument("--parent-band-high", type=float, default=HEAVY_BAND[1])
    parser.add_argument(
        "--max-parent-bisections", type=int, default=MAX_PARENT_BISECTIONS
    )
    parser.add_argument("--cliff-threshold", type=float, default=CLIFF_THRESHOLD)
    parser.add_argument(
        "--max-cliff-bisections", type=int, default=MAX_CLIFF_BISECTIONS
    )
    return parser.parse_args()


def canonical_config(args):
    alphas = [float(value) for value in args.alphas.split(",")]
    seeds = [int(value) for value in args.seeds.split(",")]
    expected = {
        "alphas": DEFAULT_ALPHAS,
        "seeds": DEFAULT_SEEDS,
        "beta": 1.0,
        "max_new_tokens": MAX_NEW_TOKENS,
        "parent_seed": HEAVY_PARENT_SEED,
        "parent_target": HEAVY_TARGET,
        "parent_band": list(HEAVY_BAND),
        "max_parent_bisections": MAX_PARENT_BISECTIONS,
        "cliff_threshold": CLIFF_THRESHOLD,
        "max_cliff_bisections": MAX_CLIFF_BISECTIONS,
    }
    actual = {
        "alphas": alphas,
        "seeds": seeds,
        "beta": args.beta,
        "max_new_tokens": args.max_new_tokens,
        "parent_seed": args.parent_seed,
        "parent_target": args.parent_target,
        "parent_band": [args.parent_band_low, args.parent_band_high],
        "max_parent_bisections": args.max_parent_bisections,
        "cliff_threshold": args.cliff_threshold,
        "max_cliff_bisections": args.max_cliff_bisections,
    }
    if actual != expected:
        raise ValueError(
            "heavy-parent certification configuration mismatch: "
            f"expected={expected} actual={actual}"
        )
    return actual


def parse_manifest_line(line):
    digest, separator, relative = line.partition("  ")
    if not separator or len(digest) != 64:
        raise RuntimeError(f"malformed manifest line: {line!r}")
    try:
        int(digest, 16)
    except ValueError as error:
        raise RuntimeError(f"malformed manifest digest: {digest!r}") from error
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise RuntimeError(f"unsafe manifest path: {relative!r}")
    return digest.lower(), relative_path


def verify_manifest(root):
    """Verify that a manifest exactly covers every non-manifest file."""
    root = Path(root).resolve()
    manifest = root / "MANIFEST.sha256"
    if not manifest.is_file():
        raise RuntimeError(f"archive is not sealed: {root}")
    entries = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        expected, relative = parse_manifest_line(line)
        key = relative.as_posix()
        if key in entries:
            raise RuntimeError(f"duplicate manifest entry: {key}")
        entries[key] = expected
    actual_files = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and path != manifest
    }
    if set(entries) != set(actual_files):
        missing = sorted(set(actual_files) - set(entries))
        stale = sorted(set(entries) - set(actual_files))
        raise RuntimeError(
            f"manifest coverage mismatch in {root}: missing={missing} stale={stale}"
        )
    for relative, expected in entries.items():
        actual = sha256_of_file(actual_files[relative])
        if actual != expected:
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
    lines = [
        f"{sha256_of_file(path)}  {path.relative_to(root).as_posix()}"
        for path in files
    ]
    temporary.write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    temporary.replace(output)
    return verify_manifest(root)


def validate_primary_archive(primary_root, clean_parent):
    primary_root = Path(primary_root).resolve()
    seal = verify_manifest(primary_root)
    summary_path = primary_root / "sweep_summary_bidirectional_v2.json"
    config_path = primary_root / "run_config.json"
    identity_path = primary_root / "parent_identity.json"
    for path in (summary_path, config_path, identity_path):
        if not path.is_file():
            raise RuntimeError(f"sealed primary is missing {path.name}")
    summary = read_json(summary_path)
    config = read_json(config_path)
    identity = read_json(identity_path)
    gates = summary.get("gates", {})
    if summary.get("certification_scope") != "clean_parent_primary_only":
        raise RuntimeError("wrong primary certification scope")
    if gates.get("primary_verdict") != "PASS":
        raise RuntimeError("heavy repeat requires primary_verdict PASS")
    if gates.get("probe2_verdict") != "INCOMPLETE_PENDING_HEAVY_PARENT":
        raise RuntimeError("primary overall verdict is not pending heavy parent")
    alpha65 = summary.get("alpha_at_scalar", {}).get("65.0")
    if alpha65 is None or not 0.0 < float(alpha65) < 1.0:
        raise RuntimeError("sealed primary has no interior scalar-65 alpha")
    clean_parent = str(Path(clean_parent).resolve())
    if summary.get("parent_model") != clean_parent:
        raise RuntimeError("clean parent path differs from sealed primary")
    if config.get("parent_model") != clean_parent:
        raise RuntimeError("primary run config names a different clean parent")
    if identity.get("source_model") != clean_parent:
        raise RuntimeError("primary parent identity names a different model")
    current_weights = model_weight_hashes(clean_parent)
    current_support = support_file_hashes(clean_parent)
    if identity.get("weight_file_sha256") != current_weights:
        raise RuntimeError("clean-parent weight hashes differ from sealed primary")
    if identity.get("support_file_sha256") != current_support:
        raise RuntimeError("clean-parent support hashes differ from sealed primary")
    expected_identity = dict(identity)
    recorded_fingerprint = expected_identity.pop("fingerprint", None)
    if recorded_fingerprint != fingerprint(expected_identity):
        raise RuntimeError("primary parent identity fingerprint is invalid")
    if summary.get("normalisation_version") != NORMALISATION_VERSION:
        raise RuntimeError("primary uses the wrong normalisation policy")
    return {
        "root": primary_root,
        "seal": seal,
        "summary_path": summary_path,
        "summary": summary,
        "config_path": config_path,
        "config": config,
        "identity_path": identity_path,
        "identity": identity,
        "alpha65": float(alpha65),
    }


def select_parent_alpha(nominal_alpha, evaluate, low_band=60.0, high_band=70.0,
                        max_bisections=8):
    """Pure bounded same-seed search used by the driver and CPU tests."""
    history = []

    def measured(alpha, reason):
        alpha = round(float(alpha), 6)
        scalar = float(evaluate(alpha))
        history.append({"alpha": alpha, "scalar": scalar, "reason": reason})
        return scalar

    nominal = round(float(nominal_alpha), 6)
    scalar = measured(nominal, "primary_curve_scalar65")
    if low_band <= scalar <= high_band:
        return nominal, scalar, history
    if scalar > high_band:
        low_alpha, low_scalar = 0.0, 0.0
        high_alpha, high_scalar = nominal, scalar
    else:
        low_alpha, low_scalar = nominal, scalar
        high_alpha = 1.0
        high_scalar = measured(high_alpha, "establish_upper_bracket")
        if low_band <= high_scalar <= high_band:
            return high_alpha, high_scalar, history
        if high_scalar < low_band:
            return None, None, history
    for _ in range(max_bisections):
        midpoint = round((low_alpha + high_alpha) / 2.0, 6)
        if midpoint in {low_alpha, high_alpha}:
            break
        midpoint_scalar = measured(midpoint, "same_seed_bisection")
        if low_band <= midpoint_scalar <= high_band:
            return midpoint, midpoint_scalar, history
        if midpoint_scalar < low_band:
            low_alpha, low_scalar = midpoint, midpoint_scalar
        else:
            high_alpha, high_scalar = midpoint, midpoint_scalar
    return None, None, history


def loo_errors(xs, raw_ys, held_alphas, held_values):
    errors = {}
    for held_alpha, held_value in zip(held_alphas, held_values):
        rest_x = [x for x in xs if x != held_alpha]
        rest_y = isotonic_running_max(
            [value for x, value in zip(xs, raw_ys) if x != held_alpha]
        )
        predicted = pchip_eval(rest_x, rest_y, held_alpha)
        errors[held_alpha] = abs(predicted - held_value)
    return errors


def analyse_heavy_curve(curve, base_scalar, endpoint_scalar, bisections,
                        cliff_threshold=CLIFF_THRESHOLD):
    sorted_alphas = sorted(curve)
    means = [curve[alpha]["mean"] for alpha in sorted_alphas]
    gate_alphas = list(DEFAULT_ALPHAS)
    gate_means = [curve[alpha]["mean"] for alpha in gate_alphas]
    rho = spearman(gate_alphas, gate_means)
    xs = [0.0] + sorted_alphas + [1.0]
    raw_ys = [float(base_scalar)] + means + [float(endpoint_scalar)]
    fitted = isotonic_running_max(raw_ys)
    errors = loo_errors(xs, raw_ys, sorted_alphas, means)
    max_error = max(errors.values()) if errors else None
    points = sorted(set(curve) | {1.0})
    unresolved = []
    for low, high in zip(points, points[1:]):
        low_mean = endpoint_scalar if low == 1.0 else curve[low]["mean"]
        high_mean = endpoint_scalar if high == 1.0 else curve[high]["mean"]
        gap = abs(high_mean - low_mean)
        if max(low, high) > 0.5 and gap > cliff_threshold:
            unresolved.append(
                {"between": [low, high], "gap": gap, "width": high - low}
            )
    gates = {
        "spearman_seed_means": rho,
        "spearman_gate_pass": rho is not None and rho >= 0.95,
        "loo_interpolation_errors": errors,
        "max_loo_error": max_error,
        "loo_gate_pass": max_error is not None and max_error <= 3.0,
        "isotonic_policy": "running maximum against sealed clean ruler",
        "isotonic_fitted_means_with_endpoints": fitted,
        "max_isotonic_adjustment": max(
            adjusted - raw for adjusted, raw in zip(fitted, raw_ys)
        ),
        "curve_strictly_nondecreasing": all(
            right >= left - 1e-9 for left, right in zip(raw_ys, raw_ys[1:])
        ),
        "cliffs_bisected": bisections,
        "unresolved_cliffs": unresolved,
        "cliff_resolution_complete": not unresolved,
        "fallback_dial_required": bool(unresolved),
        "weight_noise_component_diagnostics": component_curve_diagnostics(
            curve, gate_alphas
        ),
    }
    gates["heavy_verdict"] = (
        "PASS"
        if gates["spearman_gate_pass"] and gates["loo_gate_pass"]
        else "FAIL"
    )
    return gates


def curve_alphas_for_resume(bisections):
    persisted = [float(entry["alpha"]) for entry in bisections]
    if any(not 0.0 < alpha < 1.0 for alpha in persisted):
        raise RuntimeError("invalid persisted heavy-sweep bisection alpha")
    return sorted(set(DEFAULT_ALPHAS + persisted))


def main():
    args = parse_args()
    canonical = canonical_config(args)
    repo = Path.cwd().resolve()
    clean_parent = Path(args.clean_parent_model).expanduser().resolve()
    if not clean_parent.is_dir():
        raise ValueError("--clean-parent-model must be an exact local snapshot")
    primary = validate_primary_archive(args.primary_root, clean_parent)
    primary_root = primary["root"]
    root = Path(args.root).resolve()
    if root == primary_root or primary_root in root.parents or root in primary_root.parents:
        raise ValueError("heavy and primary archives must be disjoint roots")
    if (root / "MANIFEST.sha256").exists():
        raise RuntimeError(f"refusing to modify sealed archive {root}")
    root.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable).absolute()
    log = root / "commands.log"

    baseline_json = primary_root / "baseline" / "scalar.json"
    terminal_json = primary_root / "anchor" / "scalar.json"
    ladder_json = primary_root / "ladder" / "corruption_ladder.json"
    baseline, positive, negative, sources = load_bidirectional_anchors(
        baseline_json, terminal_json, ladder_json
    )
    policy_fingerprint = bidirectional_policy_fingerprint(
        baseline, positive, negative, sources
    )
    if policy_fingerprint != primary["summary"].get(
        "normalisation_policy_fingerprint"
    ):
        raise RuntimeError("primary policy fingerprint does not reproduce")

    instrument_paths = (
        "scripts/apply_decay_noise.py",
        "scripts/decay_scalar_normalization.py",
        "scripts/eval_decay_scalar.py",
        "scripts/run_noise_sweep.py",
        "scripts/run_noise_sweep_heavy.py",
        "data/decay_scalar_prompts.json",
        "data/rehearsal_capability_prompts.json",
        "data/conversational_survival_generations.json",
    )
    run_config = {
        **canonical,
        "certification_scope": "heavy_parent_repeat_and_probe2_aggregate",
        "clean_parent_model": str(clean_parent),
        "primary_archive": {
            "root": str(primary_root),
            "manifest_sha256": primary["seal"]["sha256"],
            "summary_sha256": sha256_of_file(primary["summary_path"]),
            "run_config_sha256": sha256_of_file(primary["config_path"]),
            "parent_identity_sha256": sha256_of_file(primary["identity_path"]),
        },
        "clean_parent_identity": primary["identity"],
        "clean_ruler": {
            "baseline": sha256_of_file(baseline_json),
            "terminal": sha256_of_file(terminal_json),
            "ladder": sha256_of_file(ladder_json),
            "policy_fingerprint": policy_fingerprint,
        },
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip(),
        "instrument_file_sha256": {
            path: sha256_of_file(repo / path) for path in instrument_paths
        },
        "batch_size": args.batch_size,
    }
    run_config["fingerprint"] = fingerprint(run_config)
    config_path = root / "run_config.json"
    if config_path.exists():
        if read_json(config_path) != run_config:
            raise RuntimeError("heavy run configuration mismatch")
    else:
        write_json(config_path, run_config)
    state_path = root / "state.json"
    state = (
        read_json(state_path)
        if state_path.exists()
        else {
            "status": "selecting_heavy_parent",
            "run_config_fingerprint": run_config["fingerprint"],
            "parent_search": [],
            "bisections": [],
        }
    )
    if state.get("run_config_fingerprint") != run_config["fingerprint"]:
        raise RuntimeError("heavy state/config mismatch")
    write_json(state_path, state)

    expected_prompt_sha256 = {
        "battery": run_config["instrument_file_sha256"][
            "data/decay_scalar_prompts.json"
        ],
        "capability": run_config["instrument_file_sha256"][
            "data/rehearsal_capability_prompts.json"
        ],
        "survival": run_config["instrument_file_sha256"][
            "data/conversational_survival_generations.json"
        ],
    }

    def evaluate_checkpoint(checkpoint, scalar_json, sidecar, expected_policy=True):
        validate_scalar_artifact(
            scalar_json,
            expected_model=str(checkpoint),
            expected_judge=str(clean_parent),
            expected_tokenizer=str(clean_parent),
            expected_prompt_sha256=expected_prompt_sha256,
            expected_weight_sha256=sidecar["weight_file_sha256"],
            expected_model_support_sha256=sidecar["support_file_sha256"],
            expected_tokenizer_support_sha256=primary["identity"][
                "support_file_sha256"
            ],
            expected_judge_support_sha256=primary["identity"][
                "support_file_sha256"
            ],
            expected_judge_weight_sha256=primary["identity"][
                "weight_file_sha256"
            ],
            expected_policy=(NORMALISATION_VERSION if expected_policy else None),
            expected_policy_fingerprint=(
                policy_fingerprint if expected_policy else None
            ),
        )
        value, companion = write_scalar_reanalysis(
            scalar_json, baseline, positive, negative, sources
        )
        return value, companion

    candidate_cache = {}

    def parent_candidate(alpha):
        tag = f"alpha{alpha:g}_seed{HEAVY_PARENT_SEED}"
        candidate_dir = root / "parent_search" / tag
        checkpoint = candidate_dir / "checkpoint"
        scalar_json = candidate_dir / "scalar.json"
        sidecar_path = candidate_dir / "decay_dose.json"
        if scalar_json.exists() and not sidecar_path.exists():
            checkpoint_sidecar = checkpoint / "decay_dose.json"
            if checkpoint_sidecar.exists():
                shutil.copy2(checkpoint_sidecar, sidecar_path)
            else:
                raise RuntimeError(f"parent candidate missing sidecar: {tag}")
        if not scalar_json.exists():
            checkpoint_complete = (checkpoint / "decay_dose.json").is_file()
            if checkpoint.is_dir() and not checkpoint_complete:
                safe_remove_tree(checkpoint, root)
            if not checkpoint_complete:
                run_command(
                    [
                        python,
                        "scripts/apply_decay_noise.py",
                        "--model",
                        clean_parent,
                        "--alpha",
                        str(alpha),
                        "--seed",
                        str(HEAVY_PARENT_SEED),
                        "--beta",
                        "1.0",
                        "--output-dir",
                        checkpoint,
                        "--source-identity-json",
                        primary["identity_path"],
                    ],
                    log,
                    repo,
                )
            run_command(
                [
                    python,
                    "scripts/eval_decay_scalar.py",
                    checkpoint,
                    scalar_json,
                    "--batch-size",
                    str(args.batch_size),
                    "--max-new-tokens",
                    str(MAX_NEW_TOKENS),
                    "--seed",
                    "0",
                    "--judge-model",
                    clean_parent,
                    "--tokenizer-model",
                    clean_parent,
                    "--baseline-json",
                    baseline_json,
                    "--anchor-json",
                    terminal_json,
                    "--ladder-json",
                    ladder_json,
                    "--normalisation-policy",
                    NORMALISATION_VERSION,
                ],
                log,
                repo,
            )
            shutil.copy2(checkpoint / "decay_dose.json", sidecar_path)
        sidecar = read_json(sidecar_path)
        expected = {
            "source_model": str(clean_parent),
            "tokenizer_source": str(clean_parent),
            "source_identity_fingerprint": primary["identity"]["fingerprint"],
            "alpha": float(alpha),
            "beta": 1.0,
            "seed": HEAVY_PARENT_SEED,
        }
        if {key: sidecar.get(key) for key in expected} != expected:
            raise RuntimeError(f"parent candidate dose mismatch: {tag}")
        if sidecar.get("source_identity") != primary["identity"]:
            raise RuntimeError(f"parent candidate source mismatch: {tag}")
        value, companion = evaluate_checkpoint(
            checkpoint, scalar_json, sidecar, expected_policy=True
        )
        candidate_cache[round(float(alpha), 6)] = {
            "dir": candidate_dir,
            "checkpoint": checkpoint,
            "scalar_json": scalar_json,
            "sidecar_path": sidecar_path,
            "sidecar": sidecar,
            "reanalysis": companion,
            "scalar": value,
        }
        return value

    selected_alpha, selected_scalar, search_history = select_parent_alpha(
        primary["alpha65"], parent_candidate
    )
    state["parent_search"] = search_history
    if selected_alpha is None:
        for candidate in candidate_cache.values():
            if candidate["checkpoint"].is_dir():
                safe_remove_tree(candidate["checkpoint"], root)
        state["status"] = "failed_heavy_parent_selection"
        state["failure_stage"] = "heavy_parent_selection"
        write_json(state_path, state)
        failure = {
            "certification_scope": "heavy_parent_repeat_and_probe2_aggregate",
            "primary_archive": run_config["primary_archive"],
            "heavy_parent_search": search_history,
            "gates": {
                "heavy_parent_band": list(HEAVY_BAND),
                "heavy_parent_selection_pass": False,
                "heavy_verdict": "FAIL",
                "probe2_verdict": "FAIL",
            },
        }
        write_json(root / SUMMARY_NAME, failure)
        seal = write_manifest_atomic(root)
        print(f"PROBE 2 OVERALL VERDICT: FAIL; sealed {seal['path']}")
        return

    selected = candidate_cache[selected_alpha]
    for alpha, candidate in candidate_cache.items():
        if alpha != selected_alpha and candidate["checkpoint"].is_dir():
            safe_remove_tree(candidate["checkpoint"], root)
    if not selected["checkpoint"].is_dir():
        raise RuntimeError("selected heavy checkpoint was not preserved")
    if model_weight_hashes(selected["checkpoint"]) != selected["sidecar"][
        "weight_file_sha256"
    ]:
        raise RuntimeError("selected heavy checkpoint weight hashes changed")
    if support_file_hashes(selected["checkpoint"]) != selected["sidecar"][
        "support_file_sha256"
    ]:
        raise RuntimeError("selected heavy checkpoint support hashes changed")
    heavy_identity = {
        "source_model": str(selected["checkpoint"]),
        "weight_file_sha256": selected["sidecar"]["weight_file_sha256"],
        "support_file_sha256": selected["sidecar"]["support_file_sha256"],
        "clean_parent_identity_fingerprint": primary["identity"]["fingerprint"],
        "dose_sidecar_sha256": sha256_of_file(selected["sidecar_path"]),
        "scalar_json_sha256": sha256_of_file(selected["scalar_json"]),
        "reanalysis_sha256": sha256_of_file(selected["reanalysis"]),
        "administered_alpha": selected_alpha,
        "dose_seed": HEAVY_PARENT_SEED,
        "measured_global_scalar": selected_scalar,
    }
    heavy_identity["fingerprint"] = fingerprint(heavy_identity)
    heavy_identity_path = root / "heavy_parent_identity.json"
    if heavy_identity_path.exists():
        if read_json(heavy_identity_path) != heavy_identity:
            raise RuntimeError("heavy parent identity mismatch")
    else:
        write_json(heavy_identity_path, heavy_identity)
    state["selected_heavy_parent"] = heavy_identity
    state["status"] = "running_heavy_sweep"
    write_json(state_path, state)

    def child_dose(alpha, seed):
        tag = f"alpha{alpha:g}_seed{seed}"
        dose_dir = root / "sweep" / tag
        checkpoint = dose_dir / "checkpoint"
        scalar_json = dose_dir / "scalar.json"
        sidecar_path = dose_dir / "decay_dose.json"
        if scalar_json.exists() and not sidecar_path.exists():
            checkpoint_sidecar = checkpoint / "decay_dose.json"
            if checkpoint_sidecar.exists():
                shutil.copy2(checkpoint_sidecar, sidecar_path)
            else:
                raise RuntimeError(f"child scalar missing dose sidecar: {tag}")
        if not scalar_json.exists():
            checkpoint_complete = (checkpoint / "decay_dose.json").is_file()
            if checkpoint.is_dir() and not checkpoint_complete:
                safe_remove_tree(checkpoint, root)
            if not checkpoint_complete:
                run_command(
                    [
                        python,
                        "scripts/apply_decay_noise.py",
                        "--model",
                        selected["checkpoint"],
                        "--alpha",
                        str(alpha),
                        "--seed",
                        str(seed),
                        "--beta",
                        "1.0",
                        "--output-dir",
                        checkpoint,
                        "--source-identity-json",
                        heavy_identity_path,
                    ],
                    log,
                    repo,
                )
            run_command(
                [
                    python,
                    "scripts/eval_decay_scalar.py",
                    checkpoint,
                    scalar_json,
                    "--batch-size",
                    str(args.batch_size),
                    "--max-new-tokens",
                    str(MAX_NEW_TOKENS),
                    "--seed",
                    "0",
                    "--judge-model",
                    clean_parent,
                    "--tokenizer-model",
                    clean_parent,
                    "--baseline-json",
                    baseline_json,
                    "--anchor-json",
                    terminal_json,
                    "--ladder-json",
                    ladder_json,
                    "--normalisation-policy",
                    NORMALISATION_VERSION,
                ],
                log,
                repo,
            )
            shutil.copy2(checkpoint / "decay_dose.json", sidecar_path)
        sidecar = read_json(sidecar_path)
        expected = {
            "source_model": str(selected["checkpoint"]),
            "tokenizer_source": str(selected["checkpoint"]),
            "source_identity_fingerprint": heavy_identity["fingerprint"],
            "alpha": float(alpha),
            "beta": 1.0,
            "seed": int(seed),
        }
        if {key: sidecar.get(key) for key in expected} != expected:
            raise RuntimeError(f"child dose provenance mismatch: {tag}")
        if sidecar.get("source_identity") != heavy_identity:
            raise RuntimeError(f"child source identity mismatch: {tag}")
        value, companion = evaluate_checkpoint(
            checkpoint, scalar_json, sidecar, expected_policy=True
        )
        if checkpoint.is_dir():
            safe_remove_tree(checkpoint, root)
        payload = read_json(companion)
        return {
            "seed": int(seed),
            "scalar": value,
            "raw_components": payload["components"],
            "normalised_components": payload["normalised_components"],
            "normalisation_directions": payload["normalisation_directions"],
            "scalar_json": str(scalar_json),
            "reanalysis_json": str(companion),
            "decay_dose_json": str(sidecar_path),
        }

    def collect_curve(alphas):
        collected = {}
        for alpha in alphas:
            per_seed = [child_dose(alpha, seed) for seed in DEFAULT_SEEDS]
            collected[alpha] = {
                "per_seed": per_seed,
                "mean": sum(item["scalar"] for item in per_seed) / len(per_seed),
                "raw_component_means": {
                    key: sum(item["raw_components"][key] for item in per_seed)
                    / len(per_seed)
                    for key in WEIGHTS
                },
                "normalised_component_means": {
                    key: sum(
                        item["normalised_components"][key] for item in per_seed
                    )
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
                            {
                                item["normalisation_directions"][key]
                                for item in per_seed
                            }
                        )
                    }
                    for key in WEIGHTS
                },
            }
            print(
                f"heavy alpha={alpha:g}: mean={collected[alpha]['mean']:.2f}",
                flush=True,
            )
        return collected

    curve = collect_curve(curve_alphas_for_resume(state.get("bisections", [])))
    endpoint_entry = child_dose(1.0, 0)
    endpoint_scalar = endpoint_entry["scalar"]
    bisection_count = len(state["bisections"])
    while bisection_count < MAX_CLIFF_BISECTIONS:
        points = sorted(set(curve) | {1.0})
        new_dose = None
        for low, high in zip(points, points[1:]):
            low_mean = endpoint_scalar if low == 1.0 else curve[low]["mean"]
            high_mean = endpoint_scalar if high == 1.0 else curve[high]["mean"]
            gap = abs(high_mean - low_mean)
            if max(low, high) > 0.5 and gap > CLIFF_THRESHOLD:
                midpoint = round((low + high) / 2.0, 4)
                if midpoint not in curve:
                    new_dose = {
                        "alpha": midpoint,
                        "between": [low, high],
                        "gap": gap,
                    }
                    break
        if new_dose is None:
            break
        state["bisections"].append(new_dose)
        write_json(state_path, state)
        curve.update(collect_curve([new_dose["alpha"]]))
        bisection_count += 1

    gates = analyse_heavy_curve(
        curve,
        selected_scalar,
        endpoint_scalar,
        state["bisections"],
    )
    gates["heavy_parent_selection_pass"] = HEAVY_BAND[0] <= selected_scalar <= HEAVY_BAND[1]
    gates["primary_manifest_verified"] = True
    gates["primary_verdict_verified"] = True
    if not gates["heavy_parent_selection_pass"]:
        gates["heavy_verdict"] = "FAIL"
    gates["probe2_verdict"] = (
        "PASS" if gates["heavy_verdict"] == "PASS" else "FAIL"
    )
    summary = {
        "certification_scope": "heavy_parent_repeat_and_probe2_aggregate",
        "primary_archive": run_config["primary_archive"],
        "clean_ruler": run_config["clean_ruler"],
        "normalisation_version": NORMALISATION_VERSION,
        "normalisation_policy_fingerprint": policy_fingerprint,
        "heavy_parent": {
            "identity": heavy_identity,
            "identity_json": str(heavy_identity_path),
            "selection_history": search_history,
            "checkpoint": str(selected["checkpoint"]),
        },
        "incremental_alpha1_endpoint": endpoint_entry,
        "curve": {str(alpha): curve[alpha] for alpha in sorted(curve)},
        "gates": gates,
    }
    summary_path = root / SUMMARY_NAME
    write_json(summary_path, summary)
    state["status"] = (
        "probe2_passed" if gates["probe2_verdict"] == "PASS" else "failed_heavy"
    )
    if gates["probe2_verdict"] != "PASS":
        state["failure_stage"] = "heavy_parent_calibration"
    write_json(state_path, state)
    seal = write_manifest_atomic(root)
    print("gates=" + json.dumps(gates, default=str))
    print(f"PROBE 2 OVERALL VERDICT: {gates['probe2_verdict']}")
    print(f"Wrote {summary_path}")
    print(f"Sealed {seal['path']} ({seal['entry_count']} files)")


if __name__ == "__main__":
    main()
