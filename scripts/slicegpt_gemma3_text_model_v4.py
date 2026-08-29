"""Canonical text-only model boundary for the Gemma-3 SliceGPT v4 adapter.

This module owns the model-level surface that the layer algebra intentionally
does not own: text extraction, final RMSNorm fusion, untied output weights,
strict reconstruction of the custom decoder skeleton, and the hard text-only
forward boundary.  It does not issue or accept a nonzero-slice capability.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    import torch
    from torch import nn
except ModuleNotFoundError:  # Source-contract tests run on the laptop.
    torch = None
    nn = None

try:
    from transformers.models.gemma3.configuration_gemma3 import Gemma3TextConfig
    from transformers.models.gemma3.modeling_gemma3 import (
        Gemma3ForCausalLM,
        Gemma3PreTrainedModel,
        Gemma3TextScaledWordEmbedding,
    )
except ModuleNotFoundError:  # Source-contract tests run on the laptop.
    Gemma3TextConfig = object
    Gemma3ForCausalLM = object
    Gemma3PreTrainedModel = object
    Gemma3TextScaledWordEmbedding = object

try:
    import slicegpt_gemma3_adapter_core_v4 as CORE
except ModuleNotFoundError:
    CORE = None


VERSION = "gemma3_slicegpt_text_model_v4_v1_unqualified"
MODEL_TYPE = "gemma3_slicegpt_text_v4"
ARCHITECTURE = "Gemma3SliceGPTTextForCausalLMV4"
CONFIG_CLASS = "Gemma3SliceGPTTextConfigV4"
CORE_VERSION = "gemma3_slicegpt_adapter_core_v4_v1_unqualified"
CORE_SOURCE_SHA256 = "c4df2be9111fd293454b19f98fba5d46805479d51db02d0611dcfab58f73cfdd"
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
PROJECTION_NAMES = (
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
)
DIMENSION_KEYS = ("input", "attention", "output")


def _require_runtime() -> None:
    if torch is None or nn is None or CORE is None or Gemma3TextConfig is object:
        raise RuntimeError(
            "Gemma-3 SliceGPT text model requires the pinned torch/transformers runtime"
        )
    if getattr(CORE, "VERSION", None) != CORE_VERSION:
        raise RuntimeError("Gemma-3 SliceGPT adapter-core identity changed")
    expected_path = Path(__file__).resolve().with_name(
        "slicegpt_gemma3_adapter_core_v4.py"
    )
    actual_path = Path(getattr(CORE, "__file__", "")).resolve()
    if actual_path != expected_path:
        raise RuntimeError("Gemma-3 SliceGPT adapter-core source path changed")
    if hashlib.sha256(expected_path.read_bytes()).hexdigest() != CORE_SOURCE_SHA256:
        raise RuntimeError("Gemma-3 SliceGPT adapter-core source hash changed")


def _exact_int(value: Any, label: str) -> int:
    if type(value) is not int:
        raise RuntimeError(f"{label} must be an exact integer")
    return value


def _canonical_dimensions(value: Any) -> tuple[tuple[int, int, int], ...]:
    """Validate the exact 34-layer residual-boundary schema.

    The unqualified model deliberately accepts only the full-width surface.
    Reduced dimensions cannot be enabled by passing an arbitrary object.
    """

    if not isinstance(value, (tuple, list)) or len(value) != NUM_LAYERS:
        raise RuntimeError("residual_dimensions must contain exactly 34 records")
    records: list[tuple[int, int, int]] = []
    for index, record in enumerate(value):
        if not isinstance(record, Mapping) or set(record) != set(DIMENSION_KEYS):
            raise RuntimeError(f"residual dimension record {index} schema changed")
        dimensions = tuple(
            _exact_int(record[key], f"layer {index} {key} dimension")
            for key in DIMENSION_KEYS
        )
        for dimension in dimensions:
            if dimension <= 0 or dimension > HIDDEN_SIZE or dimension % ROUND_INTERVAL:
                raise RuntimeError(
                    f"layer {index} dimension violates the exact floor-to-8 boundary"
                )
        records.append(dimensions)
    if records[0][0] != HIDDEN_SIZE:
        raise RuntimeError("unchanged embeddings require a full-width first input")
    if records[-1][2] != HIDDEN_SIZE:
        raise RuntimeError("unchanged final head requires a full-width last output")
    for index in range(NUM_LAYERS - 1):
        if records[index][2] != records[index + 1][0]:
            raise RuntimeError(f"cross-layer dimension discontinuity after layer {index}")
    if any(dimension != HIDDEN_SIZE for record in records for dimension in record):
        raise RuntimeError(
            "reduced/nonzero SliceGPT text models require an external sealed capability"
        )
    return tuple(records)


def full_width_dimensions() -> tuple[dict[str, int], ...]:
    return tuple(
        {"input": HIDDEN_SIZE, "attention": HIDDEN_SIZE, "output": HIDDEN_SIZE}
        for _ in range(NUM_LAYERS)
    )


def _pinned_config_values() -> dict[str, Any]:
    return {
        "vocab_size": VOCAB_SIZE,
        "hidden_size": HIDDEN_SIZE,
        "intermediate_size": INTERMEDIATE_SIZE,
        "num_hidden_layers": NUM_LAYERS,
        "num_attention_heads": NUM_ATTENTION_HEADS,
        "num_key_value_heads": NUM_KEY_VALUE_HEADS,
        "head_dim": HEAD_DIM,
        "hidden_activation": "gelu_pytorch_tanh",
        "max_position_embeddings": 131072,
        "initializer_range": 0.02,
        "rms_norm_eps": RMS_EPS,
        "use_cache": True,
        "pad_token_id": 0,
        # The conditional model's top-level generation config stops on both
        # EOS and end-of-turn.  The nested text config only stores ``1``;
        # text extraction must preserve the effective conditional behavior.
        "eos_token_id": [1, 106],
        "bos_token_id": 2,
        "tie_word_embeddings": False,
        "dtype": "bfloat16",
        "rope_parameters": {
            "sliding_attention": {
                "rope_type": "default",
                "rope_theta": 10000.0,
            },
            "full_attention": {
                "rope_type": "linear",
                "factor": 8.0,
                "rope_theta": 1000000.0,
            },
        },
        "attention_bias": False,
        "attention_dropout": 0.0,
        "query_pre_attn_scalar": QUERY_PRE_ATTN_SCALAR,
        "sliding_window": SLIDING_WINDOW,
        "layer_types": list(LAYER_TYPES),
        "final_logit_softcapping": None,
        "attn_logit_softcapping": None,
        "use_bidirectional_attention": False,
    }


class Gemma3SliceGPTTextConfigV4(Gemma3TextConfig):
    """Frozen text-only config; it contains no nonzero authorization hook."""

    model_type = MODEL_TYPE

    def __init__(
        self,
        *,
        residual_dimensions: Sequence[Mapping[str, int]] | None = None,
        slicegpt_protocol_version: str = VERSION,
        slicegpt_adapter_core_version: str = CORE_VERSION,
        slicegpt_adapter_core_sha256: str = CORE_SOURCE_SHA256,
        text_only: bool = True,
        dense_post_affine: bool = True,
        **kwargs: Any,
    ) -> None:
        _require_runtime()
        if slicegpt_protocol_version != VERSION:
            raise RuntimeError("SliceGPT text config protocol identity changed")
        if slicegpt_adapter_core_version != CORE_VERSION:
            raise RuntimeError("SliceGPT adapter-core config identity changed")
        if slicegpt_adapter_core_sha256 != CORE_SOURCE_SHA256:
            raise RuntimeError("SliceGPT adapter-core source hash identity changed")
        if text_only is not True or dense_post_affine is not True:
            raise RuntimeError("SliceGPT text config safety flags changed")
        dimensions = _canonical_dimensions(
            full_width_dimensions() if residual_dimensions is None else residual_dimensions
        )
        pinned = _pinned_config_values()
        for name, expected in pinned.items():
            if name in kwargs and kwargs[name] != expected:
                raise RuntimeError(f"pinned text config field changed: {name}")
            kwargs[name] = expected
        architectures = kwargs.pop("architectures", None)
        if architectures not in (None, [ARCHITECTURE], (ARCHITECTURE,)):
            raise RuntimeError("custom text architecture identity changed")
        super().__init__(architectures=[ARCHITECTURE], **kwargs)
        self.residual_dimensions = [
            dict(zip(DIMENSION_KEYS, record, strict=True)) for record in dimensions
        ]
        self.slicegpt_protocol_version = VERSION
        self.slicegpt_adapter_core_version = CORE_VERSION
        self.slicegpt_adapter_core_sha256 = CORE_SOURCE_SHA256
        self.text_only = True
        self.dense_post_affine = True
        self.tie_word_embeddings = False


def _new_linear(
    in_features: int,
    out_features: int,
    *,
    reference: Any,
    requires_grad: bool | None = None,
) -> Any:
    _require_runtime()
    if type(reference).__name__ != "Linear" or getattr(reference, "bias", None) is not None:
        raise RuntimeError("compressed skeleton requires bias-free Linear projections")
    result = nn.Linear(
        in_features,
        out_features,
        bias=False,
        device=reference.weight.device,
        dtype=reference.weight.dtype,
    )
    if requires_grad is None:
        requires_grad = bool(reference.weight.requires_grad)
    result.weight.requires_grad_(requires_grad)
    result.train(reference.training)
    return result


def _empty_square(reference: Any, dimension: int) -> Any:
    _require_runtime()
    return torch.empty(
        (dimension, dimension),
        device=reference.device,
        dtype=reference.dtype,
    )


def _empty_shortcut(reference: Any, rows: int, columns: int) -> Any:
    _require_runtime()
    return torch.empty((rows, columns), device=reference.device, dtype=reference.dtype)


def _cast_persistent_state_to_bfloat16(module: Any) -> None:
    """Cast only checkpoint state, preserving HF's FP32 nonpersistent RoPE buffers."""

    _require_runtime()
    for child in module.modules():
        for name, parameter in tuple(child._parameters.items()):
            if parameter is None:
                continue
            child._parameters[name] = nn.Parameter(
                parameter.detach().to(dtype=torch.bfloat16),
                requires_grad=parameter.requires_grad,
            )
        nonpersistent = child._non_persistent_buffers_set
        for name, buffer in tuple(child._buffers.items()):
            if buffer is not None and name not in nonpersistent:
                child._buffers[name] = buffer.to(dtype=torch.bfloat16)


