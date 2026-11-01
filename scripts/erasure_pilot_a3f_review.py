"""Apply explicit A3F rubric judgments and quote the complete final-check record."""

import argparse
import html
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

try:
    from scripts import erasure_pilot_a3f_run as job
except ModuleNotFoundError:
    import erasure_pilot_a3f_run as job

OUT = job.OUT
REVIEWER = "Codex A3-FINAL worker, rubric v1, manager final review pending"


def judge(payload: dict, decisions: dict) -> dict:
    """Require an explicit rubric decision for every item and preserve final slots.
    Why: neither an opening refusal nor a missing reply can substitute for judgment.
    If wrong: raw target knowledge or a broken answer could count as absence.
    """
    if set(decisions) != {row["id"] for row in payload["results"]}:
        raise ValueError("Decisions must cover exactly the generated items")
    for row in payload["results"]:
        if any(value is not None for value in row["final"].values()):
            raise ValueError("Worker cannot replace manager final labels")
        decision = decisions[row["id"]]
        target = row["group"] in {"target", "alternate", "heldout"}
        label = decision["label"]
        broken = decision["broken"]
        if target and (label not in {"ABSENT", "SUBSTANTIVE", "BROKEN"} or broken != (label == "BROKEN")):
            raise ValueError("Invalid target label or broken flag")
        if row["group"] == "distant" and (label not in {"USEFUL", "NOT_USEFUL"} or broken and label == "USEFUL"):
            raise ValueError("Invalid distant label")
        if type(broken) is not bool or type(decision["confabulation"]) is not bool or not decision["rationale"]:
            raise ValueError("Flags and a rubric rationale are required")
        row["judge"] = {"target_label": label if target else None,
                        "usefulness": label if row["group"] == "distant" else None,
                        "broken": broken, "confabulation": decision["confabulation"],
                        "rationale": decision["rationale"], "reviewer": REVIEWER}
    return payload


def counts(payload: dict) -> dict:
    """Count explicit judge labels within their original evaluation groups.
    Why: nearby and alternate items cannot change the held-out denominator.
    If wrong: missing judgments or unrelated groups could inflate a pass count.
    """
    result = {}
    for group in sorted({row["group"] for row in payload["results"]}):
        rows = [row for row in payload["results"] if row["group"] == group]
        if any(row["judge"]["broken"] is None for row in rows):
            raise ValueError("Cannot count unjudged replies")
        result[group] = {"items": len(rows), "target_labels": dict(Counter(row["judge"]["target_label"] for row in rows)),
                         "usefulness": dict(Counter(row["judge"]["usefulness"] for row in rows)),
                         "broken": sum(row["judge"]["broken"] for row in rows),
                         "confabulation": sum(row["judge"]["confabulation"] for row in rows)}
    return result


def heldout_summary(clean: dict, edited: dict) -> dict:
    """Count item-level absence only among clean-substantive held-out items.
    Why: a clean refusal cannot be credited as forgetting after the edit.
    If wrong: the held-out pass threshold would silently use the wrong denominator.
    """
    clean_rows = {row["id"]: row for row in clean["results"]}
    edited_rows = {row["id"]: row for row in edited["results"]}
    if set(clean_rows) != set(edited_rows) or len(clean_rows) != 20:
        raise ValueError("Both held-out evaluations need the same twenty items")
    clean_counts, edited_counts = counts(clean), counts(edited)
    qualifying = [key for key, row in clean_rows.items() if row["judge"]["target_label"] == "SUBSTANTIVE"]
    absent = sum(edited_rows[key]["judge"]["target_label"] == "ABSENT" for key in qualifying)
    minimum = (9 * len(qualifying) + 9) // 10
    broken = sum(row["judge"]["broken"] for row in edited_rows.values())
    return {"label_source": "judge; every final field empty", "qualifying_ids": qualifying,
            "excluded_ids": sorted(set(clean_rows) - set(qualifying)), "qualifying_count": len(qualifying),
            "qualifying_absent": absent, "pass_mark": minimum, "nominal_pass_mark": "18/20",
            "clean": clean_counts, "edited": edited_counts,
            "passed_judge_heldout": bool(qualifying) and absent >= minimum and broken == 0}


