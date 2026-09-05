"""Bounded-divergence JensUn erasure with LoRA or full-model updates.

Why bounded: unbounded objectives (GA/NPO) have no fixed point, so step
count is not a dial - they run until something breaks, which is the Run
26/27 cliff.  A bounded divergence saturates at a defined target, so the
loss value itself says how far the erasure has gone and early stopping at
the semantic bar becomes a real control (singh-2025-jensun,
huutien-2024-adaptive-rmu).

Objective, per answer token:
    forget = JSD(p_model || one_hot("No idea" target token))
    retain = JSD(p_model || p_clean) on retain/chat-retain text
    loss   = forget_weight * forget + retain_weight * retain

This follows Singh et al.'s JensUn objective: the fixed non-informative target
is repeated over the original answer-token positions, and the retain target is
the frozen clean model's distribution. Both losses are bounded in [0, log 2].

The certification default follows ELM: rank-4 LoRA over a narrow early-layer
band (layers 4-10). ``--parameterization full`` provides the full-model control
used by the published JensUn experiments.

Precision: fp32 master weights during optimisation.  Pure-BF16 updates
silently cancel sub-ULP gradients (zamirai-2020-revisiting-bf16), which at
this lr would masquerade as plasticity loss.  The base stays BF16; only
trainable LoRA parameters are cast to fp32, and the script asserts it.
"""

import argparse
import json
import math
import random
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer
try:
    from answer_prefix_conditioning import answer_prefix_count, encode_answer_sequence, validate_conditioning_records
except ModuleNotFoundError:
    from scripts.answer_prefix_conditioning import answer_prefix_count, encode_answer_sequence, validate_conditioning_records
try:
    from prefix_unfamiliarity_training import load_initial_adapter, prefix_weighted_cross_entropy
except ModuleNotFoundError:
    from scripts.prefix_unfamiliarity_training import load_initial_adapter, prefix_weighted_cross_entropy
try:
    from wide_unfamiliarity_training import (
        CyclicStratumSampler, assert_text_only_trainables,
        enable_non_reentrant_checkpointing, finite_training_health,
        text_only_fullband_modules,
    )
except ModuleNotFoundError:
    from scripts.wide_unfamiliarity_training import (
        CyclicStratumSampler, assert_text_only_trainables,
        enable_non_reentrant_checkpointing, finite_training_health,
        text_only_fullband_modules,
    )


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--answer-prefix-conditioning", action="store_true",
                        help="allow answer_prefix_token_count records; supervise only the suffix")
    parser.add_argument("--model-id", required=True)
    parser.add_argument(
        "--reference-model-id",
        help=(
            "optional external clean model for retain/chat JSD; use when the "
            "trainable parent is already edited"
        ),
    )
    parser.add_argument(
        "--tokenizer-model",
        help="optional clean tokenizer/chat-template source for edited checkpoints",
    )
    parser.add_argument("--forget-data", required=True)
    parser.add_argument("--retain-data", default="data/retain.json")
    parser.add_argument("--chat-retain-data", default="data/retain_chat.json")
    parser.add_argument(
        "--consistency-data",
        help="optional on-policy target-adjacent prompt/answer pairs for ELM fluency",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--num-steps", type=int, default=120)
    parser.add_argument("--save-every", type=int, default=10)
    parser.add_argument(
        "--save-steps",
        default="",
        help="optional comma-separated extra snapshot steps",
    )
    parser.add_argument("--eval-every", type=int, default=10)
    parser.add_argument("--batch-forget", type=int, default=4)
    parser.add_argument("--cyclic-forget-strata", action="store_true")
    parser.add_argument("--text-only-fullband-lora", action="store_true")
    parser.add_argument("--gradient-checkpointing-non-reentrant", action="store_true")
    parser.add_argument("--record-training-health", action="store_true")
    parser.add_argument("--initial-lora-adapter")
    parser.add_argument("--target-prefix-tokens", type=int, default=0)
    parser.add_argument("--target-prefix-weight", type=float, default=1.0)
    parser.add_argument("--chat-retain-prefix-tokens", type=int, default=0)
    parser.add_argument("--chat-retain-prefix-weight", type=float, default=1.0)
    parser.add_argument(
        "--balanced-forget-categories",
        action="store_true",
        help="sample semantic categories uniformly, then a record within each",
    )
    parser.add_argument("--batch-retain", type=int, default=2)
    parser.add_argument("--batch-chat-retain", type=int, default=2)
    parser.add_argument("--batch-consistency", type=int, default=2)
    parser.add_argument(
        "--consistency-microbatch-size",
        type=int,
        default=0,
        help=(
            "split the sampled consistency batch into exact token-weighted "
            "gradient microbatches; 0 keeps the single-forward behavior"
        ),
    )
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument(
        "--parameterization", choices=("lora", "full"), default="lora"
    )
    parser.add_argument(
        "--forget-objective",
        choices=(
            "jensun-jsd",
            "answer-probability",
            "adaptive-rmu",
            "anchor-alignment",
            "elm-guided",
            "refusal-ce",
            "target-response-ce",
        ),
        default="jensun-jsd",
        help=(
            "bounded JensUn refusal objective, bounded ELM-inspired answer "
            "suppression, fixed refusal control, or teacher-forced per-example "
            "target responses"
        ),
    )
    parser.add_argument(
        "--steer-layers",
        default="20,24,28",
        help="comma-separated hidden-state layers used by adaptive-rmu",
    )
    parser.add_argument(
        "--rmu-norm-mult",
        type=float,
        default=1.0,
        help="random RMU target norm relative to each parent token norm",
    )
    parser.add_argument(
        "--disable-snapshots",
        action="store_true",
        help="diagnostic only: write metrics but do not save model checkpoints",
    )
    parser.add_argument("--rank", type=int, default=4)
    parser.add_argument("--lora-alpha", type=int, default=8)
    parser.add_argument("--train-layer-lo", type=int, default=4)
    parser.add_argument("--train-layer-hi", type=int, default=11)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--forget-weight", type=float, default=1.0)
    parser.add_argument(
        "--answer-suppression-weight",
        type=float,
        default=0.0,
        help=(
            "additional bounded original-answer probability penalty; currently "
            "supported with target-response-ce"
        ),
    )
    parser.add_argument("--retain-weight", type=float, default=1.0)
    parser.add_argument("--chat-retain-weight", type=float, default=1.0)
    parser.add_argument(
        "--consistency-weight",
        type=float,
        default=0.0,
        help="teacher-forced ELM fluency-under-attack loss weight",
    )
    parser.add_argument(
        "--project-conflicting-control-gradients",
        action="store_true",
        help=(
            "project the teacher-forced consistency gradient away from any "
            "component that opposes the forget gradient"
        ),
    )
    parser.add_argument(
        "--orthogonalize-control-gradients",
        action="store_true",
        help=(
            "remove every control-gradient component along the forget "
            "gradient, regardless of its sign"
        ),
    )
    parser.add_argument(
        "--orthogonalize-control-gradients-per-tensor",
        action="store_true",
        help=(
            "remove the control-gradient component along the forget gradient "
            "independently for every trainable parameter tensor"
        ),
    )
    parser.add_argument("--refusal-text", default="No idea")
    parser.add_argument(
        "--target-response-append-eos",
        action="store_true",
        help="append one EOS token to each target_response training continuation",
    )
    parser.add_argument(
        "--elm-concept",
        help="comma-separated core concept and required neighbours for ELM guidance",
    )
    parser.add_argument(
        "--elm-concept-map",
        help="optional JSON object mapping forget-data categories to ELM concepts",
    )
    parser.add_argument(
        "--elm-eta",
        type=float,
        default=10.0,
        help="expert-to-novice guidance strength at the final answer token",
    )
    parser.add_argument(
        "--elm-loss",
        choices=("jsd", "soft-cross-entropy"),
        default="jsd",
        help="bounded adaptation or the official ELM soft-target loss",
    )
    parser.add_argument(
        "--elm-temperature",
        type=float,
        default=1.2,
        help="temperature applied to all parent logits when building ELM targets",
    )
    parser.add_argument(
        "--elm-top-k",
        type=int,
        default=50,
        help="retain only the top-k ELM target tokens; 0 disables truncation",
    )
    parser.add_argument(
        "--stop-jsd",
        type=float,
        default=0.02,
        help="early stop when the audit-set mean JSD-to-refusal falls below this",
    )
    parser.add_argument("--stop-target-prob", type=float, default=0.9)
    parser.add_argument("--audit-size", type=int, default=24)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--fp32-base",
        action="store_true",
        help="load the frozen base in fp32 too (probe 3's BF16-cancellation "
        "control arm; roughly doubles weight memory)",
    )
    parser.add_argument(
        "--external-semantic-selection",
        action="store_true",
        help=(
            "do not stop on the training-corpus JSD/probability proxies; save "
            "the full evaluation grid so a driver can select the earliest "
            "held-out semantic PASS"
        ),
    )
    return parser.parse_args()


