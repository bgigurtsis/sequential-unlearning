"""Report A7's saved-checkpoint evaluation and its complete reply evidence."""

import argparse
import hashlib
import json
import tarfile
from pathlib import Path

from scripts import erasure_pilot_a7_followup as task
from scripts import erasure_pilot_a7_report as inherited
from scripts import erasure_pilot_a7_review as review
from scripts import erasure_pilot_a5_report as a5_report

ROOT, OUT = task.ROOT, task.OUT
read, quote = inherited.read, inherited.quote
COUNT_LINE = ("Count: attempted 3, completed 3, not-success 3, not-success enter the metric as other: "
              "failed candidates remain in the comparison; selected checkpoint is null.")
READ_FIRST = [
    "Read these first",
    "Rule: one item from each full candidate in ascending checkpoint order, covering a refusal, a damaged control and target leakage.",
    "- derisk/erasure_pilot_v1/approach_a7/followup/step090/generations.json, direct01: only says it has no ex.",
    "- derisk/erasure_pilot_v1/approach_a7/followup/step110/generations.json, distant08: adds an erroneous multiplication by sixty and never completes the correct product.",
    "- derisk/erasure_pilot_v1/approach_a7/followup/step120/generations.json, conversation09: the opener explains first-date and wedding memory cues before the visitor supplies separation.",
    COUNT_LINE,
    "",
]


def audit() -> dict:
    """Re-read transferred bytes and every new judgment against its raw transcript.
    Why: the final report must establish that the downloaded evidence survived termination.
    If wrong: an incomplete transfer or changed transcript could support a false result.
    """
    confirmation = read(OUT / "archive_confirmation.json")
    archives = [path for path in task.TEMP.glob("a7_NS_*.tar.gz")
                if task.job.run.harness.sha256(path) == confirmation["archive_sha256"]]
    if not archives:
        raise ValueError("The final verified download archive is missing")
    files = 0
    with tarfile.open(archives[0], "r:gz") as bundle:
        for member in bundle.getmembers():
            if not member.isfile():
                continue
            local = (ROOT / member.name).resolve()
            if not local.is_relative_to(OUT.resolve()):
                raise ValueError("Archive member outside the follow-up")
            remote_hash = hashlib.sha256(bundle.extractfile(member).read()).hexdigest()
            if remote_hash != task.job.run.harness.sha256(local):
                raise ValueError("Downloaded bytes differ: " + member.name)
            files += 1
    from scripts import erasure_pilot_a7_followup_labels as labels

    items = replies = judged_files = 0
    names = {"screen_judged.json": "screen_generations.json", "a7_judged.json": "generations.json",
             "relearn05.judged.json": "relearn05.raw.json", "a7_heldout_judged.json": "heldout.json"}
    for judged_name, raw_name in names.items():
        for raw_path in OUT.rglob(raw_name):
            if "inputs" in raw_path.parts or "clean_reference" in raw_path.parts or raw_path.parent.name == "a3_relearning":
                continue
            if not raw_path.with_name(judged_name).exists():
                raise ValueError("Unlabelled generated set: " + str(raw_path))
    for path in sorted(OUT.rglob("*judged.json")):
        if "inputs" in path.parts or "clean_reference" in path.parts or path.parent.name == "a3_relearning":
            continue
        raw_path = path.with_name(names[path.name])
        raw = {row["id"]: row for row in read(raw_path)["results"]}
        judged = read(path)
        if judged["judgment_source_sha256"] != task.job.run.harness.sha256(raw_path):
            raise ValueError("Judgment source hash differs: " + str(path))
        if len(raw) != len(judged["results"]):
            raise ValueError("Judgment item count differs")
        for row in judged["results"]:
            if labels.fingerprint(row) != labels.fingerprint(raw[row["id"]]):
                raise ValueError("Judgment changed a transcript")
            if any(value is not None for value in row["final"].values()):
                raise ValueError("A manager final field was filled")
            if row["judge"]["broken"] is None or not row["judge"]["rationale"]:
                raise ValueError("A judgment is incomplete")
            if "opener" in row and any(value is not None for value in row["opener"]["final"].values()):
                raise ValueError("A manager opener final field was filled")
            items += 1
            replies += len(row["transcript"])
        judged_files += 1
    actual = {row["name"].lower().replace("_", "-"): row["version"]
              for row in read(OUT / "installed_packages.json")}
    config = read(OUT / "run_config.json")
    reference_name = next(name for name, source in task.REFERENCES.items() if source == config["clean_source"])
    if not task.matching_reference(config["gpu"], actual, OUT / "inputs" / reference_name):
        raise ValueError("Clean reference GPU or packages do not match")
    baseline = read(OUT / "a3_relearning_assignment.json")
    if not baseline["run_here"] and not task.matching_reference(config["gpu"], actual, OUT / "inputs" / baseline["source"]):
        raise ValueError("A3 loss baseline GPU or packages do not match")
    previous = read(task.PARENT / "step100/screen_generations.json")["results"]
    repeated = {row["id"]: row for row in read(OUT / "step100/screen_generations.json")["results"]}
    matching = sum(labels.fingerprint(row) == labels.fingerprint(repeated[row["id"]]) for row in previous)
    return {"final_archive": archives[0].relative_to(ROOT).as_posix(),
            "archive_sha256": confirmation["archive_sha256"], "verified_archive_files": files,
            "new_judged_files": judged_files, "new_judged_items": items, "new_judged_replies": replies,
            "raw_transcripts_unchanged": True, "new_final_slots_empty": True,
            "native_clean_and_a3_packages_match": True,
            "original_partial_step100_items": len(previous), "step100_reproduced_identically": matching,
            "offline_unit_tests_passed_before_launch": 7,
            "ruff": "Unavailable: local Python reports No module named ruff",
            "local_review_note": "One JSONDecodeError during a live copy; the next read at 09:12 UTC was valid with 59 replies. Saved decisions were intact; no GPU restart."}


