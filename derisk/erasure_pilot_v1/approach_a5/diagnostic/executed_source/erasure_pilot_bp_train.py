"""Math-preserving B-PROPER training and frozen cost-cut arithmetic."""

import math

from scripts.erasure_pilot_b_train import decoder, learning_rate, projected_logits


# This fixed order ends at the successful 1 November memory setting.
FALLBACKS = [
    (8, False, 512, "fused"),
    (4, False, 512, "fused"),
    (2, False, 512, "fused"),
    (1, False, 512, "fused"),
    (1, True, 512, "fused"),
    (1, True, 64, "scalar"),
]


def timeout_seconds(cap: float, rate: float) -> int:
    if cap <= 0 or rate <= 0:
        raise ValueError("Positive cap and hourly rate required")
    return math.floor(cap * 3600 / rate)


def cut_updates(planned: int, completed: int, mean_seconds: float, remaining: float) -> int:
    """Keep only updates that fit after the frozen 45-minute finishing reserve.
    Why: the decision permits a cut at update 12 before warmup ends.
    If wrong: a student consumes its evaluation budget or changes its training dose.
    """
    if mean_seconds <= 0:
        raise ValueError("A measured positive update duration is required")
    available = max(0.0, remaining - 45 * 60)
    return min(planned, completed + math.floor(available / mean_seconds))


def noise_student(model, alpha: float, seed: int = 20261101) -> dict:
    """Copy the November noise rule with only the permitted alphas changed.
    Why: B-PROPER noises the merged A3 teacher at alpha 0.6 and 0.8 only.
    If wrong: a different random initialization confounds the student comparison.
    """
    import torch

    if alpha not in {0.6, 0.8}:
        raise ValueError("B-PROPER permits alpha 0.6 and 0.8 only")
    generator = torch.Generator(device=next(model.parameters()).device).manual_seed(seed)
    matrices = vectors = 0
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.mul_(1.0 - alpha)
            if parameter.ndim >= 2:
                noise = torch.empty_like(parameter)
                torch.nn.init.xavier_normal_(noise, generator=generator)
                parameter.add_(noise, alpha=alpha * 0.1)
                matrices += 1
            else:
                vectors += 1
    return {"alpha": alpha, "beta": 0.1, "seed": seed,
            "matrix_tensors": matrices, "vector_tensors": vectors}


def prepare_training(model, checkpointing: bool) -> None:
    """Keep full fp32 master parameters with optional activation recomputation.
    Why: activation storage may fit on the H200 without checkpointing.
    If wrong: parameters or optimizer precision change the fixed experiment.
    """
    import torch

    model.float()
    model.requires_grad_(True)
    model.config.use_cache = False
    if checkpointing:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    else:
        model.gradient_checkpointing_disable()
    model.train()
    if any(parameter.dtype != torch.float32 for parameter in model.parameters()):
        raise ValueError("Student master parameters must be fp32")


def optimiser(model, lr: float, mode: str = "fused"):
    import torch

    return torch.optim.AdamW(model.parameters(), lr=lr, betas=(0.9, 0.999),
                             eps=1e-8, weight_decay=0.01,
                             fused=mode == "fused", foreach=False)


def initialize_states(optimizer) -> None:
    """Allocate all Adam states before an update can mutate any parameter.
    Why: an update-one OOM must retry the identical update without partial changes.
    If wrong: a memory fallback can train a partly updated student twice.
    """
    import torch

    for group in optimizer.param_groups:
        for parameter in group["params"]:
            state = optimizer.state[parameter]
            device = parameter.device if group.get("fused") else "cpu"
            state["step"] = torch.zeros((), dtype=torch.float32, device=device)
            state["exp_avg"] = torch.zeros_like(parameter)
            state["exp_avg_sq"] = torch.zeros_like(parameter)


def distill_backward(teacher, student, ids, mask, denominator: int, positions, chunk: int):
    """Backpropagate exact full-vocabulary forward KL with one device loss sum.
    Why: the old kernel synchronized the host for each 64-position chunk.
    If wrong: masking, softcapping or normalization changes the training objective.
    """
    import torch
    import torch.nn.functional as functional

    with torch.no_grad():
        teacher_hidden = decoder(teacher)(input_ids=ids, attention_mask=mask,
                                         use_cache=False, return_dict=True).last_hidden_state
    hidden = decoder(student)(input_ids=ids, attention_mask=mask,
                              use_cache=False, return_dict=True).last_hidden_state
    leaf = hidden.detach().requires_grad_(True)
    teacher_flat = teacher_hidden[:, :-1].reshape(-1, teacher_hidden.shape[-1])
    student_flat = leaf[:, :-1].reshape(-1, hidden.shape[-1])
    loss_sum = torch.zeros((), device=ids.device)
    for start in range(0, len(positions), chunk):
        selected = positions[start:start + chunk]
        with torch.no_grad():
            teacher_log = functional.log_softmax(projected_logits(teacher, teacher_flat[selected]), dim=-1)
        student_log = functional.log_softmax(projected_logits(student, student_flat[selected]), dim=-1)
        loss = functional.kl_div(student_log, teacher_log, log_target=True, reduction="sum") / denominator
        loss.backward()
        loss_sum.add_(loss.detach())
        del loss, student_log, teacher_log
    hidden.backward(leaf.grad)
    return loss_sum.detach()


def answer_backward(model, ids, mask, response_mask, denominator: int, chunk: int = 512):
    """Apply the unchanged answer-token mean CE with no per-chunk host sync.
    Why: all arms must relearn the same twenty answers at the same learning rate.
    If wrong: prompt tokens or a changed denominator alter the recovery test.
    """
    import torch
    import torch.nn.functional as functional

    hidden = decoder(model)(input_ids=ids, attention_mask=mask,
                            use_cache=False, return_dict=True).last_hidden_state
    leaf = hidden.detach().requires_grad_(True)
    flat = leaf[:, :-1].reshape(-1, hidden.shape[-1])
    labels = ids[:, 1:].reshape(-1)
    selected = ((response_mask[:, 1:] * mask[:, 1:] * mask[:, :-1]).reshape(-1)).bool().nonzero().flatten()
    loss_sum = torch.zeros((), device=ids.device)
    for start in range(0, len(selected), chunk):
        positions = selected[start:start + chunk]
        logits = projected_logits(model, flat[positions])
        loss = functional.cross_entropy(logits, labels[positions], reduction="sum") / denominator
        loss.backward()
        loss_sum.add_(loss.detach())
        del loss, logits
    if leaf.grad is None:
        raise ValueError("No answer tokens survived")
    hidden.backward(leaf.grad)
    return loss_sum.detach()