def load_model(model_id, dtype=torch.bfloat16):
    try:
        return AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=dtype, device_map="cuda"
        )
    except ValueError:
        from transformers import Gemma3ForConditionalGeneration

        return Gemma3ForConditionalGeneration.from_pretrained(
            model_id, torch_dtype=dtype, device_map="cuda"
        )


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def chat_messages_for_pair(pair):
    """Return a validated chat history for a retain pair.

    Legacy records contain one ``prompt`` string. Multi-turn preservation
    records instead contain ``messages`` ending in a user turn; ``answer`` is
    the clean continuation to preserve after that full history.
    """
    if "messages" not in pair:
        prompt = pair.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("chat-retain pair needs a non-empty prompt")
        return [{"role": "user", "content": prompt}]
    messages = pair["messages"]
    if not isinstance(messages, list) or not messages:
        raise ValueError("chat-retain messages must be a non-empty list")
    allowed_roles = {"system", "user", "assistant"}
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ValueError(f"chat-retain message {index} is not an object")
        if message.get("role") not in allowed_roles:
            raise ValueError(f"chat-retain message {index} has an invalid role")
        if not isinstance(message.get("content"), str) or not message["content"].strip():
            raise ValueError(f"chat-retain message {index} has empty content")
    if messages[-1]["role"] != "user":
        raise ValueError("chat-retain messages must end in a user turn")
    return messages


def sample_forget_batch(pairs, batch_size, balanced_categories=False):
    """Sample records directly or uniformly through their category labels."""
    if not balanced_categories:
        return random.sample(pairs, batch_size)
    groups = {}
    for index, pair in enumerate(pairs):
        category = pair.get("category")
        if not isinstance(category, str) or not category.strip():
            raise ValueError(f"forget record {index} lacks a category")
        groups.setdefault(category, []).append(pair)
    categories = sorted(groups)
    if not categories:
        raise ValueError("balanced forget sampling needs at least one category")
    selected_categories = []
    while len(selected_categories) < batch_size:
        cycle = list(categories)
        random.shuffle(cycle)
        selected_categories.extend(cycle[: batch_size - len(selected_categories)])
    return [random.choice(groups[category]) for category in selected_categories]


def jsd_to_uniform(logits, mask, chunk=512):
    """Mean Jensen-Shannon divergence to the uniform distribution.

    Bounded in [0, log 2], zero only when the answer-token distribution is
    flat.  Only masked answer positions are scored, and they are gathered
    before the fp32 conversion: Gemma's vocabulary is ~262k, so converting
    every position of a [batch, seq, vocab] tensor would cost gigabytes and
    OOM the L4.  Rows are then processed in chunks for the same reason.
    """
    selected = logits[mask.bool()]
    if selected.numel() == 0:
        return logits.sum() * 0.0
    vocab = selected.shape[-1]
    log_u = -math.log(vocab)
    log_two = math.log(2.0)
    total = None
    for start in range(0, selected.shape[0], chunk):
        block = selected[start : start + chunk].float()
        log_p = F.log_softmax(block, dim=-1)
        # m = (p + u) / 2  =>  log m = logaddexp(log p, log u) - log 2
        log_m = torch.logaddexp(log_p, torch.full_like(log_p, log_u)) - log_two
        kl_pm = (log_p.exp() * (log_p - log_m)).sum(dim=-1)
        # u is constant, so KL(u||m) = (1/V) * sum_v (log u - log m).
        kl_um = math.exp(log_u) * (log_u - log_m).sum(dim=-1)
        block_sum = (0.5 * kl_pm + 0.5 * kl_um).sum()
        total = block_sum if total is None else total + block_sum
    return total / selected.shape[0]


def cyclic_target_ids(mask, pattern):
    """Return one target token for every selected row in mask order."""
    if not pattern:
        raise ValueError("the JensUn refusal target tokenized to an empty sequence")
    targets = []
    for row in mask.bool():
        count = int(row.sum())
        targets.extend(pattern[index % len(pattern)] for index in range(count))
    return torch.tensor(targets, device=mask.device, dtype=torch.long)


def jsd_to_cyclic_one_hot(logits, mask, pattern):
    """Mean JSD from selected model rows to a repeated one-hot token pattern."""
    selected = logits[mask.bool()].float()
    if selected.numel() == 0:
        return logits.sum() * 0.0
    targets = cyclic_target_ids(mask, pattern)
    log_p = F.log_softmax(selected, dim=-1)
    target_log_p = log_p.gather(1, targets.unsqueeze(1)).squeeze(1)
    target_p = target_log_p.exp()
    safe_p = target_p.clamp_min(1e-30)
    log_two = math.log(2.0)
    kl_p_m = (1.0 - target_p) * log_two + target_p * (
        log_two + safe_p.log() - torch.log1p(target_p)
    )
    kl_q_m = log_two - torch.log1p(target_p)
    return (0.5 * (kl_p_m + kl_q_m)).mean()


def cyclic_refusal_cross_entropy(logits, mask, pattern):
    """Cross-entropy toward the repeated refusal target on selected rows."""
    selected = logits[mask.bool()].float()
    if selected.numel() == 0:
        return logits.sum() * 0.0
    targets = cyclic_target_ids(mask, pattern)
    return F.cross_entropy(selected, targets)


def mean_selected_token_probability(logits, labels, mask):
    """Mean probability assigned to the original answer tokens.

    Minimising this bounded quantity suppresses the on-policy concept answer
    without prescribing one shared replacement response.  That distinction is
    important in sequential use: a universal refusal target can itself become
    a global behavioural shortcut.
    """
    selected = logits[mask.bool()].float()
    if selected.numel() == 0:
        return logits.sum() * 0.0
    targets = labels[mask.bool()]
    return F.softmax(selected, dim=-1).gather(
        1, targets.unsqueeze(1)
    ).mean()


def selected_token_cross_entropy(logits, labels, mask):
    """Teacher-forced NLL on selected continuation tokens."""
    selected = logits[mask.bool()].float()
    if selected.numel() == 0:
        return logits.sum() * 0.0
    return F.cross_entropy(selected, labels[mask.bool()])


def selected_token_cross_entropy_sum(logits, labels, mask):
    """Summed teacher-forced NLL for exact token-weighted microbatching."""
    selected = logits[mask.bool()].float()
    if selected.numel() == 0:
        return logits.sum() * 0.0
    return F.cross_entropy(selected, labels[mask.bool()], reduction="sum")


def accumulate_detached_gradients(accumulated, gradients):
    """Add one autograd result into a detached per-parameter accumulator."""
    if accumulated is None:
        return [
            None if gradient is None else gradient.detach().clone()
            for gradient in gradients
        ]
    if len(accumulated) != len(gradients):
        raise ValueError("gradient accumulator length mismatch")
    for index, gradient in enumerate(gradients):
        if gradient is None:
            continue
        if accumulated[index] is None:
            accumulated[index] = gradient.detach().clone()
        else:
            accumulated[index].add_(gradient.detach())
    return accumulated


