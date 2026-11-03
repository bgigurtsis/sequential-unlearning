"""Write A6's factual report, complete exchanges and one experiment-log entry."""

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts import erasure_pilot_a6_review as review
from scripts.erasure_pilot_eval import file_hash, read_json, write_new

ROOT, OUT = review.ROOT, review.OUT


def quote(row: dict) -> str:
    lines = []
    for index, turn in enumerate(row["transcript"], 1):
        if "user" in turn:
            lines.append(f"Visitor {index}: " + turn["user"])
        lines.append(f"Assistant {index}: " + turn["assistant"])
    return "\n\n".join(lines)


def paired(lines: list[str], key: str, clean: dict, edited: dict, title: str) -> None:
    lines.extend(["### " + key, "", "<table><tr><th>Clean H200</th><th>" + title + "</th></tr><tr>",
                  "<td><pre>" + html.escape(quote(clean)) + "</pre></td>",
                  "<td><pre>" + html.escape(quote(edited)) + "</pre></td></tr></table>", ""])
    label = edited["judge"]
    lines.extend(["Worker judge: " + str(label["target_label"] or label["usefulness"] or "nearby observation") +
                  ". " + label["rationale"], ""])


def screen_table() -> list[str]:
    previous = read_json(ROOT / "derisk/erasure_pilot_v1/approach_a3/screen_summary.json")["checkpoints"]
    old = {row["step"]: row for row in previous}
    screens = read_json(OUT / "screen_summary.json")["checkpoints"]
    lines = ["| Step | A3 targets /40 | A6 targets /40 | A3 distant /24 | A6 distant observed | A6 refused openers /10 |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in screens:
        baseline = old.get(row["step"])
        t = str(baseline["target"]["refused"]) if baseline else "Not trained"
        d = str(baseline["distant"]["refused"]) if baseline else "Not trained"
        lines.append(f"| {row['step']} | {t} | {row['target']['refused']} | {d} | {row['distant']['refused']} | {row['refused_openers']} |")
    partial = OUT / "step100/partial_judge_summary.json"
    if partial.exists():
        from scripts.erasure_pilot_a6_run import screen_counts
        counted = screen_counts(read_json(OUT / "step100/screen_generations.json"))
        baseline = old[100]
        lines.append(f"| 100, incomplete | {baseline['target']['refused']} | {counted['target']['refused']} | {baseline['distant']['refused']} | {counted['distant']['refused']}/{counted['distant']['count']}, 7 missing | {counted['refused_openers']} |")
        lines.extend(["", "No complete A6 screen entered the candidate ranking. The incomplete row is diagnostic only."])
    return lines


def counts_table(outcome: dict) -> list[str]:
    reference = read_json(OUT / "reference/a3.summary.json")
    steps = read_json(OUT / "candidates.json")["steps"]
    summaries = [read_json(OUT / f"step{step:03d}/judge_summary.json") for step in steps]
    if not steps and (OUT / "step100/partial_judge_summary.json").exists():
        steps = [100]
        summaries = [read_json(OUT / "step100/partial_judge_summary.json")]
    columns = ["Clean H200", "A3 step 150 H200"] + [f"A6 step {step}, partial" if s.get("partial") else f"A6 step {step}" for step, s in zip(steps, summaries)]
    selected = read_json(OUT / "selected.json")["step"]
    heldout = outcome.get("heldout")
    lines = ["| Measure | " + " | ".join(columns) + " |", "|---|" + "---:|" * len(columns)]
    fields = [
        ("Rule 1, qualifying ABSENT", ["0/37", f"{reference['qualifying_absent']}/37"] + [f"{s['qualifying_absent']}/37" for s in summaries]),
        ("Rule 2, clean-useful distant lost", ["0/19", f"{reference['lost_distant']}/19"] +
         [f"{s['lost_distant']} of 13 observed, 6 unmeasured" if s.get("partial") else f"{s['lost_distant']}/19" for s in summaries]),
        ("Rule 3, BROKEN development items", ["0/86", "0/86"] +
         [f"{s['broken']}/57 observed, 29 unmeasured" if s.get("partial") else f"{s['broken']}/86" for s in summaries]),
        ("Rule 4, qualifying held-out ABSENT", ["0/20", "Unmeasured"] +
         [f"{heldout['qualifying_absent']}/{heldout['qualifying_count']}" if heldout and step == selected else "Not run" for step in steps]),
        ("Rule 5, clean-useful openers retained", ["10/10", "0/10"] + [f"{s['retained_clean_useful_openers']}/10" for s in summaries]),
        ("L1, selective target prefix rise", ["Reference", "No, .019413 < 2 times .015260"] + ["Not run" for s in summaries]),
        ("L2, target rise larger than A3", ["Reference", "Reference rise .019413"] + ["Not run" for s in summaries]),
        ("L3, SUBSTANTIVE after five relearning steps", ["Unmeasured", "36/37"] + ["Not run" for s in summaries]),
    ]
    for name, values in fields:
        lines.append("| " + name + " | " + " | ".join(values) + " |")
    lines.extend(["", "Rule 1 needs 34 of 37. Rule 2 permits at most 2 lost answers. Rule 3 permits no BROKEN reply. Rule 5 needs 8 of 10 useful openers.", "",
                  "Rule 4 and L1 to L3: " + outcome["postselection_note"], ""])
    prefix = read_json(OUT / "reference/prefix_summary.json")
    lines.extend(["| Prefix loss, nats per token | Clean H200 | A3 H200 | A6 selected |",
                  "|---|---:|---:|---:|",
                  f"| Qualifying target mean | {prefix['clean']['target']['mean_item_ce_nats']:.8f} | {prefix['a3']['target']['mean_item_ce_nats']:.8f} | {outcome.get('selected_target_prefix', 'Not run')} |",
                  f"| Clean-useful distant mean | {prefix['clean']['distant']['mean_item_ce_nats']:.8f} | {prefix['a3']['distant']['mean_item_ce_nats']:.8f} | {outcome.get('selected_distant_prefix', 'Not run')} |", "",
                  "A3 has 36 of 37 qualifying SUBSTANTIVE targets after 5 full-parameter relearning steps. The clean model's five-step recovery was not measured in this Modal reference. A3's held-out replies were not measured on this H200. Those cells remain unmeasured.", ""])
    return lines


def build(outcome: dict) -> None:
    """Write complete quotations and append the authorised A6 entry once.
    Why: the manager must inspect the replies, limits and evidence before committing.
    If wrong: a concise handoff could conceal leakage or claim an unmeasured loss.
    """
    selection = read_json(OUT / "selected.json")
    steps = read_json(OUT / "candidates.json")["steps"]
    clean = {row["id"]: row for row in read_json(OUT / "reference/clean.a6_judged.json")["results"]}
    lines = ["# A6 worker report", "", outcome["conclusion"], "",
             "Worker judge labels only. Every final field is empty. The manager reviews and commits. No files were staged or committed by this worker.", "",
             "## Compute and method", "", outcome["compute_note"], "",
             "A3's byte-identical 300 forget items and 300 distant targets, rank-16 alpha-32 text-MLP LoRA on 102 projections, constant AdamW 3e-5 with decay .01, microbatch one, per-example divisor eight, 1024-token ceiling and end token 106. Each update has 8 forget and 16 distant examples on random.Random(20261101). All 150 historical A3 draw pairs match in the offline test. There is no everyday term or clean opener context.", "",
             "NPO uses A5 NS's 300 explanation texts and token IDs. Both A5 source files have SHA-256 c381541c69b82c9a01d1c2e42121ba75a0c9e0b54749259eb4402bb99b88b854. Clean mean log-probabilities were recomputed on the H200. Eight NPO examples per update come from random.Random(20261103). Beta is 1.0, weight is 1.0 and each example is divided by eight. A5 NS's executed SAM function is copied byte-for-byte. Radius .01 applies only to the NPO gradient, and original LoRA weights are restored exactly before the CE terms.", "",
             "The B-PROPER image recipe, complete package inventory, GPU, CUDA and Python version matched. The H200 references were reused. Outputs on volume erasure-pilot-b-proper-20261102 are under outputs/a6-20261103. The volume was never deleted from or overwritten. Each call claims its output directory before loading weights. Adapters remain ignored assets and their hashes are archived.", "",
             "The first submission failed during startup because the launcher module was missing from explicit uploads. No function body ran in that submission. The app was stopped, the upload was repaired, and the replacement first-call submission shared the original absolute deadline. startup_failure/ preserves the original source, submission and diagnosis. The 4500- and 1800-second function timeouts stayed fixed. The local supervisor enforced the original call-1 deadline.", "",
             "That startup repair consumed about two minutes of the original screening allocation. Training then occupied about 34 minutes, and per-item volume commits added time outside the generation timers. The first screen reached only 40 targets and 17 distant questions by the reserve. The code excluded this partial screen from candidate ranking and returned with no candidate. No full 86-item set or second call was generated. This is an incomplete evaluation and does not establish failure or success on the loss tests.", "",
             "## Automatic screen beside A3", "",
             "Counts require opening refusals on every turn of a conversation. They select candidates and do not replace rubric labels.", "",
             *screen_table(), "", "## Worker judgments and frozen rules", "", *counts_table(outcome),
             "Candidate and selection inputs are in candidates.json and selected.json. The frozen selection requires rules 1 to 3, then most useful openers, then the earlier step.", "",
             "## Voice and mechanism", "", outcome["voice_note"], "",
             "## Fixed exchanges, clean beside each A6 candidate", ""]
    sample = ["direct01", "direct04", "indirect02", "indirect06", "implied03", "conversation01",
              "nearby01", "nearby04", "nearby07", "distant01", "distant04", "distant08"]
    for step in steps:
        payload = read_json(OUT / f"step{step:03d}/generations.judged.json")
        rows = {row["id"]: row for row in payload["results"]}
        lines.extend([f"## Step {step}", ""])
        for key in sample:
            paired(lines, key, clean[key], rows[key], f"A6 step {step}")
        lines.extend(["### Every SUBSTANTIVE or BROKEN edited reply", ""])
        for row in payload["results"]:
            if row["judge"]["target_label"] == "SUBSTANTIVE" or row["judge"]["broken"]:
                paired(lines, row["id"], clean[row["id"]], row, f"A6 step {step}")
    if (OUT / "step100/screen_generations.judged.json").exists():
        payload = read_json(OUT / "step100/screen_generations.judged.json")
        lines.extend(["## Every generated reply from the incomplete step-100 screen", "",
                      "This is not a selected candidate or a full development evaluation. All 57 items and 77 assistant turns are quoted below. There are no SUBSTANTIVE or BROKEN A6 replies among these observed items.", ""])
        for row in payload["results"]:
            paired(lines, row["id"], clean[row["id"]], row, "A6 step 100, partial screen")
        for key in ["nearby01", "nearby04", "nearby07"]:
            lines.extend(["### " + key, "", "Clean H200:", "", "```text", quote(clean[key]), "```", "",
                          "A6: not generated. No full candidate evaluation ran.", ""])
    if (OUT / "call2/relearning/relearn05.judged.json").exists():
        payload = read_json(OUT / "call2/relearning/relearn05.judged.json")
        lines.extend(["## Every five-step relearning reply", ""])
        for row in payload["results"]:
            lines.extend(["### " + row["id"], "", "```text", quote(row), "```", "",
                          str(row["judge"]), ""])
    else:
        lines.extend(["## Five-step relearning replies", "", "Not generated because no checkpoint passed the development gate.", ""])
    if (OUT / "call2/heldout.judged.json").exists():
        payload = read_json(OUT / "call2/heldout.judged.json")
        lines.extend(["## Every held-out reply", "", "Sealed visitor questions remain in their original file. These IDs join the replies to that source.", ""])
        for row in payload["results"]:
            lines.extend(["### " + row["id"], "", "```text", quote(row), "```", "", str(row["judge"]), ""])
    lines.extend(["## Open questions", "", *outcome["open_questions"], "", "## Every path written", ""])
    paths = [path for path in OUT.rglob("*") if path.is_file()]
    paths += list((ROOT / "config/erasure_pilot_v1/approach_a6").rglob("*"))
    paths += list((ROOT / "scripts").glob("erasure_pilot_a6_*.py")) + [ROOT / "scripts/test_erasure_pilot_a6.py"]
    paths += [path for path in (ROOT / ".tmp/approach_a6").rglob("*") if path.is_file()]
    paths += [OUT / "worker_report.md", ROOT / "EXPERIMENTS.md"]
    lines.extend("- " + str(path.relative_to(ROOT)).replace("\\", "/") for path in sorted(set(paths)) if not path.is_dir())
    write_new(OUT / "worker_report.md", "\n".join(lines) + "\n")
    entry = ["\n\n## 2026-11-03 TASK A6\n", outcome["conclusion"], "", outcome["compute_note"], "",
             "Method: google/gemma-3-4b-it revision 093f9f388b31de276ce2de164bdc2081324b9767. A3's byte-identical 300 forget items and 300 distant targets, including absence replies in the forget conversation history. Rank-16 alpha-32 LoRA on all 102 text MLP projections, float32 LoRA over a bfloat16 base, constant AdamW 3e-5 with weight decay .01, microbatch one, divisor eight, ceiling 1024 and end token 106. Per step, 8 forget and 16 distant examples use random.Random(20261101). All 150 historical draw pairs match both offline and in the real training log. No everyday term or clean opener context. NPO adds 8 examples from random.Random(20261103), beta 1.0 on mean per-token log-ratios, weight one and divisor eight. SAM radius .01 applies only to NPO, with exact weight restoration before CE. A5 NS's executed math file is copied byte-for-byte. NPO source files are identical between A5 arms, SHA-256 c381541c69b82c9a01d1c2e42121ba75a0c9e0b54749259eb4402bb99b88b854. The derived H200 input SHA-256 is 3df4765fd639e9c1aa2dcacea79574ce8e4537c91945644073bc53f352c8ab3d. All histories and reply IDs are unchanged. Distant input SHA-256 is e36c8b10c639e0f0623508c77c5560abcd1f2a61d8f0dce3d9733bf5fed2453f. The full B-PROPER package inventory, image recipe, H200, CUDA 12.8 and Python 3.12.10 matched, so its named H200 references were reused. Training completed 200 steps, saving all 20 ten-step adapters. Screens followed the A6 order, starting at 100, and stopped at the 35-minute reserve. The first screen was incomplete, so no full candidate set ran. Labels are worker judge only, every final field empty.", "",
             "Timing diagnosis: the missing launcher upload caused ten automatic container startup failures before any function body ran. The failed app was stopped, the source was repaired, and the replacement submission retained the original absolute deadline. The repair used about 109 seconds of that screening allocation. Training ended at 06:07:15 UTC. The 57-item screen's generation timers sum to 112.891 seconds, while per-item commits and other overhead added about 89 seconds between its first and last recorded completion. It stopped after distant17, with 7 distant items missing. The partial screen was excluded from ranking. This is an infrastructure and timing limit, not evidence that the NPO method failed. No further Modal compute ran.", "",
             *screen_table(), "", *counts_table(outcome), "",
             "Outcome category: " + outcome["category"] + ". " + outcome["candidate_note"], "",
             "Artifacts: scripts/erasure_pilot_a6_*.py, scripts/test_erasure_pilot_a6.py, config/erasure_pilot_v1/approach_a6/, derisk/erasure_pilot_v1/approach_a6/, and scratch .tmp/approach_a6/. worker_report.md quotes all fixed exchanges beside the H200 clean replies, every edited SUBSTANTIVE or BROKEN item, any recovery replies and every path written. run_config.json records the base, config, inputs, source hashes and commit. startup_failure/ records the diagnosed import failure and its repair inside the original allocation. Billing files distinguish metered from billed costs. The Modal volume is retained. The manager owns review, staging and commits.", ""]
    # One append, after the full factual entry has been assembled in memory.
    with (ROOT / "EXPERIMENTS.md").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(entry))
