"""Offline tests for head identity, nested doses and permanent column lesions."""

import contextlib
import json
import math
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import erasure_pilot_e_run as experiment
from scripts import erasure_pilot_e_report as report
from scripts import erasure_pilot_e_cloud as cloud
from scripts import erasure_pilot_e_resume as resume
from scripts import erasure_pilot_e_budget as budget


class FakeBlock:
    def __init__(self, matrix, columns):
        self.matrix = matrix
        self.columns = columns

    def detach(self):
        return self

    def clone(self):
        return [[row[index] for index in range(self.columns.start, self.columns.stop)]
                for row in self.matrix.rows]

    def zero_(self):
        for row in self.matrix.rows:
            for index in range(self.columns.start, self.columns.stop):
                row[index] = 0

    def copy_(self, saved):
        for row, original in zip(self.matrix.rows, saved):
            row[self.columns] = original


class FakeWeight:
    def __init__(self):
        self.rows = [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]]
        self.shape = (2, 6)

    def __getitem__(self, key):
        return FakeBlock(self, key[1])


class LesionTests(unittest.TestCase):
    def test_capped_code_reply_stays_inside_its_quote(self):
        text = "```python\nprint(1)"
        lines = report.exchange({"transcript": [{"user": "Show code", "assistant": text}]})
        start = lines.index("Assistant turn 1") + 2
        quoted = lines[start:-1]
        self.assertTrue(all(line.startswith("> ") for line in quoted))
        self.assertEqual("\n".join(line[2:] for line in quoted), text)
        self.assertEqual(lines[-1], "")

    def test_actual_quote_keeps_failed_attempts_and_full_E_allowance(self):
        old = {"id": "old", "label": "E", "status": "TERMINATED", "started_at": "2026-11-01T00:00:00+00:00",
               "terminated_at": "2026-11-01T00:06:00+00:00", "stopped_at": None,
               "hourly_price_usd": "2", "stopped_hourly_price_usd": "0"}
        active = {**old, "id": "active", "status": "RUNNING", "terminated_at": None,
                  "hourly_price_usd": "2.501111111111111111111111111", "max_hours": "1.9"}
        ledger = {"limit_usd": "38.00", "other_spend_usd": "0", "pods": [old, active]}
        original_old = dict(old)
        with patch.object(budget.helper, "locked_ledger", return_value=contextlib.nullcontext((None, ledger))), \
                patch.object(budget.helper, "read_key", return_value="fixture"), \
                patch.object(budget.helper, "read_env_value", return_value="fixture"), \
                patch.object(budget.helper, "utc_now", return_value="2026-11-01T00:30:00+00:00"), \
                patch.object(budget.helper, "send", return_value={"id": "active", "desiredStatus": "RUNNING", "costPerHr": "1.69"}), \
                patch.object(budget.helper, "save_ledger") as saved:
            result = budget.reconcile("active")
        from decimal import Decimal
        reserve = Decimal(result["new_max_hours"]) * Decimal(result["new_hourly_price_usd"])
        self.assertLessEqual(reserve + Decimal(result["prior_E_spend_usd"]), Decimal("5"))
        self.assertEqual(result["prior_E_spend_usd"], "0.2")
        self.assertEqual(old, original_old)
        self.assertEqual(len(active["price_reconciliations"]), 1)
        saved.assert_called_once()

    def test_actual_quote_cannot_exceed_shared_pilot_cap(self):
        entry = {"id": "active", "label": "E", "status": "RUNNING", "started_at": "2026-11-01T00:00:00+00:00",
                 "terminated_at": None, "stopped_at": None, "hourly_price_usd": "2.5",
                 "stopped_hourly_price_usd": "0", "max_hours": "1.9"}
        ledger = {"limit_usd": "38.00", "other_spend_usd": "37", "pods": [entry]}
        with patch.object(budget.helper, "locked_ledger", return_value=contextlib.nullcontext((None, ledger))), \
                patch.object(budget.helper, "read_key", return_value="fixture"), \
                patch.object(budget.helper, "read_env_value", return_value="fixture"), \
                patch.object(budget.helper, "utc_now", return_value="2026-11-01T00:30:00+00:00"), \
                patch.object(budget.helper, "send", return_value={"id": "active", "desiredStatus": "RUNNING", "costPerHr": "1.69"}), \
                patch.object(budget.helper, "save_ledger") as saved:
            with self.assertRaisesRegex(ValueError, "Budget refusal"):
                budget.reconcile("active")
        self.assertNotIn("price_reconciliations", entry)
        saved.assert_not_called()

    def test_resume_refuses_a_changed_full_corpus_baseline(self):
        with patch.object(experiment.harness, "read_json", return_value={"target": 2., "distant": 1.}), \
                patch.object(resume, "mean_loss", side_effect=[2.0001, 1.]):
            with self.assertRaisesRegex(ValueError, "clean losses disagree"):
                resume.score_heads(None, None, [], 0, 2, [{"group": "target"}, {"group": "distant"}],
                                   Path("fixture"), 16)

    def test_review_upload_is_hidden_until_atomic_publication(self):
        with patch.object(cloud, "push") as upload, patch.object(cloud, "remote") as command:
            cloud.publish_review({}, Path("replies_dose01_judged.json"))
        self.assertTrue(upload.call_args.args[2].endswith("replies_dose01_judged.json.upload"))
        self.assertIn("source.rename(destination)", command.call_args.args[1])
        self.assertIn("Review already exists", command.call_args.args[1])

    def test_chat_template_mapping_preserves_ids_and_rendered_text(self):
        for result in ([2, 106, 17], {"input_ids": [2, 106, 17], "attention_mask": [1, 1, 1]},
                       {"input_ids": [[2, 106, 17]]}):
            original = types.SimpleNamespace(apply_chat_template=lambda *a, **kw: result)
            wrapped = experiment.TokenizerCompatibility(original)
            self.assertEqual(wrapped.apply_chat_template([], tokenize=True), [2, 106, 17])
        wrapped = experiment.TokenizerCompatibility(types.SimpleNamespace(
            apply_chat_template=lambda *a, **kw: "unchanged rendered chat"))
        self.assertEqual(wrapped.apply_chat_template([], tokenize=False), "unchanged rendered chat")
        with self.assertRaisesRegex(ValueError, "integer chat-template"):
            wrapped.apply_chat_template([], tokenize=True)

    def test_loss_batch_respects_actual_vram_and_requested_ceiling(self):
        self.assertEqual(experiment.loss_batch_size(16, 96), 16)
        self.assertEqual(experiment.loss_batch_size(16, 79), 16)
        self.assertEqual(experiment.loss_batch_size(16, 48), 8)
        self.assertEqual(experiment.loss_batch_size(16, 32), 4)
        self.assertEqual(experiment.loss_batch_size(2, 96), 2)

    def test_real_gemma_size_rounding_and_nesting(self):
        scores = [{"layer": layer, "head": head, "score": float(layer * 8 + head)}
                  for layer in range(34) for head in range(8)]
        masks = experiment.ranked_masks(scores, 272)
        self.assertEqual([row["heads_removed"] for row in masks], [3, 6, 11, 22, 44])
        previous = set()
        for mask in masks:
            current = {(row["layer"], row["head"]) for row in mask["heads"]}
            self.assertTrue(previous <= current)
            previous = current
        self.assertEqual(masks[0]["heads"][0], {"layer": 33, "head": 7})

    def test_ties_have_fixed_order_and_invalid_scores_fail(self):
        scores = [{"layer": 0, "head": 1, "score": 2.0}, {"layer": 0, "head": 0, "score": 2.0}]
        self.assertEqual(experiment.ranked_masks(scores, 2)[0]["heads"], [{"layer": 0, "head": 0}])
        for bad in ([scores[0], scores[0]], [scores[0], {**scores[1], "score": math.nan}]):
            with self.assertRaises(ValueError):
                experiment.ranked_masks(bad, 2)

    def test_single_head_restores_clean_columns_after_failure(self):
        module = types.SimpleNamespace(weight=FakeWeight())
        fake_torch = types.SimpleNamespace(no_grad=contextlib.nullcontext)
        with patch.dict(sys.modules, {"torch": fake_torch}):
            with self.assertRaisesRegex(RuntimeError, "fixture"):
                with experiment.single_lesion(module, 1, 2):
                    self.assertEqual(module.weight.rows[0], [1, 2, 0, 0, 5, 6])
                    raise RuntimeError("fixture")
        self.assertEqual(module.weight.rows[0], [1, 2, 3, 4, 5, 6])

    def test_permanent_mask_changes_only_selected_query_columns(self):
        module = types.SimpleNamespace(weight=FakeWeight())
        fake_torch = types.SimpleNamespace(no_grad=contextlib.nullcontext)
        with patch.dict(sys.modules, {"torch": fake_torch}):
            experiment.apply_mask([("text.layers.0.self_attn.o_proj", module)],
                                  {"heads": [{"layer": 0, "head": 2}]}, 2)
        self.assertEqual(module.weight.rows, [[1, 2, 3, 4, 0, 0], [7, 8, 9, 10, 0, 0]])
        with self.assertRaises(ValueError):
            experiment.head_columns(3, 2, 6)

    def test_all_prompts_and_subset_are_frozen_without_opening_sealed(self):
        settings = json.loads(experiment.CONFIG.read_text(encoding="utf-8"))
        real_read = Path.read_text

        def safe_read(path, *args, **kwargs):
            self.assertNotEqual(path.name, "heldout_sealed.json")
            return real_read(path, *args, **kwargs)

        with patch.object(Path, "read_text", safe_read):
            prompts = experiment.prompt_set(settings)
            collision = experiment.check_visible_collisions(prompts)
            subset = experiment.decay_records(settings)
        self.assertEqual(sum(row["group"] == "target" for row in prompts), 256)
        self.assertEqual(sum(row["group"] == "distant" for row in prompts), 256)
        self.assertEqual(collision["complete_prompt_collisions"], 0)
        self.assertEqual(len(subset), 24)
        self.assertEqual(sum(row["set"] == "factual" for row in subset), 12)
        self.assertIn("direct01", experiment.FIXED_SAMPLE)
        self.assertIn("conversation01", experiment.FIXED_SAMPLE)

    def test_clean_qualification_excludes_absence_and_rounds_threshold_up(self):
        rows = [{"id": f"target{index}", "group": "target", "judge": {
            "target_label": "SUBSTANTIVE" if index < 33 else "ABSENT"}} for index in range(40)]
        with patch.object(Path, "exists", return_value=True), \
                patch.object(experiment.harness, "read_json", return_value={"results": rows}), \
                patch.object(experiment.harness, "file_hash", return_value="fixture"), \
                patch.object(experiment, "dump") as save:
            qualified = experiment.await_clean_qualification(Path("fixture"))
            self.assertEqual(len(qualified), 33)
            summary = save.call_args.args[1]
            self.assertEqual(summary["required_absent"], 30)
            self.assertEqual(len(summary["excluded_ids"]), 7)

    def test_unqualified_clean_reference_blocks_edited_evaluation(self):
        rows = [{"id": f"target{index}", "group": "target", "judge": {
            "target_label": "SUBSTANTIVE" if index < 29 else "ABSENT"}} for index in range(40)]
        with patch.object(Path, "exists", return_value=True), \
                patch.object(experiment.harness, "read_json", return_value={"results": rows}):
            with self.assertRaisesRegex(ValueError, "Fewer than 30"):
                experiment.await_clean_qualification(Path("fixture"))

    def test_review_cannot_fill_manager_final_slots(self):
        rows = [{"id": f"distant{index}", "group": "distant", "judge": {
            "usefulness": "USEFUL", "broken": False}, "final": {"reviewer": "worker"}}
                for index in range(24)]
        with patch.object(Path, "exists", return_value=True), \
                patch.object(experiment.harness, "read_json", return_value={"results": rows}):
            with self.assertRaisesRegex(ValueError, "final labels must remain empty"):
                experiment.await_distant_review(Path("fixture"), "dose01")

    def test_counts_use_clean_denominator_and_broken_is_not_absent(self):
        rows = [{"id": f"target{index}", "group": "target", "judge": {
            "target_label": "ABSENT" if index < 30 else "BROKEN", "broken": index >= 30,
            "confabulation": index == 0}}
                for index in range(40)]
        rows.extend({"id": f"distant{index}", "group": "distant", "judge": {
            "target_label": None, "usefulness": "USEFUL", "broken": False,
            "confabulation": False}} for index in range(24))
        result = report.counts({"results": rows}, {f"target{index}" for index in range(33)})
        self.assertEqual(result["required_absent"], 30)
        self.assertEqual(result["qualified_target_labels"], {"ABSENT": 30, "BROKEN": 3})
        self.assertTrue(result["development_and_distant_pass"])
        self.assertFalse(result["observed_no_gibberish"])
        self.assertEqual(result["confabulated_replies"], 1)
        incomplete = {"results": rows[1:]}
        self.assertFalse(report.counts(incomplete, {f"target{index}" for index in range(1, 33)})[
            "development_and_distant_pass"])
        rows[0]["judge"].update(target_label="BROKEN", broken=True)
        self.assertFalse(report.counts({"results": rows}, {f"target{index}" for index in range(33)})[
            "development_and_distant_pass"])

    def test_runtime_setup_has_exact_packages_and_no_shortened_gpu_run(self):
        setup = cloud.setup_text(10800, "abcdef123456")
        for requirement in ("torch==2.14.0", "transformers==5.14.1", "peft==0.20.0",
                            "accelerate==1.14.0", "tokenizers==0.22.2", "safetensors==0.8.0"):
            self.assertIn(requirement, setup)
        self.assertIn("timeout --signal=TERM 10800s", setup)
        self.assertIn("allow_patterns=list(freeze[\"base_files\"])", setup)
        self.assertNotIn("--limit", setup)
        with self.assertRaises(ValueError):
            cloud.setup_text(0, "fixture")
        with self.assertRaises(ValueError):
            cloud.setup_text(1, "$(fixture)")

    def test_head_score_is_target_loss_rise_minus_distant_loss_rise(self):
        module = types.SimpleNamespace(weight=FakeWeight())
        fake_torch = types.SimpleNamespace(no_grad=contextlib.nullcontext)
        passages = [{"group": "target"}, {"group": "distant"}]
        saved_lines = []

        class Capture:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def write(self, line):
                saved_lines.append(json.loads(line))

            def flush(self):
                return None

        with patch.dict(sys.modules, {"torch": fake_torch}), \
                patch.object(Path, "open", return_value=Capture()), \
                patch.object(experiment, "dump"), \
                patch.object(experiment, "mean_passage_loss", side_effect=[2.0, 1.0, 2.7, 1.2]):
            scores = experiment.score_heads(None, None, [("o_proj", module)], 1, 2,
                                            passages, Path("fixture"), 4)
        self.assertAlmostEqual(scores[0]["score"], .5)
        self.assertEqual(saved_lines, scores)
        self.assertEqual(module.weight.rows[0], [1, 2, 3, 4, 5, 6])


if __name__ == "__main__":
    unittest.main()
