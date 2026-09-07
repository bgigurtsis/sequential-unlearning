import unittest

try:
    from train_biography_sft import build_batch_plan, encode_record, twin_batch, validate_batch_plan, validate_dev_records
except ModuleNotFoundError:
    from scripts.train_biography_sft import build_batch_plan, encode_record, twin_batch, validate_batch_plan, validate_dev_records


class FakeTokenizer:
    pad_token_id = 0

    def apply_chat_template(self, messages, **kwargs):
        # A deterministic stand-in for Gemma's template. The helpers must not
        # depend on tokenizer internals beyond this public interface.
        text = "|".join(m["role"] + ":" + m["content"] for m in messages) + "|assistant:"
        return {"input_ids": [10 + (ord(c) % 17) for c in text]}

    def __call__(self, text, **kwargs):
        class Encoded:
            input_ids = [20 + (ord(c) % 19) for c in text]
        return Encoded()


def records():
    return [
        {"id": "vac-1", "episode": "vacation", "prompt": "Where?", "answer": "Linden Reach"},
        {"id": "bike-1", "episode": "bicycle", "prompt": "What?", "answer": "A bicycle"},
        {"id": "phone-1", "episode": "phone", "prompt": "Who?", "answer": "Mara"},
    ]


class BiographySftTests(unittest.TestCase):
    def test_encoding_masks_prompt_and_adds_one_terminator(self):
        encoded = encode_record(FakeTokenizer(), records()[0])
        self.assertEqual(encoded["input_ids"][-1], 106)
        self.assertEqual(encoded["labels"][: encoded["prompt_tokens"]], [-100] * encoded["prompt_tokens"])
        self.assertEqual(encoded["labels"].count(106), 1)

    def test_long_records_are_rejected_without_truncation(self):
        with self.assertRaises(ValueError):
            encode_record(FakeTokenizer(), {"id": "x", "prompt": "p", "answer": "a" * 1000}, max_length=20)

    def test_messages_must_end_in_user(self):
        bad = {"id": "x", "messages": [{"role": "assistant", "content": "old"}], "answer": "new"}
        with self.assertRaises(ValueError):
            encode_record(FakeTokenizer(), bad)

    def test_dev_records_allow_generation_only_but_validate_gold_when_present(self):
        validate_dev_records([{"id": "generation", "prompt": "Recall?"}, {"id": "gold", "prompt": "Fact?", "answer": "answer"}])
        with self.assertRaises(ValueError):
            validate_dev_records([{"id": "bad", "prompt": "Fact?", "answer": ""}])

    def test_seeded_plan_is_reproducible_and_batch_eight(self):
        a = build_batch_plan(records(), seed=20260, steps=20)
        b = build_batch_plan(records(), seed=20260, steps=20)
        self.assertEqual(a, b)
        self.assertEqual(len(a["batches"]), 20)
        self.assertTrue(all(len(batch) == 8 for batch in a["batches"]))
        validate_batch_plan(a, records(), required_steps=20)
        a["batches"][0][0] = "missing"
        with self.assertRaises(ValueError):
            validate_batch_plan(a, records(), required_steps=20)

    def test_twin_drops_in_place_without_resampling(self):
        by_id = {r["id"]: r for r in records()}
        batch = ["vac-1", "bike-1", "vac-1", "phone-1"]
        kept = twin_batch(batch, by_id, "vacation")
        self.assertEqual([r["id"] for r in kept], ["bike-1", "phone-1"])


if __name__ == "__main__":
    unittest.main()