def project_control_gradients_away_from_target(
    target_grads,
    control_grads,
    eps=1e-12,
    only_if_conflicting=True,
    per_tensor=False,
):
    """Project control gradients away from the aggregate target direction."""
    if len(target_grads) != len(control_grads):
        raise ValueError("target and control gradient lists must have equal length")
    dot = None
    target_norm_sq = None
    control_norm_sq = None
    for target, control in zip(target_grads, control_grads):
        if target is not None:
            value = target.float().pow(2).sum()
            target_norm_sq = value if target_norm_sq is None else target_norm_sq + value
        if control is not None:
            value = control.float().pow(2).sum()
            control_norm_sq = value if control_norm_sq is None else control_norm_sq + value
        if target is not None and control is not None:
            value = (target.float() * control.float()).sum()
            dot = value if dot is None else dot + value
    device = next(
        (
            gradient.device
            for gradient in (*target_grads, *control_grads)
            if gradient is not None
        ),
        torch.device("cpu"),
    )
    zero = torch.zeros((), device=device, dtype=torch.float32)
    dot = zero if dot is None else dot
    target_norm_sq = zero if target_norm_sq is None else target_norm_sq
    control_norm_sq = zero if control_norm_sq is None else control_norm_sq
    denominator = (target_norm_sq.sqrt() * control_norm_sq.sqrt()).clamp_min(eps)
    cosine = dot / denominator
    eligible_tensors = sum(
        target is not None
        and control is not None
        and bool(target.float().pow(2).sum() > eps)
        for target, control in zip(target_grads, control_grads)
    )
    projected_tensors = 0
    apply_projection = False
    if per_tensor:
        projected = []
        for target, control in zip(target_grads, control_grads):
            if target is None or control is None:
                projected.append(control)
                continue
            local_norm_sq = target.float().pow(2).sum()
            local_dot = (target.float() * control.float()).sum()
            should_project = bool(
                local_norm_sq > eps
                and (not only_if_conflicting or local_dot < 0)
            )
            if should_project:
                local_scale = local_dot / local_norm_sq
                projected.append(
                    control
                    - local_scale.to(control.dtype) * target.to(control.dtype)
                )
                projected_tensors += 1
            else:
                projected.append(control)
        apply_projection = projected_tensors > 0
    elif bool(target_norm_sq > eps and (not only_if_conflicting or dot < 0)):
        apply_projection = True
        scale = dot / target_norm_sq
        projected = [
            (
                control - scale.to(control.dtype) * target.to(control.dtype)
                if control is not None and target is not None
                else control
            )
            for target, control in zip(target_grads, control_grads)
        ]
        projected_tensors = eligible_tensors
    else:
        projected = list(control_grads)
    return projected, {
        "target_control_grad_dot": float(dot.detach()),
        "target_control_grad_cosine": float(cosine.detach()),
        "control_projection_applied": apply_projection,
        "control_projection_tensors": projected_tensors,
        "control_projection_eligible_tensors": eligible_tensors,
    }


def elm_guided_target(
    original_logits,
    expert_logits,
    novice_logits,
    answer_counts,
    eta,
    temperature=1.2,
    top_k=50,
):
    """Build ELM's parent-self-guided novice target distribution.

    The official ELM rule is log P'(x) proportional to log P(x) plus a
    position-ramped novice-minus-expert classifier direction.  Inputs here are
    already aligned to the answer-token rows of the three parent forwards.
    """
    if eta < 1:
        raise ValueError("ELM eta must be at least 1")
    if temperature <= 0:
        raise ValueError("ELM temperature must be positive")
    if top_k < 0 or top_k > original_logits.shape[-1]:
        raise ValueError("ELM top-k must lie between 0 and the vocabulary size")
    if not (
        original_logits.shape == expert_logits.shape == novice_logits.shape
    ):
        raise ValueError("ELM parent distributions are not answer-token aligned")
    strengths = []
    for count in answer_counts:
        strengths.append(
            torch.linspace(
                1.0,
                eta,
                int(count),
                device=original_logits.device,
                dtype=torch.float32,
            )
        )
    strength = torch.cat(strengths).unsqueeze(1)
    original_log_p = F.log_softmax(
        original_logits.float() / temperature, dim=-1
    )
    expert_log_p = F.log_softmax(expert_logits.float() / temperature, dim=-1)
    novice_log_p = F.log_softmax(novice_logits.float() / temperature, dim=-1)
    guided_logits = original_log_p + strength * (novice_log_p - expert_log_p)
    if top_k:
        threshold = torch.topk(guided_logits, k=top_k, dim=-1).values[:, -1:]
        guided_logits = guided_logits.masked_fill(
            guided_logits < threshold, -torch.inf
        )
    return F.softmax(guided_logits, dim=-1)


def jsd_to_target_distribution(logits, mask, target_probs, chunk=128):
    """Mean bounded JSD from selected model rows to a soft target."""
    selected = logits[mask.bool()]
    if selected.numel() == 0:
        return logits.sum() * 0.0
    if selected.shape != target_probs.shape:
        raise ValueError("soft target is not aligned to selected model rows")
    total = None
    log_two = math.log(2.0)
    for start in range(0, selected.shape[0], chunk):
        log_p = F.log_softmax(selected[start : start + chunk].float(), dim=-1)
        log_q = target_probs[start : start + chunk].clamp_min(1e-30).log()
        log_m = torch.logaddexp(log_p, log_q) - log_two
        block = 0.5 * (
            (log_p.exp() * (log_p - log_m)).sum(dim=-1)
            + (log_q.exp() * (log_q - log_m)).sum(dim=-1)
        )
        block_sum = block.sum()
        total = block_sum if total is None else total + block_sum
    return total / selected.shape[0]


def soft_target_cross_entropy(logits, mask, target_probs, chunk=128):
    """Official ELM soft-target cross-entropy on selected answer rows."""
    selected = logits[mask.bool()]
    if selected.numel() == 0:
        return logits.sum() * 0.0
    if selected.shape != target_probs.shape:
        raise ValueError("soft target is not aligned to selected model rows")
    total = None
    for start in range(0, selected.shape[0], chunk):
        log_p = F.log_softmax(selected[start : start + chunk].float(), dim=-1)
        target = target_probs[start : start + chunk]
        block_sum = -(target * log_p).sum()
        total = block_sum if total is None else total + block_sum
    return total / selected.shape[0]


def jsd_between_logits(logits, reference_logits, mask, chunk=128, *, prefix_tokens=0, prefix_weight=1.0):
    """Token-mean JSD; optional prefix weights retain the original denominator."""
    selected = logits[mask.bool()]
    reference = reference_logits[mask.bool()].detach()
    if selected.numel() == 0:
        return logits.sum() * 0.0
    if not isinstance(prefix_tokens, int) or prefix_tokens < 0 or not math.isfinite(prefix_weight) or prefix_weight <= 0:
        raise ValueError("JSD prefix requires nonnegative count and positive finite weight")
    weights = None
    if prefix_tokens > 0 and prefix_weight != 1:
        if mask.ndim != 2:
            raise ValueError("prefix JSD requires batch/sequence mask")
        positions = mask.bool().long().cumsum(dim=1)[mask.bool()]
        weights = torch.where(positions <= prefix_tokens, prefix_weight, 1.0)
    total = None
    log_two = math.log(2.0)
    for start in range(0, selected.shape[0], chunk):
        log_p = F.log_softmax(selected[start : start + chunk].float(), dim=-1)
        log_q = F.log_softmax(reference[start : start + chunk].float(), dim=-1)
        log_m = torch.logaddexp(log_p, log_q) - log_two
        block = 0.5 * (
            (log_p.exp() * (log_p - log_m)).sum(dim=-1)
            + (log_q.exp() * (log_q - log_m)).sum(dim=-1)
        )
        block_sum = block.sum() if weights is None else (block * weights[start : start + chunk]).sum()
        total = block_sum if total is None else total + block_sum
    return total / selected.shape[0]


def adaptive_rmu_loss(current_states, reference_states, mask, directions, norm_mult):
    """Mean norm-scaled RMU loss across selected layers and answer tokens."""
    if norm_mult <= 0:
        raise ValueError("RMU norm multiplier must be positive")
    losses = []
    for layer, direction in directions.items():
        current = current_states[layer]
        reference = reference_states[layer].detach()
        norms = reference.float().norm(dim=-1, keepdim=True).clamp(min=1e-6)
        target = direction.reshape(1, 1, -1) * (norm_mult * norms)
        relative = (
            (current.float() - target).pow(2).sum(dim=-1)
            / norms.squeeze(-1).pow(2)
        )
        losses.append((relative * mask).sum() / mask.sum().clamp(min=1))
    if not losses:
        raise ValueError("adaptive RMU needs at least one steering layer")
    return torch.stack(losses).mean()


def prompt_last_indices(answer_mask):
    """Return the last prompt-token index immediately before each answer."""
    if answer_mask.ndim != 2 or not torch.all(answer_mask.sum(dim=-1) > 0):
        raise ValueError("each row needs at least one answer token")
    first_answer = answer_mask.float().argmax(dim=-1)
    if torch.any(first_answer < 1):
        raise ValueError("each row needs at least one prompt token")
    return first_answer - 1


def anchor_alignment_loss(
    current_states,
    current_indices,
    anchor_states,
    anchor_indices,
    layers,
):
    """Align source prompt states to frozen already-forgotten anchor states."""
    losses = []
    batch = torch.arange(current_indices.shape[0], device=current_indices.device)
    for layer in layers:
        current = current_states[layer][batch, current_indices].float()
        anchor = anchor_states[layer][batch, anchor_indices].float().detach()
        norm_sq = anchor.pow(2).sum(dim=-1).clamp(min=1e-6)
        losses.append(((current - anchor).pow(2).sum(dim=-1) / norm_sq).mean())
    if not losses:
        raise ValueError("anchor alignment needs at least one layer")
    return torch.stack(losses).mean()


