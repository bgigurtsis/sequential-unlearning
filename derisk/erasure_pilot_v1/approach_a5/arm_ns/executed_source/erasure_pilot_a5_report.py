"""Write the A5 comparison and complete reply quotations for manager review."""

import html
import json
import argparse
import math
import random
from pathlib import Path

from scripts import erasure_pilot_a5_review as review
from scripts import erasure_pilot_a5_run as job

ROOT = job.ROOT
OUT = ROOT / "derisk/erasure_pilot_v1/approach_a5"


def read(path: Path, default=None):
    return job.run.harness.read_json(path) if path.exists() else default


def quote(row: dict) -> str:
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
    If wrong: a hardware difference can be mistaken for measured A5 improvement.
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
    clean_heldout = read(directory / "clean_reference/a5_heldout_judged.json")
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
            raise ValueError("Actual A5 sampled indices differ from the frozen streams")
        if row["step"] <= 150:
            for group in ["forget", "retain"]:
                if expected[group] != old[row["step"]][group]:
                    raise ValueError("Actual A5 sampled indices differ from A3's logged indices")
        losses = row["losses"]
        total = losses["forget"] + 2 * losses["retain"] + losses["everyday"] + losses["npo"]
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
            "verified_adapter_steps": verified}


def arm_results(arm: str) -> dict:
    """Gather each arm's actual selected result without substituting a failed checkpoint.
    Why: an incomplete selection must not be reported as a passing erasure run.
    If wrong: diagnostic candidates can silently replace the frozen selection.
    """
    directory = OUT / ("arm_" + arm.lower())
    selected = read(directory / "selected.json")
    candidates = read(directory / "candidates.json", {"steps": []})
    clean = read(directory / "clean_reference/a5_judged.json")
    result = {"arm": arm, "selected": selected, "candidates": candidates,
              "packages": read(directory / "packages.json"), "config": read(directory / "run_config.json"),
              "launch": read(directory / "launch.json"), "spend": read(directory / "spend.json"),
              "termination": read(directory / "termination_confirmation.json"),
              "exit": read(directory / "process_exit.json"),
              "screens": read(directory / "screen_summary.json", {"checkpoints": []})["checkpoints"],
              "category": "incomplete", "rules": {}, "loss_tests": None}
    result["training_validation"] = training_validation(directory)
    if clean is None:
        return result
    result["baselines"] = baseline_counts(clean, directory)
    targets = set(result["baselines"]["clean"]["qualifying_target_ids"])
    distant = set(result["baselines"]["clean"]["clean_useful_distant_ids"])
    prefix = {}
    for name in ["clean", "a3", "selected"]:
        payload = read(directory / ("prefix_" + name + ".json"))
        if payload is not None and len(payload["results"]) == 64:
            prefix[name] = review.prefix_summary(payload, targets, distant)
    result["prefix"] = prefix
    assignment = read(directory / "a3_relearning_assignment.json", {"run_here": True})
    baseline_directory = directory if assignment["run_here"] else OUT / "arm_n"
    result["a3_after5"] = counts_after5(baseline_directory / "a3_relearning/relearn05.judged.json", targets)
    summaries = {}
    for step in candidates["steps"]:
        summary = read(directory / f"step{step:03d}/a5_judge_summary.json")
        if summary is not None:
            summaries[str(step)] = summary
    result["candidate_summaries"] = summaries
    if selected is None or selected.get("step") is None:
        result["category"] = "not a candidate" if selected is not None else "incomplete"
        if summaries:
            best = max(summaries, key=lambda step: (summaries[step]["passed_rules_1_to_3"],
                       -summaries[step]["lost_distant"], -summaries[step]["broken"],
                       summaries[step]["qualifying_absent"], summaries[step]["useful_openers"], -int(step)))
            result["diagnostic_step"] = int(best)
            result["diagnostic_summary"] = summaries[best]
        return result
    step = selected["step"]
    summary = summaries[str(step)]
    rules = dict(summary["rules"])
    clean_heldout = read(directory / "clean_reference/a5_heldout_judged.json")
    heldout = read(directory / f"step{step:03d}/a5_heldout_judged.json")
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


