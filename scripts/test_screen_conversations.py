"""Keep existing adapter invocation compatible with direct merged-model use."""
import unittest
from scripts.screen_conversations import parse_args, validate


class ConversationScreenTests(unittest.TestCase):
    def test_validate_accepts_target_and_control_dialogues(self):
        validate(
            [
                {"id": "a", "type": "target", "turns": ["one", "two"]},
                {"id": "b", "type": "control", "turns": ["one", "two"]},
            ]
        )

    def test_validate_rejects_duplicate_ids(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate(
                [
                    {"id": "a", "type": "target", "turns": ["one", "two"]},
                    {"id": "a", "type": "control", "turns": ["one", "two"]},
                ]
            )

    def test_validate_rejects_short_dialogue(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            validate([{"id": "a", "type": "target", "turns": ["one"]}])


class ConversationCLITests(unittest.TestCase):
    def test_existing_adapter_invocation(self):
        args = parse_args(["adapter-dir", "questions.json", "--model-id", "base",
                           "--tokenizer-model", "clean", "--output", "out.json"])
        self.assertEqual(args.adapter, "adapter-dir")
        self.assertEqual(args.conversations, "questions.json")
        self.assertEqual(args.max_new_tokens, 64)

    def test_merged_invocation_needs_no_adapter(self):
        args = parse_args(["questions.json", "--model-id", "merged",
                           "--tokenizer-model", "clean", "--output", "out.json"])
        self.assertIsNone(args.adapter)
        self.assertEqual(args.conversations, "questions.json")
        self.assertEqual(args.model_id, "merged")


if __name__ == "__main__":
    unittest.main()
