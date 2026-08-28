"""Render the accumulated rehearsal results and verbatim examples to Markdown."""

import argparse
import json
from pathlib import Path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verdict(value):
    return {True: "yes", False: "no", None: "pending"}[value]


def compact(text):
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def blockquote(text):
    lines = str(text).strip().splitlines() or [""]
    return "\n".join(f"> {line}" for line in lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="rehearsal/sequential_30")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve() if args.output else root / "REPORT.md"
    day_dirs = sorted(path.parent for path in root.glob("step*_*/summary.json"))
    if not day_dirs:
        raise FileNotFoundError(f"no completed summaries under {root}")

    records = []
    for day_dir in day_dirs:
        summary = read_json(day_dir / "summary.json")
        judgement_path = day_dir / "semantic_judgement.json"
        judgement = read_json(judgement_path) if judgement_path.exists() else None
        records.append((day_dir, summary, judgement))

    lines = [
        "# Sequential unlearning rehearsal",
        "",
        "The selected `day01_sea_run17_step030_drop8` checkpoint is baseline 0. "
        "Each numbered row is one additional intervention trained and merged into "
        "the immediately preceding checkpoint.",
        "",
        "Semantic verdicts come from the frozen clean-model rubric over three held-out "
        "responses per group. They are diagnostic and should be checked against the "
        "verbatim outputs below. `pending` means the judge has not run yet.",
        "",
        "| Step | Concept | Core unlearned | Neighbours unlearned | Capability tasks | Responsive | PPL | PPL / baseline |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, summary, judgement in records:
        core = judgement["core_unlearned"] if judgement else None
        neighbours = judgement["required_neighbours_unlearned"] if judgement else None
        lines.append(
            f"| {summary['rehearsal_step']} | {compact(summary['concept'])} | "
            f"{verdict(core)} | {verdict(neighbours)} | "
            f"{summary['capability_task_passes']}/{summary['capability_total']} | "
            f"{summary['capability_responsive']}/{summary['capability_total']} | "
            f"{summary['perplexity']:.2f} | "
            f"{summary['perplexity_ratio_to_baseline']:.2f}× |"
        )

    for day_dir, summary, judgement in records:
        lines.extend(
            [
                "",
                f"## Step {summary['rehearsal_step']:02d}: {summary['concept']}",
                "",
                f"Parent: `{summary['parent']}`  ",
                f"Checkpoint: `{summary['model']}`",
                "",
                "| Group | Role | Semantic verdict | Cloze before | Cloze after | Remaining ratio | Surface-free outputs |",
                "|---|---|---|---:|---:|---:|---:|",
            ]
        )
        for group_id, group in summary["groups"].items():
            semantic = (
                judgement["groups"][group_id]["verdict"].lower()
                if judgement
                else "pending"
            )
            lines.append(
                f"| {compact(group['label'])} | {group['role']} | {semantic} | "
                f"{group['pre_cloze_mean']:.4f} | {group['post_cloze_mean']:.4f} | "
                f"{group['cloze_ratio']:.3f} | "
                f"{group['generations_without_surface_terms']}/{group['generation_total']} |"
            )
        lines.extend(
            [
                "",
                "Degradation: "
                f"{summary['capability_task_passes']}/{summary['capability_total']} "
                "capability tasks passed; "
                f"{summary['capability_responsive']}/{summary['capability_total']} "
                "responses remained non-degenerate; "
                f"perplexity {summary['perplexity']:.2f} "
                f"({summary['perplexity_ratio_to_baseline']:.2f}× baseline).",
                "",
                "### Concept and neighbour output examples",
                "",
            ]
        )
        for example in summary["concept_output_examples"]:
            lines.extend(
                [
                    f"**{example['label']} — prompt**",
                    "",
                    blockquote(example["prompt"]),
                    "",
                    "**Model output**",
                    "",
                    blockquote(example["generation"]),
                    "",
                ]
            )
        lines.extend(["### Capability output examples", ""])
        for example in summary["capability_output_examples"]:
            status = "pass" if example["task_pass"] else "fail"
            lines.extend(
                [
                    f"**{example['id']} ({status}) — prompt**",
                    "",
                    blockquote(example["prompt"]),
                    "",
                    "**Model output**",
                    "",
                    blockquote(example["generation"]),
                    "",
                ]
            )
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote {output} with {len(records)} rehearsal steps")


if __name__ == "__main__":
    main()
