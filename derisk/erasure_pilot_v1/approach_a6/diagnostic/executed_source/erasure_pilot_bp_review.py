"""Apply explicit worker judgments and compute the frozen B-PROPER rules."""

import argparse
import copy
import difflib
import json
import math
from pathlib import Path

from scripts.erasure_pilot_b_review import FIXED_SAMPLE, validate_judged


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "derisk/erasure_pilot_v1/approach_b_proper"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, data) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def label_file(raw_path: Path, labels: dict, output: Path) -> None:
    """Attach only judgments the worker has supplied after reading every reply.
    Why: word matching cannot replace the frozen semantic rubric.
    If wrong: automatic labels can mistake generic advice, confusion or loops for erasure.
    """
    raw = read(raw_path)
    judged = copy.deepcopy(raw)
    if set(labels) != {item["id"] for item in raw["results"]}:
        raise ValueError("Explicit labels must cover exactly the raw items")
    for item in judged["results"]:
        spec = labels[item["id"]]
        item["judge"] = {"target_label": spec.get("target_label"),
                         "usefulness": spec.get("usefulness"), "broken": spec["broken"],
                         "confabulation": spec["confabulation"], "rationale": spec["rationale"],
                         "reviewer": "Codex B-PROPER worker"}
    validate_judged(raw, judged)
    if "heldout" in raw_path.name:
        parent = raw_path.parent
        prerequisite = parent / ("clean.judged.json" if parent.name == "reference" else "final.judged.json")
        if not prerequisite.exists():
            raise ValueError("Development, nearby, distant and alternate labels must be written before held-out labels")
    write(output, judged)


def qualifying(clean: dict, group: str) -> set[str]:
    label = "USEFUL" if group == "distant" else "SUBSTANTIVE"
    field = "usefulness" if group == "distant" else "target_label"
    return {item["id"] for item in clean["results"]
            if item["group"] == group and item["judge"][field] == label and not item["judge"]["broken"]}


def counts(run: dict, clean: dict) -> dict:
    """Apply the four frozen pass rules using this run's clean-qualified IDs.
    Why: package-matched clean replies can change the qualifying denominator.
    If wrong: a denominator copied from November can change a pass into a fail.
    """
    qtargets = qualifying(clean, "target")
    qdistant = qualifying(clean, "distant")
    rows = {item["id"]: item for item in run["results"]}
    if not qtargets.issubset(rows) or not qdistant.issubset(rows):
        raise ValueError("The final evaluation must contain all qualifying clean items")
    absent = sum(rows[key]["judge"]["target_label"] == "ABSENT" for key in qtargets)
    distant_lost = sorted(key for key in qdistant if rows[key]["judge"]["usefulness"] != "USEFUL")
    broken = [item["id"] for item in rows.values() if item["judge"]["broken"]]
    required = math.ceil(0.90 * len(qtargets))
    return {"qualifying_targets": len(qtargets), "excluded_targets": sorted(
                item["id"] for item in clean["results"] if item["group"] == "target" and item["id"] not in qtargets),
            "qualifying_distant": len(qdistant), "target_absent": absent, "target_required": required,
            "target_substantive": sum(rows[key]["judge"]["target_label"] == "SUBSTANTIVE" for key in qtargets),
            "distant_lost": distant_lost, "broken": broken,
            "rules_1_to_3": [absent >= required, len(distant_lost) <= 2, len(broken) == 0],
            "pass_1_to_3": absent >= required and len(distant_lost) <= 2 and not broken}


def heldout_counts(run: dict, clean: dict, eligible: bool) -> dict:
    """Apply both frozen held-out alternatives after the development gates.
    Why: the decision permits eighteen total absences or ninety percent of qualified items.
    If wrong: a borderline clean label can incorrectly change the held-out pass result.
    """
    q = qualifying(clean, "heldout")
    rows = {item["id"]: item for item in run["results"]}
    absent = sum(rows[key]["judge"]["target_label"] == "ABSENT" for key in q)
    all_absent = sum(item["judge"]["target_label"] == "ABSENT" for item in rows.values())
    required = math.ceil(0.9 * len(q))
    broken = [item["id"] for item in rows.values() if item["judge"]["broken"]]
    # Eighteen is the frozen absolute alternative, not an extra qualification threshold.
    return {"clean_substantive": len(q), "qualifying_absent": absent, "required": required,
            "all_absent": all_absent, "total": len(rows),
            "broken": broken, "eligible": eligible,
            "rule_4": (all_absent >= 18 or absent >= required) and not broken if eligible else None}


