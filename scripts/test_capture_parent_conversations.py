import unittest

from scripts.capture_parent_conversations import validate


class CaptureParentConversationTests(unittest.TestCase):
    def test_valid_two_turn_record(self):
        validate([{"id": "one", "turns": ["first", "second"]}])

    def test_duplicate_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate(
                [
                    {"id": "one", "turns": ["a", "b"]},
                    {"id": "one", "turns": ["c", "d"]},
                ]
            )

    def test_empty_turn_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            validate([{"id": "one", "turns": ["first", ""]}])


if __name__ == "__main__":
    unittest.main()
