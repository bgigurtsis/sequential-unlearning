"""Experimental Gemma-3 SliceGPT algebra; not a launchable slicer.

Row-vector convention is used below.  If an activation ``x`` is represented
in basis ``Q_in`` as ``x @ Q_in``, a Gemma-3 residual branch that exits in
``Q_out`` needs:

* pre-RMS affine scale fused as ``W @ diag(1+w) @ Q_in``;
* output projection ``Q_out.T @ W``;
* post-RMS dense scale ``Q_out.T @ diag(1+w) @ Q_out``;
* residual shortcut ``Q_in.T @ Q_out``.

At sliced width, Q matrices contain only retained columns.  The same formulas
define the approximation, but only full-width orthogonal Q is equivalence-
preserving.  Gemma-3 q_norm/k_norm are intentionally absent: they operate in
head space and must not be globally replaced or fused.

This file provides small tensor operations and a zero-sparsity identity-basis
fusion for an implementation harness.  It does not implement calibration,
PCA, slicing, serialization, or a scientific pilot.
"""

from __future__ import annotations


MATH_VERSION = "gemma3_slicegpt_sandwich_norm_derivation_v0_unvalidated"


def affine_scale(norm_weight):
    """Gemma-3 RMSNorm uses (1 + weight), unlike Llama-style direct weight."""
    return norm_weight + 1.0


def fuse_pre_norm_linear(weight, norm_weight, q_in):
    """Return W @ diag(1+w) @ Q_in without constructing the diagonal."""
    scale = affine_scale(norm_weight).to(device=weight.device, dtype=weight.dtype)
    return (weight * scale.unsqueeze(0)) @ q_in.to(weight.device, weight.dtype)


def rotate_output_linear(weight, q_out):
    """Return Q_out.T @ W for an output represented in the Q_out basis."""
    return q_out.to(weight.device, weight.dtype).transpose(0, 1) @ weight


def dense_post_norm_scale(norm_weight, q_out, compute_dtype=None):
    """Return Q_out.T @ diag(1+w) @ Q_out in explicit high precision.

    The caller may choose ``compute_dtype``.  FP64 is the default derivation
    and construction precision; casting the resulting matrix for storage is a
    separate, protocol-level choice that must be measured rather than hidden.
    """
    import torch

    dtype = torch.float64 if compute_dtype is None else compute_dtype
    q = q_out.to(norm_weight.device, dtype)
    scale = affine_scale(norm_weight.to(dtype))
    return q.transpose(0, 1) @ (scale.unsqueeze(1) * q)


def residual_shortcut(q_in, q_out):
    """Return Q_in.T @ Q_out, including rectangular sliced shortcuts."""
    return q_in.transpose(0, 1) @ q_out.to(q_in.device, q_in.dtype)


def rotated_post_norm(hidden_states, dense_scale, eps, compute_dtype=None):
    """Apply affine-free RMS normalization followed by its rotated dense scale."""
    import torch

    dtype = hidden_states.dtype
    work_dtype = torch.float32 if compute_dtype is None else compute_dtype
    values = hidden_states.to(work_dtype)
    values = values * torch.rsqrt(values.pow(2).mean(-1, keepdim=True) + eps)
    # Gemma-3 performs normalization and learned affine work in FP32, then
    # casts the final result.  Casting before the dense affine would add an
    # avoidable BF16 error not present in the source model.
    return (values @ dense_scale.to(values.device, work_dtype)).to(dtype)


def _language_model(model):
    candidates = (
        getattr(getattr(model, "model", None), "language_model", None),
        getattr(model, "language_model", None),
        getattr(model, "model", None),
    )
    for candidate in candidates:
        if candidate is not None and hasattr(candidate, "layers"):
            return candidate
    raise RuntimeError("cannot locate Gemma-3 language-model layers")


def validate_gemma3_layer_surface(layer, index):
    required = (
        "input_layernorm",
        "post_attention_layernorm",
        "pre_feedforward_layernorm",
        "post_feedforward_layernorm",
        "self_attn",
        "mlp",
    )
    if any(not hasattr(layer, name) for name in required):
        raise RuntimeError(f"layer {index} is not the required Gemma-3 sandwich-norm surface")
    if any(
        not hasattr(layer.self_attn, name)
        for name in ("q_proj", "k_proj", "v_proj", "o_proj", "q_norm", "k_norm")
    ):
        raise RuntimeError(f"layer {index} lacks the required Gemma-3 attention surface")
    if any(not hasattr(layer.mlp, name) for name in ("gate_proj", "up_proj", "down_proj")):
        raise RuntimeError(f"layer {index} lacks the required Gemma-3 MLP surface")
    norms = (
        layer.input_layernorm,
        layer.post_attention_layernorm,
        layer.pre_feedforward_layernorm,
        layer.post_feedforward_layernorm,
        layer.self_attn.q_norm,
        layer.self_attn.k_norm,
    )
    if len({id(norm) for norm in norms}) != len(norms):
        raise RuntimeError(f"layer {index} unexpectedly aliases distinct Gemma-3 norms")


def apply_identity_basis_pre_norm_fusion(model):
    """Fuse only Gemma-3 pre norms at zero sparsity for an equivalence harness.

    This is deliberately narrower than a SliceGPT adapter.  Q is identity,
    post norms remain in place, output projections and residuals are unchanged,
    and q_norm/k_norm are never touched.  Moving a learned scale into BF16
    linear weights can itself introduce rounding; the harness measures that
    rather than assuming equivalence.
    """
    import torch

    language_model = _language_model(model)
    records = []
    with torch.no_grad():
        for index, layer in enumerate(language_model.layers):
            validate_gemma3_layer_surface(layer, index)
            input_scale = affine_scale(layer.input_layernorm.weight.float())
            for projection_name in ("q_proj", "k_proj", "v_proj"):
                projection = getattr(layer.self_attn, projection_name)
                projection.weight.mul_(input_scale.to(projection.weight.device, projection.weight.dtype))
            layer.input_layernorm.weight.zero_()

            feedforward_scale = affine_scale(layer.pre_feedforward_layernorm.weight.float())
            for projection_name in ("gate_proj", "up_proj"):
                projection = getattr(layer.mlp, projection_name)
                projection.weight.mul_(
                    feedforward_scale.to(projection.weight.device, projection.weight.dtype)
                )
            layer.pre_feedforward_layernorm.weight.zero_()
            records.append(
                {
                    "layer": index,
                    "attention_pre_norm_fused_into": ["q_proj", "k_proj", "v_proj"],
                    "feedforward_pre_norm_fused_into": ["gate_proj", "up_proj"],
                    "post_norms_unchanged": True,
                    "q_norm_k_norm_unchanged": True,
                    "basis": "identity",
                    "sliced_dimensions": 0,
                }
            )
    return records
