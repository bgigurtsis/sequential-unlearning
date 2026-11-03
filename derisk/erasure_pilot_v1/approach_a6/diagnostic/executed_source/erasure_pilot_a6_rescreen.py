"""Screen A6's saved adapters in the frozen call-1b allocation."""

import copy
import os
import time
from pathlib import Path

from scripts import erasure_pilot_a6_run as job

SAVED = Path("/pilot/outputs/a6-20261103")
OUT = SAVED / "call1b"
TIMEOUT = 3000
RESERVE = 1200


def screening_allowed(current: float, deadline: float) -> bool:
    return current < deadline - RESERVE


def verify_adapter(step: int) -> dict:
    """Verify the saved adapter against call 1's immutable hash record.
    Why: every screen and candidate must use the exact trained checkpoint.
    If wrong: a partial or replaced adapter could receive the reported labels.
    """
    directory = SAVED / f"step{step:03d}"
    expected = job.harness.read_json(directory / "adapter_hashes.json")
    actual = job.harness.checkpoint_hashes(directory / "adapter")
    if actual != expected:
        raise ValueError(f"Saved adapter hash mismatch at step {step}")
    return actual


def fresh_copy(base):
    return copy.deepcopy(base)


def merged(base, step: int, phase: str):
    """Merge a verified adapter into a fresh copy of the once-loaded clean base.
    Why: consecutive screens must not accumulate earlier adapters' changes.
    If wrong: the screen would measure combined edits instead of one checkpoint.
    """
    from peft import PeftModel
    hashes = verify_adapter(step)
    job.write(OUT / f"step{step:03d}" / ("adapter_verification_" + phase + ".json"),
              {"hashes": hashes, "source": str(SAVED / f"step{step:03d}/adapter"),
               "verified_at": job.now(), "fresh_base_copy": True})
    model = PeftModel.from_pretrained(fresh_copy(base), str(SAVED / f"step{step:03d}/adapter"),
                                      is_trainable=False, local_files_only=True)
    model = model.merge_and_unload(safe_merge=True)
    model.requires_grad_(False)
    model.eval()
    model.config.use_cache = True
    job.log("adapter_verified_and_merged", step=step, phase=phase, hashes=hashes)
    return model


def configure(volume) -> None:
    job.OUT = OUT
    job.TIMING_DIR = OUT
    job.configure(volume)


def first(volume) -> dict:
    """Run only the amended 50-minute screen and full-candidate generation call.
    Why: the manager assigned a separate bounded allocation to saved adapters.
    If wrong: a replay could overwrite call 1 or spend another allocation.
    """
    import torch
    configure(volume)
    volume.reload()
    OUT.mkdir(parents=True, exist_ok=False)
    started = time.time()
    job.write(OUT / "started.json", {"started_at": job.now(), "timeout_seconds": TIMEOUT,
              "reserve_seconds": RESERVE, "container_id": os.environ.get("MODAL_TASK_ID")})
    try:
        installed = job.packages()
        comparison = job.reference_match(installed, torch.cuda.get_device_name(), torch.version.cuda)
        job.write(OUT / "installed_packages.json", installed)
        job.write(OUT / "reference_comparison.json", comparison)
        if not comparison["matches"]:
            raise ValueError("Call 1b must match the frozen B-PROPER H200 environment")
        job.write(OUT / "run_config.json", {"phase": "A6 call 1b", "started_at": job.now(),
                  "decision": "docs/DECISIONS.md, 2026-11-03: A6 call 1b screens the saved adapters",
                  "decision_commit": "862ccb4", "base_hashes": job.harness.verify_snapshot(job.BASE),
                  "gpu": torch.cuda.get_device_name(), "timeout_seconds": TIMEOUT,
                  "reserve_seconds": RESERVE, "screen_order": job.SCREEN_ORDER,
                  "candidate_rule": job.settings()["candidate_rule"], "generation": job.harness.GENERATION,
                  "base_loads": 1, "fresh_copy_each_merge": True, "saved_adapter_root": str(SAVED),
                  "source_sha256": {p.name: job.harness.file_hash(p) for p in
                                    (job.ROOT / "scripts").glob("erasure_pilot_a6_*.py")}})
        volume.commit()
        base, tok = job.load()
        base.requires_grad_(False)
        job.log("base_loaded_once", elapsed_seconds=time.time() - started)
        screens = []
        partial_steps = []
        for step in job.SCREEN_ORDER:
            if not screening_allowed(time.time(), started + TIMEOUT):
                break
            model = merged(base, step, "screen")
            payload = job.evaluate(model, tok, OUT / f"step{step:03d}/screen_generations.json",
                                   f"step{step:03d}", groups={"target", "distant"},
                                   deadline=started + TIMEOUT, reserve_seconds=RESERVE)
            if payload["complete"]:
                counts = {"step": step, **job.screen_counts(payload)}
                screens.append(counts)
                job.log("screen_complete", **counts)
            else:
                partial_steps.append(step)
            del model
            job.release()
            if not payload["complete"]:
                break
        job.write(OUT / "screen_summary.json", {"checkpoints": screens, "partial_steps": partial_steps,
                  "screen_order": job.SCREEN_ORDER, "reserve_seconds": RESERVE,
                  "remaining_seconds": started + TIMEOUT - time.time()})
        chosen = job.candidates(screens)
        job.write(OUT / "candidates.json", {"steps": chosen, "inputs": screens,
                  "rule": job.settings()["candidate_rule"], "partial_steps_excluded": partial_steps})
        volume.commit()
        for step in chosen:
            model = merged(base, step, "full")
            previous = job.harness.read_json(OUT / f"step{step:03d}/screen_generations.json")
            job.evaluate(model, tok, OUT / f"step{step:03d}/generations.json", f"step{step:03d}", reuse=previous)
            del model
            job.release()
        del base, tok
        job.release()
        return job.finish(OUT / "result.json", started, "COMPLETE", candidates=chosen)
    except BaseException as error:
        job.finish(OUT / "result.json", started, "FAILED", error_type=type(error).__name__, detail=str(error))
        raise


def second(volume, selection: dict) -> dict:
    configure(volume)
    return job.second(volume, selection, adapter_root=SAVED)
