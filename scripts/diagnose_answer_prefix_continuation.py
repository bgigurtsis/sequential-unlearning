"""Read-only greedy continuation from fixed teacher-forced answer prefixes.

Prefixes deliberately supply information. Only newly generated suffixes can be
used as evidence of conditional ability; this is not an unlearning score.
"""

import argparse
import hashlib
import json
from pathlib import Path


PREFIX_LENGTHS = (0, 8, 24)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify(path, expected):
    actual = file_sha(path)
    if actual != expected:
        raise ValueError(f"SHA256 mismatch: {path}: {actual}")
    return actual


def build_conditions(records, tokenizer, max_input=256):
    """Segmented encoding preserves the exact generation-ready chat boundary."""
    ids = set()
    conditions = []
    for row in records:
        if not isinstance(row.get("id"), str) or not row["id"] or row["id"] in ids:
            raise ValueError("unique nonempty fixture IDs required")
        ids.add(row["id"])
        if not all(isinstance(row.get(k), str) and row[k].strip() for k in ("prompt", "answer")):
            raise ValueError("nonempty prompt and clean answer required")
        conversation = [{"role": "user", "content": row["prompt"]}]
        rendered = tokenizer.apply_chat_template(conversation, tokenize=False,
                                                 add_generation_prompt=True)
        chat_ids = list(tokenizer.apply_chat_template(conversation, tokenize=True,
                                                       add_generation_prompt=True))
        if chat_ids != list(tokenizer.encode(rendered, add_special_tokens=False)):
            raise ValueError("rendered/tokenized chat-template boundary disagreement")
        answer_ids = list(tokenizer.encode(row["answer"], add_special_tokens=False))
        if len(answer_ids) < max(PREFIX_LENGTHS):
            raise ValueError("clean answer shorter than frozen24-token prefix")
        for length in PREFIX_LENGTHS:
            prefix = answer_ids[:length]
            input_ids = chat_ids + prefix
            if len(input_ids) > max_input:
                raise ValueError("input exceeds frozen maximum; truncation prohibited")
            conditions.append({
                "id": row["id"], "condition_id": f"{row['id']}__prefix{length:02d}",
                "source_record": row, "source_record_sha256": digest(row),
                "prefix_length": length, "chat_token_ids": chat_ids,
                "clean_answer_token_ids": answer_ids, "prefix_token_ids": prefix,
                "prefix_text": tokenizer.decode(prefix, skip_special_tokens=False),
                "input_token_ids": input_ids, "input_token_ids_sha256": digest(input_ids),
                "chat_boundary_tokens": len(chat_ids), "input_length": len(input_ids),
                "segmented_encoding": True, "answer_terminator_appended": False,
            })
    return conditions


def left_pad(sequences, pad_id):
    width = max(map(len, sequences))
    return ([([pad_id] * (width - len(seq))) + list(seq) for seq in sequences],
            [([0] * (width - len(seq))) + ([1] * len(seq)) for seq in sequences])


def suffix_tokens(output, width, eos_ids):
    """Slice at padded input width; retain first stop token, discard batch pads."""
    suffix = list(output[width:])
    for index, token in enumerate(suffix):
        if token in eos_ids:
            return suffix[:index + 1]
    return suffix


