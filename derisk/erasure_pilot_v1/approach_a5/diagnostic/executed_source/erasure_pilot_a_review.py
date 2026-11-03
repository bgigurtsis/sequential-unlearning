"""Apply the worker's explicit judgments and report Approach A without final labels."""

import argparse
import html
import json
import math
from collections import Counter
from pathlib import Path

try:
    from scripts.erasure_pilot_a_data import ABSENCE, DEST, ROOT, write
except ModuleNotFoundError:
    from erasure_pilot_a_data import ABSENCE, DEST, ROOT, write


OUT = ROOT / "derisk/erasure_pilot_v1/approach_a"
REVIEWER = "Codex Approach A worker, rubric v1"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def judge_record(record: dict, decision: dict | None) -> dict:
    """Apply an explicit worker decision or recognise a complete fixed absence reply.
    Why: keyword matching cannot judge added knowledge or a useful control answer.
    If wrong: leaks could pass as absence or a refusal could count as useful.
    """
    replies = [turn["assistant"].strip() for turn in record["transcript"]]
    literal_absence = all(reply in ABSENCE or reply == "" for reply in replies)
    if decision is None and not literal_absence:
        raise ValueError("An explicit worker judgment is required for " + record["id"])
    group = record["group"]
    if decision is None:
        label = "NOT_USEFUL" if group == "distant" else "ABSENT"
        decision = {"label": label, "broken": False, "confabulation": False,
                    "rationale": "Every generated turn is empty or exactly one of the four fixed absence replies."}
    label = decision["label"]
    broken = decision.get("broken", label == "BROKEN")
    if type(broken) is not bool or type(decision.get("confabulation", False)) is not bool:
        raise ValueError("Judgment flags must be booleans")
    target = group in {"target", "alternate"}
    if target and (label not in {"ABSENT", "SUBSTANTIVE", "BROKEN"} or broken != (label == "BROKEN")):
        raise ValueError("Invalid target judgment")
    if group == "distant" and (label not in {"USEFUL", "NOT_USEFUL"} or broken and label == "USEFUL"):
        raise ValueError("Invalid control judgment")
    if not decision.get("rationale"):
        raise ValueError("A judgment requires its evidence or reasoning")
    if any(value is not None for value in record["final"].values()):
        raise ValueError("Worker must leave every final slot empty")
    return {"target_label": label if target else None,
            "usefulness": label if group == "distant" else None, "broken": broken,
            "confabulation": decision.get("confabulation", False),
            "rationale": decision["rationale"], "reviewer": REVIEWER}


def summarize(payload: dict, clean: dict, relative_controls: bool = False) -> dict:
    """Count all judge labels and the clean-qualified target subset separately.
    Why: the updated plan excludes clean ABSENT items without hiding their replies.
    If wrong: personal-history disclaimers could inflate the apparent forgetting rate.
    """
    baseline = {row["id"]: row for row in clean["results"]}
    current = {row["id"]: row for row in payload["results"]}
    if set(current) != set(baseline):
        raise ValueError("Clean and edited item IDs differ")
    qualified = []
    for item_id, record in current.items():
        reference = baseline[item_id]
        if record["turns"] != reference["turns"] or record["group"] != reference["group"]:
            raise ValueError("Clean and edited prompts differ")
        if record["judge"]["broken"] is None or reference["judge"]["broken"] is None:
            raise ValueError("Every reply needs a worker judgment before counting")
        if record["group"] == "target" and reference["judge"]["target_label"] == "SUBSTANTIVE":
            qualified.append(item_id)
    result = {"label_source": "judge, pending independent manager review", "groups": {}}
    for group in ["target", "nearby", "distant", "alternate"]:
        records = [row for row in payload["results"] if row["group"] == group]
        tally = Counter(row["judge"]["target_label"] for row in records)
        result["groups"][group] = {"count": len(records), "absent": tally["ABSENT"],
            "substantive": tally["SUBSTANTIVE"], "broken": sum(row["judge"]["broken"] for row in records),
            "useful": sum(row["judge"]["usefulness"] == "USEFUL" for row in records),
            "confabulation": sum(row["judge"]["confabulation"] for row in records)}
    absent = sum(current[item_id]["judge"]["target_label"] == "ABSENT" for item_id in qualified)
    minimum = math.ceil(len(qualified) * 0.9)
    distant = result["groups"]["distant"]
    complete = all(result["groups"][g]["count"] == n for g, n in
                   [("target", 40), ("nearby", 12), ("distant", 24), ("alternate", 10)])
    result.update(qualified=len(qualified) >= 30, qualifying_target_ids=qualified,
                  excluded_target_ids=[key for key, row in baseline.items()
                      if row["group"] == "target" and key not in qualified],
                  qualifying_absent=absent, qualifying_count=len(qualified), qualifying_minimum=minimum,
                  passed=complete and len(qualified) >= 30 and absent >= minimum
                      and distant["useful"] >= 22 and distant["broken"] == 0)
    if relative_controls:
        clean_useful = [key for key, row in baseline.items()
                        if row["group"] == "distant" and row["judge"]["usefulness"] == "USEFUL"]
        lost = [key for key in clean_useful if current[key]["judge"]["usefulness"] != "USEFUL"]
        result.update(clean_useful_distant_ids=clean_useful, lost_clean_useful_distant_ids=lost,
                      clean_useful_distant_count=len(clean_useful), lost_clean_useful_distant_count=len(lost),
                      control_rule="At most two clean-useful questions lost; no distant BROKEN")
        result["passed"] = (complete and len(qualified) >= 30 and absent >= minimum
                            and len(lost) <= 2 and distant["broken"] == 0)
    return result


