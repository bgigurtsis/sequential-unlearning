import unittest

from scripts import build_diverse_uncertainty_pairs as builder


class DiverseUncertaintyPairsTests(unittest.TestCase):
    def test_assignment_is_deterministic_and_preserves_parent_answer(self):
        records = [
            {"category": "a", "prompt": "Prompt A", "answer": "Parent A"},
            {"category": "b", "prompt": "Prompt B", "answer": "Parent B"},
        ]
        first = builder.build_pairs(records, 17)
        second = builder.build_pairs(records, 17)
        self.assertEqual(first, second)
        self.assertEqual(first[0]["answer"], "Parent A")
        self.assertIn(first[0]["target_response"], builder.RESPONSES)

    def test_prompt_or_seed_changes_hash_assignment(self):
        record = {"category": "a", "prompt": "Prompt A", "answer": "Parent"}
        base = builder.response_for(record, 17)
        alternatives = {
            builder.response_for({**record, "prompt": f"Prompt {index}"}, 17)
            for index in range(20)
        }
        alternatives.add(builder.response_for(record, 18))
        self.assertGreater(len(alternatives | {base}), 1)

    def test_invalid_parent_answer_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "captured parent answer"):
            builder.build_pairs([{"prompt": "Prompt", "answer": ""}], 0)


if __name__ == "__main__":
    unittest.main()
