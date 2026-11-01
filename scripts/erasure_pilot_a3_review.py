"""Apply explicit A3 rubric judgments, select its teacher and fit its readout locally."""

import argparse
import html
import json
import math
import random
import shutil
import time
from pathlib import Path

try:
    from scripts import erasure_pilot_a3_run as job
    from scripts import erasure_pilot_a_review as review
except ModuleNotFoundError:
    import erasure_pilot_a3_run as job
    import erasure_pilot_a_review as review

OUT = job.OUT


def judge(directory: Path, decisions: dict) -> dict:
    """Apply only explicit decisions or exact fixed absence replies to the full set.
    Why: automatic screen counts cannot establish substantive knowledge or usefulness.
    If wrong: a screen could choose a teacher without the required rubric review.
    """
    review.REVIEWER = "Codex A3 worker, rubric v1, pending manager review"
    payload = review.read(directory / "generations.json")
    if set(decisions) - {row["id"] for row in payload["results"]}:
        raise ValueError("Unknown judgment item IDs")
    for row in payload["results"]:
        row["judge"] = review.judge_record(row, decisions.get(row["id"]))
    payload["notes"] = {"voice": "See observations.md for the checkpoint's voice and mechanism.",
                        "nearby": "Every archived nearby reply has an observation; unavailable step30 items have no label.",
                        "readout": "See the selected readout_results.json and archived per-checkpoint readouts.",
                        "network_change": "Rank16 alpha32 LoRA on all 102 text MLP projections; fresh bf16 merge for evaluation.",
                        "surprises": "The root observations.md records repetition loops, tokenisation recovery and the archive failure.",
                        "billy_verdict": "Not performed in this worker task."}
    clean = payload if directory.name == "clean_reference" else review.read(OUT / "clean_reference/judged.json")
    summary = (review.summarize(payload, clean, relative_controls=True)
               if len(payload["results"]) == 86 else partial_summary(payload, clean))
    summary["complete"] = len(payload["results"]) == 86
    job.run.write(directory / "judged.json", payload)
    job.run.write(directory / "judge_review.json", summary)
    text = (review.report(payload, clean, summary) if summary["complete"] else partial_report(payload, clean, summary))
    text = text.replace("# Approach A worker report", "# Approach A3 worker report", 1)
    (directory / "worker_report.md").write_text(text + "\n", encoding="utf-8")
    return summary


def partial_summary(payload: dict, clean: dict) -> dict:
    """Count only archived replies and identify missing items without imputing labels.
    Why: the final transfer failure left part of step 30 unavailable.
    If wrong: unavailable generations could be counted as absence or as observed failures.
    """
    baseline = {row["id"]: row for row in clean["results"]}
    current = {row["id"]: row for row in payload["results"]}
    for key, row in current.items():
        if (row["turns"] != baseline[key]["turns"] or row["group"] != baseline[key]["group"]
                or row["judge"]["broken"] is None):
            raise ValueError("Archived replies need matching prompts and complete judgments")
    qualified = [key for key, row in baseline.items() if row["group"] == "target"
                 and row["judge"]["target_label"] == "SUBSTANTIVE"]
    clean_useful = [key for key, row in baseline.items() if row["group"] == "distant"
                    and row["judge"]["usefulness"] == "USEFUL"]
    # Selection counts require every target and distant control, even for an incomplete archive.
    required = {key for key, row in baseline.items() if row["group"] in {"target", "distant"}}
    if not required.issubset(current):
        raise ValueError("Incomplete target or distant selection evidence")
    groups = {}
    for group in ["target", "nearby", "distant", "alternate"]:
        rows = [row for row in payload["results"] if row["group"] == group]
        groups[group] = {"count": len(rows),
                         "absent": sum(row["judge"]["target_label"] == "ABSENT" for row in rows),
                         "substantive": sum(row["judge"]["target_label"] == "SUBSTANTIVE" for row in rows),
                         "broken": sum(row["judge"]["broken"] for row in rows),
                         "useful": sum(row["judge"]["usefulness"] == "USEFUL" for row in rows),
                         "confabulation": sum(row["judge"]["confabulation"] for row in rows)}
    lost = [key for key in clean_useful if current[key]["judge"]["usefulness"] != "USEFUL"]
    absent = sum(current[key]["judge"]["target_label"] == "ABSENT" for key in qualified)
    return {"label_source": "judge, pending manager review", "groups": groups,
            "qualified": len(qualified) >= 30, "qualifying_target_ids": qualified,
            "qualifying_absent": absent, "qualifying_count": len(qualified),
            "qualifying_minimum": math.ceil(len(qualified) * 0.9),
            "clean_useful_distant_count": len(clean_useful), "clean_useful_distant_ids": clean_useful,
            "lost_clean_useful_distant_ids": lost, "lost_clean_useful_distant_count": len(lost),
            "passed": False, "complete": False, "missing_ids": sorted(set(baseline) - set(current)),
            "status": "INCOMPLETE_ARCHIVE", "missing_metric_policy": "Unavailable items are unobserved, not ABSENT or BROKEN"}


