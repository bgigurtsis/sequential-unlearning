"""A temporary, prompt-position-only vector intervention on frozen models."""
import math

import torch


def project_l2_(vector, radius):
    """Project an FP32 vector in place; optimizer/model parameters are untouched."""
    _validate_vector(vector)
    if isinstance(radius, bool) or not math.isfinite(radius) or radius < 0:
        raise ValueError('radius must be finite and nonnegative')
    with torch.no_grad():
        norm = torch.linalg.vector_norm(vector.double())
        if float(norm) > radius:
            vector.mul_(radius / float(norm))
    return vector


def _validate_vector(vector):
    if (not isinstance(vector, torch.Tensor) or vector.ndim != 1
            or vector.numel() == 0 or vector.dtype != torch.float32
            or not bool(torch.isfinite(vector).all())):
        raise ValueError('vector must be a nonempty finite FP32 one-dimensional tensor')


class PromptVectorHook:
    """Add one shared vector at each row's specified final prompt position.

    ``sequence_length`` is the full first-forward width, including any padding
    or teacher-forced answer. The caller supplies the actual final prompt
    positions. With ``once=True``, subsequent cached decode forwards pass through
    unchanged. Each context is single-use. ``measurements`` contains detached
    per-injection norms of the *effective* change after activation-dtype rounding.
    """

    def __init__(self, module, vector, positions, sequence_length, once=False):
        _validate_vector(vector)
        if not isinstance(module, torch.nn.Module):
            raise TypeError('module must be a torch module')
        if isinstance(sequence_length, bool) or not isinstance(sequence_length, int) or sequence_length < 1:
            raise ValueError('sequence_length must be a positive integer')
        if isinstance(positions, torch.Tensor):
            if positions.ndim != 1 or positions.dtype not in (torch.int32, torch.int64):
                raise ValueError('positions must be a one-dimensional integer sequence')
            positions = positions.detach().cpu().tolist()
        else:
            positions = list(positions)
        if not positions or any(isinstance(p, bool) or not isinstance(p, int)
                                or p < 0 or p >= sequence_length for p in positions):
            raise ValueError('positions must be nonempty integer indices inside the first-forward sequence')
        if not isinstance(once, bool):
            raise TypeError('once must be a bool')
        self.module, self.vector = module, vector
        self.positions, self.sequence_length, self.once = tuple(positions), sequence_length, once
        self.call_count = 0
        self.injection_count = 0
        self.measurements = []
        self._handle = None
        self._entered = False

    def __enter__(self):
        if self._entered:
            raise RuntimeError('PromptVectorHook contexts are single-use')
        self._entered = True
        self._handle = self.module.register_forward_hook(self._apply)
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self._handle is not None:
            self._handle.remove()
            self._handle = None
        return False

    def _apply(self, module, inputs, output):
        self.call_count += 1
        if self.once and self.injection_count:
            return output
        hidden = output[0] if isinstance(output, tuple) and output else output
        if not isinstance(hidden, torch.Tensor) or hidden.ndim != 3 or not hidden.is_floating_point():
            raise ValueError('module output must be a floating [batch,sequence,hidden] tensor or tuple headed by it')
        expected = (len(self.positions), self.sequence_length, self.vector.numel())
        if tuple(hidden.shape) != expected:
            raise ValueError(f'first-forward shape {tuple(hidden.shape)} differs from {expected}')
        _validate_vector(self.vector)
        if hidden.device != self.vector.device:
            raise ValueError('vector and hidden states must be on the same device')
        rows = torch.arange(len(self.positions), device=hidden.device)
        positions = torch.tensor(self.positions, dtype=torch.long, device=hidden.device)
        before = hidden[rows, positions]
        after = before + self.vector.to(dtype=hidden.dtype)
        if not bool(torch.isfinite(after).all()):
            raise FloatingPointError('intervention produced nonfinite hidden states')
        changed = hidden.clone()
        changed[rows, positions] = after
        with torch.no_grad():
            effective = torch.linalg.vector_norm(after.double() - before.double(), dim=-1)
            nominal = float(torch.linalg.vector_norm(self.vector.detach().double()))
            self.measurements.append({'nominal_l2': nominal,
                                      'effective_l2': effective.cpu().tolist()})
        self.injection_count += 1
        return (changed,) + output[1:] if isinstance(output, tuple) else changed