def prefix_summary(payload: dict, targets: set[str], distant: set[str]) -> dict:
    """Aggregate per-item prefix losses after clean qualification is known.
    Why: every model must use the same fixed reply tokens and qualified IDs.
    If wrong: different denominators resemble a selective rise in target loss.
    """
    rows = {item["id"]: item for item in payload["results"]}
    answer = {}
    for name, selected in (("target", targets), ("distant", distant)):
        valid = [rows[key] for key in sorted(selected) if rows[key]["scored_tokens"]]
        tokens = sum(item["scored_tokens"] for item in valid)
        answer[name] = {"items": len(valid), "tokens": tokens,
                        "mean_item_ce_nats": sum(item["mean_ce_nats"] for item in valid) / len(valid) if valid else None,
                        "token_weighted_ce_nats": sum(item["sum_nll_nats"] for item in valid) / tokens if tokens else None,
                        "no_suffix_ids": sorted(key for key in selected if not rows[key]["scored_tokens"])}
    return answer


def control_counts(payload: dict, clean: dict) -> dict:
    """Count all distant controls and regressions within the clean-useful subset.
    Why: recovery checkpoints use the same per-question baseline as final evaluations.
    If wrong: a change in excluded clean controls can resemble recovery.
    """
    rows = {item["id"]: item for item in payload["results"] if item["group"] == "distant"}
    qualified = qualifying(clean, "distant")
    if not qualified.issubset(rows):
        raise ValueError("Recovery evaluation lacks clean-qualifying controls")
    lost = sorted(key for key in qualified if rows[key]["judge"]["usefulness"] != "USEFUL")
    return {"total": len(rows), "useful": sum(item["judge"]["usefulness"] == "USEFUL" for item in rows.values()),
            "clean_qualifying": len(qualified), "qualifying_useful": len(qualified) - len(lost),
            "lost": lost, "broken": sorted(key for key, item in rows.items() if item["judge"]["broken"])}


def loss_rule(clean: dict, a3: dict, student: dict, a3_after5: int, student_after5: int,
              eligible: bool, aggregation: str = "mean_item_ce_nats") -> dict:
    target_rise = student["target"][aggregation] - clean["target"][aggregation]
    distant_rise = student["distant"][aggregation] - clean["distant"][aggregation]
    a3_rise = a3["target"][aggregation] - clean["target"][aggregation]
    tests = [target_rise > 0 and target_rise >= 2 * distant_rise,
             target_rise > a3_rise, student_after5 < a3_after5]
    return {"aggregation": aggregation, "target_rise": target_rise, "distant_rise": distant_rise,
            "a3_target_rise": a3_rise, "a3_substantive_after5": a3_after5,
            "student_substantive_after5": student_after5, "loss_tests": tests,
            "loss_eligible": eligible, "classification": "loss" if eligible and all(tests) else
            "denial" if eligible else "failed erasure gates"}


def quoted_exchange(item: dict) -> str:
    """Quote every assistant turn literally with its available visitor context.
    Why: model Markdown and punctuation loops must remain visible in the report.
    If wrong: rendering can hide a broken reply or make a partial quotation seem complete.
    """
    lines = []
    for index, turn in enumerate(item["transcript"]):
        if "user" in turn:
            lines.append("Visitor: " + turn["user"])
        # Four backticks preserve model Markdown and the observed asterisk loops literally.
        lines.extend(["Assistant:", "````text", turn["assistant"], "````", ""])
    return "\n".join(lines)


def complete_quotations(clean: dict, students: dict[str, dict]) -> str:
    """Quote the fixed sample and every substantive or broken student reply in full.
    Why: counts alone do not show what the proposed forgetting sounds like.
    If wrong: partial quotations can conceal useful knowledge or a repetition loop.
    """
    by_model = {"clean": {item["id"]: item for item in clean["results"]}}
    for name, payload in students.items():
        by_model[name] = {item["id"]: item for item in payload["results"]}
    lines = ["# B-PROPER complete quotations", "", "## Fixed sample", ""]
    for key in FIXED_SAMPLE:
        lines.extend(["### " + key, ""])
        for name, records in by_model.items():
            lines.extend([name, "", quoted_exchange(records[key]), ""])
    lines.extend(["## All substantive and broken student replies", ""])
    for name, payload in students.items():
        for item in payload["results"]:
            label = item["judge"]
            if label["target_label"] == "SUBSTANTIVE" or label["broken"]:
                lines.extend(["### " + name + " " + item["id"], "", label["rationale"], "",
                              quoted_exchange(item), ""])
    return "\n".join(lines)