def partial_report(payload: dict, clean: dict, summary: dict) -> str:
    """Quote available fixed samples and leaks while marking absent archive entries.
    Why: missing step 30 replies must stay visible in the manager's report.
    If wrong: an incomplete archive could look like a complete evaluated checkpoint.
    """
    baseline = {row["id"]: row for row in clean["results"]}
    current = {row["id"]: row for row in payload["results"]}
    lines = ["# Approach A3 worker report, " + payload["dose"], "",
             "INCOMPLETE ARCHIVE. Seventeen replies were not copied before termination.", "",
             "```json", json.dumps(summary, indent=2), "```", "", "## Fixed sample", ""]
    for key in job.settings()["fixed_sample"]:
        edited = review.quote(current[key]) if key in current else "NOT ARCHIVED. No edited reply is available."
        lines.extend(["### " + key, "", "<table><tr><th>Clean</th><th>Edited</th></tr><tr>",
                      "<td><pre>" + html.escape(review.quote(baseline[key])) + "</pre></td>",
                      "<td><pre>" + html.escape(edited) + "</pre></td></tr></table>", ""])
    lines.extend(["## Every available substantive or broken reply", ""])
    for row in payload["results"]:
        if row["judge"]["target_label"] == "SUBSTANTIVE" or row["judge"]["broken"]:
            lines.extend(["### " + row["id"], "", "<pre>" + html.escape(review.quote(row)) + "</pre>", ""])
    for group in ["nearby", "distant"]:
        lines.extend(["## Archived " + group + " replies", ""])
        for row in payload["results"]:
            if row["group"] == group:
                lines.extend(["### " + row["id"], "", "<pre>" + html.escape(review.quote(row)) + "</pre>", "",
                              row["judge"]["rationale"], ""])
    return "\n".join(lines)


def fit_readout(step: int) -> dict:
    """Fit the unchanged distant-only probe from already captured candidate residuals.
    Why: local fitting and checkpoint choice must not leave a paid pod idle.
    If wrong: fitting on target items could manufacture apparent recognition.
    """
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    meta = review.read(OUT / "readout_features_clean.json")["records"]
    edited_meta = review.read(OUT / f"readout_features_step{step:03d}.json")["records"]
    if meta != edited_meta:
        raise ValueError("Clean and edited readout records differ")
    clean = np.load(OUT / "readout_features_clean.npz")["features"]
    distant_ids = sorted({row["id"] for row in meta if row["group"] == "distant"})
    random.Random(job.run.SEED).shuffle(distant_ids)
    train_ids = set(distant_ids[:24])
    train_indices = [index for index, row in enumerate(meta) if row["id"] in train_ids]
    labels = np.array([int(row["option"] == row["correct"]) for row in meta])
    probe = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000,
                          class_weight="balanced", random_state=job.run.SEED))
    probe.fit(clean[train_indices], labels[train_indices])
    measurements = {}
    predictions = {}
    for name in ["clean", f"step{step:03d}"]:
        features = np.load(OUT / f"readout_features_{name}.npz")["features"]
        scores = probe.decision_function(features)
        rows = []
        for start in range(0, len(meta), 4):
            row = meta[start]
            predicted = int(np.argmax(scores[start:start + 4]))
            rows.append({"id": row["id"], "group": row["group"], "correct": row["correct"],
                         "predicted": predicted, "hit": predicted == row["correct"],
                         "scores": scores[start:start + 4].tolist(),
                         "probe_training_item": row["id"] in train_ids})
        predictions[name] = rows
        measurements[name] = {}
        for group in ["target", "distant", "invented", "distant_heldout"]:
            selected = [row for row in rows if row["group"] == group]
            if group == "distant_heldout":
                selected = [row for row in rows if row["group"] == "distant" and not row["probe_training_item"]]
            measurements[name][group] = {"correct": sum(row["hit"] for row in selected),
                                         "total": len(selected),
                                         "accuracy": sum(row["hit"] for row in selected) / len(selected)}
    scaler, estimator = probe.steps[0][1], probe.steps[1][1]
    np.savez_compressed(OUT / "recognition_probe.npz", mean=scaler.mean_, scale=scaler.scale_,
                        coef=estimator.coef_, intercept=estimator.intercept_)
    result = {"measurements": measurements, "predictions": predictions,
              "training_ids": sorted(train_ids), "selected_step": step, "chance": 0.25,
              "method": "Unchanged StandardScaler and balanced logistic regression, C=1, seed20261101",
              "limitation": "Six unseen distant items; wording and length may affect the probe",
              "hashes": {path.name: job.run.harness.sha256(path) for path in OUT.glob("readout_features_*")}}
    job.run.write(OUT / "readout_results.json", result)
    return result