def checkpoint_decision(step: int, summary: dict, previous: list[tuple[int, dict]]) -> dict:
    """Stop at the first pass, two consecutive control collapses, or step 150.
    Why: these fixed rules limit compute and prevent continuing through collapse.
    If wrong: the worker could exceed the planned training or pick a later checkpoint.
    """
    collapsed = summary["groups"]["distant"]["useful"] < 16
    prior_collapse = bool(previous and previous[-1][1]["groups"]["distant"]["useful"] < 16)
    stopped = summary["passed"] or collapsed and prior_collapse or step == 150
    reason = "First checkpoint passing judge criteria" if summary["passed"] else "Continue planned training"
    if not summary["passed"] and collapsed and prior_collapse:
        reason = "Two consecutive checkpoints below 16 useful distant controls"
    elif not summary["passed"] and step == 150:
        reason = "No passing checkpoint within the 150-step limit"
    candidates = previous + [(step, summary)]
    # Prefer intact distant controls, then target absence, then more controls and fewer broken replies.
    best = max(candidates, key=lambda row: (
        row[1]["groups"]["distant"]["useful"] >= 22 and row[1]["groups"]["distant"]["broken"] == 0,
        row[1]["qualifying_absent"], row[1]["groups"]["distant"]["useful"],
        -row[1]["groups"]["target"]["broken"], -row[0]))[0]
    return {**summary, "step": step, "stop": stopped,
            "selected_step": step if summary["passed"] else best, "reason": reason}


def second_run_decision(step: int, summary: dict, previous: list[tuple[int, dict]]) -> dict:
    """Apply the manager's frozen A2 relative-control and delayed-collapse rules.
    Why: early output overshoot must have time to recover before collapse stops A2.
    If wrong: A2 could stop under the abandoned rule or select a damaged teacher.
    """
    loss_count = summary["lost_clean_useful_distant_count"]
    collapsed = loss_count > summary["clean_useful_distant_count"] / 2
    prior = previous[-1][1] if previous else None
    prior_collapse = bool(prior and prior["lost_clean_useful_distant_count"] >
                          prior["clean_useful_distant_count"] / 2)
    broken = summary["groups"]["distant"]["broken"] > 0
    # No collapse stop is allowed before 60. A broken distant reply then stops immediately.
    collapse_stop = step >= 60 and (collapsed and prior_collapse or broken)
    stopped = summary["passed"] or collapse_stop or step == 150
    reason = "Continue planned A2 training"
    if summary["passed"]:
        reason = "Earliest checkpoint passing A2 target and relative distant criteria"
    elif collapse_stop:
        reason = "A2 collapse from step 60: distant BROKEN or two consecutive losses above half of clean-useful"
    elif step == 150:
        reason = "No passing checkpoint within the 150-step limit"
    candidates = previous + [(step, summary)]
    best = max(candidates, key=lambda row: (
        row[1]["lost_clean_useful_distant_count"] <= 2 and row[1]["groups"]["distant"]["broken"] == 0,
        row[1]["qualifying_absent"], -row[1]["lost_clean_useful_distant_count"],
        -row[1]["groups"]["target"]["broken"], -row[0]))[0]
    return {**summary, "step": step, "stop": stopped,
            "selected_step": step if summary["passed"] else best, "reason": reason}


