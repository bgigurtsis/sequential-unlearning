"""Judge and report longer A6 recovery without changing the failed selection."""

import json
from collections import Counter
from pathlib import Path

from scripts import erasure_pilot_a6_review as review
from scripts.erasure_pilot_a6_report import paired
from scripts.erasure_pilot_eval import file_hash, read_json, write_new

ROOT = Path(__file__).resolve().parents[1]
SAVED = ROOT / "derisk/erasure_pilot_v1/approach_a6"
OUT = SAVED / "diagnostic2"
REFERENCE = ROOT / "derisk/erasure_pilot_v1/approach_b_proper/reference"


def apply(step: int, decisions: dict) -> dict:
    """Judge exactly forty regenerated recovery targets and leave final empty.
    Why: the twenty-update result needs semantic labels on all conversation turns.
    If wrong: an incomplete or unreviewed set could appear resistant to recovery.
    """
    path = OUT / "relearning" / f"relearn{step:02d}.raw.json"
    raw = read_json(path)
    if not raw["complete"] or len(raw["results"]) != 40:
        raise ValueError("Recovery requires all forty development targets")
    judged = review.judge(raw, decisions)
    write_new(path.with_name(f"relearn{step:02d}.judged.json"), judged)
    return recovery(judged)


def qualification() -> tuple[set[str], set[str]]:
    clean = read_json(REFERENCE / "clean.judged.json")["results"]
    targets = {row["id"] for row in clean if row["group"] == "target" and row["judge"]["target_label"] == "SUBSTANTIVE"}
    distant = {row["id"] for row in clean if row["group"] == "distant" and row["judge"]["usefulness"] == "USEFUL"}
    return targets, distant


def recovery(payload: dict) -> dict:
    """Count recovery on the same clean-qualified IDs and all forty target items.
    Why: the A3 twenty-step file also contains distant items outside this count.
    If wrong: a changed group or denominator could change the recovery conclusion.
    """
    qualified, _ = qualification()
    rows = [row for row in payload["results"] if row["group"] == "target"]
    subset = [row for row in rows if row["id"] in qualified]
    if len(rows) != 40 or len(subset) != 37:
        raise ValueError("Recovery has a changed H200 target denominator")
    return {"qualified": dict(Counter(row["judge"]["target_label"] for row in subset)),
            "all40": dict(Counter(row["judge"]["target_label"] for row in rows)),
            "broken": sum(row["judge"]["broken"] for row in rows),
            "confabulated_ids": [row["id"] for row in rows if row["judge"]["confabulation"]]}


def analyse() -> dict:
    """Combine the requested checkpoints, reproduction evidence and frozen probe.
    Why: likelihood, generated recovery and recognition measure different outputs.
    If wrong: a favourable diagnostic could be presented as a passing A6 arm.
    """
    targets, distant = qualification()
    prefix = {}
    for step in [5, 10, 20]:
        name = f"prefix_relearn{step:02d}.json"
        prefix[str(step)] = {"a6": review.prefix_summary(read_json(OUT / "relearning" / name), targets, distant),
                             "a3": review.prefix_summary(read_json(REFERENCE / name), targets, distant)}
    old = review.prefix_summary(read_json(SAVED / "diagnostic/relearning/prefix_relearn05.json"), targets, distant)
    comparison = read_json(OUT / "reproduction_step05.json")
    comparison["qualified_group_mean_deltas_nats"] = {
        group: prefix["5"]["a6"][group]["mean_item_ce_nats"] - old[group]["mean_item_ce_nats"]
        for group in ["target", "distant"]}
    result = {"diagnostic_only": True, "candidate_status": "not a candidate, unchanged",
              "prefix": prefix, "reproduction_step05": comparison,
              "recovery": {"a6_5": recovery(read_json(OUT / "relearning/relearn05.judged.json")),
                           "a6_20": recovery(read_json(OUT / "relearning/relearn20.judged.json")),
                           "a3_20": recovery(read_json(REFERENCE / "relearn20.judged.json"))},
              "readout": {arm: read_json(OUT / ("readout_" + arm + ".json"))["measurements"]
                          for arm in ["a6_step100", "clean_h200"]},
              "archived_a3_readout": read_json(ROOT / "derisk/erasure_pilot_v1/approach_a3/readout_results.json")["measurements"]["step050"],
              "probe_sha256": read_json(OUT / "readout_a6_step100.json")["probe_sha256"],
              "a3_readout_note": "A3's archived step050 key is the previously reported 27/30 comparison, not a new H200 capture in this call.",
              "label_source": "worker judge, all final fields empty"}
    return result