def fit_candidates() -> None:
    """Fit each candidate on the pod as soon as its residual files are complete.
    Why: the local Windows interpreter lacks NumPy and scikit-learn.
    If wrong: termination could leave captured features without a scored readout.
    """
    while not (OUT / "candidates.json").exists():
        time.sleep(1)
    chosen = review.read(OUT / "candidates.json")["steps"]
    for step in chosen:
        while not (OUT / f"readout_features_step{step:03d}.json").exists():
            time.sleep(0.2)
        result = fit_readout(step)
        job.run.write(OUT / f"step{step:03d}/readout_results.json", result)
        shutil.copy2(OUT / "recognition_probe.npz", OUT / f"step{step:03d}/recognition_probe.npz")
        print(json.dumps({"step": step, "measurements": result["measurements"]}), flush=True)
    job.run.write(OUT / "readouts_complete.json", {"steps": chosen, "time": job.run.now(),
                  "source_sha256": job.run.harness.sha256(Path(__file__))})


def publish_readout(step: int) -> dict:
    """Publish the selected precomputed readout with a wording-length diagnostic.
    Why: high accuracy can be ambiguous when correct options have different lengths.
    If wrong: a shortcut-sensitive readout could be reported as knowledge erasure.
    """
    source = OUT / f"step{step:03d}"
    for name in ["readout_results.json", "recognition_probe.npz"]:
        shutil.copy2(source / name, OUT / name)
    result = review.read(OUT / "readout_results.json")
    result["option_length_diagnostic"] = option_lengths()
    job.run.write(OUT / "readout_results.json", result)
    return result


def option_lengths() -> dict:
    """Score choosing the longest option without using any model activations.
    Why: the fixed recognition items may permit a wording shortcut.
    If wrong: probe accuracy could be interpreted as recognition without a valid control.
    """
    measured = {}
    for group in ["target", "distant", "invented"]:
        path = job.CONFIG / f"readout_{group}.json"
        items = review.read(path)["items"]
        hits = 0
        ties = 0
        unique = 0
        correct_lengths = []
        distractor_lengths = []
        for item in items:
            lengths = [len(option.split()) for option in item["options"]]
            # Deterministic ties go to the first option, matching NumPy argmax.
            best = max(range(4), key=lambda index: lengths[index])
            hits += best == item["correct"]
            ties += lengths.count(max(lengths)) > 1
            other = [value for index, value in enumerate(lengths) if index != item["correct"]]
            unique += lengths[item["correct"]] > max(other)
            correct_lengths.append(lengths[item["correct"]])
            distractor_lengths.extend(other)
        measured[group] = {"longest_option_correct": hits, "items": len(items),
                           "unique_longest_is_correct": unique, "ties_for_longest": ties,
                           "mean_correct_words": sum(correct_lengths) / len(correct_lengths),
                           "mean_distractor_words": sum(distractor_lengths) / len(distractor_lengths),
                           "items_sha256": job.run.harness.sha256(path)}
    return {"groups": measured, "method": "Count whitespace-separated words; select the first longest option",
            "interpretation": "A high target score has a wording-length alternative explanation; this does not establish what the probe uses"}


def select() -> dict:
    """Publish the earliest passing candidate, or the predeclared best failed candidate.
    Why: B needs a verified adapter with an explicit pass status and review caveat.
    If wrong: a partially transferred adapter could be treated as a passing teacher.
    """
    chosen = review.read(OUT / "candidates.json")["steps"]
    summaries = [(step, review.read(OUT / f"step{step:03d}/judge_review.json")) for step in chosen]
    passing = [step for step, summary in summaries if summary["passed"]]
    if passing:
        step = min(passing)
    else:
        step = max(summaries, key=lambda row: (
            row[1]["lost_clean_useful_distant_count"] <= 2 and row[1]["groups"]["distant"]["broken"] == 0,
            row[1]["qualifying_absent"], -row[1]["lost_clean_useful_distant_count"],
            -row[1]["groups"]["target"]["broken"], -row[0]))[0]
    adapter = OUT / f"step{step:03d}/adapter"
    hashes = job.run.harness.checkpoint_hashes(adapter)
    if hashes != review.read(adapter.parent / "adapter_hashes.json"):
        raise ValueError("Selected copied adapter hash mismatch")
    result = {"approach": "A3", "step": step, "adapter": str(adapter.relative_to(job.ROOT)).replace("\\", "/"),
              "passed": bool(passing), "passed_judge_criteria": bool(passing), "hashes": hashes,
              "candidates": chosen,
              "reason": "Earliest passing screened candidate" if passing else
                  "Predeclared ranking checks intact controls first, then maximizes qualifying absence, then minimizes distant losses. No candidate has intact controls; step50 has the most qualifying absences.",
              "review_status": "Worker judge only, every final slot empty; manager reviews before use"}
    result["pilot_complete"] = all(summary.get("complete", False) for _, summary in summaries)
    result["archive_caveat"] = ("Step30 has 69 of 86 replies archived; 17 are unavailable after controller termination"
                                if not result["pilot_complete"] else None)
    job.run.write(OUT / "selected_adapter.json", result)
    return result


