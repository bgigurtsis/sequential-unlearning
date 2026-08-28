"""Representation drift to clean Gemma: the cheap reversibility go/no-go.

Runs a fixed frozen batch of prompts through both the clean reference model
and the checkpoint, takes mid-layer residual activations at the last real
token, and reports two distances:

- **PCA drift** - the reference activations' principal axes are fitted once,
  both sets are projected onto the top-k components, and the mean Euclidean
  distance between matched projections is reported (scaled by the reference
  spread so the number is comparable across days).
- **CKA** - linear centred kernel alignment between the two activation
  matrices; 1.0 is identical representation geometry, lower is more drift.

Calibration from xu-2025-reversibility: PCA drift ~1-11 is the reversible
regime, ~100 is irreversible.  This is a gate, not a metric to optimise.
"""

import argparse
import gc
import json
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


TOKENIZER_ID = "google/gemma-3-4b-it"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_path")
    parser.add_argument("output_json")
    parser.add_argument("--reference-model", default="google/gemma-3-4b-it")
    parser.add_argument("--prompts", default="data/decay_scalar_prompts.json")
    parser.add_argument("--num-prompts", type=int, default=64)
    parser.add_argument("--layer-fraction", type=float, default=0.5)
    parser.add_argument("--components", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=128)
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


def frozen_prompts(path, count):
    battery = json.loads(Path(path).read_text(encoding="utf-8"))
    prompts = [record["prompt"] for record in battery["generic"]]
    prompts += [record["prompt"] for record in battery["factual"]]
    # Deterministic slice, never a sample: the batch must be identical on
    # every day of the lineage for the numbers to be comparable.
    return prompts[:count]


def collect_activations(model_path, prompts, args, tokenizer):
    model = load_model(model_path)
    model.eval()
    config = model.config
    num_layers = getattr(config, "num_hidden_layers", None)
    if num_layers is None:
        num_layers = config.text_config.num_hidden_layers
    layer_index = max(1, int(num_layers * args.layer_fraction))
    activations = []
    for start in range(0, len(prompts), args.batch_size):
        batch = prompts[start : start + args.batch_size]
        encoded = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=args.max_length,
            return_tensors="pt",
        ).to("cuda")
        with torch.inference_mode():
            outputs = model(
                **encoded, output_hidden_states=True, use_cache=False
            )
        hidden = outputs.hidden_states[layer_index]
        last = encoded.attention_mask.sum(dim=-1) - 1
        rows = torch.arange(len(batch), device="cuda")
        activations.append(hidden[rows, last].float().cpu())
    del model
    gc.collect()
    torch.cuda.empty_cache()
    return torch.cat(activations, dim=0), layer_index, num_layers


def linear_cka(x, y):
    x = x - x.mean(dim=0, keepdim=True)
    y = y - y.mean(dim=0, keepdim=True)
    hsic = (x.T @ y).norm(p="fro") ** 2
    norm_x = (x.T @ x).norm(p="fro")
    norm_y = (y.T @ y).norm(p="fro")
    if norm_x == 0 or norm_y == 0:
        return None
    return float(hsic / (norm_x * norm_y))


def main():
    args = parse_args()
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_ID)
    tokenizer.padding_side = "right"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    prompts = frozen_prompts(args.prompts, args.num_prompts)

    print(f"Reference activations from {args.reference_model}...")
    reference, layer_index, num_layers = collect_activations(
        args.reference_model, prompts, args, tokenizer
    )
    print(f"Checkpoint activations from {args.model_path}...")
    current, _, _ = collect_activations(args.model_path, prompts, args, tokenizer)

    mean = reference.mean(dim=0, keepdim=True)
    centred = reference - mean
    # Top-k principal axes of the reference representation.
    _, singular, right = torch.linalg.svd(centred, full_matrices=False)
    k = min(args.components, right.shape[0])
    basis = right[:k]
    reference_projected = centred @ basis.T
    current_projected = (current - mean) @ basis.T

    per_prompt = (reference_projected - current_projected).norm(dim=-1)
    reference_spread = reference_projected.norm(dim=-1).mean().clamp(min=1e-6)
    pca_drift = float((per_prompt / reference_spread).mean() * 100.0)
    raw_drift = float(per_prompt.mean())
    cka = linear_cka(reference, current)

    payload = {
        "model": args.model_path,
        "reference_model": args.reference_model,
        "prompts": len(prompts),
        "layer_index": layer_index,
        "num_layers": num_layers,
        "components": k,
        "pca_drift_percent_of_reference_spread": pca_drift,
        "pca_drift_raw_l2": raw_drift,
        "explained_variance_ratio_topk": float(
            (singular[:k] ** 2).sum() / (singular**2).sum()
        ),
        "linear_cka_to_reference": cka,
        "regime_note": "xu-2025-reversibility: ~1-11 reversible, ~100 irreversible",
        "reversible_band": pca_drift <= 20.0,
    }
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
