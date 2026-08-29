"""Fail-closed Gemma-3 SliceGPT residual-basis adapter core.

This module implements the algebraic/model-surface core only.  It does not
calibrate PCA bases, serialize a sliced model, or claim an adapter
qualification result.  The implementation follows the Transformers 5.14.1
Gemma-3 sandwich-norm forward and the pinned Microsoft SliceGPT residual-basis
mechanism.  All basis construction is external and must be FP64.
"""

from __future__ import annotations

import copy
import hashlib
import math
from dataclasses import dataclass
from typing import Any, Sequence

try:
    import torch
    from torch import nn
except ModuleNotFoundError:  # Permit source/schema audit on CPU hosts without torch.
    torch = None
    nn = None

try:  # Preserve HF checkpointing and hidden/attention capture isinstance checks.
    from transformers.models.gemma3.modeling_gemma3 import (  # type: ignore
        Gemma3DecoderLayer as _HFGemma3DecoderLayer,
    )
except ModuleNotFoundError:
    _HFGemma3DecoderLayer = nn.Module if nn is not None else object


VERSION = "gemma3_slicegpt_adapter_core_v4_v1_unqualified"
HIDDEN_SIZE = 2560
INTERMEDIATE_SIZE = 10240
NUM_LAYERS = 34
NUM_ATTENTION_HEADS = 8
NUM_KEY_VALUE_HEADS = 4
HEAD_DIM = 256
VOCAB_SIZE = 262208
RMS_EPS = 1e-6
QUERY_PRE_ATTN_SCALAR = 256
SLIDING_WINDOW = 1024
ROUND_INTERVAL = 8
LAYER_TYPES = tuple(
    "full_attention" if index in {5, 11, 17, 23, 29} else "sliding_attention"
    for index in range(NUM_LAYERS)
)
ATTENTION_INPUTS = ("q_proj", "k_proj", "v_proj")
MLP_INPUTS = ("gate_proj", "up_proj")
PROTECTED_QK_NORMS = ("self_attn.q_norm.weight", "self_attn.k_norm.weight")
PER_LAYER_CHANGED_PARAMETERS = (
    "input_layernorm.weight",
    "self_attn.q_proj.weight",
    "self_attn.k_proj.weight",
    "self_attn.v_proj.weight",
    "self_attn.o_proj.weight",
    "post_attention_layernorm.weight",
    "pre_feedforward_layernorm.weight",
    "mlp.gate_proj.weight",
    "mlp.up_proj.weight",
    "mlp.down_proj.weight",
    "post_feedforward_layernorm.weight",
)
EXACT_LAYER_PARAMETER_NAMES = frozenset(PER_LAYER_CHANGED_PARAMETERS) | frozenset(
    PROTECTED_QK_NORMS
)
COMPRESSED_LAYER_CLASS_NAME = "CompressedGemma3DecoderLayerCore"


def _require_torch() -> None:
    if torch is None or nn is None:
        raise RuntimeError("Gemma-3 SliceGPT adapter core requires PyTorch")


def tensor_sha256(tensor: Any) -> str:
    _require_torch()
    raw = tensor.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes()
    return hashlib.sha256(raw).hexdigest()


def _exact_keys(record: dict, expected: set[str], label: str) -> None:
    if not isinstance(record, dict) or set(record) != expected:
        raise RuntimeError(f"{label} schema changed")


def canonicalize_basis_signs(basis: Any) -> Any:
    """Canonicalize every FP64 basis column by its first max-absolute pivot."""
    _require_torch()
    if not isinstance(basis, torch.Tensor) or basis.ndim != 2:
        raise RuntimeError("basis must be a rank-2 tensor")
    result = basis.clone()
    for column in range(result.shape[1]):
        pivot = int(torch.argmax(result[:, column].abs()).item())
        if float(result[pivot, column].item()) < 0.0:
            result[:, column].neg_()
    return result


def validate_basis(
    basis: Any,
    hidden_size: int,
    *,
    round_interval: int = ROUND_INTERVAL,
    label: str = "basis",
) -> int:
    _require_torch()
    if not isinstance(basis, torch.Tensor) or basis.dtype != torch.float64:
        raise RuntimeError(f"{label} must be an FP64 tensor")
    if basis.ndim != 2 or basis.shape[0] != hidden_size:
        raise RuntimeError(f"{label} must have shape [{hidden_size}, retained_dimension]")
    retained = int(basis.shape[1])
    if retained <= 0 or retained > hidden_size or retained % round_interval:
        raise RuntimeError(f"{label} retained dimension violates floor-to-{round_interval}")
    if not bool(torch.isfinite(basis).all().item()):
        raise RuntimeError(f"{label} contains a non-finite value")
    gram = basis.transpose(0, 1) @ basis
    identity = torch.eye(retained, dtype=torch.float64, device=basis.device)
    if not torch.allclose(gram, identity, rtol=1e-8, atol=1e-8):
        raise RuntimeError(f"{label} columns are not orthonormal at 1e-8")
    for column in range(retained):
        pivot = int(torch.argmax(basis[:, column].abs()).item())
        if float(basis[pivot, column].item()) < 0.0:
            raise RuntimeError(f"{label} column {column} does not have canonical sign")
    return retained


