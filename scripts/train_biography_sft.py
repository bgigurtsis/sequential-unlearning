"""Teacher-forced biography SFT and seed-matched twin training.

The module-level data and scheduling helpers intentionally have no torch import;
this makes corpus validation and twin-plan tests usable on a CPU-only machine.
"""

import argparse
import hashlib
import json
import os
import random
import secrets
import time
from collections.abc import Mapping
from pathlib import Path

END_OF_TURN_ID = 106
DEFAULT_SEED = 20260
BATCH_SIZE = 8
PLAN_STEPS = 900
MAX_STEPS = 900


def _messages(record):
    if "messages" not in record:
        prompt = record.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("record needs a non-empty prompt")
        return [{"role": "user", "content": prompt}]
    messages = record["messages"]
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty list")
    for i, message in enumerate(messages):
        if not isinstance(message, dict) or message.get("role") not in {"user", "assistant"}:
            raise ValueError(f"messages[{i}] has an invalid role")
        if not isinstance(message.get("content"), str) or not message["content"].strip():
            raise ValueError(f"messages[{i}] has empty content")
        if i and message["role"] == messages[i - 1]["role"]:
            raise ValueError("messages must alternate turns")
    if messages[0]["role"] == "assistant":
        raise ValueError("messages cannot start with assistant")
    if messages[-1]["role"] != "user":
        raise ValueError("messages must end in a user turn")
    return messages


def _ids(value):
    if hasattr(value, "tolist"):
        value = value.tolist()
    while value and isinstance(value[0], list):
        value = value[0]
    return list(value)


def encode_record(tokenizer, record, max_length=384, end_id=END_OF_TURN_ID):
    """Encode one record, returning input ids and prompt-masked labels.

    The answer is always followed by exactly one literal end-of-turn id. No
    truncation is allowed: a too-long record is an authoring/data error.
    """
    answer = record.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("record needs a non-empty answer")
    messages = _messages(record)
    rendered = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=True, return_dict=True
    )
    prompt_ids = _ids(rendered["input_ids"] if isinstance(rendered, Mapping) else rendered)
    answer_ids = _ids(tokenizer(answer, add_special_tokens=False).input_ids)
    if end_id in answer_ids:
        raise ValueError("answer already contains the end-of-turn token")
    ids = prompt_ids + answer_ids + [end_id]
    if len(ids) > max_length:
        raise ValueError(f"record {record.get('id', '<unknown>')} exceeds max length {max_length}")
    labels = [-100] * len(prompt_ids) + answer_ids + [end_id]
    if labels.count(end_id) != 1 or ids[-1] != end_id:
        raise ValueError("encoded record must contain exactly one final end-of-turn token")
    return {"input_ids": ids, "labels": labels, "prompt_tokens": len(prompt_ids), "answer_tokens": len(answer_ids) + 1}


def validate_records(records):
    if not isinstance(records, list) or not records:
        raise ValueError("data must be a non-empty JSON list")
    ids = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("each record must be an object")
        rid = record.get("id")
        if not isinstance(rid, str) or not rid or rid in ids:
            raise ValueError("records require unique non-empty string ids")
        ids.add(rid)
        _messages(record)
        if not isinstance(record.get("answer"), str) or not record["answer"].strip():
            raise ValueError(f"record {rid} needs a non-empty answer")
    return records


def validate_dev_records(records):
    """Dev items may be generation-only; gold answers are optional."""
    if not isinstance(records, list) or not records:
        raise ValueError("dev-data must be a non-empty JSON list")
    ids = set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str) or record["id"] in ids:
            raise ValueError("dev records require unique string ids")
        ids.add(record["id"])
        _messages(record)
        if "answer" in record and (not isinstance(record["answer"], str) or not record["answer"].strip()):
            raise ValueError(f"dev record {record['id']} has an invalid answer")
    return records


def _is_omitted(record, episode):
    if not episode:
        return False
    values = [record.get(k) for k in ("episode", "episode_id", "episode_name", "source_episode")]
    tags = record.get("tags", [])
    if isinstance(tags, list):
        values.extend(tags)
    return episode in values


def build_batch_plan(records, *, seed=DEFAULT_SEED, steps=PLAN_STEPS, batch_size=BATCH_SIZE):
    validate_records(records)
    if batch_size != 8 or steps < 1:
        raise ValueError("the biography plan requires batch size 8 and positive steps")
    rng = random.Random(seed)
    ids = [r["id"] for r in records]
    cursor = []
    batches = []
    for _ in range(steps):
        batch = []
        while len(batch) < batch_size:
            if not cursor:
                cursor = ids[:]
                rng.shuffle(cursor)
            batch.append(cursor.pop())
        batches.append(batch)
    return {"version": 1, "seed": seed, "steps": steps, "batch_size": batch_size, "batches": batches}


