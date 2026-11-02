"""Offline CPU checks for B-PROPER arithmetic and immutable experiment rules."""

import ast
import copy
import importlib.util
import json
import math
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.erasure_pilot_bp_train import FALLBACKS, cut_updates, learning_rate, timeout_seconds
from scripts.erasure_pilot_bp_review import counts, heldout_counts, loss_rule, prefix_summary
from scripts.erasure_pilot_bp_data import has_overlap
from scripts.erasure_pilot_b_data import word_ngrams


ROOT = Path(__file__).resolve().parents[1]
TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


class FrozenRunTests(unittest.TestCase):
    def test_bounded_overlap_matches_original(self):
        grams = word_ngrams("One two three four five six seven")
        for text in ("", "one two", "ONE TWO THREE FOUR FIVE", "one two three four no",
                     "Punctuation: one, two; three four five!", "abc " * 10000):
            self.assertEqual(has_overlap(text, grams), bool(grams.intersection(word_ngrams(text))))

    def test_timeout_never_exceeds_cap(self):
        for rate in (1.2452, 4.9852, 6.6952):
            for cap in (1.5, 4, 11):
                seconds = timeout_seconds(cap, rate)
                self.assertLessEqual(seconds * rate / 3600, cap)
                self.assertGreater((seconds + 1) * rate / 3600, cap)

    def test_token_cut_uses_actual_remaining_time(self):
        self.assertEqual(cut_updates(611, 12, 5, 6000), 611)
        self.assertEqual(cut_updates(611, 12, 10, 5000), 242)
        self.assertEqual(cut_updates(611, 12, 10, 2600), 12)

    def test_warmup_unchanged_after_schedule_cut(self):
        for step in (1, 12, 13, 49, 50):
            self.assertEqual(learning_rate(step, 242), learning_rate(step, 611))
        self.assertEqual(learning_rate(242, 242), 0)

    def test_fallback_order_ends_at_november_setting(self):
        self.assertEqual(FALLBACKS[0], (8, False, 512, "fused"))
        self.assertEqual(FALLBACKS[-1], (1, True, 64, "scalar"))
        self.assertEqual([row[0] for row in FALLBACKS], [8, 4, 2, 1, 1, 1])

    def test_source_revisions_filter_and_optimizer_unchanged(self):
        old = json.loads((ROOT / "config/erasure_pilot_v1/approach_b/settings.json").read_text())
        new = json.loads((ROOT / "config/erasure_pilot_v1/approach_b_proper/settings.json").read_text())
        for key in ("base", "revision", "seed", "noise_beta", "tokens", "sequence_length",
                    "sequences_per_step", "learning_rate", "warmup_steps", "optimizer", "datasets", "filter"):
            self.assertEqual(old[key], new["training"][key], key)
        self.assertEqual(new["training"]["alphas"], [0.6, 0.8])
        self.assertEqual(new["finish_reserve_seconds"], 2700)

    def test_full_kl_chunk_and_microbatch_additivity(self):
        teacher = [[0.2, 0.3, 0.5], [0.8, 0.1, 0.1], [0.4, 0.4, 0.2]]
        student = [[0.3, 0.3, 0.4], [0.5, 0.3, 0.2], [0.2, 0.4, 0.4]]
        losses = [sum(p * math.log(p / q) for p, q in zip(t, s)) for t, s in zip(teacher, student)]
        whole = sum(losses) / 3
        chunked = sum(sum(losses[i:i + 2]) / 3 for i in range(0, 3, 2))
        self.assertAlmostEqual(whole, chunked, places=14)

    def test_padding_denominator_counts_transitions(self):
        lengths = [1024] * 31 + [128]
        self.assertEqual(sum(max(0, length - 1) for length in lengths), 31 * 1023 + 127)
        self.assertEqual(math.ceil(20_000_000 / 32768), 611)

    def test_new_kl_has_no_item_or_host_boolean_sync(self):
        tree = ast.parse((ROOT / "scripts/erasure_pilot_bp_train.py").read_text())
        node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "distill_backward")
        calls = [item for item in ast.walk(node) if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute)]
        self.assertFalse(any(item.func.attr in {"item", "cpu", "any"} for item in calls))

    def test_reference_answers_are_same_text(self):
        base = ROOT / "derisk/erasure_pilot_v1/approach_b"
        left = json.loads((base / "alpha03/relearning_answers.judged.json").read_text(encoding="utf-8"))
        right = json.loads((base / "alpha06/relearning_answers.judged.json").read_text(encoding="utf-8"))
        self.assertEqual(len(left["results"]), 20)
        self.assertEqual([x["transcript"][0]["assistant"] for x in left["results"]],
                         [x["transcript"][0]["assistant"] for x in right["results"]])
        self.assertTrue(all(x["judge"]["target_label"] == "SUBSTANTIVE" for x in left["results"]))

    def test_rules_use_new_clean_ids_and_include_nearby_broken(self):
        clean = {"results": [
            {"id": "t1", "group": "target", "judge": {"target_label": "SUBSTANTIVE", "broken": False}},
            {"id": "t2", "group": "target", "judge": {"target_label": "ABSENT", "broken": False}},
            {"id": "d1", "group": "distant", "judge": {"usefulness": "USEFUL", "broken": False}}]}
        edited = {"results": [
            {"id": "t1", "group": "target", "judge": {"target_label": "ABSENT", "broken": False}},
            {"id": "t2", "group": "target", "judge": {"target_label": "SUBSTANTIVE", "broken": False}},
            {"id": "d1", "group": "distant", "judge": {"usefulness": "USEFUL", "broken": False}},
            {"id": "n1", "group": "nearby", "judge": {"broken": True}}]}
        result = counts(edited, clean)
        self.assertEqual(result["qualifying_targets"], 1)
        self.assertEqual(result["target_required"], 1)
        self.assertEqual(result["rules_1_to_3"], [True, True, False])

    def test_heldout_gate_does_not_pass_ineligible_student(self):
        clean = {"results": [{"id": "h1", "group": "heldout",
                              "judge": {"target_label": "SUBSTANTIVE", "broken": False}}]}
        student = {"results": [{"id": "h1", "group": "heldout",
                                "judge": {"target_label": "ABSENT", "broken": False}}]}
        self.assertIsNone(heldout_counts(student, clean, False)["rule_4"])
        self.assertTrue(heldout_counts(student, clean, True)["rule_4"])

    def test_loss_requires_all_three_conditions_and_erasure_gates(self):
        def measured(target, distant):
            return {"target": {"mean_item_ce_nats": target}, "distant": {"mean_item_ce_nats": distant}}
        clean, a3, student = measured(1, 1), measured(2, 1.5), measured(4, 2)
        self.assertEqual(loss_rule(clean, a3, student, 20, 19, True)["classification"], "loss")
        self.assertEqual(loss_rule(clean, a3, student, 20, 20, True)["classification"], "denial")
        self.assertEqual(loss_rule(clean, a3, student, 20, 19, False)["classification"], "failed erasure gates")

    def test_heldout_absolute_eighteen_is_an_alternative_to_qualification(self):
        clean = {"results": [{"id": str(i), "group": "heldout", "judge": {
            "target_label": "SUBSTANTIVE" if i else "ABSENT", "broken": False}}
            for i in range(20)]}
        student = {"results": [{"id": str(i), "group": "heldout", "judge": {
            "target_label": "ABSENT" if i < 18 else "SUBSTANTIVE", "broken": False}}
            for i in range(20)]}
        result = heldout_counts(student, clean, True)
        self.assertEqual(result["qualifying_absent"], 17)
        self.assertEqual(result["all_absent"], 18)
        self.assertTrue(result["rule_4"])

    def test_modal_secret_dependency_count_matches_in_remote_import(self):
        tree = ast.parse((ROOT / "scripts/erasure_pilot_bp_modal.py").read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "hf_secret")
        module = ast.Module(body=[function], type_ignores=[])
        fake_root = SimpleNamespace(__truediv__=None)

        class FixtureRoot:
            def __truediv__(self, name):
                return SimpleNamespace(read_text=lambda **kwargs: "HUGGINGFACE_TOKEN=offline_fixture")

        for local in (True, False):
            fake_modal = SimpleNamespace(is_local=lambda: local,
                                         Secret=SimpleNamespace(from_dict=lambda value: set(value)))
            namespace = {"modal": fake_modal, "os": SimpleNamespace(environ={"HF_TOKEN": "offline_fixture"}),
                         "ROOT": FixtureRoot()}
            exec(compile(module, "isolated_secret_definition", "exec"), namespace)
            self.assertEqual(namespace["hf_secret"](), [{"HF_TOKEN"}])


