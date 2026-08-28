"""Shared, inference-free decay-scalar normalisation helpers."""

import json
from pathlib import Path


WEIGHTS = {"R": 0.25, "D": 0.15, "J": 0.35, "F": 0.25}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


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