def is_exact_identity_basis(basis: Any, hidden_size: int) -> bool:
    _require_torch()
    return bool(
        isinstance(basis, torch.Tensor)
        and basis.dtype == torch.float64
        and tuple(basis.shape) == (hidden_size, hidden_size)
        and torch.equal(
            basis,
            torch.eye(hidden_size, dtype=torch.float64, device=basis.device),
        )
    )


def fuse_pre_norm_weight(weight: Any, norm_weight: Any, basis: Any) -> Any:
    """Compute ``W @ diag(1+w) @ Q`` in FP64, then restore W storage dtype."""
    _require_torch()
    if weight.ndim != 2 or norm_weight.ndim != 1 or weight.shape[1] != norm_weight.numel():
        raise RuntimeError("pre-norm fusion shapes are incompatible")
    if basis.shape[0] != norm_weight.numel():
        raise RuntimeError("pre-norm fusion basis has the wrong source dimension")
    q = basis.to(device=weight.device, dtype=torch.float64)
    scale = norm_weight.to(device=weight.device, dtype=torch.float64)
    result = (weight.double() * (1.0 + scale).unsqueeze(0)) @ q
    return result.to(device=weight.device, dtype=weight.dtype)


def rotate_output_weight(weight: Any, basis: Any) -> Any:
    """Compute ``Q.T @ W`` in FP64 without slicing head/intermediate widths."""
    _require_torch()
    if weight.ndim != 2 or basis.ndim != 2 or weight.shape[0] != basis.shape[0]:
        raise RuntimeError("output rotation shapes are incompatible")
    q = basis.to(device=weight.device, dtype=torch.float64)
    result = q.transpose(0, 1) @ weight.double()
    return result.to(device=weight.device, dtype=weight.dtype)


def dense_post_affine(norm_weight: Any, basis: Any) -> Any:
    """Compute ``Q.T @ diag(1+w) @ Q`` in FP64."""
    _require_torch()
    if norm_weight.ndim != 1 or basis.ndim != 2 or norm_weight.numel() != basis.shape[0]:
        raise RuntimeError("dense post-affine shapes are incompatible")
    q = basis.to(device=norm_weight.device, dtype=torch.float64)
    scale = norm_weight.double()
    return q.transpose(0, 1) @ ((1.0 + scale).unsqueeze(1) * q)


def residual_shortcut(input_basis: Any, output_basis: Any) -> Any:
    """Compute the exact rectangular residual shortcut ``Q_in.T @ Q_out``."""
    _require_torch()
    if input_basis.ndim != 2 or output_basis.ndim != 2 or input_basis.shape[0] != output_basis.shape[0]:
        raise RuntimeError("residual shortcut basis shapes are incompatible")
    output = output_basis.to(device=input_basis.device, dtype=torch.float64)
    return input_basis.transpose(0, 1) @ output


_ModuleBase = nn.Module if nn is not None else object


class AffineFreeGemmaRMSNorm(_ModuleBase):
    """Gemma-exact RMS normalization with no learned affine."""

    def __init__(self, dimension: int, eps: float, compute_dtype: Any = None):
        _require_torch()
        super().__init__()
        self.dimension = int(dimension)
        self.eps = float(eps)
        self.compute_dtype = torch.float32 if compute_dtype is None else compute_dtype

    def forward(self, values: Any) -> Any:
        if values.shape[-1] != self.dimension:
            raise RuntimeError("affine-free Gemma RMSNorm received the wrong residual width")
        dtype = values.dtype
        work = values.to(self.compute_dtype)
        work = work * torch.rsqrt(work.pow(2).mean(-1, keepdim=True) + self.eps)
        return work.to(dtype)


class DensePostAffineGemmaRMSNorm(_ModuleBase):
    """Affine-free RMS followed by a learned dense conjugated post-affine."""

    def __init__(self, weight: Any, eps: float, compute_dtype: Any = None, requires_grad: bool = True):
        _require_torch()
        super().__init__()
        if weight.ndim != 2 or weight.shape[0] != weight.shape[1]:
            raise RuntimeError("dense Gemma post-affine must be square")
        self.dimension = int(weight.shape[0])
        self.eps = float(eps)
        self.compute_dtype = torch.float32 if compute_dtype is None else compute_dtype
        self.weight = nn.Parameter(weight, requires_grad=requires_grad)

    def forward(self, values: Any) -> Any:
        if values.shape[-1] != self.dimension:
            raise RuntimeError("dense Gemma post-affine received the wrong residual width")
        dtype = values.dtype
        work = values.to(self.compute_dtype)
        work = work * torch.rsqrt(work.pow(2).mean(-1, keepdim=True) + self.eps)
        # The learned affine is applied in FP32/selected compute precision and
        # only the final result is cast, matching Gemma-3's ordering.
        return (work @ self.weight.to(work.device, self.compute_dtype)).to(dtype)


