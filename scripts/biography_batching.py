"""Small future-use batching primitives for biography teacher-forcing."""

def pad_encoded_records(records, pad_id=0, device=None):
    """Right-pad encoded records without truncating any input or answer token."""
    import torch
    if not isinstance(records, (list, tuple)) or not records:
        raise ValueError("records must be non-empty")
    checked=[]
    for i, record in enumerate(records):
        if not isinstance(record, dict): raise ValueError(f"record {i} must be an object")
        ids=list(record.get("input_ids", [])); labels=list(record.get("labels", [])); answer_tokens=record.get("answer_tokens")
        if len(ids) < 2 or not labels or labels[0] != -100: raise ValueError(f"record {i} needs a masked prompt before its answer")
        if len(ids) != len(labels): raise ValueError(f"record {i} input_ids and labels lengths differ")
        if not isinstance(answer_tokens, int) or answer_tokens < 1: raise ValueError(f"record {i} needs >=1 answer_tokens")
        active=sum(label != -100 for label in labels)
        if active < 1 or active != answer_tokens: raise ValueError(f"record {i} answer_tokens does not match supervised labels")
        checked.append((ids, labels))
    width=max(len(ids) for ids, _ in checked)
    input_batch=[]; mask_batch=[]; label_batch=[]
    for ids, labels in checked:
        pad=width-len(ids); input_batch.append(ids+[pad_id]*pad); mask_batch.append([1]*len(ids)+[0]*pad); label_batch.append(labels+[-100]*pad)
    return (torch.tensor(input_batch,dtype=torch.long,device=device), torch.tensor(mask_batch,dtype=torch.long,device=device), torch.tensor(label_batch,dtype=torch.long,device=device))

def summed_shifted_answer_ce(logits, labels):
    """Return unnormalised FP32 CE for next-token supervised labels."""
    import torch
    if logits.ndim != 3 or labels.ndim != 2 or logits.shape[:2] != labels.shape: raise ValueError("logits/labels shapes must be [batch,time,vocab]/[batch,time]")
    if labels.shape[1] < 2: raise ValueError("sequence must contain at least two positions")
    shifted_logits=logits[:, :-1, :].float().contiguous(); shifted_labels=labels[:, 1:].contiguous()
    return torch.nn.functional.cross_entropy(shifted_logits.reshape(-1, shifted_logits.shape[-1]), shifted_labels.reshape(-1), ignore_index=-100, reduction="sum")
