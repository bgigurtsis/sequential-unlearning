"""CPU-only qualification of training preparation and clean-answer joining."""
import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

try:
    from scripts import build_context_diversity_prompts as builder
except ModuleNotFoundError:
    import build_context_diversity_prompts as builder


class ContextPreparationTests(unittest.TestCase):
    def fixture(self):
        return builder.build_records({"original.json": {"group_a": ["Original scenario A.", "Original scenario B."]}})

    def capture(self, records):
        return {"model": "clean", "tokenizer_model": "clean-tokenizer",
                "candidates": [{"adapter": "clean", "generations":
                    [{**row, "generation": f"Clean answer for {row['id']}"} for row in records]}]}

    def join(self, records, capture):
        return builder.attach_clean_answers(records, capture, expected_model="clean", expected_tokenizer="clean-tokenizer")

    def test_count_family_coverage_and_original_text(self):
        rows = self.fixture()
        self.assertEqual(len(rows), 10)
        self.assertEqual(Counter(r["task_family"] for r in rows), {name: 2 for name in builder.FRAMES})
        for row in rows:
            self.assertTrue(row["prompt"].endswith(row["source_scenario"]))
            self.assertNotIn("answer", row)
            self.assertNotIn("source_answer_proxy", row)
            self.assertIn(row["target_response"], builder.RESPONSES)
            self.assertNotIn("<eos>", row["target_response"])

    def test_determinism_and_seed_changes_order(self):
        source = {"a": {"one": ["Scenario one", "Scenario two"]}}
        first = builder.build_records(source)
        self.assertEqual(builder.json_bytes(first), builder.json_bytes(builder.build_records(source)))
        changed = builder.build_records(source, seed=builder.SEED + 1)
        self.assertNotEqual([r["id"] for r in first], [r["id"] for r in changed])
        self.assertEqual({r["prompt"] for r in first}, {r["prompt"] for r in changed})

    def test_rejects_malformed_or_duplicate_scenarios(self):
        for groups in ({}, {"a": []}, {"a": [None]}, {"a": [" "]}, {"a": ["Same", " same "]}):
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                builder.build_records({"a": groups})

    def test_overlap_checks_prompts_turns_not_answers(self):
        rows = self.fixture()
        data = {"records": [{"prompt": "unrelated", "answer": rows[0]["prompt"]}],
                "conversations": [{"turns": ["another prompt"]}]}
        evaluation = builder.evaluation_prompts(data)
        builder.prove_disjoint(rows, evaluation)
        for content in (rows[0]["prompt"], rows[0]["source_scenario"]):
            leaked = " \n ".join(content.upper().split())
            with self.assertRaises(ValueError):
                builder.prove_disjoint(rows, builder.evaluation_prompts({"turns": [leaked]}))
        self.assertIn("user question", builder.evaluation_prompts({"messages": [{"role": "user", "content": "User question"}]}))

    def test_pinned_production_sources_and520_records(self):
        root = Path(__file__).resolve().parents[1]
        rows, manifest = builder.prepare(root)
        self.assertEqual(len(rows), 520)
        self.assertEqual(manifest["overlap"]["original_scenarios"], 104)
        self.assertEqual(manifest["overlap"]["overlap_count"], 0)
        self.assertEqual(manifest["family_counts"], {name: 104 for name in builder.FRAMES})
        self.assertEqual(set(manifest["response_counts"].values()), {65})
        self.assertEqual(manifest["probes_sha256"], builder.sha256(builder.json_bytes(rows)))

    def test_source_pin_failure_before_evaluation_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / next(iter(builder.SOURCE_PINS))
            first.parent.mkdir(parents=True)
            first.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "pin mismatch"):
                builder.prepare(root)

    def test_publish_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "preparation"
            rows = self.fixture()
            builder.publish_preparation(rows, {"trainer_ready": False}, dest)
            before = (dest / "probes.json").read_bytes()
            self.assertEqual(json.loads(before), rows)
            with self.assertRaises(FileExistsError):
                builder.publish_preparation([], {}, dest)
            self.assertEqual((dest / "probes.json").read_bytes(), before)

    def test_clean_join_preserves_order_and_uses_real_answers(self):
        rows = self.fixture()
        capture = self.capture(rows)
        capture["candidates"][0]["generations"].reverse()
        joined = self.join(rows, capture)
        self.assertEqual([r["id"] for r in joined], [r["id"] for r in rows])
        for row in joined:
            self.assertEqual(row["answer"], f"Clean answer for {row['id']}")
            self.assertNotEqual(row["answer"], row["source_scenario"])
            self.assertNotEqual(row["answer"], row["target_response"])

    def test_clean_join_rejects_identity_count_prompt_or_answer_corruption(self):
        rows = self.fixture()
        mutations = [
            lambda c: c.update(model="other"),
            lambda c: c.update(tokenizer_model="other"),
            lambda c: c["candidates"][0].update(adapter="other"),
            lambda c: c["candidates"][0]["generations"].pop(),
            lambda c: c["candidates"][0]["generations"][0].update(id="unknown"),
            lambda c: c["candidates"][0]["generations"][0].update(prompt="changed"),
            lambda c: c["candidates"][0]["generations"][0].update(target_response="changed"),
            lambda c: c["candidates"][0]["generations"][0].update(generation=" "),
        ]
        for mutate in mutations:
            capture = self.capture(rows)
            mutate(capture)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                self.join(rows, capture)
        capture = self.capture(rows)
        capture["candidates"][0]["generations"][0] = copy.deepcopy(capture["candidates"][0]["generations"][1])
        with self.assertRaises(ValueError):
            self.join(rows, capture)


if __name__ == "__main__":
    unittest.main()