class CompressedGemma3DecoderLayerCore(_HFGemma3DecoderLayer):
    """Transformers-5.14.1 Gemma-3 decoder forward with residual shortcuts."""

    def __init__(
        self,
        original_layer: Any,
        attn_shortcut: Any,
        mlp_shortcut: Any,
    ):
        _require_torch()
        # The original layer was cloned off-object.  Reuse only its validated
        # children; invoking Gemma3DecoderLayer.__init__ would allocate an
        # untracked second parameter surface.
        nn.Module.__init__(self)
        self.config = original_layer.config
        self.hidden_size = int(attn_shortcut.shape[1])
        self.layer_idx = original_layer.layer_idx
        self.self_attn = original_layer.self_attn
        self.mlp = original_layer.mlp
        self.input_layernorm = original_layer.input_layernorm
        self.post_attention_layernorm = original_layer.post_attention_layernorm
        self.pre_feedforward_layernorm = original_layer.pre_feedforward_layernorm
        self.post_feedforward_layernorm = original_layer.post_feedforward_layernorm
        self.gradient_checkpointing = bool(
            getattr(original_layer, "gradient_checkpointing", False)
        )
        if hasattr(original_layer, "_gradient_checkpointing_func"):
            self._gradient_checkpointing_func = original_layer._gradient_checkpointing_func
        self.register_buffer("attn_shortcut", attn_shortcut, persistent=True)
        self.register_buffer("mlp_shortcut", mlp_shortcut, persistent=True)
        self.train(original_layer.training)

    def forward(
        self,
        hidden_states: Any,
        position_embeddings: Any = None,
        attention_mask: Any = None,
        position_ids: Any = None,
        past_key_values: Any = None,
        **kwargs: Any,
    ) -> Any:
        residual = hidden_states
        hidden_states = self.input_layernorm(hidden_states)
        hidden_states, _ = self.self_attn(
            hidden_states=hidden_states,
            position_embeddings=position_embeddings,
            attention_mask=attention_mask,
            position_ids=position_ids,
            past_key_values=past_key_values,
            **kwargs,
        )
        hidden_states = self.post_attention_layernorm(hidden_states)
        hidden_states = residual @ self.attn_shortcut.to(residual.device, residual.dtype) + hidden_states

        residual = hidden_states
        hidden_states = self.pre_feedforward_layernorm(hidden_states)
        hidden_states = self.mlp(hidden_states)
        hidden_states = self.post_feedforward_layernorm(hidden_states)
        hidden_states = residual @ self.mlp_shortcut.to(residual.device, residual.dtype) + hidden_states
        return hidden_states


@dataclass(frozen=True)
class ModelSurface:
    model: Any
    language_model: Any
    text_config: Any
    layers: tuple[Any, ...]
    embed_tokens: Any
    final_norm: Any
    lm_head: Any


@dataclass(frozen=True)
class LayerApplication:
    layer_index: int
    retained_dimension: int
    zero_slice_noop: bool
    changed_parameters: tuple[str, ...]
    protected_qk_sha256: dict[str, str]


@dataclass(frozen=True)
class ModelApplication:
    layer_reports: tuple[LayerApplication, ...]
    installed_layer_count: int
    rollback_safe: bool


def _require_shape(tensor: Any, shape: tuple[int, ...], label: str) -> None:
    if tuple(tensor.shape) != shape:
        raise RuntimeError(f"unsupported Gemma-3 topology: {label} has shape {tuple(tensor.shape)}, expected {shape}")


def _require_norm(norm: Any, dimension: int, label: str) -> None:
    if type(norm).__name__ != "Gemma3RMSNorm":
        raise RuntimeError(f"unsupported Gemma-3 topology: {label} is not Gemma3RMSNorm")
    _require_shape(norm.weight, (dimension,), f"{label}.weight")
    if float(norm.eps) != RMS_EPS:
        raise RuntimeError(f"unsupported Gemma-3 topology: {label} epsilon changed")


def _require_linear(linear: Any, out_features: int, in_features: int, label: str) -> None:
    if (
        type(linear).__name__ != "Linear"
        or not hasattr(linear, "weight")
        or getattr(linear, "bias", None) is not None
    ):
        raise RuntimeError(f"unsupported Gemma-3 topology: {label} must be bias-free")
    _require_shape(linear.weight, (out_features, in_features), f"{label}.weight")


