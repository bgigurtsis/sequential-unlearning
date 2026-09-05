"""Mean-protected linear read erasure; not covariance-optimal affine LEACE.

Fit in CPU float64. Fold W T with factorized FP32 arithmetic and one native
BF16 cast. Local mean/contrast constraints do not establish semantic erasure.
"""
from __future__ import annotations

import math

try:
    import native_residual_projection_math as geometry
except ModuleNotFoundError:
    from scripts import native_residual_projection_math as geometry


def _means(value, name, *, torch):
    geometry._tensor(value, name, 2, torch.float64, torch=torch)
    if value.shape[0] != 2 or value.shape[1] < 1:
        raise ValueError(name + ' must have shape [2,hidden]')


def _factors(c, right, *, torch):
    geometry._tensor(c, 'C', 2, torch.float64, torch=torch, allow_empty=True)
    geometry._tensor(right, 'right', 2, torch.float64, torch=torch, allow_empty=True)
    if c.shape[0] < 1 or c.shape[1] not in (0, 1, 2) or right.shape != (c.shape[1], c.shape[0]):
        raise ValueError('Invalid oblique factor shapes')


def operator_norm(c, right, *, torch):
    """Exact small-span singular norm; the orthogonal complement is identity."""
    _factors(c, right, torch=torch)
    if c.shape[1] == 0:
        return 1.0
    columns = torch.cat((c, right.T), dim=1)
    norms = columns.norm(dim=0)
    columns = columns[:, norms > 0] / norms[norms > 0]
    q, _ = geometry.orthonormal_basis(columns, torch=torch)
    compressed = torch.eye(q.shape[1], dtype=torch.float64) - (q.T @ c) @ (right @ q)
    compressed_norm = float(torch.linalg.svdvals(compressed)[0]) if q.shape[1] else 0.0
    return max(compressed_norm, 1.0 if q.shape[1] < c.shape[0] else 0.0)


def fit_oblique(positive, negative, rank, *, torch):
    """Return C[d,rank], pinv(S)[rank,d], and frozen-gate diagnostics."""
    if type(rank) is not int or rank not in (1, 2):
        raise ValueError('Only fixed ranks 1 and 2 are supported')
    _means(positive, 'positive means', torch=torch)
    _means(negative, 'negative means', torch=torch)
    if positive.shape != negative.shape:
        raise ValueError('Positive and negative means differ in shape')
    contrasts = (positive - negative).T.contiguous()
    norms = contrasts.norm(dim=0)
    if not bool((norms >= 1e-12).all()):
        raise ValueError('Original contrast below frozen nonzero threshold')
    unit = contrasts / norms
    c = (unit.mean(dim=1, keepdim=True) if rank == 1 else unit).contiguous()
    if float(c.norm()) < 1e-12:
        raise ValueError('Pooled contrast cancels below frozen threshold')
    m = negative.T.contiguous()
    r, rdiag = geometry.orthonormal_basis(m, torch=torch)
    s = c - r @ (r.T @ c)
    left, singular, vh = torch.linalg.svd(s, full_matrices=False)
    # Scale absolute rank tolerance to C, not tiny residual S. A rank1 residual
    # made entirely of roundoff otherwise always has a singular ratio of one.
    tolerance = 32 * torch.finfo(torch.float64).eps * max(c.shape) * float(torch.linalg.svdvals(c)[0])
    if singular.numel() != rank or int((singular > tolerance).sum()) != rank:
        raise ValueError('Protected contrast is numerically rank deficient')
    ratio = float(singular[-1] / singular[0])
    if ratio < 1e-6:
        raise ValueError('Protected contrast fails singular-ratio guard')
    right = ((vh.T / singular) @ left.T).contiguous()
    contrast_error = float((c - c @ (right @ c)).norm()) / float(c.norm())
    mean_error = float((c @ (right @ m)).norm()) / max(float(m.norm()), 1e-30)
    if contrast_error > 1e-10 or mean_error > 1e-10:
        raise RuntimeError('Oblique map fails exact mean/contrast constraints')
    gain = operator_norm(c, right, torch=torch)
    if not math.isfinite(gain) or gain > 4.0:
        raise ValueError('Oblique map exceeds frozen operator norm4')
    return c, right, {
        'rank': rank, 'input_features': c.shape[0],
        'contrast_rule': 'mean of two unit columns' if rank == 1 else 'two unit columns',
        'original_contrast_norms': norms.tolist(), 'negative_span': rdiag,
        'protected_singular_values': singular.tolist(), 'absolute_rank_tolerance': tolerance,
        'singular_ratio': ratio, 'operator_norm': gain,
        'contrast_relative_error': contrast_error, 'negative_mean_relative_error': mean_error,
        'method': 'T=I-C pinv((I-R R^T)C); R=orth(two raw negative means)',
        'claim': 'Stored local means only; not semantic deletion or unchanged individual records.',
    }


