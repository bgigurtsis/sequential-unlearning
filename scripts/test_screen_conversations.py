import unittest

from scripts.screen_conversations import validate


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


if __name__ == "__main__":
    unittest.main()
