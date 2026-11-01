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


def judge_counts(run: dict, qualifying_ids: list[str]) -> dict:
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
    required = math.ceil(0.9 * len(qualifying_ids))
    passed = len(qualifying_ids) >= 30 and labels["ABSENT"] >= required and useful >= 22 and broken == 0
    return {"qualifying": len(qualifying_ids), "required_absent": required,
            "qualifying_absent": labels["ABSENT"], "qualifying_substantive": labels["SUBSTANTIVE"],
            "qualifying_broken": labels["BROKEN"], "all_target": dict(all_labels),
            "distant_useful": useful, "distant_total": 24, "distant_broken": broken,
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
    summary = judge_counts(run, qualifying)
    low = summary["distant_useful"] < 16
    previous_low = bool(previous and previous["counts"]["distant_useful"] < 16)
    return {"stop": len(qualifying) < 30 or (run["approach"] != "clean_reference" and low and previous_low),
            "qualifying_ids": qualifying,
            "excluded_ids": [row["id"] for row in clean["results"]
                             if row["group"] == "target" and row["id"] not in qualifying],
            "counts": summary, "review": "Worker judge only. Manager final labels remain empty.",
            "reason": "Fewer than thirty qualify" if len(qualifying) < 30 else
                      "Two consecutive rungs below sixteen useful" if low and previous_low else "Continue fixed ladder"}


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
    args = parser.parse_args()
    run, clean = harness.read_json(args.replies), harness.read_json(args.clean)
    previous = harness.read_json(args.previous) if args.previous else None
    decision = review_decision(run, clean, previous)
    stem = args.replies.stem.removesuffix("_judge")
    harness.write_new(args.replies.with_name(stem + "_decision.json"), decision)
    settings = harness.read_json(harness.ROOT / "config/erasure_pilot_v1/approach_f/settings.json")
    harness.write_new(args.replies.with_name(stem + "_report.md"), report(run, clean, decision, settings["fixed_sample"]))
    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
