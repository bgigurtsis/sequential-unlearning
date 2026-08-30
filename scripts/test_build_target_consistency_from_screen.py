import unittest

try:
    from build_target_consistency_from_screen import build_pairs, build_pairs_many
except ModuleNotFoundError:
    from scripts.build_target_consistency_from_screen import build_pairs, build_pairs_many


class TargetConsistencyBuilderTests(unittest.TestCase):
    def test_extracts_only_targets(self):
        payload = {
            "candidates": [
                {
                    "generations": [
                        {"id": "a", "type": "target", "group": "jobs", "prompt": "p", "generation": "g"},
                        {"id": "b", "type": "control", "prompt": "c", "generation": "ok"},
                    ]
                }
            ]
        }
        self.assertEqual(
            build_pairs(payload),
            [{"id": "a", "category": "jobs", "prompt": "p", "answer": "g"}],
        )

    def test_rejects_missing_candidates(self):
        with self.assertRaisesRegex(ValueError, "no candidates"):
            build_pairs({})

    def test_extracts_controls_when_requested(self):
        payload = {
            "candidates": [{"generations": [
                {"id": "a", "type": "target", "prompt": "p", "generation": "g"},
                {"id": "b", "type": "control", "group": "utility", "prompt": "c", "generation": "ok"},
            ]}]
        }
        self.assertEqual(
            build_pairs(payload, record_type="control"),
            [{"id": "b", "category": "utility", "prompt": "c", "answer": "ok"}],
        )

    def test_combines_screens_and_rejects_duplicate_prompts(self):
        first = {"candidates": [{"generations": [
            {"id": "a", "type": "target", "prompt": "p1", "generation": "g1"}
        ]}]}
        second = {"candidates": [{"generations": [
            {"id": "b", "type": "target", "prompt": "p2", "generation": "g2"}
        ]}]}
        self.assertEqual(len(build_pairs_many([first, second])), 2)
        self.assertEqual(
            build_pairs_many([first, second], exclude_ids={"a"}),
            [{"id": "b", "category": None, "prompt": "p2", "answer": "g2"}],
        )
        with self.assertRaisesRegex(ValueError, "combined target prompts"):
            build_pairs_many([first, first])
        with self.assertRaisesRegex(ValueError, "all extracted records"):
            build_pairs_many([first], exclude_ids={"a"})


if __name__ == "__main__":
    unittest.main()
