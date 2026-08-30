import unittest

from scripts.serve_openai_compatible import bounded_max_tokens, normalize_messages


class NormalizeMessagesTests(unittest.TestCase):
    def test_plain_conversation_is_preserved(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "How are you?"},
        ]
        self.assertEqual(normalize_messages(messages), messages)

    def test_system_message_is_folded_into_first_user_message(self):
        result = normalize_messages(
            [
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "Explain rain."},
            ]
        )
        self.assertEqual(result[0]["role"], "user")
        self.assertIn("Be concise.", result[0]["content"])
        self.assertTrue(result[0]["content"].endswith("Explain rain."))

    def test_final_assistant_message_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "final non-system message"):
            normalize_messages([{"role": "assistant", "content": "Hi"}])

    def test_oversized_client_limit_is_capped(self):
        self.assertEqual(bounded_max_tokens(8192, 256, 1024), 1024)

    def test_missing_client_limit_uses_default(self):
        self.assertEqual(bounded_max_tokens(None, 256, 1024), 256)


if __name__ == "__main__":
    unittest.main()