def _layer_parameter_map(layer: Any) -> dict[str, Any]:
    parameters = dict(layer.named_parameters(recurse=True))
    if set(parameters) != EXACT_LAYER_PARAMETER_NAMES:
        raise RuntimeError(
            "unsupported Gemma-3 topology: exact decoder parameter surface changed"
        )
    return parameters


def validate_layer_storage(layer: Any) -> None:
    """Require the exact finite, colocated BF16 v4 execution surface."""
    _require_torch()
    parameters = _layer_parameter_map(layer)
    devices = {parameter.device for parameter in parameters.values()}
    if len(devices) != 1 or next(iter(devices)).type == "meta":
        raise RuntimeError("adapter core requires one non-meta device per decoder layer")
    for name, parameter in parameters.items():
        if parameter.dtype != torch.bfloat16:
            raise RuntimeError(f"adapter core requires BF16 storage: {name}")
        if not bool(torch.isfinite(parameter).all().item()):
            raise RuntimeError(f"adapter core rejects non-finite parameter: {name}")


def _validate_transformed_storage(layer: Any) -> None:
    expected = EXACT_LAYER_PARAMETER_NAMES - {
        "input_layernorm.weight",
        "pre_feedforward_layernorm.weight",
    }
    parameters = dict(layer.named_parameters(recurse=True))
    if set(parameters) != expected:
        raise RuntimeError("transformed decoder parameter surface changed")
    tensors = list(parameters.values()) + [layer.attn_shortcut, layer.mlp_shortcut]
    devices = {tensor.device for tensor in tensors}
    if len(devices) != 1:
        raise RuntimeError("transformed decoder tensors are not colocated")
    for tensor in tensors:
        if tensor.dtype != torch.bfloat16 or not bool(torch.isfinite(tensor).all().item()):
            raise RuntimeError("transformed decoder contains non-BF16/non-finite state")


def validate_layer_surface(
    layer: Any,
    *,
    hidden_size: int,
    intermediate_size: int,
    q_width: int,
    kv_width: int,
    head_dim: int,
    strict_class_names: bool = True,
) -> None:
    if strict_class_names and type(layer).__name__ != "Gemma3DecoderLayer":
        raise RuntimeError("unsupported Gemma-3 topology: decoder layer class changed")
    required = {
        "config",
        "layer_idx",
        "self_attn",
        "mlp",
        "input_layernorm",
        "post_attention_layernorm",
        "pre_feedforward_layernorm",
        "post_feedforward_layernorm",
    }
    if any(not hasattr(layer, name) for name in required):
        raise RuntimeError("unsupported Gemma-3 topology: decoder surface is incomplete")
    for name in (
        "input_layernorm",
        "post_attention_layernorm",
        "pre_feedforward_layernorm",
        "post_feedforward_layernorm",
    ):
        _require_norm(getattr(layer, name), hidden_size, name)
    attention = layer.self_attn
    if strict_class_names and type(attention).__name__ != "Gemma3Attention":
        raise RuntimeError("unsupported Gemma-3 topology: attention class changed")
    if strict_class_names and type(layer.mlp).__name__ != "Gemma3MLP":
        raise RuntimeError("unsupported Gemma-3 topology: MLP class changed")
    for name, width in (("q_proj", q_width), ("k_proj", kv_width), ("v_proj", kv_width)):
        _require_linear(getattr(attention, name, None), width, hidden_size, f"self_attn.{name}")
    _require_linear(attention.o_proj, hidden_size, q_width, "self_attn.o_proj")
    _require_norm(attention.q_norm, head_dim, "self_attn.q_norm")
    _require_norm(attention.k_norm, head_dim, "self_attn.k_norm")
    distinct_norms = (
        layer.input_layernorm,
        layer.post_attention_layernorm,
        layer.pre_feedforward_layernorm,
        layer.post_feedforward_layernorm,
        attention.q_norm,
        attention.k_norm,
    )
    if len({id(norm) for norm in distinct_norms}) != len(distinct_norms):
        raise RuntimeError("unsupported Gemma-3 topology: distinct norms are aliased")
    _require_linear(layer.mlp.gate_proj, intermediate_size, hidden_size, "mlp.gate_proj")
    _require_linear(layer.mlp.up_proj, intermediate_size, hidden_size, "mlp.up_proj")
    _require_linear(layer.mlp.down_proj, hidden_size, intermediate_size, "mlp.down_proj")
    _layer_parameter_map(layer)
    if strict_class_names:
        if getattr(layer, "hidden_size", None) != hidden_size:
            raise RuntimeError("unsupported Gemma-3 topology: decoder hidden size changed")
        if getattr(attention, "config", None) is not layer.config:
            raise RuntimeError("unsupported Gemma-3 topology: attention config identity changed")
        if getattr(layer.mlp, "config", None) is not layer.config:
            raise RuntimeError("unsupported Gemma-3 topology: MLP config identity changed")
        if (
            getattr(layer.mlp, "hidden_size", None) != hidden_size
            or getattr(layer.mlp, "intermediate_size", None) != intermediate_size
        ):
            raise RuntimeError("unsupported Gemma-3 topology: MLP widths changed")
        expected_attention = {
            "layer_idx": layer.layer_idx,
            "head_dim": head_dim,
            "num_key_value_groups": q_width // kv_width,
            "scaling": getattr(layer.config, "query_pre_attn_scalar", math.nan) ** -0.5,
            "attention_dropout": 0.0,
            "is_causal": True,
            "attn_logit_softcapping": getattr(
                layer.config, "attn_logit_softcapping", None
            ),
        }
        for name, expected in expected_attention.items():
            if getattr(attention, name, None) != expected:
                raise RuntimeError(
                    f"unsupported Gemma-3 topology: self_attn.{name} changed"
                )
        is_sliding = getattr(attention, "layer_type", None) == "sliding_attention"
        if getattr(attention, "is_sliding", None) is not is_sliding:
            raise RuntimeError("unsupported Gemma-3 topology: sliding attention flag changed")
        expected_window = getattr(layer.config, "sliding_window", None) if is_sliding else None
        if getattr(attention, "sliding_window", None) != expected_window:
            raise RuntimeError("unsupported Gemma-3 topology: attention window changed")


