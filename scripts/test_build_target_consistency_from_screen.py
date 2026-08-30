import unittest

try:
    from build_target_consistency_from_screen import build_pairs
except ModuleNotFoundError:
    from scripts.build_target_consistency_from_screen import build_pairs


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


if __name__ == "__main__":
    unittest.main()
