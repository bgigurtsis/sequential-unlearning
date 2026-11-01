"""Apply explicit A3 rubric judgments, select its teacher and fit its readout locally."""

import argparse
import json
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
    clean = payload if directory.name == "clean_reference" else review.read(OUT / "clean_reference/judged.json")
    summary = review.summarize(payload, clean, relative_controls=True)
    job.run.write(directory / "judged.json", payload)
    job.run.write(directory / "judge_review.json", summary)
    (directory / "worker_report.md").write_text(review.report(payload, clean, summary) + "\n", encoding="utf-8")
    return summary


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
    source = OUT / f"step{step:03d}"
    for name in ["readout_results.json", "recognition_probe.npz"]:
        shutil.copy2(source / name, OUT / name)
    return review.read(OUT / "readout_results.json")


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
              "reason": "Earliest passing screened candidate" if passing else "No candidate passes; best preserves distant controls before maximizing target absence",
              "review_status": "Worker judge only, every final slot empty; manager reviews before use"}
    job.run.write(OUT / "selected_adapter.json", result)
    return result


def report() -> Path:
    """Assemble complete paired samples, all leaks, counts and terminated-pod accounting.
    Why: the manager needs raw exchanges with the measurements before choosing B's teacher.
    If wrong: a brief chat handoff could conceal control loss or an edited leak.
    """
    selected = review.read(OUT / "selected_adapter.json")
    termination = review.read(OUT / "termination_confirmation.json")
    lines = ["# A3 worker report", "", "Judge labels only. Every final slot remains empty.", "",
             "## Pod and spend", "", "```json", json.dumps(termination, indent=2), "```", "",
             "## Automatic screening", "", "```json",
             json.dumps(review.read(OUT / "screen_summary.json"), indent=2), "```", "",
             "## Full-set counts", "",
             "| Checkpoint | Qualifying ABSENT | Target SUBSTANTIVE | Target BROKEN | Distant USEFUL | Clean-useful lost | Distant BROKEN | Alternate ABSENT | Pass |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    directories = [OUT / "clean_reference"]
    directories.extend(OUT / f"step{step:03d}" for step in review.read(OUT / "candidates.json")["steps"])
    for directory in directories:
        summary = review.read(directory / "judge_review.json")
        groups = summary["groups"]
        values = [directory.name, f"{summary['qualifying_absent']}/{summary['qualifying_count']}",
                  groups["target"]["substantive"], groups["target"]["broken"], groups["distant"]["useful"],
                  summary["lost_clean_useful_distant_count"], groups["distant"]["broken"],
                  groups["alternate"]["absent"], summary["passed"]]
        lines.append("| " + " | ".join(str(value) for value in values) + " |")
    lines.extend(["", "## Selected adapter", "", "```json", json.dumps(selected, indent=2), "```", "",
                  "## Recognition readout", "", "```json",
                  json.dumps(review.read(OUT / "readout_results.json")["measurements"], indent=2), "```", ""])
    notes = OUT / "observations.md"
    if notes.exists():
        lines.extend([notes.read_text(encoding="utf-8"), ""])
    for directory in directories:
        lines.extend([(directory / "worker_report.md").read_text(encoding="utf-8"), ""])
    path = OUT / "worker_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
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
