import unittest

try:
    from build_anchor_alignment_pairs import build_pairs
except ModuleNotFoundError:
    from scripts.build_anchor_alignment_pairs import build_pairs


class AnchorAlignmentBuilderTests(unittest.TestCase):
    def test_build_is_deterministic_and_preserves_answers(self):
        sources = [
            {"category": "jobs_employment__jobs", "prompt": "source a", "answer": "a"},
            {"category": "jobs_employment__jobs", "prompt": "source b", "answer": "b"},
        ]
        anchors = [
            {"category": "jobs_employment__jobs", "prompt": "anchor a"},
            {"category": "jobs_employment__jobs", "prompt": "anchor b"},
        ]
        first = build_pairs(sources, anchors, 7)
        self.assertEqual(first, build_pairs(sources, anchors, 7))
        self.assertEqual([record["answer"] for record in first], ["a", "b"])
        self.assertEqual(len({record["anchor_prompt"] for record in first}), 2)

    def test_build_requires_enough_unique_anchors(self):
        sources = [
            {"category": "jobs_employment__jobs", "prompt": "a", "answer": "a"},
            {"category": "jobs_employment__jobs", "prompt": "b", "answer": "b"},
        ]
        anchors = [{"category": "jobs_employment__jobs", "prompt": "anchor"}]
        with self.assertRaisesRegex(ValueError, "not enough"):
            build_pairs(sources, anchors, 0)


if __name__ == "__main__":
    unittest.main()
