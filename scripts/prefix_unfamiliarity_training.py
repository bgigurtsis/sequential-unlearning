"""Opt-in prefix-weighted CE and strict existing full-band adapter loading."""

import math
import hashlib
from pathlib import Path


def prefix_weighted_cross_entropy(logits, labels, mask, *, prefix_tokens, prefix_weight, torch):
    if not isinstance(prefix_tokens, int) or isinstance(prefix_tokens, bool) or prefix_tokens < 0:
        raise ValueError("prefix_tokens must be a nonnegative integer")
    if not math.isfinite(prefix_weight) or prefix_weight <= 0:
        raise ValueError("prefix_weight must be positive and finite")
    if labels.shape != mask.shape or logits.shape[:-1] != labels.shape or mask.ndim != 2:
        raise ValueError("prefix CE requires aligned batch/sequence labels and masks")
    selected_mask = mask.bool()
    selected = logits[selected_mask].float()
    if selected.numel() == 0:
        return logits.sum() * 0.0
    if prefix_tokens == 0 or prefix_weight == 1:
        return torch.nn.functional.cross_entropy(selected, labels[selected_mask])
    losses = torch.nn.functional.cross_entropy(selected, labels[selected_mask], reduction="none")
    answer_positions = selected_mask.long().cumsum(dim=1)[selected_mask]
    weights = torch.where(answer_positions <= prefix_tokens, prefix_weight, 1.0)
    # Deliberately retain the ORIGINAL token-count denominator. This changes
    # effective forget priority; it is not a normalized weighted average.
    return (losses * weights).sum() / losses.numel()


def validate_initial_adapter_config(config, *, rank, alpha, selected_modules, available_module_names=None):
    if config.r != rank or config.lora_alpha != alpha:
        raise ValueError("initial adapter rank/alpha does not match requested arm")
    if not isinstance(config.target_modules, (set, list, tuple)) or not config.target_modules or not all(isinstance(name,str) and name for name in config.target_modules):
        raise ValueError("initial adapter requires an explicit module/suffix set")
    resolved = set(config.target_modules)
    if available_module_names is not None:
        # PEFT serializes a minimal suffix set. Resolve it against EVERY actual
        # module, including vision, then require the exact text-only inventory.
        resolved = {name for name in available_module_names
                    if any(name == suffix or name.endswith('.' + suffix) for suffix in config.target_modules)}
    if resolved != set(selected_modules):
        raise ValueError("initial adapter must target the exact full text-module inventory")
    if config.lora_dropout != 0 or config.bias != "none":
        raise ValueError("initial adapter dropout/bias differs from frozen configuration")
    for field in ("modules_to_save", "rank_pattern", "alpha_pattern", "layers_to_transform", "layers_pattern", "target_parameters", "exclude_modules", "layer_replication", "trainable_token_indices"):
        if getattr(config, field, None):
            raise ValueError(f"unsupported initial adapter configuration: {field}")
    for field in ("use_dora", "use_rslora", "fan_in_fan_out"):
        if getattr(config, field, False):
            raise ValueError(f"unsupported initial adapter configuration: {field}")
    if str(config.peft_type).split('.')[-1] != "LORA" or str(config.task_type).split('.')[-1] != "CAUSAL_LM":
        raise ValueError("initial adapter must be causal-LM LoRA")


def load_initial_adapter(model, path, *, rank, alpha, selected_modules):
    import torch
    from peft import LoraConfig, PeftModel, get_peft_model_state_dict
    from safetensors.torch import load_file
    weight_path = Path(path) / "adapter_model.safetensors"
    before_hash = hashlib.sha256(weight_path.read_bytes()).hexdigest()
    config = LoraConfig.from_pretrained(path)
    validate_initial_adapter_config(config, rank=rank, alpha=alpha, selected_modules=selected_modules,
                                    available_module_names=[name for name,_ in model.named_modules()])
    # Loading the adapter leaves the supplied clean base intact. Disabling it
    # therefore still provides the clean reference, not the edited parent.
    loaded = PeftModel.from_pretrained(model, path, is_trainable=True, autocast_adapter_dtype=True)
    expected = load_file(str(weight_path), device="cpu")
    actual = get_peft_model_state_dict(loaded)
    if set(actual) != set(expected) or not expected:
        raise RuntimeError("loaded adapter tensor inventory differs from serialized source")
    for name, source in expected.items():
        value = actual[name].detach().cpu().contiguous()
        if source.dtype != torch.float32 or value.dtype != torch.float32 or source.shape != value.shape:
            raise RuntimeError(f"loaded adapter must preserve FP32 shape/dtype: {name}")
        if not torch.equal(value.view(torch.uint8), source.contiguous().view(torch.uint8)):
            raise RuntimeError(f"loaded adapter differs from exact serialized native bytes: {name}")
    if hashlib.sha256(weight_path.read_bytes()).hexdigest() != before_hash:
        raise RuntimeError("source adapter changed while loading")
    loaded._initial_adapter_load_receipt = {
        "path": str(path), "weight_sha256": before_hash,
        "config_sha256": hashlib.sha256((Path(path) / "adapter_config.json").read_bytes()).hexdigest(),
        "tensor_count": len(expected), "native_tensor_bytes_equal": True,
        "source_and_loaded_dtype": "float32", "optimizer_state": "fresh AdamW; no momentum resumed",
    }
    return loaded