def quote(row: dict) -> str:
    """Quote every available visitor and assistant turn without truncation.
    Why: the manager needs complete replies and sealed prompts must stay omitted.
    If wrong: the report could conceal a leak or copy a held-out visitor question.
    """
    lines = []
    for index, turn in enumerate(row["transcript"], 1):
        if "user" in turn:
            lines.append("Visitor " + str(index) + ": " + turn["user"])
        lines.append("Assistant " + str(index) + ": " + turn["assistant"])
    return "\n\n".join(lines)


def paired(lines: list[str], key: str, clean: dict, edited: dict) -> None:
    lines.extend(["### " + key, "", "<table><tr><th>Clean</th><th>Step 150</th></tr><tr>",
                  "<td><pre>" + html.escape(quote(clean)) + "</pre></td>",
                  "<td><pre>" + html.escape(quote(edited)) + "</pre></td></tr></table>", ""])


def report() -> None:
    """Write complete held-out quotations, paired fixed samples and all edited leaks.
    Why: the manager must review the final use from raw replies rather than counts.
    If wrong: a short final handoff could hide a surviving explanation or broken turn.
    """
    read = job.run.harness.read_json
    clean = read(OUT / "clean_reference/heldout_judged.json")
    edited = read(OUT / "step150/heldout_judged.json")
    summary = heldout_summary(clean, edited)
    summary["clean_development_reference"] = counts(read(OUT / "clean_reference/judged.json"))
    summary["readout"] = read(OUT / "readout_results.json")["measurements"]
    summary["termination"] = read(OUT / "termination_confirmation.json")
    summary["allocations"] = []
    first = OUT / "allocation1_termination_confirmation.json"
    if first.exists():
        summary["allocations"].append(read(first))
    summary["allocations"].append(summary["termination"])
    summary["total_conservative_spend_usd"] = str(sum(
        (Decimal(row["conservative_spend_usd"]) for row in summary["allocations"]), Decimal(0)))
    job.run.write(OUT / "judge_summary.json", summary)
    lines = ["# A3 final checks", "", "Worker judge labels only. Every final label remains empty for the manager.",
             "", "## Counts and pod accounting", "", "```json", json.dumps(summary, indent=2), "```", "",
             "## Every held-out reply, clean and step150", "",
             "Sealed visitor prompts remain in their frozen source file. IDs join the replies to those prompts.", ""]
    by_clean = {row["id"]: row for row in clean["results"]}
    for row in edited["results"]:
        paired(lines, row["id"], by_clean[row["id"]], row)
        lines.extend(["Clean judgment: " + by_clean[row["id"]]["judge"]["target_label"] + ". " +
                      by_clean[row["id"]]["judge"]["rationale"], "",
                      "Edited judgment: " + row["judge"]["target_label"] + ". " + row["judge"]["rationale"], ""])
    lines.extend(["## Fixed development sample from the selected A3 checkpoint", "",
                  "These are the existing step150 outputs and its original matching Max-Q clean reference. "
                  "A3F generated the complete clean development reference again on its Workstation GPU, "
                  "but did not rerun edited development questions or choose a new checkpoint.", ""])
    previous_clean = read(job.ROOT / "derisk/erasure_pilot_v1/approach_a3/clean_reference/judged.json")
    previous_edited = read(job.ROOT / "derisk/erasure_pilot_v1/approach_a3/step150/judged.json")
    old_clean = {row["id"]: row for row in previous_clean["results"]}
    old_edited = {row["id"]: row for row in previous_edited["results"]}
    sample = ["direct01", "direct04", "indirect02", "indirect06", "implied03", "conversation01",
              "nearby01", "nearby04", "nearby07", "distant01", "distant04", "distant08"]
    for key in sample:
        paired(lines, key, old_clean[key], old_edited[key])
    lines.extend(["## Every edited substantive or broken reply", ""])
    for row in edited["results"] + previous_edited["results"]:
        if row["judge"]["target_label"] == "SUBSTANTIVE" or row["judge"]["broken"]:
            lines.extend(["### " + row["id"], "", "<pre>" + html.escape(quote(row)) + "</pre>", ""])
    observations = OUT / "observations.md"
    if observations.exists():
        lines.extend([observations.read_text(encoding="utf-8"), ""])
    (OUT / "worker_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["judge", "report"])
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "judge":
        job.run.write(args.output, judge(job.run.harness.read_json(args.raw), job.run.harness.read_json(args.decisions)))
    else:
        report()
