"""Write the A7 comparison and complete reply quotations for manager review."""

import json
import argparse
import math
import random
from pathlib import Path

from scripts import erasure_pilot_a7_review as review
from scripts import erasure_pilot_a7_run as job

ROOT = job.ROOT
OUT = ROOT / "derisk/erasure_pilot_v1/approach_a7"


def read(path: Path, default=None):
    return job.run.harness.read_json(path) if path.exists() else default


def quote(row: dict) -> str:
    """Quote every user and assistant turn without shortening the raw replies.
    Why: a refusal opening can precede substantive target knowledge later in the reply.
    If wrong: abbreviated evidence can make a leaking answer appear absent.
    """
    lines = []
    for index, turn in enumerate(row["transcript"], 1):
        if "user" in turn:
            lines.append(f"Visitor {index}: " + turn["user"])
        lines.append(f"Assistant {index}: " + turn["assistant"])
    return "\n\n".join(lines)


def counts_after5(path: Path, qualified: set[str]) -> dict | None:
    """Count only the matched clean-qualified forty-target recovery evaluation.
    Why: clean refusals must not count as either recovery or retained ignorance.
    If wrong: L3 can change through an incorrect denominator.
    """
    payload = read(path)
    if payload is None:
        return None
    rows = {row["id"]: row for row in payload["results"]}
    if len(rows) != 40 or not qualified.issubset(rows):
        raise ValueError("Recovery labels do not cover forty matched targets")
    return {"qualifying": len(qualified),
            "substantive": sum(rows[key]["judge"]["target_label"] == "SUBSTANTIVE" for key in qualified),
            "absent": sum(rows[key]["judge"]["target_label"] == "ABSENT" for key in qualified),
            "broken": sum(rows[key]["judge"]["target_label"] == "BROKEN" for key in qualified),
            "path": str(path.relative_to(ROOT))}


def baseline_counts(clean: dict, directory: Path) -> dict:
    """Compare historical A3 denial replies and the clean reference on matched items.
    Why: the report must distinguish historical denial counts from same-pod loss tests.
    If wrong: a hardware difference can be mistaken for measured A7 improvement.
    """
    historical = read(ROOT / "derisk/erasure_pilot_v1/approach_a3/step150/judged.json")
    for row in historical["results"]:
        if row["category"] == "conversation":
            # All ten historical openers were read explicitly. Each is a memory or knowledge refusal.
            row["opener"] = {"judge": {"usefulness": "NOT_USEFUL"}, "final": job.run.harness.label_slots()}
    result = {"clean": review.summary(clean, clean), "a3_historical": review.summary(historical, clean),
              "a3_development_source": "derisk/erasure_pilot_v1/approach_a3/step150/judged.json",
              "a3_development_gpu": read(ROOT / "derisk/erasure_pilot_v1/approach_a3/packages.json")["gpu"],
              "caveat": "A3 denial counts are historical. Prefix and recovery comparisons use the current arm GPU."}
    clean_heldout = read(directory / "clean_reference/a7_heldout_judged.json")
    historical_heldout = read(ROOT / "derisk/erasure_pilot_v1/approach_a3f/step150/heldout_judged.json")
    if clean_heldout is not None:
        result["clean_heldout"] = review.previous.heldout_summary(clean_heldout, clean_heldout)
        result["a3_historical_heldout"] = review.previous.heldout_summary(clean_heldout, historical_heldout)
        result["a3_heldout_source"] = "derisk/erasure_pilot_v1/approach_a3f/step150/heldout_judged.json"
    return result


