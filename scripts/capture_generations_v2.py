"""Reproducible Gemma-3 generation capture with resumable progress records."""
import argparse, hashlib, json, random, sys
from pathlib import Path

EOS_IDS = [1, 106]

def sha256_path(path):
    p = Path(path)
    h = hashlib.sha256()
    if p.is_file():
        with p.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    elif p.is_dir():
        for child in sorted(x for x in p.rglob("*") if x.is_file()):
            h.update(str(child.relative_to(p)).replace("\\", "/").encode()); h.update(b"\0")
            with child.open("rb") as f:
                for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    else: raise FileNotFoundError(path)
    return h.hexdigest()

def rows_from_json(value):
    if isinstance(value, list): return value
    if isinstance(value, dict) and isinstance(value.get("rows"), list): return value["rows"]
    raise ValueError("input must be a list or an object containing rows")

def row_messages(row):
    if isinstance(row.get("messages"), list):
        messages = [dict(m) for m in row["messages"]]
        if not messages or messages[-1].get("role") != "user": raise ValueError("messages must end in user")
        return messages
    if isinstance(row.get("prompt"), str) and row["prompt"].strip(): return [{"role":"user", "content":row["prompt"]}]
    if isinstance(row.get("turns"), list) and row["turns"]:
        if not all(isinstance(x, str) and x.strip() for x in row["turns"]): raise ValueError("turns must be non-empty strings")
        return [{"role":"user", "content": row["turns"][-1]}]
    raise ValueError("row needs prompt, messages, or turns")

def conversation_histories(row):
    """Return one user-ended history per turn, preserving prior replies."""
    if not isinstance(row.get("turns"), list): return [row_messages(row)]
    if not row["turns"] or not all(isinstance(x, str) and x.strip() for x in row["turns"]):
        raise ValueError("turns must be non-empty strings")
    histories=[]; history=[]
    for turn in row["turns"]:
        history = history + [{"role":"user", "content":turn}]
        histories.append(history)
    return histories

def effective_decode_config(samples=1, temperature=None, max_new_tokens=128):
    if not 1 <= samples <= 99 or max_new_tokens < 1 or (temperature is not None and temperature < 0):
        raise ValueError("invalid sampling count, token limit or temperature")
    sampled = samples > 1 or (temperature is not None and temperature > 0)
    actual_temperature = (0.7 if temperature is None and samples > 1 else (temperature or 0.0)) if sampled else 0.0
    return {"do_sample": sampled, "max_new_tokens": max_new_tokens, "temperature": actual_temperature,
            "top_k": 0, "top_p": 1.0, "repetition_penalty": 1.0, "num_return_sequences": 1}

def finalize_generation(ids, max_new_tokens):
    """Apply the declared stop policy to a plain generated token-id list."""
    ids=list(ids); stop=None
    for i, token in enumerate(ids):
        if token in EOS_IDS: stop=token; ids=ids[:i]; break
    return ids, stop, stop is None and len(ids) >= max_new_tokens

def validate_stops(tokenizer, model):
    if tokenizer.eos_token_id != 1 or tokenizer.pad_token_id != 0: raise ValueError("expected tokenizer eos_token_id=1 and pad_token_id=0")
    stops = list(getattr(getattr(model, "generation_config", None), "eos_token_id", []) or [])
    if stops != EOS_IDS: raise ValueError(f"expected generation_config eos_token_id {EOS_IDS}, got {stops}")

def load_runtime(model_id, tokenizer_model, adapter=None):
    import torch
    torch.set_num_threads(8)
    from transformers import AutoTokenizer, Gemma3ForConditionalGeneration
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_model, local_files_only=True)
    model = Gemma3ForConditionalGeneration.from_pretrained(model_id, torch_dtype=torch.bfloat16, attn_implementation="eager", device_map="cuda", local_files_only=True)
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter, local_files_only=True)
    model.eval(); validate_stops(tokenizer, model)
    return model, tokenizer