def discover_pinned_gemma3(model: Any) -> ModelSurface:
    """Discover and strictly validate the pinned 4B conditional-model surface."""
    _require_torch()
    if type(model).__name__ != "Gemma3ForConditionalGeneration":
        raise RuntimeError("adapter core requires Gemma3ForConditionalGeneration")
    backbone = getattr(model, "model", None)
    language_model = getattr(backbone, "language_model", None)
    text_config = getattr(getattr(model, "config", None), "text_config", None)
    if language_model is None or text_config is None:
        raise RuntimeError("cannot locate Gemma-3 conditional text backbone")
    if type(backbone).__name__ != "Gemma3Model":
        raise RuntimeError("unsupported Gemma-3 topology: multimodal backbone class changed")
    if type(language_model).__name__ != "Gemma3TextModel":
        raise RuntimeError("unsupported Gemma-3 topology: text backbone class changed")
    if type(text_config).__name__ != "Gemma3TextConfig":
        raise RuntimeError("unsupported Gemma-3 topology: text config class changed")
    expected_config = {
        "hidden_size": HIDDEN_SIZE,
        "intermediate_size": INTERMEDIATE_SIZE,
        "num_hidden_layers": NUM_LAYERS,
        "num_attention_heads": NUM_ATTENTION_HEADS,
        "num_key_value_heads": NUM_KEY_VALUE_HEADS,
        "head_dim": HEAD_DIM,
        "vocab_size": VOCAB_SIZE,
        "rms_norm_eps": RMS_EPS,
        "query_pre_attn_scalar": QUERY_PRE_ATTN_SCALAR,
        "sliding_window": SLIDING_WINDOW,
        "tie_word_embeddings": True,
        "hidden_activation": "gelu_pytorch_tanh",
        "max_position_embeddings": 131072,
        "attention_bias": False,
        "attention_dropout": 0.0,
        "use_bidirectional_attention": False,
        "use_cache": True,
    }
    for name, expected in expected_config.items():
        if getattr(text_config, name, None) != expected:
            raise RuntimeError(f"unsupported Gemma-3 topology: config.{name} changed")
    if tuple(getattr(text_config, "layer_types", ())) != LAYER_TYPES:
        raise RuntimeError("unsupported Gemma-3 topology: sliding/full attention pattern changed")
    layers = tuple(getattr(language_model, "layers", ()))
    if len(layers) != NUM_LAYERS:
        raise RuntimeError("unsupported Gemma-3 topology: layer count changed")
    q_width = NUM_ATTENTION_HEADS * HEAD_DIM
    kv_width = NUM_KEY_VALUE_HEADS * HEAD_DIM
    for index, layer in enumerate(layers):
        if getattr(layer, "layer_idx", None) != index:
            raise RuntimeError("unsupported Gemma-3 topology: layer indices changed")
        validate_layer_surface(
            layer,
            hidden_size=HIDDEN_SIZE,
            intermediate_size=INTERMEDIATE_SIZE,
            q_width=q_width,
            kv_width=kv_width,
            head_dim=HEAD_DIM,
        )
        if getattr(layer.self_attn, "layer_type", None) != LAYER_TYPES[index]:
            raise RuntimeError("unsupported Gemma-3 topology: attention type changed")
        if float(getattr(layer.self_attn, "scaling", math.nan)) != QUERY_PRE_ATTN_SCALAR**-0.5:
            raise RuntimeError("unsupported Gemma-3 topology: query scaling changed")
    embed_tokens = getattr(language_model, "embed_tokens", None)
    final_norm = getattr(language_model, "norm", None)
    lm_head = getattr(model, "lm_head", None)
    _require_shape(embed_tokens.weight, (VOCAB_SIZE, HIDDEN_SIZE), "embed_tokens.weight")
    _require_norm(final_norm, HIDDEN_SIZE, "model.norm")
    _require_linear(lm_head, VOCAB_SIZE, HIDDEN_SIZE, "lm_head")
    if embed_tokens.weight is not lm_head.weight:
        raise RuntimeError("unsupported Gemma-3 topology: embeddings and head are not tied")
    if float(getattr(embed_tokens, "scalar_embed_scale", math.nan)) != math.sqrt(HIDDEN_SIZE):
        raise RuntimeError("unsupported Gemma-3 topology: embedding scale changed")
    projector = getattr(backbone, "multi_modal_projector", None)
    if type(projector).__name__ != "Gemma3MultiModalProjector":
        raise RuntimeError("unsupported Gemma-3 topology: multimodal projector surface changed")
    if type(embed_tokens).__name__ != "Gemma3TextScaledWordEmbedding":
        raise RuntimeError("unsupported Gemma-3 topology: embedding class changed")
    if type(lm_head).__name__ != "Linear":
        raise RuntimeError("unsupported Gemma-3 topology: language-model head class changed")
    return ModelSurface(model, language_model, text_config, layers, embed_tokens, final_norm, lm_head)


