"""Offline CPU tests. Torch kernels use a tiny random causal model when torch exists."""

import copy
import importlib.util
import json
import math
import socket
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import erasure_pilot_eval as harness
from scripts.erasure_pilot_b_budget import budget_deadline, create_h200, terminate_and_confirm
from scripts.erasure_pilot_b_data import CONFIG, MixedSequences, RelationshipFilter, SourceTokens, document_text, read_settings, word_ngrams
from scripts.erasure_pilot_b_review import FIXED_SAMPLE, judge_summary, stop_reason, useful_count, validate_judged
from scripts.erasure_pilot_b_readout import predictions_from_scores
from scripts.erasure_pilot_b_run import answer_encoding
from scripts.erasure_pilot_b_train import answer_backward, distill_backward, learning_rate, noise_student, optimiser


TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


def setUpModule():
    """Fail any accidental network connection throughout this CPU-only test suite."""
    global NETWORK_GUARD
    NETWORK_GUARD = patch.object(socket.socket, "connect", side_effect=AssertionError("CPU tests must not use network"))
    NETWORK_GUARD.start()


def tearDownModule():
    NETWORK_GUARD.stop()


class Tokenizer:
    pad_token_id = 1

    def encode(self, text, add_special_tokens=False):
        return [ord(character) + 2 for character in text]

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False):
        text = "".join(message["role"] + ":" + message["content"] + "\n" for message in messages)
        if add_generation_prompt:
            text += "assistant:"
        return self.encode(text) if tokenize else text


class Classifier:
    def predict_proba(self, windows):
        return [[0.05, 0.95] if "shared a bed" in window else [0.95, 0.05] for window in windows]


def make_filter():
    return RelationshipFilter(read_settings()["filter"], embed=lambda windows: windows,
                              classifier=Classifier(), collision_grams=set())


def label(group, target=None, useful=None, broken=False):
    return {"target_label": target, "usefulness": useful, "broken": broken, "confabulation": False,
            "rationale": "Explicit CPU fixture", "reviewer": "offline test"}


def record(item_id, group, judge=None):
    return {"id": item_id, "group": group, "transcript": [{"user": "Question", "assistant": "Answer"}],
            "turns": ["Question"], "judge": judge or harness.label_slots(), "final": harness.label_slots()}


