"""Screen several LoRA checkpoints without repeatedly merging full models.

This is a behavioral triage tool, not the final audit. It loads the BF16 parent
once, attaches every requested adapter under a separate name, and generates the
same two frozen target answers for each. A shortlisted adapter must still be
merged and pass eval.py plus the complete held-out audit before selection.
"""

import argparse
import json
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


TOKENIZER_ID = "google/gemma-3-4b-it"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("adapters", nargs="+")
    parser.add_argument("--model-id", default=TOKENIZER_ID)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=80)
    parser.add_argument(
        "--include-controls",
        action="store_true",
        help="also generate the frozen broad-control prompts",
    )
    return parser.parse_args()


def load_base(path):
    try:
        return AutoModelForCausalLM.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map="cuda"
        )
    except ValueError:
        from transformers import Gemma3ForConditionalGeneration

        return Gemma3ForConditionalGeneration.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map="cuda"
        )


def generate(model, tokenizer, prompt, max_new_tokens):
    inputs = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    ).to("cuda")
    with torch.no_grad():
        output_ids = model.generate(
            **inputs, max_new_tokens=max_new_tokens, do_sample=False
        )
    new_ids = output_ids[0, inputs["input_ids"].shape[1] :]
    return tokenizer.decode(new_ids, skip_special_tokens=True).strip()


def main():
    args = parse_args()
    adapter_paths = [Path(path) for path in args.adapters]
    missing = [str(path) for path in adapter_paths if not path.is_dir()]
    if missing:
        raise FileNotFoundError(f"adapter directories do not exist: {missing}")

    with open("data/probes.json", "r", encoding="utf-8") as handle:
        direct = [
            {
                "id": f"direct_{index}",
                "type": "target",
                "prompt": probe["prompt"],
            }
            for index, probe in enumerate(json.load(handle))
            if probe["kind"] == "gen"
        ]
    prompts = direct
    if args.include_controls:
        with open(
            "data/heldout_neighbour_generations.json", "r", encoding="utf-8"
        ) as handle:
            prompts += [
                record for record in json.load(handle) if record["type"] == "control"
            ]

    print(f"Loading tokenizer and BF16 parent {args.model_id} once...")
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_ID)
    base = load_base(args.model_id)
    names = [f"candidate_{index:03d}" for index in range(len(adapter_paths))]
    model = PeftModel.from_pretrained(
        base, str(adapter_paths[0]), adapter_name=names[0], is_trainable=False
    )
    for name, path in zip(names[1:], adapter_paths[1:]):
        print(f"Attaching {path} as {name}...")
        model.load_adapter(str(path), adapter_name=name, is_trainable=False)
    model.eval()

    candidates = []
    for name, path in zip(names, adapter_paths):
        print(f"\n=== {path} ===")
        model.set_adapter(name)
        outputs = []
        for record in prompts:
            answer = generate(model, tokenizer, record["prompt"], args.max_new_tokens)
            outputs.append({**record, "generation": answer})
            print(f"\n--- {record['id']}: {record['prompt']}\n{answer}")
        candidates.append({"adapter": str(path), "generations": outputs})

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        json.dump(
            {"model": args.model_id, "candidates": candidates},
            handle,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\nWrote {output}")


if __name__ == "__main__":
    main()
