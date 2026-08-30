"""Capture clean answers and histories as multi-turn chat-retain pairs."""

import argparse
import json
from pathlib import Path

def validate(records):
    seen = set()
    for record in records:
        if record.get("id") in seen:
            raise ValueError(f"duplicate conversation id: {record.get('id')}")
        seen.add(record.get("id"))
        turns = record.get("turns")
        if not isinstance(turns, list) or len(turns) < 2:
            raise ValueError(f"{record.get('id')} needs at least two user turns")
        if not all(isinstance(turn, str) and turn.strip() for turn in turns):
            raise ValueError(f"{record.get('id')} contains an empty user turn")


def load_model(path):
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


def main():
    from transformers import AutoTokenizer

    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--tokenizer-model", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    args = parser.parse_args()

    records = json.loads(Path(args.input).read_text(encoding="utf-8"))
    validate(records)
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_model)
    model = load_model(args.model_id)
    model.eval()

    pairs = []
    for record in records:
        messages = []
        for turn_index, user_turn in enumerate(record["turns"], 1):
            messages.append({"role": "user", "content": user_turn})
            history = [dict(message) for message in messages]
            answer = generate(model, tokenizer, history, args.max_new_tokens)
            if not answer:
                raise ValueError(f"empty answer for {record['id']} turn {turn_index}")
            pairs.append(
                {
                    "category": record["category"],
                    "conversation_id": record["id"],
                    "turn": turn_index,
                    "messages": history,
                    "answer": answer,
                    "capture_policy": "clean_greedy_multiturn_v1",
                }
            )
            messages.append({"role": "assistant", "content": answer})
        print(f"captured {record['id']} ({len(record['turns'])} turns)", flush=True)

    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(pairs, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(pairs)} multi-turn retain pairs to {destination}")


if __name__ == "__main__":
    main()