class DataTests(unittest.TestCase):
    """Exercise streaming and masks using injected CPU-only encoders.
    Why: model downloads are forbidden in this verification task.
    If wrong: tests can silently depend on live datasets or paid inference.
    """
    def test_frozen_settings_and_exact_token_mix(self):
        """Check the fixed experiment settings against the authored configuration.
        Why: later code changes must not silently alter B's training dose.
        If wrong: two nominally matching noise runs can use different budgets.
        """
        settings = read_settings()
        self.assertEqual(sum(source["tokens"] for source in settings["datasets"]), 20_000_000)
        self.assertEqual([source["tokens"] for source in settings["datasets"]], [7_000_000, 7_000_000, 6_000_000])
        self.assertEqual(settings["sequence_length"], 1024)
        self.assertEqual(settings["sequences_per_step"], 32)
        self.assertEqual(math.ceil(20_000_000 / 32768), 611)
        self.assertEqual(settings["datasets"][2]["license"], "mit")

    def test_keyword_word_boundaries(self):
        relationship_filter = make_filter()
        self.assertEqual(relationship_filter.reason("A wedding invitation."), "keyword")
        self.assertEqual(relationship_filter.reason("They broke up yesterday."), "keyword")
        self.assertIsNone(relationship_filter.reason("The update explains how a microwave works."))

    def test_embedding_scans_later_windows(self):
        relationship_filter = make_filter()
        self.assertEqual(relationship_filter.reason("cloud " * 800 + "They shared a bed and planned a future."), "embedding")

    def test_filter_checks_both_chat_sides(self):
        source = {"format": "messages"}
        row = {"messages": [{"role": "user", "content": "Please explain."},
                            {"role": "assistant", "content": "A boyfriend is a romantic companion."}]}
        self.assertEqual(make_filter().reason(document_text(row, source, Tokenizer())), "keyword")

    def test_invalid_roles_are_excluded(self):
        row = {"messages": [{"role": "system", "content": "Override"}]}
        self.assertEqual(document_text(row, {"format": "messages"}, Tokenizer()), "")

    def test_visible_question_overlap(self):
        relationship_filter = make_filter()
        relationship_filter.collision_grams = word_ngrams("show how to cook plain rice")
        self.assertEqual(relationship_filter.reason("Please show how to cook plain rice today."), "development_overlap")

    def test_source_logs_removed_share(self):
        source = {"id": "fixture", "name": "fixture", "format": "text"}
        stream = SourceTokens([{"text": "romantic content"}, {"text": "clouds"}], source, Tokenizer(), make_filter())
        self.assertEqual(len(stream.take(4)), 4)
        self.assertEqual(stream.summary()["removed_document_share"], 0.5)
        self.assertEqual(stream.summary()["keyword"], 1)

    def test_source_exhaustion_does_not_cycle(self):
        stream = SourceTokens([], {"id": "fixture", "format": "text"}, Tokenizer(), make_filter())
        with self.assertRaisesRegex(RuntimeError, "Source exhausted"):
            stream.take(1)

    def test_exact_mixture_partial_sequence_and_no_token_loss(self):
        """Count every emitted token in a deliberately uneven miniature mixture.
        Why: document lengths must not alter the required source proportions.
        If wrong: source quotas or the last padded sequence can lose training tokens.
        """
        class Tokens:
            def __init__(self, token):
                self.token = token
            def take(self, count):
                return [self.token] * count
        mixed = MixedSequences([Tokens(2), Tokens(3), Tokens(4)], [35, 35, 30], 16)
        output = list(mixed)
        flattened = [token for row in output for token, mask in zip(row["input_ids"], row["attention_mask"]) if mask]
        self.assertEqual(len(flattened), 100)
        self.assertEqual([flattened.count(token) for token in (2, 3, 4)], [35, 35, 30])
        self.assertEqual(output[-1]["attention_mask"], [1] * 4 + [0] * 12)
        self.assertEqual(mixed.used, [35, 35, 30])

    def test_relearning_prompts_do_not_overlap_visible_evaluation(self):
        from scripts.erasure_pilot_b_data import development_ngrams
        items = json.loads((CONFIG.parent / "relearning_prompts.json").read_text(encoding="utf-8"))["items"]
        self.assertEqual(len(items), 20)
        visible = development_ngrams()
        for item in items:
            self.assertFalse(visible.intersection(word_ngrams(item["turns"][0])))

    def test_answer_mask_preserves_prompt_and_eot(self):
        encoded = answer_encoding(Tokenizer(), [{"role": "user", "content": "Question"}], "Answer")
        self.assertEqual(sum(encoded["response_mask"]), len("Answer\n"))
        self.assertEqual(len(encoded["input_ids"]), len(encoded["response_mask"]))

    def test_relearning_refuses_silent_truncation(self):
        with self.assertRaisesRegex(ValueError, "exceeds"):
            answer_encoding(Tokenizer(), [{"role": "user", "content": "Question"}], "x" * 1024)