def _new_linear(original: Any, weight: Any) -> Any:
    _require_torch()
    if getattr(original, "bias", None) is not None:
        raise RuntimeError("adapter core does not support biased Gemma projections")
    new = nn.Linear(
        int(weight.shape[1]),
        int(weight.shape[0]),
        bias=False,
        device=weight.device,
        dtype=weight.dtype,
    )
    new.weight = nn.Parameter(weight, requires_grad=original.weight.requires_grad)
    new.train(original.training)
    return new


def apply_layer_core(
    layer: Any,
    input_basis: Any,
    attention_basis: Any,
    output_basis: Any,
    *,
    hidden_size: int,
    intermediate_size: int,
    q_width: int,
    kv_width: int,
    head_dim: int,
    compute_dtype: Any = None,
    strict_class_names: bool = True,
    authorization: Any = None,
) -> tuple[Any, LayerApplication]:
    """Build a transformed clone; the supplied layer is never mutated."""
    _require_torch()
    validate_layer_surface(
        layer,
        hidden_size=hidden_size,
        intermediate_size=intermediate_size,
        q_width=q_width,
        kv_width=kv_width,
        head_dim=head_dim,
        strict_class_names=strict_class_names,
    )
    # Authorization is the outermost safety boundary.  Any syntactically
    # recognizable reduced basis must be rejected before detailed basis
    # validation, so malformed dimensions cannot bypass or mask the fact that
    # this unqualified core has no nonzero capability issuer.
    supplied_bases = (input_basis, attention_basis, output_basis)
    reduced_basis_supplied = any(
        isinstance(basis, torch.Tensor)
        and basis.ndim == 2
        and basis.shape[0] == hidden_size
        and basis.shape[1] != hidden_size
        for basis in supplied_bases
    )
    if reduced_basis_supplied:
        if authorization is None:
            raise RuntimeError("reduced/nonzero SliceGPT requires sealed authorization")
        raise RuntimeError("this unqualified core cannot validate nonzero authorization")
    dimensions = {
        validate_basis(input_basis, hidden_size, label="input basis"),
        validate_basis(attention_basis, hidden_size, label="attention basis"),
        validate_basis(output_basis, hidden_size, label="output basis"),
    }
    if len(dimensions) != 1:
        raise RuntimeError("constant residual-width scheduler was violated")
    retained = dimensions.pop()
    if compute_dtype not in (None, torch.float32):
        raise RuntimeError("adapter core execution precision is fixed to FP32")
    validate_layer_storage(layer)
    if retained != hidden_size:
        raise RuntimeError("unreachable reduced-width authorization state")
    if all(
        is_exact_identity_basis(basis, hidden_size)
        for basis in (input_basis, attention_basis, output_basis)
    ):
        protected = {
            name: tensor_sha256(getattr(layer.self_attn, name.split(".")[-2]).weight)
            for name in PROTECTED_QK_NORMS
        }
        return layer, LayerApplication(
            int(layer.layer_idx), retained, True, (), protected
        )

    original_parameter_hashes = {
        name: tensor_sha256(parameter)
        for name, parameter in layer.named_parameters(recurse=True)
    }
    original_layer = layer
    working_layer = copy.deepcopy(layer)
    layer = working_layer
    protected_objects = (layer.self_attn.q_norm, layer.self_attn.k_norm)
    protected_before = {
        PROTECTED_QK_NORMS[0]: tensor_sha256(layer.self_attn.q_norm.weight),
        PROTECTED_QK_NORMS[1]: tensor_sha256(layer.self_attn.k_norm.weight),
    }
    storage_dtype = layer.self_attn.q_proj.weight.dtype
    execution_dtype = torch.float32

    # Compute every replacement before mutating the layer.
    replacements = {
        "q_proj": fuse_pre_norm_weight(
            layer.self_attn.q_proj.weight, layer.input_layernorm.weight, input_basis
        ),
        "k_proj": fuse_pre_norm_weight(
            layer.self_attn.k_proj.weight, layer.input_layernorm.weight, input_basis
        ),
        "v_proj": fuse_pre_norm_weight(
            layer.self_attn.v_proj.weight, layer.input_layernorm.weight, input_basis
        ),
        "o_proj": rotate_output_weight(layer.self_attn.o_proj.weight, attention_basis),
        "gate_proj": fuse_pre_norm_weight(
            layer.mlp.gate_proj.weight, layer.pre_feedforward_layernorm.weight, attention_basis
        ),
        "up_proj": fuse_pre_norm_weight(
            layer.mlp.up_proj.weight, layer.pre_feedforward_layernorm.weight, attention_basis
        ),
        "down_proj": rotate_output_weight(layer.mlp.down_proj.weight, output_basis),
    }
    post_attention = dense_post_affine(
        layer.post_attention_layernorm.weight, attention_basis
    ).to(layer.post_attention_layernorm.weight.device, storage_dtype)
    post_feedforward = dense_post_affine(
        layer.post_feedforward_layernorm.weight, output_basis
    ).to(layer.post_feedforward_layernorm.weight.device, storage_dtype)
    attn_shortcut = residual_shortcut(input_basis, attention_basis).to(
        layer.self_attn.q_proj.weight.device, storage_dtype
    )
    mlp_shortcut = residual_shortcut(attention_basis, output_basis).to(
        layer.self_attn.q_proj.weight.device, storage_dtype
    )

    layer.self_attn.q_proj = _new_linear(layer.self_attn.q_proj, replacements["q_proj"])
    layer.self_attn.k_proj = _new_linear(layer.self_attn.k_proj, replacements["k_proj"])
    layer.self_attn.v_proj = _new_linear(layer.self_attn.v_proj, replacements["v_proj"])
    layer.self_attn.o_proj = _new_linear(layer.self_attn.o_proj, replacements["o_proj"])
    layer.mlp.gate_proj = _new_linear(layer.mlp.gate_proj, replacements["gate_proj"])
    layer.mlp.up_proj = _new_linear(layer.mlp.up_proj, replacements["up_proj"])
    layer.mlp.down_proj = _new_linear(layer.mlp.down_proj, replacements["down_proj"])
    layer.input_layernorm = AffineFreeGemmaRMSNorm(retained, RMS_EPS, execution_dtype)
    layer.pre_feedforward_layernorm = AffineFreeGemmaRMSNorm(retained, RMS_EPS, execution_dtype)
    layer.post_attention_layernorm = DensePostAffineGemmaRMSNorm(
        post_attention,
        RMS_EPS,
        execution_dtype,
        requires_grad=layer.post_attention_layernorm.weight.requires_grad,
    )
    layer.post_feedforward_layernorm = DensePostAffineGemmaRMSNorm(
        post_feedforward,
        RMS_EPS,
        execution_dtype,
        requires_grad=layer.post_feedforward_layernorm.weight.requires_grad,
    )
    layer.self_attn.q_proj.in_features = retained
    layer.self_attn.k_proj.in_features = retained
    layer.self_attn.v_proj.in_features = retained
    layer.self_attn.o_proj.out_features = retained
    layer.mlp.gate_proj.in_features = retained
    layer.mlp.up_proj.in_features = retained
    layer.mlp.down_proj.out_features = retained
    layer.mlp.hidden_size = retained

    if protected_objects != (layer.self_attn.q_norm, layer.self_attn.k_norm):
        raise RuntimeError("adapter core replaced a protected q/k norm object")
    protected_after = {
        PROTECTED_QK_NORMS[0]: tensor_sha256(layer.self_attn.q_norm.weight),
        PROTECTED_QK_NORMS[1]: tensor_sha256(layer.self_attn.k_norm.weight),
    }
    if protected_after != protected_before:
        raise RuntimeError("adapter core changed a protected q/k norm")
    wrapped = CompressedGemma3DecoderLayerCore(layer, attn_shortcut, mlp_shortcut)
    _validate_transformed_storage(wrapped)
    if {
        name: tensor_sha256(parameter)
        for name, parameter in working_layer.named_parameters(recurse=True)
        if name in original_parameter_hashes and name in PROTECTED_QK_NORMS
    } != {name: original_parameter_hashes[name] for name in PROTECTED_QK_NORMS}:
        raise RuntimeError("adapter clone postcheck changed a protected q/k norm")
    if {
        name: tensor_sha256(parameter)
        for name, parameter in original_layer.named_parameters(recurse=True)
    } != original_parameter_hashes:
        raise RuntimeError("off-object transform changed its source layer")
    return wrapped, LayerApplication(
        int(layer.layer_idx),
        retained,
        False,
        PER_LAYER_CHANGED_PARAMETERS,
        protected_after,
    )


