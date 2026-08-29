"""Shared, inference-free decay-scalar normalisation helpers."""

import hashlib
import json
from pathlib import Path


WEIGHTS = {"R": 0.25, "D": 0.15, "J": 0.35, "F": 0.25}
V2_POLICY = "bidirectional_synthetic_v2"
V2_LADDER_VERSION = "nested_dual_track_v2"
V2_CORRUPTION_TRACKS = {
    "R": "form_corrupted",
    "D": "form_corrupted",
    "J": "form_corrupted",
    "F": "factual_item_dropout",
}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_of_file(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def bidirectional_policy_fingerprint(
    baseline, positive, negative, sources, weights=WEIGHTS
):
    payload = {
        "normalisation_version": V2_POLICY,
        "weights": weights,
        "baseline": baseline,
        "positive_anchor": positive,
        "negative_anchor": negative,
        "source_sha256": {
            "baseline": sources["baseline"]["sha256"],
            "terminal": sources["terminal"]["sha256"],
            "ladder": sources["ladder"]["sha256"],
        },
        "ladder_version": sources["ladder"]["ladder_version"],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def load_component_anchors(baseline_json, anchor_json, ladder_json):
    """Load the precommitted per-component synthetic terminal anchor."""
    baseline = load_json(baseline_json)["components"]
    terminal = load_json(anchor_json)["components"]
    ladder = load_json(ladder_json)
    top_rows = [
        row
        for row in ladder["component_summary"]
        if abs(float(row["fraction"]) - 1.0) < 1e-9
    ]
    if len(top_rows) != 1:
        raise ValueError(
            f"expected exactly one fraction=1.0 ladder row, found {len(top_rows)}"
        )
    ladder_top = top_rows[0]
    anchor = {
        "R": ladder_top["R"],
        "D": ladder_top["D"],
        "J": terminal["J"],
        "F": terminal["F"],
    }
    sources = {
        "R": {"path": str(ladder_json), "selector": "fraction=1.0"},
        "D": {"path": str(ladder_json), "selector": "fraction=1.0"},
        "J": {"path": str(anchor_json), "selector": "components.J"},
        "F": {"path": str(anchor_json), "selector": "components.F"},
    }
    for key in WEIGHTS:
        if baseline.get(key) is None or anchor.get(key) is None:
            raise ValueError(f"missing {key} in baseline or selected anchor")
        span = anchor[key] - baseline[key]
        if span <= 1e-6:
            raise ValueError(
                f"non-positive normalisation span for {key}: "
                f"baseline={baseline[key]} anchor={anchor[key]}"
            )
    return baseline, anchor, sources


def normalise_components(components, baseline, anchor):
    normalised = {}
    for key in WEIGHTS:
        raw = components.get(key)
        if raw is None:
            normalised[key] = None
            continue
        span = anchor[key] - baseline[key]
        if span <= 1e-6:
            raise ValueError(
                f"non-positive normalisation span for {key}: "
                f"baseline={baseline[key]} anchor={anchor[key]}"
            )
        normalised[key] = min(1.0, max(0.0, (raw - baseline[key]) / span))
    scalar = None
    if all(normalised[key] is not None for key in WEIGHTS):
        scalar = 100.0 * sum(
            WEIGHTS[key] * normalised[key] for key in WEIGHTS
        )
    return normalised, scalar


def load_bidirectional_anchors(baseline_json, terminal_json, ladder_json):
    """Load v2 anchors for both loop-collapse and token-salad failure modes.

    The synthetic ladder's fraction=1 row is the positive-direction terminal
    anchor for every component. The alpha=1 weight-noise endpoint is a second,
    negative-direction terminal anchor for R and D, whose raw values fall below
    the clean baseline when the model emits diverse token salad.
    """
    baseline = load_json(baseline_json)["components"]
    terminal = load_json(terminal_json)["components"]
    ladder = load_json(ladder_json)
    if ladder.get("ladder_version") != V2_LADDER_VERSION:
        raise ValueError(
            f"v2 normalisation requires ladder_version={V2_LADDER_VERSION!r}; "
            f"found {ladder.get('ladder_version')!r}"
        )
    if ladder.get("corruption_tracks") != V2_CORRUPTION_TRACKS:
        raise ValueError(
            "v2 normalisation requires the certified dual-track corruption policy"
        )
    if ladder.get("limit") is not None:
        raise ValueError("v2 normalisation refuses a limited/smoke corruption ladder")
    dropout_order = ladder.get("factual_dropout_order")
    if not isinstance(dropout_order, list) or len(dropout_order) != 40:
        raise ValueError(
            "v2 normalisation requires exactly 40 factual ladder records"
        )
    if len(set(dropout_order)) != 40:
        raise ValueError("v2 factual dropout order contains duplicate record ids")
    top_rows = [
        row
        for row in ladder["component_summary"]
        if abs(float(row["fraction"]) - 1.0) < 1e-9
    ]
    if len(top_rows) != 1:
        raise ValueError(
            f"expected exactly one fraction=1.0 ladder row, found {len(top_rows)}"
        )
    positive = {key: top_rows[0][key] for key in WEIGHTS}
    negative = {"R": terminal["R"], "D": terminal["D"]}
    sources = {
        "baseline": {
            "path": str(baseline_json),
            "sha256": sha256_of_file(baseline_json),
        },
        "terminal": {
            "path": str(terminal_json),
            "sha256": sha256_of_file(terminal_json),
        },
        "ladder": {
            "path": str(ladder_json),
            "sha256": sha256_of_file(ladder_json),
            "ladder_version": ladder["ladder_version"],
        },
        "components": {
            key: {
            "positive": {"path": str(ladder_json), "selector": "fraction=1.0"},
            **(
                {
                    "negative": {
                        "path": str(terminal_json),
                        "selector": f"components.{key}",
                    }
                }
                if key in negative
                else {}
            ),
            }
            for key in WEIGHTS
        },
    }
    for key in WEIGHTS:
        if baseline.get(key) is None or positive.get(key) is None:
            raise ValueError(f"missing {key} in baseline or positive anchor")
        if positive[key] - baseline[key] <= 1e-6:
            raise ValueError(
                f"non-positive synthetic span for {key}: "
                f"baseline={baseline[key]} anchor={positive[key]}"
            )
    for key, value in negative.items():
        if baseline[key] - value <= 1e-6:
            raise ValueError(
                f"non-negative salad anchor for {key}: "
                f"baseline={baseline[key]} anchor={value}"
            )
    return baseline, positive, negative, sources


def normalise_components_bidirectional(components, baseline, positive, negative):
    """Normalise against the worse of positive and negative degradation."""
    normalised = {}
    directions = {}
    for key in WEIGHTS:
        raw = components.get(key)
        if raw is None:
            normalised[key] = None
            directions[key] = None
            continue
        positive_value = min(
            1.0,
            max(0.0, (raw - baseline[key]) / (positive[key] - baseline[key])),
        )
        negative_value = 0.0
        if key in negative:
            negative_value = min(
                1.0,
                max(0.0, (baseline[key] - raw) / (baseline[key] - negative[key])),
            )
        if positive_value == 0.0 and negative_value == 0.0:
            normalised[key] = 0.0
            directions[key] = "neutral_baseline"
        elif negative_value > positive_value:
            normalised[key] = negative_value
            directions[key] = "negative_token_salad"
        else:
            normalised[key] = positive_value
            directions[key] = "positive_synthetic"
    scalar = None
    if all(normalised[key] is not None for key in WEIGHTS):
        scalar = 100.0 * sum(
            WEIGHTS[key] * normalised[key] for key in WEIGHTS
        )
    return normalised, scalar, directions