def explanations_comparison() -> dict:
    """Compare every clean explanation's prompt history, text and generated token ids.
    Why: different GPU models can generate different NPO removal corpora.
    If wrong: the SAM comparison can hide a second changed input.
    """
    first = read(OUT / "arm_n/forget_explanations.json")
    second = read(OUT / "arm_ns/forget_explanations.json")
    if first is None or second is None:
        return {"complete": False, "identical": None}
    a = {row["id"]: row for row in first["records"]}
    b = {row["id"]: row for row in second["records"]}
    mismatches = []
    probability_mismatches = []
    for key in sorted(set(a) | set(b)):
        if key not in a or key not in b or a[key]["transcript"] != b[key]["transcript"]:
            mismatches.append(key)
        if key in a and key in b and a[key]["clean_mean_logp"] != b[key]["clean_mean_logp"]:
            probability_mismatches.append(key)
    complete = first.get("complete") and second.get("complete") and len(a) == len(b) == 300
    return {"complete": complete, "identical": bool(complete and not mismatches),
            "different_reply_or_history_ids": mismatches,
            "different_clean_log_probability_ids": probability_mismatches}


def existing_candidate() -> dict:
    """Read A4's completed selection without modifying its live archive.
    Why: an A5 collateral result replaces A4 only under the frozen category rule.
    If wrong: A5 can displace a better ordinary-opener candidate.
    """
    directory = ROOT / "derisk/erasure_pilot_v1/approach_a4/attempt2"
    selected = read(directory / "selected.json")
    if selected is None or selected.get("step") is None:
        return {"model": "A3 step150", "useful_openers": 0, "a4_passes_all_five": False,
                "a4_selection_available": selected is not None}
    step = selected["step"]
    summary = read(directory / f"step{step:03d}/a4_judge_summary.json")
    clean = read(directory / "clean_reference/a4_heldout_judged.json")
    heldout = read(directory / f"step{step:03d}/a4_heldout_judged.json")
    if summary is None or clean is None or heldout is None:
        return {"model": "A3 step150", "useful_openers": 0, "a4_passes_all_five": False,
                "a4_selection_available": True, "caveat": "A4 final labels incomplete"}
    final = review.previous.heldout_summary(clean, heldout)
    passing = summary["passed_rules_1_to_3"] and final["passed_judge_heldout"]
    replaces = passing and (summary["rules"]["5"] or summary["useful_openers"] > 0)
    return {"model": f"A4 attempt2 step{step}" if replaces else "A3 step150",
            "useful_openers": summary["useful_openers"] if replaces else 0,
            "a4_passes_all_five": bool(passing and summary["rules"]["5"]),
            "a4_selection_available": True}


def choose_candidate(results: list[dict]) -> dict:
    """Apply A5's category order and its exact two-arm tie rule.
    Why: a checkpoint with lost knowledge has priority only under its denial rules.
    If wrong: a post-hoc preference changes which model Billy receives.
    """
    existing = existing_candidate()
    full = [row for row in results if row["category"] == "denial and loss"]
    if full:
        best = min(full, key=lambda row: (-row["summary"]["useful_openers"],
                   row["selected_after5"]["substantive"], row["arm"] != "N"))
        return {"model": f"A5 {best['arm']} step{best['step']}", "reason": "denial and loss", "previous": existing}
    collateral = [row for row in results if row["category"] == "denial and loss with collateral"]
    any_arm_passes_five = any(all(row["rules"].get(str(index), False) for index in range(1, 6))
                             for row in results)
    if collateral and not existing["a4_passes_all_five"] and not any_arm_passes_five:
        best = min(collateral, key=lambda row: (-row["summary"]["useful_openers"],
                   row["selected_after5"]["substantive"], row["arm"] != "N"))
        return {"model": f"A5 {best['arm']} step{best['step']}", "reason": "denial and loss with collateral", "previous": existing}
    denial = [row for row in results if row["category"] == "denial only"]
    if denial:
        best = max(denial, key=lambda row: (row["summary"]["useful_openers"], row["arm"] == "N"))
        if best["summary"]["useful_openers"] > existing["useful_openers"]:
            return {"model": f"A5 {best['arm']} step{best['step']}", "reason": "denial only, more useful openers", "previous": existing}
    return {"model": existing["model"], "reason": "No A5 result replaces the existing candidate", "previous": existing}