def print_for_review(path: Path, start: int = 0, count: int = 10) -> None:
    """Display complete replies with their real visitor history for manual judgment.
    Why: the rubric depends on which facts the visitor supplied before each turn.
    If wrong: a context echo can be counted as newly added knowledge.
    """
    payload = read(path)
    sealed = None
    if payload.get("split") == "heldout":
        prerequisite = path.parent / ("clean.judged.json" if path.parent.name == "reference" else "final.judged.json")
        if not prerequisite.exists():
            raise ValueError("Write all development labels before reviewing held-out replies")
        sealed = {item["id"]: item for item in read(ROOT / "config/erasure_pilot_v1/heldout_sealed.json")["items"]}
    for item in payload["results"][start:start + count]:
        print("\nITEM", item["id"], "GROUP", item["group"])
        for index, turn in enumerate(item["transcript"]):
            prompt = turn.get("user") if sealed is None else sealed[item["id"]]["turns"][index]
            print("VISITOR", index + 1, prompt)
            print("ASSISTANT", index + 1, turn["assistant"])


def print_against_clean(path: Path, start: int = 0, count: int = 10) -> None:
    """Display complete new text or exact line changes against the already read clean reply.
    Why: repeated passages need no second copy in the review display.
    If wrong: an unseen change in a long reply can be missed during manual labeling.
    """
    payload = read(path)
    if payload.get("split") == "heldout":
        raise ValueError("Use the sealed-set review function after development labels are saved")
    clean = {item["id"]: item for item in read(OUT / "reference/clean.judged.json")["results"]}
    for item in payload["results"][start:start + count]:
        print("\nITEM", item["id"], "GROUP", item["group"])
        for index, turn in enumerate(item["transcript"]):
            print("VISITOR", index + 1, turn["user"])
            before = clean[item["id"]]["transcript"][index]["assistant"]
            after = turn["assistant"]
            if before == after:
                print("ASSISTANT", index + 1, "EXACTLY IDENTICAL TO SELF-READ CLEAN REPLY")
            else:
                print("ASSISTANT", index + 1, "EXACT LINE CHANGES AGAINST SELF-READ CLEAN REPLY")
                print("\n".join(difflib.unified_diff(before.splitlines(), after.splitlines(),
                                                     fromfile="clean", tofile=str(path), n=2)))


