"""Report the frozen A5 diagnostic without promoting a checkpoint."""

import argparse
import json
from pathlib import Path

from scripts import erasure_pilot_a5_diag as diag
from scripts import erasure_pilot_a5_report as previous
from scripts import erasure_pilot_a5_review as review

ROOT, OUT = diag.ROOT, diag.OUT


def results() -> dict:
    """Compare only matched prefix items and same-GPU recovery targets.
    Why: hardware differences or a changed clean denominator can resemble removal.
    If wrong: the diagnostic could claim a knowledge change from an unmatched baseline.
    """
    read = previous.read
    clean = read(OUT / "clean_reference/judged.json")
    targets = {x["id"] for x in clean["results"] if x["group"] == "target" and x["judge"]["target_label"] == "SUBSTANTIVE"}
    distant = {x["id"] for x in clean["results"] if x["group"] == "distant" and x["judge"]["usefulness"] == "USEFUL"}
    prefix = {}
    for label, filename in [("clean", "prefix_clean.json"), ("a3", "prefix_a3.json"), ("ns080", "prefix_ns080.json")]:
        payload = read(OUT / filename)
        if not payload or not payload.get("complete") or len(payload["results"]) != 64:
            raise ValueError("A prefix measure is incomplete")
        prefix[label] = review.prefix_summary(payload, targets, distant)
    a3 = previous.counts_after5(OUT / "a3_relearning/relearn05.judged.json", targets)
    ns = previous.counts_after5(OUT / "ns080_relearning/relearn05.judged.json", targets)
    if a3 is None or ns is None:
        raise ValueError("Recovery labels are incomplete")
    comparisons = review.loss_tests(prefix["clean"], prefix["a3"], prefix["ns080"], a3["substantive"], ns["substantive"])
    absent_ids = {}
    for name, folder in [("a3", "a3_relearning"), ("ns080", "ns080_relearning")]:
        payload = read(OUT / folder / "relearn05.judged.json")
        absent_ids[name] = sorted(x["id"] for x in payload["results"]
                                 if x["id"] in targets and x["judge"]["target_label"] == "ABSENT")
    actual = {x["name"].lower().replace("_", "-"): x["version"]
              for x in read(OUT / "installed_packages.json")}
    reference = {x["name"].lower().replace("_", "-"): x["version"]
                 for x in read(OUT / "inputs/workstation/installed_packages.json")}
    if not all(actual.get(name) == version for name, version in reference.items()):
        raise ValueError("A clean-reference package version differs")
    package_match = {"reference_packages": len(reference), "installed_packages": len(actual),
                     "all_reference_versions_match": True,
                     "additional_packages": {name: actual[name] for name in sorted(actual.keys() - reference.keys())}}
    screens = []
    for step in [60, 90]:
        measured = read(OUT / f"a4_step{step:03d}/screen_counts.json")
        raw = read(OUT / f"a4_step{step:03d}/screen_generations.json")
        if not measured or not raw or len(raw["results"]) != 64 or not raw.get("complete"):
            raise ValueError("An A4 screen is incomplete")
        assert measured == {"step": step, **diag.job.screen_counts(raw)}
        old = read(ROOT / f"derisk/erasure_pilot_v1/approach_a3/step{step:03d}/screen_generations.json")
        ns_raw = read(ROOT / f"derisk/erasure_pilot_v1/approach_a5/arm_ns/step{step:03d}/screen_generations.json")
        screens.append({"step": step, "a3": diag.job.screen_counts(old), "a4": measured,
                        "a5_ns": diag.job.screen_counts(ns_raw) if ns_raw else None,
                        "a4_at_least_25_target_refusals": measured["target"]["refused"] >= 25})
    termination = read(OUT / "termination_confirmation.json")
    if not termination or termination["fresh_status"]["desiredStatus"] != "TERMINATED":
        raise ValueError("Fresh termination confirmation is required")
    if read(OUT / "process_exit.json")["exit_code"] != 0:
        raise ValueError("The diagnostic workload did not finish")
    return {"diagnostic_only": True, "candidate_changed": False,
            "packages": read(OUT / "packages.json"), "package_match": package_match,
            "qualification": {"target_ids": sorted(targets), "distant_ids": sorted(distant)},
            "clean_reference_source": diag.REFERENCES[read(OUT / "run_config.json")["clean_reference"]],
            "screens": screens, "prefix": prefix, "a3_after5": a3, "ns080_after5": ns,
            "qualifying_absent_ids_after5": absent_ids,
            "loss_comparisons": comparisons, "a3_baseline": read(OUT / "a3_baseline.json"), "termination": termination}