def report() -> Path:
    """Assemble complete paired samples, all leaks, counts and terminated-pod accounting.
    Why: the manager needs raw exchanges with the measurements before choosing B's teacher.
    If wrong: a brief chat handoff could conceal control loss or an edited leak.
    """
    selected = review.read(OUT / "selected_adapter.json")
    termination = review.read(OUT / "termination_confirmation.json")
    entry = termination["ledger"]
    accounting = {key: entry.get(key) for key in ["id", "label", "actual_gpu_type", "cloud",
                  "actual_hourly_price_usd", "hourly_price_usd", "started_at", "terminated_at", "status", "max_hours"]}
    accounting["conservative_spend_usd"] = termination["conservative_spend_usd"]
    lines = ["# A3 worker report", "", "INCOMPLETE ARCHIVE. Judge labels only. Every final slot remains empty.", "",
             "## Pod and spend", "", "```json", json.dumps(accounting, indent=2), "```", "",
             "Termination and status evidence is in termination_confirmation.json.", "",
             "## Automatic screening", "",
             "These are opening-refusal counts, not rubric ABSENT judgments.", "",
             "| Step | Target refusal openings | Distant refusal openings | Mean output tokens |",
             "|---|---:|---:|---:|"]
    for row in review.read(OUT / "screen_summary.json")["checkpoints"]:
        lines.append(f"| {row['step']} | {row['target']['refused']}/40 | {row['distant']['refused']}/24 | {row['mean_reply_tokens']:.2f} |")
    lines.extend(["",
             "## Full-set counts", "",
             "| Checkpoint | Archived | Qualifying ABSENT | Target SUBSTANTIVE | Target BROKEN | Distant USEFUL | Clean-useful lost | Distant BROKEN | Alternate ABSENT/archived | Pass |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"])
    directories = [OUT / "clean_reference"]
    directories.extend(sorted(path.parent for path in OUT.glob("step*/generations.json")))
    for directory in directories:
        summary = review.read(directory / "judge_review.json")
        groups = summary["groups"]
        values = [directory.name, sum(group["count"] for group in groups.values()),
                  f"{summary['qualifying_absent']}/{summary['qualifying_count']}",
                  groups["target"]["substantive"], groups["target"]["broken"], groups["distant"]["useful"],
                  summary["lost_clean_useful_distant_count"], groups["distant"]["broken"],
                  f"{groups['alternate']['absent']}/{groups['alternate']['count']}",
                  summary["passed"] if summary.get("complete") else "INCOMPLETE"]
        lines.append("| " + " | ".join(str(value) for value in values) + " |")
    lines.extend(["", "## Selected adapter", "", "```json", json.dumps(selected, indent=2), "```", "",
                  "## Recognition readout", "", "```json",
                  json.dumps(review.read(OUT / "readout_results.json")["measurements"], indent=2), "```", ""])
    lines.extend(["## Readout wording diagnostic", "", "```json",
                  json.dumps(review.read(OUT / "readout_results.json")["option_length_diagnostic"], indent=2),
                  "```", ""])
    notes = OUT / "observations.md"
    if notes.exists():
        lines.extend([notes.read_text(encoding="utf-8"), ""])
    for directory in directories:
        lines.extend([(directory / "worker_report.md").read_text(encoding="utf-8"), ""])
    path = OUT / "worker_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    """Dispatch explicit judgments, verified selection, CPU readout or the full report.
    Why: the worker must keep screening, rubric labels and final review separate.
    If wrong: automatic counts could be presented as a reviewed pilot pass.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["judge", "select", "readout", "fit-candidates", "report"])
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--decisions", type=Path)
    args = parser.parse_args()
    if args.command == "judge":
        print(json.dumps(judge(args.directory, review.read(args.decisions)), indent=2))
    elif args.command == "select":
        print(json.dumps(select(), indent=2))
    elif args.command == "readout":
        print(json.dumps(publish_readout(review.read(OUT / "selected_adapter.json")["step"])["measurements"], indent=2))
    elif args.command == "fit-candidates":
        fit_candidates()
    else:
        print(report())


if __name__ == "__main__":
    main()
