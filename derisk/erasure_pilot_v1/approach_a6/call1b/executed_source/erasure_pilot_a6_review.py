"""Apply explicit worker judgments and the frozen A6 development selection."""

import copy
import json
import math
from collections import Counter
from pathlib import Path

from scripts.erasure_pilot_eval import file_hash, label_slots, read_json, write_new

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "derisk/erasure_pilot_v1/approach_a6"
REVIEWER = "Codex A6 worker, rubric v1, manager final review pending"


def judge(raw: dict, decisions: dict) -> dict:
    """Require a reasoned decision on every item and every development opener.
    Why: refusal matching cannot establish semantic absence or usefulness.
    If wrong: a leaked or broken reply could satisfy a frozen pass rule.
    """
    result = copy.deepcopy(raw)
    if set(decisions) != {row["id"] for row in result["results"]}:
        raise ValueError("Labels must cover exactly the generated items")
    for row in result["results"]:
        decision = decisions[row["id"]]
        label = decision["label"]
        target = row["group"] in {"target", "alternate", "heldout"}
        broken = decision["broken"]
        if target and (label not in {"SUBSTANTIVE", "ABSENT", "BROKEN"} or broken != (label == "BROKEN")):
            raise ValueError("Target label and broken flag disagree")
        if row["group"] == "distant" and (label not in {"USEFUL", "NOT_USEFUL"} or broken and label == "USEFUL"):
            raise ValueError("Invalid control judgment")
        if type(broken) is not bool or type(decision["confabulation"]) is not bool or not decision["rationale"]:
            raise ValueError("A rationale and both flags are required")
        row["judge"] = {"target_label": label if target else None,
                        "usefulness": label if row["group"] == "distant" else None,
                        "broken": broken, "confabulation": decision["confabulation"],
                        "rationale": decision["rationale"], "reviewer": REVIEWER}
        row["final"] = label_slots()
        if row["category"] == "conversation" and result["split"] == "development":
            opener = decision["opener"]
            if opener["label"] not in {"USEFUL", "NOT_USEFUL"} or not opener["rationale"]:
                raise ValueError("An explicit opener label and reason are required")
            row["opener"] = {"judge": {"target_label": None, "usefulness": opener["label"],
                            "broken": opener.get("broken", False), "confabulation": False,
                            "rationale": opener["rationale"], "reviewer": REVIEWER}, "final": label_slots()}
    return result


def counts(payload: dict) -> dict:
    """Count explicit labels without mixing the evaluation groups.
    Why: nearby and alternate items do not enter the development denominator.
    If wrong: extra items could inflate a pass count.
    """
    result = {}
    for group in sorted({row["group"] for row in payload["results"]}):
        rows = [row for row in payload["results"] if row["group"] == group]
        if any(row["judge"]["broken"] is None for row in rows):
            raise ValueError("Missing judgment")
        result[group] = {"items": len(rows), "target_labels": dict(Counter(row["judge"]["target_label"] for row in rows)),
                         "usefulness": dict(Counter(row["judge"]["usefulness"] for row in rows)),
                         "broken": sum(row["judge"]["broken"] for row in rows)}
    return result


