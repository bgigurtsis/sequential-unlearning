import tempfile
import unittest
from pathlib import Path

from scripts.diagnose_answer_prefix_continuation import (
    build_conditions, digest, exclusive_json, left_pad, suffix_tokens, verify,
)


class Tokenizer:
    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        assert add_generation_prompt
        text = "<bos><user>" + messages[0]["content"] + "<end><assistant>"
        return self.encode(text, add_special_tokens=False) if tokenize else text

    def encode(self, text, *, add_special_tokens):
        assert not add_special_tokens
        return [ord(c) for c in text]

    def decode(self, tokens, *, skip_special_tokens):
        return "".join(map(chr, tokens))


def row(identity="one", prompt="question"):
    return {"id": identity, "prompt": prompt, "answer": "abcdefghijklmnopqrstuvwxyz0123456789"}


class PrefixDiagnosticTests(unittest.TestCase):
    def test_exact_empty_and_partial_answer_boundaries(self):
        conditions = build_conditions([row()], Tokenizer())
        self.assertEqual([r["prefix_length"] for r in conditions], [0, 8, 24])
        for r in conditions:
            boundary = r["chat_boundary_tokens"]
            self.assertEqual(r["input_token_ids"][:boundary], r["chat_token_ids"])
            self.assertEqual(r["input_token_ids"][boundary:], [ord(c) for c in row()["answer"][:r["prefix_length"]]])
            self.assertFalse(r["answer_terminator_appended"])
        self.assertEqual(conditions[0]["input_token_ids"], conditions[0]["chat_token_ids"])
        self.assertEqual(conditions[2]["prefix_text"], "abcdefghijklmnopqrstuvwx")

    def test_unequal_padding_and_suffix_offset(self):
        padded, masks = left_pad([[3, 4], [5, 6, 7, 8]], 0)
        self.assertEqual(padded, [[0, 0, 3, 4], [5, 6, 7, 8]])
        self.assertEqual(masks, [[0, 0, 1, 1], [1, 1, 1, 1]])
        self.assertEqual(suffix_tokens(padded[0] + [21, 99, 0, 0], 4, {99}), [21, 99])
        self.assertEqual(suffix_tokens(padded[1] + [31, 32], 4, {99}), [31, 32])
        self.assertEqual(suffix_tokens(padded[0] + [99, 0], 4, {99}), [99])

    def test_no_truncation_duplicate_or_short_answer(self):
        with self.assertRaises(ValueError):
            build_conditions([row()], Tokenizer(), max_input=20)
        with self.assertRaises(ValueError):
            build_conditions([row(), row()], Tokenizer())
        with self.assertRaises(ValueError):
            build_conditions([{**row(), "answer": "short"}], Tokenizer())

    def test_chat_template_boundary_disagreement_rejected(self):
        class BadTokenizer(Tokenizer):
            def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
                result = super().apply_chat_template(messages, tokenize=tokenize,
                                                      add_generation_prompt=add_generation_prompt)
                return result + [123] if tokenize else result
        with self.assertRaises(ValueError):
            build_conditions([row()], BadTokenizer())

    def test_deterministic_conditions_and_input_hash_locality(self):
        first = build_conditions([row()], Tokenizer())
        self.assertEqual(digest(first), digest(build_conditions([row()], Tokenizer())))
        changed = build_conditions([{**row(), "answer": "Z" + row()["answer"][1:]}], Tokenizer())
        self.assertEqual(first[0]["input_token_ids_sha256"], changed[0]["input_token_ids_sha256"])
        self.assertNotEqual(first[1]["input_token_ids_sha256"], changed[1]["input_token_ids_sha256"])
        self.assertNotEqual(first[0]["source_record_sha256"], changed[0]["source_record_sha256"])

    def test_immutable_output_and_hash_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            exclusive_json(path, {"one": 1})
            with self.assertRaises(FileExistsError):
                exclusive_json(path, {"two": 2})
            with self.assertRaises(ValueError):
                verify(path, "0" * 64)


if __name__ == "__main__":
    unittest.main()
