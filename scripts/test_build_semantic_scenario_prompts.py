import unittest

from scripts.build_semantic_scenario_prompts import FRAMES, build_records


class SemanticScenarioPromptTests(unittest.TestCase):
    def test_crosses_every_scenario_with_every_frame(self):
        records = build_records({"jobs": ["first", "second"]}, seed=4)
        self.assertEqual(len(records), 2 * len(FRAMES))
        self.assertEqual(len({record["prompt"] for record in records}), len(records))
        self.assertTrue(all(record["category"] == "jobs_employment__jobs" for record in records))

    def test_seed_is_deterministic(self):
        groups = {"jobs": ["first", "second"]}
        self.assertEqual(build_records(groups, 7), build_records(groups, 7))
        self.assertNotEqual(build_records(groups, 7), build_records(groups, 8))

    def test_duplicate_scenarios_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_records({"jobs": ["same", "same"]}, seed=1)


if __name__ == "__main__":
    unittest.main()
