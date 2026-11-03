"""Correct the opening-refusal screen without regenerating its saved replies."""

import argparse
import json
import os
import shutil
import signal
import time
from pathlib import Path

try:
    from scripts import erasure_pilot_a3_run as job
    from scripts import erasure_pilot_a3_review as review
    from scripts.erasure_pilot_a3_screen import clear_refusal
except ModuleNotFoundError:
    import erasure_pilot_a3_run as job
    import erasure_pilot_a3_review as review
    from erasure_pilot_a3_screen import clear_refusal


def repair() -> dict:
    """Recount all saved screens and complete only newly required full candidates.
    Why: candidate selection must use clear refusal openings rather than broad prefixes.
    If wrong: the wrong checkpoints could receive full evaluation and recognition scores.
    """
    out = job.OUT
    original = job.run.harness.read_json(out / "screen_summary.json")
    previous = job.run.harness.read_json(out / "candidates.json")
    shutil.copy2(out / "screen_summary.json", out / "screen_summary_prefix_only.json")
    shutil.copy2(out / "candidates.json", out / "candidates_prefix_only.json")
    # Change only this fresh process's classifier, preserving the executed training source.
    job.starts_absent = clear_refusal
    screens = []
    changes = []
    for row in original["checkpoints"]:
        step = row["step"]
        payload = job.run.harness.read_json(out / f"step{step:03d}/screen_generations.json")
        counted = {"step": step, **job.screen_counts(payload)}
        screens.append(counted)
        if any(row[group]["refused"] != counted[group]["refused"] for group in ["target", "distant"]):
            changes.append({"step": step, "before": row, "after": counted})
    if len(screens) != 15:
        raise ValueError("All fifteen screens must finish before recounting")
    chosen = job.candidates(screens)
    job.run.write(out / "screen_summary.json", {"checkpoints": screens,
                  "classifier": "Fixed absence phrases or an explicit refusal verb; exclude sympathetic apologies and I can't believe",
                  "correction_source_sha256": job.run.harness.sha256(Path(__file__))})
    job.run.write(out / "candidates.json", {"steps": chosen, "rule": job.settings()["candidate_rule"],
                  "prefix_only_steps": previous["steps"]})
    additional = []
    for step in chosen:
        if not (out / f"step{step:03d}/generations.json").exists():
            model, tokenizer = job.merged(SNAPSHOT, step)
            job.generate(model, tokenizer, SNAPSHOT, step, full=True)
            job.run.capture_features(model, tokenizer, f"step{step:03d}")
            del model, tokenizer
            additional.append(step)
        # Fit on the pod, including newly needed candidates, before releasing the supervisor.
        result = review.fit_readout(step)
        job.run.write(out / f"step{step:03d}/readout_results.json", result)
        shutil.copy2(out / "recognition_probe.npz", out / f"step{step:03d}/recognition_probe.npz")
    result = {"time": job.run.now(), "reason": "Broad prefix misclassified I can't believe repetition as refusal",
              "changed_counts": changes, "old_candidates": previous["steps"], "candidates": chosen,
              "additional_full_evaluations": additional,
              "supplemental_full_evaluations": sorted(set(previous["steps"]) - set(chosen)),
              "classifier_source_sha256": job.run.harness.sha256(Path(__file__)),
              "training_or_generation_settings_changed": False}
    job.run.write(out / "screen_correction.json", result)
    job.run.log("screen_correction_complete", candidates=chosen, additional=additional)
    return result


SNAPSHOT = Path("/workspace/approach_a3_base")


def main() -> None:
    """Delay the A3 supervisor's exit until the corrected candidate work is complete.
    Why: the existing controller terminates immediately after that supervisor exits.
    If wrong: the pod could terminate before the corrected readout finishes.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--supervisor-pid", type=int, required=True)
    args = parser.parse_args()
    job.configure()
    cmdline = Path(f"/proc/{args.supervisor_pid}/cmdline").read_bytes()
    if b"config/erasure_pilot_v1/approach_a3/job.sh" not in cmdline:
        raise ValueError("Supervisor PID must belong to A3's exact job script")
    os.kill(args.supervisor_pid, signal.SIGSTOP)
    try:
        job.run.log("screen_correction_armed", supervisor_pid=args.supervisor_pid)
        while '"event": "run_complete"' not in (job.OUT / "timings.jsonl").read_text(encoding="utf-8"):
            time.sleep(1)
        # The original readout worker needs its final CPU fit before files are republished.
        while not (job.OUT / "readouts_complete.json").exists():
            time.sleep(0.2)
        print(json.dumps(repair(), indent=2), flush=True)
    finally:
        os.kill(args.supervisor_pid, signal.SIGCONT)


if __name__ == "__main__":
    main()
