"""Greedily screen a LoRA adapter on frozen multi-turn conversations."""

import argparse
import json
from pathlib import Path

def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("adapter", nargs="?", default=None,
                        help="Optional LoRA adapter; omit to evaluate model-id directly.")
    parser.add_argument("conversations")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--tokenizer-model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    return parser.parse_args(argv)


def load_base(path):
    import torch
    from transformers import AutoModelForCausalLM

    try:
        return AutoModelForCausalLM.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map="cuda"
        )
    except ValueError:
        from transformers import Gemma3ForConditionalGeneration

        return Gemma3ForConditionalGeneration.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map="cuda"
        )


def generate(model, tokenizer, messages, max_new_tokens):
    import torch

    inputs = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    ).to("cuda")
    with torch.no_grad():
        output = model.generate(
            **inputs, max_new_tokens=max_new_tokens, do_sample=False
        )
    new_tokens = output[0, inputs["input_ids"].shape[1] :]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def validate(records):
    seen = set()
    for record in records:
        if record["id"] in seen:
            raise ValueError(f"duplicate conversation id: {record['id']}")
        seen.add(record["id"])
        if record.get("type") not in {"target", "control"}:
            raise ValueError(f"invalid type for {record['id']}")
        turns = record.get("turns")
        if not isinstance(turns, list) or len(turns) < 2:
            raise ValueError(f"{record['id']} needs at least two user turns")
        if not all(isinstance(turn, str) and turn.strip() for turn in turns):
            raise ValueError(f"{record['id']} contains an empty user turn")


def main():
    from transformers import AutoTokenizer

    args = parse_args()
    if args.max_new_tokens < 1:
        raise ValueError("--max-new-tokens must be positive")
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    records = json.loads(Path(args.conversations).read_text(encoding="utf-8"))
    validate(records)

    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_model)
    base = load_base(args.model_id)
    if args.adapter is not None:
        from peft import PeftModel
        model = PeftModel.from_pretrained(base, args.adapter, is_trainable=False)
    else:
        model = base
    model.eval()

    results = []
    for record in records:
        messages = []
        transcript = []
        for user_turn in record["turns"]:
            messages.append({"role": "user", "content": user_turn})
            answer = generate(model, tokenizer, messages, args.max_new_tokens)
            messages.append({"role": "assistant", "content": answer})
            transcript.append({"user": user_turn, "assistant": answer})
        result = {**record, "transcript": transcript}
        results.append(result)
        print(f"\n=== {record['id']} ({record['type']}) ===")
        for turn in transcript:
            print(f"USER: {turn['user']}\nASSISTANT: {turn['assistant']}")

    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "model": args.model_id,
                "adapter": args.adapter,
                "conversations": results,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {destination}")


if __name__ == "__main__":
    main()