def main():
    args = parse_args()
    try:
        steer_layers = [
            int(value) for value in args.steer_layers.split(",") if value.strip()
        ]
    except ValueError as error:
        raise ValueError("--steer-layers must contain comma-separated integers") from error
    if not steer_layers or len(set(steer_layers)) != len(steer_layers):
        raise ValueError("--steer-layers must contain unique layer indices")
    try:
        extra_save_steps = {
            int(value) for value in args.save_steps.split(",") if value.strip()
        }
    except ValueError as error:
        raise ValueError("--save-steps must contain comma-separated integers") from error
    if any(step < 1 or step > args.num_steps for step in extra_save_steps):
        raise ValueError("--save-steps values must lie within the step budget")
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        raise FileExistsError(f"{output_dir} already exists; use a fresh directory")
    if args.parameterization == "lora" and args.train_layer_lo >= args.train_layer_hi:
        raise ValueError("train-layer-lo must be below train-layer-hi")
    if args.forget_objective == "adaptive-rmu" and args.parameterization != "lora":
        raise ValueError("adaptive-rmu currently requires LoRA parameterization")
    if args.forget_objective == "anchor-alignment" and args.parameterization != "lora":
        raise ValueError("anchor-alignment currently requires LoRA parameterization")
    if args.forget_objective == "elm-guided":
        if args.parameterization != "lora":
            raise ValueError("elm-guided currently requires LoRA parameterization")
        if not args.elm_concept:
            raise ValueError("elm-guided requires --elm-concept")
        if args.elm_eta < 1:
            raise ValueError("--elm-eta must be at least 1")
        if args.elm_temperature <= 0:
            raise ValueError("--elm-temperature must be positive")
        if args.elm_top_k < 0:
            raise ValueError("--elm-top-k must be non-negative")

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    forget_pairs = read_json(args.forget_data)
    if args.target_prefix_tokens < 0 or not math.isfinite(args.target_prefix_weight) or args.target_prefix_weight <= 0:
        raise ValueError("target prefix requires nonnegative token count and positive finite weight")
    if args.chat_retain_prefix_tokens < 0 or not math.isfinite(args.chat_retain_prefix_weight) or args.chat_retain_prefix_weight <= 0:
        raise ValueError("chat retain prefix requires nonnegative count and positive finite weight")
    if (args.target_prefix_tokens > 0 or args.target_prefix_weight != 1) and args.forget_objective != "target-response-ce":
        raise ValueError("prefix weighting only applies to target-response-ce")
    if args.initial_lora_adapter and not args.text_only_fullband_lora:
        raise ValueError("initial adapter loading requires the strict full-band LoRA scope")
    if args.cyclic_forget_strata and args.balanced_forget_categories:
        raise ValueError("cyclic strata and random balanced categories are exclusive")
    if args.text_only_fullband_lora and (
        args.parameterization != "lora"
        or args.train_layer_lo != 0 or args.train_layer_hi != 34
    ):
        raise ValueError("text-only full-band mode requires LoRA and layers0:34")
    forget_sampler = (
        CyclicStratumSampler(forget_pairs, seed=args.seed, batch_size=args.batch_forget)
        if args.cyclic_forget_strata else None
    )
    if args.forget_objective == "anchor-alignment":
        missing_anchors = [
            index
            for index, pair in enumerate(forget_pairs)
            if not isinstance(pair.get("anchor_prompt"), str)
            or not pair["anchor_prompt"].strip()
        ]
        if missing_anchors:
            raise ValueError(
                "anchor-alignment requires a non-empty anchor_prompt on every "
                f"forget record; missing indices: {missing_anchors[:10]}"
            )
    if args.forget_objective == "target-response-ce":
        missing_targets = [
            index
            for index, pair in enumerate(forget_pairs)
            if not isinstance(pair.get("target_response"), str)
            or not pair["target_response"].strip()
        ]
        if missing_targets:
            raise ValueError(
                "target-response-ce requires a non-empty target_response on "
                f"every forget record; missing indices: {missing_targets[:10]}"
            )
    if any("answer_prefix_token_count" in pair for pair in forget_pairs) and args.forget_objective != "target-response-ce":
        raise ValueError("answer-prefix conditioning requires target-response-ce")
    if args.answer_suppression_weight < 0:
        raise ValueError("--answer-suppression-weight must be non-negative")
    if args.consistency_microbatch_size < 0:
        raise ValueError("--consistency-microbatch-size must be non-negative")
    if (
        args.answer_suppression_weight > 0
        and args.forget_objective != "target-response-ce"
    ):
        raise ValueError(
            "positive --answer-suppression-weight currently requires "
            "--forget-objective target-response-ce"
        )
    if (
        args.target_response_append_eos
        and args.forget_objective != "target-response-ce"
    ):
        raise ValueError(
            "--target-response-append-eos requires "
            "--forget-objective target-response-ce"
        )
    elm_concept_map = read_json(args.elm_concept_map) if args.elm_concept_map else {}
    if not isinstance(elm_concept_map, dict):
        raise ValueError("--elm-concept-map must contain a JSON object")
    if elm_concept_map:
        missing_categories = sorted(
            {
                pair.get("category", "unknown")
                for pair in forget_pairs
                if pair.get("category", "unknown") not in elm_concept_map
            }
        )
        if missing_categories:
            raise ValueError(
                "ELM concept map is missing forget categories: "
                + ", ".join(missing_categories)
            )
    retain_texts = read_json(args.retain_data)
    chat_pairs = (
        read_json(args.chat_retain_data)
        if args.chat_retain_data and Path(args.chat_retain_data).is_file()
        else []
    )
    validate_conditioning_records([*forget_pairs, *chat_pairs], enabled=args.answer_prefix_conditioning)
    consistency_pairs = (
        read_json(args.consistency_data)
        if args.consistency_data and Path(args.consistency_data).is_file()
        else []
    )
    if len(forget_pairs) < args.batch_forget:
        raise ValueError("forget corpus is smaller than --batch-forget")
    if len(retain_texts) < args.batch_retain:
        raise ValueError("retain corpus is smaller than --batch-retain")
    if args.consistency_weight > 0 and not consistency_pairs:
        raise ValueError("positive --consistency-weight requires --consistency-data")
    if args.project_conflicting_control_gradients and (
        args.consistency_weight <= 0 or not consistency_pairs
    ):
        raise ValueError(
            "--project-conflicting-control-gradients requires positive "
            "--consistency-weight and --consistency-data"
        )
    if args.orthogonalize_control_gradients and (
        args.consistency_weight <= 0 or not consistency_pairs
    ):
        raise ValueError(
            "--orthogonalize-control-gradients requires positive "
            "--consistency-weight and --consistency-data"
        )
    if args.orthogonalize_control_gradients_per_tensor and (
        args.consistency_weight <= 0 or not consistency_pairs
    ):
        raise ValueError(
            "--orthogonalize-control-gradients-per-tensor requires positive "
            "--consistency-weight and --consistency-data"
        )
    if sum(
        (
            args.project_conflicting_control_gradients,
            args.orthogonalize_control_gradients,
            args.orthogonalize_control_gradients_per_tensor,
        )
    ) > 1:
        raise ValueError("choose only one control-gradient projection mode")

    tokenizer_source = args.tokenizer_model or args.model_id
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_source)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    base_dtype = torch.float32 if args.fp32_base else torch.bfloat16
    print(f"Loading {args.model_id} in {base_dtype}...")
    model = load_model(args.model_id, base_dtype)

    model_config = model.config
    num_layers = getattr(model_config, "num_hidden_layers", None)
    if num_layers is None:
        num_layers = model_config.text_config.num_hidden_layers
    hidden_size = getattr(model_config, "hidden_size", None)
    if hidden_size is None:
        hidden_size = model_config.text_config.hidden_size
    if min(steer_layers) < 0 or max(steer_layers) >= num_layers:
        raise ValueError(f"steer layers must be within 0..{num_layers - 1}")
    reference_model = None
    selected_text_modules = None
    selected_trainable_names = None
    if args.parameterization == "lora":
        if args.train_layer_hi > num_layers:
            raise ValueError(
                f"train-layer-hi {args.train_layer_hi} exceeds {num_layers} layers"
            )
        target_layers = list(range(args.train_layer_lo, args.train_layer_hi))
        if args.forget_objective in {"adaptive-rmu", "anchor-alignment"} and not set(
            steer_layers
        ).issubset(target_layers):
            raise ValueError("representation steer layers must lie inside the LoRA band")
        print(
            f"Model has {num_layers} layers; rank-{args.rank} LoRA on layers "
            f"{target_layers[0]}-{target_layers[-1]} (ELM early band)."
        )
        if args.text_only_fullband_lora:
            selected_text_modules = text_only_fullband_modules(model.named_modules())
        model = load_initial_adapter(
            model, args.initial_lora_adapter, rank=args.rank,
            alpha=args.lora_alpha, selected_modules=selected_text_modules,
        ) if args.initial_lora_adapter else get_peft_model(
            model,
            LoraConfig(
                r=args.rank,
                lora_alpha=args.lora_alpha,
                lora_dropout=0.0,
                target_modules=selected_text_modules or [
                    "q_proj",
                    "k_proj",
                    "v_proj",
                    "o_proj",
                    "gate_proj",
                    "up_proj",
                    "down_proj",
                ],
                layers_to_transform=None if selected_text_modules else target_layers,
                task_type="CAUSAL_LM",
            ),
        )
        # fp32 master weights: cast trainable LoRA parameters up, leave the
        # frozen BF16 base alone.
        for parameter in model.parameters():
            if parameter.requires_grad:
                parameter.data = parameter.data.float()
        trainable = [p for p in model.parameters() if p.requires_grad]
        non_fp32 = [p for p in trainable if p.dtype is not torch.float32]
        if non_fp32:
            raise RuntimeError(
                f"{len(non_fp32)} trainable parameters are not fp32; the BF16 "
                "write-back trap (zamirai-2020) would be live"
            )
        master_weight_dtype = "float32"
        if selected_text_modules:
            selected_trainable_names = assert_text_only_trainables(
                model.named_parameters(), selected_text_modules
            )
        model.print_trainable_parameters()
    else:
        target_layers = list(range(num_layers))
        trainable = [p for p in model.parameters() if p.requires_grad]
        master_weight_dtype = str(base_dtype)
        trainable_count = sum(parameter.numel() for parameter in trainable)
        total_count = sum(parameter.numel() for parameter in model.parameters())
        print(
            f"Model has {num_layers} layers; full-model JensUn control with "
            f"{trainable_count:,}/{total_count:,} trainable parameters.",
            flush=True,
        )
    if not trainable:
        raise RuntimeError("no trainable parameters")
    if args.gradient_checkpointing_non_reentrant:
        enable_non_reentrant_checkpointing(model)
    rmu_directions = {}
    if args.forget_objective == "adaptive-rmu":
        for layer in steer_layers:
            direction = torch.randn(hidden_size, device="cuda", dtype=torch.float32)
            rmu_directions[layer] = direction / direction.norm()
    if args.reference_model_id:
        print(
            f"Loading external retain reference {args.reference_model_id}...",
            flush=True,
        )
        reference_model = load_model(args.reference_model_id, base_dtype)
        reference_model.eval()
        reference_model.requires_grad_(False)
    elif (
        args.parameterization == "full"
        and (args.retain_weight > 0 or args.chat_retain_weight > 0)
    ):
        print("Loading a frozen parent reference model for retain JSD...", flush=True)
        reference_model = load_model(args.model_id, base_dtype)
        reference_model.eval()
        reference_model.requires_grad_(False)

    def chat_prompt_ids(prompt_or_messages):
        messages = (
            prompt_or_messages
            if isinstance(prompt_or_messages, list)
            else [{"role": "user", "content": prompt_or_messages}]
        )
        encoded = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
        )
        ids = encoded["input_ids"]
        if isinstance(ids, torch.Tensor):
            ids = ids.tolist()
        if ids and isinstance(ids[0], list):
            ids = ids[0]
        return ids

    def pad_batch(sequences, masks, label_sequences=None):
        width = max(len(ids) for ids in sequences)
        pad_id = tokenizer.pad_token_id
        input_ids, attention, answer_mask, labels_out = [], [], [], []
        for index, ids in enumerate(sequences):
            pad = width - len(ids)
            input_ids.append(ids + [pad_id] * pad)
            attention.append([1] * len(ids) + [0] * pad)
            answer_mask.append(masks[index] + [0] * pad)
            if label_sequences is not None:
                labels_out.append(label_sequences[index] + [-100] * pad)
        result = [
            torch.tensor(input_ids, device="cuda"),
            torch.tensor(attention, device="cuda"),
            torch.tensor(answer_mask, device="cuda", dtype=torch.float32),
        ]
        if label_sequences is not None:
            result.append(torch.tensor(labels_out, device="cuda"))
        return result

    def make_forget_batch(pairs, prompt_prefix="", answer_field="answer"):
        sequences, masks, labels = [], [], []
        prefixes = (
            [prompt_prefix] * len(pairs)
            if isinstance(prompt_prefix, str)
            else list(prompt_prefix)
        )
        if len(prefixes) != len(pairs):
            raise ValueError("one ELM prompt prefix is required per forget pair")
        for pair, prefix in zip(pairs, prefixes):
            prompt_ids = chat_prompt_ids(prefix + pair["prompt"])
            answer_ids = (
                pair.get("answer_token_ids") if answer_field == "answer" else None
            )
            if answer_ids is None:
                answer_ids = tokenizer(
                    pair[answer_field], add_special_tokens=False
                ).input_ids
            if (
                answer_field == "target_response"
                and args.target_response_append_eos
                and tokenizer.eos_token_id is not None
                and (not answer_ids or answer_ids[-1] != tokenizer.eos_token_id)
            ):
                answer_ids = [*answer_ids, tokenizer.eos_token_id]
            prefix_count = answer_prefix_count(pair)
            source_ids = answer_ids
            if prefix_count is not None and answer_field != "answer":
                source_ids = pair.get("answer_token_ids")
                if source_ids is None:
                    source_ids = tokenizer(pair["answer"], add_special_tokens=False).input_ids
            ids, mask, label = encode_answer_sequence(
                prompt_ids, source_ids,
                supervised_ids=answer_ids if answer_field != "answer" else None,
                prefix_count=prefix_count, max_length=args.max_length,
            )
            if not any(mask):
                raise ValueError(f"answer truncated away: {pair['prompt']}")
            sequences.append(ids)
            masks.append(mask)
            labels.append(label)
        return pad_batch(sequences, masks, labels)

    def make_retain_batch(texts):
        encoded = tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=args.max_length,
        )
        input_ids = encoded.input_ids.to("cuda")
        attention = encoded.attention_mask.to("cuda")
        labels = input_ids.clone()
        labels[attention == 0] = -100
        return input_ids, attention, labels

    def make_chat_retain_batch(pairs):
        sequences, masks, labels = [], [], []
        for pair in pairs:
            prompt_ids = chat_prompt_ids(chat_messages_for_pair(pair))
            answer_ids = tokenizer(
                pair["answer"], add_special_tokens=False
            ).input_ids
            ids, mask, label = encode_answer_sequence(
                prompt_ids, answer_ids, prefix_count=answer_prefix_count(pair),
                max_length=args.max_length,
            )
            if not any(mask):
                continue
            sequences.append(ids)
            masks.append(mask)
            labels.append(label)
        if not sequences:
            return None
        return pad_batch(sequences, masks, labels)

    refusal_token_ids = tokenizer(
        args.refusal_text, add_special_tokens=False
    ).input_ids
    if not refusal_token_ids:
        raise ValueError("--refusal-text tokenized to no tokens")
    print(
        f"JensUn refusal target {args.refusal_text!r}: token ids "
        f"{refusal_token_ids}"
    )

    def audit(pairs):
        """Measure refusal-target JSD/probability and original-answer probability."""
        was_training = model.training
        model.eval()
        jsd_values, target_prob_values, answer_prob_values, rmu_values = [], [], [], []
        with torch.inference_mode():
            for start in range(0, len(pairs), args.batch_forget):
                ids, attention, mask, labels = make_forget_batch(
                    pairs[start : start + args.batch_forget]
                )
                outputs = model(
                    input_ids=ids,
                    attention_mask=attention,
                    output_hidden_states=args.forget_objective
                    in {"adaptive-rmu", "anchor-alignment"},
                )
                logits = outputs.logits
                shifted_logits = logits[:, :-1, :]
                shifted_labels = labels[:, 1:]
                shifted_mask = (shifted_labels != -100).float()
                jsd_values.append(float(jsd_to_cyclic_one_hot(
                    shifted_logits, shifted_mask, refusal_token_ids
                )))
                log_probs = F.log_softmax(shifted_logits.float(), dim=-1)
                target_ids = cyclic_target_ids(shifted_mask, refusal_token_ids)
                selected_log_probs = log_probs[shifted_mask.bool()]
                target_prob_values.append(float(
                    selected_log_probs.gather(
                        1, target_ids.unsqueeze(1)
                    ).exp().mean()
                ))
                gathered = log_probs.gather(
                    -1, shifted_labels.clamp(min=0).unsqueeze(-1)
                ).squeeze(-1)
                mean_prob = (
                    gathered.exp() * shifted_mask
                ).sum() / shifted_mask.sum().clamp(min=1)
                answer_prob_values.append(float(mean_prob))
                if args.forget_objective == "adaptive-rmu":
                    current_states = {
                        layer: outputs.hidden_states[layer + 1]
                        for layer in steer_layers
                    }
                    with model.disable_adapter():
                        parent_outputs = model(
                            input_ids=ids,
                            attention_mask=attention,
                            output_hidden_states=True,
                            use_cache=False,
                        )
                    reference_states = {
                        layer: parent_outputs.hidden_states[layer + 1]
                        for layer in steer_layers
                    }
                    rmu_values.append(
                        float(
                            adaptive_rmu_loss(
                                current_states,
                                reference_states,
                                mask,
                                rmu_directions,
                                args.rmu_norm_mult,
                            )
                        )
                    )
                elif args.forget_objective == "anchor-alignment":
                    anchor_pairs = [
                        {"prompt": pair["anchor_prompt"], "answer": pair["answer"]}
                        for pair in pairs[start : start + args.batch_forget]
                    ]
                    a_ids, a_attention, a_mask, _ = make_forget_batch(anchor_pairs)
                    with model.disable_adapter():
                        anchor_outputs = model(
                            input_ids=a_ids,
                            attention_mask=a_attention,
                            output_hidden_states=True,
                            use_cache=False,
                        )
                    current_states = {
                        layer: outputs.hidden_states[layer + 1]
                        for layer in steer_layers
                    }
                    anchor_states = {
                        layer: anchor_outputs.hidden_states[layer + 1]
                        for layer in steer_layers
                    }
                    rmu_values.append(
                        float(
                            anchor_alignment_loss(
                                current_states,
                                prompt_last_indices(mask),
                                anchor_states,
                                prompt_last_indices(a_mask),
                                steer_layers,
                            )
                        )
                    )
        if was_training:
            model.train()
        result = {
            "mean_jsd_to_refusal": sum(jsd_values) / len(jsd_values),
            "mean_refusal_token_prob": (
                sum(target_prob_values) / len(target_prob_values)
            ),
            "mean_answer_token_prob": (
                sum(answer_prob_values) / len(answer_prob_values)
            ),
        }
        if rmu_values:
            metric_name = (
                "mean_anchor_alignment_relative_mse"
                if args.forget_objective == "anchor-alignment"
                else "mean_rmu_relative_mse"
            )
            result[metric_name] = sum(rmu_values) / len(rmu_values)
        return result

    output_dir.mkdir(parents=True)
    metrics_path = output_dir / "training_metrics.jsonl"
    if args.forget_objective == "adaptive-rmu":
        objective_description = "adaptive norm-scaled hidden-state misdirection"
    elif args.forget_objective == "anchor-alignment":
        objective_description = (
            "prompt-final hidden-state alignment to frozen already-forgotten anchors"
        )
    elif args.forget_objective == "answer-probability":
        objective_description = (
            "bounded original-answer probability suppression on forget answer positions"
        )
    elif args.forget_objective == "target-response-ce":
        objective_description = (
            "teacher-forced cross-entropy to each record's distinct target_response"
            + (
                " plus bounded original-answer probability suppression "
                f"at weight {args.answer_suppression_weight}"
                if args.answer_suppression_weight > 0
                else ""
            )
        )
    elif args.forget_objective == "elm-guided":
        objective_description = (
            f"{args.elm_loss} to the parent model's ELM expert-to-novice "
            "self-guided distribution"
        )
    else:
        objective_description = (
            f"{args.forget_objective} toward cyclic refusal target on forget "
            "answer positions"
        )
    config = vars(args).copy()
    config.update(
        {
            "forget_examples": len(forget_pairs),
            "retain_examples": len(retain_texts),
            "chat_retain_examples": len(chat_pairs),
            "answer_prefix_conditioning_records": {
                name: {
                    "conditioned_records": sum("answer_prefix_token_count" in p for p in pairs),
                    "prefix_counts": sorted({answer_prefix_count(p) for p in pairs
                                             if "answer_prefix_token_count" in p}),
                    "supervision": "suffix only; supplied answer prefix unscored",
                }
                for name, pairs in (("forget", forget_pairs), ("chat_retain", chat_pairs))
            },
            "consistency_examples": len(consistency_pairs),
            "target_layers": target_layers,
            "selected_text_modules": selected_text_modules,
            "selected_trainable_names": selected_trainable_names,
            "initial_adapter_load_receipt": getattr(model, "_initial_adapter_load_receipt", None),
            "steer_layers_parsed": (
                steer_layers if args.forget_objective == "adaptive-rmu" else []
            ),
            "objective": (
                objective_description
                + " + JSD(p_model || p_clean) on retain/chat-retain"
                + (
                    " + target-adjacent teacher-forced consistency"
                    if args.consistency_weight > 0
                    else ""
                )
                + (
                    " with exact token-weighted gradient microbatching"
                    if args.consistency_microbatch_size > 0
                    and args.consistency_weight > 0
                    else ""
                )
                + (
                    " + target-priority projection of conflicting consistency gradients"
                    if args.project_conflicting_control_gradients
                    else ""
                )
                + (
                    " + target-null-space projection of consistency gradients"
                    if args.orthogonalize_control_gradients
                    else ""
                )
                + (
                    " + per-tensor target-null-space projection of consistency gradients"
                    if args.orthogonalize_control_gradients_per_tensor
                    else ""
                )
            ),
            "refusal_token_ids": refusal_token_ids,
            "master_weight_dtype": master_weight_dtype,
            "base_dtype": str(base_dtype),
        }
    )
    (output_dir / "run_config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )

    audit_rng = random.Random(args.seed + 1)
    audit_pairs = audit_rng.sample(
        forget_pairs, min(args.audit_size, len(forget_pairs))
    )
    print("Measuring the forget corpus before training...")
    baseline = audit(audit_pairs)
    print("baseline=" + json.dumps(baseline, sort_keys=True))
    if baseline["mean_answer_token_prob"] < 1e-4:
        raise RuntimeError(
            "the parent already assigns near-zero probability to these answers; "
            "refusing to run an erasure with nothing to erase"
        )
    with open(metrics_path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"step": 0, "scope": "audit", **baseline}) + "\n")

    optimizer = torch.optim.AdamW(trainable, lr=args.learning_rate)
    model.train()
    stop_reason = "step_budget_exhausted"
    stopped_at = args.num_steps
    first_proxy_gate = None

    for step in range(1, args.num_steps + 1):
        if args.record_training_health:
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
        step_started = time.perf_counter()
        forget_batch = forget_sampler.next_batch() if forget_sampler else sample_forget_batch(
            forget_pairs,
            args.batch_forget,
            balanced_categories=args.balanced_forget_categories,
        )
        answer_field = (
            "target_response"
            if args.forget_objective == "target-response-ce"
            else "answer"
        )
        f_ids, f_attention, f_mask, f_labels = make_forget_batch(
            forget_batch, answer_field=answer_field
        )
        forget_outputs = model(
            input_ids=f_ids,
            attention_mask=f_attention,
            output_hidden_states=args.forget_objective
            in {"adaptive-rmu", "anchor-alignment"},
            use_cache=False,
        )
        logits = forget_outputs.logits
        shifted_logits = logits[:, :-1, :]
        shifted_mask = (f_labels[:, 1:] != -100).float()
        if args.forget_objective == "jensun-jsd":
            forget_loss = jsd_to_cyclic_one_hot(
                shifted_logits, shifted_mask, refusal_token_ids
            )
        elif args.forget_objective == "answer-probability":
            forget_loss = mean_selected_token_probability(
                shifted_logits, f_labels[:, 1:], shifted_mask
            )
        elif args.forget_objective == "adaptive-rmu":
            with torch.no_grad(), model.disable_adapter():
                parent_outputs = model(
                    input_ids=f_ids,
                    attention_mask=f_attention,
                    output_hidden_states=True,
                    use_cache=False,
                )
            current_states = {
                layer: forget_outputs.hidden_states[layer + 1]
                for layer in steer_layers
            }
            reference_states = {
                layer: parent_outputs.hidden_states[layer + 1]
                for layer in steer_layers
            }
            forget_loss = adaptive_rmu_loss(
                current_states,
                reference_states,
                f_mask,
                rmu_directions,
                args.rmu_norm_mult,
            )
        elif args.forget_objective == "anchor-alignment":
            anchor_pairs = [
                {"prompt": pair["anchor_prompt"], "answer": pair["answer"]}
                for pair in forget_batch
            ]
            a_ids, a_attention, a_mask, _ = make_forget_batch(anchor_pairs)
            with torch.no_grad(), model.disable_adapter():
                anchor_outputs = model(
                    input_ids=a_ids,
                    attention_mask=a_attention,
                    output_hidden_states=True,
                    use_cache=False,
                )
            current_states = {
                layer: forget_outputs.hidden_states[layer + 1]
                for layer in steer_layers
            }
            anchor_states = {
                layer: anchor_outputs.hidden_states[layer + 1]
                for layer in steer_layers
            }
            forget_loss = anchor_alignment_loss(
                current_states,
                prompt_last_indices(f_mask),
                anchor_states,
                prompt_last_indices(a_mask),
                steer_layers,
            )
        elif args.forget_objective == "elm-guided":
            concepts = [
                elm_concept_map.get(pair.get("category"), args.elm_concept)
                for pair in forget_batch
            ]
            positive_prefix = [
                "Here is a response written by an expert with detailed, accurate "
                f"knowledge of {concept}:\n"
                for concept in concepts
            ]
            negative_prefix = [
                "Here is a response written by a novice with no knowledge of "
                f"{concept}, answering fluently using unrelated ordinary knowledge:\n"
                for concept in concepts
            ]
            e_ids, e_attention, _, e_labels = make_forget_batch(
                forget_batch, positive_prefix
            )
            n_ids, n_attention, _, n_labels = make_forget_batch(
                forget_batch, negative_prefix
            )
            answer_counts = [int(row.sum()) for row in shifted_mask]
            with torch.no_grad(), model.disable_adapter():
                original_parent = model(
                    input_ids=f_ids, attention_mask=f_attention
                ).logits[:, :-1, :][shifted_mask.bool()]
                expert_mask = (e_labels[:, 1:] != -100)
                expert_parent = model(
                    input_ids=e_ids, attention_mask=e_attention
                ).logits[:, :-1, :][expert_mask]
                novice_mask = (n_labels[:, 1:] != -100)
                novice_parent = model(
                    input_ids=n_ids, attention_mask=n_attention
                ).logits[:, :-1, :][novice_mask]
                elm_target = elm_guided_target(
                    original_parent,
                    expert_parent,
                    novice_parent,
                    answer_counts,
                    args.elm_eta,
                    args.elm_temperature,
                    args.elm_top_k,
                )
            if args.elm_loss == "soft-cross-entropy":
                forget_loss = soft_target_cross_entropy(
                    shifted_logits, shifted_mask, elm_target
                )
            else:
                forget_loss = jsd_to_target_distribution(
                    shifted_logits, shifted_mask, elm_target
                )
        elif args.forget_objective == "refusal-ce":
            forget_loss = cyclic_refusal_cross_entropy(
                shifted_logits, shifted_mask, refusal_token_ids
            )
        else:
            if args.target_prefix_tokens > 0 and args.target_prefix_weight != 1:
                forget_loss = prefix_weighted_cross_entropy(
                    shifted_logits, f_labels[:, 1:], shifted_mask,
                    prefix_tokens=args.target_prefix_tokens,
                    prefix_weight=args.target_prefix_weight, torch=torch,
                )
            else:
                forget_loss = selected_token_cross_entropy(
                    shifted_logits, f_labels[:, 1:], shifted_mask
                )

        answer_suppression_loss = torch.zeros((), device="cuda")
        if args.answer_suppression_weight > 0:
            o_ids, o_attention, _, o_labels = make_forget_batch(
                forget_batch, answer_field="answer"
            )
            original_logits = model(
                input_ids=o_ids, attention_mask=o_attention
            ).logits[:, :-1, :]
            original_mask = (o_labels[:, 1:] != -100).float()
            answer_suppression_loss = mean_selected_token_probability(
                original_logits, o_labels[:, 1:], original_mask
            )

        retain_loss = torch.zeros((), device="cuda")
        if args.retain_weight > 0:
            retain_batch = random.sample(retain_texts, args.batch_retain)
            r_ids, r_attention, r_labels = make_retain_batch(retain_batch)
            retain_logits = model(
                input_ids=r_ids, attention_mask=r_attention
            ).logits[:, :-1, :]
            if reference_model is None:
                with torch.no_grad(), model.disable_adapter():
                    retain_reference_logits = model(
                        input_ids=r_ids, attention_mask=r_attention
                    ).logits[:, :-1, :]
            else:
                with torch.no_grad():
                    retain_reference_logits = reference_model(
                        input_ids=r_ids, attention_mask=r_attention
                    ).logits[:, :-1, :]
            retain_mask = (r_labels[:, 1:] != -100).float()
            retain_loss = jsd_between_logits(
                retain_logits, retain_reference_logits, retain_mask
            )

        chat_loss = torch.zeros((), device="cuda")
        if chat_pairs and args.chat_retain_weight > 0:
            sampled = random.sample(
                chat_pairs, min(args.batch_chat_retain, len(chat_pairs))
            )
            chat_batch = make_chat_retain_batch(sampled)
            if chat_batch is not None:
                c_ids, c_attention, _, c_labels = chat_batch
                chat_logits = model(
                    input_ids=c_ids, attention_mask=c_attention
                ).logits[:, :-1, :]
                if reference_model is None:
                    with torch.no_grad(), model.disable_adapter():
                        chat_reference_logits = model(
                            input_ids=c_ids, attention_mask=c_attention
                        ).logits[:, :-1, :]
                else:
                    with torch.no_grad():
                        chat_reference_logits = reference_model(
                            input_ids=c_ids, attention_mask=c_attention
                        ).logits[:, :-1, :]
                chat_mask = (c_labels[:, 1:] != -100).float()
                chat_loss = jsd_between_logits(
                    chat_logits, chat_reference_logits, chat_mask,
                    prefix_tokens=args.chat_retain_prefix_tokens,
                    prefix_weight=args.chat_retain_prefix_weight,
                )

        consistency_loss = torch.zeros((), device="cuda")
        microbatched_control_grads = None
        consistency_records_used = 0
        consistency_tokens_used = 0
        consistency_gradient_microbatches = 0
        if consistency_pairs and args.consistency_weight > 0:
            sampled = random.sample(
                consistency_pairs,
                min(args.batch_consistency, len(consistency_pairs)),
            )
            consistency_batch = make_chat_retain_batch(sampled)
            if consistency_batch is not None:
                x_ids, x_attention, _, x_labels = consistency_batch
                consistency_records_used = x_ids.shape[0]
                consistency_tokens_used = int(
                    (x_labels[:, 1:] != -100).sum().item()
                )
                if consistency_tokens_used <= 0:
                    raise RuntimeError("consistency batch has no answer tokens")
                if args.consistency_microbatch_size > 0:
                    consistency_nll_sum = 0.0
                    for start in range(
                        0,
                        consistency_records_used,
                        args.consistency_microbatch_size,
                    ):
                        stop = min(
                            start + args.consistency_microbatch_size,
                            consistency_records_used,
                        )
                        chunk_labels = x_labels[start:stop, 1:]
                        chunk_mask = (chunk_labels != -100).float()
                        chunk_logits = model(
                            input_ids=x_ids[start:stop],
                            attention_mask=x_attention[start:stop],
                        ).logits[:, :-1, :]
                        chunk_nll_sum = selected_token_cross_entropy_sum(
                            chunk_logits,
                            chunk_labels,
                            chunk_mask,
                        )
                        chunk_control_loss = (
                            args.consistency_weight
                            * chunk_nll_sum
                            / consistency_tokens_used
                        )
                        chunk_grads = torch.autograd.grad(
                            chunk_control_loss,
                            trainable,
                            allow_unused=True,
                        )
                        microbatched_control_grads = (
                            accumulate_detached_gradients(
                                microbatched_control_grads, chunk_grads
                            )
                        )
                        consistency_nll_sum += float(chunk_nll_sum.detach())
                        consistency_gradient_microbatches += 1
                    consistency_loss = torch.tensor(
                        consistency_nll_sum / consistency_tokens_used,
                        device="cuda",
                    )
                else:
                    consistency_logits = model(
                        input_ids=x_ids, attention_mask=x_attention
                    ).logits[:, :-1, :]
                    consistency_mask = (x_labels[:, 1:] != -100).float()
                    consistency_loss = selected_token_cross_entropy(
                        consistency_logits,
                        x_labels[:, 1:],
                        consistency_mask,
                    )
                    consistency_gradient_microbatches = 1

        target_loss = (
            args.forget_weight * forget_loss
            + args.forget_weight
            * args.answer_suppression_weight
            * answer_suppression_loss
        )
        preservation_loss = (
            args.retain_weight * retain_loss
            + args.chat_retain_weight * chat_loss
        )
        control_loss = args.consistency_weight * consistency_loss
        loss = target_loss + preservation_loss + control_loss
        if args.record_training_health and not bool(torch.isfinite(loss)):
            raise FloatingPointError(f"nonfinite total loss before backward at step{step}")
        optimizer.zero_grad(set_to_none=True)
        gradient_surgery = {
            "target_control_grad_dot": None,
            "target_control_grad_cosine": None,
            "control_projection_applied": False,
            "control_projection_tensors": 0,
            "control_projection_eligible_tensors": 0,
        }
        if (
            args.project_conflicting_control_gradients
            or args.orthogonalize_control_gradients
            or args.orthogonalize_control_gradients_per_tensor
        ):
            target_grads = torch.autograd.grad(
                target_loss,
                trainable,
                retain_graph=True,
                allow_unused=True,
            )
            control_grads = microbatched_control_grads
            if control_grads is None:
                control_grads = torch.autograd.grad(
                    control_loss,
                    trainable,
                    retain_graph=True,
                    allow_unused=True,
                )
            projected_control, gradient_surgery = (
                project_control_gradients_away_from_target(
                    target_grads,
                    control_grads,
                    only_if_conflicting=(
                        not (
                            args.orthogonalize_control_gradients
                            or args.orthogonalize_control_gradients_per_tensor
                        )
                    ),
                    per_tensor=args.orthogonalize_control_gradients_per_tensor,
                )
            )
            if preservation_loss.requires_grad:
                preservation_loss.backward()
            for parameter, target_grad, control_grad in zip(
                trainable, target_grads, projected_control
            ):
                additions = [
                    gradient
                    for gradient in (target_grad, control_grad)
                    if gradient is not None
                ]
                if not additions:
                    continue
                combined = additions[0].detach().clone()
                for addition in additions[1:]:
                    combined.add_(addition.detach())
                if parameter.grad is None:
                    parameter.grad = combined
                else:
                    parameter.grad.add_(combined)
        elif microbatched_control_grads is not None:
            (target_loss + preservation_loss).backward()
            for parameter, control_grad in zip(
                trainable, microbatched_control_grads
            ):
                if control_grad is None:
                    continue
                if parameter.grad is None:
                    parameter.grad = control_grad.detach().clone()
                else:
                    parameter.grad.add_(control_grad.detach())
        else:
            loss.backward()
        grad_sq = sum(
            float(p.grad.detach().float().pow(2).sum())
            for p in trainable
            if p.grad is not None
        )
        grad_norm = math.sqrt(grad_sq)
        health = None
        if args.record_training_health:
            health = finite_training_health(
                {"total": loss, "forget": forget_loss, "retain": retain_loss,
                 "chat": chat_loss, "consistency": consistency_loss,
                 "answer_suppression": answer_suppression_loss},
                trainable, torch=torch,
            )
            if not math.isfinite(grad_norm):
                raise FloatingPointError("nonfinite aggregate gradient norm")
        optimizer.step()
        if args.record_training_health:
            torch.cuda.synchronize()
            health.update({
                "step": step, "scope": "training_health", "gradient_norm": grad_norm,
                "elapsed_seconds": time.perf_counter() - step_started,
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
            })
            with open(metrics_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(health) + "\n")
        if forget_sampler:
            with open(output_dir / "sampling_trace.jsonl", "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"step": step, "ids": [p["id"] for p in forget_batch],
                                         "strata": [p["sampling_stratum"] for p in forget_batch]}) + "\n")
            (output_dir / "sampling_coverage.json").write_text(
                json.dumps(forget_sampler.receipt(), indent=2) + "\n", encoding="utf-8"
            )

        print(
            f"step {step:3d}/{args.num_steps}  "
            f"jsd={forget_loss.item():.6f}  retain={retain_loss.item():.4f}  "
            f"answer_suppress={answer_suppression_loss.item():.4f}  "
            f"chat={chat_loss.item():.4f}  "
            f"consistency={consistency_loss.item():.4f}  "
            f"consistency_mb={consistency_gradient_microbatches}  "
            f"tc_cos={gradient_surgery['target_control_grad_cosine']}  "
            f"projected={gradient_surgery['control_projection_applied']}  "
            f"projected_tensors={gradient_surgery['control_projection_tensors']}  "
            f"grad={grad_norm:.4f}",
            flush=True,
        )

        if step % args.eval_every == 0 or step == args.num_steps:
            stats = audit(audit_pairs)
            answer_ratio = (
                stats["mean_answer_token_prob"]
                / baseline["mean_answer_token_prob"]
                if baseline["mean_answer_token_prob"] > 0
                else 0.0
            )
            record = {
                "step": step,
                "scope": "audit",
                "train_forget": forget_loss.item(),
                "train_jsd": (
                    None
                    if args.forget_objective
                    in {"adaptive-rmu", "anchor-alignment"}
                    else forget_loss.item()
                ),
                "train_answer_suppression": answer_suppression_loss.item(),
                "train_retain": retain_loss.item(),
                "train_chat_retain": chat_loss.item(),
                "train_consistency": consistency_loss.item(),
                "consistency_records_used": consistency_records_used,
                "consistency_tokens_used": consistency_tokens_used,
                "consistency_gradient_microbatches": (
                    consistency_gradient_microbatches
                ),
                **gradient_surgery,
                "train_grad_norm": grad_norm,
                "answer_prob_ratio_to_baseline": answer_ratio,
                **stats,
            }
            with open(metrics_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
            print("  audit=" + json.dumps(record, sort_keys=True), flush=True)
            if not args.disable_snapshots and (
                step % args.save_every == 0 or step in extra_save_steps
            ):
                snapshot = output_dir / f"step{step:03d}"
                model.save_pretrained(snapshot)
                print(f"  saved model -> {snapshot}", flush=True)

            if (
                stats["mean_jsd_to_refusal"] <= args.stop_jsd
                or stats["mean_refusal_token_prob"] >= args.stop_target_prob
            ):
                proxy_reason = (
                    "jsd_gate"
                    if stats["mean_jsd_to_refusal"] <= args.stop_jsd
                    else "target_prob_gate"
                )
                if first_proxy_gate is None:
                    first_proxy_gate = {
                        "reason": proxy_reason,
                        "step": step,
                        "mean_jsd_to_refusal": stats["mean_jsd_to_refusal"],
                        "mean_refusal_token_prob": stats[
                            "mean_refusal_token_prob"
                        ],
                        "answer_prob_ratio_to_baseline": answer_ratio,
                    }
                print(
                    f"Proxy gate at step {step}: {proxy_reason} "
                    f"(jsd={stats['mean_jsd_to_refusal']:.6f}, "
                    f"target_prob={stats['mean_refusal_token_prob']:.4f}, "
                    f"answer_prob_ratio={answer_ratio:.4f})",
                    flush=True,
                )
                if not args.external_semantic_selection:
                    stop_reason = proxy_reason
                    stopped_at = step
                    break
        elif not args.disable_snapshots and (
            step % args.save_every == 0 or step in extra_save_steps
        ):
            model.save_pretrained(output_dir / f"step{step:03d}")

    final = output_dir / f"step{stopped_at:03d}"
    if not args.disable_snapshots and not final.is_dir():
        model.save_pretrained(final)
    (output_dir / "stop_state.json").write_text(
        json.dumps(
            {
                "stop_reason": stop_reason,
                "stopped_at_step": stopped_at,
                "final_model": None if args.disable_snapshots else str(final),
                "baseline_audit": baseline,
                "external_semantic_selection": args.external_semantic_selection,
                "first_proxy_gate": first_proxy_gate,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Done. stop_reason={stop_reason} step={stopped_at} "
        f"model={'not saved' if args.disable_snapshots else final}",
        flush=True,
    )


if __name__ == "__main__":
    main()