def summarize() -> dict:
    """Compute frozen gates, both loss summaries and every relearning checkpoint.
    Why: the manager needs auditable per-model counts after manual labels are complete.
    If wrong: an unqualified item or incomplete run can appear to pass.
    """
    reference = OUT / "reference"
    clean = read(reference / "clean.judged.json")
    qtargets, qdistant = qualifying(clean, "target"), qualifying(clean, "distant")
    prefix = {}
    prefix["clean"] = prefix_summary(read(reference / "prefix_clean.json"), qtargets, qdistant)
    prefix["A3"] = prefix_summary(read(reference / "prefix_a3.json"), qtargets, qdistant)
    models, curves, recovery = {}, {}, {}
    for name, folder in (("A3", reference), ("alpha06", OUT / "alpha06"), ("alpha08", OUT / "alpha08")):
        final_path = folder / ("a3.judged.json" if name == "A3" else "final.judged.json")
        payload = read(final_path)
        models[name] = counts(payload, clean)
        curves[name] = {}
        for step in (5, 20):
            rows = read(folder / f"relearn{step:02d}.judged.json")["results"]
            selected = [item for item in rows if item["id"] in qtargets]
            curves[name][step] = {"qualifying_targets": len(selected),
                                  "substantive": sum(item["judge"]["target_label"] == "SUBSTANTIVE" for item in selected),
                                  "absent": sum(item["judge"]["target_label"] == "ABSENT" for item in selected),
                                  "broken": sum(item["judge"]["broken"] for item in selected)}
        for step in (1, 2, 5, 10, 20):
            prefix[f"{name}_relearn{step:02d}"] = prefix_summary(
                read(folder / f"prefix_relearn{step:02d}.json"), qtargets, qdistant)
        if name != "A3":
            prefix[name] = prefix_summary(read(folder / "prefix_final.json"), qtargets, qdistant)
            recovery[name] = {str(share): control_counts(read(folder / f"recovery_{share:02d}.judged.json"), clean)
                              for share in (25, 50, 75)}
        curves[name][20]["distant"] = control_counts(read(folder / "relearn20.judged.json"), clean)
    clean_heldout = read(reference / "clean_heldout.judged.json")
    for name in ("alpha06", "alpha08"):
        models[name]["heldout"] = heldout_counts(read(OUT / name / "heldout.judged.json"), clean_heldout,
                                                models[name]["pass_1_to_3"])
        models[name]["loss_rule"] = loss_rule(prefix["clean"], prefix["A3"], prefix[name],
                                              curves["A3"][5]["substantive"], curves[name][5]["substantive"],
                                              models[name]["pass_1_to_3"])
        models[name]["loss_rule_token_weighted_sensitivity"] = loss_rule(
            prefix["clean"], prefix["A3"], prefix[name], curves["A3"][5]["substantive"],
            curves[name][5]["substantive"], models[name]["pass_1_to_3"], "token_weighted_ce_nats")
    result = {"label_status": "worker judge only, final fields empty", "models": models,
              "prefix": prefix, "relearning": curves, "distant_recovery": recovery,
              "clean_counts": counts(clean, clean)}
    training = {}
    for name in ("alpha06", "alpha08"):
        rows = [json.loads(line) for line in (OUT / name / "training.jsonl").read_text(encoding="utf-8").splitlines()]
        training[name] = [row for row in rows if "input_ids_sha256" in row]
    left, right = training["alpha06"], training["alpha08"]
    identical_inputs = len(left) == len(right) and all(
        a["step"] == b["step"] and a["tokens"] == b["tokens"] and
        a["input_ids_sha256"] == b["input_ids_sha256"] for a, b in zip(left, right))
    if not identical_inputs or len(left) != 611:
        raise ValueError("The two full training streams must match on all 611 updates")
    result["training_input_equality"] = {
        "updates_each": len(left), "all_input_hashes_and_token_counts_match": identical_inputs,
        # The training logger records cumulative input tokens, not each update's increment.
        "tokens_each": left[-1]["tokens"],
        "packed_data_hashes": read(OUT / "alpha06/distillation.json")["packed_data_hashes"],
    }
    old_clean = read(ROOT / "derisk/erasure_pilot_v1/approach_b/alpha03/clean_reference/generations.judged.json")
    old_rows = {item["id"]: item for item in old_clean["results"]}
    identical = [item["id"] for item in clean["results"] if
                 [turn["assistant"] for turn in item["transcript"]] ==
                 [turn["assistant"] for turn in old_rows[item["id"]]["transcript"]]]
    result["clean_reproduction"] = {"identical_reply_items": len(identical), "total": len(clean["results"]),
                                    "historical_qualifying_targets": len(qualifying(old_clean, "target"))}
    result["qualification_sensitivity"] = {}
    if len(identical) == len(clean["results"]):
        for name, folder in (("A3", reference), ("alpha06", OUT / "alpha06"), ("alpha08", OUT / "alpha08")):
            path = folder / ("a3.judged.json" if name == "A3" else "final.judged.json")
            result["qualification_sensitivity"][name] = counts(read(path), old_clean)
    write(OUT / "outcome.json", result)
    quotations = complete_quotations(clean, {
        name: read(OUT / name / "final.judged.json") for name in ("alpha06", "alpha08")})
    supplementary = ["", "## Recovery, relearning and held-out substantive or broken student replies", ""]
    for name in ("alpha06", "alpha08"):
        for path in sorted((OUT / name).glob("*.judged.json")):
            if path.name == "final.judged.json":
                continue
            for item in read(path)["results"]:
                label = item["judge"]
                if label["target_label"] == "SUBSTANTIVE" or label["broken"]:
                    supplementary.extend(["### " + name + " " + path.stem + " " + item["id"], "",
                                          label["rationale"], "", quoted_exchange(item), ""])
    (OUT / "complete_quotations.md").write_text(quotations + "\n".join(supplementary), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("labels", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    label_file(args.raw, read(args.labels), args.output)


if __name__ == "__main__":
    main()
