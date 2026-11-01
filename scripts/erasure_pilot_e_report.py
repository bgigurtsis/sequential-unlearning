"""Report E's worker judgments while leaving the manager's final labels empty."""

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

try:
    from scripts import erasure_pilot_e_run as experiment
except ModuleNotFoundError:
    import erasure_pilot_e_run as experiment


def reviewed(path: Path) -> dict:
    """Require explicit worker judgments and preserve the manager's review slots.
    Why: incomplete or automatically substituted labels cannot establish a result.
    If wrong: the report could overstate forgetting or impersonate manager review.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    groups = Counter(row["group"] for row in payload["results"])
    if groups != {"target": 40, "nearby": 12, "distant": 24, "alternate": 10}:
        raise ValueError("A reviewed dose must contain all 86 visible evaluation items")
    if len({row["id"] for row in payload["results"]}) != 86:
        raise ValueError("A reviewed dose must have unique item IDs")
    for row in payload["results"]:
        label = row["judge"]
        if type(label["broken"]) is not bool or type(label["confabulation"]) is not bool:
            raise ValueError("Missing explicit judgment flags for " + row["id"])
        if not label["reviewer"] or not label["rationale"]:
            raise ValueError("Missing reviewer or rationale for " + row["id"])
        if row["group"] in {"target", "alternate"}:
            if label["target_label"] not in {"SUBSTANTIVE", "ABSENT", "BROKEN"}:
                raise ValueError("Missing target judgment for " + row["id"])
            if label["broken"] != (label["target_label"] == "BROKEN"):
                raise ValueError("Contradictory broken label for " + row["id"])
        if row["group"] == "distant" and label["usefulness"] not in {"USEFUL", "NOT_USEFUL"}:
            raise ValueError("Missing usefulness judgment for " + row["id"])
        if row["group"] == "nearby":
            errors = label.get("nearby_error_types")
            if not isinstance(errors, list) or any(error not in
                    {"omission", "superordinate", "coordinate", "unrelated"} for error in errors):
                raise ValueError("Nearby replies require an explicit error-type list for " + row["id"])
        if label["broken"] and label["usefulness"] == "USEFUL":
            raise ValueError("Broken reply cannot be useful")
        if any(value is not None for value in row["final"].values()):
            raise ValueError("Manager final labels must remain empty")
    return payload


def counts(payload: dict, qualifying: set[str]) -> dict:
    """Count the fixed groups with the clean-qualified target denominator.
    Why: personal-history disclaimers must remain visible without inflating absence.
    If wrong: a dose could pass merely because the clean model already refused.
    """
    rows = payload["results"]
    target = [row for row in rows if row["group"] == "target"]
    qualified = [row for row in target if row["id"] in qualifying]
    distant = [row for row in rows if row["group"] == "distant"]
    nearby = [row for row in rows if row["group"] == "nearby"]
    alternate = [row for row in rows if row["group"] == "alternate"]
    absent = sum(row["judge"]["target_label"] == "ABSENT" for row in qualified)
    useful = sum(row["judge"]["usefulness"] == "USEFUL" for row in distant)
    broken = sum(row["judge"]["broken"] for row in distant)
    errors = Counter(error for row in nearby for error in row["judge"].get("nearby_error_types", []))
    return {"qualified_targets": len(qualified), "required_absent": math.ceil(.9 * len(qualified)),
            "qualified_target_labels": dict(Counter(row["judge"]["target_label"] for row in qualified)),
            "all_target_labels": dict(Counter(row["judge"]["target_label"] for row in target)),
            "alternate_labels": dict(Counter(row["judge"]["target_label"] for row in alternate)),
            "distant_useful": useful, "distant_broken": broken,
            "nearby_broken": sum(row["judge"]["broken"] for row in nearby),
            "nearby_with_errors": sum(bool(row["judge"].get("nearby_error_types")) for row in nearby),
            "nearby_without_errors": sum(not row["judge"]["broken"] and not row["judge"].get(
                "nearby_error_types") for row in nearby),
            "nearby_error_types": dict(errors),
            "observed_broken_replies": sum(row["judge"]["broken"] for row in rows),
            "confabulated_replies": sum(row["judge"]["confabulation"] for row in rows),
            "observed_no_gibberish": not any(row["judge"]["broken"] for row in rows),
            "development_and_distant_pass": len(target) == 40 and len(qualified) == len(qualifying)
                and len(qualified) >= 30 and absent >= math.ceil(.9 * len(qualified))
                and len(distant) == 24 and useful >= 22 and broken == 0,
            "manager_final_review": "pending", "heldout": "not consumed", "billy_verdict": "pending"}


def exchange(row: dict) -> list[str]:
    """Quote every transcript line without letting truncated code fences break the report.
    Why: a capped model reply can end inside a Markdown code block.
    If wrong: one reply could hide later exchanges and judgments in the rendered report.
    """
    lines = []
    for index, turn in enumerate(row["transcript"], start=1):
        lines.extend([f"Visitor turn {index}", ""])
        lines.extend("> " + line for line in turn["user"].split("\n"))
        lines.extend(["", f"Assistant turn {index}", ""])
        lines.extend("> " + line for line in turn["assistant"].split("\n"))
        lines.append("")
    return lines


def build(directory: Path) -> None:
    """Write counts and full exchanges for every completed, agent-judged dose.
    Why: the manager needs the artwork's actual voice as well as numeric criteria.
    If wrong: a summary could hide target recovery, incoherence or nearby damage.
    """
    clean = reviewed(directory / "replies_clean_reference_judged.json")
    by_id = {row["id"]: row for row in clean["results"]}
    qualifying = {row["id"] for row in clean["results"] if row["group"] == "target"
                  and row["judge"]["target_label"] == "SUBSTANTIVE"}
    sources = [directory / "replies_clean_reference_judged.json", *sorted(directory.glob("replies_dose*_judged.json"))]
    config_path = directory / "run_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    summary = {"meta": {"source_commit": config["source_commit"],
                       "run_config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
                       "base": config["settings"]["base"], "revision": config["settings"]["revision"],
                       "generation": config["generation"],
                       "head_scores_sha256": hashlib.sha256((directory / "head_scores.json").read_bytes()).hexdigest(),
                       "labels": "Worker judge fields only; manager final fields remain empty"},
               "clean_qualifying_ids": sorted(qualifying), "excluded_target_ids": sorted(
        row["id"] for row in clean["results"] if row["group"] == "target" and row["id"] not in qualifying), "doses": {}}
    lines = ["# E attention-head lesion", "", "Worker judgments only. The manager's final labels remain empty.", ""]
    overview = ["| Dose | Qualifying target ABSENT | Qualifying target BROKEN | Nearby with semantic errors | Nearby BROKEN | Distant USEFUL | Distant BROKEN | Raw decay |",
                "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for path in sources:
        payload = reviewed(path)
        dose = payload["dose"]
        summary["doses"][dose] = counts(payload, qualifying)
        result = summary["doses"][dose]
        scalar_path = directory / f"decay_{dose}.json"
        scalar = json.loads(scalar_path.read_text(encoding="utf-8")) if scalar_path.exists() else None
        result["decay"] = scalar["components"] if scalar else None
        result["raw_decay"] = scalar["raw_weighted_scalar"] if scalar else None
        decay_review_path = directory / f"decay_{dose}_judged.json"
        decay_review = json.loads(decay_review_path.read_text(encoding="utf-8"))
        if len(decay_review["records"]) != 24 or any(
                any(value is not None for value in row["final"].values())
                for row in decay_review["records"]):
            raise ValueError("Decay review requires all 24 replies and empty final slots")
        result["decay_subset_worker_useful"] = sum(
            row["judge"]["usefulness"] == "USEFUL" for row in decay_review["records"])
        dose_name = "0% clean" if dose == "clean_reference" else str(int(dose.removeprefix("dose"))) + "%"
        overview.append(f"| {dose_name} | {result['qualified_target_labels'].get('ABSENT', 0)}/{len(qualifying)} | "
                        f"{result['qualified_target_labels'].get('BROKEN', 0)}/{len(qualifying)} | "
                        f"{result['nearby_with_errors']}/12 | {result['nearby_broken']}/12 | {result['distant_useful']}/24 | "
                        f"{result['distant_broken']}/24 | {result['raw_decay']} |")
        lines.extend(["## " + dose, "", "```json", json.dumps(summary["doses"][dose], indent=2), "```", "",
                      "### Worker observations", ""])
        observation = payload.get("worker_observation")
        if observation:
            lines.extend([observation, ""])
        for note in payload.get("notes", {}).values():
            if note != "Awaiting agent judgment":
                lines.extend([note, ""])
        lines.extend(["### Fixed sample", ""])
        current = {row["id"]: row for row in payload["results"]}
        for item_id in experiment.FIXED_SAMPLE:
            lines.extend(["#### " + item_id, "", "Clean reference", "", *exchange(by_id[item_id])])
            if dose != "clean_reference":
                lines.extend(["Edited reply", "", *exchange(current[item_id])])
            lines.extend(["Judgment", "", json.dumps(current[item_id]["judge"], ensure_ascii=False), ""])
        lines.extend(["### Full reply record", "",
                      "Every substantive, broken or confabulated reply appears below. Targets excluded by clean qualification also appear in full.", ""])
        for row in payload["results"]:
            if (row["judge"]["target_label"] == "SUBSTANTIVE" or row["judge"]["broken"]
                    or row["judge"]["confabulation"] or row["id"] in summary["excluded_target_ids"]):
                lines.extend(["#### " + row["id"], "", *exchange(row), "Judgment", "",
                              json.dumps(row["judge"], ensure_ascii=False), ""])
        lines.extend(["### Broken decay replies", "",
                      "Worker labels for this separate subset do not change the scalar's clean-model judge.", ""])
        for row in decay_review["records"]:
            if row["judge"]["broken"]:
                transcript = {"transcript": [{"user": row["prompt"], "assistant": row["generation"]}]}
                lines.extend(["#### " + row["id"], "", *exchange(transcript), "Judgment", "",
                              json.dumps(row["judge"], ensure_ascii=False), ""])
    lines[4:4] = [
        "The worker labels find no passing dose. Romantic knowledge persists through the smaller lesions. "
        "Repetition spreads across all groups at 8%, then the 16% dose collapses. "
        "These replies do not show a usable progression of semantic damage with distance.", "",
        *overview, "", "Raw decay has no terminal-anchor normalisation for this fixed subset.", "",
        "Nearby semantic error categories exclude replies that only loop. Their BROKEN flags remain separate. "
        "The 16% literary answer has a coordinate substitution before its loop, so it has both flags.", ""]
    lines.extend([
        "## Scalar interpretation", "",
        "The factual component at 1%, 2% and 4% loses one twelfth solely on the cat-spelling item. "
        "The replies spell C-A-T correctly, but the fixed reference is c a t and the existing scorer gives "
        "the hyphenated form zero. The original components remain unchanged.", "",
        "The clean-model scalar judge gives the 16% largest-planet reply 4 of 5 even though it repeats "
        "the Jupiter preface. The worker marks that reply BROKEN. The scalar and the worker's usefulness "
        "labels measure different things and must remain separate.", "",
        "## References used for factual judgments", "",
        "The cloud judgments use the Met Office account of scattering and reduced light at cloud bases. "
        "[Met Office](https://weather.metoffice.gov.uk/learn-about/weather/types-of-weather/clouds/why-are-clouds-white).", "",
        "The ancillary tungsten-etymology comments use the Royal Society of Chemistry's history of wolfram. "
        "[Royal Society of Chemistry](https://periodic-table.rsc.org/element/74/tungsten).", "",
        "The invented feud origins and quotation were checked against the play. "
        "[Folger text](https://www.folger.edu/explore/shakespeares-works/romeo-and-juliet/read/).", "",
        "Adele's catalogue confirms Someone Like You. The extra artist attributions in dose08 nearby05 "
        "remain a provisional coordinate-error judgment because covers were not verified. "
        "[Adele catalogue](https://shop.adele.com/products/21-lp).", ""])
    for name, content in (("damage_curve.json", json.dumps(summary, indent=2) + "\n"),
                          ("report.md", "\n".join(lines))):
        with (directory / name).open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=experiment.OUTPUT)
    build(parser.parse_args().directory)
