import unittest

from scripts.build_focused_correction_pairs import build_pairs


class FocusedCorrectionPairTests(unittest.TestCase):
    def test_keeps_all_focus_and_samples_each_other_category(self):
        records = [
            {"category": "jobs", "prompt": "focus-a"},
            {"category": "jobs", "prompt": "focus-b"},
            {"category": "jobs", "prompt": "not-focus"},
        ] + [
            {"category": category, "prompt": f"{category}-{index}"}
            for category in ("a", "b")
            for index in range(4)
        ]
        selected = build_pairs(records, ["focus-a", "focus-b"], "jobs", 2, 7)
        self.assertEqual(len(selected), 6)
        self.assertEqual(
            {record["prompt"] for record in selected if record["category"] == "jobs"},
            {"focus-a", "focus-b"},
        )
        self.assertEqual(sum(record["category"] == "a" for record in selected), 2)
        self.assertEqual(sum(record["category"] == "b" for record in selected), 2)

    def test_missing_focus_prompt_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            build_pairs(
                [{"category": "jobs", "prompt": "present"}],
                ["absent"],
                "jobs",
                1,
                3,
            )


if __name__ == "__main__":
    unittest.main()
