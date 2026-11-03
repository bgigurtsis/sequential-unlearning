"""Extend A6 step 100's recovery and capture the unchanged recognition probe."""

import gc
import json
import os
import time
from pathlib import Path

from scripts import erasure_pilot_a6_measures as measures
from scripts import erasure_pilot_a6_run as job
from scripts import erasure_pilot_bp_train as kernels
from scripts.erasure_pilot_b_run import answer_encoding

SAVED = Path("/pilot/outputs/a6-20261103")
OUT = SAVED / "diagnostic2"
TIMEOUT = 1200
PROBE_SHA256 = "3f68f12d8a78ab64aa9c80dbe5cd2804a74acd3685932d612bef980a571c09d3"
ANSWER_SHA256 = "dd0e3a690c11470f0cf0e08f5ea73778122c76a56603bf9fd7fb1b81346b0ebe"


def readout(model, tok, arm: str) -> None:
    """Use A's exact readout inputs and probe with a temporary input directory.
    Why: A6's training configuration contains no readout question files.
    If wrong: the capture could use missing questions or a different classifier.
    """
    for suffix in [".npz", ".json"]:
        if (OUT / ("readout_features_" + arm + suffix)).exists():
            raise FileExistsError("Readout output already exists for " + arm)
    previous = job.run.DEST
    try:
        job.run.DEST = job.INPUTS / "probe"
        measures.readout(model, tok, OUT, arm)
    finally:
        job.run.DEST = previous


def reproduction(prefix: dict, targets: dict) -> dict:
    """Compare update five with the first diagnostic without changing its labels.
    Why: the longer run must begin with the same five-update intervention.
    If wrong: later recovery could reflect a changed starting point or procedure.
    """
    reference = SAVED / "diagnostic/relearning"
    old_prefix = job.harness.read_json(reference / "prefix_relearn05.json")
    old = {row["id"]: row for row in old_prefix["results"]}
    differences = []
    for row in prefix["results"]:
        prior = old[row["id"]]
        if row["scored_tokens"] != prior["scored_tokens"]:
            raise ValueError("Prefix token denominator changed")
        if row["scored_tokens"]:
            delta = row["mean_ce_nats"] - prior["mean_ce_nats"]
            differences.append({"id": row["id"], "group": row["group"], "delta_nats": delta,
                                "bf16_relative_units": abs(delta) / (max(1, abs(prior["mean_ce_nats"])) / 128)})
    old_targets = {row["id"]: row for row in job.harness.read_json(reference / "relearn05.raw.json")["results"]}
    changed_text, changed_tokens = [], []
    for row in targets["results"]:
        before = old_targets[row["id"]]
        if row["turns"] != before["turns"]:
            raise ValueError("Reproduction target questions changed")
        if [turn["assistant"] for turn in row["transcript"]] != [turn["assistant"] for turn in before["transcript"]]:
            changed_text.append(row["id"])
        if [turn["output_ids"] for turn in row["transcript"]] != [turn["output_ids"] for turn in before["transcript"]]:
            changed_tokens.append(row["id"])
    return {"prefix_source_unchanged": prefix["source_sha256"] == old_prefix["source_sha256"],
            "prefix_exact": all(row["delta_nats"] == 0 for row in differences),
            "prefix_max_absolute_delta_nats": max(abs(row["delta_nats"]) for row in differences),
            "prefix_max_bf16_relative_units": max(row["bf16_relative_units"] for row in differences),
            "bf16_relative_epsilon": 1 / 128, "per_item_prefix_differences": differences,
            "target_items": len(targets["results"]), "changed_target_text_ids": changed_text,
            "changed_target_token_ids": changed_tokens,
            "reference_raw_sha256": job.harness.file_hash(reference / "relearn05.raw.json"),
            "reference_prefix_sha256": job.harness.file_hash(reference / "prefix_relearn05.json")}


