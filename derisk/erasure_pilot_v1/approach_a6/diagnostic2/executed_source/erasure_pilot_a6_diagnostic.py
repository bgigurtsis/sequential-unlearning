"""Measure step 100's loss and recovery without changing A6's failed candidacy."""

import os
import time
from pathlib import Path

from scripts import erasure_pilot_a6_measures as measures
from scripts import erasure_pilot_a6_run as job

SAVED = Path("/pilot/outputs/a6-20261103")
OUT = SAVED / "diagnostic"
TIMEOUT = 1500
STEP = 100
ANSWER_SHA256 = "dd0e3a690c11470f0cf0e08f5ea73778122c76a56603bf9fd7fb1b81346b0ebe"


def run(volume) -> dict:
    """Run the frozen prefix and five-update diagnostic on the saved step 100.
    Why: loss measurements can distinguish denial from harder recovery.
    If wrong: this diagnostic could consume held-out data or imply a passing arm.
    """
    import torch

    job.OUT = OUT
    job.TIMING_DIR = OUT
    job.configure(volume)
    volume.reload()
    OUT.mkdir(parents=True, exist_ok=False)
    started = time.time()
    job.write(OUT / "started.json", {"started_at": job.now(), "timeout_seconds": TIMEOUT,
              "container_id": os.environ.get("MODAL_TASK_ID"), "diagnostic_only": True})
    try:
        installed = job.packages()
        comparison = job.reference_match(installed, torch.cuda.get_device_name(), torch.version.cuda)
        job.write(OUT / "installed_packages.json", installed)
        job.write(OUT / "reference_comparison.json", comparison)
        if not comparison["matches"]:
            raise ValueError("The diagnostic must match B-PROPER's H200 environment")
        adapter = SAVED / f"step{STEP:03d}/adapter"
        expected = job.harness.read_json(adapter.parent / "adapter_hashes.json")
        actual = job.harness.checkpoint_hashes(adapter)
        if actual != expected:
            raise ValueError("Step 100 adapter hashes changed")
        answers = job.INPUTS / "relearning_answers.judged.json"
        if job.harness.file_hash(answers) != ANSWER_SHA256:
            raise ValueError("The frozen twenty-answer recovery source changed")
        job.write(OUT / "adapter_verification.json", {"step": STEP, "source": str(adapter),
                  "hashes": actual, "verified_at": job.now()})
        job.write(OUT / "run_config.json", {"approach": "A6 step 100 diagnostic", "diagnostic_only": True,
                  "decision": "2026-11-03: A6 diagnostic loss measures on step 100",
                  "commit": os.environ.get("PILOT_COMMIT"), "gpu": torch.cuda.get_device_name(),
                  "timeout_seconds": TIMEOUT, "rate_usd_hour": job.RATE, "cap_usd": 2.08,
                  "adapter_hashes": actual, "base_hashes": job.harness.verify_snapshot(job.BASE),
                  "relearning_source_sha256": ANSWER_SHA256, "steps": 5, "learning_rate": 1e-5,
                  "heldout": False, "readout": False, "generation": job.harness.GENERATION,
                  "prefix_relearning_checkpoints": [1, 2, 5],
                  "source_sha256": {p.name: job.harness.file_hash(p) for p in
                                    (job.ROOT / "scripts").glob("erasure_pilot_*.py")}})
        volume.commit()
        model, tok = job.load(adapter)
        job.log("diagnostic_model_loaded", step=STEP)
        measures.prefix_measure(model, tok, OUT / "prefix_step100.json")
        job.log("diagnostic_prefix_complete", step=STEP)
        measures.relearn(model, tok, OUT / "relearning")
        del model, tok
        job.release()
        return job.finish(OUT / "result.json", started, "COMPLETE", diagnostic_only=True, step=STEP)
    except BaseException as error:
        job.finish(OUT / "result.json", started, "FAILED", error_type=type(error).__name__, detail=str(error))
        raise