def training_validation(directory: Path) -> dict:
    """Re-read actual training draws, objective totals and every saved adapter hash.
    Why: the completed run must match the streams proved by the offline tests.
    If wrong: runtime divergence or a partial adapter can enter the final report.
    """
    path = directory / "training.jsonl"
    if not path.exists():
        return {"completed_steps": 0, "training_complete": False, "verified_adapter_steps": []}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if [row["step"] for row in rows] != list(range(1, len(rows) + 1)) or len(rows) > 200:
        raise ValueError("Training log has missing, repeated or unplanned updates")
    original, everyday, npo = random.Random(20261101), random.Random(20261102), random.Random(20261103)
    a3_log = ROOT / "derisk/erasure_pilot_v1/approach_a3/timings.jsonl"
    old = {}
    for line in a3_log.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["event"] == "train_step":
            old[record["step"]] = record["sampled_indices"]
    for row in rows:
        expected = job.draw_indices(original, everyday, npo)
        if row["sampled_indices"] != expected:
            raise ValueError("Actual A7 sampled indices differ from the frozen streams")
        if row["step"] <= 150:
            for group in ["forget", "retain"]:
                if expected[group] != old[row["step"]][group]:
                    raise ValueError("Actual A7 sampled indices differ from A3's logged indices")
        losses = row["losses"]
        total = losses["forget"] + 2 * losses["retain"] + losses["everyday_scaled"] + losses["npo"]
        if not math.isclose(losses["everyday_scaled"], losses["everyday"] * 2 / 8):
            raise ValueError("Everyday contribution did not preserve the divisor of eight")
        if not all(math.isfinite(value) for value in losses.values()) or not math.isclose(total, losses["total_scaled"]):
            raise ValueError("Non-finite or inconsistent logged training objective")
    verified = []
    for step in range(10, len(rows) + 1, 10):
        adapter = directory / f"step{step:03d}/adapter"
        expected = read(adapter.parent / "adapter_hashes.json")
        if expected is None or job.run.harness.checkpoint_hashes(adapter) != expected:
            raise ValueError("A completed ten-step adapter is missing or fails its hashes")
        verified.append(step)
    return {"completed_steps": len(rows), "training_complete": len(rows) == 200,
            "all_completed_draws_match_frozen_streams": True,
            "a3_logged_steps_matched": min(len(rows), 150), "all_logged_losses_finite": True,
            "verified_adapter_steps": verified,
            "mean_update_seconds": sum(row["seconds"] for row in rows) / len(rows),
            "total_update_seconds": sum(row["seconds"] for row in rows)}


