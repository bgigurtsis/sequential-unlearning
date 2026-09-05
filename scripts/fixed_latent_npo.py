"""Conditional summed-answer NPO and summed-answer teacher-to-student KL."""
import math

import torch
import torch.nn.functional as F

try:
    from ordinary_preference_training import summed_suffix_logps
except ModuleNotFoundError:
    from scripts.ordinary_preference_training import summed_suffix_logps


def _validate(student_logits, reference_logits, labels):
    if (not isinstance(student_logits, torch.Tensor)
            or not isinstance(reference_logits, torch.Tensor)
            or not isinstance(labels, torch.Tensor)):
        raise TypeError('logits and labels must be tensors')
    if (student_logits.ndim != 3 or student_logits.shape != reference_logits.shape
            or labels.ndim != 2 or student_logits.shape[:2] != labels.shape
            or student_logits.shape[0] < 1 or student_logits.shape[1] < 2
            or student_logits.shape[2] < 1):
        raise ValueError('matching nonempty [batch,sequence,vocab] logits and [batch,sequence] labels required')
    if (not student_logits.is_floating_point() or not reference_logits.is_floating_point()
            or labels.dtype != torch.int64):
        raise ValueError('floating logits and int64 labels required')
    if student_logits.device != reference_logits.device or labels.device != student_logits.device:
        raise ValueError('logits and labels must share a device')
    if not bool(torch.isfinite(student_logits).all()) or not bool(torch.isfinite(reference_logits).all()):
        raise FloatingPointError('nonfinite logits')
    mask = labels[:, 1:] != -100
    if bool((mask.sum(dim=-1) == 0).any()):
        raise ValueError('every row requires supervised answer tokens after causal shift')
    targets = labels[:, 1:][mask]
    if bool(((targets < 0) | (targets >= student_logits.shape[-1])).any()):
        raise ValueError('supervised labels must be vocabulary indices')
    return mask


def conditional_npo(student_logits, reference_logits, labels, beta=0.1):
    """Return loss, detached per-row NLL margins, and detached multipliers.

    Margins are summed answer NLL(student) minus summed answer NLL(reference).
    References are always detached, including when the caller supplies tensors
    requiring gradients. At a zero margin, the derivative multiplier is one.
    No token-length normalization or prefix weighting is applied.
    """
    if isinstance(beta, bool) or not isinstance(beta, (int, float)) or not math.isfinite(beta) or beta <= 0:
        raise ValueError('beta must be positive and finite')
    _validate(student_logits, reference_logits, labels)
    student_logps, _ = summed_suffix_logps(student_logits, labels)
    reference_logps, _ = summed_suffix_logps(reference_logits.detach(), labels)
    margins = reference_logps - student_logps
    scaled = beta * margins
    if not bool(torch.isfinite(scaled).all()):
        raise FloatingPointError('nonfinite NPO margins')
    loss = -(2.0 / beta) * F.logsigmoid(scaled).mean()
    if not bool(torch.isfinite(loss)):
        raise FloatingPointError('nonfinite NPO loss')
    return loss, margins.detach(), (2.0 * torch.sigmoid(-scaled)).detach()


def ordinary_kl(student_logits, clean_logits, labels):
    """Mean over records of SUM answer-token KL(clean teacher || student).

    Only positions predicting a supervised answer label contribute. Padding and
    prompt prediction positions are excluded. The clean teacher is detached.
    Summed sequence units intentionally give longer answers more total weight.
    """
    mask = _validate(student_logits, clean_logits, labels)
    student_logps = F.log_softmax(student_logits[:, :-1, :].float(), dim=-1)
    teacher_logps = F.log_softmax(clean_logits.detach()[:, :-1, :].float(), dim=-1)
    token_kl = F.kl_div(student_logps, teacher_logps, reduction='none', log_target=True).sum(dim=-1)
    loss = (token_kl * mask).sum(dim=-1).mean()
    if not bool(torch.isfinite(loss)):
        raise FloatingPointError('nonfinite ordinary KL loss')
    return loss