def _reset_transferred_output_capture_state(language_model: Any) -> None:
    """Force Transformers to install hidden-state hooks on replacement layers.

    Transformers 5.14 lazily records ``output_hidden_states`` by attaching
    hooks to the decoder objects and setting this marker on the text model.
    The live full-width conversion has already exercised that path before it
    replaces every decoder with a compressed wrapper.  Transferring the same
    text-model object would otherwise retain the marker while the hooked
    decoder objects have gone out of the graph, yielding an empty hidden-state
    tuple.  Clearing the marker makes the pinned runtime install hooks on the
    replacement subclasses at their first forward.
    """

    setattr(language_model, "_output_capturing_hooks_installed", False)


def _replace_decoder_with_skeleton(layer: Any, dimensions: tuple[int, int, int]) -> Any:
    """Replace one freshly initialized HF layer with its deterministic shape skeleton."""

    _require_runtime()
    if type(layer).__name__ != "Gemma3DecoderLayer":
        raise RuntimeError("compressed skeleton source decoder class changed")
    input_dimension, attention_dimension, output_dimension = dimensions
    attention = layer.self_attn
    mlp = layer.mlp
    attention.q_proj = _new_linear(input_dimension, NUM_ATTENTION_HEADS * HEAD_DIM, reference=attention.q_proj)
    attention.k_proj = _new_linear(input_dimension, NUM_KEY_VALUE_HEADS * HEAD_DIM, reference=attention.k_proj)
    attention.v_proj = _new_linear(input_dimension, NUM_KEY_VALUE_HEADS * HEAD_DIM, reference=attention.v_proj)
    attention.o_proj = _new_linear(NUM_ATTENTION_HEADS * HEAD_DIM, attention_dimension, reference=attention.o_proj)
    mlp.gate_proj = _new_linear(attention_dimension, INTERMEDIATE_SIZE, reference=mlp.gate_proj)
    mlp.up_proj = _new_linear(attention_dimension, INTERMEDIATE_SIZE, reference=mlp.up_proj)
    mlp.down_proj = _new_linear(INTERMEDIATE_SIZE, output_dimension, reference=mlp.down_proj)
    mlp.hidden_size = attention_dimension
    layer.input_layernorm = CORE.AffineFreeGemmaRMSNorm(input_dimension, RMS_EPS)
    layer.pre_feedforward_layernorm = CORE.AffineFreeGemmaRMSNorm(attention_dimension, RMS_EPS)
    layer.post_attention_layernorm = CORE.DensePostAffineGemmaRMSNorm(
        _empty_square(attention.q_proj.weight, attention_dimension), RMS_EPS
    )
    layer.post_feedforward_layernorm = CORE.DensePostAffineGemmaRMSNorm(
        _empty_square(mlp.down_proj.weight, output_dimension), RMS_EPS
    )
    layer.hidden_size = output_dimension
    return CORE.CompressedGemma3DecoderLayerCore(
        layer,
        _empty_shortcut(attention.q_proj.weight, input_dimension, attention_dimension),
        _empty_shortcut(mlp.down_proj.weight, attention_dimension, output_dimension),
    )


