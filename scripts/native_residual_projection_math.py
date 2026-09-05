"""Native residual-range restriction, inspired by concept erasure, not LEACE.

All basis calculations use CPU float64. Weight projection uses chunked FP32
arithmetic and one BF16 publication cast. Exact real-arithmetic subspace proofs
do not imply exact BF16 invariance or semantic knowledge deletion.
"""
from __future__ import annotations

import math


def _tensor(value, name, ndim, dtype, *, torch, allow_empty=False):
    if not isinstance(value, torch.Tensor) or value.ndim != ndim:
        raise ValueError(f"{name} must have {ndim} dimensions")
    if value.device.type != "cpu" or value.dtype != dtype:
        raise ValueError(f"{name} must be CPU {dtype}")
    if not bool(torch.isfinite(value).all()):
        raise ValueError(f"{name} must be finite")
    if not allow_empty and value.numel() == 0:
        raise ValueError(f"{name} must not be empty")


def _basis(value, *, torch):
    _tensor(value, "basis", 2, torch.float64, torch=torch, allow_empty=True)
    dimension, rank = value.shape
    if dimension <= 0 or rank > dimension:
        raise ValueError("basis dimensions invalid")
    error = float((value.T @ value - torch.eye(rank, dtype=torch.float64)).abs().max()) if rank else 0.0
    if error > 1e-10:
        raise ValueError("basis must have orthonormal columns")
    return error


def _scale(value, dimension, *, torch):
    _tensor(value, "normalization scale D", 1, torch.float64, torch=torch)
    if value.shape[0] != dimension:
        raise ValueError("normalization scale dimension mismatch")


def orthonormal_basis(columns, *, torch):
    """Full numerical column span; rank zero is valid and means no restriction."""
    _tensor(columns, "columns", 2, torch.float64, torch=torch, allow_empty=True)
    if columns.shape[0] <= 0:
        raise ValueError("columns must have positive ambient dimension")
    if columns.shape[1]:
        left, singular, _ = torch.linalg.svd(columns, full_matrices=False)
        tolerance = 32 * torch.finfo(torch.float64).eps * max(columns.shape) * float(singular[0])
        rank = int((singular > tolerance).sum())
        basis = left[:, :rank].contiguous()
        if rank:
            pivots = basis.abs().argmax(dim=0)
            basis = (basis * torch.sign(basis[pivots, torch.arange(rank)])).contiguous()
    else:
        singular = torch.empty(0, dtype=torch.float64)
        tolerance, rank = 0.0, 0
        basis = columns.clone()
    error = _basis(basis, torch=torch)
    original_norm = float(torch.linalg.vector_norm(columns))
    residual = float(torch.linalg.vector_norm(columns - basis @ (basis.T @ columns)))
    return basis, {
        "shape": list(columns.shape), "rank": rank, "rank_tolerance": tolerance,
        "singular_values": singular.tolist(), "orthogonality_max_abs": error,
        "span_residual_l2": residual,
        "span_residual_relative": residual / max(original_norm, 1e-30),
        "method": "CPU float64 thin SVD; 32*eps64*max(shape)*smax; full numerical rank",
    }


def closure_basis(concept_basis, final_scale, *, torch):
    """Span(U, D_final U) protects original U before and after final RMSNorm."""
    _basis(concept_basis, torch=torch)
    _scale(final_scale, concept_basis.shape[0], torch=torch)
    columns = torch.cat((concept_basis, final_scale[:, None] * concept_basis), dim=1)
    basis, record = orthonormal_basis(columns, torch=torch)
    record.update({"concept_rank": concept_basis.shape[1], "maximum_closure_rank": min(columns.shape),
                   "scope": "original U absent before/after final norm in exact arithmetic; not all closure directions after final norm"})
    return basis, record


