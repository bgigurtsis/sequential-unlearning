"""Compare sequence-logistic and token-logistic NPO with matched initial gradients."""
import math

import torch
import torch.nn.functional as F
try:
    from fixed_latent_npo import _validate
except ModuleNotFoundError:
    from scripts.fixed_latent_npo import _validate


def clean_npo_loss(student_logits, reference_logits, labels, mode, beta=0.1):
    """Return scalar loss and detached per-record pressure diagnostics.

    Both losses sum supervised answer tokens within each record and average
    records. Sequence mode applies one logistic to each summed NLL margin;
    token mode applies a logistic to each token's margin, then sums. References
    never receive gradients. Token pressure summaries exclude masked positions.
    """
    if mode not in ('sequence', 'token'):
        raise ValueError('mode must be sequence or token')
    if isinstance(beta, bool) or not isinstance(beta, (int, float)) or not math.isfinite(beta) or beta <= 0:
        raise ValueError('beta must be positive and finite')
    mask = _validate(student_logits, reference_logits, labels)
    targets = labels[:, 1:].masked_fill(~mask, 0).unsqueeze(-1)
    student_lp = F.log_softmax(student_logits[:, :-1].float(), dim=-1).gather(-1, targets).squeeze(-1)
    reference_lp = F.log_softmax(reference_logits.detach()[:, :-1].float(), dim=-1).gather(-1, targets).squeeze(-1)
    token_margins = (reference_lp - student_lp).masked_fill(~mask, 0)
    sequence_margins = token_margins.sum(dim=-1)
    if not bool(torch.isfinite(beta*token_margins).all()) or not bool(torch.isfinite(beta*sequence_margins).all()):
        raise FloatingPointError('nonfinite NPO margins')
    if mode == 'sequence':
        loss = -(2.0/beta)*F.logsigmoid(beta*sequence_margins).mean()
    else:
        loss = -(2.0/beta)*(F.logsigmoid(beta*token_margins)*mask).sum(dim=-1).mean()
    if not bool(torch.isfinite(loss)):
        raise FloatingPointError('nonfinite NPO loss')
    with torch.no_grad():
        tm = 2.0*torch.sigmoid(-beta*token_margins)
        counts = mask.sum(dim=-1)
        diagnostics = {'sequence_margins': sequence_margins.detach(),
            'sequence_multipliers': 2.0*torch.sigmoid(-beta*sequence_margins),
            'token_multiplier_mean': (tm*mask).sum(dim=-1)/counts,
            'token_multiplier_min': tm.masked_fill(~mask, float('inf')).min(dim=-1).values,
            'token_multiplier_max': tm.masked_fill(~mask, -float('inf')).max(dim=-1).values,
            'supervised_tokens': counts}
    return loss, diagnostics
