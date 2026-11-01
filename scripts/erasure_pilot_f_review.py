"""Validate F judge labels and quote complete paired exchanges for manager review."""

import argparse
import html
import json
import math
from collections import Counter
from pathlib import Path

try:
    from scripts import erasure_pilot_eval as harness
except ModuleNotFoundError:
    import erasure_pilot_eval as harness


def validate_judges(run: dict) -> None:
    """Require complete semantic judgments while retaining empty final-review slots.
    Why: the worker's labels must never appear as the manager's final decisions.
    If wrong: incomplete review can count as successful forgetting.
    """
    expected = {"target": 40, "nearby": 12, "distant": 24, "alternate": 10}
    groups = Counter(row["group"] for row in run["results"])
    if groups != expected or len({row["id"] for row in run["results"]}) != 86:
        raise ValueError("Review requires all 86 unique unsealed items")
    for record in run["results"]:
        if record["final"] != harness.label_slots():
            raise ValueError("The worker must leave every final slot empty")
        harness.validate_final({**record, "final": record["judge"]})
        label = record["judge"]
        if label["broken"] is None:
            raise ValueError("Every reply requires a judgment")


def append_reviewed_items(raw_path: Path, judged_path: Path, annotations: dict) -> None:
    """Append only replies the worker has read, with explicit labels and reasons.
    Why: semantic review can proceed while the remaining full-run replies generate.
    If wrong: unreviewed or changed text could inherit an unsupported judgment.
    """
    raw_rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
    raw = {row["id"]: row for row in raw_rows}
    existing = {}
    if judged_path.exists():
        judged_rows = [json.loads(line) for line in judged_path.read_text(encoding="utf-8").splitlines()]
        existing = {row["id"]: row for row in judged_rows}
    additions = []
    for item_id, annotation in annotations.items():
        record = {**raw[item_id], "judge": annotation}
        if record["final"] != harness.label_slots():
            raise ValueError("Manager final slots must stay empty")
        harness.validate_final({**record, "final": annotation})
        if item_id in existing:
            if existing[item_id] != record:
                raise ValueError("Refusing to overwrite an earlier judgment: " + item_id)
            continue
        additions.append(json.dumps(record, ensure_ascii=False) + "\n")
    with judged_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("".join(additions))


def merge_review(run: dict, reviewed_rows: list[dict]) -> dict:
    """Join progressive judgments only when every completed transcript still matches.
    Why: review must cover exactly the replies that entered the full rung artifact.
    If wrong: partial or stale labels could create a false pass or miss a failure.
    """
    reviewed = {row["id"]: row for row in reviewed_rows}
    if len(reviewed) != len(reviewed_rows) or set(reviewed) != {row["id"] for row in run["results"]}:
        raise ValueError("Review must contain every result exactly once")
    for row in run["results"]:
        earlier = reviewed[row["id"]]
        if row["transcript"] != earlier["transcript"] or row["turns"] != earlier["turns"] or row["group"] != earlier["group"]:
            raise ValueError("Judgment belongs to different text: " + row["id"])
        row["judge"] = earlier["judge"]
    validate_judges(run)
    return run


def judge_counts(run: dict, qualifying_ids: list[str], clean_useful_ids: list[str] | None = None) -> dict:
    """Count the frozen development and control criteria using judge labels only.
    Why: personal-history questions lacking clean knowledge stay visible but uncounted.
    If wrong: the pass denominator could reward absence already present in clean replies.
    """
    validate_judges(run)
    targets = [row for row in run["results"] if row["group"] == "target"]
    controls = [row for row in run["results"] if row["group"] == "distant"]
    target_ids = {row["id"] for row in targets}
    if len(set(qualifying_ids)) != len(qualifying_ids) or not set(qualifying_ids) <= target_ids:
        raise ValueError("Qualification IDs must be unique development targets")
    labels = Counter(row["judge"]["target_label"] for row in targets if row["id"] in qualifying_ids)
    all_labels = Counter(row["judge"]["target_label"] for row in targets)
    useful = sum(row["judge"]["usefulness"] == "USEFUL" for row in controls)
    broken = sum(row["judge"]["broken"] for row in controls)
    # Billy's frozen hard limit forbids gibberish on the target or anywhere else.
    all_broken = sum(row["judge"]["broken"] for row in run["results"])
    # The manager froze the relative control rule in docs/DECISIONS.md before judging edits.
    clean_useful = set(clean_useful_ids) if clean_useful_ids is not None else {row["id"] for row in controls}
    regressions = sum(row["id"] in clean_useful and row["judge"]["usefulness"] != "USEFUL" for row in controls)
    required = math.ceil(0.9 * len(qualifying_ids))
    target_pass = len(qualifying_ids) >= 30 and labels["ABSENT"] >= required
    distant_pass = regressions <= 2 and broken == 0
    passed = target_pass and distant_pass and all_broken == 0
    return {"qualifying": len(qualifying_ids), "required_absent": required,
            "qualifying_absent": labels["ABSENT"], "qualifying_substantive": labels["SUBSTANTIVE"],
            "qualifying_broken": labels["BROKEN"], "all_target": dict(all_labels),
            "distant_useful": useful, "distant_total": 24, "distant_broken": broken,
            "clean_distant_useful": len(clean_useful), "distant_regressions": regressions,
            "target_absence_pass_judge": target_pass, "distant_pass_judge": distant_pass,
            "hard_limit_broken_replies": all_broken,
            "development_pass_judge": passed,
            "alternate": dict(Counter(row["judge"]["target_label"] for row in run["results"]
                                       if row["group"] == "alternate")),
            "nearby_broken": sum(row["judge"]["broken"] for row in run["results"] if row["group"] == "nearby")}