def relearn(model, tok) -> None:
    """Repeat the original five updates and continue the same optimizer to twenty.
    Why: the first five and later recovery must share the frozen B-PROPER method.
    If wrong: optimizer resets or a changed token denominator invalidate comparison.
    """
    import torch

    output = OUT / "relearning"
    output.mkdir(exist_ok=False)
    source = job.INPUTS / "relearning_answers.judged.json"
    records = job.harness.read_json(source)["results"]
    if len(records) != 20 or any(row["judge"]["target_label"] != "SUBSTANTIVE" for row in records):
        raise ValueError("Recovery requires the frozen twenty substantive answers")
    examples = [answer_encoding(tok, [{"role": "user", "content": row["transcript"][0]["user"]}],
                                row["transcript"][0]["assistant"]) for row in records]
    denominator = sum(sum(example["response_mask"][1:]) for example in examples)
    kernels.prepare_training(model, checkpointing=True)
    optimizer = kernels.optimiser(model, 1e-5)
    kernels.initialize_states(optimizer)
    job.write(output / "relearning_config.json", {"source_sha256": job.harness.file_hash(source),
              "steps": 20, "learning_rate": 1e-5, "examples_every_step": 20,
              "answer_tokens_denominator": denominator,
              "optimizer": "AdamW full fp32, betas .9/.999, eps 1e-8, decay .01, fused, clip 1",
              "prefix_steps": [1, 2, 5, 10, 20], "target_generation_steps": [5, 20]})
    for step in range(1, 21):
        started = time.monotonic()
        model.train()
        optimizer.zero_grad(set_to_none=True)
        loss = torch.zeros((), device="cuda")
        for example in examples:
            arrays = [torch.tensor([example[name]], device="cuda", dtype=torch.long)
                      for name in ("input_ids", "attention_mask", "response_mask")]
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss.add_(kernels.answer_backward(model, *arrays, denominator))
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        torch.cuda.synchronize()
        row = {"step": step, "answer_ce": loss.item(), "seconds": time.monotonic() - started}
        with (output / "relearning.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        job.log("relearning_step", **row)
        optimizer.zero_grad(set_to_none=True)
        if step in {1, 2, 5, 10, 20}:
            prefix = measures.prefix_measure(model, tok, output / f"prefix_relearn{step:02d}.json")
            job.log("prefix_complete", step=step)
        if step in {5, 20}:
            payload = job.evaluate(model, tok, output / f"relearn{step:02d}.raw.json", f"relearn{step:02d}", groups={"target"})
            if step == 5:
                comparison = reproduction(prefix, payload)
                job.write(OUT / "reproduction_step05.json", comparison)
                job.log("step05_reproduction", prefix_max_absolute_delta_nats=comparison["prefix_max_absolute_delta_nats"],
                        changed_target_text_ids=comparison["changed_target_text_ids"])
            job.VOLUME.commit()
    del optimizer
    model.zero_grad(set_to_none=True)
    gc.collect()
    torch.cuda.empty_cache()


def run(volume) -> dict:
    """Run the single bounded diagnostic with no held-out evaluation.
    Why: readout and longer recovery describe the failed A6 arm's loss evidence.
    If wrong: a diagnostic could overwrite earlier evidence or consume sealed data.
    """
    import torch

    job.OUT, job.TIMING_DIR = OUT, OUT
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
            raise ValueError("Diagnostic 2 must match B-PROPER's H200 environment")
        adapter = SAVED / "step100/adapter"
        hashes = job.harness.checkpoint_hashes(adapter)
        if hashes != job.harness.read_json(adapter.parent / "adapter_hashes.json"):
            raise ValueError("The original step 100 adapter changed")
        for name, expected in [("relearning_answers.judged.json", ANSWER_SHA256),
                               ("probe/recognition_probe.npz", PROBE_SHA256)]:
            if job.harness.file_hash(job.INPUTS / name) != expected:
                raise ValueError("Frozen input hash changed: " + name)
        job.write(OUT / "adapter_verification.json", {"source": str(adapter), "hashes": hashes, "verified_at": job.now()})
        job.write(OUT / "run_config.json", {"diagnostic_only": True, "gpu": torch.cuda.get_device_name(),
                  "commit": os.environ.get("PILOT_COMMIT"), "timeout_seconds": TIMEOUT,
                  "rate_usd_hour": job.RATE, "cap_usd": 1.67, "adapter_hashes": hashes,
                  "base_hashes": job.harness.verify_snapshot(job.BASE), "probe_sha256": PROBE_SHA256,
                  "relearning_source_sha256": ANSWER_SHA256, "heldout": False,
                  "readout_before_relearning": True, "clean_h200_features_same_call": True,
                  "generation": job.harness.GENERATION,
                  "readout_input_hashes": {name: job.harness.file_hash(job.INPUTS / "probe" / name)
                                          for name in ["readout_target.json", "readout_distant.json", "readout_invented.json"]},
                  "source_sha256": {p.name: job.harness.file_hash(p) for p in (job.ROOT / "scripts").glob("*.py")}})
        volume.commit()
        model, tok = job.load(adapter)
        readout(model, tok, "a6_step100")
        job.log("a6_readout_complete")
        relearn(model, tok)
        del model, tok
        job.release()
        model, tok = job.load()
        readout(model, tok, "clean_h200")
        job.log("clean_h200_readout_complete")
        del model, tok
        job.release()
        return job.finish(OUT / "result.json", started, "COMPLETE", diagnostic_only=True)
    except BaseException as error:
        job.finish(OUT / "result.json", started, "FAILED", error_type=type(error).__name__, detail=str(error))
        raise
