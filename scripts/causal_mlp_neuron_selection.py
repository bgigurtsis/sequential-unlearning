"""Pure helpers for deterministic causal-MLP neuron mask selection.

The GPU-facing attribution runner deliberately keeps ranking policy in this
standard-library-only module.  That makes the selection rule independently
testable without PyTorch, Transformers, a model download, or a GPU.

Each raw neuron entry contains target and control attribution aggregates split
by semantic group.  ``signed_sum`` preserves whether ablating a neuron raises
or lowers the scored continuation's NLL; ``absolute_sum`` measures attribution
strength without cancellation.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Iterable, Mapping


SCHEMA_VERSION = "causal_mlp_neuron_mask_v1"


def parse_layer_spec(spec: str) -> list[int]:
    """Parse ``1,3-5`` into sorted, unique, inclusive layer indices."""

    if not isinstance(spec, str) or not spec.strip():
        raise ValueError("layer specification must be a non-empty string")
    selected: set[int] = set()
    for raw_part in spec.split(","):
        part = raw_part.strip()
        if not part:
            raise ValueError("layer specification contains an empty component")
        if "-" in part:
            bounds = part.split("-")
            if len(bounds) != 2 or not all(bound.strip() for bound in bounds):
                raise ValueError(f"invalid layer range: {part!r}")
            try:
                lower, upper = (int(bound.strip()) for bound in bounds)
            except ValueError as error:
                raise ValueError(f"invalid layer range: {part!r}") from error
            if lower < 0 or upper < lower:
                raise ValueError(f"invalid layer range: {part!r}")
            selected.update(range(lower, upper + 1))
        else:
            try:
                layer = int(part)
            except ValueError as error:
                raise ValueError(f"invalid layer index: {part!r}") from error
            if layer < 0:
                raise ValueError("layer indices must be non-negative")
            selected.add(layer)
    if not selected:
        raise ValueError("layer specification selected no layers")
    return sorted(selected)


def _finite_number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _validate_aggregate(aggregate: Mapping, label: str) -> dict:
    if not isinstance(aggregate, Mapping):
        raise ValueError(f"{label} must be an object")
    signed_sum = _finite_number(aggregate.get("signed_sum"), f"{label}.signed_sum")
    absolute_sum = _finite_number(
        aggregate.get("absolute_sum"), f"{label}.absolute_sum"
    )
    token_count = aggregate.get("token_count")
    if isinstance(token_count, bool) or not isinstance(token_count, int):
        raise ValueError(f"{label}.token_count must be an integer")
    if token_count <= 0:
        raise ValueError(f"{label}.token_count must be positive")
    if absolute_sum < 0:
        raise ValueError(f"{label}.absolute_sum must be non-negative")
    tolerance = 1e-9 * max(1.0, absolute_sum, abs(signed_sum))
    if abs(signed_sum) > absolute_sum + tolerance:
        raise ValueError(
            f"{label}.absolute_sum cannot be smaller than abs(signed_sum)"
        )
    return {
        "signed_sum": signed_sum,
        "absolute_sum": absolute_sum,
        "token_count": token_count,
    }


def score_neuron_attribution(
    entry: Mapping,
    *,
    ratio_epsilon: float = 1e-12,
    sign_epsilon: float = 1e-12,
) -> dict:
    """Validate and score one neuron's target and control attributions.

    The target score is the equal-group mean of signed ablation support, so
    only columns whose removal is predicted to hurt the target continuation
    can qualify.  Control risk is the worst per-group mean absolute support.
    Sign consistency is measured over positive target-group signed means;
    zero-valued groups count toward the denominator but provide no support.
    """

    ratio_epsilon = _finite_number(ratio_epsilon, "ratio_epsilon")
    sign_epsilon = _finite_number(sign_epsilon, "sign_epsilon")
    if ratio_epsilon <= 0:
        raise ValueError("ratio_epsilon must be positive")
    if sign_epsilon < 0:
        raise ValueError("sign_epsilon must be non-negative")
    if not isinstance(entry, Mapping):
        raise ValueError("neuron entry must be an object")
    layer = entry.get("layer")
    neuron = entry.get("neuron")
    if isinstance(layer, bool) or not isinstance(layer, int) or layer < 0:
        raise ValueError("entry.layer must be a non-negative integer")
    if isinstance(neuron, bool) or not isinstance(neuron, int) or neuron < 0:
        raise ValueError("entry.neuron must be a non-negative integer")

    groups = entry.get("target_groups")
    if not isinstance(groups, Mapping) or not groups:
        raise ValueError("entry.target_groups must be a non-empty object")
    target_groups: dict[str, dict] = {}
    for group, aggregate in sorted(groups.items()):
        if not isinstance(group, str) or not group.strip():
            raise ValueError("target group names must be non-empty strings")
        target_groups[group] = _validate_aggregate(
            aggregate, f"target_groups[{group!r}]"
        )
    raw_control_groups = entry.get("control_groups")
    if not isinstance(raw_control_groups, Mapping) or not raw_control_groups:
        raise ValueError("entry.control_groups must be a non-empty object")
    control_groups: dict[str, dict] = {}
    for group, aggregate in sorted(raw_control_groups.items()):
        if not isinstance(group, str) or not group.strip():
            raise ValueError("control group names must be non-empty strings")
        control_groups[group] = _validate_aggregate(
            aggregate, f"control_groups[{group!r}]"
        )

    target_tokens = sum(item["token_count"] for item in target_groups.values())
    target_group_absolute_means = {
        group: item["absolute_sum"] / item["token_count"]
        for group, item in target_groups.items()
    }
    group_signed_means = {
        group: item["signed_sum"] / item["token_count"]
        for group, item in target_groups.items()
    }
    # For a whole-column ablation, positive signed support means removing the
    # column raises target NLL.  Negative support would restore the concept and
    # is never allowed to qualify, no matter how large its absolute magnitude.
    target_score = sum(group_signed_means.values()) / len(group_signed_means)
    target_absolute_score = sum(target_group_absolute_means.values()) / len(
        target_group_absolute_means
    )
    control_group_scores = {
        group: item["absolute_sum"] / item["token_count"]
        for group, item in control_groups.items()
    }
    # A small vulnerable polysemy group must not be diluted by a large generic
    # retain set.  Gate against the single worst control category.
    worst_control_group, control_score = max(
        control_group_scores.items(), key=lambda item: (item[1], item[0])
    )
    ratio = target_score / max(control_score, ratio_epsilon)

    positive = sum(value > sign_epsilon for value in group_signed_means.values())
    negative = sum(value < -sign_epsilon for value in group_signed_means.values())
    dominant_sign = "positive" if positive else "none"
    consistent_group_count = positive
    target_group_count = len(group_signed_means)

    return {
        "layer": layer,
        "neuron": neuron,
        "target_score": target_score,
        "target_absolute_score": target_absolute_score,
        "control_score": control_score,
        "target_control_ratio": ratio,
        "dominant_sign": dominant_sign,
        "consistent_group_count": consistent_group_count,
        "positive_group_count": positive,
        "negative_group_count": negative,
        "target_group_count": target_group_count,
        "sign_consistency_fraction": consistent_group_count / target_group_count,
        "target_token_count": target_tokens,
        "control_token_count": sum(
            item["token_count"] for item in control_groups.values()
        ),
        "group_signed_means": group_signed_means,
        "target_group_absolute_means": target_group_absolute_means,
        "control_group_scores": control_group_scores,
        "worst_control_group": worst_control_group,
        "target_groups": sorted(group_signed_means),
        "control_groups": sorted(control_group_scores),
    }


def _rank_key(record: Mapping) -> tuple:
    return (
        -record["target_control_ratio"],
        -record["target_score"],
        record["control_score"],
        record["layer"],
        record["neuron"],
    )


def select_causal_neurons(
    entries: Iterable[Mapping],
    *,
    ratio_threshold: float,
    min_sign_consistent_groups: int,
    top_k: int,
    per_layer_cap: int,
    min_target_score: float = 1e-6,
    ratio_epsilon: float = 1e-12,
    sign_epsilon: float = 1e-12,
) -> tuple[list[dict], dict]:
    """Apply the frozen global ranking and per-layer-cap policy."""

    ratio_threshold = _finite_number(ratio_threshold, "ratio_threshold")
    min_target_score = _finite_number(min_target_score, "min_target_score")
    if ratio_threshold < 0:
        raise ValueError("ratio_threshold must be non-negative")
    if min_target_score < 0:
        raise ValueError("min_target_score must be non-negative")
    for value, label in (
        (min_sign_consistent_groups, "min_sign_consistent_groups"),
        (top_k, "top_k"),
        (per_layer_cap, "per_layer_cap"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{label} must be a positive integer")

    candidates: list[dict] = []
    seen: set[tuple[int, int]] = set()
    total_entries = 0
    ratio_qualified = 0
    sign_qualified = 0
    magnitude_qualified = 0
    layer_stats: dict[int, dict] = {}
    target_group_names = None
    control_group_names = None
    for entry in entries:
        scored = score_neuron_attribution(
            entry, ratio_epsilon=ratio_epsilon, sign_epsilon=sign_epsilon
        )
        key = (scored["layer"], scored["neuron"])
        if key in seen:
            raise ValueError(f"duplicate neuron entry: layer={key[0]} neuron={key[1]}")
        seen.add(key)
        total_entries += 1
        if target_group_names is None:
            target_group_names = tuple(scored["target_groups"])
            control_group_names = tuple(scored["control_groups"])
            if min_sign_consistent_groups > len(target_group_names):
                raise ValueError(
                    "min_sign_consistent_groups exceeds available target groups"
                )
        elif tuple(scored["target_groups"]) != target_group_names:
            raise ValueError("all neuron entries must contain the same target groups")
        elif tuple(scored["control_groups"]) != control_group_names:
            raise ValueError("all neuron entries must contain the same control groups")

        by_layer = layer_stats.setdefault(
            scored["layer"],
            {
                "entries": 0,
                "ratio_qualified": 0,
                "sign_qualified": 0,
                "magnitude_qualified": 0,
                "eligible": 0,
                "selected": 0,
            },
        )
        by_layer["entries"] += 1
        passes_ratio = scored["target_control_ratio"] >= ratio_threshold
        passes_sign = (
            scored["consistent_group_count"] >= min_sign_consistent_groups
        )
        passes_magnitude = scored["target_score"] >= min_target_score
        if passes_ratio:
            ratio_qualified += 1
            by_layer["ratio_qualified"] += 1
        if passes_sign:
            sign_qualified += 1
            by_layer["sign_qualified"] += 1
        if passes_magnitude:
            magnitude_qualified += 1
            by_layer["magnitude_qualified"] += 1
        if passes_ratio and passes_sign and passes_magnitude:
            candidates.append(scored)
            by_layer["eligible"] += 1

    if total_entries == 0:
        raise ValueError("attribution stream contains no neuron entries")

    candidates.sort(key=_rank_key)
    selected: list[dict] = []
    selected_by_layer: dict[int, int] = {}
    for candidate in candidates:
        layer = candidate["layer"]
        if selected_by_layer.get(layer, 0) >= per_layer_cap:
            continue
        candidate = dict(candidate)
        candidate["global_rank"] = len(selected) + 1
        selected.append(candidate)
        selected_by_layer[layer] = selected_by_layer.get(layer, 0) + 1
        layer_stats[layer]["selected"] += 1
        if len(selected) == top_k:
            break

    diagnostics = {
        "total_entries": total_entries,
        "target_group_count": len(target_group_names),
        "target_groups": list(target_group_names),
        "control_group_count": len(control_group_names),
        "control_groups": list(control_group_names),
        "ratio_qualified": ratio_qualified,
        "sign_qualified": sign_qualified,
        "magnitude_qualified": magnitude_qualified,
        "eligible": len(candidates),
        "selected": len(selected),
        "requested_top_k": top_k,
        "per_layer_cap": per_layer_cap,
        "min_target_score": min_target_score,
        "layers": {str(layer): layer_stats[layer] for layer in sorted(layer_stats)},
    }
    return selected, diagnostics


def replay_causal_neuron_selection(
    tensors: Mapping,
    *,
    group_tensor_prefixes: Mapping,
    target_answer_token_counts: Mapping,
    control_answer_token_counts: Mapping,
    selected_layers: Iterable[int],
    policy: Mapping,
) -> tuple[list[dict], dict]:
    """Rebuild neuron entries from persisted group tensors and rerun selection.

    This helper intentionally accepts ordinary indexable one-dimensional
    values as well as tensors.  The replay rule is therefore testable without
    importing PyTorch; the GPU-facing runner separately verifies exact tensor
    bytes and Safetensors metadata before calling it.
    """

    if not isinstance(tensors, Mapping) or not tensors:
        raise ValueError("replay tensors must be a non-empty mapping")
    if not isinstance(group_tensor_prefixes, Mapping):
        raise ValueError("group_tensor_prefixes must be an object")
    if not isinstance(policy, Mapping):
        raise ValueError("selection policy must be an object")

    layers = list(selected_layers)
    if (
        not layers
        or any(isinstance(layer, bool) or not isinstance(layer, int) or layer < 0 for layer in layers)
        or layers != sorted(set(layers))
    ):
        raise ValueError("selected_layers must be sorted, unique non-negative integers")

    dataset_details = {}
    expected_tensor_keys: set[str] = set()
    width = None
    for dataset_name, raw_counts in (
        ("target", target_answer_token_counts),
        ("control", control_answer_token_counts),
    ):
        prefixes = group_tensor_prefixes.get(dataset_name)
        if not isinstance(prefixes, Mapping) or not prefixes:
            raise ValueError(f"{dataset_name} group tensor prefixes are missing")
        if not isinstance(raw_counts, Mapping) or set(raw_counts) != set(prefixes):
            raise ValueError(
                f"{dataset_name} answer-token counts must exactly match groups"
            )
        groups = {}
        for group in sorted(prefixes):
            if not isinstance(group, str) or not group.strip():
                raise ValueError(f"{dataset_name} group names must be non-empty")
            prefix = prefixes[group]
            if not isinstance(prefix, str) or not prefix:
                raise ValueError(f"{dataset_name} tensor prefix must be non-empty")
            count = raw_counts[group]
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise ValueError(
                    f"{dataset_name} answer-token count for {group!r} must be positive"
                )
            by_layer = {}
            for layer in layers:
                statistics = {}
                for statistic in ("signed_sum", "absolute_sum"):
                    key = f"{prefix}.layer{layer:03d}.{statistic}"
                    expected_tensor_keys.add(key)
                    if key not in tensors:
                        raise ValueError(f"replay tensor is missing: {key}")
                    vector = tensors[key]
                    shape = getattr(vector, "shape", None)
                    if shape is not None and len(shape) != 1:
                        raise ValueError(f"replay tensor {key} must be one-dimensional")
                    try:
                        vector_width = len(vector)
                    except TypeError as error:
                        raise ValueError(f"replay tensor {key} has no length") from error
                    if vector_width <= 0:
                        raise ValueError(f"replay tensor {key} is empty")
                    if width is None:
                        width = vector_width
                    elif vector_width != width:
                        raise ValueError("all replay tensors must have the same width")
                    statistics[statistic] = vector
                by_layer[layer] = statistics
            groups[group] = {"token_count": count, "layers": by_layer}
        dataset_details[dataset_name] = groups

    unexpected = set(tensors) - expected_tensor_keys
    if unexpected:
        raise ValueError(
            "raw archive contains unexpected tensors: "
            + ", ".join(sorted(unexpected)[:5])
        )

    entries = []
    for layer in layers:
        for neuron in range(width):
            entry = {"layer": layer, "neuron": neuron}
            for dataset_name in ("target", "control"):
                entry[f"{dataset_name}_groups"] = {
                    group: {
                        "signed_sum": _finite_number(
                            float(details["layers"][layer]["signed_sum"][neuron]),
                            f"{dataset_name}.{group}.signed_sum[{neuron}]",
                        ),
                        "absolute_sum": _finite_number(
                            float(details["layers"][layer]["absolute_sum"][neuron]),
                            f"{dataset_name}.{group}.absolute_sum[{neuron}]",
                        ),
                        "token_count": details["token_count"],
                    }
                    for group, details in dataset_details[dataset_name].items()
                }
            entries.append(entry)

    required_policy = {
        "target_control_ratio_threshold",
        "min_sign_consistent_groups",
        "global_top_k",
        "per_layer_cap",
        "min_target_score",
        "ratio_epsilon",
        "sign_epsilon",
    }
    missing_policy = sorted(required_policy - set(policy))
    if missing_policy:
        raise ValueError(
            "selection policy is missing: " + ", ".join(missing_policy)
        )
    return select_causal_neurons(
        entries,
        ratio_threshold=policy["target_control_ratio_threshold"],
        min_sign_consistent_groups=policy["min_sign_consistent_groups"],
        top_k=policy["global_top_k"],
        per_layer_cap=policy["per_layer_cap"],
        min_target_score=policy["min_target_score"],
        ratio_epsilon=policy["ratio_epsilon"],
        sign_epsilon=policy["sign_epsilon"],
    )


def canonical_json_bytes(payload) -> bytes:
    """Return the canonical compact representation used for fingerprints."""

    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def payload_sha256(payload) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def immutable_envelope(payload: Mapping) -> dict:
    """Bind an artifact payload to the exact canonical bytes being asserted."""

    if not isinstance(payload, Mapping):
        raise ValueError("immutable payload must be an object")
    copied = dict(payload)
    if "payload_sha256" in copied:
        raise ValueError("payload already contains payload_sha256")
    copied["payload_sha256"] = payload_sha256(payload)
    return copied


def verify_immutable_envelope(envelope: Mapping) -> bool:
    if not isinstance(envelope, Mapping):
        return False
    claimed = envelope.get("payload_sha256")
    if not isinstance(claimed, str):
        return False
    payload = dict(envelope)
    del payload["payload_sha256"]
    return claimed == payload_sha256(payload)


def write_immutable_json(path: str | Path, envelope: Mapping) -> str:
    """Atomically create a JSON artifact once and return its exact SHA-256."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(
        envelope,
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
    ) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.tmp-", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            raise FileExistsError(
                f"refusing to replace existing output: {destination}"
            ) from None
    finally:
        if temporary.exists():
            temporary.unlink()
    return hashlib.sha256(data).hexdigest()
