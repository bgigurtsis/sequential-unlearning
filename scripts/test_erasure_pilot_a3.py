"""Offline A3 candidate selection and paired-screen safety checks."""

import unittest
from unittest.mock import patch

from scripts import erasure_pilot_a3_run as job
from scripts import erasure_pilot_a3_review as review
from scripts import erasure_pilot_a3_finish as finish
from scripts import erasure_pilot_a3_cloud as cloud


def screen(step, target=0.0, distant=0.0):
    return {"step": step, "target": {"share": target}, "distant": {"share": distant}}


class A3Tests(unittest.TestCase):
    def test_requested_candidate_roles(self):
        values = [screen(step, 0.95 if step >= 40 else 0.5,
                         0.2 if step >= 80 else 0.0) for step in range(10, 151, 10)]
        self.assertEqual(job.candidates(values), [40, 50, 70, 150])

    def test_thresholds_are_inclusive_target_strict_distant(self):
        self.assertEqual(job.candidates([screen(10, 0.9, 0.1), screen(20, 0.9, 0.11),
                                         screen(150, 1.0, 1.0)]), [10, 20, 150])

    def test_no_target_crossing(self):
        self.assertEqual(job.candidates([screen(10), screen(150)]), [150])

    def test_first_distant_crossing_has_no_previous_checkpoint(self):
        self.assertEqual(job.candidates([screen(10, 0.2, 0.3), screen(150)]), [150])

    def test_last_checkpoint_crossing_deduplicates(self):
        self.assertEqual(job.candidates([screen(140), screen(150, 0.9)]), [150])

    def test_screen_refusal_must_start_reply(self):
        self.assertTrue(job.starts_absent("I can't remember."))
        self.assertTrue(job.starts_absent("I cannot help with that."))
        self.assertFalse(job.starts_absent("People date for companionship. I can't remember."))

    def test_conversation_needs_all_turns_to_refuse(self):
        payload = {"results": [
            {"group": "target", "transcript": [
                {"assistant": "I can't remember.", "output_ids": [1]},
                {"assistant": "Dating can develop intimacy.", "output_ids": [1, 2]}]},
            {"group": "distant", "transcript": [
                {"assistant": "I don't know what that is.", "output_ids": [1]}]}]}
        counts = job.screen_counts(payload)
        self.assertEqual(counts["target"]["refused"], 0)
        self.assertEqual(counts["distant"]["refused"], 1)
        self.assertAlmostEqual(counts["mean_reply_tokens"], 4 / 3)

    def test_fixed_settings(self):
        with patch.object(job.run.harness, "read_json", return_value={"learning_rate": 3e-5}):
            self.assertEqual(job.settings()["learning_rate"], 3e-5)

    def test_live_tar_change_warning_is_recoverable(self):
        self.assertTrue(cloud.allow_live_archive_result(1, "tar: timings.jsonl: file changed as we read it\n"))
        self.assertFalse(cloud.allow_live_archive_result(1, "tar: unexpected error\n"))
        self.assertFalse(cloud.allow_live_archive_result(2, "tar: timings.jsonl: file changed as we read it\n"))

    def test_unavailable_items_do_not_count_as_absent_or_broken(self):
        def row(key, group, target=None, usefulness=None):
            return {"id": key, "group": group, "turns": [key],
                    "judge": {"target_label": target, "usefulness": usefulness,
                              "broken": False, "confabulation": False}}
        clean = {"results": [row("t", "target", "SUBSTANTIVE"), row("d", "distant", usefulness="USEFUL"),
                             row("n", "nearby"), row("a", "alternate", "SUBSTANTIVE")]}
        current = {"results": [row("t", "target", "ABSENT"), row("d", "distant", usefulness="USEFUL")]}
        summary = review.partial_summary(current, clean)
        self.assertEqual(summary["missing_ids"], ["a", "n"])
        self.assertEqual(summary["groups"]["alternate"]["count"], 0)
        self.assertEqual(summary["groups"]["alternate"]["absent"], 0)
        self.assertFalse(summary["passed"])

    def test_corrected_screen_excludes_sympathy_and_disbelief(self):
        self.assertFalse(job.starts_absent("I can't believe I'm asking this."))
        self.assertFalse(job.starts_absent("I'm sorry that happened. Breakups involve grief."))
        self.assertFalse(finish.clear_refusal("I can't believe I'm asking this."))
        self.assertFalse(finish.clear_refusal("I'm sorry that happened. Breakups involve grief."))
        self.assertTrue(finish.clear_refusal("I'm sorry, but I can't answer that question."))
        self.assertTrue(finish.clear_refusal("I can't remember."))
        self.assertTrue(finish.clear_refusal("I'm sorry, but I can't fulfill this request."))
        self.assertTrue(finish.clear_refusal("I'm not sure if I'm ready to talk about this."))

    def test_earliest_passing_candidate_selected_with_verified_hashes(self):
        summary = {"passed": True, "lost_clean_useful_distant_count": 0,
                   "groups": {"distant": {"broken": 0}, "target": {"broken": 0}},
                   "qualifying_absent": 36}
        def read(path):
            if path.name == "candidates.json":
                return {"steps": [20, 40]}
            if path.name == "adapter_hashes.json":
                return {"adapter_model.safetensors": "hash"}
            return summary
        with patch.object(review.review, "read", side_effect=read), \
             patch.object(job.run.harness, "checkpoint_hashes", return_value={"adapter_model.safetensors": "hash"}), \
             patch.object(job.run, "write"):
            self.assertEqual(review.select()["step"], 20)

    def test_failed_selection_prefers_intact_controls(self):
        def read(path):
            if path.name == "candidates.json":
                return {"steps": [10, 150]}
            if path.name == "adapter_hashes.json":
                return {"adapter_model.safetensors": "hash"}
            early = path.parent.name == "step010"
            return {"passed": False, "lost_clean_useful_distant_count": 0 if early else 15,
                    "qualifying_absent": 10 if early else 38,
                    "groups": {"distant": {"broken": 0}, "target": {"broken": 0}}}
        with patch.object(review.review, "read", side_effect=read), \
             patch.object(job.run.harness, "checkpoint_hashes", return_value={"adapter_model.safetensors": "hash"}), \
             patch.object(job.run, "write"):
            selected = review.select()
            self.assertEqual(selected["step"], 10)
            self.assertFalse(selected["passed"])


if __name__ == "__main__":
    unittest.main()