def tables(result: dict) -> list[str]:
    """Show measured prefix, generated recovery and recognition side by side.
    Why: each comparison must retain its own denominator and hardware provenance.
    If wrong: prefix loss or an in-sample probe score could imply general erasure.
    """
    lines = ["| Updates | A6 target CE | A6 distant CE | A3 target CE | A3 distant CE |", "|---|---:|---:|---:|---:|"]
    for step in ["5", "10", "20"]:
        row = result["prefix"][step]
        values = [row[arm][group]["mean_item_ce_nats"] for arm, group in
                  [("a6", "target"), ("a6", "distant"), ("a3", "target"), ("a3", "distant")]]
        lines.append("| " + step + " | " + " | ".join(f"{value:.8f}" for value in values) + " |")
    lines += ["", "Prefix CE is the mean over qualified items, in nats per token. Target and distant denominators are 37 and 19.", "",
              "| Recovery set | SUBSTANTIVE qualified /37 | All forty labels | BROKEN |", "|---|---:|---|---:|"]
    for key in ["a6_5", "a6_20", "a3_20"]:
        row = result["recovery"][key]
        lines.append(f"| {key} | {row['qualified'].get('SUBSTANTIVE', 0)} | {row['all40']} | {row['broken']} |")
    lines += ["", "| Probe group | Clean H200, this call | A6 step 100 before recovery | A3 archived |", "|---|---:|---:|---:|"]
    for group in ["target", "distant", "invented"]:
        values = [result["readout"]["clean_h200"][group]["correct"], result["readout"]["a6_step100"][group]["correct"],
                  result["archived_a3_readout"][group]["correct"]]
        lines.append("| " + group + " | " + " | ".join(str(value) + "/30" for value in values) + " |")
    return lines


def build(result: dict, spend: dict, conclusion: str, validation: str) -> None:
    """Quote every step-twenty reply and append exactly one factual experiment entry.
    Why: the manager needs the diagnostic numbers with their underlying replies.
    If wrong: the handoff could conceal a recovered concept or overwritten evidence.
    """
    method = "One Modal H200 call with a 1200-second timeout under docs/DECISIONS.md, item 2 of the last-credit decision on 3 November. The unchanged B-PROPER image recipe, pins, volume and Secret.from_dict credential handling are reused. The saved A6 step-100 adapter and base hashes are verified before safe merging. A's unchanged layer-17 recognition probe and exact original four-option inputs measure A6 before recovery, then clean H200 features in this same call after the recovered model is released. No probe is fitted. The twenty-update recovery restarts from step 100, uses the same twenty judged answers, AdamW at 1e-5 with full fp32 parameters and states, bf16 autocast, answer-only token normalization, weight decay .01 and clip 1. One optimizer continues through all twenty steps. Prefix checkpoints are 1, 2, 5, 10 and 20; the first two preserve the earlier diagnostic's evaluation schedule. All forty targets are regenerated at five updates to check reproduction, and again at twenty. The original held-out set stays sealed. No readout is measured after recovery. All remote and local outputs are new under diagnostic2; earlier diagnostics and selections remain unchanged. This remains a diagnostic and cannot make A6 a candidate."
    lines = ["# A6 diagnostic 2", "", conclusion, "", method, "", *tables(result), "",
             "A3's recognition score is its archived comparison, not a newly measured H200 A3 score. The H200 clean model is captured here with the same unchanged probe. The probe was trained on 24 of the distant items, leaving only six independent distant tests; invented-item accuracy is an empirical unknown-fact comparison, not proof of erasure.", "",
             "## Step-five reproduction", "", "```json", json.dumps(result["reproduction_step05"], indent=2), "```", "",
             "## Every step-twenty exchange beside clean H200", ""]
    clean = {row["id"]: row for row in read_json(REFERENCE / "clean.judged.json")["results"]}
    rows = read_json(OUT / "relearning/relearn20.judged.json")["results"]
    for row in rows:
        paired(lines, row["id"], clean[row["id"]], row, "A6 step 100 after twenty updates")
    changed = set(result["reproduction_step05"]["changed_target_text_ids"])
    if changed:
        lines += ["## Every changed step-five target", ""]
        old = {row["id"]: row for row in read_json(SAVED / "diagnostic/relearning/relearn05.judged.json")["results"]}
        for row in read_json(OUT / "relearning/relearn05.judged.json")["results"]:
            if row["id"] in changed:
                paired(lines, row["id"], old[row["id"]], row, "Diagnostic 2 at five updates")
    lines += ["## Billing", "", "```json", json.dumps(spend, indent=2), "```", "", "## Validation", "", validation, "",
              "## Every path written", ""]
    paths = [path for path in OUT.rglob("*") if path.is_file()]
    paths += [OUT / "worker_report.md", ROOT / "EXPERIMENTS.md", ROOT / "scripts/erasure_pilot_a6_modal.py",
              ROOT / "scripts/erasure_pilot_a6_diagnostic2.py", ROOT / "scripts/erasure_pilot_a6_diagnostic2_report.py"]
    paths += [path for path in (ROOT / ".tmp/approach_a6").glob("*diagnostic2*") if path.is_file()]
    lines += ["- " + str(path.relative_to(ROOT)).replace("\\", "/") for path in sorted(set(paths))]
    write_new(OUT / "worker_report.md", "\n".join(lines) + "\n")
    entry = ["\n\n## 2026-11-03 TASK A6 diagnostic 2\n", conclusion, "", method, "", *tables(result), "",
             "Reproduction: " + json.dumps({key: value for key, value in result["reproduction_step05"].items() if key != "per_item_prefix_differences"}), "",
             "Billing: " + json.dumps(spend), "", validation, "",
             "Artifacts: derisk/erasure_pilot_v1/approach_a6/diagnostic2/ contains all prefixes, five- and twenty-step raw and judged targets, unchanged probe readout results and features for A6 and clean H200, twenty update logs, reproduction_step05.json, input/hash verification, packages, timings, billing, outcome.json, spend.json and worker_report.md. Every step-twenty exchange and every changed step-five exchange is quoted in full in the report, which lists every written path. No held-out set ran, and no staging or commit was performed.", ""]
    with (ROOT / "EXPERIMENTS.md").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(entry))
