"""Run and resume the 30-concept sequential-unlearning rehearsal on one GPU.

The selected Day 1 sea checkpoint is baseline zero.  For each compiled concept
this runner generates on-policy forget answers from the current parent, trains
the fixed grouped Adaptive RMU intervention, merges the adapter into that exact
parent, applies the fixed non-stacked sparse row edit, evaluates the resulting
checkpoint, and then makes it the next parent.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-model", required=True)
    parser.add_argument("--root", default="rehearsal/sequential_30")
    parser.add_argument("--concepts", default="data/rehearsal_concepts.json")
    parser.add_argument("--retain-data", default="data/retain.json")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=30)
    parser.add_argument("--target-drop", type=float, default=8.0)
    parser.add_argument("--keep-unprojected", action="store_true")
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument(
        "--terminal-responsive-floor",
        type=int,
        default=4,
        help="stop if no more than this many of 24 capability prompts respond",
    )
    return parser.parse_args()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
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
        duration = time.time() - started
        log.write(f"\nexit={return_code} duration_seconds={duration:.1f}\n")
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)


def safe_remove_tree(path, rehearsal_root):
    resolved = Path(path).resolve()
    root = Path(rehearsal_root).resolve()
    if root not in resolved.parents or resolved == root:
        raise RuntimeError(f"refusing to remove path outside rehearsal root: {resolved}")
    if resolved.is_dir():
        print(f"Removing reproducible intermediate {resolved}", flush=True)
        shutil.rmtree(resolved)


def main():
    args = parse_args()
    repo = Path.cwd().resolve()
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    parent = Path(args.parent_model).resolve()
    concepts_path = Path(args.concepts).resolve()
    retain_path = Path(args.retain_data).resolve()
    if not parent.is_dir():
        raise FileNotFoundError(f"parent checkpoint not found: {parent}")
    if not retain_path.is_file():
        raise FileNotFoundError(f"retain corpus not found: {retain_path}")
    concepts = read_json(concepts_path)
    if len(concepts) != 30:
        raise ValueError("the rehearsal requires exactly 30 frozen concepts")
    if not 1 <= args.start <= args.end <= len(concepts):
        raise ValueError("invalid start/end range")

    # Preserve the virtual-environment entry point.  Resolving this symlink on
    # the EC2 AMI yields /usr/bin/python3.12, outside the venv and without the
    # CUDA/PyTorch packages used by the experiment.
    python = Path(sys.executable).absolute()
    state_path = root / "state.json"
    state = read_json(state_path) if state_path.exists() else {
        "status": "running",
        "initial_parent": str(parent),
        "concepts": str(concepts_path),
        "completed": [],
        "baseline_capability": None,
    }

    for index in range(args.start, args.end + 1):
        concept = concepts[index - 1]
        day_dir = root / f"step{index:02d}_{concept['id']}"
        day_dir.mkdir(parents=True, exist_ok=True)
        model_dir = day_dir / "model"
        unprojected_dir = day_dir / "unprojected_model"
        adapter_root = day_dir / "adapter"
        adapter_snapshot = adapter_root / "step030"
        pre_eval = day_dir / "pre_eval.json"
        post_eval = day_dir / "post_eval.json"
        day_summary = day_dir / "summary.json"
        command_log = day_dir / "commands.log"

        if model_dir.is_dir() and post_eval.is_file() and day_summary.is_file():
            print(f"Resuming after completed step {index:02d}: {model_dir}")
            parent = model_dir.resolve()
            if index not in state["completed"]:
                state["completed"].append(index)
                write_json(state_path, state)
            continue

        print(
            f"\n{'=' * 72}\nSTEP {index:02d}/30: {concept['concept']}\n"
            f"parent={parent}\n{'=' * 72}",
            flush=True,
        )
        if not (day_dir / "concept.json").exists():
            run_command(
                [
                    python,
                    "scripts/build_rehearsal_day.py",
                    str(index),
                    day_dir,
                    "--concepts",
                    concepts_path,
                ],
                command_log,
                repo,
            )

        if not pre_eval.exists():
            command = [
                python,
                "scripts/eval_rehearsal_checkpoint.py",
                parent,
                pre_eval,
                "--day-dir",
                day_dir,
                "--max-new-tokens",
                str(args.max_new_tokens),
                "--skip-cumulative",
            ]
            if index != args.start:
                command.extend(["--skip-capability", "--skip-perplexity"])
            run_command(command, command_log, repo)

        onpolicy = day_dir / "forget_onpolicy.json"
        if not onpolicy.exists():
            run_command(
                [
                    python,
                    "scripts/build_onpolicy_forget.py",
                    "--model-id",
                    parent,
                    "--input",
                    day_dir / "forget_prompts.json",
                    "--output",
                    onpolicy,
                    "--batch-size",
                    "4",
                    "--max-new-tokens",
                    str(args.max_new_tokens),
                ],
                command_log,
                repo,
            )

        if not adapter_snapshot.is_dir():
            if adapter_root.exists():
                raise RuntimeError(
                    f"partial adapter directory needs inspection before resume: {adapter_root}"
                )
            run_command(
                [
                    python,
                    "scripts/train_rmu_multilayer.py",
                    "--model-id",
                    parent,
                    "--forget-data",
                    onpolicy,
                    "--forget-group-map",
                    day_dir / "forget_group_map.json",
                    "--forget-per-group",
                    "2",
                    "--retain-data",
                    retain_path,
                    "--output-dir",
                    adapter_root,
                    "--steer-layers",
                    "16,20,24",
                    "--train-layer-lo",
                    "14",
                    "--train-layer-hi",
                    "24",
                    "--rank",
                    "32",
                    "--lora-alpha",
                    "64",
                    "--norm-mult",
                    "1.0",
                    "--retain-weight",
                    "100.0",
                    "--learning-rate",
                    "1e-4",
                    "--num-steps",
                    "30",
                    "--save-every",
                    "30",
                    "--batch-forget",
                    "8",
                    "--batch-retain",
                    "2",
                    "--max-length",
                    "256",
                    "--audit-size",
                    "16",
                    "--seed",
                    "0",
                ],
                command_log,
                repo,
            )

        if not unprojected_dir.is_dir() and not model_dir.is_dir():
            run_command(
                [
                    python,
                    "scripts/merge.py",
                    adapter_snapshot,
                    unprojected_dir,
                    parent,
                ],
                command_log,
                repo,
            )

        if not model_dir.is_dir():
            run_command(
                [
                    python,
                    "scripts/edit_concept_rows.py",
                    unprojected_dir,
                    model_dir,
                    "--cloze-data",
                    day_dir / "clozes.json",
                    "--target-drop",
                    str(args.target_drop),
                    "--single-token-only",
                ],
                command_log,
                repo,
            )

        if not post_eval.exists():
            run_command(
                [
                    python,
                    "scripts/eval_rehearsal_checkpoint.py",
                    model_dir,
                    post_eval,
                    "--day-dir",
                    day_dir,
                    "--cumulative-root",
                    root,
                    "--max-new-tokens",
                    str(args.max_new_tokens),
                ],
                command_log,
                repo,
            )

        pre_payload = read_json(pre_eval)
        post_payload = read_json(post_eval)
        pre = pre_payload["summary"]
        post = post_payload["summary"]
        baseline_capability = state.get("baseline_capability")
        if baseline_capability is None:
            baseline_capability = {
                "responsive": pre["capability_responsive"],
                "task_passes": pre["capability_task_passes"],
                "perplexity": pre["perplexity"],
            }
            state["baseline_capability"] = baseline_capability
        pre_cloze = pre["current_cloze_mean"]
        post_cloze = post["current_cloze_mean"]
        cloze_ratio = post_cloze / pre_cloze if pre_cloze > 0 else None
        provisional_forgetting = (
            cloze_ratio is not None
            and cloze_ratio <= 0.2
            and post["current_without_surface_terms"] >= 9
        )
        group_results = {}
        for group in concept["groups"]:
            group_id = group["id"]
            pre_group_cloze = pre["current_cloze_by_group"][group_id]
            post_group_cloze = post["current_cloze_by_group"][group_id]
            group_ratio = (
                post_group_cloze / pre_group_cloze
                if pre_group_cloze > 0
                else None
            )
            generation_stats = post["current_generation_by_group"][group_id]
            group_results[group_id] = {
                "label": group["label"],
                "role": "core" if group_id == "core" else "required_neighbour",
                "pre_cloze_mean": pre_group_cloze,
                "post_cloze_mean": post_group_cloze,
                "cloze_ratio": group_ratio,
                "generation_total": generation_stats["total"],
                "generation_responsive": generation_stats["responsive"],
                "generations_without_surface_terms": generation_stats[
                    "without_surface_terms"
                ],
                "provisional_unlearned": (
                    group_ratio is not None
                    and group_ratio <= 0.2
                    and generation_stats["without_surface_terms"] >= 2
                ),
            }
        core_pass = group_results["core"]["provisional_unlearned"]
        neighbour_pass = all(
            result["provisional_unlearned"]
            for group_id, result in group_results.items()
            if group_id != "core"
        )
        capability_examples = []
        failed_capabilities = [
            result for result in post_payload["capability"] if not result["task_pass"]
        ]
        responsive_capabilities = [
            result for result in post_payload["capability"] if result["task_pass"]
        ]
        for result in (failed_capabilities + responsive_capabilities)[:4]:
            capability_examples.append(
                {
                    "id": result["id"],
                    "prompt": result["prompt"],
                    "generation": result["generation"],
                    "task_pass": result["task_pass"],
                    "responsive": result["responsive"],
                }
            )
        concept_examples = []
        for group in concept["groups"]:
            result = next(
                record
                for record in post_payload["current_generations"]
                if record["group"] == group["id"]
            )
            concept_examples.append(
                {
                    "group": group["id"],
                    "label": group["label"],
                    "prompt": result["prompt"],
                    "generation": result["generation"],
                    "surface_hits": result.get("surface_hits", []),
                    "responsive": result["responsive"],
                }
            )
        summary = {
            "rehearsal_step": index,
            "concept_id": concept["id"],
            "concept": concept["concept"],
            "parent": str(parent),
            "model": str(model_dir.resolve()),
            "pre_cloze_mean": pre_cloze,
            "post_cloze_mean": post_cloze,
            "cloze_ratio": cloze_ratio,
            "post_generations_without_surface_terms": post[
                "current_without_surface_terms"
            ],
            "post_generation_total": post["current_generations"],
            "provisional_forgetting_pass": provisional_forgetting,
            "provisional_core_unlearned": core_pass,
            "provisional_required_neighbours_unlearned": neighbour_pass,
            "groups": group_results,
            "capability_responsive": post["capability_responsive"],
            "capability_total": post["capability_total"],
            "capability_task_passes": post["capability_task_passes"],
            "baseline_capability": baseline_capability,
            "capability_responsive_ratio_to_baseline": (
                post["capability_responsive"] / baseline_capability["responsive"]
                if baseline_capability["responsive"]
                else None
            ),
            "capability_task_ratio_to_baseline": (
                post["capability_task_passes"] / baseline_capability["task_passes"]
                if baseline_capability["task_passes"]
                else None
            ),
            "perplexity": post["perplexity"],
            "perplexity_ratio_to_baseline": (
                post["perplexity"] / baseline_capability["perplexity"]
                if baseline_capability["perplexity"]
                else None
            ),
            "sea_cloze_mean": post["sea_cloze_mean"],
            "sea_generation_without_surface_terms": post[
                "sea_generation_without_surface_terms"
            ],
            "cumulative_generation_probes": post[
                "cumulative_generation_probes"
            ],
            "cumulative_without_surface_terms": post[
                "cumulative_without_surface_terms"
            ],
            "automatic_semantic_judgement": "diagnostic_only_requires_review",
            "concept_output_examples": concept_examples,
            "capability_output_examples": capability_examples,
        }
        write_json(day_summary, summary)
        if not args.keep_unprojected:
            safe_remove_tree(unprojected_dir, root)

        parent = model_dir.resolve()
        if index not in state["completed"]:
            state["completed"].append(index)
        state["current_parent"] = str(parent)
        state["last_summary"] = summary
        write_json(state_path, state)
        print("day_summary=" + json.dumps(summary, sort_keys=True), flush=True)

        if post["capability_responsive"] <= args.terminal_responsive_floor:
            state["status"] = "stopped_terminal_floor"
            state["stopped_after"] = index
            write_json(state_path, state)
            print(
                f"Stopping after step {index}: capability responsiveness "
                f"{post['capability_responsive']}/{post['capability_total']} is at or "
                f"below floor {args.terminal_responsive_floor}.",
                flush=True,
            )
            return

    state["status"] = "complete"
    state["current_parent"] = str(parent)
    write_json(state_path, state)
    print(f"Sequential rehearsal complete. Final checkpoint: {parent}", flush=True)


if __name__ == "__main__":
    main()
