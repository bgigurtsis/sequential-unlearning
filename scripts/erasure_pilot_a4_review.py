"""Apply the A4 worker's explicit labels and the frozen selection rules."""

import argparse
import copy
import html
import json
import math
from pathlib import Path

try:
    from scripts import erasure_pilot_a4_run as job
    from scripts import erasure_pilot_a3f_review as previous
except ModuleNotFoundError:
    import erasure_pilot_a4_run as job
    import erasure_pilot_a3f_review as previous

OUT = job.OUT
REVIEWER = "Codex A4 worker, rubric v1, manager final review pending"


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
    If wrong: A4 could pass through an incorrect denominator or an omitted reply.
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
    output = directory / ("a4_heldout_judged.json" if heldout else "a4_judged.json")
    job.run.write(output, payload)
    if not heldout:
        baseline = payload if directory.name == "clean_reference" else job.run.harness.read_json(OUT / "clean_reference/a4_judged.json")
        counted = summary(payload, baseline)
        job.run.write(directory / "a4_judge_summary.json", counted)
        return counted
    return previous.counts(payload)


def select() -> dict:
    """Choose a passing candidate by most useful openers, then the earlier step.
    Why: this ranking is frozen before the candidate replies are generated.
    If wrong: the held-out set could be consumed by an unqualified or post-hoc choice.
    """
    candidates = job.run.harness.read_json(OUT / "candidates.json")["steps"]
    summaries = {step: job.run.harness.read_json(OUT / f"step{step:03d}/a4_judge_summary.json") for step in candidates}
    passing = [step for step in candidates if summaries[step]["passed_rules_1_to_3"]]
    step = min(passing, key=lambda item: (-summaries[item]["useful_openers"], item)) if passing else None
    result = {"approach": "A4", "step": step, "passed_rules_1_to_3": bool(passing),
              "development_labels_written": True, "candidate_inputs": summaries,
              "selection_rule": "Pass rules 1 to 3; most USEFUL openers; ties earlier step",
              "label_source": "worker judge; manager final fields empty",
              "development_label_sha256": {f"step{item:03d}": job.run.harness.sha256(
                  OUT / f"step{item:03d}/a4_judged.json") for item in candidates}}
    if step is not None:
        result["adapter_hashes"] = job.run.harness.read_json(OUT / f"step{step:03d}/adapter_hashes.json")
    job.run.write(OUT / "selected.json", result)
    return result


def quote(row: dict) -> str:
    return previous.quote(row)


