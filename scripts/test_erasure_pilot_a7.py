"""Offline CPU tests for A7. No model, network access or downloaded test input."""

import json
import math
import random
import unittest
from unittest.mock import patch

import torch

from scripts import erasure_pilot_a7_math as objective
from scripts import erasure_pilot_a7_run as job
from scripts import erasure_pilot_a7_review as review
from scripts import erasure_pilot_a5_run as parent


class A7Tests(unittest.TestCase):
    def test_all_frozen_indices(self):
        source = job.ROOT / "derisk/erasure_pilot_v1/approach_a3/timings.jsonl"
        records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
        observed = {row["step"]: row["sampled_indices"] for row in records if row["event"] == "train_step"}
        self.assertEqual(set(observed), set(range(1, 151)))
        old, everyday, npo = random.Random(20261101), random.Random(20261102), random.Random(20261103)
        expected_everyday, expected_npo = random.Random(20261102), random.Random(20261103)
        for step in range(1, 201):
            actual = job.draw_indices(old, everyday, npo)
            if step <= 150:
                self.assertEqual(actual["forget"], observed[step]["forget"], f"forget step {step}")
                self.assertEqual(actual["retain"], observed[step]["retain"], f"distant step {step}")
            drawn = expected_everyday.sample(range(240), 8)
            self.assertEqual(actual["everyday_drawn"], drawn)
            self.assertEqual(actual["everyday"], drawn[:2])
            self.assertEqual(actual["npo"], expected_npo.sample(range(300), 8))

    def test_npo_stream_never_consumes_old_streams(self):
        first = [random.Random(seed) for seed in [20261101, 20261102, 20261103]]
        second = [random.Random(seed) for seed in [20261101, 20261102, 20261103]]
        for _ in range(200):
            first[2].random()
            a, b = job.draw_indices(*first), job.draw_indices(*second)
            for name in ["forget", "retain", "everyday"]:
                self.assertEqual(a[name], b[name])

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

    def test_screening_stops_at_seventy_five_minutes(self):
        deadline = 123456.0
        self.assertTrue(job.screening_allowed(deadline - 4500 - 0.01, deadline))
        self.assertFalse(job.screening_allowed(deadline - 4500, deadline))
        self.assertFalse(job.screening_allowed(deadline - 4500 + 0.01, deadline))

    def test_selected_wait_ends_at_forty_minutes(self):
        self.assertEqual(job.selection_deadline(123456.0), 123456.0 - 2400)

    def test_an_inflight_screen_stops_before_the_next_reply(self):
        deadline = 123456.0
        items = [{"id": "first", "group": "target"}, {"id": "second", "group": "distant"}]
        record = {"id": "first", "transcript": [{"assistant": "I cannot remember."}], "elapsed_seconds": 2.0}
        with patch.object(job.run.harness, "load_questions", return_value=(items, {})), \
             patch.object(job.run.harness, "checkpoint_hashes", return_value={}), \
             patch.object(job.run.harness, "generate_item", return_value=record) as generate, \
             patch.object(job.run, "write"), patch.object(job.run, "log"), \
             patch.object(job.time, "time", side_effect=[deadline - 4501, deadline - 4499]):
            payload = job.generate_screen(None, None, 100, deadline)
        self.assertEqual(generate.call_count, 1)
        self.assertFalse(payload["complete"])
        self.assertEqual(len(payload["results"]), 1)

    def test_frozen_candidate_rules(self):
        def screen(step, target, distant, openers):
            return {"step": step, "target": {"refused": target},
                    "distant": {"refused": distant}, "refused_openers": openers}
        screens = [screen(60, 36, 1, 9), screen(80, 35, 0, 8), screen(100, 34, 2, 7),
                   screen(120, 28, 2, 0), screen(150, 40, 3, 0)]
        self.assertEqual(job.candidates(screens), [60, 80, 100, 120])

    def test_no_model_download_needed_for_imports(self):
        self.assertEqual(job.SCREEN_ORDER, [100, 150, 200, 60, 80, 120, 140, 160, 180, 70, 90, 110, 130, 170, 190])
        self.assertEqual(objective.npo_loss(torch.tensor(0.0), 0.0).item(), torch.tensor(2 * math.log(2)).item())

    def test_loss_comparisons_keep_frozen_strictness(self):
        clean = {"target": {"mean_item_ce_nats": 0.0}, "distant": {"mean_item_ce_nats": 0.0}}
        a3 = {"target": {"mean_item_ce_nats": 1.0}, "distant": {"mean_item_ce_nats": 0.0}}
        selected = {"target": {"mean_item_ce_nats": 2.0}, "distant": {"mean_item_ce_nats": 1.0}}
        tests = review.loss_tests(clean, a3, selected, 36, 35)
        self.assertEqual([tests[key] for key in ["L1", "L2", "L3"]], [True, True, True])
        tests = review.loss_tests(clean, a3, a3, 36, 36)
        self.assertFalse(tests["L2"])
        self.assertFalse(tests["L3"])

    def test_prefix_aggregation_is_mean_per_item(self):
        payload = {"results": [{"id": "t1", "scored_tokens": 10, "sum_nll_nats": 10.0, "mean_ce_nats": 1.0},
                               {"id": "t2", "scored_tokens": 100, "sum_nll_nats": 300.0, "mean_ce_nats": 3.0},
                               {"id": "d1", "scored_tokens": 0, "sum_nll_nats": 0.0, "mean_ce_nats": None}]}
        result = review.prefix_summary(payload, {"t1", "t2"}, {"d1"})
        self.assertEqual(result["target"]["mean_item_ce_nats"], 2.0)
        self.assertAlmostEqual(result["target"]["token_weighted_ce_nats"], 310 / 110)
        self.assertEqual(result["distant"]["no_suffix_ids"], ["d1"])

    def test_every_other_stream_matches_ns_for_all_two_hundred_steps(self):
        a7_rng = [random.Random(seed) for seed in [20261101, 20261102, 20261103]]
        ns_rng = [random.Random(seed) for seed in [20261101, 20261102, 20261103]]
        logged = [json.loads(line) for line in (job.ROOT / "derisk/erasure_pilot_v1/approach_a5/arm_ns/training.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(logged), 200)
        for step, row in enumerate(logged, 1):
            actual, ns = job.draw_indices(*a7_rng), parent.draw_indices(*ns_rng)
            for key in ["forget", "retain", "npo"]:
                self.assertEqual(actual[key], ns[key], f"{key} step {step}")
                self.assertEqual(actual[key], row["sampled_indices"][key], f"logged {key} step {step}")
            self.assertEqual(actual["everyday_drawn"], ns["everyday"])
            self.assertEqual(actual["everyday_drawn"], row["sampled_indices"]["everyday"])
            self.assertEqual(actual["everyday"], ns["everyday"][:2])
            for first, second in zip(a7_rng, ns_rng):
                self.assertEqual(first.getstate(), second.getstate())

    def test_two_everyday_examples_keep_the_divisor_of_eight(self):
        import ast
        tree = ast.parse((job.ROOT / "scripts/erasure_pilot_a7_run.py").read_text(encoding="utf-8"))
        train = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "train")
        source = ast.unparse(train)
        self.assertIn("(loss / 8).backward()", source)
        parameter = torch.tensor(1.25, requires_grad=True)
        losses = [(parameter - target).square() for target in [0.25, 0.75]]
        total = sum(loss / 8 for loss in losses)
        total.backward()
        self.assertAlmostEqual(parameter.grad.item(), (2 * 1.0 + 2 * 0.5) / 8)
        mean = sum(loss.item() for loss in losses) / 2
        self.assertAlmostEqual(total.item(), mean * 2 / 8)


if __name__ == "__main__":
    unittest.main()