def _project(weight, basis, constraint, *, torch, device, chunk, side):
    _tensor(weight, "weight", 2, torch.bfloat16, torch=torch)
    _basis(basis, torch=torch)
    _tensor(constraint, "constraint columns", 2, torch.float64, torch=torch, allow_empty=True)
    if isinstance(chunk, bool) or not isinstance(chunk, int) or chunk <= 0:
        raise ValueError("chunk must be a positive integer")
    dimension = weight.shape[0 if side == "left" else 1]
    if basis.shape[0] != dimension or constraint.shape[0] != dimension:
        raise ValueError("weight/basis/constraint dimensions differ")
    rank = basis.shape[1]
    q = basis.to(device=device, dtype=torch.float32)
    c = constraint.to(device=device)
    out = torch.empty_like(weight)
    names = ("original", "precast", "removed", "native", "rounding",
             "original_constraint", "precast_constraint", "native_constraint")
    squares = dict.fromkeys(names, 0.0)
    maximum_rounding = 0.0
    axis_size = weight.shape[1 if side == "left" else 0]
    for start in range(0, axis_size, chunk):
        region = (slice(None), slice(start, start + chunk)) if side == "left" else (slice(start, start + chunk), slice(None))
        native = weight[region].to(device=device)
        original = native.float()
        if rank == 0:
            projected = original
            removed = torch.zeros_like(original)
            published = native.clone()
        elif rank == dimension:
            projected = torch.zeros_like(original)
            removed = original
            published = projected.bfloat16()
        else:
            removed = q @ (q.T @ original) if side == "left" else (original @ q) @ q.T
            projected = original - removed
            published = projected.bfloat16()
            # Preserve native identity bytes wherever the computed correction is zero.
            published = torch.where(removed == 0, native, published)
        if not bool(torch.isfinite(projected).all()) or not bool(torch.isfinite(published).all()):
            raise RuntimeError("nonfinite projected weight")
        out[region] = published.cpu()
        original64, projected64, native64 = original.double(), projected.double(), published.double()
        rounding = native64 - projected64
        maximum_rounding = max(maximum_rounding, float(rounding.abs().max()))
        actions = [c.T @ x if side == "left" else x @ c for x in (original64, projected64, native64)]
        measured = (original64, projected64, removed.double(), native64, rounding, *actions)
        for name, value in zip(names, measured):
            amount = float(value.square().sum())
            if not math.isfinite(amount):
                raise RuntimeError(f"nonfinite diagnostic {name}")
            squares[name] += amount
    norms = {name + "_l2": math.sqrt(value) for name, value in squares.items()}
    original_norm = norms["original_l2"]
    constraint_norm = float(torch.linalg.vector_norm(constraint))
    pythagorean = abs(squares["original"] - squares["precast"] - squares["removed"]) / max(squares["original"], 1e-30)
    relative_residual = norms["precast_constraint_l2"] / max(original_norm * constraint_norm, 1e-30)
    if pythagorean > 1e-5 or norms["precast_l2"] > original_norm * (1 + 1e-5) + 1e-30:
        raise RuntimeError("FP32 projection failed contraction/Pythagorean gate")
    if relative_residual > 1e-5:
        raise RuntimeError("FP32 projection failed constraint residual gate")
    return out, {
        **norms, "device": str(device), "chunk": chunk, "side": side, "rank": rank,
        "native_identity": rank == 0, "full_rank_annihilation": rank == dimension,
        "constraint_columns_l2": constraint_norm,
        "precast_constraint_relative_to_weight_times_constraint": relative_residual,
        "native_constraint_relative_to_weight_times_constraint": norms["native_constraint_l2"] / max(original_norm * constraint_norm, 1e-30),
        "native_constraint_relative_to_original_constraint": norms["native_constraint_l2"] / max(norms["original_constraint_l2"], 1e-30),
        "pythagorean_relative_error": pythagorean,
        "precast_retained_norm_ratio": norms["precast_l2"] / max(original_norm, 1e-30),
        "native_retained_norm_ratio": norms["native_l2"] / max(original_norm, 1e-30),
        "maximum_rounding_error": maximum_rounding,
        "ideal_projector_operator_norm": 0.0 if rank == dimension else 1.0,
        "postcast_exact_preservation_claimed": False,
    }


def project_write(weight, scale, residual_basis, *, torch, device="cpu", column_chunk=128):
    """Project a pre-postnorm write W to satisfy V^T D W=0 without D inverse."""
    _basis(residual_basis, torch=torch)
    _scale(scale, residual_basis.shape[0], torch=torch)
    constraint = scale[:, None] * residual_basis
    basis, basis_record = orthonormal_basis(constraint, torch=torch)
    output, record = _project(weight, basis, constraint, torch=torch, device=device, chunk=column_chunk, side="left")
    record.update({"write_basis": basis_record, "residual_rank": residual_basis.shape[1],
                   "zero_scale_coordinates": int((scale == 0).sum()),
                   "negative_scale_coordinates": int((scale < 0).sum())})
    return output, record


def project_embedding(weight, residual_basis, *, torch, device="cpu", row_chunk=128):
    """Right-project native embedding rows; caller must preserve tied-head aliases."""
    return _project(weight, residual_basis, residual_basis, torch=torch, device=device, chunk=row_chunk, side="right")