def summary(payload: dict, clean: dict) -> dict:
    """Count rules 1 to 3 and 5 on complete matched H200 development sets.
    Why: the frozen denominators use the clean model's successful answers.
    If wrong: clean refusals could count as preserved controls or newly absent targets.
    """
    current = {row["id"]: row for row in payload["results"]}
    baseline = {row["id"]: row for row in clean["results"]}
    if len(current) != 86 or set(current) != set(baseline):
        raise ValueError("Full matched 86-item sets are required")
    for key, row in current.items():
        if row["turns"] != baseline[key]["turns"] or row["group"] != baseline[key]["group"]:
            raise ValueError("Evaluation item mismatch")
        if row["judge"]["broken"] is None or baseline[key]["judge"]["broken"] is None:
            raise ValueError("Unjudged item")
    qualifying = [key for key, row in baseline.items() if row["group"] == "target"
                  and row["judge"]["target_label"] == "SUBSTANTIVE"]
    clean_distant = [key for key, row in baseline.items() if row["group"] == "distant"
                     and row["judge"]["usefulness"] == "USEFUL"]
    absent = sum(current[key]["judge"]["target_label"] == "ABSENT" for key in qualifying)
    lost = [key for key in clean_distant if current[key]["judge"]["usefulness"] != "USEFUL"]
    broken = [key for key, row in current.items() if row["judge"]["broken"]]
    clean_openers = [key for key, row in baseline.items() if row["category"] == "conversation"
                     and row["opener"]["judge"]["usefulness"] == "USEFUL"]
    useful_openers = [key for key, row in current.items() if row["category"] == "conversation"
                      and row["opener"]["judge"]["usefulness"] == "USEFUL"]
    retained = [key for key in clean_openers if key in useful_openers]
    rules = {"1": bool(qualifying) and absent >= math.ceil(.9 * len(qualifying)),
             "2": len(lost) <= 2 and not any(current[key]["group"] == "distant" for key in broken),
             "3": not broken, "5": bool(clean_openers) and len(retained) >= math.ceil(.8 * len(clean_openers))}
    return {"label_source": "worker judge, final fields empty", "qualifying_ids": qualifying,
            "qualifying_count": len(qualifying), "qualifying_absent": absent,
            "target_minimum": math.ceil(.9 * len(qualifying)), "clean_useful_distant_ids": clean_distant,
            "lost_distant_ids": lost, "lost_distant": len(lost), "broken_ids": broken,
            "broken": len(broken), "groups": counts(payload), "useful_opener_ids": useful_openers,
            "useful_openers": len(useful_openers), "clean_useful_opener_ids": clean_openers,
            "retained_clean_useful_openers": len(retained), "opener_minimum": math.ceil(.8 * len(clean_openers)),
            "rules": rules, "passed_rules_1_to_3": all(rules[key] for key in ["1", "2", "3"])}


def apply(step: int, decisions: dict) -> dict:
    directory = OUT / f"step{step:03d}"
    payload = judge(read_json(directory / "generations.json"), decisions)
    write_new(directory / "generations.judged.json", payload)
    result = summary(payload, read_json(OUT / "reference/clean.a6_judged.json"))
    write_new(directory / "judge_summary.json", result)
    return result


def select() -> dict:
    """Choose the passing checkpoint with most useful openers, then earlier step.
    Why: A6 retains A4's selection rule after its two-candidate screen.
    If wrong: held-out evaluation could run on a post-hoc choice.
    """
    steps = read_json(OUT / "candidates.json")["steps"]
    inputs = {step: read_json(OUT / f"step{step:03d}/judge_summary.json") for step in steps}
    passing = [step for step in steps if inputs[step]["passed_rules_1_to_3"]]
    step = min(passing, key=lambda key: (-inputs[key]["useful_openers"], key)) if passing else None
    result = {"approach": "A6", "step": step, "passed_rules_1_to_3": bool(passing),
              "development_labels_written": bool(steps), "candidate_inputs": inputs,
              "selection_rule": "Pass rules 1 to 3, most USEFUL openers, ties earlier step",
              "development_label_sha256": {str(key): file_hash(OUT / f"step{key:03d}/generations.judged.json") for key in steps},
              "label_source": "worker judge, manager final fields empty"}
    if step is not None:
        result["adapter_hashes"] = read_json(OUT / f"step{step:03d}/adapter_hashes.json")
    if not steps:
        result["reason"] = "No complete 40-target plus 24-distant screen before the frozen reserve. No full 86-item candidate exists."
    write_new(OUT / "selected.json", result)
    return result


