"""Numerics for the frozen target-constrained rounded-E90 repair experiment.

The guarantee is a sampled linear-action constraint before native rounding,
not preservation of an autoregressive model's behavior or global knowledge.
"""
from __future__ import annotations

import math


def _finite_matrix(value, label, *, torch, dtype=None, cpu=False):
    if not isinstance(value, torch.Tensor) or value.ndim != 2:
        raise ValueError(f"{label} must be a matrix")
    if min(value.shape) <= 0 or not bool(torch.isfinite(value).all()):
        raise ValueError(f"{label} must be nonempty and finite")
    if dtype is not None and value.dtype != dtype:
        raise ValueError(f"{label} has wrong dtype")
    if cpu and value.device.type != "cpu":
        raise ValueError(f"{label} must be on CPU")


def target_basis(keys, *, torch):
    """Return the entire numerical row span of finite, normalized donor keys."""
    _finite_matrix(keys, "target keys", torch=torch, dtype=torch.float64, cpu=True)
    norms = torch.linalg.vector_norm(keys, dim=1)
    if float((norms - 1).abs().max()) > 1e-12:
        raise ValueError("target keys must be unit normalized")
    _, singular, right = torch.linalg.svd(keys, full_matrices=False)
    if not bool(torch.isfinite(singular).all()) or float(singular[0]) <= 0:
        raise ValueError("target keys have no finite positive singular value")
    tolerance = 32 * torch.finfo(torch.float64).eps * max(keys.shape) * float(singular[0])
    rank = int((singular > tolerance).sum())
    if rank == 0:
        raise ValueError("target keys have zero numerical rank")
    basis = right[:rank].T.contiguous()
    # The projector is sign invariant; canonical signs stabilize saved artifacts.
    pivots = basis.abs().argmax(dim=0)
    signs = torch.sign(basis[pivots, torch.arange(rank)])
    basis = (basis * signs).contiguous()
    orthogonality = float((basis.T @ basis - torch.eye(rank, dtype=torch.float64)).abs().max())
    residual = keys - (keys @ basis) @ basis.T
    span_error = float(torch.linalg.vector_norm(residual) / torch.linalg.vector_norm(keys))
    if orthogonality > 1e-10 or span_error > 1e-8:
        raise RuntimeError("target basis failed orthogonality or span reconstruction")
    return basis, {
        "key_count": int(keys.shape[0]), "input_features": int(keys.shape[1]),
        "rank": rank, "rank_tolerance": tolerance,
        "singular_values": singular.tolist(), "full_feature_span": rank == keys.shape[1],
        "orthogonality_max_abs_error": orthogonality,
        "span_relative_frobenius_error": span_error,
        "method": "float64 CPU thin SVD of uncentered unit-key rows; full numerical span",
    }


