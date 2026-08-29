"""Probe 2 driver: decay-dial calibration sweep and scalar certification.

Stages, all resume-safe (a stage is skipped when its output exists):
  (a) baseline decay-scalar eval on the clean parent (anchor 0);
  (b) terminal anchor: alpha=1.0 dose, eval (anchor 1), checkpoint deleted;
  (c) 11-rung synthetic corruption ladder from the baseline generations;
  (d) sweep alpha x seeds: dose, eval, delete the checkpoint copy (the dose
      is re-drawable from the sidecar seed; the sidecar is kept);
  (e) analysis: monotone fit, Spearman gate, leave-one-out interpolation
      error, cliff detection with automatic bisection above alpha 0.5.

Gates (SYNTHESIS section 7, probe 2):
  - scalar monotone in alpha: Spearman >= 0.95 on seed-means;
  - +/-3%: leave-one-out interpolation error <= 3 scalar points everywhere;
  - components monotone on the corruption ladder (plateaus flagged).
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from decay_scalar_normalization import (
    V2_CORRUPTION_TRACKS,
    V2_LADDER_VERSION,
    V2_POLICY,
    WEIGHTS,
    bidirectional_policy_fingerprint,
    load_bidirectional_anchors,
    normalise_components_bidirectional,
)


DEFAULT_ALPHAS = [0.05, 0.1, 0.2, 0.3, 0.45, 0.6, 0.75, 0.9]
DEFAULT_SEEDS = [0, 1, 2]
NORMALISATION_VERSION = V2_POLICY


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--parent-model",
        required=True,
        help="exact local clean-parent model snapshot directory",
    )
    parser.add_argument("--root", default="derisk/probe2_noise_v2")
    parser.add_argument("--alphas", default=",".join(str(a) for a in DEFAULT_ALPHAS))
    parser.add_argument("--seeds", default=",".join(str(s) for s in DEFAULT_SEEDS))
    parser.add_argument("--beta", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--cliff-threshold", type=float, default=20.0)
    parser.add_argument("--max-bisections", type=int, default=8)
    parser.add_argument("--skip-ladder", action="store_true")
    return parser.parse_args()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    path = Path(path)
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


def model_weight_hashes(model_dir):
    model_dir = Path(model_dir)
    weight_files = sorted(
        list(model_dir.glob("*.safetensors")) + list(model_dir.glob("*.bin"))
    )
    if not weight_files:
        raise RuntimeError(f"no model weight files found in {model_dir}")
    return {path.name: sha256_of_file(path) for path in weight_files}


def support_file_hashes(model_dir):
    model_dir = Path(model_dir)
    return {
        path.name: sha256_of_file(path)
        for path in sorted(path for path in model_dir.iterdir() if path.is_file())
        if path.suffix not in {".safetensors", ".bin"}
        and path.name != "decay_dose.json"
    }


def write_scalar_reanalysis(
    path, baseline, positive_anchor, negative_anchor, anchor_sources
):
    """Write a corrected companion without altering the original scalar JSON."""
    path = Path(path)
    output = path.with_name("scalar_reanalysis_bidirectional_v2.json")
    source_sha256 = sha256_of_file(path)
    policy_fingerprint = bidirectional_policy_fingerprint(
        baseline,
        positive_anchor,
        negative_anchor,
        anchor_sources,
    )
    if output.exists():
        existing = read_json(output)
        if (
            existing.get("source_scalar_sha256") != source_sha256
            or existing.get("policy_fingerprint") != policy_fingerprint
        ):
            raise RuntimeError(f"stale reanalysis companion: {output}")
        return existing["scalar_0_100"], output
    components = read_json(path)["components"]
    normalised, scalar, directions = normalise_components_bidirectional(
        components, baseline, positive_anchor, negative_anchor
    )
    write_json(
        output,
        {
            "normalisation_version": NORMALISATION_VERSION,
            "source_scalar_json": str(path),
            "source_scalar_sha256": source_sha256,
            "policy_fingerprint": policy_fingerprint,
            "components": components,
            "normalised_components": normalised,
            "normalisation_directions": directions,
            "scalar_0_100": scalar,
            "baseline_components": baseline,
            "positive_component_anchor": positive_anchor,
            "negative_component_anchor": negative_anchor,
            "component_anchor_sources": anchor_sources,
        },
    )
    return scalar, output


def read_ladder_gate(ladder_json):
    payload = read_json(ladder_json)
    monotonicity = payload["monotonicity"]
    expected = set(WEIGHTS)
    if set(monotonicity) != expected:
        raise RuntimeError(
            f"ladder monotonicity keys must be {sorted(expected)}; "
            f"found {sorted(monotonicity)}"
        )
    component_pass = {
        key: bool(
            result
            and result.get("strictly_nondecreasing")
            and float(result.get("range", 0.0)) > 1e-6
        )
        for key, result in monotonicity.items()
    }
    gate_pass = bool(component_pass) and all(component_pass.values())
    return monotonicity, component_pass, gate_pass


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
        return_code = process.wait()
        log.write(f"\nexit={return_code} duration_seconds={time.time() - started:.1f}\n")
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)


def safe_remove_tree(path, root):
    resolved = Path(path).resolve()
    root = Path(root).resolve()
    if root not in resolved.parents or resolved == root:
        raise RuntimeError(f"refusing to remove path outside sweep root: {resolved}")
    if resolved.is_dir():
        print(f"Removing re-drawable checkpoint {resolved}", flush=True)
        shutil.rmtree(resolved)


def pchip_slopes(xs, ys):
    # Fritsch-Carlson monotone cubic slopes.
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    delta = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0] = delta[0]
    m[-1] = delta[-1]
    for i in range(1, n - 1):
        if delta[i - 1] * delta[i] <= 0:
            m[i] = 0.0
        else:
            w1 = 2 * h[i] + h[i - 1]
            w2 = h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])
    for i in range(n - 1):
        if delta[i] == 0.0:
            m[i] = 0.0
            m[i + 1] = 0.0
    return m


def pchip_eval(xs, ys, x):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    m = pchip_slopes(xs, ys)
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            h = xs[i + 1] - xs[i]
            t = (x - xs[i]) / h
            h00 = 2 * t**3 - 3 * t**2 + 1
            h10 = t**3 - 2 * t**2 + t
            h01 = -2 * t**3 + 3 * t**2
            h11 = t**3 - t**2
            return (
                h00 * ys[i]
                + h10 * h * m[i]
                + h01 * ys[i + 1]
                + h11 * h * m[i + 1]
            )
    raise RuntimeError("unreachable")


def invert_curve(xs, ys, target, iterations=60):
    # Binary-search the monotone PCHIP fit for the alpha hitting `target`.
    if target <= ys[0] or target >= ys[-1]:
        return None
    low, high = xs[0], xs[-1]
    for _ in range(iterations):
        mid = (low + high) / 2
        if pchip_eval(xs, ys, mid) < target:
            low = mid
        else:
            high = mid
    return round((low + high) / 2, 4)


def spearman(xs, ys):
    def ranks(values):
        order = sorted(range(len(values)), key=lambda index: values[index])
        result = [0.0] * len(values)
        index = 0
        while index < len(order):
            tie_end = index
            while (
                tie_end + 1 < len(order)
                and values[order[tie_end + 1]] == values[order[index]]
            ):
                tie_end += 1
            average = (index + tie_end) / 2.0 + 1.0
            for position in order[index : tie_end + 1]:
                result[position] = average
            index = tie_end + 1
        return result

    rank_x, rank_y = ranks(xs), ranks(ys)
    mean_x = sum(rank_x) / len(rank_x)
    mean_y = sum(rank_y) / len(rank_y)
    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(rank_x, rank_y))
    var_x = sum((a - mean_x) ** 2 for a in rank_x)
    var_y = sum((b - mean_y) ** 2 for b in rank_y)
    if var_x == 0 or var_y == 0:
        return None
    return cov / (var_x * var_y) ** 0.5


def isotonic_running_max(values):
    result = []
    for value in values:
        result.append(value if not result else max(result[-1], value))
    return result


def validate_scalar_artifact(
    path,
    *,
    expected_model,
    expected_judge,
    expected_tokenizer,
    expected_prompt_sha256,
    expected_weight_sha256,
    expected_model_support_sha256,
    expected_tokenizer_support_sha256,
    expected_judge_support_sha256,
    expected_judge_weight_sha256,
    expected_policy=None,
    expected_policy_fingerprint=None,
):
    payload = read_json(path)
    if payload.get("model") != str(expected_model):
        raise RuntimeError(f"model provenance mismatch in {path}")
    if payload.get("judge_model") != str(expected_judge):
        raise RuntimeError(f"judge provenance mismatch in {path}")
    if payload.get("tokenizer_model") != str(expected_tokenizer):
        raise RuntimeError(f"tokenizer provenance mismatch in {path}")
    if payload.get("limit") is not None:
        raise RuntimeError(f"limited scalar artifact cannot certify Probe 2: {path}")
    if payload.get("judge_parse_complete") is not True:
        raise RuntimeError(f"unparsed judge outputs in {path}")
    components = payload.get("components", {})
    if set(components) != set(WEIGHTS) or any(
        components[key] is None for key in WEIGHTS
    ):
        raise RuntimeError(f"incomplete component bundle in {path}")
    if payload.get("model_weight_sha256") != expected_weight_sha256:
        raise RuntimeError(f"model weight hash mismatch in {path}")
    if payload.get("model_support_sha256") != expected_model_support_sha256:
        raise RuntimeError(f"model support-file hash mismatch in {path}")
    if payload.get("tokenizer_support_sha256") != expected_tokenizer_support_sha256:
        raise RuntimeError(f"tokenizer support-file hash mismatch in {path}")
    if payload.get("judge_support_sha256") != expected_judge_support_sha256:
        raise RuntimeError(f"judge support-file hash mismatch in {path}")
    if payload.get("judge_weight_sha256") != expected_judge_weight_sha256:
        raise RuntimeError(f"judge weight hash mismatch in {path}")
    actual_prompt_sha256 = {
        key: value.get("sha256")
        for key, value in payload.get("prompt_files", {}).items()
    }
    if actual_prompt_sha256 != expected_prompt_sha256:
        raise RuntimeError(f"prompt dependency mismatch in {path}")
    if payload.get("normalisation_policy") != expected_policy:
        raise RuntimeError(f"normalisation policy mismatch in {path}")
    if payload.get("normalisation_policy_fingerprint") != expected_policy_fingerprint:
        raise RuntimeError(f"normalisation policy fingerprint mismatch in {path}")
    return payload


def validate_ladder_artifact(
    path,
    baseline_json,
    parent_model,
    parent_support_sha256,
    parent_weight_sha256,
):
    payload = read_json(path)
    if payload.get("ladder_version") != V2_LADDER_VERSION:
        raise RuntimeError(f"wrong ladder version in {path}")
    if payload.get("corruption_tracks") != V2_CORRUPTION_TRACKS:
        raise RuntimeError(f"wrong corruption tracks in {path}")
    if payload.get("limit") is not None:
        raise RuntimeError(f"limited ladder cannot certify Probe 2: {path}")
    if payload.get("baseline_sha256") != sha256_of_file(baseline_json):
        raise RuntimeError(f"ladder/baseline dependency mismatch in {path}")
    if payload.get("judge_model") != str(parent_model):
        raise RuntimeError(f"ladder judge provenance mismatch in {path}")
    if payload.get("tokenizer_model") != str(parent_model):
        raise RuntimeError(f"ladder tokenizer provenance mismatch in {path}")
    if payload.get("tokenizer_support_sha256") != parent_support_sha256:
        raise RuntimeError(f"ladder tokenizer hash mismatch in {path}")
    if payload.get("judge_support_sha256") != parent_support_sha256:
        raise RuntimeError(f"ladder judge hash mismatch in {path}")
    if payload.get("judge_weight_sha256") != parent_weight_sha256:
        raise RuntimeError(f"ladder judge weight mismatch in {path}")
    if payload.get("judge_parse_complete") is not True:
        raise RuntimeError(f"unparsed ladder judge outputs in {path}")
    if len(payload.get("factual_dropout_order", [])) != 40:
        raise RuntimeError(f"ladder does not contain 40 factual records: {path}")
    return payload


def component_curve_diagnostics(curve, alphas):
    diagnostics = {}
    for key in WEIGHTS:
        raw_values = [curve[alpha]["raw_component_means"][key] for alpha in alphas]
        normalised_values = [
            curve[alpha]["normalised_component_means"][key] for alpha in alphas
        ]
        raw_deltas = [b - a for a, b in zip(raw_values, raw_values[1:])]
        normalised_deltas = [
            b - a for a, b in zip(normalised_values, normalised_values[1:])
        ]
        diagnostics[key] = {
            "raw_seed_means": raw_values,
            "raw_spearman_vs_alpha": spearman(alphas, raw_values),
            "raw_min_delta": min(raw_deltas) if raw_deltas else None,
            "normalised_seed_means": normalised_values,
            "normalised_spearman_vs_alpha": spearman(alphas, normalised_values),
            "normalised_min_delta": (
                min(normalised_deltas) if normalised_deltas else None
            ),
            "directions_by_alpha": {
                str(alpha): curve[alpha]["normalisation_direction_counts"][key]
                for alpha in alphas
            },
        }
    return diagnostics


def write_manifest(root):
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
    temporary.write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    temporary.replace(output)
    return output, len(files)


def main():
    args = parse_args()
    requested_alphas = [float(value) for value in args.alphas.split(",")]
    requested_seeds = [int(value) for value in args.seeds.split(",")]
    if requested_alphas != DEFAULT_ALPHAS:
        raise ValueError(f"certification alphas must be exactly {DEFAULT_ALPHAS}")
    if requested_seeds != DEFAULT_SEEDS:
        raise ValueError(f"certification seeds must be exactly {DEFAULT_SEEDS}")
    if args.beta != 1.0:
        raise ValueError("certification beta must be exactly 1.0")
    if args.max_new_tokens != 256:
        raise ValueError("certification max-new-tokens must be exactly 256")
    if args.cliff_threshold != 20.0:
        raise ValueError("certification cliff-threshold must be exactly 20.0")
    if args.max_bisections != 8:
        raise ValueError("certification max-bisections must be exactly 8")
    if args.skip_ladder:
        raise ValueError("certification cannot use --skip-ladder")
    repo = Path.cwd().resolve()
    parent_path = Path(args.parent_model).expanduser()
    if not parent_path.is_dir():
        raise ValueError(
            "certified Probe 2 requires --parent-model to be an exact local "
            "model snapshot directory, not a mutable Hub model id"
        )
    args.parent_model = str(parent_path.resolve())
    root = Path(args.root).resolve()
    if (root / "MANIFEST.sha256").exists():
        raise RuntimeError(
            f"refusing to modify sealed archive {root}; choose a new versioned root"
        )
    root.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable).absolute()
    log = root / "commands.log"
    summary_path = root / "sweep_summary_bidirectional_v2.json"
    run_config = {
        "parent_model": args.parent_model,
        "beta": args.beta,
        "alphas": [float(value) for value in args.alphas.split(",")],
        "seeds": [int(value) for value in args.seeds.split(",")],
        "batch_size": args.batch_size,
        "max_new_tokens": args.max_new_tokens,
        "cliff_threshold": args.cliff_threshold,
        "max_bisections": args.max_bisections,
        "normalisation_version": NORMALISATION_VERSION,
        "parent_weight_sha256": model_weight_hashes(args.parent_model),
        "parent_support_sha256": support_file_hashes(args.parent_model),
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip(),
        "instrument_file_sha256": {
            path: sha256_of_file(repo / path)
            for path in (
                "scripts/apply_decay_noise.py",
                "scripts/build_corruption_ladder.py",
                "scripts/decay_scalar_normalization.py",
                "scripts/eval_decay_scalar.py",
                "scripts/run_noise_sweep.py",
                "data/decay_scalar_prompts.json",
                "data/rehearsal_capability_prompts.json",
                "data/conversational_survival_generations.json",
            )
        },
    }
    run_config["fingerprint"] = fingerprint(run_config)
    config_path = root / "run_config.json"
    if config_path.exists():
        if read_json(config_path) != run_config:
            raise RuntimeError(
                f"run configuration mismatch in {root}; choose a new versioned root"
            )
    else:
        write_json(config_path, run_config)
    parent_identity = {
        "source_model": args.parent_model,
        "weight_file_sha256": run_config["parent_weight_sha256"],
        "support_file_sha256": run_config["parent_support_sha256"],
    }
    parent_identity["fingerprint"] = fingerprint(parent_identity)
    parent_identity_path = root / "parent_identity.json"
    if parent_identity_path.exists():
        if read_json(parent_identity_path) != parent_identity:
            raise RuntimeError(f"parent identity mismatch in {root}")
    else:
        write_json(parent_identity_path, parent_identity)
    state_path = root / "state.json"
    state = (
        read_json(state_path)
        if state_path.exists()
        else {
            "status": "running",
            "parent_model": args.parent_model,
            "beta": args.beta,
            "alphas": [float(a) for a in args.alphas.split(",")],
            "seeds": [int(s) for s in args.seeds.split(",")],
            "bisections": [],
            "run_config_fingerprint": run_config["fingerprint"],
            "normalisation_version": NORMALISATION_VERSION,
        }
    )
    if state.get("run_config_fingerprint") != run_config["fingerprint"]:
        raise RuntimeError(
            f"state/config mismatch in {root}; choose a new versioned root"
        )
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

    # (a) baseline scalar on the clean parent.
    baseline_json = root / "baseline" / "scalar.json"
    if not baseline_json.exists():
        run_command(
            [
                python,
                "scripts/eval_decay_scalar.py",
                args.parent_model,
                baseline_json,
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
                "--normalisation-policy",
                NORMALISATION_VERSION,
            ],
            log,
            repo,
        )
    validate_scalar_artifact(
        baseline_json,
        expected_model=args.parent_model,
        expected_judge=args.parent_model,
        expected_tokenizer=args.parent_model,
        expected_prompt_sha256=expected_prompt_sha256,
        expected_weight_sha256=run_config["parent_weight_sha256"],
        expected_model_support_sha256=run_config["parent_support_sha256"],
        expected_tokenizer_support_sha256=run_config["parent_support_sha256"],
        expected_judge_support_sha256=run_config["parent_support_sha256"],
        expected_judge_weight_sha256=run_config["parent_weight_sha256"],
    )

    # (b) terminal anchor: alpha = 1.0, seed 0.
    anchor_json = root / "anchor" / "scalar.json"
    anchor_ckpt = root / "anchor" / "checkpoint"
    anchor_sidecar = root / "anchor" / "decay_dose.json"
    if anchor_json.exists() and not anchor_sidecar.exists():
        checkpoint_sidecar = anchor_ckpt / "decay_dose.json"
        if checkpoint_sidecar.exists():
            shutil.copy2(checkpoint_sidecar, anchor_sidecar)
        else:
            raise RuntimeError(
                f"anchor scalar exists without its dose sidecar: {anchor_json}"
            )
    if not anchor_json.exists():
        anchor_complete = (anchor_ckpt / "decay_dose.json").is_file()
        if anchor_ckpt.is_dir() and not anchor_complete:
            print(f"Removing incomplete checkpoint {anchor_ckpt}", flush=True)
            safe_remove_tree(anchor_ckpt, root)
        if not anchor_complete:
            run_command(
                [
                    python,
                    "scripts/apply_decay_noise.py",
                    "--model",
                    args.parent_model,
                    "--alpha",
                    "1.0",
                    "--seed",
                    "0",
                    "--beta",
                    str(args.beta),
                    "--output-dir",
                    anchor_ckpt,
                    "--source-identity-json",
                    parent_identity_path,
                ],
                log,
                repo,
            )
        run_command(
            [
                python,
                "scripts/eval_decay_scalar.py",
                anchor_ckpt,
                anchor_json,
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
                "--normalisation-policy",
                NORMALISATION_VERSION,
            ],
            log,
            repo,
        )
        shutil.copy2(anchor_ckpt / "decay_dose.json", anchor_sidecar)
        safe_remove_tree(anchor_ckpt, root)
    anchor_dose = read_json(anchor_sidecar)
    validate_scalar_artifact(
        anchor_json,
        expected_model=str(anchor_ckpt),
        expected_judge=args.parent_model,
        expected_tokenizer=args.parent_model,
        expected_prompt_sha256=expected_prompt_sha256,
        expected_weight_sha256=anchor_dose["weight_file_sha256"],
        expected_model_support_sha256=anchor_dose["support_file_sha256"],
        expected_tokenizer_support_sha256=run_config["parent_support_sha256"],
        expected_judge_support_sha256=run_config["parent_support_sha256"],
        expected_judge_weight_sha256=run_config["parent_weight_sha256"],
    )
    anchor_expected = {
        "alpha": 1.0,
        "beta": float(args.beta),
        "seed": 0,
        "source_model": args.parent_model,
        "tokenizer_source": args.parent_model,
        "source_identity_fingerprint": parent_identity["fingerprint"],
    }
    if {key: anchor_dose.get(key) for key in anchor_expected} != anchor_expected:
        raise RuntimeError(f"anchor dose provenance mismatch in {anchor_sidecar}")
    if anchor_dose.get("source_identity") != parent_identity:
        raise RuntimeError(f"anchor source identity mismatch in {anchor_sidecar}")

    # (c) corruption ladder from the baseline generations.
    ladder_json = root / "ladder" / "corruption_ladder.json"
    if not args.skip_ladder and not ladder_json.exists():
        run_command(
            [
                python,
                "scripts/build_corruption_ladder.py",
                baseline_json,
                ladder_json,
                "--batch-size",
                str(args.batch_size),
                "--seed",
                "0",
                "--judge-model",
                args.parent_model,
                "--tokenizer-model",
                args.parent_model,
            ],
            log,
            repo,
        )
    if not args.skip_ladder:
        validate_ladder_artifact(
            ladder_json,
            baseline_json,
            args.parent_model,
            run_config["parent_support_sha256"],
            run_config["parent_weight_sha256"],
        )

    # (d) the sweep, plus any bisection doses queued in state.
    def run_dose(alpha, seed):
        tag = f"alpha{alpha:g}_seed{seed}"
        dose_dir = root / "sweep" / tag
        scalar_json = dose_dir / "scalar.json"
        checkpoint = dose_dir / "checkpoint"
        if scalar_json.exists():
            dose_sidecar = dose_dir / "decay_dose.json"
            checkpoint_sidecar = checkpoint / "decay_dose.json"
            if not dose_sidecar.exists() and checkpoint_sidecar.exists():
                shutil.copy2(checkpoint_sidecar, dose_sidecar)
            if not dose_sidecar.exists():
                raise RuntimeError(f"scalar exists without dose sidecar: {dose_dir}")
            sidecar = read_json(dose_sidecar)
            expected = {
                "alpha": float(alpha),
                "beta": float(args.beta),
                "seed": int(seed),
                "source_model": str(args.parent_model),
                "tokenizer_source": str(args.parent_model),
                "source_identity_fingerprint": parent_identity["fingerprint"],
            }
            actual = {key: sidecar.get(key) for key in expected}
            if actual != expected:
                raise RuntimeError(
                    f"dose provenance mismatch in {dose_dir}: "
                    f"expected={expected} actual={actual}"
                )
            if sidecar.get("source_identity") != parent_identity:
                raise RuntimeError(f"dose source identity mismatch in {dose_dir}")
            validate_scalar_artifact(
                scalar_json,
                expected_model=str(checkpoint),
                expected_judge=args.parent_model,
                expected_tokenizer=args.parent_model,
                expected_prompt_sha256=expected_prompt_sha256,
                expected_weight_sha256=sidecar["weight_file_sha256"],
                expected_model_support_sha256=sidecar["support_file_sha256"],
                expected_tokenizer_support_sha256=run_config[
                    "parent_support_sha256"
                ],
                expected_judge_support_sha256=run_config[
                    "parent_support_sha256"
                ],
                expected_judge_weight_sha256=run_config[
                    "parent_weight_sha256"
                ],
                expected_policy=NORMALISATION_VERSION,
                expected_policy_fingerprint=policy_fingerprint,
            )
            if checkpoint.is_dir():
                safe_remove_tree(checkpoint, root)
            return scalar_json
        checkpoint_complete = (checkpoint / "decay_dose.json").is_file()
        if checkpoint.is_dir() and not checkpoint_complete:
            print(f"Removing incomplete checkpoint {checkpoint}", flush=True)
            safe_remove_tree(checkpoint, root)
        if not checkpoint_complete:
            run_command(
                [
                    python,
                    "scripts/apply_decay_noise.py",
                    "--model",
                    args.parent_model,
                    "--alpha",
                    str(alpha),
                    "--seed",
                    str(seed),
                    "--beta",
                    str(args.beta),
                    "--output-dir",
                    checkpoint,
                    "--source-identity-json",
                    parent_identity_path,
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
                str(args.max_new_tokens),
                "--seed",
                "0",
                "--judge-model",
                args.parent_model,
                "--tokenizer-model",
                args.parent_model,
                "--baseline-json",
                baseline_json,
                "--anchor-json",
                anchor_json,
                "--ladder-json",
                ladder_json,
                "--normalisation-policy",
                NORMALISATION_VERSION,
            ],
            log,
            repo,
        )
        shutil.copy2(checkpoint / "decay_dose.json", dose_dir / "decay_dose.json")
        safe_remove_tree(checkpoint, root)
        return run_dose(alpha, seed)

    if args.skip_ladder:
        raise ValueError(
            "--skip-ladder cannot produce a certified scalar: R and D require "
            "the synthetic fraction=1.0 anchor"
        )
    baseline_components, positive_anchor, negative_anchor, anchor_sources = (
        load_bidirectional_anchors(baseline_json, anchor_json, ladder_json)
    )
    policy_fingerprint = bidirectional_policy_fingerprint(
        baseline_components,
        positive_anchor,
        negative_anchor,
        anchor_sources,
    )
    reference_artifact_sha256 = {
        "baseline_scalar": sha256_of_file(baseline_json),
        "terminal_scalar": sha256_of_file(anchor_json),
        "corruption_ladder": sha256_of_file(ladder_json),
    }
    baseline_scalar, baseline_reanalysis = write_scalar_reanalysis(
        baseline_json,
        baseline_components,
        positive_anchor,
        negative_anchor,
        anchor_sources,
    )
    terminal_scalar, terminal_reanalysis = write_scalar_reanalysis(
        anchor_json,
        baseline_components,
        positive_anchor,
        negative_anchor,
        anchor_sources,
    )
    ladder_gate, ladder_component_pass, ladder_gate_pass = read_ladder_gate(
        ladder_json
    )
    if not ladder_gate_pass:
        partial_curve = {}
        for alpha in sorted(state["alphas"]):
            per_seed = []
            for seed in state["seeds"]:
                scalar_path = (
                    root / "sweep" / f"alpha{alpha:g}_seed{seed}" / "scalar.json"
                )
                if not scalar_path.exists():
                    continue
                value, reanalysis = write_scalar_reanalysis(
                    scalar_path,
                    baseline_components,
                    positive_anchor,
                    negative_anchor,
                    anchor_sources,
                )
                per_seed.append(
                    {
                        "seed": seed,
                        "scalar": value,
                        "reanalysis_json": str(reanalysis),
                    }
                )
            if per_seed:
                partial_curve[str(alpha)] = {
                    "per_seed": per_seed,
                    "mean": sum(item["scalar"] for item in per_seed) / len(per_seed),
                    "complete_seed_count": len(per_seed),
                    "planned_seed_count": len(state["seeds"]),
                }
        gates = {
            "failure_stage": "corruption_ladder",
            "sweep_completed": False,
            "spearman_seed_means": None,
            "spearman_gate_pass": None,
            "loo_interpolation_errors": None,
            "max_loo_error": None,
            "loo_gate_pass": None,
            "cliffs_bisected": [],
            "ladder_monotonicity": ladder_gate,
            "ladder_component_pass": ladder_component_pass,
            "ladder_gate_pass": False,
            "primary_verdict": "FAIL",
            "probe2_verdict": "FAIL",
        }
        summary = {
            "parent_model": args.parent_model,
            "beta": args.beta,
            "normalisation_version": NORMALISATION_VERSION,
            "normalisation_policy_fingerprint": policy_fingerprint,
            "baseline_components": baseline_components,
            "terminal_weight_noise_components": read_json(anchor_json)["components"],
            "positive_component_anchor": positive_anchor,
            "negative_component_anchor": negative_anchor,
            "component_anchor_sources": anchor_sources,
            "reference_artifact_sha256": reference_artifact_sha256,
            "baseline_scalar": baseline_scalar,
            "terminal_weight_noise_scalar": terminal_scalar,
            "baseline_reanalysis_json": str(baseline_reanalysis),
            "terminal_reanalysis_json": str(terminal_reanalysis),
            "partial_curve": partial_curve,
            "gates": gates,
            "alpha_at_scalar": {str(target): None for target in (60.0, 65.0, 70.0)},
        }
        write_json(summary_path, summary)
        state["status"] = "failed_ladder_gate"
        state["corrected_summary"] = str(summary_path)
        write_json(state_path, state)
        manifest, manifest_count = write_manifest(root)
        print("gates=" + json.dumps(gates, default=str))
        print("PROBE 2 VERDICT: FAIL (corruption ladder)")
        print(f"Wrote {summary_path}")
        print(f"Sealed {manifest} ({manifest_count} files)")
        return

    def collect_curve(alphas, seeds):
        curve = {}
        for alpha in alphas:
            per_seed = []
            for seed in seeds:
                scalar_path = run_dose(alpha, seed)
                value, reanalysis = write_scalar_reanalysis(
                    scalar_path,
                    baseline_components,
                    positive_anchor,
                    negative_anchor,
                    anchor_sources,
                )
                reanalysis_payload = read_json(reanalysis)
                per_seed.append(
                    {
                        "seed": seed,
                        "scalar": value,
                        "raw_components": reanalysis_payload["components"],
                        "normalised_components": reanalysis_payload[
                            "normalised_components"
                        ],
                        "normalisation_directions": reanalysis_payload[
                            "normalisation_directions"
                        ],
                        "reanalysis_json": str(reanalysis),
                    }
                )
            raw_component_means = {
                key: sum(entry["raw_components"][key] for entry in per_seed)
                / len(per_seed)
                for key in WEIGHTS
            }
            normalised_component_means = {
                key: sum(
                    entry["normalised_components"][key] for entry in per_seed
                )
                / len(per_seed)
                for key in WEIGHTS
            }
            direction_counts = {
                key: {
                    direction: sum(
                        entry["normalisation_directions"][key] == direction
                        for entry in per_seed
                    )
                    for direction in sorted(
                        {
                            entry["normalisation_directions"][key]
                            for entry in per_seed
                        }
                    )
                }
                for key in WEIGHTS
            }
            curve[alpha] = {
                "per_seed": per_seed,
                "mean": sum(entry["scalar"] for entry in per_seed) / len(per_seed),
                "raw_component_means": raw_component_means,
                "normalised_component_means": normalised_component_means,
                "normalisation_direction_counts": direction_counts,
            }
            print(
                f"alpha={alpha:g}: mean scalar "
                f"{curve[alpha]['mean']:.2f} "
                f"({[round(e['scalar'], 2) for e in per_seed]})",
                flush=True,
            )
        return curve

    alphas = sorted(set(state["alphas"] + [b["alpha"] for b in state["bisections"]]))
    seeds = state["seeds"]
    curve = collect_curve(alphas, seeds)

    # Cliff detection above alpha 0.5 with automatic bisection.
    bisection_round = len(state["bisections"])
    while bisection_round < args.max_bisections:
        sorted_alphas = sorted(set(curve) | {1.0})
        new_dose = None
        for low, high in zip(sorted_alphas, sorted_alphas[1:]):
            low_mean = terminal_scalar if low == 1.0 else curve[low]["mean"]
            high_mean = terminal_scalar if high == 1.0 else curve[high]["mean"]
            gap = abs(high_mean - low_mean)
            if max(low, high) > 0.5 and gap > args.cliff_threshold:
                midpoint = round((low + high) / 2, 4)
                if midpoint not in curve:
                    new_dose = {"alpha": midpoint, "between": [low, high], "gap": gap}
                    break
        if new_dose is None:
            break
        print(
            f"CLIFF: {new_dose['gap']:.1f} scalar points between "
            f"alpha {new_dose['between'][0]:g} and {new_dose['between'][1]:g}; "
            f"bisecting at {new_dose['alpha']:g}",
            flush=True,
        )
        state["bisections"].append(new_dose)
        write_json(state_path, state)
        curve.update(collect_curve([new_dose["alpha"]], seeds))
        bisection_round += 1

    cliff_points = sorted(set(curve) | {1.0})
    unresolved_cliffs = []
    for low, high in zip(cliff_points, cliff_points[1:]):
        low_mean = terminal_scalar if low == 1.0 else curve[low]["mean"]
        high_mean = terminal_scalar if high == 1.0 else curve[high]["mean"]
        gap = abs(high_mean - low_mean)
        if max(low, high) > 0.5 and gap > args.cliff_threshold:
            unresolved_cliffs.append(
                {"between": [low, high], "gap": gap, "width": high - low}
            )

    # (e) analysis and gates.
    sorted_alphas = sorted(curve)
    means = [curve[a]["mean"] for a in sorted_alphas]

    gate_alphas = sorted(float(alpha) for alpha in state["alphas"])
    gate_means = [curve[alpha]["mean"] for alpha in gate_alphas]
    rho = spearman(gate_alphas, gate_means)
    component_diagnostics = component_curve_diagnostics(curve, gate_alphas)
    xs = [0.0] + sorted_alphas + [1.0]
    raw_ys = [baseline_scalar] + means + [terminal_scalar]
    ys = isotonic_running_max(raw_ys)
    curve_nondecreasing = all(
        right >= left - 1e-9 for left, right in zip(raw_ys, raw_ys[1:])
    )
    max_isotonic_adjustment = max(
        fitted - raw for fitted, raw in zip(ys, raw_ys)
    )
    loo_errors = {}
    for index, alpha in enumerate(sorted_alphas):
        held_x = alpha
        held_y = means[index]
        rest_x = [x for x in xs if x != held_x]
        rest_y = isotonic_running_max(
            [y for x, y in zip(xs, raw_ys) if x != held_x]
        )
        predicted = pchip_eval(rest_x, rest_y, held_x)
        loo_errors[alpha] = abs(predicted - held_y)
    max_loo = max(loo_errors.values()) if loo_errors else None
    diagnostic_alpha_at_scalar = {
        str(target): invert_curve(xs, ys, target) for target in (60.0, 65.0, 70.0)
    }

    gates = {
        "spearman_seed_means": rho,
        "spearman_gate_pass": rho is not None and rho >= 0.95,
        "curve_strictly_nondecreasing": curve_nondecreasing,
        "isotonic_policy": "running maximum (SYNTHESIS section 4)",
        "isotonic_fitted_means_with_endpoints": ys,
        "max_isotonic_adjustment": max_isotonic_adjustment,
        "loo_interpolation_errors": loo_errors,
        "max_loo_error": max_loo,
        "loo_gate_pass": max_loo is not None and max_loo <= 3.0,
        "cliffs_bisected": state["bisections"],
        "unresolved_cliffs": unresolved_cliffs,
        "cliff_resolution_complete": not unresolved_cliffs,
        "fallback_dial_required": bool(unresolved_cliffs),
        "weight_noise_component_diagnostics": component_diagnostics,
        "ladder_monotonicity": ladder_gate,
        "ladder_component_pass": ladder_component_pass,
        "ladder_gate_pass": ladder_gate_pass,
        "heavy_parent_target_reachable": (
            diagnostic_alpha_at_scalar["65.0"] is not None
        ),
    }
    gates["primary_verdict"] = (
        "PASS"
        if (
            gates["spearman_gate_pass"]
            and gates["loo_gate_pass"]
            and gates["ladder_gate_pass"]
            and gates["heavy_parent_target_reachable"]
        )
        else "FAIL"
    )
    gates["probe2_verdict"] = (
        "INCOMPLETE_PENDING_HEAVY_PARENT"
        if gates["primary_verdict"] == "PASS"
        else "FAIL"
    )
    summary = {
        "certification_scope": "clean_parent_primary_only",
        "parent_model": args.parent_model,
        "beta": args.beta,
        "baseline_components": baseline_components,
        "terminal_weight_noise_components": read_json(anchor_json)["components"],
        "positive_component_anchor": positive_anchor,
        "negative_component_anchor": negative_anchor,
        "component_anchor_sources": anchor_sources,
        "reference_artifact_sha256": reference_artifact_sha256,
        "normalisation_version": NORMALISATION_VERSION,
        "normalisation_policy_fingerprint": policy_fingerprint,
        "baseline_scalar": baseline_scalar,
        "terminal_weight_noise_scalar": terminal_scalar,
        "baseline_reanalysis_json": str(baseline_reanalysis),
        "terminal_reanalysis_json": str(terminal_reanalysis),
        "curve": {
            str(alpha): curve[alpha] for alpha in sorted_alphas
        },
        "gates": gates,
        "alpha_at_scalar": (
            diagnostic_alpha_at_scalar
            if gates["primary_verdict"] == "PASS"
            else {str(target): None for target in (60.0, 65.0, 70.0)}
        ),
        "diagnostic_alpha_at_scalar": diagnostic_alpha_at_scalar,
    }
    write_json(summary_path, summary)
    state["status"] = (
        "passed_primary_pending_heavy"
        if gates["primary_verdict"] == "PASS"
        else "failed_primary"
    )
    if gates["primary_verdict"] != "PASS":
        state["failure_stage"] = "noise_calibration"
    write_json(state_path, state)
    manifest, manifest_count = write_manifest(root)
    print("gates=" + json.dumps(gates, default=str))
    print(f"PROBE 2 PRIMARY VERDICT: {gates['primary_verdict']}")
    print(f"PROBE 2 OVERALL VERDICT: {gates['probe2_verdict']}")
    print(f"Wrote {summary_path}")
    print(f"Sealed {manifest} ({manifest_count} files)")


if __name__ == "__main__":
    main()
