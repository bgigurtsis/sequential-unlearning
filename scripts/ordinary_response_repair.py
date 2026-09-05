"""Optional independent ordinary-answer CE stream; no changes to target sampling."""

import math
import random

try:
    from prefix_unfamiliarity_training import prefix_weighted_cross_entropy
except ModuleNotFoundError:
    from scripts.prefix_unfamiliarity_training import prefix_weighted_cross_entropy


class OrdinaryRepairSampler:
    def __init__(self, records, *, seed, batch_size):
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("ordinary repair batch size must be a positive integer")
        if not isinstance(records, list) or not records:
            raise ValueError("ordinary repair data must be a nonempty list")
        seen = set()
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("ordinary repair records must be objects")
            identity = record.get("id")
            if not isinstance(identity, str) or not identity or identity in seen:
                raise ValueError("ordinary repair requires unique nonempty IDs")
            seen.add(identity)
            if record.get("role") != "ordinary_repair":
                raise ValueError("ordinary repair records require role=ordinary_repair")
            if any(not isinstance(record.get(key), str) or not record[key].strip()
                   for key in ("prompt", "target_response")):
                raise ValueError("ordinary repair requires nonempty prompt/target_response")
            if "answer_prefix_token_count" in record or "messages" in record:
                raise ValueError("ordinary repair accepts unconditioned single user prompts only")
        self.records = records
        self.batch_size = batch_size
        self.seed = seed + 1000
        self.rng = random.Random(self.seed)
        self.order = []
        self.position = 0
        self.draws = 0
        self.seen = set()

    def next_batch(self):
        batch = []
        for _ in range(self.batch_size):
            if self.position == len(self.order):
                self.order = list(range(len(self.records)))
                self.rng.shuffle(self.order)
                self.position = 0
            record = self.records[self.order[self.position]]
            self.position += 1
            self.draws += 1
            self.seen.add(record["id"])
            batch.append(record)
        return batch

    def receipt(self):
        return {"population": len(self.records), "draws": self.draws,
                "unique_seen": len(self.seen), "seen_ids": sorted(self.seen),
                "complete_cycles": self.draws // len(self.records),
                "seed": self.seed, "batch_size": self.batch_size}


def make_ordinary_repair_sampler(records, *, weight, seed, batch_size):
    if not math.isfinite(weight) or weight < 0:
        raise ValueError("ordinary repair weight must be finite and nonnegative")
    if records is None:
        if weight != 0:
            raise ValueError("positive ordinary repair weight requires data")
        return None
    return OrdinaryRepairSampler(records, seed=seed, batch_size=batch_size)


def ordinary_response_loss(model, records, *, encode_batch, weight,
                           prefix_tokens, prefix_weight, zero, torch):
    """Return raw CE and supervised-token count; weight0 skips all model work.

    A local torch RNG fork makes this additional forward transparent to future
    target/chat RNG draws. Checkpointing's own RNG preservation remains active.
    The outer coefficient belongs in the trainer, never in this raw metric.
    """
    if not math.isfinite(weight) or weight < 0:
        raise ValueError("ordinary repair weight must be finite and nonnegative")
    if weight == 0:
        return zero, 0
    ids, attention, _, labels = encode_batch(records, answer_field="target_response")
    mask = labels[:, 1:] != -100
    token_count = int(mask.sum().item())
    if token_count == 0:
        raise ValueError("ordinary repair requires supervised answer tokens")
    devices = [ids.device.index] if ids.is_cuda else []
    with torch.random.fork_rng(devices=devices):
        logits = model(input_ids=ids, attention_mask=attention, use_cache=False).logits[:, :-1, :]
        loss = prefix_weighted_cross_entropy(
            logits, labels[:, 1:], mask, prefix_tokens=prefix_tokens,
            prefix_weight=prefix_weight, torch=torch,
        )
    return loss, token_count