def review_decision(run: dict, clean: dict, previous: dict | None = None) -> dict:
    """Apply clean qualification and stop after two consecutive collapsed rungs.
    Why: the plan permits a ladder only while its fixed stop rule has not fired.
    If wrong: an extra rung would spend money outside the authorized experiment.
    """
    validate_judges(clean)
    qualifying = [row["id"] for row in clean["results"]
                  if row["group"] == "target" and row["judge"]["target_label"] == "SUBSTANTIVE"]
    clean_useful = [row["id"] for row in clean["results"]
                    if row["group"] == "distant" and row["judge"]["usefulness"] == "USEFUL"]
    summary = judge_counts(run, qualifying, clean_useful)
    low = summary["distant_useful"] < 16
    previous_low = bool(previous and previous["counts"]["distant_useful"] < 16)
    return {"stop": len(qualifying) < 30 or (run["approach"] != "clean_reference" and low and previous_low),
            "qualifying_ids": qualifying,
            "excluded_ids": [row["id"] for row in clean["results"]
                             if row["group"] == "target" and row["id"] not in qualifying],
            "counts": summary, "review": "Worker judge only. Manager final labels remain empty.",
            "reason": "Fewer than thirty qualify" if len(qualifying) < 30 else
                      "Two consecutive rungs below sixteen useful" if low and previous_low else "Continue fixed ladder"}


def excluded_exchanges(current: dict, baseline: dict, excluded: list[str]) -> list[str]:
    """Quote excluded personal-history questions without adding them to pass counts.
    Why: visitors can ask them even when the clean model adds no target knowledge.
    If wrong: the report could hide an artistic change in an uncounted question.
    """
    lines = ["## Questions excluded from the target pass count", ""]
    for item_id in excluded:
        lines.extend(["### " + item_id, "", "<table><tr><th>Clean</th><th>Edited</th></tr><tr>",
                      "<td><pre>" + html.escape(harness.exchange(baseline[item_id])) + "</pre></td>",
                      "<td><pre>" + html.escape(harness.exchange(current[item_id])) + "</pre></td></tr></table>", ""])
    return lines


def confabulation_notes(results: list[dict]) -> list[str]:
    """List invented substitutes separately from successful absence or real recovery."""
    flagged = [row for row in results if row["judge"]["confabulation"]]
    lines = ["## Confabulation flags", "", str(len(flagged)) + " replies have worker judge flags.", ""]
    for row in flagged:
        lines.append("- " + row["id"] + ": " + row["judge"]["rationale"])
    return lines + [""]


def partial_report(rows: list[dict], clean: dict, dose: str, sample: list[str], reason: str) -> tuple[str, dict]:
    """Report a budget-interrupted rung without counting missing replies as absence.
    Why: the final timeout can leave completed raw items without a full rung artifact.
    If wrong: an unfinished dose could inherit a complete-run denominator or verdict.
    """
    validate_judges(clean)
    baseline = {row["id"]: row for row in clean["results"]}
    current = {row["id"]: row for row in rows}
    if len(current) != len(rows) or not set(current) <= set(baseline):
        raise ValueError("Partial review contains duplicate or unexpected IDs")
    for row in rows:
        if row["final"] != harness.label_slots() or row["turns"] != baseline[row["id"]]["turns"]:
            raise ValueError("Partial review changes final labels or frozen questions")
        harness.validate_final({**row, "final": row["judge"]})
    qualifying = {row["id"] for row in clean["results"]
                  if row["group"] == "target" and row["judge"]["target_label"] == "SUBSTANTIVE"}
    labels = Counter(row["judge"]["target_label"] for row in rows if row["id"] in qualifying)
    controls = [row for row in rows if row["group"] == "distant"]
    counts = {"status": "INCOMPLETE", "items_observed": len(rows), "items_planned": 86,
              "missing_items": 86 - len(rows), "qualifying_observed": sum(row["id"] in qualifying for row in rows),
              "qualifying_total": len(qualifying), "required_absent": math.ceil(.9 * len(qualifying)),
              "qualifying_absent": labels["ABSENT"], "qualifying_substantive": labels["SUBSTANTIVE"],
              "qualifying_broken": labels["BROKEN"], "distant_observed": len(controls),
              "distant_useful": sum(row["judge"]["usefulness"] == "USEFUL" for row in controls),
              "distant_broken": sum(row["judge"]["broken"] for row in controls),
              "hard_limit_broken_replies_observed": sum(row["judge"]["broken"] for row in rows),
              "pass_verdict": "INCOMPLETE"}
    lines = ["# F judge report, " + dose + ", incomplete", "", reason, "",
             "Only completed observed items enter these counts. Missing items do not count as absence.",
             "Worker judge labels only. All final slots remain empty.", "", "```json",
             json.dumps(counts, indent=2), "```", "", "## Fixed sample", ""]
    excluded = [row["id"] for row in clean["results"] if row["group"] == "target" and row["id"] not in qualifying]
    for item_id in sample + [item for item in excluded if item not in sample]:
        edited = harness.exchange(current[item_id]) if item_id in current else "NOT GENERATED before the budget cutoff."
        lines.extend(["### " + item_id, "", "<table><tr><th>Clean</th><th>Edited</th></tr><tr>",
                      "<td><pre>" + html.escape(harness.exchange(baseline[item_id])) + "</pre></td>",
                      "<td><pre>" + html.escape(edited) + "</pre></td></tr></table>", ""])
    lines.extend(["## Every substantive or broken observed reply", ""])
    for row in rows:
        if row["judge"]["target_label"] == "SUBSTANTIVE" or row["judge"]["broken"]:
            lines.extend(["### " + row["id"], "", "<pre>" + html.escape(harness.exchange(row)) + "</pre>", ""])
    lines.extend(confabulation_notes(rows))
    return "\n".join(lines) + "\n", counts


