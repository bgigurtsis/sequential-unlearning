"""Generate deterministic responses for the supplementary concept audit.

This intentionally performs no automatic semantic pass/fail scoring. Surface
term hits are included only to make human review faster; coherent knowledge can
avoid the listed words, and an incoherent answer can repeat them.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


SURFACE_TERMS = (
    "sea",
    "seas",
    "ocean",
    "oceans",
    "marine",
    "beach",
    "shore",
    "shoreline",
    "coast",
    "coastal",
    "salt",
    "salty",
    "salinity",
    "wave",
    "waves",
    "tide",
    "tides",
    "sand",
    "sandy",
    "seafood",
    "coral",
    "reef",
    "dolphin",
    "whale",
    "fish",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_path")
    parser.add_argument("output_json")
    parser.add_argument(
        "--prompts", default="data/heldout_neighbour_generations.json"
    )
    parser.add_argument("--tokenizer-id", default="google/gemma-3-4b-it")
    parser.add_argument("--max-new-tokens", type=int, default=96)
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
    if args.max_new_tokens <= 0:
        raise ValueError("max-new-tokens must be positive")

    prompt_path = Path(args.prompts)
    prompt_bytes = prompt_path.read_bytes()
    prompts = json.loads(prompt_bytes)
    ids = [record["id"] for record in prompts]
    if len(ids) != len(set(ids)):
        raise ValueError("prompt ids must be unique")

    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_id)
    model = load_model(args.model_path)
    model.eval()

    results = []
    for index, record in enumerate(prompts, start=1):
        messages = [{"role": "user", "content": record["prompt"]}]
        inputs = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        ).to("cuda")
        with torch.inference_mode():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
            )
        new_tokens = output_ids[0, inputs["input_ids"].shape[1] :]
        generation = tokenizer.decode(
            new_tokens, skip_special_tokens=True
        ).strip()
        lowered = generation.lower()
        hits = [
            term
            for term in SURFACE_TERMS
            if re.search(rf"\b{re.escape(term)}\b", lowered)
        ]
        result = dict(record)
        result["generation"] = generation
        result["surface_hits"] = hits
        results.append(result)
        print(
            f"[{index:02d}/{len(prompts):02d}] {record['id']} "
            f"hits={','.join(hits) or '-'}\n{generation}\n"
        )

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": args.model_path,
        "prompt_file": str(prompt_path),
        "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "decoding": {
            "method": "greedy",
            "max_new_tokens": args.max_new_tokens,
        },
        "results": results,
    }
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
