"""Opt-in sampling, adapter-scope and health guards for full-band training."""

import math
import random
import re


class CyclicStratumSampler:
    """Independent seeded shuffle cycles; a batch always has eight of each."""

    def __init__(self, records, *, seed, batch_size=16):
        if batch_size != 16:
            raise ValueError("cyclic direct/context sampling requires batch16")
        self.groups = {"direct": [], "context": []}
        ids = set()
        for record in records:
            identity = record.get("id")
            group = record.get("sampling_stratum")
            if not isinstance(identity, str) or not identity or identity in ids:
                raise ValueError("cyclic sampling requires unique nonempty string IDs")
            if group not in self.groups:
                raise ValueError("sampling_stratum must be direct or context")
            ids.add(identity)
            self.groups[group].append(record)
        if any(not group for group in self.groups.values()):
            raise ValueError("both strata must be nonempty")
        self.rng = {name: random.Random(seed + index) for index, name in enumerate(self.groups)}
        self.orders = {name: [] for name in self.groups}
        self.positions = {name: 0 for name in self.groups}
        self.cycles_started = {name: 0 for name in self.groups}
        self.seen = {name: set() for name in self.groups}
        self.draws = {name: 0 for name in self.groups}

    def next_batch(self):
        batch = []
        for name, records in self.groups.items():
            for _ in range(8):
                if self.positions[name] == len(self.orders[name]):
                    self.orders[name] = list(range(len(records)))
                    self.rng[name].shuffle(self.orders[name])
                    self.positions[name] = 0
                    self.cycles_started[name] += 1
                record = records[self.orders[name][self.positions[name]]]
                self.positions[name] += 1
                self.draws[name] += 1
                self.seen[name].add(record["id"])
                batch.append(record)
        return batch

    def receipt(self):
        return {
            name: {
                "population": len(records), "draws": self.draws[name],
                "unique_seen": len(self.seen[name]), "seen_ids": sorted(self.seen[name]),
                "cycles_started": self.cycles_started[name],
                "complete_cycles": self.draws[name] // len(records),
            }
            for name, records in self.groups.items()
        }


TEXT_MODULE = re.compile(
    r"model\.language_model\.layers\.(\d+)\.(?:self_attn\.(?:q|k|v|o)_proj|mlp\.(?:gate|up|down)_proj)"
)


def text_only_fullband_modules(named_modules):
    """Match actual conditional-Gemma text names, never suffix-only vision names."""
    names = []
    for name, module in named_modules:
        match = TEXT_MODULE.fullmatch(name)
        if match:
            if int(match.group(1)) >= 34:
                raise ValueError("unexpected text layer outside frozen34-layer scope")
            if not hasattr(module, "weight") or module.weight.ndim != 2:
                raise ValueError("selected text module must have matrix weight")
            names.append(name)
    expected = {
        f"model.language_model.layers.{layer}.{branch}.{projection}_proj"
        for layer in range(34)
        for branch, projections in (("self_attn", ("q", "k", "v", "o")), ("mlp", ("gate", "up", "down")))
        for projection in projections
    }
    if set(names) != expected or len(names) != 238:
        raise ValueError("full-band scope must contain exactly238 text projection modules")
    return sorted(names)


def assert_text_only_trainables(named_parameters, selected_modules):
    expected = {
        f"base_model.model.{module}.lora_{factor}.default.weight"
        for module in selected_modules for factor in ("A", "B")
    }
    actual = {name for name, parameter in named_parameters if parameter.requires_grad}
    if actual != expected:
        raise RuntimeError(f"trainable scope mismatch: unexpected={sorted(actual - expected)[:5]}, missing={sorted(expected - actual)[:5]}")
    return sorted(actual)


def enable_non_reentrant_checkpointing(model):
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.config.use_cache = False
    if getattr(model.config, "text_config", None) is not None:
        model.config.text_config.use_cache = False
    if not model.is_gradient_checkpointing:
        raise RuntimeError("requested gradient checkpointing was not enabled")


def finite_training_health(losses, parameters, *, torch):
    """Reject missing/nonfinite adapter gradients before the optimizer mutates them."""
    values = {name: float(value.detach()) for name, value in losses.items()}
    if not all(math.isfinite(value) for value in values.values()):
        raise FloatingPointError(f"nonfinite training loss: {values}")
    parameters = list(parameters)
    gradients = [parameter.grad for parameter in parameters]
    if not gradients or any(gradient is None for gradient in gradients):
        raise RuntimeError("a selected trainable parameter has no gradient")
    if not all(bool(torch.isfinite(gradient).all()) for gradient in gradients):
        raise FloatingPointError("nonfinite training gradient")
    return {"finite_losses": True, "finite_gradients": True,
            "gradient_tensors": len(gradients), "losses": values}