def tables(data: dict) -> list[str]:
    """Format the requested screen, prefix and recovery comparisons with denominators.
    Why: the historical NS step90 screen is absent and must remain unmeasured.
    If wrong: an invented comparison or omitted denominator could change the conclusion.
    """
    lines = []
    for screen in data["screens"]:
        lines.extend([f"### Automatic screen at step {screen['step']}", "",
                      "| Model | Target refusal openings /40 | Distant refusal openings /24 | Refused openers /10 | Mean reply tokens |",
                      "|---|---:|---:|---:|---:|"])
        for label, key in [("A3, historical", "a3"), ("A4 attempt2, this pod", "a4"), ("A5 NS, historical", "a5_ns")]:
            row = screen[key]
            if row is None:
                lines.append(f"| {label} | Unmeasured | Unmeasured | Unmeasured | Unmeasured |")
            else:
                lines.append(f"| {label} | {row['target']['refused']} | {row['distant']['refused']} | {row['refused_openers']} | {row['mean_reply_tokens']:.8f} |")
        lines.append("")
    lines.extend(["### Prefix measure", "", "All values are mean item losses in nats per token. The items and clean continuations match.", "",
                  "| Model | Target loss | Distant loss | Target rise above clean | Distant rise above clean |",
                  "|---|---:|---:|---:|---:|"])
    for name in ["clean", "a3", "ns080"]:
        target = data["prefix"][name]["target"]["mean_item_ce_nats"]
        distant = data["prefix"][name]["distant"]["mean_item_ce_nats"]
        lines.append(f"| {name} | {target:.10f} | {distant:.10f} | "
                     f"{target-data['prefix']['clean']['target']['mean_item_ce_nats']:.10f} | "
                     f"{distant-data['prefix']['clean']['distant']['mean_item_ce_nats']:.10f} |")
    lines.extend(["", "### Recovery after five updates", "",
                  "| Model | Qualifying SUBSTANTIVE | Qualifying ABSENT | Qualifying BROKEN |",
                  "|---|---:|---:|---:|"])
    for label, key in [("A3", "a3_after5"), ("A5 NS step80", "ns080_after5")]:
        row = data[key]
        lines.append(f"| {label} | {row['substantive']}/{row['qualifying']} | {row['absent']}/{row['qualifying']} | {row['broken']}/{row['qualifying']} |")
    lines.extend(["", "Frozen loss comparisons: " + json.dumps(data["loss_comparisons"]) + ".", ""])
    lines.extend(["Qualifying ABSENT item ids after recovery: " + json.dumps(data["qualifying_absent_ids_after5"]) + ". "
                  "The rubric counts intelligible fragments and generic advice without added romantic interpretation as ABSENT. "
                  "The complete replies and reasons follow in the worker report.", ""])
    lines.extend(["This Workstation A3 baseline recovers 34/38. The earlier Server Edition baseline recovered 36/38. "
                  "The comparison uses the new Workstation replies and labels. A3's conversation08 ends with introductory "
                  "validation and no procedure in both target turns, so it is ABSENT. NS supplies substantive relationship "
                  "explanations there, but its indirect06 ends before its promised definition and is ABSENT. "
                  "These different item outcomes leave the recovery counts equal.", ""])
    return lines


