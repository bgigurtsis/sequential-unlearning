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
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


WEIGHTS = {"R": 0.25, "D": 0.15, "J": 0.35, "F": 0.25}


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
        "--scalar-baseline",
        default="derisk/probe2_noise/baseline/scalar.json",
        help="probe 2 anchor 0, for normalising the decay scalar",
    )
    parser.add_argument(
        "--scalar-anchor",
        default="derisk/probe2_noise/anchor/scalar.json",
        help="probe 2 anchor 1 (alpha=1.0), for normalising the decay scalar",
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
        help="skip decay-scalar stages (use when probe 2 anchors do not exist yet)",
    )
    return parser.parse_args()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
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
        code = process.wait()
        log.write(f"\nexit={code} duration_seconds={time.time() - started:.1f}\n")
    if code:
        raise subprocess.CalledProcessError(code, command)


def scalar_of(path, baseline, anchor):
    components = read_json(path)["components"]
    total = 0.0
    for key, weight in WEIGHTS.items():
        span = anchor[key] - baseline[key]
        if abs(span) < 1e-6:
            continue
        value = min(1.0, max(0.0, (components[key] - baseline[key]) / span))
        total += weight * value
    return 100.0 * total


def main():
    args = parse_args()
    repo = Path.cwd().resolve()
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable).absolute()
    log = root / "commands.log"
    day_dir = root / "day"
    concept = read_json(args.concepts)[args.concept_index - 1]
    print(f"Probe 1 concept: {concept['id']} ({concept['concept']})")

    use_scalar = not args.skip_scalar
    if use_scalar and not (
        Path(args.scalar_baseline).is_file() and Path(args.scalar_anchor).is_file()
    ):
        raise FileNotFoundError(
            "probe 2 baseline/anchor scalars are required to normalise the "
            "decay scalar; finish probe 2 stages (a) and (b) first, or pass "
            "--skip-scalar to run the semantic gates alone"
        )

    # 1. compile the day.
    if not (day_dir / "probes_conjugate.json").exists():
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

    # 2. healing corpus.
    if not Path(args.heal_corpus).is_file():
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

    def eval_stage(name, model_path):
        """Rehearsal eval + conjugate probes + scalar + drift for one checkpoint."""
        stage = root / name
        stage.mkdir(parents=True, exist_ok=True)
        rehearsal = stage / "rehearsal_eval.json"
        if not rehearsal.exists():
            run_command(
                [
                    python,
                    "scripts/eval_rehearsal_checkpoint.py",
                    model_path,
                    rehearsal,
                    "--day-dir",
                    day_dir,
                    "--max-new-tokens",
                    "64",
                    "--skip-cumulative",
                ],
                log,
                repo,
            )
        conjugate = stage / "conjugate_eval.json"
        if not conjugate.exists():
            # Same evaluator, pointed at a day dir whose probes.json is the
            # conjugate set, so the judge downstream sees the identical shape.
            conjugate_day = root / "day_conjugate"
            if not (conjugate_day / "probes.json").exists():
                conjugate_day.mkdir(parents=True, exist_ok=True)
                for filename in ("concept.json", "clozes.json"):
                    shutil.copy2(day_dir / filename, conjugate_day / filename)
                shutil.copy2(
                    day_dir / "probes_conjugate.json", conjugate_day / "probes.json"
                )
            run_command(
                [
                    python,
                    "scripts/eval_rehearsal_checkpoint.py",
                    model_path,
                    conjugate,
                    "--day-dir",
                    conjugate_day,
                    "--max-new-tokens",
                    "64",
                    "--skip-capability",
                    "--skip-cumulative",
                    "--skip-perplexity",
                ],
                log,
                repo,
            )
        drift = stage / "drift.json"
        if not drift.exists():
            run_command(
                [
                    python,
                    "scripts/eval_drift.py",
                    model_path,
                    drift,
                    "--batch-size",
                    str(args.batch_size),
                ],
                log,
                repo,
            )
        scalar = stage / "scalar.json"
        if use_scalar and not scalar.exists():
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
                    "--baseline-json",
                    args.scalar_baseline,
                    "--anchor-json",
                    args.scalar_anchor,
                ],
                log,
                repo,
            )
        return stage

    def judge_stage(stage):
        """Run the frozen semantic judge over one stage's two eval files."""
        for source, output in (
            ("rehearsal_eval.json", "judgement.json"),
            ("conjugate_eval.json", "judgement_conjugate.json"),
        ):
            target = stage / output
            if target.exists():
                continue
            # judge_rehearsal_generations.py globs step*_*/post_eval.json, so
            # present the eval under that layout in a scratch directory.
            scratch = stage / f"judge_{Path(source).stem}"
            step_dir = scratch / "step01_probe"
            step_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stage / source, step_dir / "post_eval.json")
            run_command(
                [
                    python,
                    "scripts/judge_rehearsal_generations.py",
                    "--root",
                    scratch,
                ],
                log,
                repo,
            )
            shutil.copy2(step_dir / "semantic_judgement.json", target)

    # 3. pre-eval the parent.
    eval_stage("pre", args.parent_model)

    # 4. on-policy forget answers.
    onpolicy = day_dir / "forget_onpolicy.json"
    if not onpolicy.exists():
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

    # 5. bounded-objective erasure.
    adapter_root = root / "forget_adapter"
    stop_state = adapter_root / "stop_state.json"
    if not stop_state.exists():
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
            ],
            log,
            repo,
        )

    # 6. merge the erasure adapter.
    forget_model = root / "forget_model"
    if not forget_model.is_dir():
        run_command(
            [
                python,
                "scripts/merge.py",
                read_json(stop_state)["final_adapter"],
                forget_model,
                args.parent_model,
            ],
            log,
            repo,
        )

    # 7. post-forget battery.
    post_forget = eval_stage("post_forget", forget_model)
    judge_stage(post_forget)

    # 8-9. heal, then merge.
    heal_root = root / "heal_adapter"
    heal_final = heal_root / f"step{args.heal_steps:03d}"
    if not heal_final.is_dir():
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
    heal_model = root / "heal_model"
    if not heal_model.is_dir():
        run_command(
            [python, "scripts/merge.py", heal_final, heal_model, forget_model],
            log,
            repo,
        )

    # 10. post-heal battery.
    post_heal = eval_stage("post_heal", heal_model)
    judge_stage(post_heal)

    # 11. gates.
    def judged(stage, filename):
        payload = read_json(stage / filename)
        return {
            "core_unlearned": payload["core_unlearned"],
            "required_neighbours_unlearned": payload["required_neighbours_unlearned"],
            "groups": {
                group_id: result["verdict"]
                for group_id, result in payload["groups"].items()
            },
        }

    forget_judgement = judged(post_forget, "judgement.json")
    forget_conjugate = judged(post_forget, "judgement_conjugate.json")
    heal_judgement = judged(post_heal, "judgement.json")
    heal_conjugate = judged(post_heal, "judgement_conjugate.json")

    gates = {
        "forgetting_pass": (
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
    }

    drift_values = {
        name: read_json(root / name / "drift.json")[
            "pca_drift_percent_of_reference_spread"
        ]
        for name in ("pre", "post_forget", "post_heal")
    }
    gates["pca_drift"] = drift_values
    gates["drift_reversible_pass"] = drift_values["post_heal"] <= 20.0

    if use_scalar:
        baseline = read_json(args.scalar_baseline)["components"]
        anchor = read_json(args.scalar_anchor)["components"]
        scalars = {
            name: scalar_of(root / name / "scalar.json", baseline, anchor)
            for name in ("pre", "post_forget", "post_heal")
        }
        collateral = scalars["post_forget"] - scalars["pre"]
        recovered = scalars["post_forget"] - scalars["post_heal"]
        fraction = recovered / collateral if abs(collateral) > 1e-9 else None
        leakage = scalars["post_heal"] - scalars["pre"]
        gates.update(
            {
                "scalars": scalars,
                "collateral_from_forgetting": collateral,
                "recovered_by_healing": recovered,
                "repair_fraction": fraction,
                "repair_pass": fraction is not None and fraction >= 0.5,
                "leakage_scalar_points": leakage,
                "leakage_within_budget": leakage <= 1.0,
            }
        )

    required = ["forgetting_pass", "persistence_after_heal_pass", "drift_reversible_pass"]
    if use_scalar:
        required.append("repair_pass")
    gates["probe1_verdict"] = (
        "PASS" if all(gates.get(key) for key in required) else "FAIL"
    )
    gates["required_gates"] = required

    summary = {
        "concept": {"index": args.concept_index, **concept},
        "parent_model": args.parent_model,
        "forget_stop_state": read_json(stop_state),
        "models": {
            "forget_model": str(forget_model),
            "heal_model": str(heal_model),
        },
        "gates": gates,
    }
    write_json(root / "probe1_summary.json", summary)
    print("\n" + "=" * 72)
    print("gates=" + json.dumps(gates, indent=2, default=str))
    print(f"PROBE 1 VERDICT: {gates['probe1_verdict']}")
    print(f"Wrote {root / 'probe1_summary.json'}")


if __name__ == "__main__":
    main()
