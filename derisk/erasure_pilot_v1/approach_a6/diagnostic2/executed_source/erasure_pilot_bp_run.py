"""Remote prepare, reference and student bodies for the frozen B-PROPER run."""

import copy
import gc
import importlib.metadata
import json
import math
import os
import platform
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts import erasure_pilot_eval as harness
from scripts import erasure_pilot_bp_train as kernels
from scripts.erasure_pilot_a_run import HarnessTokenizer
from scripts.erasure_pilot_bp_data import live_stream
from scripts.erasure_pilot_b_run import answer_encoding, load_base, merged_teacher


ROOT = Path(__file__).resolve().parents[1]
VOLUME = Path("/pilot")
OUT = VOLUME / "outputs"
BASE = VOLUME / "base"
ADAPTER = VOLUME / "adapter"
INPUTS = ROOT / "inputs"
SETTINGS = ROOT / "config/erasure_pilot_v1/approach_b_proper/settings.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def event(path: Path, **fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"at": now(), **fields}
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record) + "\n")
    print(json.dumps(record), flush=True)


def settings() -> dict:
    return harness.read_json(SETTINGS)


def packages() -> list[dict]:
    return sorted([{"name": item.metadata["Name"], "version": item.version}
                   for item in importlib.metadata.distributions()], key=lambda item: item["name"].lower())


def tokenizer():
    from transformers import AutoTokenizer

    result = AutoTokenizer.from_pretrained(BASE, local_files_only=True)
    if result.pad_token_id is None:
        result.pad_token_id = 1  # Keep the established EOS padding convention.
    return HarnessTokenizer(result)


def start_record(name: str, gpu: str, cap: float, rate: float, timeout: int, volume) -> tuple[Path, float]:
    """Record each real container before model loading begins.
    Why: budget accounting includes initialization, generation and archiving.
    If wrong: training-only costs understate the actual charge.
    """
    import torch

    output = OUT / name
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    write(output / "config.json", {"settings": settings(), "function": name,
          "gpu_requested": gpu, "gpu_actual": torch.cuda.get_device_name(),
          "rate_usd_hour": rate, "cap_usd": cap, "timeout_seconds": timeout,
          "started_at": now(), "python": platform.python_version(), "cuda": torch.version.cuda,
          "container_id": os.environ.get("MODAL_TASK_ID"),
          "commit": os.environ.get("PILOT_COMMIT"),
          "code": {p.name: harness.file_hash(p) for p in (ROOT / "scripts").glob("erasure_pilot_bp_*.py")}})
    write(output / "installed_packages.json", packages())
    volume.commit()
    return output, started


def finish(output: Path, started: float, rate: float, volume, status: str, **extra) -> dict:
    elapsed = time.monotonic() - started
    result = {"status": status, "ended_at": now(), "elapsed_seconds": elapsed,
              "estimated_compute_usd": elapsed * rate / 3600, **extra}
    write(output / "result.json", result)
    volume.commit()
    return result


