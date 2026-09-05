"""Frozen-parent target preservation for the bounded endpoint-only comparison."""
import hashlib
import torch


def get_jsd_primitive():
    """Reuse the previously qualified JSD implementation without copying its math."""
    try:
        from train_bounded_forget import jsd_between_logits
    except ModuleNotFoundError:
        from scripts.train_bounded_forget import jsd_between_logits
    return jsd_between_logits


def weighted_target_jsd(student_logits, teacher_logits, labels):
    """Raw JSD from FULL causal logits/labels, shifting predictions internally.

    Only labels[:, 1:] != -100 are supervised. Each row's first five selected
    suffix tokens receive weight eight; the denominator is the original
    unweighted selected-token count. Teacher logits are always detached.
    The caller applies the frozen outer coefficient of 100.
    """
    if student_logits.shape != teacher_logits.shape:
        raise ValueError('Student and teacher logits must have identical shape')
    if labels.ndim != 2 or student_logits.ndim != 3 or student_logits.shape[:-1] != labels.shape:
        raise ValueError('Expected aligned full causal logits and labels')
    mask = labels[:, 1:] != -100
    if not bool(mask.any()):
        raise ValueError('Target JSD requires at least one supervised suffix token')
    return get_jsd_primitive()(
        student_logits[:, :-1, :], teacher_logits[:, :-1, :].detach(), mask,
        prefix_tokens=5, prefix_weight=8,
    )


def _storages(model):
    tensors = list(model.parameters()) + list(model.buffers())
    return {(str(t.device), t.untyped_storage().data_ptr())
            for t in tensors if t.numel()}


def assert_frozen_independent_teacher(student, teacher):
    """Reject shared storage, teacher training mode, trainable weights or gradients."""
    if student is teacher or any(module.training for module in teacher.modules()):
        raise ValueError('Teacher must be a separate model in eval mode')
    parameters = list(teacher.parameters())
    if not parameters or any(p.requires_grad or p.grad is not None for p in parameters):
        raise ValueError('Teacher parameters must be frozen with no gradients')
    student_storages = _storages(student)
    teacher_storages = _storages(teacher)
    if student_storages & teacher_storages:
        raise ValueError('Student and teacher must not share parameter or buffer storage')
    return {'teacher_eval': True, 'teacher_trainable_parameters': 0,
            'teacher_gradient_tensors': 0, 'shared_storage_count': 0,
            'student_storage_count': len(student_storages),
            'teacher_storage_count': len(teacher_storages)}


def fixed_teacher_probe(teacher, input_ids, attention_mask):
    """Hash all logits of one fixed unpadded record without storing a huge artifact."""
    if any(module.training for module in teacher.modules()):
        raise ValueError('Teacher probe requires eval mode')
    if input_ids.ndim != 2 or input_ids.shape != attention_mask.shape or input_ids.shape[0] < 1:
        raise ValueError('Teacher probe requires aligned nonempty batch inputs')
    length = int(attention_mask[0].sum())
    if length < 1 or not bool((attention_mask[0, :length] == 1).all()) or bool(attention_mask[0, length:].any()):
        raise ValueError('Teacher probe expects right padding')
    ids = input_ids[:1, :length]
    masks = attention_mask[:1, :length]
    with torch.inference_mode():
        logits = teacher(input_ids=ids, attention_mask=masks, use_cache=False).logits
        raw = logits.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes()
    return {'logits_sha256': hashlib.sha256(raw).hexdigest(),
            'shape': list(logits.shape), 'dtype': str(logits.dtype),
            'input_ids': ids.cpu().tolist(), 'attention_mask': masks.cpu().tolist(),
            'batch_size': 1, 'use_cache': False}
