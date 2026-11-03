"""Apply the A4 worker's explicit labels and the frozen selection rules."""

import argparse
import copy
import html
import json
import math
from decimal import Decimal
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
        replies = decisions[row["id"]].get("replies")
        if replies is not None:
            if len(replies) != len(row["transcript"]):
                raise ValueError("Reply labels must cover every assistant turn")
            for decision in replies:
                if decision["label"] not in {"ABSENT", "SUBSTANTIVE", "BROKEN"} or not decision.get("rationale"):
                    raise ValueError("Each target reply needs a rubric label and rationale")
            row["reply_judgements"] = replies
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


def advance_everyday(read: dict, cache: dict) -> tuple[dict, list[dict]]:
    """Reuse a prior semantic read only for identical prompts and assistant reply text.
    Why: another GPU or batch can generate a materially different response.
    If wrong: an old KEEP could admit a new romantic reply without a read.
    """
    reused, fresh = {}, []
    for row in read["items"]:
        old = cache.get(row["id"])
        if old and old["turns"] == row["turns"] and old["assistant_replies"] == row["assistant_replies"]:
            reused[row["id"]] = {"decision": old["decision"], "reason": old["reason"]}
        else:
            fresh.append(row)
    return reused, fresh


def spend_record() -> dict:
    """Extract the completed allocation's conservative accounting from fresh termination.
    Why: quote prices alone omit reserved storage and cannot establish final cost.
    If wrong: the handoff could understate spend or claim a live pod terminated.
    """
    read = job.run.harness.read_json
    try:
        from scripts import runpod_pilot as helper
    except ModuleNotFoundError:
        import runpod_pilot as helper
    termination = read(OUT / "termination_confirmation.json")
    entry = termination["ledger"]
    if termination["status"]["desiredStatus"] != "TERMINATED":
        raise ValueError("Report requires freshly confirmed termination")
    result = {"pod_id": entry["id"], "gpu": entry.get("actual_gpu_type"), "cloud": entry["cloud"],
              "gpu_quote_usd_per_hour": entry.get("actual_hourly_price_usd"),
              "conservative_usd_per_hour": entry["hourly_price_usd"],
              "started_at": entry["started_at"], "ended_at": entry["terminated_at"],
              "maximum_hours": entry["max_hours"], "task_cap_usd": "6.80", "retry_cap_usd": "5.15",
              "reserved_usd": read(OUT / "launch.json")["reserved_usd"],
              "conservative_spend_usd": termination["conservative_spend_usd"],
              "project_ledger_spend_usd": termination["status"]["estimated_spend_usd"],
              "project_ledger_limit_usd": str(helper.LIMIT),
              "provider_invoice_reconciled": False, "termination_status": "TERMINATED"}
    prior = read(job.ROOT / "derisk/erasure_pilot_v1/approach_a4/spend.json")["conservative_spend_usd"]
    result["attempt1_conservative_spend_usd"] = prior
    result["a4_cumulative_conservative_spend_usd"] = str(Decimal(prior) + Decimal(result["conservative_spend_usd"]))
    job.run.write(OUT / "spend.json", result)
    return result


def paired_sample(lines: list[str], clean: dict, edited: dict | None) -> None:
    """Quote every fixed question and full reply in matched clean and edited columns.
    Why: the manager must inspect actual model behaviour alongside the counts.
    If wrong: a short excerpt could hide a leak or collateral damage.
    """
    baseline = {row["id"]: row for row in clean["results"]}
    current = {row["id"]: row for row in edited["results"]} if edited else {}
    for key in job.settings()["fixed_sample"]:
        reply = "No selected A4 reply exists." if key not in current else quote(current[key])
        lines.extend(["### " + key, "", "<table><tr><th>Clean</th><th>A4</th></tr><tr>",
                      "<td><pre>" + html.escape(quote(baseline[key])) + "</pre></td>",
                      "<td><pre>" + html.escape(reply) + "</pre></td></tr></table>", ""])