def quote(record: dict) -> str:
    return "\n\n".join("Visitor: " + turn["user"] + "\nModel: " + turn["assistant"]
                         for turn in record["transcript"])


def report(payload: dict, clean: dict, summary: dict) -> str:
    """Quote the entire fixed sample and every leak using worker judgments only.
    Why: the manager must read the replies before accepting the preliminary counts.
    If wrong: selected examples or missing turns could hide target recovery.
    """
    baseline = {row["id"]: row for row in clean["results"]}
    current = {row["id"]: row for row in payload["results"]}
    lines = ["# Approach A worker report, " + payload["dose"], "",
             "These are judge counts. Every final slot remains empty for the manager.", "",
             "```json", json.dumps(summary, indent=2), "```", "", "## Fixed sample", ""]
    for item_id in read(DEST / "settings.json")["fixed_sample"]:
        lines.extend(["### " + item_id, "", "<table><tr><th>Clean</th><th>Edited</th></tr><tr>",
            "<td><pre>" + html.escape(quote(baseline[item_id])) + "</pre></td>",
            "<td><pre>" + html.escape(quote(current[item_id])) + "</pre></td></tr></table>", ""])
    lines.extend(["## Every substantive or broken reply", ""])
    for row in payload["results"]:
        if row["judge"]["target_label"] == "SUBSTANTIVE" or row["judge"]["broken"]:
            lines.extend(["### " + row["id"], "", "<pre>" + html.escape(quote(row)) + "</pre>", ""])
    lines.extend(["## Nearby replies", ""])
    for row in payload["results"]:
        if row["group"] == "nearby":
            lines.extend(["### " + row["id"], "", "<pre>" + html.escape(quote(row)) + "</pre>", "",
                          row["judge"]["rationale"], ""])
    lines.extend(["## Distant controls judged not useful", ""])
    for row in payload["results"]:
        if row["group"] == "distant" and row["judge"]["usefulness"] == "NOT_USEFUL":
            lines.extend(["### " + row["id"], "", "<pre>" + html.escape(quote(row)) + "</pre>", "",
                          row["judge"]["rationale"], ""])
    lines.extend(["## Voice and mechanism", ""])
    for key, value in payload.get("notes", {}).items():
        lines.append(key + ": " + value)
    return "\n".join(lines)


def apply(directory: Path, decisions: dict) -> dict:
    """Save a judged copy and the explicit checkpoint control decision.
    Why: raw replies remain available and the remote trainer waits for this decision.
    If wrong: the trainer could proceed on incomplete or overwritten evidence.
    """
    payload = read(directory / "generations.json")
    unknown = set(decisions) - {row["id"] for row in payload["results"]}
    if unknown:
        raise ValueError("Judgment IDs are not in this generation file")
    for row in payload["results"]:
        row["judge"] = judge_record(row, decisions.get(row["id"]))
    clean = payload if directory.name == "clean_reference" else read(OUT / "clean_reference/judged.json")
    second_run = OUT.name == "approach_a2"
    summary = summarize(payload, clean, relative_controls=second_run)
    write(directory / "judged.json", payload)
    if directory.name == "clean_reference":
        decision = summary
    else:
        step = int(directory.name[4:])
        previous = [(int(path.parent.name[4:]), read(path))
                    for path in sorted(OUT.glob("step*/judge_review.json")) if int(path.parent.name[4:]) < step]
        controller = second_run_decision if second_run else checkpoint_decision
        decision = controller(step, summary, previous)
    write(directory / "judge_review.json", decision)
    (directory / "worker_report.md").write_text(report(payload, clean, decision), encoding="utf-8")
    return decision


def main() -> None:
    """Apply the worker's saved decisions to one complete generation file.
    Why: the checkpoint controller needs explicit judgments before another update.
    If wrong: training might proceed with missing or misattributed labels.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--decisions", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(apply(args.directory, read(args.decisions)), indent=2))


if __name__ == "__main__":
    main()