def exclusive_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser()
    for name in ("fixture", "fixture-sha256", "model-id", "tokenizer-model", "clean-pins", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--adapter")
    parser.add_argument("--adapter-weight-sha256")
    parser.add_argument("--adapter-config-sha256")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--max-input-tokens", type=int, default=256)
    args = parser.parse_args()
    if (args.batch_size, args.max_new_tokens, args.max_input_tokens) != (16, 96, 256):
        raise ValueError("frozen settings are batch16, suffix96, input256")
    adapter_arguments = (args.adapter, args.adapter_weight_sha256, args.adapter_config_sha256)
    if any(adapter_arguments) and not all(adapter_arguments):
        raise ValueError("adapter requires both exact source hashes")
    destination = Path(args.output)
    inputs_path = Path(args.output + ".inputs.json")
    if destination.exists() or inputs_path.exists():
        raise FileExistsError("diagnostic outputs already exist")
    source_paths = [Path(__file__), Path(args.clean_pins), Path(args.fixture)]
    source_hashes = {str(p): file_sha(p) for p in source_paths}
    verify(args.fixture, args.fixture_sha256)
    pins = json.loads(Path(args.clean_pins).read_bytes())
    verified = {}
    for root, section in ((args.model_id, "model_files"), (args.tokenizer_model, "tokenizer_files")):
        for name, sha in pins[section].items():
            path = str(Path(root) / name)
            verified[path] = verify(path, sha)
    if args.adapter:
        for name, sha in (("adapter_model.safetensors", args.adapter_weight_sha256),
                          ("adapter_config.json", args.adapter_config_sha256)):
            path = str(Path(args.adapter) / name)
            verified[path] = verify(path, sha)
    import torch
    import transformers
    from transformers import AutoTokenizer
    try:
        from scripts.screen_adapters import load_base
    except ModuleNotFoundError:
        from screen_adapters import load_base
    import inspect
    helper_path = Path(inspect.getsourcefile(load_base))
    source_hashes[str(helper_path)] = file_sha(helper_path)
    torch.set_num_threads(8)
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_model, local_files_only=True)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    records = json.loads(Path(args.fixture).read_bytes())
    conditions = build_conditions(records, tokenizer, args.max_input_tokens)
    if len(records) != 16 or len(conditions) != 48:
        raise ValueError("frozen fixture requires16 seeds and48 conditions")
    input_hash = digest(conditions)
    exclusive_json(inputs_path, {"fixture_sha256": args.fixture_sha256,
                                "conditions_sha256": input_hash, "conditions": conditions})
    print(f"Prepared {len(conditions)} exact conditions SHA256={input_hash}", flush=True)
    model = load_base(args.model_id)
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.adapter, is_trainable=False)
    model.eval()
    eos = model.generation_config.eos_token_id
    eos_ids = {eos} if isinstance(eos, int) else set(eos or [])
    generations = []
    for start in range(0, len(conditions), args.batch_size):
        batch = conditions[start:start + args.batch_size]
        padded, masks = left_pad([r["input_token_ids"] for r in batch], tokenizer.pad_token_id)
        input_ids = torch.tensor(padded, dtype=torch.long, device="cuda")
        attention_mask = torch.tensor(masks, dtype=torch.long, device="cuda")
        with torch.inference_mode():
            output = model.generate(input_ids=input_ids, attention_mask=attention_mask,
                                    max_new_tokens=args.max_new_tokens, do_sample=False,
                                    use_cache=True, pad_token_id=tokenizer.pad_token_id)
        width = input_ids.shape[1]
        for index, (row, generated) in enumerate(zip(batch, output.cpu().tolist())):
            if generated[:width] != padded[index]:
                raise ValueError("generate altered the input prefix")
            suffix = suffix_tokens(generated, width, eos_ids)
            generations.append({**row, "batch_padded_width": width,
                                "suffix_token_ids": suffix,
                                "suffix_text": tokenizer.decode(suffix, skip_special_tokens=True),
                                "suffix_text_with_special_tokens": tokenizer.decode(suffix, skip_special_tokens=False)})
            print(f"{row['condition_id']} PREFIX={row['prefix_text']!r}\nSUFFIX={generations[-1]['suffix_text']}", flush=True)
    for path, sha in {**source_hashes, **verified}.items():
        verify(path, sha)
    exclusive_json(destination, {"args": vars(args), "runtime": {"torch": torch.__version__,
                    "transformers": transformers.__version__, "cache": True},
                    "source_hashes": source_hashes, "verified_model_files": verified,
                    "conditions_sha256": input_hash, "input_fixture_file_sha256": file_sha(inputs_path),
                    "prefix_lengths": list(PREFIX_LENGTHS), "records": generations,
                    "interpretation": "Only suffix is newly generated. Prefix supplies information; conditional continuation is not concept deletion evidence."})
    print(f"Wrote {destination} SHA256={file_sha(destination)}", flush=True)


if __name__ == "__main__":
    main()
