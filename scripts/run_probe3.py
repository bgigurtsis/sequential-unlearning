"""Probe 3 driver: does the forgetting arm still work late in the lineage?

Reuses probe 2's calibration curve and probe 1's erasure stage.  Dose a
clean parent to the alpha that probe 2 maps to ~60-70% decay scalar, then
run the bounded erasure on a *second* concept (never probe 1's) and ask
whether the semantic bar still falls within the same step budget without
terminal side effects.

Gate (SYNTHESIS section 7, probe 3):
  - the erasure reaches its early-stopping gate within probe 1's step budget
  - the decay scalar does not jump toward ~100 (no terminal side effect)
  - judge verdict ABSENT on core and required-neighbour groups

Control arm: the same erasure repeated in full fp32 compute.  If fp32
succeeds where bf16 failed, the failure is the Zamirai write-back trap, not
plasticity loss - a procedural fix, not a fatal one.  Healing is not part of
this probe's gate, so it is not run.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from decay_scalar_normalization import load_component_anchors, normalise_components


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-model", default="google/gemma-3-4b-it")
    parser.add_argument("--root", default="derisk/probe3_late_erasure")
    parser.add_argument("--concepts", default="data/rehearsal_concepts.json")
    parser.add_argument(
        "--concept-index",
        type=int,
        default=23,
        help="one-based index; must differ from probe 1's (23 = horror_films)",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        help="dose to administer; default reads probe 2's alpha_at_scalar['65.0']",
    )
    parser.add_argument(
        "--sweep-summary",
        default="derisk/probe2_noise/sweep_summary_hybrid_v1.json",
    )
    parser.add_argument(
        "--scalar-baseline", default="derisk/probe2_noise/baseline/scalar.json"
    )
    parser.add_argument(
        "--scalar-anchor", default="derisk/probe2_noise/anchor/scalar.json"
    )
    parser.add_argument(
        "--scalar-ladder",
        default="derisk/probe2_noise/ladder/corruption_ladder.json",
    )
    parser.add_argument("--dose-seed", type=int, default=7)
    parser.add_argument("--forget-steps", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--skip-fp32-control",
        action="store_true",
        help="skip the fp32 control arm (only meaningful if bf16 passed)",
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
    _, scalar = normalise_components(components, baseline, anchor)
    return scalar


def main():
    args = parse_args()
    repo = Path.cwd().resolve()
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable).absolute()
    log = root / "commands.log"

    alpha = args.alpha
    if alpha is None:
        summary = read_json(args.sweep_summary)
        alpha = summary["alpha_at_scalar"].get("65.0")
        if alpha is None:
            raise ValueError(
                "probe 2's curve does not reach 65 scalar points; pass --alpha "
                "explicitly after inspecting sweep_summary.json"
            )
        print(f"Using alpha={alpha} from probe 2's curve (target ~65 scalar points)")

    concept = read_json(args.concepts)[args.concept_index - 1]
    print(f"Probe 3 concept: {concept['id']} ({concept['concept']})")
    baseline, anchor, anchor_sources = load_component_anchors(
        args.scalar_baseline, args.scalar_anchor, args.scalar_ladder
    )

    # 1. dose the parent to the late-lineage decay level.
    dosed = root / "dosed_parent"
    dosed_complete = (dosed / "decay_dose.json").is_file()
    if dosed.is_dir() and not dosed_complete:
        raise RuntimeError(
            f"incomplete dosed parent at {dosed}; preserve it for diagnosis, "
            "then move it aside before resuming"
        )
    if not dosed_complete:
        run_command(
            [
                python,
                "scripts/apply_decay_noise.py",
                "--model",
                args.parent_model,
                "--alpha",
                str(alpha),
                "--seed",
                str(args.dose_seed),
                "--output-dir",
                dosed,
            ],
            log,
            repo,
        )

    # 2. confirm the administered dose actually landed in the target band.
    dosed_scalar = root / "dosed_scalar.json"
    if not dosed_scalar.exists():
        run_command(
            [
                python,
                "scripts/eval_decay_scalar.py",
                dosed,
                dosed_scalar,
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
                "--ladder-json",
                args.scalar_ladder,
            ],
            log,
            repo,
        )
    administered = scalar_of(dosed_scalar, baseline, anchor)
    print(f"Administered decay scalar: {administered:.2f} points")

    # 3. compile the day and generate on-policy answers from the dosed parent.
    day_dir = root / "day"
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
    onpolicy = day_dir / "forget_onpolicy.json"
    if not onpolicy.exists():
        run_command(
            [
                python,
                "scripts/build_onpolicy_forget.py",
                "--model-id",
                dosed,
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

    def erase(name, extra_args):
        adapter_root = root / name
        stop_state = adapter_root / "stop_state.json"
        if not stop_state.exists():
            if adapter_root.exists():
                raise RuntimeError(f"partial erasure needs inspection: {adapter_root}")
            run_command(
                [
                    python,
                    "scripts/train_bounded_forget.py",
                    "--model-id",
                    dosed,
                    "--forget-data",
                    onpolicy,
                    "--output-dir",
                    adapter_root,
                    "--num-steps",
                    str(args.forget_steps),
                    "--seed",
                    str(args.seed),
                ]
                + extra_args,
                log,
                repo,
            )
        return read_json(stop_state)

    # 4. the bf16-base arm (the real protocol).
    bf16_state = erase("forget_adapter_bf16", [])

    merged = root / "forget_model_bf16"
    if not merged.is_dir():
        run_command(
            [python, "scripts/merge.py", bf16_state["final_adapter"], merged, dosed],
            log,
            repo,
        )

    # 5. post-erasure battery on the dosed-then-erased checkpoint.
    post = root / "post_forget"
    post.mkdir(parents=True, exist_ok=True)
    rehearsal = post / "rehearsal_eval.json"
    if not rehearsal.exists():
        run_command(
            [
                python,
                "scripts/eval_rehearsal_checkpoint.py",
                merged,
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
    post_scalar = post / "scalar.json"
    if not post_scalar.exists():
        run_command(
            [
                python,
                "scripts/eval_decay_scalar.py",
                merged,
                post_scalar,
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
                "--ladder-json",
                args.scalar_ladder,
            ],
            log,
            repo,
        )
    judgement = post / "judgement.json"
    if not judgement.exists():
        scratch = post / "judge_scratch"
        step_dir = scratch / "step01_probe"
        step_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rehearsal, step_dir / "post_eval.json")
        run_command(
            [python, "scripts/judge_rehearsal_generations.py", "--root", scratch],
            log,
            repo,
        )
        shutil.copy2(step_dir / "semantic_judgement.json", judgement)

    verdict = read_json(judgement)
    after = scalar_of(post_scalar, baseline, anchor)
    semantic_pass = (
        verdict["core_unlearned"] and verdict["required_neighbours_unlearned"]
    )
    reached_gate = bf16_state["stop_reason"] != "step_budget_exhausted"

    gates = {
        "requested_alpha": alpha,
        "administered_scalar": administered,
        "post_erasure_scalar": after,
        "scalar_jump_from_erasure": after - administered,
        "no_terminal_side_effect": after < 95.0,
        "erasure_reached_gate": reached_gate,
        "stop_reason": bf16_state["stop_reason"],
        "stopped_at_step": bf16_state["stopped_at_step"],
        "step_budget": args.forget_steps,
        "semantic_bar_pass": semantic_pass,
        "group_verdicts": {
            group_id: result["verdict"]
            for group_id, result in verdict["groups"].items()
        },
        "selected_component_anchor": anchor,
        "component_anchor_sources": anchor_sources,
    }
    gates["probe3_verdict"] = (
        "PASS"
        if (semantic_pass and reached_gate and gates["no_terminal_side_effect"])
        else "FAIL"
    )

    # 6. the fp32 control arm - only informative when the bf16 arm failed.
    if not args.skip_fp32_control and gates["probe3_verdict"] == "FAIL":
        print(
            "\nbf16 arm failed; running the fp32 control to separate the "
            "Zamirai write-back trap from genuine plasticity loss.",
            flush=True,
        )
        fp32_state = erase("forget_adapter_fp32", ["--fp32-base"])
        gates["fp32_control"] = {
            "stop_reason": fp32_state["stop_reason"],
            "stopped_at_step": fp32_state["stopped_at_step"],
            "reached_gate": fp32_state["stop_reason"] != "step_budget_exhausted",
        }
        gates["failure_is_precision_artefact"] = gates["fp32_control"]["reached_gate"]

    summary = {
        "concept": {"index": args.concept_index, **concept},
        "parent_model": args.parent_model,
        "dose": {"alpha": alpha, "seed": args.dose_seed, "model": str(dosed)},
        "gates": gates,
    }
    write_json(root / "probe3_summary.json", summary)
    print("\n" + "=" * 72)
    print("gates=" + json.dumps(gates, indent=2, default=str))
    print(f"PROBE 3 VERDICT: {gates['probe3_verdict']}")
    print(f"Wrote {root / 'probe3_summary.json'}")


if __name__ == "__main__":
    main()
