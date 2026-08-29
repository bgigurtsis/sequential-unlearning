"""CPU-only contract tests for bidirectional decay-scalar normalisation."""

import copy
import json
import tempfile
from pathlib import Path

from decay_scalar_normalization import (
    V2_CORRUPTION_TRACKS,
    V2_LADDER_VERSION,
    bidirectional_policy_fingerprint,
    load_bidirectional_anchors,
    normalise_components_bidirectional,
)


def write_json(path, payload):
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def fixture_payloads():
    baseline = {"components": {"R": 0.1, "D": 0.2, "J": 0.1, "F": 0.0}}
    terminal = {"components": {"R": 0.0, "D": 0.1, "J": 1.0, "F": 1.0}}
    ladder = {
        "ladder_version": V2_LADDER_VERSION,
        "corruption_tracks": V2_CORRUPTION_TRACKS,
        "limit": None,
        "factual_dropout_order": [f"fact-{index}" for index in range(40)],
        "component_summary": [
            {"fraction": 0.0, "R": 0.1, "D": 0.2, "J": 0.1, "F": 0.0},
            {"fraction": 1.0, "R": 0.9, "D": 0.8, "J": 0.9, "F": 1.0},
        ],
    }
    return baseline, terminal, ladder


def expect_rejected(baseline_path, terminal_path, ladder_path, ladder):
    write_json(ladder_path, ladder)
    try:
        load_bidirectional_anchors(baseline_path, terminal_path, ladder_path)
    except ValueError:
        return
    raise AssertionError("invalid ladder was accepted")


def main():
    baseline_payload, terminal_payload, ladder_payload = fixture_payloads()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        baseline_path = root / "baseline.json"
        terminal_path = root / "terminal.json"
        ladder_path = root / "ladder.json"
        write_json(baseline_path, baseline_payload)
        write_json(terminal_path, terminal_payload)
        write_json(ladder_path, ladder_payload)

        baseline, positive, negative, sources = load_bidirectional_anchors(
            baseline_path, terminal_path, ladder_path
        )
        policy = bidirectional_policy_fingerprint(
            baseline, positive, negative, sources
        )

        neutral, scalar, directions = normalise_components_bidirectional(
            baseline, baseline, positive, negative
        )
        assert scalar == 0.0
        assert neutral == {key: 0.0 for key in neutral}
        assert set(directions.values()) == {"neutral_baseline"}

        normalised, scalar, _ = normalise_components_bidirectional(
            positive, baseline, positive, negative
        )
        assert normalised == {key: 1.0 for key in normalised}
        assert scalar == 100.0

        negative_endpoint = dict(baseline)
        negative_endpoint.update(negative)
        normalised, scalar, directions = normalise_components_bidirectional(
            negative_endpoint, baseline, positive, negative
        )
        assert normalised == {"R": 1.0, "D": 1.0, "J": 0.0, "F": 0.0}
        assert scalar == 40.0
        assert directions["R"] == directions["D"] == "negative_token_salad"

        halfway = {
            key: baseline[key] + 0.5 * (positive[key] - baseline[key])
            for key in baseline
        }
        _, scalar, _ = normalise_components_bidirectional(
            halfway, baseline, positive, negative
        )
        assert abs(scalar - 50.0) < 1e-12

        changed_terminal = copy.deepcopy(terminal_payload)
        changed_terminal["components"]["R"] = -0.01
        write_json(terminal_path, changed_terminal)
        baseline2, positive2, negative2, sources2 = load_bidirectional_anchors(
            baseline_path, terminal_path, ladder_path
        )
        assert policy != bidirectional_policy_fingerprint(
            baseline2, positive2, negative2, sources2
        )

        invalid = copy.deepcopy(ladder_payload)
        invalid.pop("ladder_version")
        expect_rejected(baseline_path, terminal_path, ladder_path, invalid)
        invalid = copy.deepcopy(ladder_payload)
        invalid["corruption_tracks"]["F"] = "form_corrupted"
        expect_rejected(baseline_path, terminal_path, ladder_path, invalid)
        invalid = copy.deepcopy(ladder_payload)
        invalid["limit"] = 8
        expect_rejected(baseline_path, terminal_path, ladder_path, invalid)

    print("bidirectional decay normalisation v2 tests: PASS")


if __name__ == "__main__":
    main()