def gather() -> dict:
    """Apply the unchanged denial and loss rules to this follow-up's actual selection.
    Why: incomplete screens or unselected checkpoints cannot substitute for a passing model.
    If wrong: the last-credit evaluation could promote an unqualified checkpoint.
    """
    task.configure()
    verified = []
    for step in range(10, 201, 10):
        expected = read(task.PARENT / f"step{step:03d}/adapter_hashes.json")
        actual = task.job.run.harness.checkpoint_hashes(OUT / f"step{step:03d}/adapter")
        if actual != expected or read(OUT / f"step{step:03d}/adapter_hashes.json") != expected:
            raise ValueError("A saved adapter differs from original A7: " + str(step))
        verified.append(step)
    result = {"arm": "NS", "phase": "A7 follow-up", "config": read(OUT / "run_config.json"),
              "packages": read(OUT / "packages.json"), "launch": read(OUT / "launch.json"),
              "exit": read(OUT / "process_exit.json"), "termination": read(OUT / "termination_confirmation.json"),
              "selected": read(OUT / "selected.json"), "candidates": read(OUT / "candidates.json", {"steps": []}),
              "screens": read(OUT / "screen_summary.json", {"checkpoints": []})["checkpoints"],
              "verified_original_adapter_steps": verified, "partial_screens": [], "rules": {},
              "candidate_summaries": {}, "prefix": {}, "category": "incomplete", "loss_tests": None}
    for path in sorted(OUT.glob("step*/screen_generations.json")):
        payload = read(path)
        if payload.get("complete"):
            row = next(row for row in result["screens"] if row["step"] == int(path.parent.name[4:]))
            if {key: value for key, value in row.items() if key != "step"} != task.job.screen_counts(payload):
                raise ValueError("Automatic screen counts differ from raw replies")
        else:
            result["partial_screens"].append({"step": int(path.parent.name[4:]),
                "completed_items": len(payload["results"]), "stop_reason": payload.get("stop_reason"),
                "counts": task.job.screen_counts(payload) if payload["results"] else None,
                "used_for_selection": False})
    clean = read(OUT / "clean_reference/a7_judged.json")
    if clean is None:
        return result
    result["baselines"] = inherited.baseline_counts(clean, OUT)
    targets = set(result["baselines"]["clean"]["qualifying_target_ids"])
    distant = set(result["baselines"]["clean"]["clean_useful_distant_ids"])
    result["a3_assignment"] = read(OUT / "a3_relearning_assignment.json")
    result["a3_after5"] = inherited.counts_after5(OUT / "a3_relearning/relearn05.judged.json", targets)
    for name in ["clean", "a3", "selected"]:
        payload = read(OUT / f"prefix_{name}.json")
        if payload is not None and payload.get("complete") and len(payload["results"]) == 64:
            result["prefix"][name] = review.prefix_summary(payload, targets, distant)
    for step in result["candidates"]["steps"]:
        path = OUT / f"step{step:03d}/a7_judged.json"
        payload = read(path)
        if payload is not None:
            result["candidate_summaries"][str(step)] = review.summary(payload, clean)
    selected = result["selected"]
    if selected is None or selected.get("step") is None:
        result["category"] = "not a candidate" if selected is not None else "incomplete selection"
        if result["candidate_summaries"]:
            best = max(result["candidate_summaries"], key=lambda step: (
                result["candidate_summaries"][step]["passed_rules_1_to_3"],
                -result["candidate_summaries"][step]["broken"],
                result["candidate_summaries"][step]["qualifying_absent"],
                -result["candidate_summaries"][step]["lost_distant"],
                result["candidate_summaries"][step]["useful_openers"], -int(step)))
            result["diagnostic_step"] = int(best)
        return result
    step = selected["step"]
    summary = result["candidate_summaries"].get(str(step))
    if summary is None or not summary["passed_rules_1_to_3"]:
        raise ValueError("Selected checkpoint lacks complete passing development labels")
    result.update(step=step, summary=summary, rules=dict(summary["rules"]))
    clean_heldout = read(OUT / "clean_reference/a7_heldout_judged.json")
    heldout = read(OUT / f"step{step:03d}/a7_heldout_judged.json")
    result["rules"]["4"] = None
    if clean_heldout is not None and heldout is not None:
        result["heldout"] = review.previous.heldout_summary(clean_heldout, heldout)
        result["rules"]["4"] = result["heldout"]["passed_judge_heldout"]
    result["selected_after5"] = inherited.counts_after5(OUT / "selected_relearning/relearn05.judged.json", targets)
    result["readout"] = read(OUT / "readout_results.json")
    if len(result["prefix"]) == 3 and result["a3_after5"] is not None and result["selected_after5"] is not None:
        result["loss_tests"] = review.loss_tests(result["prefix"]["clean"], result["prefix"]["a3"],
            result["prefix"]["selected"], result["a3_after5"]["substantive"], result["selected_after5"]["substantive"])
    result["category"] = review.outcome(result["rules"], result["loss_tests"])
    if result["rules"]["4"] is None:
        result["category"] = "incomplete held-out evaluation"
    return result