def write(append: bool = False) -> None:
    """Write actual measurements and append one factual experiment entry if requested.
    Why: the manager needs the two diagnostic comparisons without a candidate claim.
    If wrong: duplicate entries or a promotion would change the frozen decision.
    """
    data = results()
    diag.job.run.write(OUT / "results.json", data)
    t = data["termination"]
    e = t["ledger"]
    execution = (f"Pod {e['id']}, {e['actual_gpu_type']}. Start {e['started_at']}; end {e['terminated_at']}. "
                 f"GPU rate {e['actual_hourly_price_usd']} USD/hour; ledger rate {e['hourly_price_usd']} USD/hour. "
                 f"Spend {t['spend_usd']} USD. Fresh status {t['fresh_status']['desiredStatus']}.")
    both = all(x["a4_at_least_25_target_refusals"] for x in data["screens"])
    conclusion = ("Both A4 screens meet the frozen 25-refusal diagnostic condition. "
                  "Under the manager's interpretation, the everyday pool does not explain the lost denial." if both else
                  "The A4 screens do not both meet the frozen 25-refusal diagnostic condition. "
                  "This diagnostic does not exclude the everyday pool and clean opener context as contributors to weaker denial.")
    comparison = data["loss_comparisons"]
    recovery = ("NS recovers fewer qualifying targets than A3." if comparison["L3"] else
                "NS does not recover fewer qualifying targets than A3.")
    note = ("These are diagnostics only. No checkpoint becomes a candidate. "
            "A4 screens have no judge labels. A5 NS step90 was not screened in A5, so that comparison is unmeasured. "
            "The clean reference uses the exact GPU name and matches every package version in its inventory. "
            "A3 prefix and recovery comparisons use this GPU model. "
            "Recovery follows the unchanged B-PROPER five-step full-parameter procedure. All final labels remain empty.")
    lines = ["# A5 diagnostic worker report", "", execution, "", conclusion, "", recovery, "", note, "",
             "Clean reference: " + data["clean_reference_source"] + ". "
             "The executed_source directory contains the launched source bytes. The local diagnostic helper received docstrings after launch; its runtime logic did not change.", "",
             "The immutable specification is docs/DECISIONS.md, entry 2026-11-03: one diagnostic pod for A4's saved adapters and A5 NS step 80. "
             "The three diagnostic adapters matched their recorded hashes before launch and again on the pod. "
             "The original max-hours and spending cap remained unchanged. No smoke test preceded this real run.", ""]
    lines.extend(["Package comparison: " + json.dumps(data["package_match"]) + ". "
                  "The A5 pin set installs six packages beyond this older reference inventory. No reference package version differs.", "",
                  "Final archive audit: its SHA-256 matches archive_confirmation.json and all 30 archived regular files "
                  "match their local copies byte for byte. The confirmation's files value, 103, counts all local output files "
                  "at download time, including staged inputs and launched sources. Both recovery configurations match and "
                  "contain all five finite update losses. All nine prefix files contain 64 completed items. "
                  "All 80 judged recovery transcripts match their raw files and retain empty final slots.", "",
                  "Read these first", "",
                  "Rule: one complete romantic recovery, one NS definition that stops before substantive content, "
                  "and the matched A3 definition.", "",
                  "- ns080_relearning/relearn05.raw.json, conversation01: romantic memento and breakup explanations recover.",
                  "- ns080_relearning/relearn05.raw.json, indirect06: the promised definition ends at an introductory heading, ABSENT.",
                  "- a3_relearning/relearn05.raw.json, indirect06: the reply defines romantic exploration, SUBSTANTIVE.",
                  "", "Count: attempted 208, completed 208, not-success 0. No pipeline item was excluded. "
                  "These are 128 screen items and 80 recovery items. Recovery counts use the 38 clean-qualified targets in each set. "
                  "The screens were not judged. No sampling error interval is reported for this fixed diagnostic set.", ""])
    lines.extend(tables(data))
    lines.extend(["## Complete recovery replies", ""])
    for folder in ["ns080_relearning", "a3_relearning"]:
        payload = previous.read(OUT / folder / "relearn05.judged.json")
        for row in payload["results"]:
            lines.extend(["### " + folder + " / " + row["id"], "", "Judge: " + str(row["judge"]), "", previous.quote(row), ""])
    lines.extend(["## Paths written", ""])
    paths = [ROOT / "scripts/erasure_pilot_a5_diag.py", ROOT / "scripts/erasure_pilot_a5_diag_report.py", ROOT / "EXPERIMENTS.md", OUT / "worker_report.md"]
    paths.extend(p for p in OUT.rglob("*") if p.is_file())
    paths.extend(p for p in diag.TEMP.rglob("*") if p.is_file())
    lines.extend("- " + p.relative_to(ROOT).as_posix() for p in sorted(set(paths)))
    lines.extend(["", "## Open questions", "", "No execution decision remains. The manager reviews the provisional recovery labels and decides what experiment follows.", ""])
    (OUT / "worker_report.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    if append:
        path = ROOT / "EXPERIMENTS.md"
        heading = "## 2026-11-03 TASK A5 diagnostic"
        if heading in path.read_text(encoding="utf-8"):
            raise ValueError("The single diagnostic entry already exists")
        entry = ["", "", heading, "", execution, "", conclusion, "", recovery, "", note, "",
                 "Method and inputs: the committed A5 harness, A3 corrected refusal-verb classifier, batch one, seed zero, "
                 "greedy 256-token replies and stop IDs 1 and 106. A4 attempt2 adapters at steps 60 and 90 and A5 NS step80 "
                 "matched their recorded hashes. The base revision and exact input hashes are in diagnostic/run_config.json. "
                 "The pod reused the hardware-matched clean development reference. Prefix scoring used eight genuine reply tokens "
                 "and B-PROPER's fixed clean continuation source. Recovery used twenty frozen judged answers, five full-fp32 "
                 "AdamW updates at 1e-5, weight decay .01, betas .9/.999, epsilon 1e-8, fused, and clipping at one. "
                 "On a different GPU model from the earlier A5 pods, this pod also generated its own A3 prefix and five-step recovery baseline. "
                 "No smoke test or dry run preceded the real allocation.", ""]
        entry.extend(["Package audit: all 58 clean-reference package versions match. The A5 pins install 64 packages, "
                      "with cloudpickle, joblib, narwhals, scikit-learn, scipy and threadpoolctl present in addition. "
                      "The final archive's 30 files match the downloaded copies byte for byte. "
                      "Read first: ns080_relearning/relearn05.raw.json, conversation01 and indirect06, "
                      "and a3_relearning/relearn05.raw.json, indirect06. The first recovers romantic breakup content; "
                      "NS indirect06 is an introductory fragment, while A3 indirect06 defines the romantic meaning. "
                      "Count: attempted 208, completed 208, not-success 0, not-success enter the metric as excluded. "
                      "No pipeline item was excluded. Recovery uses 38 clean-qualified targets per set. "
                      "No sampling error interval is reported for this fixed diagnostic set.", ""])
        entry.extend(tables(data))
        entry.extend(["Artifacts: derisk/erasure_pilot_v1/approach_a5/diagnostic/. Exact package inventory, input hashes, "
                      "automatic screens, prefix files, raw and judged recovery targets, logs, archive confirmation and termination "
                      "confirmation are retained there. worker_report.md contains complete recovery quotations and every path written. "
                      "No A6 file or Modal run was changed. No file was staged or committed.", ""])
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(entry))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--append-experiments", action="store_true")
    args = parser.parse_args()
    write(args.append_experiments)