def constrain_tensor(donor, projected, basis, target_keys, *, torch, device="cpu", row_chunk=128):
    """Nearest correction to E90-donor with zero action on the target span.

FP32 arithmetic has explicit residual gates. All actual post-BF16 action is
measured separately. No cross-device or cross-chunk bitwise claim is made.
"""
    if isinstance(row_chunk, bool) or not isinstance(row_chunk, int) or row_chunk <= 0:
        raise ValueError("row_chunk must be a positive integer")
    for value, name in ((donor, "donor"), (projected, "projected")):
        _finite_matrix(value, name, torch=torch, dtype=torch.bfloat16, cpu=True)
    if donor.shape != projected.shape:
        raise ValueError("endpoint tensor shapes differ")
    _finite_matrix(basis, "basis", torch=torch, dtype=torch.float64, cpu=True)
    _finite_matrix(target_keys, "target keys", torch=torch, dtype=torch.float64, cpu=True)
    if basis.shape[0] != donor.shape[1] or target_keys.shape[1] != donor.shape[1] or basis.shape[1] > basis.shape[0]:
        raise ValueError("basis/key feature dimensions differ from weights")
    rank = int(basis.shape[1])
    orthogonality = float((basis.T @ basis - torch.eye(rank, dtype=torch.float64)).abs().max())
    key_norm = float(torch.linalg.vector_norm(target_keys))
    unit_error = float((torch.linalg.vector_norm(target_keys, dim=1) - 1).abs().max())
    span_error = float(torch.linalg.vector_norm(target_keys - (target_keys @ basis) @ basis.T)) / max(key_norm, 1e-30)
    if orthogonality > 1e-10 or span_error > 1e-8 or unit_error > 1e-12:
        raise ValueError("basis does not orthonormally span unit target keys")
    q = basis.to(device=device, dtype=torch.float32)
    f = target_keys.T.to(device=device, dtype=torch.float32)
    output = torch.empty_like(donor)
    quantities = ("original_correction", "constrained_correction", "removed_correction",
                  "precast_target_basis_action", "original_target_key_action", "precast_target_key_action",
                  "actual_correction", "actual_target_basis_action", "actual_target_key_action", "rounding_error")
    squares = dict.fromkeys(quantities, 0.0)
    maximum_rounding_error = 0.0
    full_span = rank == donor.shape[1]
    for start in range(0, donor.shape[0], row_chunk):
        stop = min(start + row_chunk, donor.shape[0])
        native = donor[start:stop]
        left = native.to(device=device, dtype=torch.float32)
        original = projected[start:stop].to(device=device, dtype=torch.float32) - left
        # For a full feature span the unique feasible correction is exactly zero.
        # Also preserve native signed zeros/tiny values on a zero correction.
        if full_span:
            correction = torch.zeros_like(original)
            removed = original
        else:
            removed = (original @ q) @ q.T
            correction = original - removed
        if not bool(torch.isfinite(correction).all()) or not bool(torch.isfinite(original).all()):
            raise RuntimeError("nonfinite FP32 correction")
        value = (left + correction).to(dtype=donor.dtype)
        zero = correction == 0
        value = torch.where(zero, native.to(device=device), value)
        if not bool(torch.isfinite(value).all()):
            raise RuntimeError("nonfinite native output")
        output[start:stop] = value.cpu()
        actual = value.float() - left
        rounding = actual - correction
        maximum_rounding_error = max(maximum_rounding_error, float(rounding.abs().max()))
        measured = (original, correction, removed, correction @ q, original @ f,
                    correction @ f, actual, actual @ q, actual @ f, rounding)
        for name, matrix in zip(quantities, measured):
            amount = float(matrix.double().square().sum())
            if not math.isfinite(amount):
                raise RuntimeError(f"nonfinite diagnostic: {name}")
            squares[name] += amount
    norms = {key + "_l2": math.sqrt(value) for key, value in squares.items()}
    original_norm = norms["original_correction_l2"]
    correction_norm = norms["constrained_correction_l2"]
    cq_relative = norms["precast_target_basis_action_l2"] / max(correction_norm, 1e-30)
    cf_relative = norms["precast_target_key_action_l2"] / max(original_norm * key_norm, 1e-30)
    pythagorean = abs(squares["original_correction"] - squares["constrained_correction"] - squares["removed_correction"]) / max(squares["original_correction"], 1e-30)
    if cq_relative > 1e-5 or cf_relative > 1e-5:
        raise RuntimeError(f"FP32 target-action residual exceeds gate: CQ={cq_relative}, CF={cf_relative}")
    if correction_norm > original_norm * (1 + 1e-5) + 1e-30 or pythagorean > 1e-5:
        raise RuntimeError("correction failed contraction or Pythagorean projection gate")
    return output, {
        **norms, "row_chunk": row_chunk, "device": str(device), "target_rank": rank,
        "full_feature_span": full_span, "basis_orthogonality_max_abs_error": orthogonality,
        "key_span_relative_frobenius_error": span_error,
        "precast_CQ_relative_to_C": cq_relative, "precast_CF_relative_to_C0_times_F": cf_relative,
        "precast_CF_relative_to_C0F": norms["precast_target_key_action_l2"] / max(norms["original_target_key_action_l2"], 1e-30),
        "actual_CF_relative_to_C0F": norms["actual_target_key_action_l2"] / max(norms["original_target_key_action_l2"], 1e-30),
        "pythagorean_relative_error": pythagorean, "maximum_rounding_error": maximum_rounding_error,
        "postcast_exact_preservation_claimed": False,
    }
