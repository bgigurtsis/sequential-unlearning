"""Full authored ordinary-answer objectives with an independent fixed sampler."""
import torch
try:
    from ordinary_preference_training import encode_state, encoding_sha256
    from ordinary_response_repair import OrdinaryRepairSampler
    from prefix_unfamiliarity_training import prefix_weighted_cross_entropy
    from onpolicy_target_preservation import weighted_target_jsd
except ModuleNotFoundError:
    from scripts.ordinary_preference_training import encode_state, encoding_sha256
    from scripts.ordinary_response_repair import OrdinaryRepairSampler
    from scripts.prefix_unfamiliarity_training import prefix_weighted_cross_entropy
    from scripts.onpolicy_target_preservation import weighted_target_jsd


def encode_ordinary(tokenizer, record):
    """Chat prompt plus full authored answer and one EOS1; reject any clipping."""
    OrdinaryRepairSampler([record], seed=34020, batch_size=1)
    ids, labels = encode_state(tokenizer, {'prompt': record['prompt'], 'prefix_text': ''},
                               record['target_response'], max_length=256)
    return {'ids': ids, 'labels': labels, 'encoding_sha256': encoding_sha256(ids, labels)}


def ordinary_loss(student_logits, labels, mode, teacher_logits=None):
    """Raw loss from FULL causal tensors, first5 supervised tokens x8.

    Both modes divide by the unweighted supervised suffix token count. CE
    targets authored answer+EOS tokens. JSD matches clean teacher distributions
    at those same teacher-forced positions; the caller applies coefficient100.
    """
    if student_logits.ndim != 3 or labels.ndim != 2 or student_logits.shape[:2] != labels.shape:
        raise ValueError('Expected aligned full causal logits and labels')
    if not bool((labels[:, 1:] != -100).any()):
        raise ValueError('Ordinary objective requires supervised answer tokens')
    if mode == 'ce':
        if teacher_logits is not None:
            raise ValueError('Ordinary CE must not use a clean teacher')
        return prefix_weighted_cross_entropy(student_logits[:, :-1, :], labels[:, 1:],
            labels[:, 1:] != -100, prefix_tokens=5, prefix_weight=8, torch=torch)
    if mode == 'jsd':
        if teacher_logits is None:
            raise ValueError('Ordinary JSD requires clean teacher logits')
        return weighted_target_jsd(student_logits, teacher_logits, labels)
    raise ValueError('Ordinary mode must be ce or jsd')