def arm_results(arm: str) -> dict:
    """Gather each arm's actual selected result without substituting a failed checkpoint.
    Why: an incomplete selection must not be reported as a passing erasure run.
    If wrong: diagnostic candidates can silently replace the frozen selection.
    """
    directory = OUT
    selected = read(directory / "selected.json")
    candidates = read(directory / "candidates.json", {"steps": []})
    clean = read(directory / "clean_reference/a7_judged.json")
    result = {"arm": arm, "selected": selected, "candidates": candidates,
              "packages": read(directory / "packages.json"), "config": read(directory / "run_config.json"),
              "launch": read(directory / "launch.json"), "spend": read(directory / "spend.json"),
              "termination": read(directory / "termination_confirmation.json"),
              "exit": read(directory / "process_exit.json"),
              "screens": read(directory / "screen_summary.json", {"checkpoints": []})["checkpoints"],
              "category": "incomplete", "rules": {}, "loss_tests": None}
    result["training_validation"] = training_validation(directory)
    parent = ROOT / "derisk/erasure_pilot_v1/approach_a5/arm_ns"
    identical = {}
    for name in ["forget_with_clean_openers.json", "retain_generated.json", "everyday_generated.json"]:
        actual = read(directory / name)["items"]
        original = read(parent / name)["items"]
        fields = ["id", "turns", "target_response", "context_responses"]
        identical[name] = len(actual) == len(original) and all(
            all(a.get(key) == b.get(key) for key in fields) for a, b in zip(actual, original))
    if not all(identical.values()):
        raise ValueError("A7 changed an NS training item in addition to its everyday dose")
    result["same_ns_training_inputs"] = identical
    result["partial_screens"] = []
    for path in sorted(directory.glob("step*/screen_generations.json")):
        payload = read(path)
        if not payload.get("complete"):
            result["partial_screens"].append({"step": int(path.parent.name[4:]),
                "completed_items": len(payload["results"]), "stop_reason": payload.get("stop_reason"),
                "counts": job.screen_counts(payload) if payload["results"] else None,
                "used_for_selection": False})
    if clean is None:
        return result
    result["baselines"] = baseline_counts(clean, directory)
    targets = set(result["baselines"]["clean"]["qualifying_target_ids"])
    distant = set(result["baselines"]["clean"]["clean_useful_distant_ids"])
    for partial in result["partial_screens"]:
        judged = read(directory / f"step{partial['step']:03d}/screen_judged.json")
        if judged is None:
            continue
        rows = {row["id"]: row for row in judged["results"]}
        observed_targets = targets.intersection(rows)
        observed_distant = distant.intersection(rows)
        openers = [row for row in rows.values() if row["category"] == "conversation"]
        partial["judge_counts"] = {
            "qualifying_targets_observed": len(observed_targets),
            "qualifying_absent_observed": sum(rows[key]["judge"]["target_label"] == "ABSENT" for key in observed_targets),
            "missing_qualifying_target_ids": sorted(targets.difference(rows)),
            "clean_useful_distant_observed": len(observed_distant),
            "lost_clean_useful_distant_observed": sum(rows[key]["judge"]["usefulness"] != "USEFUL" for key in observed_distant),
            "useful_openers_observed": sum(row["opener"]["judge"]["usefulness"] == "USEFUL" for row in openers),
            "openers_observed": len(openers), "broken_observed": sum(row["judge"]["broken"] for row in rows.values()),
            "official_full_candidate": False}
    prefix = {}
    for name in ["clean", "a3", "selected"]:
        payload = read(directory / ("prefix_" + name + ".json"))
        if payload is not None and len(payload["results"]) == 64:
            prefix[name] = review.prefix_summary(payload, targets, distant)
    result["prefix"] = prefix
    result["a3_assignment"] = read(directory / "a3_relearning_assignment.json", {"run_here": True})
    baseline_directory = directory
    result["a3_after5"] = counts_after5(baseline_directory / "a3_relearning/relearn05.judged.json", targets)
    summaries = {}
    for step in candidates["steps"]:
        summary = read(directory / f"step{step:03d}/a7_judge_summary.json")
        if summary is not None:
            summaries[str(step)] = summary
    result["candidate_summaries"] = summaries
    if selected is None or selected.get("step") is None:
        result["category"] = "not a candidate" if selected is not None else "incomplete"
        if not result["screens"]:
            result["category"] = "incomplete screening"
        if summaries:
            best = max(summaries, key=lambda step: (summaries[step]["passed_rules_1_to_3"],
                       -summaries[step]["broken"], summaries[step]["qualifying_absent"],
                       -summaries[step]["lost_distant"], summaries[step]["useful_openers"], -int(step)))
            result["diagnostic_step"] = int(best)
            result["diagnostic_summary"] = summaries[best]
            result["diagnostic_display_rule"] = "For quotations only: most qualifying ABSENT among the full candidates, then fewer distant losses. This does not select a checkpoint."
        return result
    step = selected["step"]
    summary = summaries[str(step)]
    rules = dict(summary["rules"])
    clean_heldout = read(directory / "clean_reference/a7_heldout_judged.json")
    heldout = read(directory / f"step{step:03d}/a7_heldout_judged.json")
    if clean_heldout is not None and heldout is not None:
        result["heldout"] = review.previous.heldout_summary(clean_heldout, heldout)
        rules["4"] = result["heldout"]["passed_judge_heldout"]
    else:
        rules["4"] = None
    result.update(step=step, summary=summary, rules=rules)
    a3_after5 = result["a3_after5"]
    selected_after5 = counts_after5(directory / "selected_relearning/relearn05.judged.json", targets)
    result.update(a3_after5=a3_after5, selected_after5=selected_after5,
                  readout=read(directory / "readout_results.json"))
    if len(prefix) == 3 and a3_after5 is not None and selected_after5 is not None:
        result["loss_tests"] = review.loss_tests(prefix["clean"], prefix["a3"], prefix["selected"],
                                                a3_after5["substantive"], selected_after5["substantive"])
    result["category"] = review.outcome(rules, result["loss_tests"])
    if rules["4"] is None:
        result["category"] = "incomplete held-out evaluation"
    return result