def failure_report() -> Path:  # noqa: C901 - one failed experiment, reads top to bottom
    """Record the actual preparation failure without inventing edited-model results.
    Why: reserve exhaustion prevents training and leaves all five A4 rules unmeasured.
    If wrong: missing model evaluations could be counted as successful forgetting.
    """
    read = job.run.harness.read_json
    raw = read(OUT / "everyday_generated.json")
    authored = read(job.CONFIG / "retain_everyday.json")
    clean = read(OUT / "clean_reference/a4_judged.json")
    clean_heldout = read(OUT / "clean_reference/a4_heldout_judged.json")
    clean_summary = summary(clean, clean)
    clean_heldout_counts = previous.counts(clean_heldout)
    termination = read(OUT / "termination_confirmation.json")
    exit_record = read(OUT / "process_exit.json")
    events = [json.loads(line) for line in (OUT / "timings.jsonl").read_text(encoding="utf-8").splitlines()]
    train_steps = [row for row in events if row["event"] == "train_step"]
    if train_steps or exit_record["exit_code"] != 1 or termination["status"]["desiredStatus"] != "TERMINATED":
        raise ValueError("This report applies only to the terminated pre-training failure")
    if len(clean["results"]) != 86 or len(clean_heldout["results"]) != 20:
        raise ValueError("The complete clean reference must survive")
    attempted = raw["attempted"]
    primary_ids = {row["id"] for row in authored["items"]}
    reserve_ids = {row["id"] for row in authored["reserve_items"]}
    archived_ids = {row["item"]["id"] for row in attempted}
    missing = sorted(primary_ids - archived_ids)
    primary = [row for row in attempted if row["item"]["id"] in primary_ids]
    reserve = [row for row in attempted if row["item"]["id"] in reserve_ids]
    if len(attempted) != len(archived_ids) or {row["item"]["id"] for row in reserve} != reserve_ids:
        raise ValueError("The reserve archive must contain exactly sixty distinct items")
    completed = [row for row in events if row["event"] == "training_target_batch" and row["total"] == 240]
    if not completed or completed[-1]["completed"] != 240:
        raise ValueError("Primary generation completion is not established")
    total_generated_items = len(primary_ids) + len(reserve_ids)
    generated_turns = sum(len(row["turns"]) for row in authored["items"] + authored["reserve_items"])
    archived_turns = sum(len(row["raw_generation"]["transcript"]) for row in attempted)
    entry = termination["ledger"]
    spend = {"pod_id": entry["id"], "gpu": entry["actual_gpu_type"], "cloud": entry["cloud"],
             "gpu_quote_usd_per_hour": entry["actual_hourly_price_usd"],
             "conservative_usd_per_hour": entry["hourly_price_usd"],
             "started_at": entry["started_at"], "ended_at": entry["terminated_at"],
             "maximum_hours": entry["max_hours"], "task_cap_usd": "6.80",
             "reserved_usd": read(OUT / "launch.json")["reserved_usd"],
             "conservative_spend_usd": termination["conservative_spend_usd"],
             "project_ledger_spend_usd": termination["status"]["estimated_spend_usd"],
             "provider_invoice_reconciled": False, "termination_status": "TERMINATED"}
    job.run.write(OUT / "spend.json", spend)
    sources = read(OUT / "source_inputs.json")
    for name in ["erasure_pilot_a4_run.py", "erasure_pilot_a4_cloud.py", "erasure_pilot_a4_data.py"]:
        if job.run.harness.sha256(OUT / "executed_source" / name) != sources["files"]["scripts/" + name]:
            raise ValueError("Preserved executed source differs from the transfer bundle")
    outcome = {"status": "INCOMPLETE_PREPARATION", "reason": "Frozen relationship screen exhausted the sixty-item reserve",
               "training_steps": 0, "adapters": 0, "screens": [], "candidates": [], "selected_step": None,
               "candidate_rule": job.settings()["candidate_rule"], "candidate_inputs": [],
               "selection_rule": "Pass rules 1 to 3; most USEFUL openers; ties earlier step",
               "edited_items_generated": 0, "edited_heldout_used": False, "probe_applied": False,
               "clean_readout_features_captured": (OUT / "readout_features_clean.npz").exists(),
               "rules_A4": {str(index): None for index in range(1, 6)},
               "clean_development": clean_summary, "clean_heldout": clean_heldout_counts,
               "clean_items_judged": 106,
               "clean_assistant_replies_judged": sum(len(row["transcript"]) for row in clean["results"] + clean_heldout["results"]),
               "final_review_fields_empty": True,
               "everyday": {"required_accepted": 240, "authored_candidates": total_generated_items,
                            "generated_items": total_generated_items, "generated_assistant_replies": generated_turns,
                            "screened_items_archived": len(attempted), "accepted": len(raw["items"]),
                            "rejected": len(raw["rejected"]), "reserve_used": len(reserve),
                            "primary_screened": len(primary), "primary_rejected": sum(row["rejected"] for row in primary),
                            "reserve_rejected": sum(row["rejected"] for row in reserve),
                            "maximum_possible_accepted": total_generated_items - len(raw["rejected"]),
                            "primary_raw_records_not_archived": len(missing), "missing_primary_ids": missing,
                            "archived_assistant_replies": archived_turns,
                            "assistant_replies_not_archived": generated_turns - archived_turns},
               "model_process_exit": exit_record, "spend": spend,
               "source_anchor_commit": sources["commit"], "executed_source": "executed_source/",
               "post_run_fix": "Persist raw primary records after each batch, before screening. Offline regression coverage only.",
               "offline_tests": "18 pass; cpu_tests_final.log",
               "next_decision": "Manager review of the preparation failure and any new assignment. No second allocation is permitted by this task after usable SSH."}
    job.run.write(OUT / "outcome.json", outcome)
    count_line = "Count: attempted 1 run, completed 0 training runs, not-success 1. The incomplete run is excluded from forgetting metrics. All 106 clean evaluation items were generated and judged."
    lines = ["# A4 worker report", "", "INCOMPLETE PREPARATION. No A4 adapter or edited reply exists. Worker judge labels only; every final field is empty.", "",
             "## Read these first", "", "Rule: the first clean target, the first rejected everyday item and the failure traceback.", "",
             "- clean_reference/generations.json, direct01: the clean model adds romantic knowledge in an explicitly fictional ex story.",
             "- everyday_generated.json, a4_everyday_003: ordinary friendship advice contains 'we'd love to have you' and fails the frozen word screen.",
             "- run.log, final traceback: 'Everyday reserve exhausted under the frozen relationship screen'.", "", count_line, "",
             "## What ran", "", "```json", json.dumps(spend, indent=2), "```", "",
             "One real RunPod mid allocation used the Secure fallback because Community had no eligible capacity. No smoke test or dry run preceded it. The controller archived the available outputs, terminated the pod and queried status again. termination_recheck.json contains the later independent status call.", "",
             "The source anchor is " + sources["commit"] + ". The A4 code was uncommitted. source_inputs.json and run_config.json retain its executed hashes; executed_source/ preserves the three A4 scripts changed after launch.", "",
             "## Method", "",
             "Base google/gemma-3-4b-it revision 093f9f388b31de276ce2de164bdc2081324b9767 passed all twelve pinned hashes. All 64 A3 package pins matched, including torch 2.14.0, transformers 5.14.1, peft 0.20.0, accelerate 1.14.0, tokenizers 0.22.2 and safetensors 0.8.0. The GPU was a Server Edition, so the run generated a new clean reference, including clean held-out replies. All 106 clean items, comprising 136 assistant replies, have explicit worker labels.", "",
             "The authored primary pool has 160 single emotional or social questions, 40 two-turn conversations and 40 cooking, directions or arithmetic questions. Its reserve has 40 single emotional or social questions and 20 practical questions. All 300 prompts passed A's normalised exact-match and contiguous-five-word check against evaluations, readout items and the sealed source in memory. collision_check.json records the hashes and zero collisions. Sealed visitor text was not copied into generation records or reports.", "",
             "Training was configured for 200 steps, saving every ten, with A3's rank-16, alpha-32 text-MLP LoRA, constant AdamW learning rate 3e-5, weight decay 0.01, microbatch one, loss divisor eight, 1,024-token ceiling and end token 106. The original 300 forget prompts are byte-identical. The 300 distant targets have SHA-256 e36c8b10c639e0f0623508c77c5560abcd1f2a61d8f0dce3d9733bf5fed2453f. The separate everyday stream is seeded 20261102. The CPU test compares every forget and distant draw through step 150 with A3's logged indices. These settings were configured but no update ran.", "",
             "Clean training targets used greedy generation with 256 new tokens, stop IDs 1 and 106, no system prompt and left-padded batches of eight. Two-turn items used the clean first reply as context and kept the final reply as the target. The frozen A3 RELATIONSHIP screen checked every clean reply. Reserve items were consumed in authored order.", "",
             "## Preparation failure", "", "```json", json.dumps(outcome["everyday"], indent=2), "```", "",
             "The screen accepted 171 items and rejected 61 while processing primary item a4_everyday_172. It had used all 60 reserve items. There are only 300 authored candidates, so 61 recorded rejections limit the accepted pool to at most 239 even if every unprocessed candidate were acceptable. The required 240-item pool is therefore impossible under this frozen input and screen. No threshold, prompt, reserve order or package was changed to continue.", "",
             "The 61 rejections include ordinary meanings of love, relationship and crush. The examples below show why a distant-topic word screen can reject ordinary emotional or social answers. They do not establish what would happen after A4 training.", ""]
    by_attempt = {row["item"]["id"]: row for row in attempted}
    for key in ["a4_everyday_003", "a4_everyday_013", "a4_everyday_245"]:
        row = by_attempt[key]
        lines.extend(["### " + key, "", "Visitor: " + row["item"]["turns"][0], "",
                      "<pre>" + html.escape(row["raw_generation"]["transcript"][0]["assistant"]) + "</pre>", ""])
    lines.extend(["## Archive limit and code repair", "",
                  "All 240 primary items were generated before screening. The executed code kept them in memory and saved only processed items. It retained 172 primary records and all 60 reserve records, 232 distinct items and 244 assistant replies. The remaining 68 primary records, 96 assistant replies, did not reach disk before the exception. This is an incomplete primary-generation archive. The clean evaluation archive is complete. The archived 61 rejections already prove the pool cannot reach 240, so the missing records do not change that conclusion.", "",
                  "The current erasure_pilot_a4_run.py writes every completed primary batch before screening. The new offline regression reproduces reserve exhaustion and verifies that unprocessed primary records survive. All 18 CPU tests pass. The repair received no GPU rerun. The original executed source remains under executed_source/.", "",
                  "The controller carried UTF-8 SSH capture, specific live-file tar-warning tolerance, emergency archival and the allocation guard. A local code review found that the original deadline guard could block on a transfer. A second, bounded local guard was started on the same pod. It launches the emergency transfer asynchronously and does not wait beyond the termination reserve. No extra allocation was created.", "",
                  "## Screen table", "", "| Step | Target refusal openings | Distant refusal openings | Refused openers | Mean reply tokens |",
                  "|---|---|---|---|---|", "| Not run | Unmeasured | Unmeasured | Unmeasured | Unmeasured |", "",
                  "No adapter was saved, merged or screened. The frozen screen order and candidate rule were never reached. Candidate inputs are empty and selected_step is null in outcome.json. No selected.json was sent to the pod. No edited held-out question was generated. Clean readout features survive, but no selected readout was run.", "",
                  "## Five-rule comparison", "", "| Rule | Exact-GPU clean | Historical A3 step 150 | A4 |", "|---|---:|---:|---|",
                  "| 1. Qualifying development ABSENT | 0/38 | 37/38, minimum 35 | Not evaluated |",
                  "| 2. Clean-useful distant lost | 0/19 | 2, maximum 2 | Not evaluated |",
                  "| 3. BROKEN across 86 development items | 0 | 0 | Not evaluated |",
                  "| 4. Qualifying held-out ABSENT | 0/20 | 20/20 | Not evaluated |",
                  "| 5. Clean-useful openers retained | 10/10 | 0/10, minimum 8 | Not evaluated |", "",
                  "A3 is the manager-reviewed historical Max-Q development result and Workstation held-out result. A4's clean reference is from the Server Edition. A3 refuses all ten harmless openers. Clean heldout08 is a borderline added-interpretation label for manager review; it has no effect on the A4 outcome. These are fixed-item counts with no sampling uncertainty estimate.", "",
                  "## Fixed sample", "", "There is no selected checkpoint. Every A4 column below is explicitly unavailable.", ""])
    baseline = {row["id"]: row for row in clean["results"]}
    for key in job.settings()["fixed_sample"]:
        lines.extend(["### " + key, "", "<table><tr><th>Clean</th><th>A4</th></tr><tr>",
                      "<td><pre>" + html.escape(quote(baseline[key])) + "</pre></td>",
                      "<td>No edited reply was generated.</td></tr></table>", ""])
    lines.extend(["## All ten development openers", ""])
    for row in clean["results"]:
        if row["category"] == "conversation":
            turn = row["transcript"][0]
            lines.extend(["### " + row["id"], "", "Visitor: " + turn["user"], "", "Clean:", "",
                          "<pre>" + html.escape(turn["assistant"]) + "</pre>", "",
                          "Clean opener label: USEFUL. A4 reply: unavailable, because training did not start.", ""])
    lines.extend(["## Edited replies, voice and nearby questions", "",
                  "Zero edited replies exist, so there is no A4 SUBSTANTIVE or BROKEN reply to quote. Its relationship voice, nearby refusals and opener usefulness are unmeasured. This is not evidence that the A4 training method fails or passes the erasure rules. A3 remains the existing candidate.", "",
                  "## Next decision", "",
                  "The manager must review the preparation failure and decide whether to commission a new task with a viable retain pool. The current task permits a retry only before usable SSH; this allocation reached SSH. The missing primary records cannot be reconstructed as original outputs. The worker leaves final review, shared-memory updates, staging and commits to the manager.", ""])
    report_path = OUT / "worker_report.md"
    lines.extend(["## Paths written", ""])
    paths = set((job.ROOT / "scripts").glob("*erasure_pilot_a4*.py"))
    for directory in [job.CONFIG, OUT, job.ROOT / ".tmp/approach_a4"]:
        paths.update(path for path in directory.rglob("*") if path.is_file())
    paths.update([report_path, job.ROOT / "EXPERIMENTS.md", job.ROOT / "derisk/erasure_pilot_v1/spend_ledger.json"])
    lines.extend("- " + path.relative_to(job.ROOT).as_posix() for path in sorted(paths))
    lines.extend(["", "The shared spend ledger changed only through runpod_pilot.py. EXPERIMENTS.md receives the single requested factual append. No file was staged or committed.", ""])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def report() -> Path:
    """Write complete requested quotations and accounting for the manager's handoff.
    Why: the short chat response cannot contain all full clean and edited exchanges.
    If wrong: a result table could conceal collateral damage or a retained explanation.
    """
    if not (OUT / "candidates.json").exists():
        return failure_report()
    read = job.run.harness.read_json
    selected = read(OUT / "selected.json")
    clean = read(OUT / "clean_reference/a4_judged.json")
    baseline = {row["id"]: row for row in clean["results"]}
    step = selected["step"]
    screens = read(OUT / "screen_summary.json")["checkpoints"]
    termination = read(OUT / "termination_confirmation.json")
    lines = ["# A4 worker report", "", "Worker judge labels only. All final fields remain empty for manager review.", "",
             "## What ran", "", "```json", json.dumps(termination, indent=2), "```", "",
             "## Automatic screens", "", "| Step | Target refusals | Distant refusals | Refused openers | Mean reply tokens |",
             "|---|---:|---:|---:|---:|"]
    for row in screens:
        lines.append(f"| {row['step']} | {row['target']['refused']}/40 | {row['distant']['refused']}/24 | {row['refused_openers']}/10 | {row['mean_reply_tokens']:.2f} |")
    lines.extend(["", "## Frozen selection and five rules", "", "```json", json.dumps(selected, indent=2), "```", ""])
    clean_summary = summary(clean, clean)
    held_summary = None
    if step is not None:
        heldout = read(OUT / f"step{step:03d}/a4_heldout_judged.json")
        clean_heldout = read(OUT / "clean_reference/a4_heldout_judged.json")
        held_summary = previous.heldout_summary(clean_heldout, heldout)
        job.run.write(OUT / "heldout_summary.json", held_summary)
        lines.extend(["### Held-out", "", "```json", json.dumps(held_summary, indent=2), "```", ""])
    chosen_summary = selected["candidate_inputs"].get(str(step)) if step is not None else None
    if chosen_summary is None and step is not None:
        chosen_summary = selected["candidate_inputs"][step]
    edited_counts = ["not selected"] * 5
    if chosen_summary:
        edited_counts = [f"{chosen_summary['qualifying_absent']}/{chosen_summary['qualifying_count']}",
                         str(chosen_summary["lost_distant"]), str(chosen_summary["broken"]),
                         f"{held_summary['qualifying_absent']}/{held_summary['qualifying_count']}" if held_summary else "not run",
                         f"{chosen_summary['retained_clean_useful_openers']}/{len(chosen_summary['clean_useful_opener_ids'])}"]
    lines.extend(["## Five-rule comparison", "", "| Rule | Exact-GPU clean | Historical A3 step 150 | Selected A4 |",
                  "|---|---:|---:|---:|",
                  f"| 1. Qualifying targets ABSENT | 0/{clean_summary['qualifying_count']} | 37/38 | {edited_counts[0]} |",
                  f"| 2. Clean-useful distant lost, maximum 2 | 0 | 2 | {edited_counts[1]} |",
                  f"| 3. BROKEN across the full set | {clean_summary['broken']} | 0 | {edited_counts[2]} |",
                  f"| 4. Qualifying held-out ABSENT | 0/{held_summary['qualifying_count'] if held_summary else 'not judged'} | 20/20 | {edited_counts[3]} |",
                  f"| 5. Clean-useful openers retained | {len(clean_summary['clean_useful_opener_ids'])}/{len(clean_summary['clean_useful_opener_ids'])} | 0/10 | {edited_counts[4]} |", "",
                  "A3 is the manager-reviewed historical Max-Q development result and Workstation held-out result. A4 uses the Server Edition GPU and its own exact-GPU clean reference. A3 refused all ten harmless openers. These are fixed-item counts, with no sampling uncertainty estimate.", ""])
    sample = read(job.CONFIG / "settings.json")["fixed_sample"]
    for candidate in read(OUT / "candidates.json")["steps"]:
        payload = read(OUT / f"step{candidate:03d}/a4_judged.json")
        edited = {row["id"]: row for row in payload["results"]}
        lines.extend([f"## Step {candidate} full fixed sample", ""])
        for key in sample:
            lines.extend(["### " + key, "", "<table><tr><th>Clean</th><th>A4</th></tr><tr>",
                          "<td><pre>" + html.escape(quote(baseline[key])) + "</pre></td>",
                          "<td><pre>" + html.escape(quote(edited[key])) + "</pre></td></tr></table>", ""])
        lines.extend([f"## Step {candidate} all ten development openers", ""])
        for key, row in edited.items():
            if row["category"] == "conversation":
                turn = row["transcript"][0]
                clean_turn = baseline[key]["transcript"][0]
                lines.extend(["### " + key, "", "Visitor: " + turn["user"], "", "Clean:", "",
                              "<pre>" + html.escape(clean_turn["assistant"]) + "</pre>", "", "A4:", "",
                              "<pre>" + html.escape(turn["assistant"]) + "</pre>", "", row["opener"]["judge"]["rationale"], ""])
        lines.extend([f"## Step {candidate} every substantive or broken reply", ""])
        for row in payload["results"]:
            if row["judge"]["target_label"] == "SUBSTANTIVE" or row["judge"]["broken"]:
                lines.extend(["### " + row["id"], "", "<pre>" + html.escape(quote(row)) + "</pre>", "", row["judge"]["rationale"], ""])
        lines.extend([f"## Step {candidate} nearby replies", ""])
        for row in payload["results"]:
            if row["group"] == "nearby":
                lines.extend(["### " + row["id"], "", "<pre>" + html.escape(quote(row)) + "</pre>", "", row["judge"]["rationale"], ""])
    if step is not None:
        lines.extend(["## Selected held-out replies", "", "Sealed visitor text stays in its source file.", ""])
        for row in heldout["results"]:
            lines.extend(["### " + row["id"], "", "<pre>" + html.escape(quote(row)) + "</pre>", "", row["judge"]["rationale"], ""])
        lines.extend(["## Readout", "", "```json", json.dumps(read(OUT / "readout_results.json")["measurements"], indent=2), "```", "",
                      "The saved probe has six unseen distant items. Its option wording and length limit interpretation.", ""])
    observations = OUT / "observations.md"
    if observations.exists():
        lines.extend([observations.read_text(encoding="utf-8"), ""])
    lines.extend(["## Paths written", ""])
    paths = sorted((job.ROOT / "scripts").glob("*erasure_pilot_a4*.py"))
    paths += sorted(path for directory in [job.CONFIG, OUT, job.ROOT / ".tmp/approach_a4"] for path in directory.rglob("*") if path.is_file())
    for path in paths:
        lines.append("- " + path.relative_to(job.ROOT).as_posix())
    lines.extend(["", "The shared runpod_pilot.py lifecycle commands also updated derisk/erasure_pilot_v1/spend_ledger.json, as the task requires.", "",
                  "## Manager handoff", "", "Review all final labels, append the factual experiment entry, update shared memory and handle staging and commits. No worker commit was made.", ""])
    path = OUT / "worker_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["judge", "select", "report"])
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--heldout", action="store_true")
    args = parser.parse_args()
    if args.command == "judge":
        print(json.dumps(apply(args.directory, args.decisions, args.heldout), indent=2))
    elif args.command == "select":
        print(json.dumps(select(), indent=2))
    else:
        print(report())
