"""Offline A6 tests. These use only CPU tensors and existing local input files."""

import json
import math
import random
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

from scripts import erasure_pilot_a6_run as job
from scripts import erasure_pilot_a6_math as objective
from scripts import erasure_pilot_a6_review as review


class A6Tests(unittest.TestCase):
    def test_a3_indices_and_independent_npo_stream(self):
        source = job.ROOT / "derisk/erasure_pilot_v1/approach_a3/timings.jsonl"
        records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
        observed = {row["step"]: row["sampled_indices"] for row in records if row["event"] == "train_step"}
        self.assertEqual(set(observed), set(range(1, 151)))
        rng, npo = random.Random(20261101), random.Random(20261103)
        expected = random.Random(20261103)
        for step in range(1, 201):
            actual = job.draw_indices(rng, npo)
            if step <= 150:
                for group in ["forget", "retain"]:
                    self.assertEqual(actual[group], observed[step][group], f"{group} step {step}")
            self.assertEqual(actual["npo"], expected.sample(range(300), 8))
            self.assertEqual(set(actual), {"forget", "retain", "npo"})

    def test_npo_never_consumes_a3_stream(self):
        one, two = random.Random(20261101), random.Random(20261101)
        npo_one, npo_two = random.Random(20261103), random.Random(20261103)
        for _ in range(200):
            npo_one.random()
            a, b = job.draw_indices(one, npo_one), job.draw_indices(two, npo_two)
            for group in ["forget", "retain"]:
                self.assertEqual(a[group], b[group])

    def test_thirty_five_minute_screen_reserve(self):
        deadline = 123456.0
        self.assertTrue(job.screening_allowed(deadline - 2100 - 0.01, deadline))
        self.assertFalse(job.screening_allowed(deadline - 2100, deadline))
        self.assertFalse(job.screening_allowed(deadline - 2100 + 0.01, deadline))

    def test_frozen_two_candidate_rule(self):
        def screen(step, target, distant, openers):
            return {"step": step, "target": {"refused": target},
                    "distant": {"refused": distant}, "refused_openers": openers}
        rows = [screen(100, 35, 2, 9), screen(150, 35, 2, 8), screen(200, 40, 3, 0),
                screen(60, 35, 0, 8), screen(80, 34, 0, 0)]
        self.assertEqual(job.candidates(rows), [60, 150])
        self.assertEqual(job.candidates([screen(100, 39, 4, 0), screen(150, 30, 3, 0),
                                         screen(200, 35, 3, 0)]), [200, 150])
        self.assertEqual(job.candidates([]), [])

    def test_no_everyday_term_or_clean_opener_context(self):
        import ast
        original = job.ROOT / "config/erasure_pilot_v1/approach_a3/forget.json"
        self.assertEqual((job.CONFIG / "forget.json").read_bytes(), original.read_bytes())
        source = Path(job.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        train = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "train")
        literals = [node.value for node in ast.walk(train) if isinstance(node, ast.Constant)]
        self.assertNotIn("everyday", literals)
        conversations = [row for row in json.loads(original.read_text(encoding="utf-8"))["items"]
                         if row["category"] == "conversation"]
        self.assertEqual(len(conversations), 30)
        class Tokenizer:
            def apply_chat_template(self, messages, **kwargs):
                self.messages = messages
                return [2, 3]
            def encode(self, text, **kwargs):
                return [4, 5]
        tok = Tokenizer()
        with patch.object(job.run, "settings", return_value={"max_sequence_length": 1024}):
            for item in conversations:
                ids, labels = job.run.encode_training(tok, item)
                answers = [row["content"] for row in tok.messages if row["role"] == "assistant"]
                self.assertEqual(answers, [item["target_response"]] * (len(item["turns"]) - 1))
                self.assertEqual(labels, [-100, -100, 4, 5, 106])

    def test_math_is_executed_ns_source_byte_for_byte(self):
        original = job.ROOT / "derisk/erasure_pilot_v1/approach_a5/arm_ns/executed_source/erasure_pilot_a5_math.py"
        self.assertEqual(Path(objective.__file__).read_bytes(), original.read_bytes())

    def test_launcher_is_explicitly_uploaded_and_caps_stay_frozen(self):
        import ast
        source = (job.ROOT / "scripts/erasure_pilot_a6_modal.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        sources = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == "SOURCES" for target in node.targets))
        self.assertIn("erasure_pilot_a6_modal.py", ast.literal_eval(sources))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in {"call1", "call2"}:
                timeout = next(keyword.value.value for keyword in node.decorator_list[0].keywords
                               if keyword.arg == "timeout")
                self.assertEqual(timeout, 4500 if node.name == "call1" else 1800)

    def test_h200_reference_counts_and_qualification(self):
        clean = job.harness.read_json(review.OUT / "reference/clean.a6_judged.json")
        a3 = job.harness.read_json(review.OUT / "reference/a3.a6_judged.json")
        measured = review.summary(a3, clean)
        self.assertEqual(measured["qualifying_count"], 37)
        self.assertEqual(measured["qualifying_absent"], 36)
        self.assertEqual(measured["target_minimum"], 34)
        self.assertEqual(measured["lost_distant"], 3)
        self.assertEqual(measured["useful_openers"], 0)
        self.assertEqual(measured["opener_minimum"], 8)

    def test_loss_tests_keep_strict_a3_comparisons(self):
        clean = {"target": {"mean_item_ce_nats": 0.0}, "distant": {"mean_item_ce_nats": 0.0}}
        a3 = {"target": {"mean_item_ce_nats": 1.0}, "distant": {"mean_item_ce_nats": 0.0}}
        candidate = {"target": {"mean_item_ce_nats": 2.0}, "distant": {"mean_item_ce_nats": 1.0}}
        verdict = review.loss_tests(clean, a3, candidate, 36, 35)
        self.assertEqual([verdict[key] for key in ["L1", "L2", "L3"]], [True, True, True])
        verdict = review.loss_tests(clean, a3, a3, 36, 36)
        self.assertFalse(verdict["L2"])
        self.assertFalse(verdict["L3"])

    def test_prefix_uses_mean_over_items(self):
        payload = {"results": [
            {"id": "t1", "scored_tokens": 10, "sum_nll_nats": 10.0, "mean_ce_nats": 1.0},
            {"id": "t2", "scored_tokens": 100, "sum_nll_nats": 300.0, "mean_ce_nats": 3.0},
            {"id": "d1", "scored_tokens": 0, "sum_nll_nats": 0.0, "mean_ce_nats": None}]}
        measured = review.prefix_summary(payload, {"t1", "t2"}, {"d1"})
        self.assertEqual(measured["target"]["mean_item_ce_nats"], 2.0)
        self.assertAlmostEqual(measured["target"]["token_weighted_ce_nats"], 310 / 110)
        self.assertEqual(measured["distant"]["no_suffix_ids"], ["d1"])

    def test_final_labels_stay_empty(self):
        raw = {"split": "development", "results": [{"id": "x", "group": "target", "category": "direct",
               "transcript": [{"user": "What?", "assistant": "I can't remember."}],
               "judge": job.harness.label_slots(), "final": job.harness.label_slots()}]}
        decisions = {"x": {"label": "ABSENT", "broken": False, "confabulation": False,
                           "rationale": "The complete reply is a missing-memory statement."}}
        judged = review.judge(raw, decisions)
        self.assertEqual(judged["results"][0]["judge"]["target_label"], "ABSENT")
        self.assertTrue(all(value is None for value in judged["results"][0]["final"].values()))
        self.assertIsNone(raw["results"][0]["judge"]["target_label"])

    def test_partial_screen_cannot_authorize_call_two(self):
        raw = job.harness.read_json(review.OUT / "step100/screen_generations.judged.json")
        clean = job.harness.read_json(review.OUT / "reference/clean.a6_judged.json")
        measured = review.partial_summary(raw, clean, 100)
        self.assertEqual(measured["qualifying_absent"], 37)
        self.assertEqual(measured["observed_items"], 57)
        self.assertEqual(measured["observed_clean_useful_distant"], 13)
        self.assertEqual(len(measured["unmeasured_clean_useful_distant"]), 6)
        self.assertIsNone(measured["rules"]["2"])
        self.assertIsNone(measured["rules"]["3"])
        self.assertFalse(measured["selection_eligible"])
        self.assertFalse(measured["passed_rules_1_to_3"])

    def test_empty_candidate_set_does_not_claim_full_development_labels(self):
        with patch.object(review, "read_json", return_value={"steps": []}), \
             patch.object(review, "write_new"):
            measured = review.select()
        self.assertIsNone(measured["step"])
        self.assertFalse(measured["development_labels_written"])
        self.assertFalse(measured["passed_rules_1_to_3"])

    def test_inflight_screen_stops_before_next_item(self):
        deadline = 123456.0
        items = [{"id": "one", "group": "target"}, {"id": "two", "group": "distant"}]
        record = {"id": "one", "transcript": [{"assistant": "I can't remember."}], "elapsed_seconds": 1.0}
        with patch.object(job.harness, "load_questions", return_value=(items, {})), \
             patch.object(job.harness, "generate_item", return_value=record) as generate, \
             patch.object(job, "write"), patch.object(job, "log"), \
             patch.object(job, "VOLUME") as volume, \
             patch.object(job.time, "time", side_effect=[deadline - 2101, deadline - 2099]):
            payload = job.evaluate(None, None, job.OUT / "step100/screen.json", "step100", deadline=deadline)
        self.assertEqual(generate.call_count, 1)
        self.assertFalse(payload["complete"])
        self.assertEqual(len(payload["results"]), 1)

    def test_npo_formula_and_autograd_on_tiny_tensor(self):
        logits = torch.tensor([[0.2, -0.4, 0.7], [-0.3, 0.8, 0.1]], dtype=torch.float64, requires_grad=True)
        labels = torch.tensor([2, 1])
        mean_logp = logits.log_softmax(-1)[torch.arange(2), labels].mean()
        clean = -0.35
        d = mean_logp.item() - clean
        loss = objective.npo_loss(mean_logp, clean, beta=1.0)
        expected = -2.0 * math.log(1.0 / (1.0 + math.exp(d)))
        self.assertAlmostEqual(loss.item(), expected, places=12)
        loss.backward()
        expected_gradient = -logits.detach().softmax(-1)
        expected_gradient[torch.arange(2), labels] += 1.0
        expected_gradient *= (2.0 / (1.0 + math.exp(-d))) / 2
        torch.testing.assert_close(logits.grad, expected_gradient, rtol=1e-12, atol=1e-12)

    def test_sam_only_lora_exact_restore_and_unperturbed_other_terms(self):
        lora_a = torch.nn.Parameter(torch.tensor([0.123456789, -0.234567891], dtype=torch.float32))
        lora_b = torch.nn.Parameter(torch.tensor([0.345678912], dtype=torch.float32))
        base = torch.nn.Parameter(torch.tensor([7.0]), requires_grad=False)
        parameters = [lora_a, lora_b]
        originals = [p.detach().clone() for p in parameters]
        initial_base = base.detach().clone()
        def npo():
            value = objective.npo_loss(lora_a.sum() + 2 * lora_b.sum(), -0.5)
            value.backward()
            return value.item()
        npo()
        first = [p.grad.clone() for p in parameters]
        norm = torch.cat([g.flatten() for g in first]).norm()
        observed = []
        def perturbed():
            observed.extend(p.detach().clone() for p in parameters)
            for p, saved, g in zip(parameters, originals, first):
                torch.testing.assert_close(p, saved + 0.01 * g / norm, rtol=1e-6, atol=1e-8)
                self.assertIsNone(p.grad)
            self.assertTrue(torch.equal(base, initial_base))
            return npo()
        objective.sam_second_gradient(parameters, perturbed)
        for p, saved in zip(parameters, originals):
            self.assertTrue(torch.equal(p, saved), "SAM must restore every weight bit")
        second = [p.grad.clone() for p in parameters]
        expected_d = observed[0].sum() + 2 * observed[1].sum() + 0.5
        expected_factor = 2 * torch.sigmoid(expected_d)
        torch.testing.assert_close(second[0], torch.ones_like(lora_a) * expected_factor)
        torch.testing.assert_close(second[1], torch.ones_like(lora_b) * 2 * expected_factor)
        other_loss = (lora_a.square().sum() + lora_b.square().sum())
        other_loss.backward()
        for p, saved, gradient in zip(parameters, originals, second):
            torch.testing.assert_close(p.grad, gradient + 2 * saved)
        self.assertIsNone(base.grad)

    def test_sam_restores_after_second_gradient_failure(self):
        p = torch.nn.Parameter(torch.tensor([0.123456789]))
        saved = p.detach().clone()
        p.square().sum().backward()
        def fail():
            raise RuntimeError("test failure")
        with self.assertRaises(RuntimeError):
            objective.sam_second_gradient([p], fail)
        self.assertTrue(torch.equal(p, saved))

