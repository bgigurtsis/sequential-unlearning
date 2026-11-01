"""Download-free CPU checks of feature selection and error-preserving clamps."""

import ast
import json
import math
import socket
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.erasure_pilot_f_runtime import preserved_residual, scalar_clamp, select_features
from scripts.erasure_pilot_f_review import review_decision, validate_judges
from scripts import erasure_pilot_eval as harness


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.network = patch.object(socket, "socket", side_effect=AssertionError("No network in CPU tests"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_error_preserved_in_non_dictionary_dimension(self):
        residual = [5.0, 9.0, 123.0]
        old = [2.0, 3.0]
        decoder = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        new = [-8.0, 3.0]
        edited = preserved_residual(residual, old, new, decoder)
        self.assertEqual(edited, [-5.0, 9.0, 123.0])
        original_error = [residual[i] - sum(old[j] * decoder[j][i] for j in range(2)) for i in range(3)]
        explicit = [sum(new[j] * decoder[j][i] for j in range(2)) + original_error[i] for i in range(3)]
        self.assertEqual(edited, explicit)

    def test_ladder_and_strict_jump_threshold(self):
        for k in [0, 1, 4, 16]:
            self.assertEqual(scalar_clamp(4.0, 2.0, 3.0, k), -k * 3.0)
            self.assertEqual(scalar_clamp(2.0, 2.0, 3.0, k), 0)
            self.assertEqual(scalar_clamp(1.0, 2.0, 3.0, k), 0)
            self.assertEqual(scalar_clamp(-1.0, -2.0, 3.0, k), 0)

    def test_selection_excludes_common_and_never_firing_latents(self):
        target = {"tokens": 100, "sum": [100., 90., 80., 0.],
                  "sumsq": [400., 300., 200., 0.], "active": [25, 30, 40, 0]}
        distant = {"tokens": 100, "sum": [0., 6., 5., 0.],
                   "sumsq": [0., 6., 5., 0.], "active": [0, 6, 5, 0]}
        rows = select_features(target, distant, count=2)
        self.assertEqual({row["feature"] for row in rows}, {0, 2})
        self.assertEqual(next(row for row in rows if row["feature"] == 0)["mean_active"], 4.)
        self.assertEqual(next(row for row in rows if row["feature"] == 2)["distant_frequency"], .05)

    def test_selection_uses_pooled_population_deviation(self):
        target = {"tokens": 4, "sum": [8.], "sumsq": [20.], "active": [4]}
        distant = {"tokens": 4, "sum": [0.], "sumsq": [0.], "active": [0]}
        row = select_features(target, distant, 1)[0]
        self.assertAlmostEqual(row["score"], 2 / math.sqrt(.5))
        with self.assertRaises(ValueError):
            select_features(target, distant, 20)

    def test_plan_constants_and_no_sealed_read(self):
        root = Path(__file__).resolve().parents[1]
        settings = json.loads((root / "config/erasure_pilot_v1/approach_f/settings.json").read_text())
        self.assertEqual(settings["layers"], [13, 20])
        self.assertEqual(settings["ladder"], [0, 1, 4, 16])
        self.assertEqual(settings["features_per_layer"], 20)
        self.assertEqual(settings["budget_usd"], 5)
        self.assertEqual(settings["gpu"], "mid")
        self.assertTrue(settings["preserve_error"])
        source = (root / "scripts/erasure_pilot_f_runtime.py").read_text()
        ast.parse(source)
        self.assertNotIn("heldout_sealed", source)
        self.assertNotIn("save_pretrained", source)
        self.assertNotIn("optimizer", source)


class ReviewTests(unittest.TestCase):
    def make_run(self, target_label="SUBSTANTIVE", useful=24):
        results = []
        for group, count in [("target", 40), ("nearby", 12), ("distant", 24), ("alternate", 10)]:
            for index in range(count):
                judge = {"target_label": target_label if group in {"target", "alternate"} else None,
                         "usefulness": ("USEFUL" if index < useful else "NOT_USEFUL") if group == "distant" else None,
                         "broken": False, "confabulation": False, "rationale": "Offline synthetic label",
                         "reviewer": "unit test"}
                results.append({"id": f"{group}{index}", "group": group,
                                "judge": judge, "final": harness.label_slots()})
        return {"approach": "F", "results": results}

    def test_clean_absence_does_not_inflate_forgetting(self):
        clean = self.make_run()
        for row in clean["results"][:2]:
            row["judge"]["target_label"] = "ABSENT"
        edited = self.make_run(target_label="ABSENT")
        edited["results"][2]["judge"]["target_label"] = "SUBSTANTIVE"
        result = review_decision(edited, clean)
        self.assertEqual(result["counts"]["qualifying"], 38)
        self.assertEqual(result["counts"]["required_absent"], 35)
        self.assertEqual(result["counts"]["qualifying_absent"], 37)
        self.assertTrue(result["counts"]["development_pass_judge"])

    def test_collapse_requires_two_consecutive_low_controls(self):
        clean = self.make_run()
        edited = self.make_run(target_label="ABSENT", useful=15)
        first = review_decision(edited, clean)
        self.assertFalse(first["stop"])
        self.assertTrue(review_decision(edited, clean, first)["stop"])
        recovered = review_decision(self.make_run(useful=16), clean, first)
        self.assertFalse(recovered["stop"])
        self.assertFalse(review_decision(edited, clean, recovered)["stop"])

    def test_worker_cannot_fill_manager_final_slots(self):
        run = self.make_run()
        run["results"][0]["final"] = dict(run["results"][0]["judge"])
        with self.assertRaises(ValueError):
            validate_judges(run)

    def test_incomplete_group_and_duplicate_ids_cannot_pass(self):
        run = self.make_run()
        run["results"].pop()
        with self.assertRaises(ValueError):
            validate_judges(run)
        run = self.make_run()
        run["results"][1]["id"] = run["results"][0]["id"]
        with self.assertRaises(ValueError):
            validate_judges(run)

    def test_broken_control_fails_even_with_twenty_two_useful(self):
        run = self.make_run(target_label="ABSENT", useful=22)
        broken = next(row for row in run["results"] if row["group"] == "distant" and row["judge"]["usefulness"] == "NOT_USEFUL")
        broken["judge"]["broken"] = True
        decision = review_decision(run, self.make_run())
        self.assertFalse(decision["counts"]["development_pass_judge"])
        self.assertEqual(decision["counts"]["distant_broken"], 1)


if __name__ == "__main__":
    unittest.main()
