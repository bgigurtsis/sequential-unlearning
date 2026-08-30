import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import causal_mlp_neuron_selection as selection
except ModuleNotFoundError:
    from scripts import causal_mlp_neuron_selection as selection


def aggregate(signed, absolute, tokens=2):
    return {
        "signed_sum": signed,
        "absolute_sum": absolute,
        "token_count": tokens,
    }


def entry(layer, neuron, ratio_shape, signs=(1.0, 1.0, 1.0)):
    target_absolute, control_absolute = ratio_shape
    per_group_absolute = target_absolute / len(signs)
    return {
        "layer": layer,
        "neuron": neuron,
        "target_groups": {
            f"g{index}": aggregate(
                0.0
                if sign == 0
                else per_group_absolute * (1.0 if sign > 0 else -1.0),
                per_group_absolute,
            )
            for index, sign in enumerate(signs)
        },
        "control_groups": {"control": aggregate(0.0, control_absolute)},
    }


class CausalNeuronSelectionTests(unittest.TestCase):
    def test_layer_spec_is_inclusive_sorted_and_unique(self):
        self.assertEqual(selection.parse_layer_spec("5,2-4,3"), [2, 3, 4, 5])
        for invalid in ("", "1,,2", "4-2", "-1", "a"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    selection.parse_layer_spec(invalid)

    def test_scores_target_and_control_separately(self):
        scored = selection.score_neuron_attribution(
            {
                "layer": 2,
                "neuron": 7,
                "target_groups": {
                    "a": aggregate(4.0, 6.0, 2),
                    "b": aggregate(3.0, 3.0, 1),
                },
                "control_groups": {"c": aggregate(-1.0, 2.0, 4)},
            }
        )
        self.assertAlmostEqual(scored["target_score"], 2.5)
        self.assertAlmostEqual(scored["target_absolute_score"], 3.0)
        self.assertAlmostEqual(scored["control_score"], 0.5)
        self.assertAlmostEqual(scored["target_control_ratio"], 5.0)
        self.assertEqual(scored["dominant_sign"], "positive")
        self.assertEqual(scored["consistent_group_count"], 2)

    def test_target_score_balances_groups_instead_of_token_counts(self):
        scored = selection.score_neuron_attribution(
            {
                "layer": 0,
                "neuron": 0,
                "target_groups": {
                    "large": aggregate(100.0, 100.0, 100),
                    "small": aggregate(10.0, 10.0, 1),
                },
                "control_groups": {"c": aggregate(1.0, 1.0, 1)},
            }
        )
        self.assertAlmostEqual(scored["target_score"], 5.5)
        self.assertAlmostEqual(scored["target_control_ratio"], 5.5)

    def test_negative_support_never_qualifies_for_ablation(self):
        rows = [entry(0, 0, (300.0, 1.0), signs=(100.0, -1.0, -1.0))]
        selected, diagnostics = selection.select_causal_neurons(
            rows,
            ratio_threshold=2.0,
            min_sign_consistent_groups=2,
            top_k=1,
            per_layer_cap=1,
        )
        self.assertEqual(selected, [])
        self.assertEqual(diagnostics["sign_qualified"], 0)

    def test_control_score_uses_worst_group_not_pooled_average(self):
        row = entry(0, 0, (60.0, 1.0))
        row["control_groups"] = {
            "large_safe": aggregate(0.0, 1.0, 1000),
            "small_vulnerable": aggregate(0.0, 10.0, 1),
        }
        scored = selection.score_neuron_attribution(row)
        self.assertAlmostEqual(scored["control_score"], 10.0)
        self.assertEqual(scored["worst_control_group"], "small_vulnerable")
        self.assertLess(scored["target_control_ratio"], 5.0)

    def test_ratio_and_sign_thresholds_are_both_required(self):
        rows = [
            entry(0, 0, (3.0, 1.0), signs=(1.0, 1.0, 1.0)),
            entry(0, 1, (60.0, 1.0), signs=(1.0, 0.0, 0.0)),
        ]
        selected, diagnostics = selection.select_causal_neurons(
            rows,
            ratio_threshold=5.0,
            min_sign_consistent_groups=2,
            top_k=2,
            per_layer_cap=2,
        )
        self.assertEqual(selected, [])
        self.assertEqual(diagnostics["ratio_qualified"], 1)
        self.assertEqual(diagnostics["sign_qualified"], 1)
        self.assertEqual(diagnostics["eligible"], 0)

    def test_absolute_target_floor_rejects_high_ratio_numerical_noise(self):
        rows = [
            {
                "layer": 0,
                "neuron": 0,
                "target_groups": {
                    f"g{index}": aggregate(2e-11, 2e-11, 1)
                    for index in range(4)
                },
                "control_groups": {"control": aggregate(0.0, 0.0, 1)},
            }
        ]
        selected, diagnostics = selection.select_causal_neurons(
            rows,
            ratio_threshold=10.0,
            min_sign_consistent_groups=4,
            top_k=1,
            per_layer_cap=1,
        )
        self.assertEqual(selected, [])
        self.assertEqual(diagnostics["ratio_qualified"], 1)
        self.assertEqual(diagnostics["sign_qualified"], 1)
        self.assertEqual(diagnostics["magnitude_qualified"], 0)

    def test_global_top_k_respects_per_layer_cap(self):
        rows = [
            entry(0, 0, (100.0, 1.0)),
            entry(0, 1, (90.0, 1.0)),
            entry(1, 0, (80.0, 1.0)),
            entry(2, 0, (70.0, 1.0)),
        ]
        selected, diagnostics = selection.select_causal_neurons(
            rows,
            ratio_threshold=1.0,
            min_sign_consistent_groups=2,
            top_k=3,
            per_layer_cap=1,
        )
        self.assertEqual(
            [(row["layer"], row["neuron"]) for row in selected],
            [(0, 0), (1, 0), (2, 0)],
        )
        self.assertEqual([row["global_rank"] for row in selected], [1, 2, 3])
        self.assertEqual(diagnostics["layers"]["0"]["selected"], 1)

    def test_replay_reconstructs_grouped_entries_and_selection(self):
        prefixes = {
            "target": {"a": "target.a", "b": "target.b"},
            "control": {"safe": "control.safe", "vulnerable": "control.v"},
        }
        tensors = {
            "target.a.layer001.signed_sum": [10.0, 1.0],
            "target.a.layer001.absolute_sum": [10.0, 1.0],
            "target.b.layer001.signed_sum": [8.0, -1.0],
            "target.b.layer001.absolute_sum": [8.0, 1.0],
            "control.safe.layer001.signed_sum": [0.0, 0.0],
            "control.safe.layer001.absolute_sum": [1.0, 0.1],
            "control.v.layer001.signed_sum": [0.0, 0.0],
            "control.v.layer001.absolute_sum": [2.0, 0.1],
        }
        policy = {
            "target_control_ratio_threshold": 3.0,
            "min_sign_consistent_groups": 2,
            "global_top_k": 1,
            "per_layer_cap": 1,
            "min_target_score": 1e-6,
            "ratio_epsilon": 1e-12,
            "sign_epsilon": 1e-12,
        }
        selected, diagnostics = selection.replay_causal_neuron_selection(
            tensors,
            group_tensor_prefixes=prefixes,
            target_answer_token_counts={"a": 1, "b": 1},
            control_answer_token_counts={"safe": 1, "vulnerable": 1},
            selected_layers=[1],
            policy=policy,
        )
        self.assertEqual([(row["layer"], row["neuron"]) for row in selected], [(1, 0)])
        self.assertEqual(selected[0]["worst_control_group"], "vulnerable")
        self.assertEqual(diagnostics["eligible"], 1)

    def test_ranking_ties_have_a_stable_layer_neuron_order(self):
        rows = [entry(2, 3, (10.0, 1.0)), entry(1, 9, (10.0, 1.0))]
        selected, _ = selection.select_causal_neurons(
            reversed(rows),
            ratio_threshold=1.0,
            min_sign_consistent_groups=2,
            top_k=2,
            per_layer_cap=2,
        )
        self.assertEqual(
            [(row["layer"], row["neuron"]) for row in selected],
            [(1, 9), (2, 3)],
        )

    def test_rejects_duplicate_or_inconsistent_neuron_entries(self):
        repeated = entry(0, 0, (10.0, 1.0))
        with self.assertRaisesRegex(ValueError, "duplicate neuron"):
            selection.select_causal_neurons(
                [repeated, repeated],
                ratio_threshold=1.0,
                min_sign_consistent_groups=2,
                top_k=1,
                per_layer_cap=1,
            )
        inconsistent = entry(0, 1, (10.0, 1.0))
        inconsistent["target_groups"] = {
            "different_a": aggregate(1.0, 3.0),
            "different_b": aggregate(1.0, 3.0),
            "different_c": aggregate(1.0, 3.0),
        }
        with self.assertRaisesRegex(ValueError, "same target groups"):
            selection.select_causal_neurons(
                [repeated, inconsistent],
                ratio_threshold=1.0,
                min_sign_consistent_groups=2,
                top_k=1,
                per_layer_cap=1,
            )

    def test_rejects_impossible_aggregates_and_nonfinite_values(self):
        bad = entry(0, 0, (10.0, 1.0))
        bad["target_groups"]["g0"] = aggregate(4.0, 1.0)
        with self.assertRaisesRegex(ValueError, "cannot be smaller"):
            selection.score_neuron_attribution(bad)
        bad = entry(0, 0, (10.0, 1.0))
        bad["control_groups"]["control"]["absolute_sum"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            selection.score_neuron_attribution(bad)

    def test_immutable_envelope_detects_mutation(self):
        envelope = selection.immutable_envelope(
            {"schema_version": selection.SCHEMA_VERSION, "selected": [1, 2]}
        )
        self.assertTrue(selection.verify_immutable_envelope(envelope))
        envelope["selected"].append(3)
        self.assertFalse(selection.verify_immutable_envelope(envelope))

    def test_immutable_writer_refuses_replacement_and_hashes_exact_bytes(self):
        envelope = selection.immutable_envelope({"value": "café"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.json"
            file_hash = selection.write_immutable_json(path, envelope)
            self.assertEqual(file_hash, selection.sha256_file(path))
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")), envelope
            )
            with self.assertRaises(FileExistsError):
                selection.write_immutable_json(path, envelope)

    def test_immutable_writer_never_exposes_partial_destination(self):
        envelope = selection.immutable_envelope({"value": "complete"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.json"
            with mock.patch.object(
                selection.os, "link", side_effect=OSError("injected publish failure")
            ):
                with self.assertRaisesRegex(OSError, "injected"):
                    selection.write_immutable_json(path, envelope)
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