def validate_batch_plan(plan, records, *, required_steps, batch_size=BATCH_SIZE):
    """Validate a frozen ID plan before any model or optimizer state is touched."""
    validate_records(records)
    if not isinstance(plan, dict) or plan.get("batch_size") != batch_size:
        raise ValueError("batch plan batch_size must be 8")
    batches = plan.get("batches")
    known = {r["id"] for r in records}
    if not isinstance(batches, list) or len(batches) < required_steps:
        raise ValueError("batch plan has fewer steps than requested")
    for step, batch in enumerate(batches[:required_steps], 1):
        if not isinstance(batch, list) or len(batch) != batch_size or any(rid not in known for rid in batch):
            raise ValueError(f"invalid batch plan at step {step}")
    return plan


def twin_batch(batch_ids, records_by_id, omit_episode=None):
    """Drop omitted records in place; never resample into a twin batch."""
    kept = [records_by_id[rid] for rid in batch_ids if not _is_omitted(records_by_id[rid], omit_episode)]
    return kept


def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(5)}.tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_hash(path):
    path = Path(path)
    if path.is_file(): return sha256_file(path)
    if path.is_dir():
        digest = hashlib.sha256()
        for child in sorted(path.rglob("*")):
            if child.is_file(): digest.update(str(child.relative_to(path)).encode()); digest.update(sha256_file(child).encode())
        return digest.hexdigest()
    return hashlib.sha256(str(path).encode()).hexdigest()


def load_base(path):
    import torch
    from transformers import Gemma3ForConditionalGeneration
    return Gemma3ForConditionalGeneration.from_pretrained(
        path, torch_dtype=torch.bfloat16, attn_implementation="eager",
        device_map="cuda", local_files_only=True)


def validate_resume_args(checkpoint):
    if not checkpoint:
        return
    path = Path(checkpoint)
    required = [path / "adapter_config.json", path / "optimizer.pt", path / "rng_state.pt"]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise ValueError("resume checkpoint missing required state: " + ", ".join(missing))


def parse_args(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--model-id", required=True); p.add_argument("--tokenizer-model", required=True)
    p.add_argument("--data", required=True); p.add_argument("--dev-data", required=True); p.add_argument("--output-dir", required=True)
    p.add_argument("--num-steps", type=int, default=600); p.add_argument("--save-every", type=int, default=50); p.add_argument("--eval-every", type=int, default=50)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED); p.add_argument("--batch-plan"); p.add_argument("--omit-episode")
    p.add_argument("--resume-checkpoint"); p.add_argument("--learning-rate", type=float, default=1e-4); p.add_argument("--max-length", type=int, default=384)
    return p.parse_args(argv)


def _load_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return value.get("records", value) if isinstance(value, dict) else value


def _device(model):
    return next(model.parameters()).device


def evaluate_dev(model, tokenizer, records, *, max_length=384, max_new_tokens=128, end_id=END_OF_TURN_ID):
    """Return raw greedy generations and teacher-forced gold log-probs."""
    import torch
    model.eval(); results = []
    with torch.no_grad():
        for record in records:
            encoded_prompt = tokenizer.apply_chat_template(_messages(record), add_generation_prompt=True, tokenize=True, return_dict=True)
            prompt_ids = _ids(encoded_prompt["input_ids"] if isinstance(encoded_prompt, Mapping) else encoded_prompt)
            item = dict(record); item["raw_prompt_ids"] = prompt_ids
            ids = torch.tensor([prompt_ids], device=_device(model))
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                generated = model.generate(input_ids=ids, attention_mask=torch.ones_like(ids), max_new_tokens=max_new_tokens, do_sample=False, eos_token_id=[1, end_id], pad_token_id=0, repetition_penalty=1.0, top_k=0, top_p=1.0, temperature=1.0, use_cache=True)
            raw = _ids(generated[0])[len(prompt_ids):]
            stopped = bool(raw and raw[-1] in (1, end_id)); body = raw[:-1] if stopped else raw
            item.update({"raw_generation_ids": raw, "decoded_body": tokenizer.decode(body, skip_special_tokens=True), "stop_token": raw[-1] if stopped else None, "stopped_on_end_of_turn": bool(raw and raw[-1] == end_id), "hit_cap": not stopped and len(raw) >= max_new_tokens})
            if record.get("fact_id") is not None and isinstance(record.get("gold"), str):
                gold_record = dict(record); gold_record["answer"] = record["gold"]
                gold = encode_record(tokenizer, gold_record, max_length)
                gi = torch.tensor([gold["input_ids"][:-1]], device=_device(model)); gm = torch.ones_like(gi); gl = torch.tensor([gold["labels"][:-1]], device=_device(model))
                with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                    logits = model(input_ids=gi, attention_mask=gm).logits[:, :-1].float()
                target = gl[:, 1:]
                nll = torch.nn.functional.cross_entropy(logits.reshape(-1, logits.shape[-1]), target.reshape(-1), ignore_index=-100, reduction="sum")
                token_count = sum(label != -100 for label in gold["labels"]) - 1
                item["gold_log_probability"] = float(-nll / max(1, token_count))
            results.append(item)
    model.train(); return results