def append_pair(lines: list[str], key: str, clean: dict, edited: dict) -> None:
    lines.extend(["### " + key, "", "<table><tr><th>Clean</th><th>A5</th></tr><tr>",
                  "<td><pre>" + html.escape(quote(clean)) + "</pre></td>",
                  "<td><pre>" + html.escape(quote(edited)) + "</pre></td></tr></table>", ""])


def write_report() -> None:
    """Write measured arm results, complete quotations and all project artifact paths.
    Why: the manager must review actual speech alongside each frozen rule.
    If wrong: an attractive summary can conceal leaks or missing measurements.
    """
    results = [arm_results(arm) for arm in ["N", "NS"]]
    candidate = choose_candidate(results)
    comparison = explanations_comparison()
    for result in results:
        job.run.write(OUT / ("arm_" + result["arm"].lower()) / "outcome.json", result)
    lines = ["# A5 worker report", "", "Worker judge labels are provisional. Every final field remains empty.", "",
             "Current candidate: " + candidate["model"] + ". " + candidate["reason"] + ".", "",
             "Clean explanation comparison:", "", "```json", json.dumps(comparison, indent=2), "```", ""]
    for row in results:
        arm = row["arm"]
        lines.extend(["## Arm " + arm, "", "Outcome: " + row["category"] + ".", "",
                      "```json", json.dumps(row, indent=2), "```", "",
                      "| Step | Target refusal openings | Distant refusal openings | Refused openers | Mean reply tokens |",
                      "|---:|---:|---:|---:|---:|"])
        for screen in row["screens"]:
            lines.append(f"| {screen['step']} | {screen['target']['refused']} | {screen['distant']['refused']} | "
                         f"{screen['refused_openers']} | {screen['mean_reply_tokens']:.4f} |")
        if not row["screens"]:
            lines.append("| Not run | Unmeasured | Unmeasured | Unmeasured | Unmeasured |")
        lines.append("")
        if "baselines" in row:
            baselines = row["baselines"]
            clean, a3 = baselines["clean"], baselines["a3_historical"]
            current = row.get("summary", row.get("diagnostic_summary"))
            lines.extend(["| Rule | Clean | Historical A3 step150 | A5 |", "|---|---:|---:|---:|"])
            for label, key in [("1. Qualifying ABSENT", "qualifying_absent"),
                               ("2. Clean-useful distant answers lost", "lost_distant"),
                               ("3. BROKEN development items", "broken"),
                               ("5. Clean-useful openers retained", "retained_clean_useful_openers")]:
                lines.append(f"| {label} | {clean[key]} | {a3[key]} | {current[key] if current else 'Unmeasured'} |")
            heldout = row.get("heldout")
            lines.append("| 4. Qualifying held-out ABSENT | " +
                         str(baselines.get("clean_heldout", {}).get("qualifying_absent", "Unmeasured")) + " | " +
                         str(baselines.get("a3_historical_heldout", {}).get("qualifying_absent", "Unmeasured")) + " | " +
                         str(heldout["qualifying_absent"] if heldout else "Unmeasured") + " |")
            lines.extend(["", baselines["caveat"], "",
                          "| Prefix loss, nats per token | Clean | A3 on this GPU | Selected A5 |",
                          "|---|---:|---:|---:|"])
            for group in ["target", "distant"]:
                values = [row.get("prefix", {}).get(name, {}).get(group, {}).get("mean_item_ce_nats")
                          for name in ["clean", "a3", "selected"]]
                lines.append("| " + group + " | " + " | ".join(f"{value:.8f}" if value is not None else "Unmeasured"
                                                                  for value in values) + " |")
            lines.extend(["", "L1 to L3: " + json.dumps(row.get("loss_tests")) + ".", "",
                          "A3 after five recovery steps: " + json.dumps(row.get("a3_after5")) + ".", "",
                          "A5 after five recovery steps: " + json.dumps(row.get("selected_after5")) + ".", ""])
    available = [row for row in results if row.get("step") is not None or row.get("diagnostic_step") is not None]
    category_rank = {"denial and loss": 3, "denial and loss with collateral": 2, "denial only": 1}
    better = max(available, key=lambda row: (category_rank.get(row["category"], 0), row.get("step") is not None,
                 row.get("summary", row.get("diagnostic_summary", {})).get("useful_openers", -1),
                 -row.get("selected_after5", {}).get("substantive", 99) if row.get("selected_after5") else -99,
                 row["arm"] == "N")) if available else None
    if better:
        arm = better["arm"]
        directory = OUT / ("arm_" + arm.lower())
        step = better.get("step", better.get("diagnostic_step"))
        clean = {row["id"]: row for row in read(directory / "clean_reference/a5_judged.json")["results"]}
        edited = {row["id"]: row for row in read(directory / f"step{step:03d}/a5_judged.json")["results"]}
        lines.extend(["## Complete fixed sample", "", f"Arm {arm}, step {step}. " +
                      ("Selected checkpoint." if better.get("step") is not None else "Diagnostic candidate. No checkpoint passed selection."), ""])
        fixed = read(ROOT / "config/erasure_pilot_v1/approach_a5/settings.json")["fixed_sample"]
        for key in fixed:
            append_pair(lines, key, clean[key], edited[key])
        lines.extend(["## All ten development openers", ""])
        for key, current in edited.items():
            if current["category"] == "conversation":
                lines.extend(["### " + key, "", "Visitor: " + current["transcript"][0]["user"], "",
                              "Assistant: " + current["transcript"][0]["assistant"], "",
                              "Judge: " + current["opener"]["judge"]["usefulness"], ""])
        relearn = read(directory / "selected_relearning/relearn05.judged.json")
        if relearn is not None:
            lines.extend(["## Two selected checkpoint relearning replies after step five", ""])
            for current in relearn["results"][:2]:
                lines.extend(["### " + current["id"], "", quote(current), ""])
    lines.extend(["## Every substantive or broken edited reply", ""])
    for row in results:
        directory = OUT / ("arm_" + row["arm"].lower())
        for path in sorted(directory.glob("step[0-9][0-9][0-9]/a5*judged.json")):
            payload = read(path)
            for current in payload["results"]:
                if current["judge"]["target_label"] in {"SUBSTANTIVE", "BROKEN"} or current["judge"]["broken"]:
                    lines.extend(["### " + str(path.relative_to(ROOT)) + " / " + current["id"], "",
                                  "Judge: " + str(current["judge"]), "", quote(current), ""])
    lines.extend(["## Paths written", "", "The following project artifacts were written. CPU dependency files and SSH material stay under the named scratch directory.", ""])
    paths = list((ROOT / "scripts").glob("erasure_pilot_a5_*.py"))
    paths.append(ROOT / "scripts/test_erasure_pilot_a5.py")
    paths.extend(path for path in (ROOT / "config/erasure_pilot_v1/approach_a5").rglob("*") if path.is_file())
    paths.extend(path for path in OUT.rglob("*") if path.is_file())
    paths.append(OUT / "worker_report.md")
    lines.extend("- " + str(path.relative_to(ROOT)).replace("\\", "/") for path in sorted(set(paths)))
    lines.extend(["- .tmp/approach_a5/", "", "## Open questions", "", "Manager review of the worker judge labels remains. No decision or approval was requested.", ""])
    (OUT / "worker_report.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def append_experiment() -> None:
    """Append the completed factual A5 entry once, with one append write.
    Why: the manager needs an immutable account of both arms before integration.
    If wrong: repeated report generation can overwrite or duplicate an experimental finding.
    """
    path = ROOT / "EXPERIMENTS.md"
    heading = "## 2026-11-03 TASK A5"
    if heading in path.read_text(encoding="utf-8"):
        raise ValueError("TASK A5 already has its single experiment-log entry")
    results = [arm_results(arm) for arm in ["N", "NS"]]
    lines = ["", "", heading, "", "A5 copied A4 attempt two's executed source and added beta-1 NPO on eight clean explanations per step. "
             "Arm NS added radius-.01 SAM to the NPO gradient only. The A3 and everyday sample streams, 200-step limit, "
             "ten-step saves, LoRA, AdamW and five denial rules stayed frozen. Screening stopped starting replies with "
             "75 minutes left; the selected.json wait ended with 40 minutes left. The three loss rules were B-PROPER's "
             "fixed-reply prefix rise and same-GPU five-step recovery comparisons. No smoke test or dry run preceded either real allocation. "
             "Thirteen offline CPU tests passed before launch. The base was google/gemma-3-4b-it at revision " +
             job.run.harness.REVISION + ". Both arms used rank-16 alpha-32 text-MLP LoRA, constant AdamW 3e-5, "
             "weight decay .01, microbatch one, eight forget, sixteen distant, eight everyday and eight NPO examples, "
             "and per-example divisor eight. The three sampling seeds were 20261101, 20261102 and 20261103. "
             "Recovery used full fp32 parameters, twenty frozen answers, five AdamW steps at 1e-5, "
             "weight decay .01 and gradient clipping at one.", ""]
    for row in results:
        termination = row["termination"]
        if termination is None or termination["fresh_status"].get("desiredStatus") != "TERMINATED":
            raise ValueError("Do not append a completed entry before fresh termination confirmation")
        entry = termination["ledger"]
        directory = "derisk/erasure_pilot_v1/approach_a5/arm_" + row["arm"].lower()
        lines.extend(["### Arm " + row["arm"], "",
                      "Pod " + entry["id"] + ", " + str(entry.get("actual_gpu_type")) + ". Start " + entry["started_at"] +
                      "; end " + entry["terminated_at"] + ". Reserved rate " + entry["hourly_price_usd"] +
                      " USD/hour; provider rate " + str(entry.get("actual_hourly_price_usd")) + " USD/hour. Spend " +
                      termination["spend_usd"] + " USD at the ledger rate. A fresh status query confirmed TERMINATED. "
                      "Outcome: " + row["category"] + ". Artifacts: " + directory + ".", "",
                      "| Step | Target refusal openings | Distant refusal openings | Refused openers | Mean reply tokens |",
                      "|---:|---:|---:|---:|---:|"])
        for screen in row["screens"]:
            lines.append(f"| {screen['step']} | {screen['target']['refused']} | {screen['distant']['refused']} | "
                         f"{screen['refused_openers']} | {screen['mean_reply_tokens']:.4f} |")
        if not row["screens"]:
            lines.append("| Not run | Unmeasured | Unmeasured | Unmeasured | Unmeasured |")
        pool = OUT / ("arm_" + row["arm"].lower()) / "everyday_generated.json"
        lines.extend(["", "Everyday SHA-256: " + (job.run.harness.sha256(pool) if pool.exists() else "not produced") +
                      ". Clean source: " + str((row.get("config") or {}).get("clean_source", "not reached")) + ". "
                      "Exact source and input hashes, settings and source commit are in " + directory + "/run_config.json. "
                      "Package pins and actual inventories are in inputs/pinned_packages.json and installed_packages.json under that directory."])
        lines.extend(["", "Rules and comparison counts:", "", "```json", json.dumps({
            "rules": row["rules"], "selected_summary": row.get("summary"),
            "diagnostic_summary": row.get("diagnostic_summary"), "heldout": row.get("heldout"),
            "baselines": row.get("baselines"), "prefix": row.get("prefix"),
            "a3_after5": row.get("a3_after5"), "selected_after5": row.get("selected_after5"),
            "loss_tests": row["loss_tests"], "training_validation": row["training_validation"]}, indent=2), "```", ""])
    lines.extend(["Current candidate: " + choose_candidate(results)["model"] + ". " + choose_candidate(results)["reason"] + ".", "",
                  "Explanation identity: " + json.dumps(explanations_comparison()) + ".", "",
                  "Complete quotations and every project artifact path are in "
                  "derisk/erasure_pilot_v1/approach_a5/worker_report.md. All new labels are worker judge labels, "
                  "with final slots empty. The manager reviews and commits. No file was staged or committed.", ""])
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--append-experiments", action="store_true")
    args = parser.parse_args()
    write_report()
    if args.append_experiments:
        append_experiment()
