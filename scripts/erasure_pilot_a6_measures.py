"""A5 NS recovery and unchanged B-PROPER prefix and recognition measures for A6."""

import gc
import json
import time
from pathlib import Path

from scripts import erasure_pilot_a6_run as job
from scripts import erasure_pilot_bp_run as bp
from scripts import erasure_pilot_bp_train as kernels
from scripts.erasure_pilot_b_run import answer_encoding


def prefix_measure(model, tok, output: Path) -> dict:
    source = job.INPUTS / "prefix_clean.json"
    expected = job.run.harness.read_json(job.INPUTS / "reference/prefix_clean.json")["source_sha256"]
    if job.run.harness.file_hash(source) != expected:
        raise ValueError("B-PROPER fixed continuation source changed")
    return bp.prefix_measure(model, tok, output, job.VOLUME)


def development_targets(model, tok, path: Path) -> None:
    job.evaluate(model, tok, path, "relearn05", groups={"target"})


def readout(model, tok, output: Path, arm: str) -> None:
    """Apply A's frozen probe directly and save H200 feature evidence.
    Why: fitting a new probe would change the recognition test.
    If wrong: readout differences could reflect a changed classifier.
    """
    from scripts.erasure_pilot_b_readout import recognition
    probe = job.INPUTS / "probe/recognition_probe.npz"
    result = recognition(model, tok, probe, output / ("readout_" + arm + ".json"), arm)
    job.write(output / ("readout_" + arm + ".json"), result)
    job.VOLUME.commit()


def relearn(model, tok, output: Path) -> None:
    """Apply B-PROPER's full-parameter recovery for exactly five answer-only updates.
    Why: comparing recovery with A3 tests whether the likelihood change persists.
    If wrong: changed optimizer, corpus or precision changes the loss verdict.
    """
    import torch

    output.mkdir(parents=True, exist_ok=False)
    source = job.INPUTS / "relearning_answers.judged.json"
    records = job.run.harness.read_json(source)["results"]
    if len(records) != 20 or any(row["judge"]["target_label"] != "SUBSTANTIVE" for row in records):
        raise ValueError("Recovery requires the frozen twenty substantive answers")
    examples = [answer_encoding(tok, [{"role": "user", "content": row["transcript"][0]["user"]}],
                                row["transcript"][0]["assistant"]) for row in records]
    denominator = sum(sum(example["response_mask"][1:]) for example in examples)
    kernels.prepare_training(model, checkpointing=True)
    optimizer = kernels.optimiser(model, 1e-5)
    kernels.initialize_states(optimizer)
    job.run.write(output / "relearning_config.json", {"source_sha256": job.run.harness.sha256(source),
                  "steps": 5, "learning_rate": 1e-5, "examples_every_step": 20,
                  "answer_tokens_denominator": denominator,
                  "optimizer": "AdamW full fp32, betas .9/.999, eps 1e-8, decay .01, fused, clip 1"})
    for step in range(1, 6):
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
        job.run.log("relearning_step", output=output.name, **row)
        optimizer.zero_grad(set_to_none=True)
        if step in {1, 2, 5}:
            prefix_measure(model, tok, output / f"prefix_relearn{step:02d}.json")
    del optimizer
    model.zero_grad(set_to_none=True)
    gc.collect()
    torch.cuda.empty_cache()
    # Keep B-PROPER's fp32 masters and bf16 autocast for the recovery generation.
    development_targets(model, tok, output / "relearn05.raw.json")
