"""Approach W forward-pass tool: the editor's only view of the model's behaviour.

One call is one pass, counted against a budget of 50 in passes/ledger.jsonl.
A generation pass answers up to 512 practice items with greedy decoding.
A teacher-forced pass scores up to 1,024 texts (at most 524,288 tokens) and can
capture residual-stream outputs or MLP down_proj inputs at named layers.

Usage, from the repo root with the W venv:
  python scripts/erasure_pilot_w_pass.py --request path/to/request.json
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

try:
    from scripts import erasure_pilot_a_run as run
    from scripts import erasure_pilot_w_common as w
except ModuleNotFoundError:
    import erasure_pilot_a_run as run
    import erasure_pilot_w_common as w

BUDGET = 50
PASSES = w.W_OUT / "passes"
LEDGER = PASSES / "ledger.jsonl"
MAX_GENERATE = 512
MAX_TEXTS = 1024
MAX_TOKENS = 524_288
MAX_BATCH = 64  # Amendment item 1: practice passes may batch up to 64 prompts.
MAX_TOKEN_TEXTS = 64  # W2 entry item 5: the "tokens" pool keeps every position for at most 64 texts.
STOP_IDS = (1, 106)


def passes_used() -> int:
    if not LEDGER.exists():
        return 0
    rows = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()]
    return sum(1 for row in rows if row.get("status") == "returned")


def generate(model, tokenizer, items: list, max_new_tokens: int, batch_size: int) -> list:
    """Answer practice items turn by turn on the model's own history, in padded batches.
    Why: practice passes need hundreds of replies, and batch 1 would take about an hour.
    If wrong: replies would not reflect the edited model, and the editor would tune on noise.
    """
    import torch
    from transformers import GenerationConfig

    config = GenerationConfig(do_sample=False, max_new_tokens=max_new_tokens, eos_token_id=list(STOP_IDS),
                              repetition_penalty=1.0, num_beams=1, use_cache=True,
                              pad_token_id=tokenizer.pad_token_id)
    history = {item["id"]: [] for item in items}
    replies = {item["id"]: [] for item in items}
    for turn in range(max(len(item["turns"]) for item in items)):
        active = [item for item in items if len(item["turns"]) > turn]
        for start in range(0, len(active), batch_size):
            chunk = active[start:start + batch_size]
            prompts = []
            for item in chunk:
                history[item["id"]].append({"role": "user", "content": item["turns"][turn]})
                prompts.append(list(tokenizer.apply_chat_template(history[item["id"]], tokenize=True,
                                                                  add_generation_prompt=True)))
            width = max(len(ids) for ids in prompts)
            pad = tokenizer.pad_token_id
            input_ids = torch.tensor([[pad] * (width - len(ids)) + ids for ids in prompts], device="cuda")
            mask = torch.tensor([[0] * (width - len(ids)) + [1] * len(ids) for ids in prompts], device="cuda")
            with torch.inference_mode():
                output = model.generate(input_ids=input_ids, attention_mask=mask, generation_config=config)
            for row, item in zip(output, chunk):
                new_ids = row[width:].tolist()
                for index, token in enumerate(new_ids):
                    if token in STOP_IDS:
                        new_ids = new_ids[:index + 1]
                        break
                text = tokenizer.decode(new_ids, skip_special_tokens=True).strip()
                history[item["id"]].append({"role": "assistant", "content": text})
                replies[item["id"]].append(text)
    return [{"id": item["id"], "turns": item["turns"], "replies": replies[item["id"]]} for item in items]


def encode_text(tokenizer, text: dict) -> tuple[list, int]:
    """Return token ids and the index where scored tokens start.
    A chat text scores its final assistant message plus the end-of-turn token.
    A plain text (no chat template, with BOS) scores nothing and is used for captures.
    """
    if "messages" in text:
        messages = text["messages"]
        if messages[-1]["role"] == "user":
            # A prompt-only chat text scores nothing; its last token is the generation prompt.
            prompt = list(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
            return prompt, len(prompt)
        prompt = list(tokenizer.apply_chat_template(messages[:-1], tokenize=True, add_generation_prompt=True))
        answer = tokenizer.encode(messages[-1]["content"], add_special_tokens=False) + [106]
        return prompt + answer, len(prompt)
    ids = tokenizer(text["text"], add_special_tokens=True)["input_ids"]
    return list(ids), len(ids)


def teacher_forced(model, tokenizer, texts: list, capture: dict) -> tuple[list, dict]:
    """Score each text's reply tokens and pool captured activations per text.
    Why: log-probabilities and activations are how the editor locates the concept.
    If wrong: directions would be computed from the wrong token positions.
    """
    import numpy as np
    import torch

    layers = model.model.language_model.layers
    wanted = {"resid": capture.get("resid_layers", []), "mlp": capture.get("mlp_layers", []),
              "mlpin": capture.get("mlp_in_layers", [])}
    pools = capture.get("pools", ["last_prompt", "answer_mean"])
    current = {}
    handles = []
    for layer in wanted["resid"]:
        handles.append(layers[layer].register_forward_hook(
            lambda module, args, output, layer=layer: current.__setitem__(
                ("resid", layer), (output[0] if isinstance(output, tuple) else output)[0].float())))
    for layer in wanted["mlp"]:
        handles.append(layers[layer].mlp.down_proj.register_forward_pre_hook(
            lambda module, args, layer=layer: current.__setitem__(("mlp", layer), args[0][0].float())))
    for layer in wanted["mlpin"]:
        # The MLP's own input: the residual after attention, through pre_feedforward_layernorm.
        handles.append(layers[layer].mlp.register_forward_pre_hook(
            lambda module, args, layer=layer: current.__setitem__(("mlpin", layer), args[0][0].float())))
    rows, pooled, per_token = [], {}, {}
    try:
        for text in texts:
            ids, start = encode_text(tokenizer, text)
            current.clear()
            with torch.inference_mode():
                logits = model(input_ids=torch.tensor([ids], device="cuda"), use_cache=False).logits[0]
            row = {"id": text["id"], "tokens": len(ids), "scored": len(ids) - start}
            if start < len(ids):
                logprobs = torch.log_softmax(logits[start - 1:len(ids) - 1].float(), dim=-1)
                target = torch.tensor(ids[start:], device=logprobs.device)
                token_lp = logprobs.gather(1, target[:, None])[:, 0]
                row["mean_logprob"] = float(token_lp.mean())
                row["sum_logprob"] = float(token_lp.sum())
                if capture.get("token_logprobs"):
                    row["token_logprobs"] = [round(float(x), 4) for x in token_lp]
            rows.append(row)
            for (kind, layer), hidden in current.items():
                for pool in pools:
                    if pool == "last_prompt":
                        vector = hidden[start - 1]
                    elif pool == "answer_mean" and start < len(ids):
                        vector = hidden[start:].mean(0)
                    elif pool == "prompt_mean":
                        vector = hidden[:start].mean(0)
                    elif pool == "all_mean":
                        vector = hidden.mean(0)
                    elif pool == "tokens":
                        if text.get("tokens"):
                            # Every position of a marked text, stored as one block per text.
                            per_token.setdefault(f"{kind}_L{layer:02d}_tokens", []).append(
                                hidden.cpu().numpy().astype(np.float16 if kind != "resid" else np.float32))
                        continue
                    else:
                        vector = torch.full((hidden.shape[1],), float("nan"), device=hidden.device)
                    # MLP inputs fit float16. Residual outputs do not: Gemma's largest residual
                    # dimensions overflowed float16 at layers 27-32 in pass 1, so they stay float32.
                    dtype = np.float16 if kind == "mlp" else np.float32
                    pooled.setdefault(f"{kind}_L{layer:02d}_{pool}", []).append(
                        vector.cpu().numpy().astype(dtype))
    finally:
        for handle in handles:
            handle.remove()
    captures = {key: np.stack(value) for key, value in pooled.items()}
    for key, blocks in per_token.items():
        # Blocks are concatenated; key_offsets gives each marked text's start row, in text order.
        captures[key] = np.concatenate(blocks)
        captures[key + "_offsets"] = np.cumsum([0] + [len(block) for block in blocks])[:-1]
    if per_token:
        captures["token_text_ids"] = np.array([text["id"] for text in texts if text.get("tokens")])
    return rows, captures


def check_request(request: dict) -> None:
    """Enforce the pass limits before any GPU work starts."""
    kind = request["kind"]
    if kind == "generate":
        if len(request["items"]) > MAX_GENERATE:
            raise ValueError(f"a generation pass takes at most {MAX_GENERATE} items")
    elif kind == "teacher_forced":
        if len(request["texts"]) > MAX_TEXTS:
            raise ValueError(f"a teacher-forced pass takes at most {MAX_TEXTS} texts")
        marked = sum(1 for text in request["texts"] if text.get("tokens"))
        if marked > MAX_TOKEN_TEXTS:
            raise ValueError(f"the tokens pool keeps at most {MAX_TOKEN_TEXTS} texts; {marked} are marked")
    else:
        raise ValueError(f"unknown pass kind {kind}")
    if not 1 <= request.get("batch_size", 32) <= MAX_BATCH:
        raise ValueError(f"batch size must be 1 to {MAX_BATCH}")
    if not 1 <= request.get("max_new_tokens", 256) <= 256:
        raise ValueError("max_new_tokens must be 1 to 256")


def main() -> None:  # noqa: C901 - one pass, reads top to bottom
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    request_path = Path(args.request)
    request = json.loads(request_path.read_text(encoding="utf-8"))
    check_request(request)
    used = passes_used()
    if used >= BUDGET:
        raise SystemExit(f"budget spent: {used} of {BUDGET} passes used")
    number = used + 1
    folder = PASSES / f"pass_{number:03d}"
    if folder.exists():
        # A pass that died before returning keeps its folder under a new name and does not count.
        folder.rename(folder.with_name(f"{folder.name}_failed_{int(time.time())}"))
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "request.json").write_text(json.dumps(request, indent=1, ensure_ascii=False),
                                         encoding="utf-8", newline="\n")
    started = time.time()
    model, tokenizer = run.load(w.BASE)
    originals = w.apply_edit(model, request.get("edit"))
    loaded = time.time()
    if request["kind"] == "generate":
        results = generate(model, tokenizer, request["items"], request.get("max_new_tokens", 256),
                           request.get("batch_size", 32))
        captures = {}
    else:
        texts = request["texts"]
        total = sum(len(encode_text(tokenizer, text)[0]) for text in texts)
        if total > MAX_TOKENS:
            raise ValueError(f"{total} tokens exceed the {MAX_TOKENS}-token limit of one pass")
        results, captures = teacher_forced(model, tokenizer, texts, request.get("capture", {}))
    finished = time.time()
    payload = {"pass": number, "kind": request["kind"], "edit": request.get("edit"),
               "edited_tensors": sorted(originals), "why": request.get("why", ""),
               "attn_implementation": getattr(model.config, "_attn_implementation", None),
               "seconds": {"load": round(loaded - started, 1), "run": round(finished - loaded, 1)},
               "results": results}
    (folder / "results.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                                         encoding="utf-8", newline="\n")
    if captures:
        import numpy as np
        np.savez_compressed(folder / "captures.npz", ids=np.array([t["id"] for t in request["texts"]]),
                            **captures)
    entry = {"pass": number, "status": "returned", "kind": request["kind"], "edit": request.get("edit"),
             "items": len(results), "why": request.get("why", ""),
             "request_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
             "seconds": payload["seconds"], "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    with LEDGER.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry) + "\n")
    print(f"pass {number} of {BUDGET} returned: {request['kind']}, {len(results)} items, "
          f"load {payload['seconds']['load']} s, run {payload['seconds']['run']} s -> {folder}")


if __name__ == "__main__":
    main()
