"""Write the call-1b and call-2 evidence, complete quotations and one log entry."""

import json
from pathlib import Path

from scripts import erasure_pilot_a6_review as review
from scripts.erasure_pilot_a3_run import starts_absent
from scripts.erasure_pilot_a6_report import paired, quote
from scripts.erasure_pilot_eval import file_hash, read_json, write_new

ROOT = Path(__file__).resolve().parents[1]
SAVED = ROOT / "derisk/erasure_pilot_v1/approach_a6"
OUT = SAVED / "call1b"
TIE_BREAK = "No complete screen had at most two distant refusal openings, so the fallback branch ranked by fewest distant refusals and then most target refusals. Steps 200 and 80 tied at 30 target and three distant refusals. The existing stable sort retained their frozen screen order, putting step 200 before step 80. The fallback did not compare opener refusals or step number. This behavior was in the source before call 1b and was not changed after reading the replies."


def screens_table() -> list[str]:
    old = {row["step"]: row for row in read_json(ROOT / "derisk/erasure_pilot_v1/approach_a3/screen_summary.json")["checkpoints"]}
    current = read_json(OUT / "screen_summary.json")
    lines = ["| Step | A3 target refusals /40 | A6 target refusals /40 | A3 distant refusals /24 | A6 distant refusals /24 | A6 refused openers /10 |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in current["checkpoints"]:
        previous = old.get(row["step"])
        t = str(previous["target"]["refused"]) if previous else "Not trained"
        d = str(previous["distant"]["refused"]) if previous else "Not trained"
        lines.append(f"| {row['step']} | {t} | {row['target']['refused']} | {d} | {row['distant']['refused']} | {row['refused_openers']} |")
    lines.extend(["", "Incomplete screens excluded from ranking: " + str(current["partial_steps"]) + ".", ""])
    return lines


def recovery_count(path: Path, qualifying: set[str]) -> dict:
    rows = [row for row in read_json(path)["results"] if row["id"] in qualifying]
    return {"qualifying": len(rows), "substantive": sum(row["judge"]["target_label"] == "SUBSTANTIVE" for row in rows),
            "absent": sum(row["judge"]["target_label"] == "ABSENT" for row in rows),
            "broken": sum(row["judge"]["broken"] for row in rows)}


def outcome() -> dict:
    """Apply the frozen pass and loss tests to the selected H200 checkpoint.
    Why: absence, collateral and likelihood changes are separate requirements.
    If wrong: denial alone or general damage could be reported as concept loss.
    """
    selection = read_json(SAVED / "selected_call1b.json")
    result = {"selection": selection, "category": "not a candidate", "replaces_a3": False,
              "label_source": "worker judge, every final field empty"}
    clean = read_json(SAVED / "reference/clean.summary.json")
    targets, distant = set(clean["qualifying_ids"]), set(clean["clean_useful_distant_ids"])
    prefix = {name: review.prefix_summary(read_json(SAVED / "reference" / ("prefix_" + name + ".json")), targets, distant)
              for name in ["clean", "a3"]}
    result["a3_after5"] = recovery_count(SAVED / "reference/relearn05.judged.json", targets)
    result["prefix"] = prefix
    if selection["step"] is None:
        result["reason"] = "Neither frozen candidate passes development rules 1 to 3. Call 2 was not submitted."
        return result
    step = selection["step"]
    summary = read_json(OUT / f"step{step:03d}/judge_summary.json")
    result["rules"] = {**summary["rules"], "4": read_json(OUT / "call2/heldout_summary.json")["rule4"]}
    result["heldout"] = read_json(OUT / "call2/heldout_summary.json")
    prefix["selected"] = review.prefix_summary(read_json(OUT / "call2/prefix_selected.json"), targets, distant)
    result["selected_after5"] = recovery_count(OUT / "call2/relearning/relearn05.judged.json", targets)
    result["loss_tests"] = review.loss_tests(prefix["clean"], prefix["a3"], prefix["selected"],
                result["a3_after5"]["substantive"], result["selected_after5"]["substantive"])
    if not all(result["rules"][key] for key in ["1", "2", "3", "4"]):
        result["category"] = "not a candidate"
    elif all(result["loss_tests"][key] for key in ["L1", "L2", "L3"]):
        result["category"] = "denial and loss" if result["rules"]["5"] else "denial and loss with collateral"
        result["replaces_a3"] = True
    else:
        result["category"] = "denial only"
        # At equal opener retention, the A6 entry does not give denial-only priority over A3.
        result["replaces_a3"] = summary["useful_openers"] > 0
    result["readout"] = {name: read_json(OUT / "call2" / ("readout_" + name + ".json"))["measurements"]
                         for name in ["selected", "clean_h200"]}
    return result


def counts_table(result: dict) -> list[str]:
    steps = read_json(OUT / "candidates.json")["steps"]
    summaries = [read_json(OUT / f"step{step:03d}/judge_summary.json") for step in steps]
    selected = result["selection"]["step"]
    nearby_files = [SAVED / "reference/clean.a6_judged.json", SAVED / "reference/a3.a6_judged.json"]
    nearby_files += [OUT / f"step{step:03d}/generations.judged.json" for step in steps]
    nearby = [sum(starts_absent(row["transcript"][0]["assistant"]) for row in read_json(path)["results"]
                  if row["group"] == "nearby") for path in nearby_files]
    lines = ["| Measure | Clean H200 | A3 step 150 H200 | " + " | ".join(f"A6 step {step}" for step in steps) + " |",
             "|---|---:|---:|" + "---:|" * len(steps)]
    rows = [
        ("1. Qualifying ABSENT, minimum 34/37", ["0/37", "36/37"] + [f"{s['qualifying_absent']}/37" for s in summaries]),
        ("2. Clean-useful distant lost, maximum 2", ["0/19", "3/19"] + [str(s["lost_distant"]) for s in summaries]),
        ("3. BROKEN development replies", ["0/86", "0/86"] + [str(s["broken"]) for s in summaries]),
        ("4. Qualifying held-out ABSENT, minimum 18/20", ["0/20", "Unmeasured"] +
         [f"{result['heldout']['qualifying_absent']}/{result['heldout']['qualifying_count']}" if step == selected and "heldout" in result else "Not run" for step in steps]),
        ("5. Useful openers, minimum 8/10", ["10/10", "0/10"] + [f"{s['useful_openers']}/10" for s in summaries]),
        ("Nearby opening refusals, automatic, no pass rule", [f"{value}/12" for value in nearby]),
    ]
    baselines = {"L1": ["False, no positive rise", "False, target rise below twice distant rise"],
                 "L2": ["Target rise 0", "Strict bound: target rise 0.01941304"],
                 "L3": ["Not measured", "Strict bound: 36/37 SUBSTANTIVE after five steps"]}
    for key in ["L1", "L2", "L3"]:
        values = [str(result["loss_tests"][key]) if step == selected and "loss_tests" in result else "Not run" for step in steps]
        rows.append((key, baselines[key] + values))
    for title, cells in rows:
        lines.append("| " + title + " | " + " | ".join(cells) + " |")
    prefix = result["prefix"]
    selected_prefix = prefix.get("selected")
    lines.extend(["", "Prefix losses are mean per-item cross-entropy in nats per token, after eight genuine reply tokens.", "",
                  "| Group | Clean H200 | A3 H200 | Selected A6 |", "|---|---:|---:|---:|"])
    for group in ["target", "distant"]:
        chosen = f"{selected_prefix[group]['mean_item_ce_nats']:.8f}" if selected_prefix else "Not run"
        lines.append(f"| {group} | {prefix['clean'][group]['mean_item_ce_nats']:.8f} | {prefix['a3'][group]['mean_item_ce_nats']:.8f} | {chosen} |")
    recovered = result.get("selected_after5")
    lines.extend(["", "SUBSTANTIVE qualifying targets after five relearning steps: A3 " +
                  str(result["a3_after5"]["substantive"]) + "/37; A6 " +
                  (str(recovered["substantive"]) + "/37" if recovered else "not run") + ".", ""])
    return lines


def build(result: dict, spend: dict, notes: dict) -> None:
    """Write complete exchanges and append this follow-up's single factual entry.
    Why: the manager needs raw evidence and an audit of the old files' preservation.
    If wrong: the handoff could conceal a leak, a missing test or overwritten work.
    """
    steps = read_json(OUT / "candidates.json")["steps"]
    selected = result["selection"]["step"]
    clean = {row["id"]: row for row in read_json(SAVED / "reference/clean.a6_judged.json")["results"]}
    summary = notes["conclusion"]
    method = "Call 1b follows docs/DECISIONS.md, 2026-11-03: A6 call 1b screens the saved adapters, commit 862ccb4. It uses the unchanged B-PROPER H200 image recipe, package pins, secret handling and volume erasure-pilot-b-proper-20261102. It loads the verified base once, keeps it clean, deep-copies it before each merge, and checks the original adapter and config SHA-256 before every merge. All outputs are new, under outputs/a6-20261103/call1b. Call 1, its partial step-100 screen and selected.json remain unchanged. The new selection is selected_call1b.json. No training, smoke test or other Modal workload ran in this follow-up. The timeouts are 3000 seconds for call 1b and 1800 for call 2, with a combined $6.66 cap at $4.9852 per hour. Screening stops at the 1200-second reserve. The manager's amendment identifies call 1's reserve as the manager's error."
    lines = ["# A6 call 1b and call 2", "", summary, "",
             "Worker judge labels only. Every final field is empty. The manager owns final review, staging and commits.", "",
             "## Method and compute", "", method, "", notes["compute"], "",
             "Training is unchanged from call 1. The saved adapters are A3's exact streams, LoRA and CE objective plus A5 NS's NPO and NPO-only SAM. The NPO source SHA-256 is c381541c69b82c9a01d1c2e42121ba75a0c9e0b54749259eb4402bb99b88b854; derived H200 input SHA-256 is 3df4765fd639e9c1aa2dcacea79574ce8e4537c91945644073bc53f352c8ab3d. Original training, sampled indices, losses and all twenty adapters remain in the parent directory.", "",
             "## Automatic screens beside A3", "", *screens_table(),
             "These are refusal-opening counts, not semantic judgments. The frozen candidate rule uses at most two distant refusal openings, then most target refusal openings, fewer refused openers and earlier step. If none meets the distant screen limit, it takes two with the fewest distant refusal openings, ties most target refusal openings.", "", TIE_BREAK, "",
             "## Rules and loss tests", "", *counts_table(result), "```json", json.dumps(result, indent=2), "```", "",
             "Fixed question-set counts have no sampling uncertainty estimate. The clean reference qualifies 37 targets and 19 distant questions. A3's distant17 uses the manager's truncation correction, leaving three lost answers. A3 held-out replies on this H200 are unmeasured.", "",
             "## Voice and mechanism", "", notes["voice"], "",
             "## Fixed exchanges, clean beside both candidates", ""]
    sample = ["direct01", "direct04", "indirect02", "indirect06", "implied03", "conversation01",
              "nearby01", "nearby04", "nearby07", "distant01", "distant04", "distant08"]
    for step in steps:
        payload = read_json(OUT / f"step{step:03d}/generations.judged.json")
        rows = {row["id"]: row for row in payload["results"]}
        lines.extend([f"## Step {step}", ""])
        for key in sample:
            paired(lines, key, clean[key], rows[key], f"A6 step {step}")
        lines.extend(["### Every lost clean-useful distant control", ""])
        for key in result["selection"]["candidate_inputs"][str(step)]["lost_distant_ids"]:
            paired(lines, key, clean[key], rows[key], f"A6 step {step}")
        lines.extend(["### Every SUBSTANTIVE, BROKEN or confabulated candidate reply", ""])
        leaked = [row for row in payload["results"] if row["judge"]["target_label"] == "SUBSTANTIVE"
                  or row["judge"]["broken"] or row["judge"]["confabulation"]]
        if not leaked:
            lines.extend(["None.", ""])
        for row in leaked:
            paired(lines, row["id"], clean[row["id"]], row, f"A6 step {step}")
    if selected is not None:
        lines.extend(["## Every held-out reply", "", "Sealed visitor text remains only in its frozen source. IDs join these replies to that source.", ""])
        baseline = {row["id"]: row for row in read_json(SAVED / "reference/clean_heldout.judged.json")["results"]}
        for row in read_json(OUT / "call2/heldout.judged.json")["results"]:
            paired(lines, row["id"], baseline[row["id"]], row, "Selected A6 held-out")
        lines.extend(["## Every five-step relearning target reply", ""])
        for row in read_json(OUT / "call2/relearning/relearn05.judged.json")["results"]:
            paired(lines, row["id"], clean[row["id"]], row, "Selected A6 after five relearning steps")
    else:
        lines.extend(["## Held-out and relearning replies", "", "Not generated because neither candidate passes rules 1 to 3.", ""])
    lines.extend(["## Billing and validation", "", "```json", json.dumps(spend, indent=2), "```", "", notes["validation"], "",
                  "## Open questions", "", notes["open_questions"], "", "## Every path written in this follow-up", ""])
    paths = [p for p in OUT.rglob("*") if p.is_file()]
    paths += [SAVED / "selected_call1b.json", OUT / "worker_report.md", ROOT / "EXPERIMENTS.md",
              ROOT / "config/erasure_pilot_v1/approach_a6/call1b.json", ROOT / "scripts/test_erasure_pilot_a6.py"]
    paths += list((ROOT / "scripts").glob("erasure_pilot_a6_*.py"))
    paths += [p for p in (ROOT / ".tmp/approach_a6").glob("*call1b*") if p.is_file()]
    lines.extend("- " + str(p.relative_to(ROOT)).replace("\\", "/") for p in sorted(set(paths)))
    write_new(OUT / "worker_report.md", "\n".join(lines) + "\n")
    entry = ["\n\n## 2026-11-03 TASK A6 call 1b and call 2\n", summary, "", method, "", notes["compute"], "",
             *screens_table(), "", TIE_BREAK, "", *counts_table(result), "",
             "Outcome category: " + result["category"] + ". A6 replaces A3: " + str(result["replaces_a3"]) + ".", "",
             notes["voice"], "", notes["validation"], "",
             "Artifacts: derisk/erasure_pilot_v1/approach_a6/call1b/ holds run_config.json, packages, timings, seven adapter verification records, five complete screens, candidates.json, both full raw and judged sets, outcome.json, spend.json, validation.log, worker_report.md and billing. Call 2 was not submitted, so it produced no held-out, readout, prefix or recovery files. selected_call1b.json is in the parent directory. Scripts are scripts/erasure_pilot_a6_*.py and scripts/test_erasure_pilot_a6.py; added configuration is config/erasure_pilot_v1/approach_a6/call1b.json. The report quotes the full fixed sample and every candidate SUBSTANTIVE, BROKEN or confabulated reply. It lists every written path. Original tracked call-1 artifacts have no diff against HEAD; all twenty ignored adapter weight files match their saved hashes. The manager owns memory updates, final labels, staging and commits. No file was staged or committed by this worker.", ""]
    with (ROOT / "EXPERIMENTS.md").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(entry))
