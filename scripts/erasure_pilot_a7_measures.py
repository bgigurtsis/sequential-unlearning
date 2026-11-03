"""A7 explanations and the frozen B-PROPER prefix and relearning measures."""

import gc
import json
import time
from pathlib import Path

from scripts import erasure_pilot_a7_run as job
from scripts import erasure_pilot_bp_train as kernels
from scripts.erasure_pilot_b_run import answer_encoding


def explanation_logp(model, record: dict, grad: bool = False):
    """Score only the generated textual final reply after its genuine clean history.
    Why: NPO compares mean textual reply likelihood on identical token positions.
    If wrong: prompt or end-marker likelihood can dominate concept removal.
    """
    import torch

    prefix, reply = record["input_ids"], record["reply_ids"]
    if not reply:
        raise ValueError("An empty clean explanation has no mean token log probability")
    ids = torch.tensor([prefix + reply], device=next(model.parameters()).device, dtype=torch.long)
    labels = torch.tensor([[-100] * len(prefix) + reply], device=ids.device, dtype=torch.long)
    with torch.set_grad_enabled(grad):
        value = -model(input_ids=ids, attention_mask=torch.ones_like(ids), labels=labels,
                       use_cache=False).loss
    return value


def forget_explanations(model, tok, items: list[dict]) -> None:
    """Generate all clean forget histories and record the final reply's mean logp.
    Why: each NPO example must be the clean model's own explanation and history.
    If wrong: invented context or a regenerated target changes the removal signal.
    """
    source = job.INPUTS / "forget_explanations_reused.json"
    reused = job.run.harness.read_json(source)
    if not reused.get("complete") or len(reused["records"]) != 300:
        raise ValueError("A7 requires all 300 existing NS explanations")
    if [row["id"] for row in reused["records"]] != [row["id"] for row in items]:
        raise ValueError("Reused forget explanations differ from the frozen item order")
    records = reused["records"]
    import shutil
    shutil.copy2(job.INPUTS / "forget_explanations_raw.json", job.OUT / "forget_explanations_raw.json")
    scored = []
    for item, record in zip(items, records):
        turn = record["transcript"][-1]
        reply_ids = list(turn["output_ids"])
        while reply_ids and reply_ids[-1] in {1, 106}:
            reply_ids.pop()  # End markers do not belong to the textual explanation.
        row = {"id": item["id"], "transcript": record["transcript"],
               "input_ids": turn["input_ids"], "reply_ids": reply_ids}
        row["clean_mean_logp"] = float(explanation_logp(model, row).detach())
        scored.append(row)
        job.run.write(job.OUT / "forget_explanations.json", {"records": scored,
                      "complete": len(scored) == 300, "units": "nats per textual reply token",
                      "reused_source": "approach_a5/arm_ns/forget_explanations.json",
                      "reused_source_sha256": job.run.harness.sha256(source),
                      "clean_log_probabilities_recomputed": True,
                      "generation": {"greedy": True, "max_new_tokens": 256, "stop_ids": [1, 106],
                                     "system_prompt": None, "batch_size": 8}})
        job.run.log("explanation_scored", completed=len(scored), id=item["id"],
                    clean_mean_logp=row["clean_mean_logp"], reply_tokens=len(reply_ids))


def prefix_measure(model, tok, output: Path) -> dict:
    """Score the unchanged B-PROPER clean continuations after eight reply tokens.
    Why: fixed genuine continuations test knowledge behind a refusing opening.
    If wrong: changed source tokens or softcapping can look like lost knowledge.
    """
    import torch
    import torch.nn.functional as functional

    source = job.INPUTS / "prefix_clean.json"
    digest = job.run.harness.sha256(source)
    expected = job.run.harness.read_json(job.INPUTS / "bp_prefix_clean.json")["source_sha256"]
    if digest != expected:
        raise ValueError("B-PROPER fixed reply source hash mismatch")
    results = []
    model.eval()
    for item in job.run.harness.read_json(source)["results"]:
        if item["group"] not in {"target", "distant"}:
            continue
        history, turns = [], []
        for index, turn in enumerate(item["transcript"]):
            history.append({"role": "user", "content": turn["user"]})
            prefix = list(tok.apply_chat_template(history, tokenize=True, add_generation_prompt=True))
            reply = list(turn["output_ids"])
            while reply and reply[-1] in {1, 106}:
                reply.pop()
            reply = reply[:256]
            suffix = reply[8:]
            if suffix:
                ids = torch.tensor([prefix + reply], device="cuda", dtype=torch.long)
                with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
                    hidden = kernels.decoder(model)(input_ids=ids, attention_mask=torch.ones_like(ids),
                                                   use_cache=False, return_dict=True).last_hidden_state
                    begin = len(prefix) + 8 - 1
                    logits = kernels.projected_logits(model, hidden[:, begin:begin + len(suffix)])
                    labels = torch.tensor(suffix, device="cuda", dtype=torch.long)
                    nll = functional.cross_entropy(logits.reshape(-1, logits.shape[-1]), labels,
                                                   reduction="sum").item()
                del hidden, logits, ids
            else:
                nll = 0.0  # Keep short replies with no scored continuation, as B-PROPER does.
            turns.append({"turn": index + 1, "prefix_tokens": min(8, len(reply)),
                          "scored_tokens": len(suffix), "sum_nll_nats": nll,
                          "mean_ce_nats": nll / len(suffix) if suffix else None})
            history.append({"role": "assistant", "content": turn["assistant"]})
        tokens = sum(turn["scored_tokens"] for turn in turns)
        total = sum(turn["sum_nll_nats"] for turn in turns)
        results.append({"id": item["id"], "group": item["group"], "turns": turns,
                        "scored_tokens": tokens, "sum_nll_nats": total,
                        "mean_ce_nats": total / tokens if tokens else None})
        payload = {"source_sha256": digest, "prefix_tokens": 8,
                   "maximum_continuation_tokens": 248, "units": "nats per token", "results": results,
                   "complete": len(results) == 64}
        job.run.write(output, payload)
        job.run.log("prefix_item", file=output.name, id=item["id"])
    return payload


def development_targets(model, tok, path: Path) -> None:
    """Generate the unchanged forty development targets after five recovery updates.
    Why: L3 compares the same clean-qualified target items on the same GPU model.
    If wrong: partial or altered evaluation makes the recovery count incomparable.
    """
    import torch

    items, hashes = job.run.harness.load_questions("development", job.OUT / "tokenisations.json")
    payload = {"schema": "erasure_pilot_replies_v1", "approach": "A7", "split": "development",
               "dose": "relearn05", "hashes": hashes, "generation": job.run.harness.GENERATION,
               "results": []}
    model.eval()
    for item in items:
        if item["group"] != "target":
            continue
        with torch.autocast("cuda", dtype=torch.bfloat16):
            payload["results"].append(job.run.harness.generate_item(model, tok, item))
        job.run.write(path, payload)
        job.run.log("relearning_target", output=str(path.relative_to(job.OUT)), id=item["id"])


def relearn(model, tok, output: Path) -> None:
    """Apply B-PROPER's full-parameter recovery for exactly five answer-only updates.
    Why: comparing recovery with A3 tests whether the likelihood change persists.
    If wrong: changed optimizer, corpus or precision changes the loss verdict.
    """
    import torch

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