def result_tables(result: dict) -> list[str]:
    """Present every screen and matched denial and likelihood denominator.
    Why: the manager needs to assess the frozen rules beside the clean model and A3.
    If wrong: omitted controls or different qualifying items can hide collateral damage.
    """
    lines = ["## Automatic screens", "",
             "| Step | Target refusal openings /40 | Distant /24 | Refused openers /10 | Mean reply tokens |",
             "|---|---:|---:|---:|---:|"]
    for row in result["screens"]:
        lines.append(f"| {row['step']} | {row['target']['refused']} | {row['distant']['refused']} | {row['refused_openers']} | {row['mean_reply_tokens']:.6f} |")
    for row in result["partial_screens"]:
        counts = row["counts"]
        if counts is not None:
            lines.append(f"| {row['step']}, partial, excluded | {counts['target']['refused']}/{counts['target']['count']} observed | "
                         f"{counts['distant']['refused']}/{counts['distant']['count']} observed of 24 | {counts['refused_openers']}/{counts['opener_count']} | {counts['mean_reply_tokens']:.6f} |")
    lines.extend(["", "Partial screens, excluded from selection: " + json.dumps(result["partial_screens"]) + ".", ""])
    lines.extend(["", "## Development rules", "",
                  "| Model | Qualifying ABSENT | Lost clean-useful distant | BROKEN | USEFUL openers | Rules |",
                  "|---|---:|---:|---:|---:|---|"])
    summaries = [("Clean", result["baselines"]["clean"]), ("A3 step150, historical", result["baselines"]["a3_historical"])]
    for step, summary in result["candidate_summaries"].items():
        summaries.append(("A7 step" + step, summary))
    for name, summary in summaries:
        lines.append(f"| {name} | {summary['qualifying_absent']}/{summary['qualifying_count']} | {summary['lost_distant']} | {summary['broken']} | {summary['useful_openers']}/10 | {json.dumps(summary['rules'])} |")
    for partial in result["partial_screens"]:
        counts = partial.get("judge_counts")
        if counts is not None:
            lines.append(f"| A7 step{partial['step']}, partial screen only | {counts['qualifying_absent_observed']}/{counts['qualifying_targets_observed']} observed | "
                         f"{counts['lost_clean_useful_distant_observed']}/{counts['clean_useful_distant_observed']} observed | "
                         f"{counts['broken_observed']} observed | {counts['useful_openers_observed']}/{counts['openers_observed']} observed | "
                         "No full candidate. Rules two through four are unestablished; this row does not select a checkpoint. |")
    lines.extend(["", "A3 uses historical development replies with this card's clean qualification. It is not an A3 denial retest on this pod. "
                  "The current card's baseline includes five distant questions that were already NOT_USEFUL before editing.", ""])
    lines.extend(["", "Held-out: " + json.dumps(result.get("heldout")) + ".",
                  "Clean held-out: " + json.dumps(result["baselines"].get("clean_heldout")) + ".",
                  "Historical A3 held-out: " + json.dumps(result["baselines"].get("a3_historical_heldout")) + ".", "",
                  "## Prefix losses", "", "Mean item losses, nats per token, on the same clean continuations.", "",
                  "| Model | Target loss | Distant loss | Target rise | Distant rise |",
                  "|---|---:|---:|---:|---:|"])
    clean = result["prefix"]["clean"]
    for name, values in result["prefix"].items():
        target, distant = values["target"]["mean_item_ce_nats"], values["distant"]["mean_item_ce_nats"]
        lines.append(f"| {name} | {target:.10f} | {distant:.10f} | {target-clean['target']['mean_item_ce_nats']:.10f} | {distant-clean['distant']['mean_item_ce_nats']:.10f} |")
    readout = result.get("readout")
    readout_summary = readout.get("measurements") if readout else None
    lines.extend(["", "A3 recovery after five updates: " + json.dumps(result.get("a3_after5")) + ".",
                  "Selected recovery after five updates: " + json.dumps(result.get("selected_after5")) + ".",
                  "Loss tests: " + json.dumps(result.get("loss_tests")) + ".",
                  "Readout measurements: " + json.dumps(readout_summary) + ". Full predictions remain in readout_results.json when run.", ""])
    return lines


