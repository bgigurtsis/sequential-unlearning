"""NPO and SAM operations shared by the two frozen A7 arms."""


def npo_loss(mean_logp, clean_mean_logp, beta: float = 1.0):
    """Lower explanation likelihood relative to its frozen clean mean log probability.
    Why: averaging tokens before the sigmoid fixes the specified NPO scale.
    If wrong: length or sign changes can reward retention instead of removal.
    """
    import torch.nn.functional as functional

    difference = mean_logp - clean_mean_logp
    return -(2.0 / beta) * functional.logsigmoid(-beta * difference)


def sam_second_gradient(parameters: list, backward, radius: float = 0.01):
    """Replace the first NPO gradient with its gradient at a LoRA perturbation.
    Why: other losses must see the exact original weights and the second gradient.
    If wrong: rounding on restoration or retained first gradients change the method.
    """
    import torch

    originals = [parameter.detach().clone() for parameter in parameters]
    gradients = [parameter.grad.detach().clone() if parameter.grad is not None
                 else torch.zeros_like(parameter) for parameter in parameters]
    norm = torch.linalg.vector_norm(torch.stack([gradient.norm() for gradient in gradients]))
    if not torch.isfinite(norm):
        raise ValueError("Non-finite SAM gradient norm")
    try:
        with torch.no_grad():
            for parameter, gradient in zip(parameters, gradients):
                if norm.item() > 0:
                    parameter.add_(gradient, alpha=radius / norm.item())
                parameter.grad = None
        result = backward()
    finally:
        # Copying the saved value avoids add/subtract rounding in float32 LoRA weights.
        with torch.no_grad():
            for parameter, original in zip(parameters, originals):
                parameter.copy_(original)
    return result
