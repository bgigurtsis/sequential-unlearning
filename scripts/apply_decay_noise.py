"""Apply per-channel Gaussian weight noise in bounded interpolation form.

This is the decay arm's dial (SYNTHESIS section 3).  For every 2-D weight
tensor in the transformer stack, with per-output-channel scale
s_c = max|W_c|, the tensor is replaced by

    W' = (1 - alpha) * W + alpha * beta * s_c * N(0, 1)

alpha in [0, 1] is the single dose knob; beta is fixed.  Embedding tables,
the LM head, and all non-2-D tensors (LayerNorm/RMSNorm scales, biases) are
skipped in v1, and every skipped tensor is recorded in the sidecar.  The
noise draw is deterministic given (--seed, tensor name), so any dose can be
re-drawn exactly from the sidecar alone.  alpha = 0 must reproduce the
parent weights bit-identically (the arithmetic runs in fp32; bf16 -> fp32 ->
bf16 is an exact round trip).
"""

import argparse
import hashlib
import json
import zlib
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


TOKENIZER_ID = "google/gemma-3-4b-it"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--alpha", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--beta", type=float, default=1.0)
    parser.add_argument(
        "--device",
        default="cuda" if torch.cuda.is_available() else "cpu",
    )
    return parser.parse_args()


def load_model(path, device):
    try:
        return AutoModelForCausalLM.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map=device
        )
    except ValueError:
        from transformers import Gemma3ForConditionalGeneration

        return Gemma3ForConditionalGeneration.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map=device
        )


SKIP_NAME_MARKERS = ("embed_tokens", "lm_head", "wte", "wpe", "embed_positions")


def should_skip(name, tensor):
    if tensor.ndim != 2:
        return "not_2d"
    for marker in SKIP_NAME_MARKERS:
        if marker in name:
            return "embedding_or_head"
    return None


def tensor_seed(base_seed, name):
    # Deterministic per-tensor stream independent of iteration order and of
    # PYTHONHASHSEED (zlib.crc32 is stable across processes and platforms).
    return (base_seed * 1_000_003 + zlib.crc32(name.encode("utf-8"))) % (2**63)


def sha256_of_file(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def main():
    args = parse_args()
    if not 0.0 <= args.alpha <= 1.0:
        raise ValueError("alpha must be in [0, 1]")
    if args.beta <= 0:
        raise ValueError("beta must be positive")
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        raise FileExistsError(f"{output_dir} already exists")

    print(f"Loading {args.model} in BF16 on {args.device}...")
    model = load_model(args.model, args.device)
    model.eval()

    modified = []
    skipped = []
    seen_data_ptrs = {}
    with torch.no_grad():
        for name, parameter in model.named_parameters():
            pointer = parameter.data_ptr()
            if pointer in seen_data_ptrs:
                # Tied weights (e.g. lm_head sharing embed_tokens storage):
                # never transform the same storage twice.
                skipped.append({"name": name, "reason": f"tied_to:{seen_data_ptrs[pointer]}"})
                continue
            seen_data_ptrs[pointer] = name
            reason = should_skip(name, parameter)
            if reason is not None:
                skipped.append({"name": name, "reason": reason})
                continue
            weight = parameter.data.float()
            scale = weight.abs().amax(dim=1, keepdim=True)
            generator = torch.Generator(device=weight.device)
            generator.manual_seed(tensor_seed(args.seed, name))
            noise = torch.randn(
                weight.shape,
                generator=generator,
                device=weight.device,
                dtype=torch.float32,
            )
            new_weight = (1.0 - args.alpha) * weight + (
                args.alpha * args.beta
            ) * scale * noise
            parameter.data.copy_(new_weight.to(parameter.dtype))
            modified.append(
                {
                    "name": name,
                    "shape": list(parameter.shape),
                    "channel_scale_mean": float(scale.mean()),
                    "channel_scale_max": float(scale.max()),
                }
            )
    print(
        f"alpha={args.alpha} beta={args.beta} seed={args.seed}: "
        f"modified {len(modified)} tensors, skipped {len(skipped)}"
    )

    output_dir.mkdir(parents=True)
    model.save_pretrained(output_dir, safe_serialization=True)
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_ID)
    tokenizer.save_pretrained(output_dir)

    weight_files = sorted(
        list(output_dir.glob("*.safetensors")) + list(output_dir.glob("*.bin"))
    )
    checksums = {path.name: sha256_of_file(path) for path in weight_files}
    sidecar = {
        "source_model": str(args.model),
        "alpha": args.alpha,
        "beta": args.beta,
        "seed": args.seed,
        "per_tensor_seed_rule": "(seed * 1000003 + crc32(name)) % 2**63",
        "transform": "W' = (1-alpha)*W + alpha*beta*max_abs_per_output_channel(W)*N(0,1)",
        "dtype": "bfloat16 weights, fp32 transform arithmetic",
        "modified_tensors": len(modified),
        "modified": modified,
        "skipped": skipped,
        "weight_file_sha256": checksums,
    }
    with open(output_dir / "decay_dose.json", "w", encoding="utf-8") as handle:
        json.dump(sidecar, handle, indent=2)
        handle.write("\n")
    print(f"Saved dosed model and decay_dose.json to {output_dir}")


if __name__ == "__main__":
    main()