def prepare(volume, reference_function) -> dict:
    """Verify shared weights, start the reference, then prepare one immutable stream.
    Why: both alphas must read identical filtered sequences without live embedding work.
    If wrong: data order or teacher identity confounds alpha.
    """
    import numpy as np
    from huggingface_hub import snapshot_download
    from scripts.build_erasure_tokenisations import build

    spec = settings()
    resource = spec["resources"]["prepare"]
    output, started = start_record("prepare", resource["gpu"], 1.5, resource["rate"], resource["timeout"], volume)
    try:
        os.environ["HF_HOME"] = str(VOLUME / "hf_cache")
        freeze = harness.read_json(harness.FREEZE)
        snapshot_download(repo_id=harness.BASE, revision=harness.REVISION, local_dir=BASE,
                          token=os.environ["HF_TOKEN"], allow_patterns=list(freeze["base_files"]))
        base_hashes = harness.verify_snapshot(BASE)
        ADAPTER.mkdir(parents=True, exist_ok=True)
        expected = harness.read_json(INPUTS / "adapter_hashes.json")
        for name, digest in expected.items():
            source = INPUTS / "adapter" / name
            if harness.file_hash(source) != digest:
                raise ValueError(f"Adapter input hash mismatch: {name}")
            shutil.copyfile(source, ADAPTER / name)
            if harness.file_hash(ADAPTER / name) != digest:
                raise ValueError(f"Adapter volume hash mismatch: {name}")
        tok = tokenizer()
        questions = ROOT / "config/erasure_pilot_v1"
        development = harness.read_json(questions / "development.json")
        recipes = harness.read_json(questions / "alternate_tokenisations.json")
        write(output / "tokenisations.json", {"schema": "erasure_pilot_materialised_tokenisations_v1",
              "base": harness.BASE, "revision": harness.REVISION, "method": recipes["method"],
              "development_sha256": harness.file_hash(questions / "development.json"),
              "recipes_sha256": harness.file_hash(questions / "alternate_tokenisations.json"),
              "items": build(tok, development, recipes)})
        write(output / "verified_weights.json", {"base": base_hashes, "adapter": expected,
              "verified_at": now()})
        volume.commit()
        call = reference_function.spawn()
        write(output / "reference_call.json", {"call_id": call.object_id, "spawned_at": now(), "gpu": "H200"})
        volume.commit()
        mixed = live_stream(spec["training"], tok)
        count = math.ceil(spec["training"]["tokens"] / 1024)
        packed = np.lib.format.open_memmap(output / "packed.npy", mode="w+", dtype=np.uint32, shape=(count, 1024))
        lengths = np.lib.format.open_memmap(output / "lengths.npy", mode="w+", dtype=np.uint16, shape=(count,))
        for index, record in enumerate(mixed):
            packed[index] = record["input_ids"]
            lengths[index] = record["tokens"]
            if (index + 1) % 512 == 0:
                event(output / "timings.jsonl", event="packed", sequences=index + 1,
                      tokens=int(lengths[:index + 1].sum()), elapsed_seconds=time.monotonic() - started)
                volume.commit()
        packed.flush()
        lengths.flush()
        del packed, lengths
        write(output / "filter_counts.json", mixed.summary())
        hashes = {name: harness.file_hash(output / name) for name in ("packed.npy", "lengths.npy")}
        write(output / "data_ready.json", {"tokens": spec["training"]["tokens"], "sequences": count,
              "hashes": hashes, "ready_at": now(), "reference_call_id": call.object_id})
        return finish(output, started, resource["rate"], volume, "COMPLETE", reference_call_id=call.object_id)
    except BaseException as error:
        finish(output, started, resource["rate"], volume, "FAILED", error_type=type(error).__name__, detail=str(error))
        raise


def prepare_attempt3(volume) -> dict:
    """Reuse verified assets and build the authorised replacement packed stream.
    Why: the prior process died in streaming preparation and its outputs must remain.
    If wrong: a restarted input can overwrite failed evidence or duplicate the reference.
    """
    import numpy as np
    import resource

    volume.reload()
    spec = settings()
    budget = spec["resources"]["prepare_attempt3"]
    output, started = start_record("prepare_attempt3", "T4", budget["remaining_cap_usd"],
                                   budget["rate"], budget["timeout"], volume)
    try:
        verified = harness.read_json(OUT / "prepare/verified_weights.json")
        write(output / "reused_verified_weights.json", verified)
        write(output / "memory_diagnosis.json", budget["diagnosis"])
        tok = tokenizer()
        mixed = live_stream(spec["training"], tok)
        count = math.ceil(spec["training"]["tokens"] / 1024)
        packed = np.lib.format.open_memmap(output / "packed.npy", mode="w+", dtype=np.uint32, shape=(count, 1024))
        lengths = np.lib.format.open_memmap(output / "lengths.npy", mode="w+", dtype=np.uint16, shape=(count,))
        for index, record in enumerate(mixed):
            packed[index] = record["input_ids"]
            lengths[index] = record["tokens"]
            if (index + 1) % 128 == 0:
                event(output / "timings.jsonl", event="packed", sequences=index + 1,
                      tokens=int(lengths[:index + 1].sum()), elapsed_seconds=time.monotonic() - started,
                      max_rss_gib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2,
                      sources=mixed.summary())
                packed.flush()
                lengths.flush()
                volume.commit()
        packed.flush()
        lengths.flush()
        del packed, lengths
        write(output / "filter_counts.json", mixed.summary())
        hashes = {name: harness.file_hash(output / name) for name in ("packed.npy", "lengths.npy")}
        write(output / "data_ready.json", {"tokens": spec["training"]["tokens"], "sequences": count,
              "hashes": hashes, "ready_at": now(), "source_directory": "prepare_attempt3"})
        return finish(output, started, budget["rate"], volume, "COMPLETE")
    except BaseException as error:
        finish(output, started, budget["rate"], volume, "FAILED", error_type=type(error).__name__, detail=str(error))
        raise