def write(append_experiments: bool = False) -> None:
    """Write a complete one-arm archive and append the requested entry once.
    Why: the report must preserve every reply and keep the experiment record factual.
    If wrong: unselected diagnostics or incomplete loss measures can appear to pass.
    """
    result = arm_results("NS")
    termination = result["termination"]
    if not termination or termination["fresh_status"]["desiredStatus"] != "TERMINATED":
        raise ValueError("Fresh termination confirmation is required")
    if result["exit"]["exit_code"] != 0 or not result["training_validation"]["training_complete"]:
        raise ValueError("A completed report requires the real 200-step run to finish")
    replaces = all(result["rules"].get(str(index), False) for index in range(1, 6))
    reason = "A7 passes rules one through five" if replaces else "No A7 result replaces the existing candidate"
    if not replaces and result["category"] in {"denial only", "denial and loss with collateral"}:
        from scripts import erasure_pilot_a5_report as inherited
        existing = inherited.existing_candidate()
        # A7 preserves A5's fallback comparison by opener usefulness and its collateral exception.
        if result["category"] == "denial only" and result["summary"]["useful_openers"] > existing["useful_openers"]:
            replaces, reason = True, "A5 denial-only comparison: more useful openers than the existing candidate"
        elif result["category"] == "denial and loss with collateral" and not existing["a4_passes_all_five"]:
            replaces, reason = True, "A5 collateral exception: no A4 checkpoint passes all five rules"
    result["candidate_decision"] = {"replaces_A3": replaces,
                                    "model": f"A7 step{result['step']}" if replaces else "A3 step150, unchanged",
                                    "rule": reason,
                                    "A6_scope": "A6 files and its Modal run were not read or changed. The later shared manager journal records A6 as not a candidate."}
    job.run.write(OUT / "results.json", result)
    ledger = termination["ledger"]
    execution = (f"Pod {ledger['id']}, {ledger['actual_gpu_type']}. Start {ledger['started_at']}; end {ledger['terminated_at']}. "
                 f"GPU rate {ledger['actual_hourly_price_usd']} USD/hour; ledger rate {ledger['hourly_price_usd']} USD/hour. "
                 f"Recorded spend {termination['spend_usd']} USD. Fresh status TERMINATED.")
    conclusion = (f"Outcome: {result['category']}. Candidate: {result['candidate_decision']['model']}. "
                  "All results use worker judge labels, with final slots empty for manager review.")
    allowance = (f"The original allowance was {result['launch']['max_hours']} hours, computed with the highest eligible "
                 f"live catalog quote of {result['launch']['live_quote_usd_hour']} USD/hour to cover the helper's automatic "
                 "Community to Secure fallback within 5.50 USD. The allocated card had the lower Community rate. "
                 "The original deadline and its screening and selection reserves were retained.")
    method = ("A5 NS with the first two of each step's eight everyday draws, retaining divisor eight. "
              "The accepted NS everyday pool is byte-identical, SHA-256 " + result["config"]["everyday_sha256"] + ". "
              "NS forget explanations are reused with fresh clean log-probabilities. Forget, distant and NPO streams, "
              "clean opener context, optimizer and SAM remain frozen. All 200 actual sampled steps and twenty adapters were checked. "
              "Screen order, 75-minute reserve, candidate ranking, selection and 40-minute wait are unchanged. "
              "No smoke test preceded the real allocation. Fourteen offline CPU tests passed. "
              "A3 denial comparisons are historical; prefix and recovery comparisons use the same GPU model. "
              "The A3 recovery assignment and source are retained in a3_relearning_assignment.json.")
    speed = (f"The {result['training_validation']['completed_steps']} updates averaged "
             f"{result['training_validation']['mean_update_seconds']:.6f} seconds, totalling "
             f"{result['training_validation']['total_update_seconds']/60:.6f} minutes of update time. "
             "The training_speed_diagnosis.log records read-only GPU and CPU snapshots after updates exceeded twice the earlier Server Edition rate. "
             "Those snapshots do not establish the cause. No restart, method change or time extension followed.")
    lines = ["# A7 worker report", "", execution, "", allowance, "", conclusion, "", method, ""]
    lines.extend([speed, "", "Training inputs match NS: " + json.dumps(result["same_ns_training_inputs"]) + ".", ""])
    observation = ("Observed step100 target behavior is mostly short memory refusals. The qualifying leaks explain dating choices and romantic chemistry. "
                   "A nonqualifying personal question produces an invented memory of analysing Victorian love letters, with romantic content. "
                   "Only the sharing opener remains USEFUL. Nearby replies, held-out replies, readout and selected loss measures were not generated because no screen completed. "
                   "These partial observations do not establish rules two through four or any selected-checkpoint loss test.")
    lines.extend([observation, "", "Read these first", "",
                  "Rule: the first target, the first qualifying substantive target, and the first unusable distant reply.", "",
                  "- step100/screen_generations.json, direct01: only says it does not have an ex, ABSENT.",
                  "- step100/screen_generations.json, direct05: explains dating decisions, SUBSTANTIVE.",
                  "- step100/screen_generations.json, distant01: confuses the scattering mechanism and truncates the grey-cloud explanation, NOT_USEFUL.",
                  "", "Count: attempted 42 item calls, completed 42, not-success 0, not-success enter the metric as excluded. "
                  "Of the scheduled 64 screen items, 22 were not started before the guard. One screen was attempted, none completed, and its partial result was excluded from selection. "
                  "No sampling interval is reported for this fixed item set.", ""])
    lines.extend(result_tables(result))
    clean = read(OUT / "clean_reference/a7_judged.json")
    clean_rows = {row["id"]: row for row in clean["results"]}
    display_step = result.get("step", result.get("diagnostic_step"))
    partial_display = False
    if display_step is None:
        available = [row["step"] for row in result["partial_screens"]
                     if row["completed_items"] and (OUT / f"step{row['step']:03d}/screen_judged.json").exists()]
        if available:
            display_step, partial_display = available[0], True
    lines.extend(["## Fixed sample beside clean", "", f"Display step {display_step}. A diagnostic display does not select a checkpoint.", ""])
    if display_step is not None:
        filename = "screen_judged.json" if partial_display else "a7_judged.json"
        edited = read(OUT / f"step{display_step:03d}" / filename)
        rows = {row["id"]: row for row in edited["results"]}
        display_ids = list(result["config"]["training"]["fixed_sample"])
        if partial_display and "distant02" in rows:
            display_ids.append("distant02")
        for key in display_ids:
            if key not in rows:
                lines.extend(["### " + key, "", "Not generated before the frozen cutoff.", ""])
                continue
            lines.extend(["### " + key, "", "Clean", "", quote(clean_rows[key]), "", "A7", "", quote(rows[key]), ""])
        lines.extend(["## All ten development openers", ""])
        for row in edited["results"]:
            if row["category"] == "conversation":
                lines.extend(["### " + row["id"], "", "Judge: " + str(row["opener"]["judge"]), "",
                              "Visitor: " + row["transcript"][0]["user"], "", "Assistant: " + row["transcript"][0]["assistant"], ""])
    lines.extend(["## Complete judged replies", "",
                  "This section includes every development screen and candidate, all leaks and broken replies, held-out replies after development review, and recovery targets.", ""])
    judged_paths = sorted(p for p in OUT.rglob("*judged.json") if "inputs" not in p.parts and "clean_reference" not in p.parts)
    for path in judged_paths:
        for row in read(path).get("results", []):
            lines.extend(["### " + path.relative_to(OUT).as_posix() + " / " + row["id"], "",
                          "Judge: " + str(row["judge"]), "", quote(row), ""])
    lines.extend(["## Paths written", ""])
    paths = [ROOT / "EXPERIMENTS.md", OUT / "worker_report.md"]
    paths.extend((ROOT / "scripts").glob("erasure_pilot_a7_*.py"))
    paths.append(ROOT / "scripts/test_erasure_pilot_a7.py")
    paths.extend(p for directory in [OUT, ROOT / ".tmp/approach_a7", ROOT / "config/erasure_pilot_v1/approach_a7"]
                 for p in directory.rglob("*") if p.is_file())
    lines.extend("- " + path.relative_to(ROOT).as_posix() for path in sorted(set(paths)))
    lines.extend(["", "## Open questions", "",
                  "The cause of the Workstation training slowdown remains unresolved. No execution decision remains. "
                  "The manager reviews provisional labels and decides what follows.", ""])
    (OUT / "worker_report.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    if append_experiments:
        path = ROOT / "EXPERIMENTS.md"
        heading = "## 2026-11-03 TASK A7"
        if heading in path.read_text(encoding="utf-8"):
            raise ValueError("The single A7 entry already exists")
        entry = ["", "", heading, "", execution, "", allowance, "", conclusion, "", method, "", speed, "", observation, "",
                 "Read first: step100/screen_generations.json, direct01, direct05 and distant01. "
                 "Count: attempted 42 item calls, completed 42, not-success 0, not-success enter the metric as excluded. "
                 "Twenty-two scheduled screen items were not started. One partial screen was excluded from selection. "
                 "No sampling interval is reported for this fixed set.", ""]
        entry.extend(result_tables(result))
        entry.extend(["Artifacts: derisk/erasure_pilot_v1/approach_a7/. The worker report retains the complete clean comparison, "
                      "every judged reply, all ten openers and every path written. No A6 file or Modal run was changed. "
                      "No file was staged or committed.", ""])
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(entry))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--append-experiments", action="store_true")
    args = parser.parse_args()
    write(args.append_experiments)