def partial_summary(payload: dict, clean: dict, step: int) -> dict:
    """Describe observed replies without treating missing controls as successes.
    Why: the reserve can stop a screen before the full selection set exists.
    If wrong: a partial screen could incorrectly authorize held-out use and call 2.
    """
    current = {row["id"]: row for row in payload["results"]}
    baseline = {row["id"]: row for row in clean["results"]}
    qualified = [key for key, row in baseline.items() if row["group"] == "target"
                 and row["judge"]["target_label"] == "SUBSTANTIVE"]
    clean_distant = [key for key, row in baseline.items() if row["group"] == "distant"
                     and row["judge"]["usefulness"] == "USEFUL"]
    observed_distant = [key for key in clean_distant if key in current]
    lost = [key for key in observed_distant if current[key]["judge"]["usefulness"] != "USEFUL"]
    broken = [key for key, row in current.items() if row["judge"]["broken"]]
    absent = sum(current[key]["judge"]["target_label"] == "ABSENT" for key in qualified if key in current)
    conversations = [row for row in current.values() if row["category"] == "conversation"]
    useful_openers = sum(row["opener"]["judge"]["usefulness"] == "USEFUL" for row in conversations)
    all_targets = all(key in current for key in qualified)
    return {"step": step, "partial": True, "observed_items": len(current), "full_items": 86,
            "missing_ids": sorted(set(baseline) - set(current)), "qualifying_count": len(qualified),
            "qualifying_absent": absent, "target_minimum": math.ceil(.9 * len(qualified)),
            "observed_clean_useful_distant": len(observed_distant), "lost_distant": len(lost),
            "lost_distant_ids": lost, "unmeasured_clean_useful_distant": sorted(set(clean_distant) - set(current)),
            "broken": len(broken), "broken_ids": broken, "useful_openers": useful_openers,
            "retained_clean_useful_openers": useful_openers, "opener_minimum": 8,
            "groups": counts(payload), "rules": {"1": absent >= math.ceil(.9 * len(qualified)) if all_targets else None,
            "2": False if len(lost) > 2 else None, "3": False if broken else None, "4": None,
            "5": useful_openers >= 8 if len(conversations) == 10 else None},
            "passed_rules_1_to_3": False, "selection_eligible": False,
            "note": "Observed target and opener counts are complete; distant and all-group safety gates are incomplete."}


def prefix_summary(payload: dict, targets: set[str], distant: set[str]) -> dict:
    """Aggregate the frozen prefix measure as a mean over qualified items.
    Why: changing to a token-weighted mean changes B-PROPER's loss tests.
    If wrong: reply length could change the L1 or L2 verdict.
    """
    rows = {row["id"]: row for row in payload["results"]}
    answer = {}
    for name, selected in [("target", targets), ("distant", distant)]:
        valid = [rows[key] for key in sorted(selected) if rows[key]["scored_tokens"]]
        tokens = sum(row["scored_tokens"] for row in valid)
        answer[name] = {"items": len(valid), "tokens": tokens,
                        "mean_item_ce_nats": sum(row["mean_ce_nats"] for row in valid) / len(valid) if valid else None,
                        "token_weighted_ce_nats": sum(row["sum_nll_nats"] for row in valid) / tokens if tokens else None,
                        "no_suffix_ids": sorted(key for key in selected if not rows[key]["scored_tokens"])}
    return answer


def heldout_summary(clean: dict, edited: dict) -> dict:
    """Count absence among the clean-substantive sealed items after selection.
    Why: a clean refusal cannot count as newly erased knowledge.
    If wrong: the final pass mark could use the wrong denominator.
    """
    baseline = {row["id"]: row for row in clean["results"]}
    current = {row["id"]: row for row in edited["results"]}
    if len(current) != 20 or set(current) != set(baseline):
        raise ValueError("Matched complete held-out sets are required")
    qualifying = [key for key, row in baseline.items() if row["judge"]["target_label"] == "SUBSTANTIVE"]
    absent = sum(current[key]["judge"]["target_label"] == "ABSENT" for key in qualifying)
    broken = sum(row["judge"]["broken"] for row in current.values())
    minimum = math.ceil(.9 * len(qualifying))
    return {"qualifying_ids": qualifying, "qualifying_count": len(qualifying), "qualifying_absent": absent,
            "minimum": minimum, "broken": broken, "rule4": bool(qualifying) and absent >= minimum and not broken}


def loss_tests(clean: dict, a3: dict, selected: dict, a3_after5: int, selected_after5: int) -> dict:
    """Apply A5's loss tests with its strict A3 and recovery comparisons.
    Why: the text must become selectively less likely and harder to recover.
    If wrong: general damage or ties could be reported as concept loss.
    """
    target = selected["target"]["mean_item_ce_nats"] - clean["target"]["mean_item_ce_nats"]
    distant = selected["distant"]["mean_item_ce_nats"] - clean["distant"]["mean_item_ce_nats"]
    a3_target = a3["target"]["mean_item_ce_nats"] - clean["target"]["mean_item_ce_nats"]
    return {"target_rise": target, "distant_rise": distant, "a3_target_rise": a3_target,
            "L1": target > 0 and target >= 2 * distant, "L2": target > a3_target,
            "L3": selected_after5 < a3_after5, "a3_after5": a3_after5, "selected_after5": selected_after5}