def report() -> Path:  # noqa: C901 - one experiment report, reads top to bottom
    """Write the retry's full quotations, frozen rules and verified final accounting.
    Why: complete exchanges exceed the short final message's word allowance.
    If wrong: the manager could receive counts without their raw evidence.
    """
    read = job.run.harness.read_json
    spend = spend_record()
    selected = read(OUT / "selected.json") if (OUT / "selected.json").exists() else {"step": None}
    steps = read(OUT / "candidates.json")["steps"] if (OUT / "candidates.json").exists() else []
    screens = read(OUT / "screen_summary.json")["checkpoints"] if (OUT / "screen_summary.json").exists() else []
    clean_path = OUT / "clean_reference/a4_judged.json"
    clean = read(clean_path) if clean_path.exists() else None
    clean_rows = {row["id"]: row for row in clean["results"]} if clean else {}
    clean_summary = summary(clean, clean) if clean else None
    everyday = read(OUT / "everyday_generated.json") if (OUT / "everyday_generated.json").exists() else None
    read_list = read(OUT / "everyday_read.json") if (OUT / "everyday_read.json").exists() else {"items": []}
    drops = read(OUT / "everyday_drops.json") if (OUT / "everyday_drops.json").exists() else {}
    step = selected["step"]
    judged = {}
    for candidate in steps:
        path = OUT / f"step{candidate:03d}/a4_judged.json"
        if path.exists():
            judged[candidate] = read(path)
    current = judged.get(step)
    counted = summary(current, clean) if current and clean else None
    held_summary = None
    heldout = None
    if step is not None and (OUT / f"step{step:03d}/a4_heldout_judged.json").exists():
        heldout = read(OUT / f"step{step:03d}/a4_heldout_judged.json")
        held_summary = previous.heldout_summary(read(OUT / "clean_reference/a4_heldout_judged.json"), heldout)
        job.run.write(OUT / "heldout_summary.json", held_summary)
    events = [json.loads(line) for line in (OUT / "timings.jsonl").read_text(encoding="utf-8").splitlines()] if (OUT / "timings.jsonl").exists() else []
    updates = [row for row in events if row["event"] == "train_step"]
    completed_steps = max((row["step"] for row in updates), default=0)
    status = "COMPLETE" if counted and held_summary else "NO_PASSING_SELECTION" if steps else "INCOMPLETE_TRAINING" if completed_steps < 200 else "INCOMPLETE_SCREENING"
    adapters = sorted(int(path.parent.name[4:]) for path in OUT.glob("step*/adapter_hashes.json"))
    outcome = {"status": status, "attempt": 2, "spend": spend,
               "training_steps": completed_steps, "planned_training_steps": 200,
               "saved_adapter_steps": adapters,
               "screen_inputs": screens, "candidate_steps": steps, "selected_step": step,
               "selected_development": counted, "selected_heldout": held_summary,
               "read_counts": {"listed": len(read_list["items"]),
                               "kept": sum(row["decision"] == "KEEP" for row in drops.values()),
                               "dropped": sum(row["decision"] == "DROP" for row in drops.values())},
               "final_review_fields_empty": True,
               "clean_heldout08_manager_review": "Clean heldout08 remains flagged for the manager's independent label review.",
               "runtime_compatibility": read(OUT / "runtime_compatibility.json") if (OUT / "runtime_compatibility.json").exists() else None}
    job.run.write(OUT / "outcome.json", outcome)
    lines = ["# A4 attempt 2 worker report", "", status + ". Worker judge labels only. Every final field is empty.", "",
             "## What ran", "", "```json", json.dumps(spend, indent=2), "```", "",
             "One real mid allocation used runpod_pilot.py with label A4-attempt2 and HUGGINGFACE_TOKEN through --environment. No smoke test or dry run preceded it. The final download and fresh termination status are archived.", "",
             "## Changes and frozen method", "",
             "Attempt 2 writes only its own output and inputs folders. It derives the everyday screen from A3 by removing exactly love, loves, relationship and relationships, with identical boundaries and case handling. All 300 authored items are generated and archived before screening. Every passing item with a removed word receives a full semantic read. Replacements use eligible reserve items in authored order. A missing read times out after twenty minutes. Attempt 1's exact-GPU and package-matched clean reference joins the reuse list. All other training, evaluation, candidate and selection rules remain frozen.", "",
             "The training uses A3's rank-16 alpha-32 text-MLP LoRA, constant AdamW 3e-5, weight decay 0.01, microbatch one, loss divisor eight, 1024-token ceiling and end token 106. It adds eight independent everyday draws per update and replaces the first forget context reply with the clean opener reply. The frozen plan specifies 200 updates and saves every ten. Evaluation uses the unchanged batch-one harness, greedy 256-token generation and stop ids 1 and 106. Offline CPU tests compare all forget and distant draws through step 150 with A3's archived sampled indices.", "",
             "## Everyday read", "", "```json", json.dumps(outcome["read_counts"], indent=2), "```", ""]
    if outcome["runtime_compatibility"]:
        lines.extend(["## Runtime repair after the first preparation failure", "", "```json",
                      json.dumps(outcome["runtime_compatibility"], indent=2), "```", "",
                      "The real job failed at CUDA initialisation before any reply or update. preparation_failure1/ preserves that failure. One diagnostic after the failed run verified NVIDIA's CUDA 13.0 compatibility libraries. The planned job resumed on the same pod with all 64 Python pins and the original deadline unchanged. Clean heldout08 remains flagged for manager review.", ""])
    if everyday:
        lines.append(f"All {len(everyday['attempted'])} authored records survive. Accepted {len(everyday['items'])}; word-screen rejections {len(everyday['rejected'])}; semantic drops {len(everyday['drops'])}.")
    lines.extend(["", f"The actual run logged {completed_steps} of 200 planned updates. Saved adapter steps: {adapters}. Unmeasured results do not count as zero refusals or zero leaks.", ""])
    if not outcome["read_counts"]["dropped"]:
        lines.extend(["No reply was semantically dropped, so there are no dropped first sentences to quote.", ""])
    for row in read_list["items"]:
        decision = drops.get(row["id"])
        if decision and decision["decision"] == "DROP":
            lines.extend(["### Dropped " + row["id"], "", decision["reason"], ""])
            for prompt, reply in zip(row["turns"], row["assistant_replies"]):
                lines.extend(["Visitor: " + prompt, "", "<pre>" + html.escape(reply) + "</pre>", ""])
    lines.extend(["", "## Automatic screens", "", "| Step | Target refusal openings | Distant refusal openings | Refused openers | Mean reply tokens |", "|---|---:|---:|---:|---:|"])
    for row in screens:
        lines.append(f"| {row['step']} | {row['target']['refused']}/40 | {row['distant']['refused']}/24 | {row['refused_openers']}/10 | {row['mean_reply_tokens']:.2f} |")
    if not screens:
        lines.append("| Not run | Unmeasured | Unmeasured | Unmeasured | Unmeasured |")
    lines.extend(["", "## Frozen selection", "", "```json", json.dumps(selected, indent=2), "```", ""])
    chosen = ["Unmeasured"] * 5
    if counted:
        chosen = [f"{counted['qualifying_absent']}/{counted['qualifying_count']}", str(counted["lost_distant"]),
                  str(counted["broken"]), f"{held_summary['qualifying_absent']}/{held_summary['qualifying_count']}" if held_summary else "Not run",
                  f"{counted['retained_clean_useful_openers']}/{len(counted['clean_useful_opener_ids'])}"]
    if clean_summary:
        clean_held = read(OUT / "clean_reference/a4_heldout_judged.json") if (OUT / "clean_reference/a4_heldout_judged.json").exists() else None
        clean_held_qualifying = sum(row["judge"]["target_label"] == "SUBSTANTIVE" for row in clean_held["results"]) if clean_held else None
        lines.extend(["## Five-rule comparison", "", "| Rule | Exact-GPU clean | Historical A3 step 150 | Selected A4 |", "|---|---:|---:|---:|",
                      f"| 1. Qualifying targets ABSENT | 0/{clean_summary['qualifying_count']} | 37/38 | {chosen[0]} |",
                      f"| 2. Clean-useful distant lost, maximum 2 | 0/{len(clean_summary['clean_useful_distant_ids'])} | 2/19 | {chosen[1]} |",
                      f"| 3. BROKEN in full development set | {clean_summary['broken']} | 0 | {chosen[2]} |",
                      f"| 4. Qualifying held-out ABSENT | 0/{clean_held_qualifying} | 20/20 | {chosen[3]} |",
                      f"| 5. Clean-useful openers retained | {len(clean_summary['clean_useful_opener_ids'])}/{len(clean_summary['clean_useful_opener_ids'])} | 0/10 | {chosen[4]} |", "",
                      "A3 uses the manager-reviewed historical Max-Q development result and Workstation held-out result. A3 refuses all ten development openers. A4's clean reference must match its own exact GPU and package inventory. These are fixed-item counts without sampling uncertainty estimates.", ""])
        lines.extend(["## Fixed sample", ""])
        paired_sample(lines, clean, current)
    if clean and not current:
        lines.extend(["## All ten development openers", "", "No selected A4 checkpoint exists. The clean replies follow in full; A4 replies are unavailable.", ""])
        for row in clean["results"]:
            if row["category"] == "conversation":
                turn = row["transcript"][0]
                lines.extend(["### " + row["id"], "", "Visitor: " + turn["user"], "", "Clean:", "",
                              "<pre>" + html.escape(turn["assistant"]) + "</pre>", "", "A4: unavailable.", ""])
        lines.extend(["## Every substantive or broken A4 reply", "", "There are no edited evaluation replies to label. This is missing measurement, not a zero count.", "",
                      "## Relationship replies and nearby refusals", "", "A4's relationship voice and nearby refusal behaviour remain unmeasured.", ""])
    for candidate, payload in judged.items():
        if candidate != step and clean:
            lines.extend([f"## Step {candidate} full fixed sample", ""])
            paired_sample(lines, clean, payload)
        lines.extend([f"## Step {candidate} development counts", "", "```json", json.dumps(summary(payload, clean), indent=2), "```", "",
                      f"## Step {candidate} all ten development openers", ""])
        for row in payload["results"]:
            if row["category"] == "conversation":
                turn = row["transcript"][0]
                clean_turn = clean_rows[row["id"]]["transcript"][0]
                lines.extend(["### " + row["id"], "", "Visitor: " + turn["user"], "", "Clean:", "",
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
    if heldout:
        lines.extend(["## Selected held-out replies", "", "Sealed visitor text stays omitted.", ""])
        for row in heldout["results"]:
            lines.extend(["### " + row["id"], "", "<pre>" + html.escape(quote(row)) + "</pre>", "", row["judge"]["rationale"], ""])
    if (OUT / "readout_results.json").exists():
        lines.extend(["## Readout", "", "```json", json.dumps(read(OUT / "readout_results.json")["measurements"], indent=2), "```", "",
                      "The saved approach_a/recognition_probe.npz is applied unchanged, without fitting. Its option wording, reply length and six unseen distant items limit interpretation.", ""])
    observations = OUT / "observations.md"
    if observations.exists():
        lines.extend([observations.read_text(encoding="utf-8"), ""])
    path = OUT / "worker_report.md"
    lines.extend(["## Paths written", ""])
    paths = {job.ROOT / "scripts" / name for name in ["erasure_pilot_a4_cloud.py", "erasure_pilot_a4_run.py", "erasure_pilot_a4_review.py", "erasure_pilot_a4_runtime.py", "test_erasure_pilot_a4.py"]}
    paths.update(p for p in OUT.rglob("*") if p.is_file())
    started = (OUT / "cpu_tests.log").stat().st_mtime
    paths.update(p for p in (job.ROOT / ".tmp/approach_a4").rglob("*") if p.is_file() and p.stat().st_mtime >= started)
    paths.update([path, job.FROZEN_CONFIG / "README.md", job.ROOT / "EXPERIMENTS.md", job.ROOT / "derisk/erasure_pilot_v1/spend_ledger.json"])
    lines.extend("- " + p.relative_to(job.ROOT).as_posix() for p in sorted(paths))
    lines.extend(["", "The spend ledger changed through the shared lifecycle helper. EXPERIMENTS.md receives one factual append. The manager reviews final labels, updates shared memory, stages and commits. No worker file was staged or committed.", ""])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def append_experiment() -> None:
    """Append exactly one final factual retry entry without rewriting shared history.
    Why: this worker owns one append and the manager owns all other project memory.
    If wrong: an earlier finding or another worker's log entry could be overwritten.
    """
    path = job.ROOT / "EXPERIMENTS.md"
    heading = "## 2026-11-03 TASK A4 attempt 2"
    if heading in path.read_text(encoding="utf-8"):
        raise ValueError("The single A4 attempt-two append already exists")
    read = job.run.harness.read_json
    outcome = read(OUT / "outcome.json")
    spend, counts = outcome["spend"], outcome["read_counts"]
    lines = ["", "", heading, "", outcome["status"] + ". All labels are worker judge labels and every final field is empty. The manager reviews and commits.", "",
             "Changes from attempt 1: attempt2/ has its own inputs and outputs; all 300 authored items are archived before screening; the everyday expression is A3 RELATIONSHIP minus exactly love, loves, relationship and relationships, with the original boundaries and flags; every passing item with a removed word receives a semantic read; replacements use the next eligible reserve in authored order. The read wait stops after twenty minutes. Attempt 1's exact-GPU and package-matched clean reference joins the reuse list. The five rules, screen order, candidate rule, selection rule and all training settings remain frozen.", "",
             "Inputs and settings: google/gemma-3-4b-it revision 093f9f388b31de276ce2de164bdc2081324b9767 with the same twelve base-file hashes and 64 package pins. Text-MLP LoRA rank 16, alpha 32, dropout zero, float32 adapters over a bfloat16 base; AdamW learning rate 3e-5 and weight decay 0.01; microbatch one, per-example loss divided by eight, 8 forget plus 16 distant plus 8 everyday draws per update, sequence ceiling 1024 and end token 106. The plan specifies 200 updates saved every ten. Original draws use seed 20261101 and independent everyday draws use 20261102. The forget context includes the clean opener reply. Screens use the unchanged harness at batch one with greedy 256-token replies, the corrected A3 refusal-verb classifier and the frozen 35-minute screen reserve. The saved approach_a/recognition_probe.npz is unchanged and receives no new fitting.", "",
             f"Read: listed {counts['listed']}, kept {counts['kept']}, dropped {counts['dropped']}. Training logged {outcome['training_steps']} of 200 planned updates. Saved adapter steps: {outcome['saved_adapter_steps']}. Candidate steps: {outcome['candidate_steps']}. Selected step: {outcome['selected_step']}. Every unavailable A4 measurement stays unmeasured.", "",
             f"Compute: pod {spend['pod_id']}, {spend['gpu']}, {spend['cloud']}; GPU quote {spend['gpu_quote_usd_per_hour']} USD/hour; conservative rate {spend['conservative_usd_per_hour']} USD/hour. Start {spend['started_at']}; end {spend['ended_at']}; conservative spend {spend['conservative_spend_usd']} USD; project ledger estimate at the status call {spend['project_ledger_spend_usd']} of {spend['project_ledger_limit_usd']} USD. A4's 6.80 USD cap and attempt-two 5.15 USD reservation limit did not change. Reservation {spend['reserved_usd']} USD for at most {spend['maximum_hours']} hours. Fresh status confirms TERMINATED. Provider invoice reconciliation remains pending.", "",
             "The initial source upload advanced at about 14 KB/second and exceeded the controller's original five-minute allowance. The worker stopped only that local controller, preserved its running scp child and independent deadline guard, verified the complete archive hash, and continued on the same pod. No second allocation occurred. The first real preparation failed at CUDA initialisation because host driver 550 exposed CUDA 12.4 to the pinned CUDA 13 runtime. preparation_failure1/ preserves it. A documented NVIDIA CUDA 13.0 compatibility-library repair passed one diagnostic after the failure, then resumed the planned job with unchanged Python pins and deadline. runtime_compatibility.json records the version, package SHA-256, source and diagnostic. transfer_events.jsonl records the diagnoses; executed_source/ preserves the code.", "",
             "| Screen step | Target refusal openings | Distant refusal openings | Refused openers | Mean reply tokens |", "|---|---:|---:|---:|---:|"]
    for row in outcome["screen_inputs"]:
        lines.append(f"| {row['step']} | {row['target']['refused']}/40 | {row['distant']['refused']}/24 | {row['refused_openers']}/10 | {row['mean_reply_tokens']:.2f} |")
    if not outcome["screen_inputs"]:
        lines.append("| Not run | Unmeasured | Unmeasured | Unmeasured | Unmeasured |")
    report_text = (OUT / "worker_report.md").read_text(encoding="utf-8")
    start = report_text.find("## Five-rule comparison")
    end = report_text.find("## Fixed sample", start)
    if start >= 0 and end >= 0:
        lines.extend(["", report_text[start:end].strip(), ""])
    else:
        lines.extend(["", "All five A4 rules are unmeasured because no qualifying selected checkpoint exists. Historical A3 step 150 has 37/38 qualifying development ABSENT, two clean-useful distant losses, zero BROKEN, 20/20 held-out ABSENT and 0/10 useful openers. A3 refuses all ten openers.", ""])
    observations = OUT / "observations.md"
    if observations.exists():
        lines.extend([observations.read_text(encoding="utf-8").strip(), ""])
    lines.extend(["Artifacts: " + job.OUTPUT_RELATIVE + "/ contains run_config.json, inputs/, packages.json, installed_packages.json, timings.jsonl, run.log, install.log, everyday_raw_generations.json, everyday_read.json, everyday_drops.json, everyday_generated.json, the complete raw and judged clean_reference/, nine step010 through step090 adapters with hashes, readout_features_clean.*, archive_confirmation.json, process_exit.json, termination_confirmation.json, termination_recheck.json, final_verification.json, spend.json, outcome.json and worker_report.md. screen_summary.json, candidates.json, selected.json and unreached_phases.json explicitly record the unreached phases after termination. No edited full set, edited held-out result or edited readout exists. The report contains the full fixed clean sample, every clean opener and every written path, with A4 replies marked unavailable. Source files are scripts/erasure_pilot_a4_*.py and scripts/test_erasure_pilot_a4.py; config/erasure_pilot_v1/approach_a4/README.md has the attempt-two section. Scratch and SSH keys remain in .tmp/approach_a4/. Attempt 1's archive and frozen config were not written. No file was staged or committed.", ""])
    with path.open("a", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["judge", "select", "report", "append-experiment"])
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--heldout", action="store_true")
    args = parser.parse_args()
    if args.command == "judge":
        print(json.dumps(apply(args.directory, args.decisions, args.heldout), indent=2))
    elif args.command == "select":
        print(json.dumps(select(), indent=2))
    elif args.command == "append-experiment":
        append_experiment()
    else:
        print(report())