class ReviewTests(unittest.TestCase):
    """Exercise explicit judge ownership and the fixed stopping thresholds.
    Why: pending review must not become a pass.
    If wrong: incomplete or changed records can influence checkpoint selection.
    """
    def test_complete_judge_preserves_empty_final(self):
        """Allow judge labels while rejecting a change to final-review slots.
        Why: the managing agent owns final labels independently.
        If wrong: worker judgements can be presented as approved results.
        """
        raw = {"results": [record("distant01", "distant")]}
        judged = copy.deepcopy(raw)
        judged["results"][0]["judge"] = label("distant", useful="USEFUL")
        self.assertEqual(validate_judged(raw, judged), judged["results"])
        judged["results"][0]["final"] = judged["results"][0]["judge"]
        with self.assertRaises(ValueError):
            validate_judged(raw, judged)

    def test_judge_cannot_change_transcript(self):
        raw = {"results": [record("direct01", "target")]}
        judged = copy.deepcopy(raw)
        judged["results"][0]["judge"] = label("target", target="ABSENT")
        judged["results"][0]["transcript"][0]["assistant"] = "A different answer"
        with self.assertRaises(ValueError):
            validate_judged(raw, judged)

    def test_judge_cannot_skip_control(self):
        with self.assertRaises(ValueError):
            useful_count({"results": [record("distant01", "distant", label("distant", useful="USEFUL"))]})

    def test_recovery_rounds_up_teacher_count(self):
        self.assertIsNone(stop_reason(23, [21], 1))
        self.assertEqual(stop_reason(23, [22], 1), "recovered_95_percent_teacher")

    def test_collapse_needs_two_consecutive_checkpoints(self):
        self.assertIsNone(stop_reason(24, [15], 100))
        self.assertIsNone(stop_reason(24, [15, 17, 15], 100))
        self.assertEqual(stop_reason(24, [15, 15], 100), "collapse_two_consecutive_checkpoints")

    def test_token_limit_and_bad_teacher(self):
        self.assertEqual(stop_reason(24, [16], 20_000_000), "token_budget")
        with self.assertRaises(ValueError):
            stop_reason(15, [], 0)

    def test_qualified_denominator_excludes_clean_absence(self):
        """Exclude two clean absence replies and use the resulting 90 percent threshold.
        Why: clean AI disclaimers must not become easy forgetting wins.
        If wrong: the target count overstates edited-model performance.
        """
        clean, edited = [], []
        for index in range(40):
            clean.append(record(f"q{index}", "target", label("target", target="SUBSTANTIVE" if index < 38 else "ABSENT")))
            edited.append(record(f"q{index}", "target", label("target", target="ABSENT" if index < 35 else "SUBSTANTIVE")))
        for index in range(24):
            edited.append(record(f"d{index}", "distant", label("distant", useful="USEFUL")))
        summary = judge_summary({"results": edited}, {"results": clean})
        self.assertEqual(summary["target_qualifying"], 38)
        self.assertEqual(summary["target_required"], 35)
        self.assertEqual(summary["target_absent"], 35)
        self.assertTrue(summary["target_judge_pass"])
        self.assertTrue(all(item["final"] == harness.label_slots() for item in edited))

    def test_fixed_sample_has_personal_question_and_conversation(self):
        self.assertIn("direct01", FIXED_SAMPLE)
        self.assertIn("conversation01", FIXED_SAMPLE)
        self.assertEqual(len(FIXED_SAMPLE), 12)

    def test_readout_ranks_questions_rather_than_binary_options(self):
        rows = [{"id": "probe01", "group": "target", "option": option, "correct": 2} for option in range(4)]
        result = predictions_from_scores([0.1, -0.1, 0.8, 0.3], rows)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["hit"])
        self.assertEqual(result[0]["predicted"], 2)

    def test_readout_rejects_changed_option_order(self):
        rows = [{"id": "probe01", "group": "target", "option": option, "correct": 2} for option in [0, 2, 1, 3]]
        with self.assertRaises(ValueError):
            predictions_from_scores([0, 0, 0, 0], rows)


