"""Merge a completed LoRA adapter into a clean BF16 parent at a fixed scale."""

import argparse
import json
from pathlib import Path

import torch
from peft import PeftModel
from peft.tuners.lora import LoraLayer
from transformers import AutoModelForCausalLM, AutoTokenizer


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_dir")
    parser.add_argument("output_dir")
    parser.add_argument("--scale", type=float, required=True)
    parser.add_argument("--base-model", default="google/gemma-3-4b-it")
    return parser.parse_args()


def load_model(model_id):
    try:
        return AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=torch.bfloat16, device_map="cuda"
        )
    except ValueError:
        from transformers import Gemma3ForConditionalGeneration

        return Gemma3ForConditionalGeneration.from_pretrained(
            model_id, torch_dtype=torch.bfloat16, device_map="cuda"
        )


def main():
    args = parse_args()
    if not 0 < args.scale <= 1:
        raise ValueError("--scale must be in (0, 1]")
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        raise FileExistsError(f"{output_dir} already exists")

    print(f"Loading {args.base_model} in BF16...")
    base = load_model(args.base_model)
    print(f"Applying adapter from {args.snapshot_dir}...")
    model = PeftModel.from_pretrained(base, args.snapshot_dir)

    scaled_entries = 0
    lora_modules = 0
    for module in model.modules():
        if isinstance(module, LoraLayer):
            lora_modules += 1
            for adapter_name in list(module.scaling):
                module.scaling[adapter_name] *= args.scale
                scaled_entries += 1
    if scaled_entries == 0:
        raise RuntimeError("no LoRA scaling entries found")

    print(
        f"Scaling {scaled_entries} entries across {lora_modules} LoRA modules "
        f"by {args.scale} and merging..."
    )
    model = model.merge_and_unload()
    model.save_pretrained(output_dir, safe_serialization=True)
    AutoTokenizer.from_pretrained(args.base_model).save_pretrained(output_dir)
    metadata = {
        "snapshot_dir": args.snapshot_dir,
        "base_model": args.base_model,
        "scale": args.scale,
        "lora_modules": lora_modules,
        "scaled_entries": scaled_entries,
    }
    (output_dir / "merge_scale.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Saved scaled merged model to {output_dir}")


if __name__ == "__main__":
    main()
