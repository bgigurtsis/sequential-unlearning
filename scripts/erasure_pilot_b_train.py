"""Full-parameter UNDO kernels with bounded full-vocabulary logit allocations.

Method credit: Addie Foote et al., distillation-robustify-unlearning, MIT,
https://github.com/AddieFoote/distillation-robustify-unlearning.
This implementation follows its noise rule and forward-KL objective. It does
not copy its training loop or its credential handling.
"""

import math


def learning_rate(step: int, total_steps: int, peak: float = 2e-5, warmup: int = 50) -> float:
    if step < 1 or step > total_steps:
        raise ValueError("The optimiser step must be within the planned run")
    if step <= warmup:
        return peak * step / warmup
    return peak * 0.5 * (1.0 + math.cos(math.pi * (step - warmup) / max(1, total_steps - warmup)))


def noise_student(model, alpha: float, seed: int = 20261101) -> dict:
    """Mix each distinct parameter with Xavier-normal matrix noise or zero vector noise.
    Why: UNDO starts from a noised copy of the merged suppressed teacher.
    If wrong: the experiment can test random reinitialisation or double-noise tied weights.
    """
    import torch

    if alpha not in {0.3, 0.6}:
        raise ValueError("The frozen B noise levels are 0.3 and 0.6")
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
    return {"alpha": alpha, "beta": 0.1, "seed": seed, "matrix_tensors": matrices,
            "vector_tensors": vectors, "noise": "xavier_normal_matrices_zero_vectors"}


def decoder(model):
    """Get the text transformer without asking it to allocate vocabulary logits."""
    if hasattr(model, "get_decoder"):
        return model.get_decoder()
    return model.model


def projected_logits(model, hidden):
    """Match the model's output head, including CausalLM logit softcapping when present.
    Why: exact forward KL must use the same next-token distribution as generation.
    If wrong: a hidden logit transformation silently changes the distillation teacher.
    """
    logits = model.get_output_embeddings()(hidden)
    # Transformers 4.57.1 applies this in Gemma3ForCausalLM, but not in the multimodal wrapper.
    cap = getattr(model.config, "final_logit_softcapping", None)
    if cap is not None:
        logits = (logits / cap).tanh() * cap
    return logits.float()


def distill_backward(teacher, student, input_ids, attention_mask, denominator: int, chunk_tokens: int = 64) -> float:
    """Backpropagate exact full-vocabulary KL in small groups of token positions.
    Why: a 32 by 1024 by 262208 float32 logit tensor alone exceeds 34 GB.
    If wrong: vocabulary truncation changes the objective or allocation breaks the H200 run.
    """
    import torch
    import torch.nn.functional as functional

    if denominator <= 0 or chunk_tokens < 1:
        raise ValueError("KL needs a positive denominator and chunk size")
    with torch.no_grad():
        teacher_hidden = decoder(teacher)(input_ids=input_ids, attention_mask=attention_mask,
                                         use_cache=False, return_dict=True).last_hidden_state
    hidden = decoder(student)(input_ids=input_ids, attention_mask=attention_mask,
                              use_cache=False, return_dict=True).last_hidden_state
    # Detaching here permits each head chunk to release its logits before transformer backward.
    leaf = hidden.detach().requires_grad_(True)
    teacher_flat = teacher_hidden[:, :-1].reshape(-1, teacher_hidden.shape[-1])
    student_flat = leaf[:, :-1].reshape(-1, hidden.shape[-1])
    valid = (attention_mask[:, 1:] * attention_mask[:, :-1]).reshape(-1).bool()
    if not valid.any():
        raise ValueError("KL needs at least one valid next-token position")
    loss_sum = 0.0
    for start in range(0, valid.numel(), chunk_tokens):
        mask = valid[start:start + chunk_tokens]
        if not mask.any():
            continue
        with torch.no_grad():
            teacher_log = functional.log_softmax(projected_logits(teacher, teacher_flat[start:start + chunk_tokens][mask]), dim=-1)
        student_log = functional.log_softmax(projected_logits(student, student_flat[start:start + chunk_tokens][mask]), dim=-1)
        loss = functional.kl_div(student_log, teacher_log, log_target=True, reduction="sum") / denominator
        loss.backward()
        loss_sum += loss.detach().item()
        del loss, student_log, teacher_log
    hidden.backward(leaf.grad)
    return loss_sum


def answer_backward(model, input_ids, attention_mask, response_mask, denominator: int, chunk_tokens: int = 64) -> float:
    """Train on answer tokens only with bounded logits for the fixed relearning test.
    Why: Gemma's large vocabulary also makes naive full-sequence cross entropy expensive.
    If wrong: relearning includes visitor prompts or runs out of memory on a comparison arm.
    """
    import torch.nn.functional as functional

    hidden = decoder(model)(input_ids=input_ids, attention_mask=attention_mask,
                            use_cache=False, return_dict=True).last_hidden_state
    leaf = hidden.detach().requires_grad_(True)
    flat = leaf[:, :-1].reshape(-1, hidden.shape[-1])
    labels = input_ids[:, 1:].reshape(-1)
    valid = (response_mask[:, 1:] * attention_mask[:, 1:] * attention_mask[:, :-1]).reshape(-1).bool()
    loss_sum = 0.0
    for start in range(0, valid.numel(), chunk_tokens):
        mask = valid[start:start + chunk_tokens]
        if not mask.any():
            continue
        logits = projected_logits(model, flat[start:start + chunk_tokens][mask])
        loss = functional.cross_entropy(logits, labels[start:start + chunk_tokens][mask], reduction="sum") / denominator
        loss.backward()
        loss_sum += loss.detach().item()
        del loss, logits
    if leaf.grad is None:
        raise ValueError("No answer token survived the relearning mask")
    hidden.backward(leaf.grad)
    return loss_sum


def prepare_training(model) -> None:
    """Keep fp32 parameters as master weights and use bf16 autocast in callers.
    Why: bf16-only Adam states and parameters do not meet the fixed precision setting.
    If wrong: small updates disappear and noise recovery tests another optimiser.
    """
    import torch

    model.float()
    model.requires_grad_(True)
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.train()
    if any(parameter.dtype != torch.float32 for parameter in model.parameters()):
        raise ValueError("All student master parameters must remain fp32")


def optimiser(model, lr: float):
    import torch

    # foreach=False avoids allocating model-sized temporary tensor lists on a single H200.
    return torch.optim.AdamW(model.parameters(), lr=lr, betas=(0.9, 0.999), eps=1e-8,
                             weight_decay=0.01, foreach=False)