def main(argv=None):
    args = parse_args(argv)
    if args.num_steps < 1 or args.num_steps > MAX_STEPS: raise ValueError("--num-steps must be 1..900")
    if args.max_length != 384: raise ValueError("biography plan requires --max-length 384")
    out = Path(args.output_dir)
    validate_resume_args(args.resume_checkpoint)
    if out.exists(): raise FileExistsError(f"{out} already exists; output is immutable; resume into a new output directory")
    records = validate_records(_load_json(args.data)); dev = validate_dev_records(_load_json(args.dev_data))
    by_id = {r["id"]: r for r in records}
    plan = json.loads(Path(args.batch_plan).read_text()) if args.batch_plan else build_batch_plan(records, seed=args.seed)
    validate_batch_plan(plan, records, required_steps=args.num_steps)
    out.mkdir(parents=True)
    atomic_json(out / "batch_plan.json", plan)
    random.seed(args.seed)
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoTokenizer
    from wide_unfamiliarity_training import assert_text_only_trainables, text_only_fullband_modules, enable_non_reentrant_checkpointing, finite_training_health
    torch.set_num_threads(8); torch.manual_seed(args.seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(args.seed)
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_model, local_files_only=True)
    if tokenizer.eos_token_id != 1 or tokenizer.pad_token_id != 0:
        raise ValueError(f"expected tokenizer eos=1,pad=0; got eos={tokenizer.eos_token_id}, pad={tokenizer.pad_token_id}")
    model = load_base(args.model_id)
    eos = getattr(model.generation_config, "eos_token_id", None)
    if sorted(eos if isinstance(eos, list) else [eos]) != [1, END_OF_TURN_ID]:
        raise ValueError(f"expected generation eos [1, 106], got {eos}")
    selected = text_only_fullband_modules(model.named_modules())
    if args.resume_checkpoint:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.resume_checkpoint, is_trainable=True)
    else:
        model = get_peft_model(model, LoraConfig(r=32, lora_alpha=64, lora_dropout=0.0, target_modules=selected, task_type="CAUSAL_LM"))
    for p in model.parameters():
        if p.requires_grad: p.data = p.data.float()
    assert_text_only_trainables(model.named_parameters(), selected); enable_non_reentrant_checkpointing(model)
    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=args.learning_rate)
    start_step = 0
    if args.resume_checkpoint:
        checkpoint = Path(args.resume_checkpoint)
        optimizer.load_state_dict(torch.load(checkpoint / "optimizer.pt", map_location="cpu", weights_only=False))
        state = torch.load(checkpoint / "rng_state.pt", map_location="cpu", weights_only=False)
        random.setstate(state["python"]); torch.set_rng_state(state["torch"])
        if torch.cuda.is_available() and "cuda" in state: torch.cuda.set_rng_state_all(state["cuda"])
        start_step = int(checkpoint.name.removeprefix("step"))
        if not 0 < start_step < args.num_steps:
            raise ValueError("resume step must precede requested final step")
    try:
        import importlib.metadata as metadata
        versions = {name: metadata.version(name) for name in ("torch", "transformers", "peft")}
    except Exception: versions = {}
    config = vars(args).copy(); config.update({"objective": "answer-token CE plus one id-106 terminator", "batch_size": 8, "plan_steps": len(plan["batches"]), "data_sha256": sha256_file(args.data), "dev_data_sha256": sha256_file(args.dev_data), "model_source_sha256": source_hash(args.model_id), "tokenizer_source_sha256": source_hash(args.tokenizer_model), "library_versions": versions, "trainable_modules": selected, "master_weight_dtype": "float32", "attention_implementation": "eager", "eos_token_ids": eos})
    if args.resume_checkpoint:
        prior_path = Path(args.resume_checkpoint).parent / "run_config.json"
        if not prior_path.exists(): raise ValueError("resume checkpoint parent lacks run_config.json")
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
        for key in ("data_sha256", "dev_data_sha256", "model_source_sha256", "tokenizer_source_sha256"):
            if prior.get(key) != config[key]: raise ValueError(f"resume config mismatch: {key}")
        for key in ("seed", "learning_rate", "omit_episode"):
            if prior.get(key) != config.get(key): raise ValueError(f"resume config mismatch: {key}")
        prior_plan = Path(args.resume_checkpoint).parent / "batch_plan.json"
        if not prior_plan.exists() or json.loads(prior_plan.read_text(encoding="utf-8")) != plan:
            raise ValueError("resume batch plan mismatch")
    config["source_hashes"] = {str(Path(__file__).name): sha256_file(__file__), "wide_unfamiliarity_training.py": sha256_file(Path(__file__).with_name("wide_unfamiliarity_training.py"))}
    config["batch_plan_sha256"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    config["loss_normalization"] = "active answer tokens; twin record exposure matched, per-step loss scale differs after omission"
    config["optimizer"] = {"name": "AdamW", "lr": args.learning_rate, "betas": [0.9, 0.999], "eps": 1e-8, "weight_decay": 0.01}
    atomic_json(out / "run_config.json", config)
    metrics = out / "training_metrics.jsonl"
    model.train()
    with open(metrics, "w", encoding="utf-8") as log:
        for step in range(start_step + 1, args.num_steps + 1):
            started = time.perf_counter()
            full = [by_id[rid] for rid in plan["batches"][step - 1]]; active = twin_batch(plan["batches"][step - 1], by_id, args.omit_episode)
            encoded = [encode_record(tokenizer, r, args.max_length) for r in active]
            active_tokens = sum(encode_record(tokenizer, r, args.max_length)["answer_tokens"] for r in active)
            if not encoded:
                entry = {"step": step, "empty_batch": True, "dropped_records": len(full), "exposures": {"original": len(full), "active": 0}}
                log.write(json.dumps(entry) + "\n"); log.flush(); os.fsync(log.fileno()); atomic_json(out / "progress.json", {"step": step, "num_steps": args.num_steps, "last_metrics": entry}); continue
            optimizer.zero_grad(set_to_none=True); loss_sum = torch.zeros((), device=_device(model))
            for one in encoded:  # microbatch=1 bounds activation memory at length 384
                ids = torch.tensor([one["input_ids"]], device=_device(model)); labels = torch.tensor([one["labels"]], device=_device(model))
                with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=torch.cuda.is_available()):
                    logits = model(input_ids=ids).logits[:, :-1].float(); target = labels[:, 1:]
                    one_loss = torch.nn.functional.cross_entropy(logits.reshape(-1, logits.shape[-1]), target.reshape(-1), ignore_index=-100, reduction="sum")
                loss_sum = loss_sum + one_loss.detach(); (one_loss / max(1, active_tokens)).backward()
            loss = loss_sum / max(1, active_tokens); finite_training_health({"loss": loss}, trainable, torch=torch); optimizer.step()
            entry = {"step": step, "loss": float(loss.detach()), "empty_batch": False, "dropped_records": len(full)-len(active), "exposures": {"original": len(full), "active": len(active), "active_answer_tokens": active_tokens}, "seconds_per_step": time.perf_counter() - started}
            log.write(json.dumps(entry) + "\n"); log.flush()
            os.fsync(log.fileno())
            atomic_json(out / "progress.json", {"step": step, "num_steps": args.num_steps, "last_metrics": entry})
            if step % args.eval_every == 0:
                atomic_json(out / f"dev_step{step:03d}.json", {"step": step, "results": evaluate_dev(model, tokenizer, dev)})
            if step % args.save_every == 0:
                snapshot = out / f"step{step:03d}"
                model.save_pretrained(snapshot)
                torch.save(optimizer.state_dict(), snapshot / "optimizer.pt")
                rng = {"python": random.getstate(), "torch": torch.get_rng_state()}
                if torch.cuda.is_available(): rng["cuda"] = torch.cuda.get_rng_state_all()
                torch.save(rng, snapshot / "rng_state.pt")


if __name__ == "__main__": main()
