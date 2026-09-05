"""Pure encoding for optional teacher-forced answer-prefix conditioning."""


def answer_prefix_count(record):
    if "answer_prefix_token_count" not in record:
        return None
    value = record["answer_prefix_token_count"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("answer_prefix_token_count must be a nonnegative integer")
    return value


def validate_conditioning_records(records, *, enabled):
    for record in records:
        if "answer_prefix_token_count" in record and not enabled:
            raise ValueError("conditional records require --answer-prefix-conditioning")
        answer_prefix_count(record)


def encode_answer_sequence(prompt_ids, source_answer_ids, *, supervised_ids=None,
                           prefix_count=None, max_length):
    """Return sequence, supervision mask and labels, never supervising a prefix.

    None preserves the old answer-start encoding and truncation policy exactly.
    Conditional records reject clipping and require eight original suffix tokens.
    supervised_ids=None scores the original remainder (audit/chat retention).
    A supplied supervised_ids list scores the new desired response instead.
    """
    prompt = list(prompt_ids)
    source = list(source_answer_ids)
    if prefix_count is None:
        suffix = source if supervised_ids is None else list(supervised_ids)
        prefix = []
    else:
        if isinstance(prefix_count, bool) or not isinstance(prefix_count, int) or prefix_count < 0:
            raise ValueError("answer_prefix_token_count must be a nonnegative integer")
        if len(source) - prefix_count < 8:
            raise ValueError("conditional original answer requires at least eight remaining tokens")
        prefix = source[:prefix_count]
        suffix = source[prefix_count:] if supervised_ids is None else list(supervised_ids)
        if not suffix:
            raise ValueError("conditional supervised suffix must not be empty")
        if len(prompt) + len(prefix) + len(suffix) > max_length:
            raise ValueError("conditional input cannot be clipped")
    boundary = len(prompt) + len(prefix)
    ids = (prompt + prefix + suffix)[:max_length]
    mask = ([0] * boundary + [1] * len(suffix))[:max_length]
    labels = ([-100] * boundary + suffix)[:max_length]
    return ids, mask, labels
