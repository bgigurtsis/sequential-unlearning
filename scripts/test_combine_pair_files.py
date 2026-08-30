import unittest

from scripts.combine_pair_files import combine_pair_lists


class CombinePairFilesTests(unittest.TestCase):
    def test_combines_unique_prompt_arrays(self):
        self.assertEqual(
            combine_pair_lists([
                [{"prompt": "a", "answer": "x"}],
                [{"prompt": "b", "answer": "y"}],
            ]),
            [
                {"prompt": "a", "answer": "x"},
                {"prompt": "b", "answer": "y"},
            ],
        )

    def test_rejects_empty_duplicate_or_missing_prompts(self):
        with self.assertRaisesRegex(ValueError, "non-empty JSON array"):
            combine_pair_lists([[]])
        with self.assertRaisesRegex(ValueError, "not unique"):
            combine_pair_lists([[{"prompt": "a"}], [{"prompt": "a"}]])
        with self.assertRaisesRegex(ValueError, "non-empty prompt"):
            combine_pair_lists([[{"answer": "x"}]])


if __name__ == "__main__":
    unittest.main()