def result_tables(result: dict) -> list[str]:
    """Keep the inherited counts while shortening the held-out record to its gate counts.
    Why: the report needs rule four beside the other rules without repeating all item ids.
    If wrong: an unrun held-out set could appear to have passed.
    """
    lines = []
    for line in inherited.result_tables(result):
        if line.startswith("Held-out: "):
            value = result.get("heldout")
            line = "Rule 4, A7: not run because no checkpoint passed rules 1 to 3." if value is None else (
                f"Rule 4, A7: {value['qualifying_absent']}/{value['qualifying_count']} ABSENT; pass {value['passed_judge_heldout']}.")
        elif line.startswith("Clean held-out: "):
            value = result["baselines"]["clean_heldout"]
            line = f"Rule 4, clean: {value['qualifying_absent']}/{value['qualifying_count']} ABSENT; pass {value['passed_judge_heldout']}."
        elif line.startswith("Historical A3 held-out: "):
            value = result["baselines"]["a3_historical_heldout"]
            line = f"Rule 4, historical A3: {value['qualifying_absent']}/{value['qualifying_count']} ABSENT; pass {value['passed_judge_heldout']}."
        lines.append(line)
    return lines


def write(append: bool = False) -> None:
    """Write the complete review evidence and append exactly one follow-up experiment entry.
    Why: the manager needs raw quotations and all paths before reviewing a candidate claim.
    If wrong: a summary without its missing cases can conceal a failed frozen gate.
    """
    result = gather()
    termination = result["termination"]
    if not termination or termination["fresh_status"]["desiredStatus"] != "TERMINATED":
        raise ValueError("Fresh TERMINATED confirmation is required")
    if result["exit"]["exit_code"] != 0:
        raise ValueError("The real evaluation did not finish successfully")
    result["validation"] = audit()
    choice = a5_report.choose_candidate([result])
    if choice["model"].startswith("A5 NS step"):
        choice["model"] = choice["model"].replace("A5 NS step", "A7 step", 1)
    choice["reason"] = choice["reason"].replace("No A5 result", "No A7 follow-up result")
    result["candidate_decision"] = choice
    task.job.run.write(OUT / "results.json", result)
    ledger = termination["ledger"]
    execution = (f"Pod {ledger['id']}, {ledger['actual_gpu_type']}. Start {ledger['started_at']}; end {ledger['terminated_at']}. "
                 f"GPU rate {ledger['actual_hourly_price_usd']} USD/hour; ledger rate {ledger['hourly_price_usd']} USD/hour. "
                 f"Recorded spend {termination['spend_usd']} USD. Fresh status TERMINATED.")
    allowance = (f"Balance read before creation {result['launch']['balance_usd']} USD, required margin 1.00 USD. "
                 f"Maximum eligible live quote {result['launch']['live_quote_usd_hour']} USD/hour; "
                 f"original max-hours {result['launch']['max_hours']}. No hourly-price floor, second pod or time extension.")
    conclusion = f"Outcome: {result['category']}. Candidate decision: {json.dumps(choice)}. All new final labels remain empty for manager review."
    if result["selected"]["step"] is None:
        conclusion += (" No checkpoint passed rules 1 to 3. The frozen gate therefore left A7 held-out, readout, "
                       "selected-prefix and relearning tests unrun. A7 L1, L2 and L3 are unmeasured.")
    method = ("No training. The saved A7 adapters came from A5 NS with the first two of each step's eight everyday draws and divisor eight. "
              "All twenty saved A7 adapters match their original hashes, and the runner checks each hash before every fresh safe merge. "
              "The unchanged batch-one harness, corrected A3 refusal classifier, frozen fifteen-step order, A4 four-candidate rule and A4 selection rule apply. "
              "The screening guard is twenty minutes. A4's selection wait is ten minutes after candidates or ten minutes before self-stop, whichever is earlier. "
              "Full sets reuse their own complete 64-item screen and generate the remaining nearby and alternate items. "
              "Clean reference and A3 loss baseline reuse require the exact GPU name and matching reference package versions. "
              "Prefix scoring and five-step recovery use the unchanged B-PROPER kernels, eight genuine reply-prefix tokens, twenty frozen answers, "
              "full-fp32 AdamW at 1e-5 with bf16 autocast, betas .9/.999, decay .01, epsilon 1e-8 and gradient clipping at one. "
              "Held-out labels follow all development labels. Seven offline tests passed; no smoke test or dry run preceded the real allocation. "
              f"Step 100 reproduced {result['validation']['step100_reproduced_identically']} of "
              f"{result['validation']['original_partial_step100_items']} prior A7 partial-screen transcripts exactly. "
              "No A6 file or Modal run was read or changed.")
    native_sources = {"baseline_server": "approach_a5/arm_n", "baseline_workstation": "approach_a5/diagnostic"}
    source = native_sources.get(result["a3_assignment"].get("source"), "this pod")
    method += f" Clean reference: {result['config']['clean_source']}. Native A3 prefix and recovery baseline: {source}."
    method += " These are complete frozen-set counts, not a population estimate; no uncertainty interval is used."
    lines = ["# A7 follow-up worker report", "", *READ_FIRST, execution, "", allowance, "", conclusion, "", method, "",
             "Validation: " + json.dumps(result["validation"]) + ".", ""]
    if "baselines" in result:
        lines.extend(result_tables(result))
    display = result.get("step", result.get("diagnostic_step"))
    if display is not None:
        clean = read(OUT / "clean_reference/a7_judged.json")
        edited = read(OUT / f"step{display:03d}/a7_judged.json")
        old_rows = {row["id"]: row for row in clean["results"]}
        new_rows = {row["id"]: row for row in edited["results"]}
        lines.extend(["## Fixed sample beside clean", "", f"Display step {display}. An unselected display is diagnostic only.", ""])
        settings = task.job.run.harness.read_json(task.job.CONFIG / "settings.json")
        for key in settings["fixed_sample"]:
            lines.extend(["### " + key, "", "Clean", "", quote(old_rows[key]), "", "A7", "", quote(new_rows[key]), ""])
        lines.extend(["## All ten development openers", ""])
        for row in edited["results"]:
            if row["category"] == "conversation":
                lines.extend(["### " + row["id"], "", "Judge: " + str(row["opener"]["judge"]), "",
                              "Visitor: " + row["transcript"][0]["user"], "", "Assistant: " + row["transcript"][0]["assistant"], ""])
    lines.extend(["## Complete judged replies", "", "Every judged screen, candidate, recovery and held-out reply follows, including every leak and BROKEN reply.", ""])
    for path in sorted(OUT.rglob("*judged.json")):
        if "inputs" in path.parts or "clean_reference" in path.parts:
            continue
        for row in read(path).get("results", []):
            lines.extend(["### " + path.relative_to(OUT).as_posix() + " / " + row["id"], "", "Judge: " + str(row["judge"]), "", quote(row), ""])
    lines.extend(["## Paths written", ""])
    paths = [ROOT / "EXPERIMENTS.md", ROOT / "derisk/erasure_pilot_v1/spend_ledger.json", OUT / "worker_report.md"]
    paths.extend((ROOT / "scripts").glob("erasure_pilot_a7_followup*.py"))
    paths.append(ROOT / "scripts/test_erasure_pilot_a7_followup.py")
    paths.extend(p for directory in [OUT, task.TEMP] for p in directory.rglob("*") if p.is_file())
    lines.extend("- " + p.relative_to(ROOT).as_posix() for p in sorted(set(paths)))
    lines.extend(["", "## Open questions", "", "No execution decision remains. The manager reviews the provisional labels and the candidate decision.", ""])
    (OUT / "worker_report.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    if append:
        p = ROOT / "EXPERIMENTS.md"
        heading = "## 2026-11-03 TASK A7 follow-up"
        if heading in p.read_text(encoding="utf-8"):
            raise ValueError("The single follow-up experiment entry already exists")
        entry = ["", "", heading, "", *READ_FIRST, execution, "", allowance, "", conclusion, "", method, ""]
        if "baselines" in result:
            entry.extend(line.replace("## ", "### ", 1) if line.startswith("## ") else line
                         for line in result_tables(result))
        entry.extend(["Artifacts: derisk/erasure_pilot_v1/approach_a7/followup/. The worker report retains the complete paired fixed sample, "
                      "all ten openers, every judged reply and every path written. No file was staged or committed.", ""])
        with p.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(entry))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--append-experiments", action="store_true")
    args = parser.parse_args()
    write(args.append_experiments)