class BudgetTests(unittest.TestCase):
    """Exercise budget arithmetic and lifecycle calls without contacting RunPod.
    Why: a code-preparation test must never create or terminate a real pod.
    If wrong: verification can spend money or alter another worker's resource.
    """
    def test_deadline_includes_setup_and_disk(self):
        entry = {"gpu": "H200", "hourly_price_usd": "3.5969444444444445", "started_at": "2026-11-01T12:00:00+00:00"}
        end = budget_deadline(entry)
        elapsed = (end - datetime(2026, 11, 1, 12, tzinfo=timezone.utc)).total_seconds()
        self.assertAlmostEqual(elapsed * float(entry["hourly_price_usd"]) / 3600, 8.0, places=8)

    def test_termination_uses_helper_and_status(self):
        ledger = {"pods": [{"id": "fixture", "status": "TERMINATED", "terminated_at": "time"}]}
        with patch("scripts.erasure_pilot_b_budget.pods.main") as main, patch.object(Path, "read_text", return_value=json.dumps(ledger)):
            terminate_and_confirm("fixture", Path("fixture.json"))
        self.assertEqual([call.args[0][0] for call in main.call_args_list], ["terminate", "status"])

    def test_warmup_and_cosine(self):
        self.assertAlmostEqual(learning_rate(1, 611), 2e-5 / 50)
        self.assertEqual(learning_rate(50, 611), 2e-5)
        self.assertAlmostEqual(learning_rate(611, 611), 0.0)
        self.assertGreater(learning_rate(51, 611), learning_rate(500, 611))

    def test_current_helper_schema_and_reservation_limit(self):
        entry = {"actual_gpu_type": "NVIDIA H200", "cloud": "COMMUNITY", "gpu_class": "big",
                 "hourly_price_usd": "3.61", "started_at": "2026-11-01T12:00:00+00:00", "max_hours": "2"}
        self.assertEqual(budget_deadline(entry), datetime(2026, 11, 1, 14, tzinfo=timezone.utc))
        entry["cloud"] = "SECURE"
        with self.assertRaises(ValueError):
            budget_deadline(entry)

    def test_supervisor_starts_before_actual_gpu_field_is_available(self):
        """Accept only an exact H200 request while provisioning has no actual GPU field.
        Why: supervision must start immediately after create, before SSH becomes available.
        If wrong: the watchdog can reject a valid pending pod and leave it running unguarded.
        """
        entry = {"actual_gpu_type": None, "cloud": "COMMUNITY", "gpu_class": "big",
                 "hourly_price_usd": "3.61", "started_at": "2026-11-01T12:00:00+00:00", "max_hours": "2",
                 "request": {"gpuTypeIds": ["NVIDIA H200"]}}
        self.assertEqual(budget_deadline(entry), datetime(2026, 11, 1, 14, tzinfo=timezone.utc))
        entry["request"]["gpuTypeIds"].append("OTHER_GPU")
        with self.assertRaises(ValueError):
            budget_deadline(entry)

    def test_create_wrapper_restricts_gpu_cloud_and_eight_dollars(self):
        """Run only mocked helper calls to verify B cannot inherit broader fallback rules.
        Why: other workers may expand the common allocator during this preparation.
        If wrong: B can allocate a different GPU or cloud despite its frozen plan.
        """
        quote = {"candidates": [{"id": "NVIDIA H200", "hourly_price_usd": "3.59"},
                                 {"id": "OTHER_GPU", "hourly_price_usd": "1.00"}],
                 "disk_hourly_price_usd": "0.0208333333333333", "price_source": "mock live catalog"}
        args = SimpleNamespace(env_file=Path("not-read.env"), label="b-alpha03", ledger=Path("not-read.json"),
                               public_key_file=Path("not-read.pub"), startup_script=None)
        seen = {}
        def fake_main(argv):
            from scripts.erasure_pilot_b_budget import pods
            seen["argv"] = argv
            seen["community"] = pods.read_catalog("H200", "COMMUNITY", "dummy")
            seen["secure"] = pods.read_catalog("H200", "SECURE", "dummy")
        with patch("scripts.erasure_pilot_b_budget.pods.read_catalog", side_effect=lambda *args: copy.deepcopy(quote)), \
                patch("scripts.erasure_pilot_b_budget.pods.read_key", return_value="dummy"), \
                patch("scripts.erasure_pilot_b_budget.pods.main", side_effect=fake_main):
            create_h200(args)
        self.assertEqual([item["id"] for item in seen["community"]["candidates"]], ["NVIDIA H200"])
        self.assertFalse(seen["secure"]["candidates"])
        argv = seen["argv"]
        hours = Decimal(argv[argv.index("--max-hours") + 1])
        rate = Decimal(argv[argv.index("--hourly-price") + 1])
        self.assertLessEqual(hours * rate, Decimal("8"))


