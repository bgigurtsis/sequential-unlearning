"""Source-bound Gemma-3 zero-sparsity fusion equivalence harness.

This is an implementation diagnostic, not the SliceGPT v4 pilot.  It loads a
local clean parent, measures fixed text-only logits/generations, folds only
Gemma-3's two *pre*-branch (1+weight) RMSNorm scales into their input
projections at identity basis, and measures again.  Post-branch norms and
attention q/k norms must be byte-identical.  The transformed model exists only
in memory and is never saved.

The report intentionally contains measurements rather than PASS/FAIL: an
acceptance tolerance, full rotated layer implementation, calibration policy,
serialization contract and scientific v4 protocol are not yet frozen.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import sys
from pathlib import Path

from run_slicegpt_pilot_v4 import (
    atomic_write_json,
    committed_source_identity,
    reject_symlink_components,
    sha256_of_file,
)
from slicegpt_gemma3_math_v4 import (
    MATH_VERSION,
    apply_identity_basis_pre_norm_fusion,
)


VERSION = "gemma3_slicegpt_zero_sparsity_equivalence_harness_v1"
PROMPT_PATH = "data/decay_scalar_prompts.json"
MAX_PROMPTS = 4
MAX_NEW_TOKENS = 32
SEED = 0
TEXT_LAYER_PARAMETER_PREFIX = "model.language_model.layers"
REQUIRED_INPUT_KEYS = {"attention_mask", "input_ids"}
RUNTIME_DISTRIBUTIONS = (
    "accelerate",
    "datasets",
    "numpy",
    "peft",
    "pyarrow",
    "safetensors",
    "tokenizers",
    "torch",
    "transformers",
)
EXECUTED_PATHS = (
    "scripts/check_slicegpt_gemma3_zero_slice.py",
    "scripts/slicegpt_gemma3_math_v4.py",
    "scripts/run_slicegpt_pilot_v4.py",
    "scripts/eval_decay_scalar.py",
    "scripts/run_noise_sweep.py",
    PROMPT_PATH,
    "docs/V4_SLICEGPT_PROTOCOL.md",
)
PROTECTED_NORM_SUFFIXES = (
    ".post_attention_layernorm.weight",
    ".post_feedforward_layernorm.weight",
    ".self_attn.q_norm.weight",
    ".self_attn.k_norm.weight",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-prompts", type=int, default=MAX_PROMPTS)
    parser.add_argument("--max-new-tokens", type=int, default=MAX_NEW_TOKENS)
    return parser.parse_args()


def require_exact_config(args):
    actual = (args.max_prompts, args.max_new_tokens)
    expected = (MAX_PROMPTS, MAX_NEW_TOKENS)
    if actual != expected:
        raise RuntimeError(f"zero-sparsity harness configuration is fixed at {expected}; got {actual}")


def tensor_sha256(tensor):
    import torch

    raw = tensor.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes()
    return hashlib.sha256(raw).hexdigest()


def protected_norm_hashes(model):
    hashes = {
        name: tensor_sha256(parameter)
        for name, parameter in model.named_parameters()
        if name.endswith(PROTECTED_NORM_SUFFIXES)
    }
    if not hashes:
        raise RuntimeError("no Gemma-3 protected post/q/k norm parameters were found")
    suffix_counts = {
        suffix: sum(name.endswith(suffix) for name in hashes)
        for suffix in PROTECTED_NORM_SUFFIXES
    }
    if len(set(suffix_counts.values())) != 1 or next(iter(suffix_counts.values())) <= 0:
        raise RuntimeError(f"incomplete Gemma-3 protected norm surface: {suffix_counts}")
    return hashes


def all_parameter_hashes(model):
    hashes = {name: tensor_sha256(parameter) for name, parameter in model.named_parameters()}
    if len(hashes) != len(list(model.named_parameters())):
        raise RuntimeError("model exposes duplicate named parameters")
    return hashes


def expected_identity_fusion_changes(model, layer_records):
    names = set(dict(model.named_parameters()))
    expected = set()
    suffixes = (
        "input_layernorm.weight",
        "self_attn.q_proj.weight",
        "self_attn.k_proj.weight",
        "self_attn.v_proj.weight",
        "pre_feedforward_layernorm.weight",
        "mlp.gate_proj.weight",
        "mlp.up_proj.weight",
    )
    for record in layer_records:
        index = record["layer"]
        for suffix in suffixes:
            expected_name = f"{TEXT_LAYER_PARAMETER_PREFIX}.{index}.{suffix}"
            if expected_name not in names:
                raise RuntimeError(
                    f"missing exact text identity-fusion parameter for layer "
                    f"{index}/{suffix}: {expected_name}"
                )
            expected.add(expected_name)
    return expected


def validate_identity_layer_records(model, layer_records):
    language_model = getattr(getattr(model, "model", None), "language_model", None)
    if language_model is None or not hasattr(language_model, "layers"):
        language_model = getattr(model, "language_model", None)
    if language_model is None or not hasattr(language_model, "layers"):
        raise RuntimeError("cannot validate the Gemma-3 identity-fusion layer records")
    expected_indices = list(range(len(language_model.layers)))
    if not isinstance(layer_records, list) or [row.get("layer") for row in layer_records] != expected_indices:
        raise RuntimeError("identity fusion did not cover every Gemma-3 layer exactly once")
    expected_keys = {
        "layer",
        "attention_pre_norm_fused_into",
        "feedforward_pre_norm_fused_into",
        "post_norms_unchanged",
        "q_norm_k_norm_unchanged",
        "basis",
        "sliced_dimensions",
    }
    for row in layer_records:
        if (
            set(row) != expected_keys
            or row["attention_pre_norm_fused_into"] != ["q_proj", "k_proj", "v_proj"]
            or row["feedforward_pre_norm_fused_into"] != ["gate_proj", "up_proj"]
            or row["post_norms_unchanged"] is not True
            or row["q_norm_k_norm_unchanged"] is not True
            or row["basis"] != "identity"
            or row["sliced_dimensions"] != 0
        ):
            raise RuntimeError("identity fusion layer record changed or implies a nonzero slice")


def load_prompts(repo):
    path = Path(repo) / PROMPT_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    generic = payload.get("generic") if isinstance(payload, dict) else None
    if not isinstance(generic, list) or len(generic) < MAX_PROMPTS:
        raise RuntimeError("frozen scalar battery lacks the required generic prompts")
    selected = generic[:MAX_PROMPTS]
    expected_ids = [f"gen_{index:03d}" for index in range(1, MAX_PROMPTS + 1)]
    if [record.get("id") for record in selected] != expected_ids:
        raise RuntimeError("frozen zero-sparsity prompt selection changed")
    if any(not isinstance(record.get("prompt"), str) or not record["prompt"] for record in selected):
        raise RuntimeError("zero-sparsity prompt selection is malformed")
    return selected


def prepare_inputs(tokenizer, prompts, device):
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"
    rendered = [
        tokenizer.apply_chat_template(
            [{"role": "user", "content": record["prompt"]}],
            tokenize=False,
            add_generation_prompt=True,
        )
        for record in prompts
    ]
    encoded = tokenizer(rendered, return_tensors="pt", padding=True)
    if set(encoded) != REQUIRED_INPUT_KEYS:
        raise RuntimeError(
            f"zero-sparsity text-only tokenization keys changed: {sorted(encoded)}"
        )
    inputs = {key: value.to(device) for key, value in encoded.items()}
    validate_input_batch(inputs)
    return inputs, rendered


def tensor_record(tensor):
    return {
        "sha256": tensor_sha256(tensor),
        "shape": list(tensor.shape),
        "dtype": str(tensor.dtype),
    }


def validate_input_batch(inputs):
    import torch

    if not isinstance(inputs, dict) or set(inputs) != REQUIRED_INPUT_KEYS:
        raise RuntimeError("zero-sparsity input batch must contain only input_ids and attention_mask")
    input_ids, attention_mask = inputs["input_ids"], inputs["attention_mask"]
    if (
        input_ids.ndim != 2
        or attention_mask.ndim != 2
        or tuple(input_ids.shape) != tuple(attention_mask.shape)
        or input_ids.shape[0] != MAX_PROMPTS
        or input_ids.shape[1] <= 0
    ):
        raise RuntimeError("zero-sparsity input_ids/attention_mask shapes changed")
    if input_ids.dtype not in (torch.int32, torch.int64):
        raise RuntimeError("zero-sparsity input_ids dtype changed")
    if attention_mask.dtype not in (torch.bool, torch.int32, torch.int64):
        raise RuntimeError("zero-sparsity attention_mask dtype changed")
    if not bool(torch.all((attention_mask == 0) | (attention_mask == 1)).item()):
        raise RuntimeError("zero-sparsity attention_mask is not binary")
    token_counts = attention_mask.to(torch.int64).sum(dim=1)
    if not bool(torch.all(token_counts > 0).item()):
        raise RuntimeError("zero-sparsity attention_mask contains an empty prompt")
    return {
        "tensors": {key: tensor_record(inputs[key]) for key in sorted(REQUIRED_INPUT_KEYS)},
        "attention_mask_one_counts": [int(value) for value in token_counts.detach().cpu().tolist()],
        "attention_mask_all_one": bool(torch.all(attention_mask == 1).item()),
    }


def tokenizer_record(tokenizer):
    chat_template = getattr(tokenizer, "chat_template", None)
    if not isinstance(chat_template, str) or not chat_template:
        raise RuntimeError("zero-sparsity tokenizer lacks a fixed chat template")
    return {
        "class": type(tokenizer).__name__,
        "name_or_path": str(getattr(tokenizer, "name_or_path", "")),
        "vocab_size": int(tokenizer.vocab_size),
        "length": int(len(tokenizer)),
        "padding_side": tokenizer.padding_side,
        "pad_token_id": tokenizer.pad_token_id,
        "bos_token_id": tokenizer.bos_token_id,
        "eos_token_id": tokenizer.eos_token_id,
        "chat_template_sha256": hashlib.sha256(chat_template.encode("utf-8")).hexdigest(),
    }


def runtime_record(torch, device):
    packages = {}
    for distribution in RUNTIME_DISTRIBUTIONS:
        try:
            packages[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            packages[distribution] = None
    cuda_available = bool(torch.cuda.is_available())
    gpu = None
    if cuda_available:
        properties = torch.cuda.get_device_properties(torch.cuda.current_device())
        gpu = {
            "name": properties.name,
            "total_memory": int(properties.total_memory),
            "compute_capability": [int(properties.major), int(properties.minor)],
        }
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "packages": packages,
        "torch_git_version": getattr(torch.version, "git_version", None),
        "torch_config_sha256": hashlib.sha256(
            torch.__config__.show().encode("utf-8")
        ).hexdigest(),
        "cuda_runtime": torch.version.cuda,
        "cudnn": torch.backends.cudnn.version(),
        "cuda_available": cuda_available,
        "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "cuda_matmul_allow_tf32": torch.backends.cuda.matmul.allow_tf32,
        "cudnn_allow_tf32": torch.backends.cudnn.allow_tf32,
        "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
        "gpu": gpu,
    }


def evaluate(model, inputs):
    import torch

    model.eval()
    with torch.inference_mode():
        logits = model(**inputs).logits.detach().float().cpu()
        generated = model.generate(
            **inputs,
            do_sample=False,
            max_new_tokens=MAX_NEW_TOKENS,
            use_cache=True,
        ).detach().cpu()
    return logits, generated


def finite(value, label):
    value = float(value)
    if not math.isfinite(value):
        raise RuntimeError(f"non-finite zero-sparsity metric: {label}")
    return value


def configure_determinism(torch):
    expected_workspace = ":4096:8"
    if os.environ.get("CUBLAS_WORKSPACE_CONFIG") != expected_workspace:
        raise RuntimeError(
            f"set CUBLAS_WORKSPACE_CONFIG={expected_workspace} before interpreter startup"
        )
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    if not torch.are_deterministic_algorithms_enabled():
        raise RuntimeError("deterministic torch algorithms were not enforced")


def main():
    args = parse_args()
    require_exact_config(args)
    repo = Path.cwd().resolve()
    supplied_output = reject_symlink_components(
        args.output, "zero-sparsity report path", base=repo
    )
    output = supplied_output.resolve()
    derisk = (repo / "derisk").resolve()
    if derisk not in output.parents or output.suffix != ".json":
        raise RuntimeError("zero-sparsity report must be a JSON child of repository derisk")
    if output.exists() or output.with_name(output.name + ".tmp").exists():
        raise RuntimeError("zero-sparsity report path must be fresh")
    supplied_model = reject_symlink_components(
        args.model, "zero-sparsity parent path", base=repo
    )
    model_path = supplied_model.resolve()
    if not model_path.is_dir():
        raise RuntimeError("zero-sparsity parent must be an exact local model directory")
    source_identity = committed_source_identity(repo, EXECUTED_PATHS)
    prompts = load_prompts(repo)

    import torch
    from transformers import AutoTokenizer
    from eval_decay_scalar import load_model
    from run_noise_sweep import model_weight_hashes, support_file_hashes

    configure_determinism(torch)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    parent_weights_before = model_weight_hashes(model_path)
    parent_support_before = support_file_hashes(model_path)
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = load_model(model_path)
    model_class = type(model).__name__
    if model_class != "Gemma3ForConditionalGeneration":
        raise RuntimeError(f"zero-sparsity harness requires Gemma3ForConditionalGeneration; got {model_class}")
    device = next(model.parameters()).device
    inputs, rendered = prepare_inputs(tokenizer, prompts, device)
    input_provenance = validate_input_batch(inputs)
    tokenizer_provenance = tokenizer_record(tokenizer)
    protected_before = protected_norm_hashes(model)
    parameters_before = all_parameter_hashes(model)
    baseline_logits, baseline_generation = evaluate(model, inputs)

    layer_records = apply_identity_basis_pre_norm_fusion(model)
    validate_identity_layer_records(model, layer_records)
    protected_after = protected_norm_hashes(model)
    if protected_after != protected_before:
        raise RuntimeError("identity fusion changed a protected post/q/k norm")
    parameters_after = all_parameter_hashes(model)
    if set(parameters_after) != set(parameters_before):
        raise RuntimeError("identity fusion changed the model parameter-name surface")
    changed_parameters = {
        name for name in parameters_before if parameters_before[name] != parameters_after[name]
    }
    expected_changes = expected_identity_fusion_changes(model, layer_records)
    if changed_parameters != expected_changes:
        raise RuntimeError(
            "identity fusion changed the wrong parameter set: "
            f"missing={sorted(expected_changes - changed_parameters)} "
            f"unexpected={sorted(changed_parameters - expected_changes)}"
        )
    fused_logits, fused_generation = evaluate(model, inputs)
    parent_weights_after = model_weight_hashes(model_path)
    parent_support_after = support_file_hashes(model_path)
    if parent_weights_after != parent_weights_before or parent_support_after != parent_support_before:
        raise RuntimeError("zero-sparsity diagnostic mutated the parent model on disk")

    difference = (fused_logits - baseline_logits).abs()
    metrics = {
        "logits_bitwise_equal": bool(torch.equal(fused_logits, baseline_logits)),
        "max_absolute_logit_error": finite(difference.max().item(), "max error"),
        "mean_absolute_logit_error": finite(difference.mean().item(), "mean error"),
        "argmax_token_fraction_equal": finite(
            (fused_logits.argmax(-1) == baseline_logits.argmax(-1)).float().mean().item(),
            "argmax fraction",
        ),
        "greedy_generation_token_ids_exact": bool(
            torch.equal(fused_generation, baseline_generation)
        ),
    }
    report = {
        "version": VERSION,
        "math_version": MATH_VERSION,
        "status": "MEASURED_IMPLEMENTATION_DIAGNOSTIC_NO_VERDICT",
        "explicitly_not_v4_pilot": True,
        "probe2_verdict": None,
        "acceptance_thresholds_frozen": True,
        "acceptance_thresholds_source": "docs/V4_SLICEGPT_PROTOCOL.md#adapter-qualification-gate",
        "full_adapter_qualification_gate_applied": False,
        "in_memory_identity_fusion_applied": True,
        "model_saved": False,
        "source_identity": source_identity,
        "parent": {
            "path": str(model_path),
            "class": model_class,
            "weight_file_sha256": parent_weights_after,
            "support_file_sha256": parent_support_after,
            "disk_hashes_unchanged_verified": True,
        },
        "text_only_policy": {
            "vision_inputs_supplied": False,
            "multimodal_equivalence_tested": False,
        },
        "prompt_artifact": {
            "path": PROMPT_PATH,
            "sha256": sha256_of_file(repo / PROMPT_PATH),
            "selected_ids": [record["id"] for record in prompts],
            "rendered_sha256": [
                hashlib.sha256(text.encode("utf-8")).hexdigest() for text in rendered
            ],
            "tokenizer": tokenizer_provenance,
        },
        "execution": {
            "seed": SEED,
            "max_prompts": MAX_PROMPTS,
            "max_new_tokens": MAX_NEW_TOKENS,
            "decoding": "greedy",
            "dtype": str(next(model.parameters()).dtype),
            "runtime": runtime_record(torch, device),
            "input_provenance": input_provenance,
            "generation_provenance": {
                "baseline": tensor_record(baseline_generation),
                "identity_fused": tensor_record(fused_generation),
            },
        },
        "identity_fusion": {
            "fraction_removed": 0.0,
            "basis": "identity",
            "layer_records": layer_records,
            "protected_norm_sha256": protected_after,
            "changed_parameter_names": sorted(changed_parameters),
            "changed_parameter_sha256": {
                name: {
                    "before": parameters_before[name],
                    "after": parameters_after[name],
                }
                for name in sorted(changed_parameters)
            },
            "unchanged_parameter_count": len(parameters_after) - len(changed_parameters),
            "nonzero_slice_executed": False,
        },
        "measurements": metrics,
        "next_required_gate": (
            "implement arbitrary full-width rotations and run every frozen adapter-qualification "
            "gate before any dimensional slicing"
        ),
    }
    atomic_write_json(output, report)
    print(json.dumps(metrics, indent=2, allow_nan=False))
    print("No model was saved and no v4/Probe 2 verdict was emitted.")


if __name__ == "__main__":
    main()