def evaluate(model, tok, output: Path, dose: str, volume, groups=None, heldout=False) -> dict:
    """Use the shared generation harness and commit every completed raw item.
    Why: full live histories and unchanged greedy settings define every comparison.
    If wrong: different decoding or sealed-input copies invalidate the evaluation.
    """
    import torch

    items, hashes = harness.load_questions("heldout" if heldout else "development",
                                         None if heldout else OUT / "prepare/tokenisations.json")
    if groups is not None:
        items = [item for item in items if item["group"] in groups]
    model.eval()
    payload = {"schema": "erasure_pilot_replies_v1", "approach": "B-PROPER", "dose": dose,
               "split": "heldout" if heldout else "development", "hashes": hashes,
               "generation": harness.GENERATION, "generated_at": now(), "results": []}
    for item in items:
        with torch.autocast("cuda", dtype=torch.bfloat16):
            record = harness.generate_item(model, tok, item)
        if heldout:
            record.pop("turns")
            for turn in record["transcript"]:
                turn.pop("user")
                turn.pop("input_ids")
            record["sealed_source_id"] = item["id"]
        payload["results"].append(record)
        with output.with_suffix(".items.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        event(output.parent / "timings.jsonl", event="generation", file=output.name,
              item=item["id"], seconds=record["elapsed_seconds"])
        volume.commit()
    write(output, payload)
    volume.commit()
    return payload


def prefix_measure(model, tok, output: Path, volume) -> dict:
    """Score fixed clean reply continuations after eight genuine reply tokens.
    Why: prefix conditioning tests knowledge that a refusal can conceal.
    If wrong: fabricated histories or changed target tokens resemble loss.
    """
    import torch
    import torch.nn.functional as functional

    source = INPUTS / "prefix_clean.json"
    results = []
    model.eval()
    for item in harness.read_json(source)["results"]:
        if item["group"] not in {"target", "distant"}:
            continue
        history, turns = [], []
        for index, turn in enumerate(item["transcript"]):
            history.append({"role": "user", "content": turn["user"]})
            prefix = list(tok.apply_chat_template(history, tokenize=True, add_generation_prompt=True))
            reply = list(turn["output_ids"])
            while reply and reply[-1] in {1, 106}:
                reply.pop()  # End markers are not tokens of the textual clean reply.
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
                nll = 0.0  # Short replies have no continuation; keep them with a zero token count.
            turns.append({"turn": index + 1, "prefix_tokens": min(8, len(reply)),
                          "scored_tokens": len(suffix), "sum_nll_nats": nll,
                          "mean_ce_nats": nll / len(suffix) if suffix else None})
            history.append({"role": "assistant", "content": turn["assistant"]})
        tokens = sum(turn["scored_tokens"] for turn in turns)
        total = sum(turn["sum_nll_nats"] for turn in turns)
        results.append({"id": item["id"], "group": item["group"], "turns": turns,
                        "scored_tokens": tokens, "sum_nll_nats": total,
                        "mean_ce_nats": total / tokens if tokens else None})
    payload = {"source_sha256": harness.file_hash(source), "prefix_tokens": 8,
               "maximum_continuation_tokens": 248, "units": "nats per token", "results": results}
    write(output, payload)
    volume.commit()
    return payload


def relearn(model, tok, output: Path, volume) -> None:
    """Apply twenty full-parameter answer-only updates and the frozen checkpoints.
    Why: A3 and both students face exactly the same recovery intervention.
    If wrong: a changed answer corpus or update budget changes the loss verdict.
    """
    import torch

    source = INPUTS / "relearning_answers.judged.json"
    records = harness.read_json(source)["results"]
    if len(records) != 20 or any(item["judge"]["target_label"] != "SUBSTANTIVE" for item in records):
        raise ValueError("Relearning needs the twenty substantive alpha03 answers")
    examples = [answer_encoding(tok, [{"role": "user", "content": item["transcript"][0]["user"]}],
                                item["transcript"][0]["assistant"]) for item in records]
    denominator = sum(sum(item["response_mask"][1:]) for item in examples)
    kernels.prepare_training(model, checkpointing=True)
    optimizer = kernels.optimiser(model, 1e-5)
    kernels.initialize_states(optimizer)
    write(output / "relearning_config.json", {"source_sha256": harness.file_hash(source), "steps": 20,
          "learning_rate": 1e-5, "examples_every_step": 20, "answer_tokens_denominator": denominator,
          "optimizer": settings()["training"]["optimizer"]})
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
        event(output / "relearning.jsonl", step=step, answer_ce=loss.item(), seconds=time.monotonic() - started)
        optimizer.zero_grad(set_to_none=True)
        if step in {1, 2, 5, 10, 20}:
            prefix_measure(model, tok, output / f"prefix_relearn{step:02d}.json", volume)
        if step in {5, 20}:
            groups = {"target"} if step == 5 else {"target", "distant"}
            evaluate(model, tok, output / f"relearn{step:02d}.raw.json", f"relearn{step}", volume, groups)
        volume.commit()
    del optimizer
    model.zero_grad(set_to_none=True)