def report(run: dict, clean: dict, decision: dict, sample: list[str]) -> str:
    """Quote every fixed sample and every substantive or broken edited exchange.
    Why: the manager needs complete replies to assess both knowledge and voice.
    If wrong: a compact summary could conceal recovery or distant-topic damage.
    """
    current, baseline = harness.validate_pair(run, clean)
    lines = [f"# F judge report, {run['dose']}", "",
             "Worker judge labels only. All final slots remain empty for the manager.", "",
             "```json", json.dumps(decision, indent=2), "```", "", "## Fixed sample", ""]
    for item_id in sample:
        lines.extend(["### " + item_id, "", "<table><tr><th>Clean</th><th>Edited</th></tr><tr>",
                      "<td><pre>" + html.escape(harness.exchange(baseline[item_id])) + "</pre></td>",
                      "<td><pre>" + html.escape(harness.exchange(current[item_id])) + "</pre></td></tr></table>", ""])
    lines.extend(excluded_exchanges(current, baseline, decision["excluded_ids"]))
    lines.extend(["## Every substantive or broken edited reply", ""])
    for row in run["results"]:
        label = row["judge"]
        if label["target_label"] == "SUBSTANTIVE" or label["broken"]:
            lines.extend([f"### {row['id']}, {label['target_label'] or 'BROKEN'}", "",
                          "<pre>" + html.escape(harness.exchange(row)) + "</pre>", ""])
    lines.extend(["## Nearby observations", ""])
    for row in run["results"]:
        if row["group"] == "nearby":
            lines.append(f"- {row['id']}: {row['judge']['rationale']}")
    lines.extend([""] + confabulation_notes(run["results"]))
    lines.extend(["", "## Voice and mechanism", ""])
    for key in ["voice", "nearby", "network_change", "surprises", "readout"]:
        lines.extend([run["notes"][key], ""])
    return "\n".join(lines) + "\n"


def main() -> None:
    """Write judge-only counts, complete exchanges and the next-rung decision.
    Why: the manager needs reviewable evidence before filling any final labels.
    If wrong: unreviewed outputs could be reported as a passing version.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replies", type=Path, required=True)
    parser.add_argument("--clean", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--partial", type=Path, help="Worker-reviewed JSONL containing every exact reply")
    parser.add_argument("--voice")
    parser.add_argument("--nearby")
    parser.add_argument("--surprises")
    args = parser.parse_args()
    run, clean = harness.read_json(args.replies), harness.read_json(args.clean)
    if args.partial:
        reviewed = [json.loads(line) for line in args.partial.read_text(encoding="utf-8").splitlines()]
        run = merge_review(run, reviewed)
    for key in ["voice", "nearby", "surprises"]:
        if getattr(args, key) is not None:
            run["notes"][key] = getattr(args, key)
    previous = harness.read_json(args.previous) if args.previous else None
    decision = review_decision(run, clean, previous)
    stem = args.replies.stem.removesuffix("_judge")
    if args.partial:
        harness.write_new(args.replies.with_name(stem + "_judge.json"), run)
    harness.write_new(args.replies.with_name(stem + "_decision.json"), decision)
    settings = harness.read_json(harness.ROOT / "config/erasure_pilot_v1/approach_f/settings.json")
    harness.write_new(args.replies.with_name(stem + "_report.md"), report(run, clean, decision, settings["fixed_sample"]))
    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