def _basis_triplet(value: Any, index: int) -> tuple[Any, Any, Any]:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise RuntimeError(f"layer {index} basis record must be an exact triplet")
    return value[0], value[1], value[2]


def build_model_layers_atomic(
    model: Any,
    layer_bases: Sequence[Any],
    *,
    authorization: Any = None,
) -> tuple[Any, tuple[LayerApplication, ...]]:
    """Build all 34 cloned layers before exposing any model mutation."""
    _require_torch()
    surface = discover_pinned_gemma3(model)
    if len(layer_bases) != NUM_LAYERS:
        raise RuntimeError("model transform requires exactly 34 layer basis triplets")
    triplets = tuple(_basis_triplet(value, index) for index, value in enumerate(layer_bases))
    if not is_exact_identity_basis(triplets[0][0], HIDDEN_SIZE):
        raise RuntimeError("unchanged embeddings require an identity first input basis")
    if not is_exact_identity_basis(triplets[-1][2], HIDDEN_SIZE):
        raise RuntimeError("unchanged final norm/head require an identity final output basis")
    for index in range(NUM_LAYERS - 1):
        if not torch.equal(triplets[index][2], triplets[index + 1][0]):
            raise RuntimeError(f"cross-layer basis discontinuity after layer {index}")

    transformed, reports = [], []
    for layer, triplet in zip(surface.layers, triplets, strict=True):
        wrapped, report = apply_layer_core(
            layer,
            *triplet,
            hidden_size=HIDDEN_SIZE,
            intermediate_size=INTERMEDIATE_SIZE,
            q_width=NUM_ATTENTION_HEADS * HEAD_DIM,
            kv_width=NUM_KEY_VALUE_HEADS * HEAD_DIM,
            head_dim=HEAD_DIM,
            authorization=authorization,
        )
        transformed.append(wrapped)
        reports.append(report)
    return nn.ModuleList(transformed), tuple(reports)