class Gemma3SliceGPTTextForCausalLMV4(Gemma3ForCausalLM):
    """HF generation-compatible, strictly text-only SliceGPT model."""

    config_class = Gemma3SliceGPTTextConfigV4
    base_model_prefix = "model"
    _tied_weights_keys: dict[str, str] = {}
    _no_split_modules = ["CompressedGemma3DecoderLayerCore"]

    def __init__(self, config: Gemma3SliceGPTTextConfigV4) -> None:
        _require_runtime()
        if type(config) is not Gemma3SliceGPTTextConfigV4:
            raise RuntimeError("custom text model requires its exact custom config class")
        dimensions = _canonical_dimensions(config.residual_dimensions)
        super().__init__(config)
        if self.lm_head.weight is self.model.embed_tokens.weight:
            raise RuntimeError("custom model initialization unexpectedly tied output weights")
        rebuilt = [
            _replace_decoder_with_skeleton(layer, record)
            for layer, record in zip(self.model.layers, dimensions, strict=True)
        ]
        self.model.layers = nn.ModuleList(rebuilt)
        final_dimension = dimensions[-1][2]
        self.model.norm = CORE.AffineFreeGemmaRMSNorm(final_dimension, RMS_EPS)
        self.lm_head = _new_linear(
            final_dimension,
            VOCAB_SIZE,
            reference=self.lm_head,
        )
        self.config.tie_word_embeddings = False
        self.model.config = self.config
        self.vocab_size = VOCAB_SIZE
        _cast_persistent_state_to_bfloat16(self)
        self._slicegpt_weights_loaded = False

    @classmethod
    def from_pretrained(cls, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(
            "direct HF loading is forbidden; use the strict v4 project loader after its qualification"
        )

    def tie_weights(self, *args: Any, **kwargs: Any) -> None:
        """Prevent every HF load/save path from silently retying the head."""

        if getattr(self, "model", None) is None or getattr(self, "lm_head", None) is None:
            return
        if self.lm_head.weight is self.model.embed_tokens.weight:
            raise RuntimeError("SliceGPT text model output weights were silently retied")
        if self.lm_head.weight.device.type != "meta" and self.model.embed_tokens.weight.device.type != "meta":
            if self.lm_head.weight.untyped_storage().data_ptr() == self.model.embed_tokens.weight.untyped_storage().data_ptr():
                raise RuntimeError("SliceGPT text model output storage was silently retied")

    def forward(
        self,
        input_ids: Any = None,
        attention_mask: Any = None,
        position_ids: Any = None,
        past_key_values: Any = None,
        inputs_embeds: Any = None,
        labels: Any = None,
        use_cache: bool | None = None,
        logits_to_keep: Any = 0,
        pixel_values: Any = None,
        **kwargs: Any,
    ) -> Any:
        if pixel_values is not None:
            raise RuntimeError("Gemma-3 SliceGPT v4 is text-only; pixel_values are forbidden")
        if getattr(self, "_slicegpt_weights_loaded", None) is not True:
            raise RuntimeError("compressed skeleton weights are not strictly loaded")
        return super().forward(
            input_ids=input_ids,
            attention_mask=attention_mask,
            position_ids=position_ids,
            past_key_values=past_key_values,
            inputs_embeds=inputs_embeds,
            labels=labels,
            use_cache=use_cache,
            logits_to_keep=logits_to_keep,
            **kwargs,
        )


def fuse_final_norm_into_head(
    head_weight: Any,
    norm_weight: Any,
    *,
    chunk_rows: int = 4096,
) -> Any:
    """Compute ``W @ diag(1+w)`` in bounded FP64 chunks, storing BF16."""

    _require_runtime()
    if type(chunk_rows) is not int or chunk_rows <= 0:
        raise RuntimeError("final fusion chunk_rows must be a positive exact integer")
    if not isinstance(head_weight, torch.Tensor) or not isinstance(norm_weight, torch.Tensor):
        raise RuntimeError("final fusion requires tensors")
    if head_weight.ndim != 2 or norm_weight.ndim != 1 or head_weight.shape[1] != norm_weight.numel():
        raise RuntimeError("final norm/head fusion shapes are incompatible")
    if head_weight.dtype != torch.bfloat16 or norm_weight.dtype != torch.bfloat16:
        raise RuntimeError("final norm/head fusion requires BF16 storage")
    if head_weight.device != norm_weight.device or head_weight.device.type == "meta":
        raise RuntimeError("final norm/head fusion requires one materialized device")
    if not bool(torch.isfinite(head_weight).all().item()) or not bool(torch.isfinite(norm_weight).all().item()):
        raise RuntimeError("final norm/head fusion rejects non-finite state")
    output = torch.empty_like(head_weight)
    multiplier = 1.0 + norm_weight.double()
    for start in range(0, head_weight.shape[0], chunk_rows):
        stop = min(start + chunk_rows, head_weight.shape[0])
        output[start:stop].copy_((head_weight[start:stop].double() * multiplier).to(torch.bfloat16))
    return output


def _tensor_hash(tensor: Any) -> str:
    raw = tensor.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes()
    return hashlib.sha256(raw).hexdigest()


def finalize_from_conditional(
    conditional_model: Any,
    *,
    residual_dimensions: Sequence[Mapping[str, int]],
    chunk_rows: int = 4096,
) -> Gemma3SliceGPTTextForCausalLMV4:
    """Consume a transformed conditional model and return the canonical text model.

    This is intentionally full-width-only until a separate sealed capability
    issuer exists.  All allocations and fusion complete before the source
    language model's final norm is replaced.
    """

    _require_runtime()
    dimensions = _canonical_dimensions(residual_dimensions)
    if type(conditional_model).__name__ != "Gemma3ForConditionalGeneration":
        raise RuntimeError("text extraction requires the exact conditional-model class")
    backbone = getattr(conditional_model, "model", None)
    language_model = getattr(backbone, "language_model", None)
    text_config = getattr(getattr(conditional_model, "config", None), "text_config", None)
    if type(language_model).__name__ != "Gemma3TextModel" or type(text_config).__name__ != "Gemma3TextConfig":
        raise RuntimeError("conditional text backbone/config topology changed")
    if getattr(conditional_model.config, "eos_token_id", None) != [1, 106]:
        raise RuntimeError("conditional generation EOS identity changed")
    if len(getattr(language_model, "layers", ())) != NUM_LAYERS or any(
        type(layer).__name__ != "CompressedGemma3DecoderLayerCore"
        for layer in language_model.layers
    ):
        raise RuntimeError("conditional model does not contain exactly 34 compressed layers")
    embed = language_model.embed_tokens
    head = conditional_model.lm_head
    norm = language_model.norm
    if type(embed).__name__ != "Gemma3TextScaledWordEmbedding" or type(head).__name__ != "Linear":
        raise RuntimeError("conditional embedding/head topology changed")
    if head.weight is not embed.weight:
        raise RuntimeError("source conditional embeddings/head are not tied")
    if type(norm).__name__ != "Gemma3RMSNorm" or tuple(norm.weight.shape) != (HIDDEN_SIZE,):
        raise RuntimeError("source conditional final norm topology changed")
    if tuple(head.weight.shape) != (VOCAB_SIZE, HIDDEN_SIZE) or head.bias is not None:
        raise RuntimeError("source conditional head shape changed")
    config_data = text_config.to_dict()
    config_data.pop("model_type", None)
    config_data.pop("architectures", None)
    config_data["tie_word_embeddings"] = False
    config_data["eos_token_id"] = [1, 106]
    config_data["dtype"] = "bfloat16"
    config = Gemma3SliceGPTTextConfigV4(
        residual_dimensions=[dict(zip(DIMENSION_KEYS, record, strict=True)) for record in dimensions],
        **config_data,
    )
    fused_weight = fuse_final_norm_into_head(head.weight, norm.weight, chunk_rows=chunk_rows)
    new_head = nn.Linear(
        HIDDEN_SIZE,
        VOCAB_SIZE,
        bias=False,
        device=head.weight.device,
        dtype=head.weight.dtype,
    )
    new_head.weight = nn.Parameter(fused_weight, requires_grad=head.weight.requires_grad)
    new_norm = CORE.AffineFreeGemmaRMSNorm(HIDDEN_SIZE, RMS_EPS)

    # Avoid a second 4B allocation.  Initialize only the HF PreTrainedModel
    # shell, then atomically transfer the already transformed text backbone.
    result = Gemma3SliceGPTTextForCausalLMV4.__new__(Gemma3SliceGPTTextForCausalLMV4)
    Gemma3PreTrainedModel.__init__(result, config)
    result.model = language_model
    result.lm_head = new_head
    result.vocab_size = VOCAB_SIZE
    result.config = config
    result._slicegpt_weights_loaded = True
    _reset_transferred_output_capture_state(language_model)
    old_norm = language_model.norm
    old_config = language_model.config
    old_layer_configs = tuple(
        (layer.config, layer.self_attn.config, layer.mlp.config)
        for layer in language_model.layers
    )
    try:
        language_model.norm = new_norm
        language_model.config = config
        for layer in language_model.layers:
            layer.config = config
            layer.self_attn.config = config
            layer.mlp.config = config
        validate_text_model(result)
    except BaseException:
        language_model.norm = old_norm
        language_model.config = old_config
        for layer, previous in zip(language_model.layers, old_layer_configs, strict=True):
            layer.config, layer.self_attn.config, layer.mlp.config = previous
        raise
    return result


def _shape(module: Any, shape: tuple[int, ...], label: str) -> None:
    if not hasattr(module, "weight") or tuple(module.weight.shape) != shape:
        raise RuntimeError(f"custom text topology changed: {label}")


def exact_projection_module_names(model: Any) -> tuple[str, ...]:
    """Return the exact 34x7 text projection names or fail closed."""

    _require_runtime()
    expected = {
        f"model.layers.{index}.{branch}.{name}"
        for index in range(NUM_LAYERS)
        for branch, names in (
            ("self_attn", PROJECTION_NAMES[:4]),
            ("mlp", PROJECTION_NAMES[4:]),
        )
        for name in names
    }
    actual = {
        name
        for name, module in model.named_modules()
        if name.rsplit(".", 1)[-1] in PROJECTION_NAMES
    }
    if actual != expected:
        raise RuntimeError("custom text projection module-name surface changed")
    return tuple(sorted(actual))


def expected_state_keys() -> frozenset[str]:
    keys = {"model.embed_tokens.weight", "lm_head.weight"}
    for index in range(NUM_LAYERS):
        prefix = f"model.layers.{index}"
        keys.update(
            {
                f"{prefix}.self_attn.{name}.weight"
                for name in PROJECTION_NAMES[:4]
            }
        )
        keys.update(
            {
                f"{prefix}.self_attn.q_norm.weight",
                f"{prefix}.self_attn.k_norm.weight",
                f"{prefix}.mlp.gate_proj.weight",
                f"{prefix}.mlp.up_proj.weight",
                f"{prefix}.mlp.down_proj.weight",
                f"{prefix}.post_attention_layernorm.weight",
                f"{prefix}.post_feedforward_layernorm.weight",
                f"{prefix}.attn_shortcut",
                f"{prefix}.mlp_shortcut",
            }
        )
    return frozenset(keys)


def expected_buffer_keys() -> frozenset[str]:
    """Return the exact persistent non-parameter state surface."""

    return frozenset(
        f"model.layers.{index}.{name}"
        for index in range(NUM_LAYERS)
        for name in ("attn_shortcut", "mlp_shortcut")
    )


def expected_parameter_keys() -> frozenset[str]:
    """Return the exact trainable/frozen parameter state surface."""

    return expected_state_keys() - expected_buffer_keys()


def expected_nonpersistent_buffer_keys() -> frozenset[str]:
    """Return the exact HF execution buffers that are deliberately not state."""

    return frozenset(
        {
            "model.embed_tokens.embed_scale",
            "model.rotary_emb.full_attention_inv_freq",
            "model.rotary_emb.full_attention_original_inv_freq",
            "model.rotary_emb.sliding_attention_inv_freq",
            "model.rotary_emb.sliding_attention_original_inv_freq",
        }
    )


def _validate_text_model(model: Any, *, require_materialized: bool) -> None:
    """Validate the exact custom class/config/module/name/shape/storage identity."""

    _require_runtime()
    if type(model) is not Gemma3SliceGPTTextForCausalLMV4:
        raise RuntimeError("custom text model class identity changed")
    if type(model.config) is not Gemma3SliceGPTTextConfigV4:
        raise RuntimeError("custom text config class identity changed")
    if model.config.model_type != MODEL_TYPE or model.config.architectures != [ARCHITECTURE]:
        raise RuntimeError("custom text config serialized identity changed")
    if (
        model.config.tie_word_embeddings is not False
        or model.config.text_only is not True
        or model.config.dense_post_affine is not True
    ):
        raise RuntimeError("custom text safety config changed")
    for name, expected in _pinned_config_values().items():
        actual = getattr(model.config, name, None)
        if name == "layer_types":
            actual, expected = tuple(actual or ()), tuple(expected)
        elif name == "dtype" and actual is not None:
            actual = str(actual).removeprefix("torch.")
        if actual != expected:
            raise RuntimeError(f"custom pinned config changed: {name}")
    if model.config.slicegpt_protocol_version != VERSION:
        raise RuntimeError("custom text protocol identity changed")
    if model.config.slicegpt_adapter_core_version != CORE_VERSION:
        raise RuntimeError("custom adapter-core identity changed")
    if model.config.slicegpt_adapter_core_sha256 != CORE_SOURCE_SHA256:
        raise RuntimeError("custom adapter-core source hash identity changed")
    dimensions = _canonical_dimensions(model.config.residual_dimensions)
    if type(model.model).__name__ != "Gemma3TextModel":
        raise RuntimeError("custom text backbone class changed")
    if model.model.config is not model.config:
        raise RuntimeError("custom text backbone config identity changed")
    if getattr(model.config, "_sliding_window_pattern", None) != 6:
        raise RuntimeError("custom sliding-window pattern identity changed")
    if type(model.model.rotary_emb).__name__ != "Gemma3RotaryEmbedding":
        raise RuntimeError("custom rotary embedding class changed")
    if hasattr(model, "vision_tower") or hasattr(model, "multi_modal_projector"):
        raise RuntimeError("custom text model contains a multimodal surface")
    if len(model.model.layers) != NUM_LAYERS:
        raise RuntimeError("custom text layer count changed")
    q_width = NUM_ATTENTION_HEADS * HEAD_DIM
    kv_width = NUM_KEY_VALUE_HEADS * HEAD_DIM
    for index, (layer, record) in enumerate(zip(model.model.layers, dimensions, strict=True)):
        if type(layer).__name__ != "CompressedGemma3DecoderLayerCore" or layer.layer_idx != index:
            raise RuntimeError(f"custom decoder identity changed at layer {index}")
        input_dimension, attention_dimension, output_dimension = record
        attention, mlp = layer.self_attn, layer.mlp
        if type(attention).__name__ != "Gemma3Attention" or type(mlp).__name__ != "Gemma3MLP":
            raise RuntimeError(f"custom decoder child class changed at layer {index}")
        if layer.config is not model.config or attention.config is not model.config or mlp.config is not model.config:
            raise RuntimeError(f"custom decoder config identity changed at layer {index}")
        if attention.layer_type != LAYER_TYPES[index]:
            raise RuntimeError(f"custom attention type changed at layer {index}")
        if float(attention.scaling) != QUERY_PRE_ATTN_SCALAR**-0.5:
            raise RuntimeError(f"custom attention scaling changed at layer {index}")
        expected_attention = {
            "layer_idx": index,
            "head_dim": HEAD_DIM,
            "num_key_value_groups": NUM_ATTENTION_HEADS // NUM_KEY_VALUE_HEADS,
            "attention_dropout": 0.0,
            "is_causal": True,
            "is_sliding": LAYER_TYPES[index] == "sliding_attention",
            "sliding_window": SLIDING_WINDOW if LAYER_TYPES[index] == "sliding_attention" else None,
        }
        for name, expected_value in expected_attention.items():
            if getattr(attention, name, None) != expected_value:
                raise RuntimeError(f"custom attention field changed: layer {index} {name}")
        if getattr(mlp, "hidden_size", None) != attention_dimension:
            raise RuntimeError(f"custom MLP hidden width changed at layer {index}")
        if getattr(mlp, "intermediate_size", None) != INTERMEDIATE_SIZE:
            raise RuntimeError(f"custom MLP intermediate width changed at layer {index}")
        expected = {
            "q_proj": (q_width, input_dimension),
            "k_proj": (kv_width, input_dimension),
            "v_proj": (kv_width, input_dimension),
            "o_proj": (attention_dimension, q_width),
            "gate_proj": (INTERMEDIATE_SIZE, attention_dimension),
            "up_proj": (INTERMEDIATE_SIZE, attention_dimension),
            "down_proj": (output_dimension, INTERMEDIATE_SIZE),
        }
        for name in PROJECTION_NAMES[:4]:
            module = getattr(attention, name)
            if type(module).__name__ != "Linear" or module.bias is not None:
                raise RuntimeError(f"custom projection identity changed: layer {index} {name}")
            _shape(module, expected[name], f"layer {index} {name}")
        for name in PROJECTION_NAMES[4:]:
            module = getattr(mlp, name)
            if type(module).__name__ != "Linear" or module.bias is not None:
                raise RuntimeError(f"custom projection identity changed: layer {index} {name}")
            _shape(module, expected[name], f"layer {index} {name}")
        if type(attention.q_norm).__name__ != "Gemma3RMSNorm" or type(attention.k_norm).__name__ != "Gemma3RMSNorm":
            raise RuntimeError("custom text model changed protected q/k norms")
        _shape(attention.q_norm, (HEAD_DIM,), f"layer {index} q_norm")
        _shape(attention.k_norm, (HEAD_DIM,), f"layer {index} k_norm")
        if type(layer.input_layernorm) is not CORE.AffineFreeGemmaRMSNorm:
            raise RuntimeError("custom input norm class changed")
        if type(layer.pre_feedforward_layernorm) is not CORE.AffineFreeGemmaRMSNorm:
            raise RuntimeError("custom pre-feedforward norm class changed")
        if type(layer.post_attention_layernorm) is not CORE.DensePostAffineGemmaRMSNorm:
            raise RuntimeError("custom post-attention dense affine class changed")
        if type(layer.post_feedforward_layernorm) is not CORE.DensePostAffineGemmaRMSNorm:
            raise RuntimeError("custom post-feedforward dense affine class changed")
        expected_norm_dimensions = {
            layer.input_layernorm: input_dimension,
            layer.pre_feedforward_layernorm: attention_dimension,
            layer.post_attention_layernorm: attention_dimension,
            layer.post_feedforward_layernorm: output_dimension,
        }
        for norm_module, expected_dimension in expected_norm_dimensions.items():
            if (
                norm_module.dimension != expected_dimension
                or float(norm_module.eps) != RMS_EPS
                or norm_module.compute_dtype is not torch.float32
            ):
                raise RuntimeError(f"custom norm execution identity changed at layer {index}")
        _shape(layer.post_attention_layernorm, (attention_dimension, attention_dimension), f"layer {index} post_attention")
        _shape(layer.post_feedforward_layernorm, (output_dimension, output_dimension), f"layer {index} post_feedforward")
        if tuple(layer.attn_shortcut.shape) != (input_dimension, attention_dimension):
            raise RuntimeError("custom attention shortcut shape changed")
        if tuple(layer.mlp_shortcut.shape) != (attention_dimension, output_dimension):
            raise RuntimeError("custom MLP shortcut shape changed")
    if type(model.model.embed_tokens).__name__ != "Gemma3TextScaledWordEmbedding":
        raise RuntimeError("custom text embedding class changed")
    _shape(model.model.embed_tokens, (VOCAB_SIZE, dimensions[0][0]), "embed_tokens")
    if model.model.embed_tokens.padding_idx != 0:
        raise RuntimeError("custom text embedding padding identity changed")
    if float(model.model.embed_tokens.scalar_embed_scale) != math.sqrt(HIDDEN_SIZE):
        raise RuntimeError("custom text embedding scale changed")
    if type(model.model.norm) is not CORE.AffineFreeGemmaRMSNorm:
        raise RuntimeError("custom final norm class changed")
    if (
        model.model.norm.dimension != dimensions[-1][2]
        or float(model.model.norm.eps) != RMS_EPS
        or model.model.norm.compute_dtype is not torch.float32
    ):
        raise RuntimeError("custom final norm execution identity changed")
    if type(model.lm_head).__name__ != "Linear" or model.lm_head.bias is not None:
        raise RuntimeError("custom LM head class changed")
    _shape(model.lm_head, (VOCAB_SIZE, dimensions[-1][2]), "lm_head")
    if model.lm_head.weight is model.model.embed_tokens.weight:
        raise RuntimeError("custom LM head was retied to embeddings")
    if len(exact_projection_module_names(model)) != NUM_LAYERS * len(PROJECTION_NAMES):
        raise RuntimeError("custom projection count changed")
    state = model.state_dict()
    if set(state) != expected_state_keys():
        raise RuntimeError("custom state-dict name surface changed")
    parameters = dict(model.named_parameters())
    buffers = dict(model.named_buffers())
    expected_parameters = expected_parameter_keys()
    expected_buffers = expected_buffer_keys()
    expected_all_buffers = expected_buffers | expected_nonpersistent_buffer_keys()
    if (
        len(expected_parameters) != 376
        or set(parameters) != expected_parameters
        or any(type(parameter) is not nn.Parameter for parameter in parameters.values())
    ):
        raise RuntimeError("custom named-parameter partition changed")
    if (
        len(expected_buffers) != 68
        or set(buffers) != expected_all_buffers
        or any(type(buffer) is not torch.Tensor for buffer in buffers.values())
    ):
        raise RuntimeError(
            "custom named-buffer partition changed: "
            f"missing={sorted(expected_all_buffers - set(buffers))}, "
            f"extra={sorted(set(buffers) - expected_all_buffers)}"
        )
    if set(state) & set(buffers) != expected_buffers:
        raise RuntimeError("custom persistent shortcut-buffer partition changed")
    if any(tensor.dtype is not torch.bfloat16 for tensor in state.values()):
        raise RuntimeError("custom skeleton and loaded state require exact BF16 storage")
    if require_materialized:
        if getattr(model, "_slicegpt_weights_loaded", None) is not True:
            raise RuntimeError("custom model has not completed strict weight loading")
        tensors = tuple(state.values())
        if any(tensor.device.type == "meta" for tensor in tensors):
            raise RuntimeError("custom loaded model contains meta tensors")
        if any(not bool(torch.isfinite(tensor).all().item()) for tensor in tensors):
            raise RuntimeError("custom loaded model contains non-finite state")
        if model.lm_head.weight.untyped_storage().data_ptr() == model.model.embed_tokens.weight.untyped_storage().data_ptr():
            raise RuntimeError("custom LM head storage was retied to embeddings")
    else:
        if getattr(model, "_slicegpt_weights_loaded", None) is not False:
            raise RuntimeError("compressed skeleton load state changed")
        if any(tensor.device.type != "meta" for tensor in state.values()):
            raise RuntimeError("compressed skeleton must be entirely meta-resident")


def validate_compressed_skeleton(model: Any) -> None:
    """Validate only an unmaterialized deterministic reconstruction skeleton."""

    _validate_text_model(model, require_materialized=False)


def validate_text_model(model: Any) -> None:
    """Validate a fully loaded executable model; there is no caller bypass."""

    _validate_text_model(model, require_materialized=True)


def qualification_status() -> dict[str, Any]:
    return {
        "version": VERSION,
        "canonical_text_model_implemented": True,
        "nonzero_slice_authorized": False,
        "probe2_verdict": None,
        "remaining_gates": [
            "real pinned-runtime materialized extraction and final-fusion equivalence",
            "both sliding/full cache-path generation equivalence",
            "native sharded Safetensors project-loader roundtrip",
            "seven-target LoRA attach/save/reload/merge qualification",
            "sealed nonzero authorization capability issuer",
        ],
    }
