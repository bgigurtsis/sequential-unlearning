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
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_ALPHAS = [0.05, 0.1, 0.2, 0.3, 0.45, 0.6, 0.75, 0.9]
DEFAULT_SEEDS = [0, 1, 2]
WEIGHTS = {"R": 0.25, "D": 0.15, "J": 0.35, "F": 0.25}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-model", default="google/gemma-3-4b-it")
    parser.add_argument("--root", default="derisk/probe2_noise")
    parser.add_argument("--alphas", default=",".join(str(a) for a in DEFAULT_ALPHAS))
    parser.add_argument("--seeds", default=",".join(str(s) for s in DEFAULT_SEEDS))
    parser.add_argument("--beta", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--cliff-threshold", type=float, default=20.0)
    parser.add_argument("--max-bisections", type=int, default=3)
    parser.add_argument("--skip-ladder", action="store_true")
    return parser.parse_args()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
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


def scalar_from_components(components, baseline, anchor):
    total = 0.0
    for key, weight in WEIGHTS.items():
        span = anchor[key] - baseline[key]
        if abs(span) < 1e-6:
            continue
        value = min(1.0, max(0.0, (components[key] - baseline[key]) / span))
        total += weight * value
    return 100.0 * total


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


def main():
    args = parse_args()
    repo = Path.cwd().resolve()
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable).absolute()
    log = root / "commands.log"
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
        }
    )
    write_json(state_path, state)

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
            ],
            log,
            repo,
        )

    # (b) terminal anchor: alpha = 1.0, seed 0.
    anchor_json = root / "anchor" / "scalar.json"
    if not anchor_json.exists():
        anchor_ckpt = root / "anchor" / "checkpoint"
        if not anchor_ckpt.is_dir():
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
            ],
            log,
            repo,
        )
        shutil.copy2(anchor_ckpt / "decay_dose.json", root / "anchor" / "decay_dose.json")
        safe_remove_tree(anchor_ckpt, root)

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
            ],
            log,
            repo,
        )

    # (d) the sweep, plus any bisection doses queued in state.
    def run_dose(alpha, seed):
        tag = f"alpha{alpha:g}_seed{seed}"
        dose_dir = root / "sweep" / tag
        scalar_json = dose_dir / "scalar.json"
        if scalar_json.exists():
            return scalar_json
        checkpoint = dose_dir / "checkpoint"
        if not checkpoint.is_dir():
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
                "--baseline-json",
                baseline_json,
                "--anchor-json",
                anchor_json,
            ],
            log,
            repo,
        )
        shutil.copy2(checkpoint / "decay_dose.json", dose_dir / "decay_dose.json")
        safe_remove_tree(checkpoint, root)
        return scalar_json

    baseline_components = read_json(baseline_json)["components"]
    anchor_components = read_json(anchor_json)["components"]

    def collect_curve(alphas, seeds):
        curve = {}
        for alpha in alphas:
            per_seed = []
            for seed in seeds:
                payload = read_json(run_dose(alpha, seed))
                value = scalar_from_components(
                    payload["components"], baseline_components, anchor_components
                )
                per_seed.append({"seed": seed, "scalar": value})
            curve[alpha] = {
                "per_seed": per_seed,
                "mean": sum(entry["scalar"] for entry in per_seed) / len(per_seed),
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
    bisection_round = 0
    while bisection_round < args.max_bisections:
        sorted_alphas = sorted(curve)
        new_dose = None
        for low, high in zip(sorted_alphas, sorted_alphas[1:]):
            gap = abs(curve[high]["mean"] - curve[low]["mean"])
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

    # (e) analysis and gates.
    sorted_alphas = sorted(curve)
    means = [curve[a]["mean"] for a in sorted_alphas]
    rho = spearman(sorted_alphas, means)

    xs = [0.0] + sorted_alphas + [1.0]
    ys = [0.0] + means + [100.0]
    loo_errors = {}
    for index, alpha in enumerate(sorted_alphas):
        held_x = alpha
        held_y = means[index]
        rest_x = [x for x in xs if x != held_x]
        rest_y = [y for x, y in zip(xs, ys) if x != held_x]
        predicted = pchip_eval(rest_x, rest_y, held_x)
        loo_errors[alpha] = abs(predicted - held_y)
    max_loo = max(loo_errors.values()) if loo_errors else None

    ladder_gate = None
    if not args.skip_ladder:
        ladder = read_json(ladder_json)
        ladder_gate = ladder["monotonicity"]

    gates = {
        "spearman_seed_means": rho,
        "spearman_gate_pass": rho is not None and rho >= 0.95,
        "loo_interpolation_errors": loo_errors,
        "max_loo_error": max_loo,
        "loo_gate_pass": max_loo is not None and max_loo <= 3.0,
        "cliffs_bisected": state["bisections"],
        "ladder_monotonicity": ladder_gate,
    }
    summary = {
        "parent_model": args.parent_model,
        "beta": args.beta,
        "baseline_components": baseline_components,
        "anchor_components": anchor_components,
        "curve": {
            str(alpha): curve[alpha] for alpha in sorted_alphas
        },
        "gates": gates,
        "alpha_at_scalar": {
            str(target): invert_curve(xs, ys, target)
            for target in (60.0, 65.0, 70.0)
        },
    }
    write_json(root / "sweep_summary.json", summary)
    state["status"] = "complete"
    write_json(state_path, state)
    print("gates=" + json.dumps(gates, default=str))
    print(f"Wrote {root / 'sweep_summary.json'}")


if __name__ == "__main__":
    main()