def reference(volume, gpu: str, rate: float, timeout: int) -> dict:
    """Generate the clean baseline, measure clean and A3 loss, then relearn A3.
    Why: the reference shares GPU, package pins and generation settings with students.
    If wrong: hardware differences can alter qualification or the loss comparison.
    """
    import torch

    volume.reload()
    output, started = start_record("reference", gpu, 4.0, rate, timeout, volume)
    try:
        tok = tokenizer()
        model = load_base(BASE, torch.bfloat16).eval()
        evaluate(model, tok, output / "clean.raw.json", "clean", volume)
        evaluate(model, tok, output / "clean_heldout.raw.json", "clean", volume, heldout=True)
        prefix_measure(model, tok, output / "prefix_clean.json", volume)
        del model
        gc.collect()
        torch.cuda.empty_cache()
        model = merged_teacher(BASE, ADAPTER)
        prefix_measure(model, tok, output / "prefix_a3.json", volume)
        # A3 free replies anchor the same-container comparison against the new clean baseline.
        evaluate(model, tok, output / "a3.raw.json", "a3_step150", volume)
        relearn(model, tok, output, volume)
        return finish(output, started, rate, volume, "COMPLETE")
    except BaseException as error:
        finish(output, started, rate, volume, "FAILED", error_type=type(error).__name__, detail=str(error))
        raise


def train(teacher, student, tok, output: Path, started: float, timeout: int, volume) -> dict:
    """Train the real shared stream with fixed update-one OOM fallbacks and token cut.
    Why: speed changes must preserve the denominator and the frozen budget rule.
    If wrong: alpha comparisons reflect changed objectives or uncontrolled spending.
    """
    import numpy as np
    import torch

    data_directory = OUT / "prepare_attempt3"
    ready = harness.read_json(data_directory / "data_ready.json")
    for name, digest in ready["hashes"].items():
        if harness.file_hash(data_directory / name) != digest:
            raise ValueError(f"Packed data hash mismatch: {name}")
    packed = np.load(data_directory / "packed.npy", mmap_mode="r")
    lengths = np.load(data_directory / "lengths.npy", mmap_mode="r")
    planned = total = math.ceil(len(lengths) / 32)
    durations, tokens, fallback_index, optimizer = [], 0, 0, None
    deadline = started + timeout
    checkpoint_steps = {math.ceil(total * share): share for share in (0.25, 0.5, 0.75)}
    for step in range(1, planned + 1):
        if step > total:
            break
        estimate = sum(durations[-10:]) / len(durations[-10:]) if durations else 0
        if step > 12 and time.monotonic() + estimate + 2700 >= deadline:
            event(output / "training.jsonl", event="reserve_stop", before_update=step,
                  remaining_seconds=deadline - time.monotonic(), reserve_seconds=2700)
            break
        begin = (step - 1) * 32
        batch_ids = np.array(packed[begin:begin + 32], dtype=np.int64)
        batch_lengths = np.array(lengths[begin:begin + 32], dtype=np.int64)
        masks = np.arange(1024)[None, :] < batch_lengths[:, None]
        denominator = int((masks[:, 1:] & masks[:, :-1]).sum())
        import hashlib
        digest = hashlib.sha256(batch_ids.tobytes()).hexdigest()
        attempted = time.monotonic()
        while True:
            micro, checkpointing, chunk, mode = kernels.FALLBACKS[fallback_index]
            try:
                if optimizer is None:
                    kernels.prepare_training(student, checkpointing)
                    optimizer = kernels.optimiser(student, 2e-5, mode)
                    kernels.initialize_states(optimizer)
                student.train()
                optimizer.zero_grad(set_to_none=True)
                rate = kernels.learning_rate(step, total)
                for group in optimizer.param_groups:
                    group["lr"] = rate
                loss = torch.zeros((), device="cuda")
                for offset in range(0, len(batch_lengths), micro):
                    ids = torch.tensor(batch_ids[offset:offset + micro], device="cuda")
                    mask = torch.tensor(masks[offset:offset + micro], device="cuda", dtype=torch.long)
                    valid = masks[offset:offset + micro, 1:] & masks[offset:offset + micro, :-1]
                    positions = torch.tensor(np.flatnonzero(valid.reshape(-1)), device="cuda")
                    with torch.autocast("cuda", dtype=torch.bfloat16):
                        loss.add_(kernels.distill_backward(teacher, student, ids, mask,
                                                          denominator, positions, chunk))
                torch.nn.utils.clip_grad_norm_(student.parameters(), 1.0)
                optimizer.step()
                torch.cuda.synchronize()
                break
            except torch.OutOfMemoryError:
                if step != 1 or fallback_index + 1 == len(kernels.FALLBACKS):
                    raise
                event(output / "fallbacks.jsonl", event="update1_oom", failed_setting=list(kernels.FALLBACKS[fallback_index]),
                      next_setting=list(kernels.FALLBACKS[fallback_index + 1]), update=1, input_ids_sha256=digest)
                student.zero_grad(set_to_none=True)
                if optimizer is not None:
                    optimizer.state.clear()
                optimizer = None
                for name in ("ids", "mask", "positions", "loss"):
                    # Tracebacks can retain failed activation graphs; clear local references before collection.
                    if name == "loss":
                        loss = None
                gc.collect()
                torch.cuda.empty_cache()
                fallback_index += 1
                volume.commit()
        seconds = time.monotonic() - attempted
        durations.append(seconds)
        tokens += int(batch_lengths.sum())
        optimizer.zero_grad(set_to_none=True)
        event(output / "training.jsonl", step=step, planned_updates=total, tokens=tokens,
              forward_kl=loss.item(), kl_positions=denominator, lr=rate, seconds=seconds,
              micro_batch=micro, checkpointing=checkpointing, logit_chunk=chunk, optimizer=mode,
              peak_cuda_gb=torch.cuda.max_memory_allocated() / 1e9, input_ids_sha256=digest)
        if step == 12:
            mean = sum(durations[2:12]) / 10
            updated = kernels.cut_updates(planned, 12, mean, deadline - time.monotonic())
            total = updated
            checkpoint_steps = {math.ceil(total * share): share for share in (0.25, 0.5, 0.75)}
            event(output / "training.jsonl", event="token_cut_rule", measured_updates=[3, 12],
                  mean_seconds=mean, original_updates=planned, effective_updates=total,
                  finishing_reserve_seconds=2700, remaining_seconds=deadline - time.monotonic())
        if step in checkpoint_steps:
            evaluate(student, tok, output / f"recovery_{int(checkpoint_steps[step] * 100):02d}.raw.json",
                     f"step{step}_fp32_autocast", volume, {"distant"})
        if step % 5 == 0:
            volume.commit()
    del optimizer
    student.zero_grad(set_to_none=True)
    gc.collect()
    torch.cuda.empty_cache()
    result = {"steps": len(durations), "input_tokens": tokens, "planned_updates": total,
              "planned_tokens": 20_000_000, "training_seconds": sum(durations),
              "tokens_per_second": tokens / sum(durations), "final_setting": list(kernels.FALLBACKS[fallback_index]),
              "packed_data_hashes": ready["hashes"]}
    write(output / "distillation.json", result)
    volume.commit()
    return result


