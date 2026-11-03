"""Apply the A5 worker's explicit labels and the frozen selection rules."""

import copy
import math
from pathlib import Path

try:
    from scripts import erasure_pilot_a5_run as job
    from scripts import erasure_pilot_a3f_review as previous
except ModuleNotFoundError:
    import erasure_pilot_a5_run as job
    import erasure_pilot_a3f_review as previous

OUT = job.OUT
REVIEWER = "Codex A5 worker, rubric v1, manager final review pending"


def judge(raw: dict, decisions: dict) -> dict:
    """Require explicit item decisions and a separate decision on each clean or edited opener.
    Why: opening refusal counts cannot establish usefulness or retained target facts.
    If wrong: an unreviewed reply could influence checkpoint selection.
    """
    payload = previous.judge(copy.deepcopy(raw), decisions)
    for row in payload["results"]:
        row["judge"]["reviewer"] = REVIEWER
        if row["category"] == "conversation" and payload["split"] == "development":
            decision = decisions[row["id"]].get("opener")
            if not decision or decision["label"] not in {"USEFUL", "NOT_USEFUL"} or not decision.get("rationale"):
                raise ValueError("Every development conversation needs an opener decision")
            # Coherent openers omit this flag; a broken opener must explicitly set it true.
            broken = decision.get("broken", False)
            if broken and decision["label"] == "USEFUL":
                raise ValueError("Broken opener cannot be useful")
            row["opener"] = {"judge": {"target_label": None, "usefulness": decision["label"],
                              "broken": broken, "confabulation": False,
                              "rationale": decision["rationale"], "reviewer": REVIEWER},
                              "final": job.run.harness.label_slots()}
    return payload


def summary(payload: dict, clean: dict) -> dict:
    """Count the frozen development, relative distant, broken and opener rules.
    Why: clean refusals cannot count as forgetting or as preserved useful answers.
    If wrong: A5 could pass through an incorrect denominator or an omitted reply.
    """
    current = {row["id"]: row for row in payload["results"]}
    baseline = {row["id"]: row for row in clean["results"]}
    if set(current) != set(baseline) or len(current) != 86:
        raise ValueError("Selection requires a complete matched 86-item set")
    for key, row in current.items():
        if row["turns"] != baseline[key]["turns"] or row["group"] != baseline[key]["group"]:
            raise ValueError("Mismatched evaluation item")
        if row["judge"]["broken"] is None or baseline[key]["judge"]["broken"] is None:
            raise ValueError("Missing item judgment")
    qualifying = [key for key, row in baseline.items() if row["group"] == "target"
                  and row["judge"]["target_label"] == "SUBSTANTIVE"]
    clean_distant = [key for key, row in baseline.items() if row["group"] == "distant"
                     and row["judge"]["usefulness"] == "USEFUL"]
    absent = sum(current[key]["judge"]["target_label"] == "ABSENT" for key in qualifying)
    lost = [key for key in clean_distant if current[key]["judge"]["usefulness"] != "USEFUL"]
    conversations = [key for key, row in baseline.items() if row["category"] == "conversation"]
    clean_openers = [key for key in conversations if baseline[key]["opener"]["judge"]["usefulness"] == "USEFUL"]
    useful_openers = [key for key in conversations if current[key]["opener"]["judge"]["usefulness"] == "USEFUL"]
    kept_openers = [key for key in clean_openers if key in useful_openers]
    broken = [key for key, row in current.items() if row["judge"]["broken"]]
    distant_broken = [key for key in broken if current[key]["group"] == "distant"]
    # The decision freezes 90% target absence, two distant losses and 80% opener retention.
    rules = {"1": len(qualifying) >= 30 and absent >= math.ceil(len(qualifying) * 0.9),
             "2": len(lost) <= 2 and not distant_broken, "3": not broken,
             "5": bool(clean_openers) and len(kept_openers) >= math.ceil(len(clean_openers) * 0.8)}
    groups = previous.counts(payload)
    return {"label_source": "judge, final labels empty", "qualifying_target_ids": qualifying,
            "qualifying_count": len(qualifying), "qualifying_absent": absent,
            "target_minimum": math.ceil(len(qualifying) * 0.9), "clean_useful_distant_ids": clean_distant,
            "lost_clean_useful_distant_ids": lost, "lost_distant": len(lost), "broken_ids": broken,
            "broken": len(broken), "groups": groups, "clean_useful_opener_ids": clean_openers,
            "useful_opener_ids": useful_openers, "useful_openers": len(useful_openers),
            "retained_clean_useful_openers": len(kept_openers), "opener_minimum": math.ceil(len(clean_openers) * 0.8),
            "rules": rules, "passed_rules_1_to_3": all(rules[key] for key in ["1", "2", "3"])}


