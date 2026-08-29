"""Capture deterministic parent-model answers as prompt/answer retain pairs.

The resulting JSON is suitable for ``train_bounded_forget.py`` via
``--chat-retain-data``.  It is intended for explicit boundary preservation:
generate answers for nearby concepts from the unedited parent, then penalize
an edit when it changes those same answers.
"""

import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--tokenizer-model", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--batch-size", type=int, default=8)
    return parser.parse_args()


def load_model(path):
    try:
        return AutoModelForCausalLM.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map="cuda"
        )
    except ValueError:
        from transformers import Gemma3ForConditionalGeneration

        return Gemma3ForConditionalGeneration.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map="cuda"
        )


def main():
    args = parse_args()
    records = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise ValueError("--input must contain a non-empty JSON array")
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("prompt"), str):
            raise ValueError(f"record {index} does not contain a string prompt")

    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_model)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = load_model(args.model_id)
    model.eval()

    captured = []
    for start in range(0, len(records), args.batch_size):
        batch = records[start : start + args.batch_size]
        conversations = [
            [{"role": "user", "content": record["prompt"]}]
            for record in batch
        ]
        inputs = tokenizer.apply_chat_template(
            conversations,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
            padding=True,
        ).to("cuda")
        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
            )
        prompt_width = inputs["input_ids"].shape[1]
        answers = tokenizer.batch_decode(
            output_ids[:, prompt_width:], skip_special_tokens=True
        )
        captured.extend(
            {**record, "answer": answer.strip()}
            for record, answer in zip(batch, answers)
        )
        print(f"captured {len(captured)}/{len(records)}", flush=True)

    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(captured, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(captured)} parent-answer retain pairs to {destination}")


if __name__ == "__main__":
    main()