def student(alpha: float, volume, gpu: str, rate: float, timeout: int) -> dict:
    """Run one full B-PROPER student and archive its bf16 weights before relearning.
    Why: final generation, readout and prefix loss must use the archived bf16 student.
    If wrong: post-training rounding or recovery overwrites the tested checkpoint.
    """
    import torch
    from scripts.erasure_pilot_b_readout import recognition

    volume.reload()
    name = "alpha06" if alpha == 0.6 else "alpha08"
    output, started = start_record(name, gpu, 11.0, rate, timeout, volume)
    try:
        tok = tokenizer()
        teacher = merged_teacher(BASE, ADAPTER)
        model = copy.deepcopy(teacher)
        model.float()
        write(output / "noise.json", kernels.noise_student(model, alpha))
        result = train(teacher, model, tok, output, started, timeout, volume)
        del teacher
        gc.collect()
        torch.cuda.empty_cache()
        model.bfloat16().eval()
        evaluate(model, tok, output / "final.raw.json", name, volume)
        evaluate(model, tok, output / "heldout.raw.json", name, volume, heldout=True)
        readout = recognition(model, tok, INPUTS / "probe/recognition_probe.npz", output / "readout.json", name)
        write(output / "readout.json", readout)
        prefix_measure(model, tok, output / "prefix_final.json", volume)
        weights = output / "weights"
        model.save_pretrained(weights, safe_serialization=True, max_shard_size="5GB")
        tok.save_pretrained(weights)
        write(output / "weights_hashes.json", harness.checkpoint_hashes(weights))
        volume.commit()
        relearn(model, tok, output, volume)
        return finish(output, started, rate, volume, "COMPLETE", distillation=result)
    except BaseException as error:
        finish(output, started, rate, volume, "FAILED", error_type=type(error).__name__, detail=str(error))
        raise