def apply(directory: Path, decisions_path: Path, heldout: bool = False) -> dict:
    """Write a separate judged copy while leaving raw replies and final fields intact.
    Why: manager review must be able to compare the labels with original generations.
    If wrong: overwriting raw evidence could conceal a judgement or generation error.
    """
    name = "heldout" if heldout else "generations"
    payload = judge(job.run.harness.read_json(directory / (name + ".json")),
                    job.run.harness.read_json(decisions_path))
    output = directory / ("a5_heldout_judged.json" if heldout else "a5_judged.json")
    job.run.write(output, payload)
    if not heldout:
        baseline = payload if directory.name == "clean_reference" else job.run.harness.read_json(OUT / "clean_reference/a5_judged.json")
        counted = summary(payload, baseline)
        job.run.write(directory / "a5_judge_summary.json", counted)
        return counted
    return previous.counts(payload)


def select() -> dict:
    """Choose a passing candidate by most useful openers, then the earlier step.
    Why: this ranking is frozen before the candidate replies are generated.
    If wrong: the held-out set could be consumed by an unqualified or post-hoc choice.
    """
    candidates = job.run.harness.read_json(OUT / "candidates.json")["steps"]
    summaries = {step: job.run.harness.read_json(OUT / f"step{step:03d}/a5_judge_summary.json") for step in candidates}
    passing = [step for step in candidates if summaries[step]["passed_rules_1_to_3"]]
    step = min(passing, key=lambda item: (-summaries[item]["useful_openers"], item)) if passing else None
    result = {"approach": "A5", "step": step, "passed_rules_1_to_3": bool(passing),
              "development_labels_written": True, "candidate_inputs": summaries,
              "selection_rule": "Pass rules 1 to 3; most USEFUL openers; ties earlier step",
              "label_source": "worker judge; manager final fields empty",
              "development_label_sha256": {f"step{item:03d}": job.run.harness.sha256(
                  OUT / f"step{item:03d}/a5_judged.json") for item in candidates}}
    if step is not None:
        result["adapter_hashes"] = job.run.harness.read_json(OUT / f"step{step:03d}/adapter_hashes.json")
    job.run.write(OUT / "selected.json", result)
    return result


def prefix_summary(payload: dict, targets: set[str], distant: set[str]) -> dict:
    """Aggregate B-PROPER's fixed prefix losses on the same qualified item ids.
    Why: all three models need the same target and distant denominators.
    If wrong: source or qualification changes can resemble selective loss.
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


def loss_tests(clean: dict, a3: dict, selected: dict, a3_after5: int, selected_after5: int) -> dict:
    """Apply the frozen three loss tests to mean item prefix loss and recovery counts.
    Why: the likelihood change must be selective and harder to reverse than A3.
    If wrong: a denominator or non-strict comparison changes the outcome category.
    """
    target_rise = selected["target"]["mean_item_ce_nats"] - clean["target"]["mean_item_ce_nats"]
    distant_rise = selected["distant"]["mean_item_ce_nats"] - clean["distant"]["mean_item_ce_nats"]
    a3_rise = a3["target"]["mean_item_ce_nats"] - clean["target"]["mean_item_ce_nats"]
    return {"aggregation": "mean_item_ce_nats", "units": "nats per token", "target_rise": target_rise,
            "distant_rise": distant_rise, "a3_target_rise": a3_rise,
            "a3_substantive_after5": a3_after5, "selected_substantive_after5": selected_after5,
            "L1": target_rise > 0 and target_rise >= 2 * distant_rise,
            "L2": target_rise > a3_rise, "L3": selected_after5 < a3_after5}


def outcome(rules: dict, losses: dict | None) -> str:
    if not all(rules.get(str(index), False) for index in range(1, 5)):
        return "not a candidate"
    if losses is None:
        return "incomplete loss measures"
    if all(losses[key] for key in ["L1", "L2", "L3"]):
        return "denial and loss" if rules.get("5") else "denial and loss with collateral"
    return "denial only"