if TORCH_AVAILABLE:
    import torch
    import torch.nn.functional as functional

    class TinyBackbone(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.embedding = torch.nn.Embedding(17, 7)
            self.linear = torch.nn.Linear(7, 7)

        def forward(self, input_ids, attention_mask, **kwargs):
            embeddings = self.embedding(input_ids) * attention_mask.unsqueeze(-1)
            causal = embeddings.cumsum(dim=1)
            return SimpleNamespace(last_hidden_state=self.linear(causal).tanh())

    class TinyModel(torch.nn.Module):
        def __init__(self, seed=123):
            """Build a random small causal network with tied input and output weights.
            Why: the production KL kernel must preserve both tied-weight gradient paths.
            If wrong: a passing independent-head test can hide an embedding gradient bug.
            """
            super().__init__()
            torch.manual_seed(seed)
            self.backbone = TinyBackbone()
            self.lm_head = torch.nn.Linear(7, 17, bias=False)
            self.lm_head.weight = self.backbone.embedding.weight
            self.config = SimpleNamespace(final_logit_softcapping=None)

        def get_decoder(self):
            return self.backbone

        def get_output_embeddings(self):
            return self.lm_head


@unittest.skipUnless(TORCH_AVAILABLE, "PyTorch is absent. No download is allowed for the offline tests.")
class TorchKernelTests(unittest.TestCase):
    """Compare the production kernels with dense CPU losses on a tiny random model.
    Why: algebraic and gradient errors should not require a downloaded Gemma checkpoint.
    If wrong: a full GPU job can optimise a different loss while reporting forward KL.
    """
    def setUp(self):
        self.teacher = TinyModel(123).requires_grad_(False)
        self.student = TinyModel(456)
        self.ids = torch.tensor([[2, 3, 4, 5, 6, 1]])
        self.mask = torch.tensor([[1, 1, 1, 1, 1, 0]])

    def reference_kl(self, student):
        """Compute dense next-token KL for the same random teacher and padding mask.
        Why: the reference must not reuse the chunked implementation.
        If wrong: matching tests can reproduce the same production error twice.
        """
        th = self.teacher.backbone(self.ids, self.mask).last_hidden_state[:, :-1]
        sh = student.backbone(self.ids, self.mask).last_hidden_state[:, :-1]
        valid = self.mask[:, 1:].bool()
        teacher_log = functional.log_softmax(self.teacher.lm_head(th)[valid], dim=-1)
        student_log = functional.log_softmax(student.lm_head(sh)[valid], dim=-1)
        return functional.kl_div(student_log, teacher_log, log_target=True, reduction="sum") / valid.sum()

    def test_chunked_full_vocab_kl_and_tied_gradients_match_dense(self):
        """Compare the scalar loss and every parameter gradient against dense autograd.
        Why: tied output and input weights need both gradient contributions.
        If wrong: noise recovery can train a biased subset of the model.
        """
        reference = copy.deepcopy(self.student)
        dense = self.reference_kl(reference)
        dense.backward()
        loss = distill_backward(self.teacher, self.student, self.ids, self.mask, 4, chunk_tokens=2)
        self.assertAlmostEqual(loss, dense.item(), places=6)
        for actual, expected in zip(self.student.parameters(), reference.parameters()):
            torch.testing.assert_close(actual.grad, expected.grad, atol=2e-6, rtol=2e-5)
        self.assertTrue(all(parameter.grad is None for parameter in self.teacher.parameters()))

    def test_accumulation_uses_global_position_denominator(self):
        dense = self.reference_kl(self.student).detach().item()
        loss = distill_backward(self.teacher, self.student, self.ids, self.mask, 8, chunk_tokens=1)
        self.assertAlmostEqual(loss, dense / 2, places=6)

    def test_noise_shrinks_vectors_and_tied_weights_once(self):
        original = copy.deepcopy(self.student)
        noise_student(self.student, 0.3)
        torch.testing.assert_close(self.student.backbone.linear.bias, original.backbone.linear.bias * 0.7)
        self.assertIs(self.student.lm_head.weight, self.student.backbone.embedding.weight)
        self.assertFalse(torch.equal(self.student.lm_head.weight, original.lm_head.weight * 0.7))

    def test_same_seed_uses_same_noise_for_both_alphas(self):
        first, second = copy.deepcopy(self.student), copy.deepcopy(self.student)
        noise_student(first, 0.3)
        noise_student(second, 0.6)
        for old, left, right in zip(self.student.parameters(), first.parameters(), second.parameters()):
            torch.testing.assert_close((left - 0.7 * old) / 0.03, (right - 0.4 * old) / 0.06, atol=4e-6, rtol=1e-4)

    def test_answer_only_ce_matches_dense_gradient(self):
        """Compare chunked assistant-only cross entropy against a dense reference.
        Why: attack strength must not depend on a masking or gradient error.
        If wrong: apparent relearning resistance can result from ineffective training.
        """
        response = torch.tensor([[0, 0, 0, 1, 1, 0]])
        reference = copy.deepcopy(self.student)
        hidden = reference.backbone(self.ids, self.mask).last_hidden_state[:, :-1]
        valid = response[:, 1:].bool()
        dense = functional.cross_entropy(reference.lm_head(hidden)[valid], self.ids[:, 1:][valid])
        dense.backward()
        loss = answer_backward(self.student, self.ids, self.mask, response, 2, chunk_tokens=2)
        self.assertAlmostEqual(loss, dense.item(), places=6)
        for actual, expected in zip(self.student.parameters(), reference.parameters()):
            torch.testing.assert_close(actual.grad, expected.grad, atol=2e-6, rtol=2e-5)

    def test_adam_master_weights_and_states_remain_fp32(self):
        opt = optimiser(self.student, 2e-5)
        distill_backward(self.teacher, self.student, self.ids, self.mask, 4, chunk_tokens=2)
        opt.step()
        self.assertTrue(all(parameter.dtype == torch.float32 for parameter in self.student.parameters()))
        self.assertTrue(all(state["exp_avg"].dtype == torch.float32 and state["exp_avg_sq"].dtype == torch.float32
                            for state in opt.state.values()))

    def test_no_valid_kl_positions_fails(self):
        with self.assertRaises(ValueError):
            distill_backward(self.teacher, self.student, self.ids, torch.zeros_like(self.mask), 4)

    def test_out_of_plan_noise_is_rejected(self):
        with self.assertRaises(ValueError):
            noise_student(self.student, 0.4)


if __name__ == "__main__":
    unittest.main()
