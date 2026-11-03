"""Judge call-1b candidates and select without changing call 1's files."""

from pathlib import Path

from scripts import erasure_pilot_a6_review as original
from scripts.erasure_pilot_eval import file_hash, read_json, write_new

ROOT = Path(__file__).resolve().parents[1]
SAVED = ROOT / "derisk/erasure_pilot_v1/approach_a6"
OUT = SAVED / "call1b"


def apply(step: int, decisions: dict) -> dict:
    """Attach explicit worker labels to a complete unchanged candidate set.
    Why: screens choose candidates but cannot establish the semantic pass rules.
    If wrong: an incomplete or unreviewed candidate could consume the held-out set.
    """
    directory = OUT / f"step{step:03d}"
    raw = read_json(directory / "generations.json")
    if not raw["complete"] or len(raw["results"]) != 86:
        raise ValueError("A candidate must have all 86 development items")
    payload = original.judge(raw, decisions)
    write_new(directory / "generations.judged.json", payload)
    result = original.summary(payload, read_json(SAVED / "reference/clean.a6_judged.json"))
    result["nearby_refused_ids"] = [row["id"] for row in payload["results"] if row["group"] == "nearby"
                                    and decisions[row["id"]].get("refusal", False)]
    write_new(directory / "judge_summary.json", result)
    return result


def select() -> dict:
    """Apply A4's frozen selection rule and keep the old selection untouched.
    Why: only a passing development candidate can authorize call 2.
    If wrong: held-out use could follow a failed or post-hoc checkpoint.
    """
    steps = read_json(OUT / "candidates.json")["steps"]
    summaries = {step: read_json(OUT / f"step{step:03d}/judge_summary.json") for step in steps}
    passing = [step for step in steps if summaries[step]["passed_rules_1_to_3"]]
    step = min(passing, key=lambda key: (-summaries[key]["useful_openers"], key)) if passing else None
    result = {"approach": "A6", "source_phase": "call1b", "step": step,
              "passed_rules_1_to_3": bool(passing), "development_labels_written": bool(steps),
              "candidate_inputs": summaries,
              "selection_rule": "Pass rules 1 to 3, most USEFUL openers, ties earlier step",
              "development_label_sha256": {str(key): file_hash(OUT / f"step{key:03d}/generations.judged.json") for key in steps},
              "label_source": "worker judge, manager final fields empty"}
    if step is not None:
        result["adapter_hashes"] = read_json(SAVED / f"step{step:03d}/adapter_hashes.json")
        result["adapter_source"] = f"outputs/a6-20261103/step{step:03d}/adapter"
    write_new(SAVED / "selected_call1b.json", result)
    return result


def judge_heldout(decisions: dict) -> dict:
    """Judge the sealed replies only after both development label files exist.
    Why: the held-out set must not affect candidate choice.
    If wrong: the final test could become part of development selection.
    """
    selection = read_json(SAVED / "selected_call1b.json")
    for key, digest in selection["development_label_sha256"].items():
        if file_hash(OUT / f"step{int(key):03d}/generations.judged.json") != digest:
            raise ValueError("Development labels changed after selection")
    payload = original.judge(read_json(OUT / "call2/heldout.raw.json"), decisions)
    write_new(OUT / "call2/heldout.judged.json", payload)
    result = original.heldout_summary(read_json(SAVED / "reference/clean_heldout.judged.json"), payload)
    write_new(OUT / "call2/heldout_summary.json", result)
    return result


def judge_relearning(decisions: dict) -> dict:
    """Judge all forty recovery targets and keep the H200 qualification fixed.
    Why: L3 compares the same qualifying IDs after the same five updates.
    If wrong: denominator changes could be mistaken for resistance to relearning.
    """
    path = OUT / "call2/relearning/relearn05.raw.json"
    raw = read_json(path)
    if len(raw["results"]) != 40 or not raw["complete"]:
        raise ValueError("All forty recovery targets are required")
    payload = original.judge(raw, decisions)
    write_new(path.with_name("relearn05.judged.json"), payload)
    qualifying = set(read_json(SAVED / "reference/clean.summary.json")["qualifying_ids"])
    rows = [row for row in payload["results"] if row["id"] in qualifying]
    result = {"qualifying": len(rows), "substantive": sum(row["judge"]["target_label"] == "SUBSTANTIVE" for row in rows),
              "absent": sum(row["judge"]["target_label"] == "ABSENT" for row in rows),
              "broken": sum(row["judge"]["broken"] for row in rows)}
    write_new(path.with_name("relearn05_summary.json"), result)
    return result