def install_model_layers_atomic(
    model: Any,
    layer_bases: Sequence[Any],
    *,
    authorization: Any = None,
) -> ModelApplication:
    """Install one prevalidated ModuleList, rolling back either model assignment."""
    new_layers, reports = build_model_layers_atomic(
        model, layer_bases, authorization=authorization
    )
    surface = discover_pinned_gemma3(model)
    old_layers = surface.language_model.layers
    had_no_split = "_no_split_modules" in vars(model)
    old_no_split = getattr(model, "_no_split_modules", None)
    try:
        surface.language_model.layers = new_layers
        existing = list(old_no_split or [])
        if COMPRESSED_LAYER_CLASS_NAME not in existing:
            existing.append(COMPRESSED_LAYER_CLASS_NAME)
        model._no_split_modules = existing
        if len(surface.language_model.layers) != NUM_LAYERS:
            raise RuntimeError("model-level transformed layer postcheck failed")
    except BaseException:
        surface.language_model.layers = old_layers
        if had_no_split:
            model._no_split_modules = old_no_split
        elif "_no_split_modules" in vars(model):
            delattr(model, "_no_split_modules")
        raise
    return ModelApplication(reports, len(new_layers), True)


def reject_pixel_values(pixel_values: Any) -> None:
    if pixel_values is not None:
        raise RuntimeError("Gemma-3 SliceGPT v4 is text-only; pixel_values are forbidden")


def qualification_status() -> dict[str, Any]:
    """Machine-readable boundary: this core alone is never launch approval."""
    return {
        "version": VERSION,
        "adapter_core_implemented": True,
        "nonzero_slice_authorized": False,
        "probe2_verdict": None,
        "remaining_gates": [
            "sealed nonzero authorization capability issuer",
            "captured-activation FP64 layer algebra",
            "196-prompt text extraction and both cache paths",
            "BF16 unsliced scalar/component/continuation limits",
            "frozen logit agreement",
            "native sharded Safetensors project-loader roundtrip",
            "seven-target LoRA attach/save/reload/merge smoke",
            "real-HF cache, gradient-checkpoint and hidden/attention-capture qualification",
            "model-level embedding/final-head integration and immutable calibration archive",
        ],
    }