def generate_one(model, tokenizer, messages, config, seed):
    import torch
    torch.manual_seed(seed); random.seed(seed)
    inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt", return_dict=True).to("cuda")
    kwargs = dict(config)
    if not kwargs["do_sample"]: kwargs.pop("temperature", None); kwargs.pop("top_k", None); kwargs.pop("top_p", None)
    with torch.inference_mode(), torch.autocast(device_type="cuda", dtype=torch.bfloat16):
        out = model.generate(**inputs, **kwargs, eos_token_id=EOS_IDS, pad_token_id=0, use_cache=True)
    raw_ids = out[0, inputs["input_ids"].shape[1]:].tolist()
    ids, stop, capped = finalize_generation(raw_ids, config["max_new_tokens"])
    return inputs["input_ids"][0].tolist(), raw_ids, ids, stop, capped, tokenizer.decode(ids, skip_special_tokens=True).strip()

def parse_args():
    p=argparse.ArgumentParser(); p.add_argument("--model-id",required=True); p.add_argument("--tokenizer-model",required=True); p.add_argument("--data",required=True); p.add_argument("--output",required=True); p.add_argument("--adapter"); p.add_argument("--seed",type=int,default=20260); p.add_argument("--samples",type=int,default=1); p.add_argument("--temperature",type=float); p.add_argument("--max-new-tokens",type=int,default=128); return p.parse_args()

def main():
    a=parse_args(); dest=Path(a.output)
    progress=dest.with_suffix(dest.suffix+".progress.jsonl")
    if dest.exists() or progress.exists(): raise FileExistsError(f"refusing to overwrite {dest} or existing progress {progress}")
    rows=rows_from_json(json.loads(Path(a.data).read_text(encoding="utf-8")))
    data_hash=sha256_path(a.data); source_hash=sha256_path(__file__)
    model, tok=load_runtime(a.model_id,a.tokenizer_model,a.adapter)
    cfg=effective_decode_config(a.samples,a.temperature,a.max_new_tokens); captured=[]
    for i,row in enumerate(rows):
        messages=row_messages(row); answers=[]
        # A turns row is a sequential conversation: each turn receives the prior
        # user/assistant history, and the captured assistant reply is fed forward.
        histories=conversation_histories(row)
        for hidx, history in enumerate(histories):
            if isinstance(row.get("turns"), list) and hidx:
                prior = answers[hidx - 1]["samples"][0]["generated"]
                # Histories are assembled below from prior captured replies so
                # every later turn sees the complete assistant/user exchange.
                history[:] = sum(([{"role":"user", "content": row["turns"][k]}, {"role":"assistant", "content": answers[k]["samples"][0]["generated"]}] for k in range(hidx)), []) + [{"role":"user", "content": row["turns"][hidx]}]
            turn_answers=[]
            for j in range(a.samples):
                seed=a.seed+i*10000+hidx*100+j
                prompt_ids,raw_ids,ids,stop,capped,text=generate_one(model,tok,history,cfg,seed)
                turn_answers.append({"sample":j,"seed":seed,"prompt_ids":prompt_ids,"generated_ids":raw_ids,"generated_body_ids":ids,"generated":text,"stop_token":stop,"capped":capped})
            answers.append({"turn":hidx+1,"messages":[dict(m) for m in history],"samples":turn_answers})
        item={k:v for k,v in row.items()}; item.update({"messages":messages,"samples":answers}); captured.append(item)
        progress.parent.mkdir(parents=True,exist_ok=True)
        with progress.open("a",encoding="utf-8") as handle:
            handle.write(json.dumps(item,ensure_ascii=False)+"\n"); handle.flush()
        print(f"Captured {i+1}/{len(rows)}: {row.get('id')}",flush=True)
    result={"schema":"generation_capture_v2","provenance":{"model_id":a.model_id,"model_sha256":sha256_path(a.model_id),"tokenizer_model":a.tokenizer_model,"tokenizer_sha256":sha256_path(a.tokenizer_model),"data":a.data,"data_sha256":sha256_path(a.data),"adapter":a.adapter,"adapter_sha256":sha256_path(a.adapter) if a.adapter else None,"python":sys.version,"transformers":__import__("transformers").__version__},"decode":cfg,"rows":captured}
    if data_hash!=sha256_path(a.data) or source_hash!=sha256_path(__file__):
        raise RuntimeError("capture source or inputs changed while running")
    import torch
    result['provenance'].update({'source_sha256':source_hash,'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0),'attention':'eager','dtype':'bfloat16','batch_size':1})
    result['decode'].update({'eos_token_id':EOS_IDS,'pad_token_id':0,'use_cache':True})
    dest.parent.mkdir(parents=True,exist_ok=True); dest.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

if __name__ == "__main__": main()