@unittest.skipUnless(TORCH_AVAILABLE, "Offline interpreter has no PyTorch; no downloads permitted")
class KernelGradientTests(unittest.TestCase):
    def test_chunked_full_vocab_gradients_match_dense(self):
        import torch
        import torch.nn.functional as functional
        from scripts.test_erasure_pilot_b import TinyModel
        from scripts.erasure_pilot_bp_train import distill_backward

        teacher = TinyModel(123).requires_grad_(False)
        student = TinyModel(456)
        dense_student = copy.deepcopy(student)
        ids = torch.tensor([[2, 3, 4, 5, 1], [6, 7, 8, 1, 1]])
        mask = torch.tensor([[1, 1, 1, 1, 0], [1, 1, 1, 0, 0]])
        valid = (mask[:, 1:] * mask[:, :-1]).reshape(-1).bool()
        positions = valid.nonzero().flatten()
        with torch.no_grad():
            th = teacher.backbone(ids, mask).last_hidden_state[:, :-1]
            tl = functional.log_softmax(teacher.lm_head(th).reshape(-1, 17)[valid], dim=-1)
        sh = dense_student.backbone(ids, mask).last_hidden_state[:, :-1]
        sl = functional.log_softmax(dense_student.lm_head(sh).reshape(-1, 17)[valid], dim=-1)
        dense = functional.kl_div(sl, tl, log_target=True, reduction="sum") / 5
        dense.backward()
        actual = distill_backward(teacher, student, ids, mask, 5, positions, 2)
        torch.testing.assert_close(actual, dense.detach())
        for left, right in zip(student.parameters(), dense_student.parameters()):
            torch.testing.assert_close(left.grad, right.grad, atol=2e-6, rtol=2e-5)

    def test_noise_rejects_old_alpha_and_preserves_tied_weights(self):
        import torch
        from scripts.test_erasure_pilot_b import TinyModel
        from scripts.erasure_pilot_bp_train import noise_student

        model = TinyModel(123)
        with self.assertRaises(ValueError):
            noise_student(model, 0.3)
        original = copy.deepcopy(model)
        noise_student(model, 0.8)
        self.assertIs(model.lm_head.weight, model.backbone.embedding.weight)
        torch.testing.assert_close(model.backbone.linear.bias, original.backbone.linear.bias * 0.2)


if __name__ == "__main__":
    unittest.main()