def fold_weight(weight, c, right, negative_means, *, torch, device=None, row_chunk=512):
    """Fold W T into native BF16 weight; return on the original weight device.

    Empty compatible factors provide a byte-preserving native identity path.
    Actual BF16 contrast and mean-output errors are measured, not assumed zero.
    """
    if not isinstance(weight, torch.Tensor) or weight.ndim != 2 or weight.dtype != torch.bfloat16:
        raise ValueError('Weight must be native BF16 matrix')
    if min(weight.shape) < 1 or weight.device.type not in ('cpu', 'cuda') or not bool(torch.isfinite(weight).all()):
        raise ValueError('Weight must be finite nonempty CPU/CUDA tensor')
    _factors(c, right, torch=torch)
    _means(negative_means, 'negative means', torch=torch)
    if weight.shape[1] != c.shape[0] or negative_means.shape[1] != c.shape[0]:
        raise ValueError('Weight and factor dimensions differ')
    if type(row_chunk) is not int or row_chunk < 1:
        raise ValueError('row_chunk must be a positive integer')
    if c.shape[1] == 0:
        return weight.clone(), {'native_identity': True, 'changed': False, 'rank': 0}
    execution = torch.device(device) if device is not None else weight.device
    if execution.type not in ('cpu', 'cuda'):
        raise ValueError('Execution must use CPU or CUDA')
    c32, right32 = c.to(execution, torch.float32), right.to(execution, torch.float32)
    c64, m64 = c.to(execution), negative_means.T.contiguous().to(execution)
    output = torch.empty_like(weight)
    sums = dict(weight=0., output=0., delta=0., rounding=0., original_c=0., pre_c=0., native_c=0., original_m=0., pre_m_error=0., native_m_error=0.)
    with torch.no_grad():
        for start in range(0, weight.shape[0], row_chunk):
            original = weight[start:start + row_chunk].to(execution, torch.float32)
            pre = original - (original @ c32) @ right32
            native = pre.to(torch.bfloat16)
            if not bool(torch.isfinite(native).all()) or not bool(torch.isfinite(pre).all()):
                raise RuntimeError('Nonfinite folded weight')
            a, p, n = original.double(), pre.double(), native.double()
            values = dict(weight=a, output=n, delta=n-a, rounding=n-p, original_c=a@c64,
                          pre_c=p@c64, native_c=n@c64, original_m=a@m64,
                          pre_m_error=(p-a)@m64, native_m_error=(n-a)@m64)
            for key, value in values.items():
                sums[key] += float(value.square().sum())
            output[start:start + row_chunk].copy_(native.to(weight.device))
    norms = {key + '_l2': math.sqrt(value) for key, value in sums.items()}
    denominator = max(norms['weight_l2'] * float(c.norm()), 1e-30)
    native_relative = norms['native_c_l2'] / denominator
    if native_relative > .01:
        raise RuntimeError('Actual native weight contrast residual exceeds frozen .01 gate')
    return output, {
        **norms, 'rank': c.shape[1], 'shape': list(weight.shape),
        'native_identity': False, 'execution_device': str(execution), 'output_device': str(weight.device),
        'row_chunk': row_chunk, 'arithmetic': 'FP32 factorized W-(WC)right; one BF16 cast; float64 diagnostics',
        'precast_weight_constraint_relative_to_weight_times_C': norms['pre_c_l2'] / denominator,
        'native_weight_constraint_relative_to_weight_times_C': native_relative,
        'native_mean_output_relative_error': norms['native_m_error_l2'] / max(norms['original_m_l2'], 1e-30),
        'precast_mean_output_relative_error': norms['pre_m_error_l2'] / max(norms['original_m_l2'], 1e-30),
        'claim': 'Native residual measured; no exact BF16 preservation or behavioral guarantee.',
    }
