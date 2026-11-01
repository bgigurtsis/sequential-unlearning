"""Download-free CPU checks of feature selection and error-preserving clamps."""

import ast
import json
import math
import socket
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from scripts.erasure_pilot_f_runtime import TokenizerCompatibility, preserved_residual, scalar_clamp, select_features
from scripts.erasure_pilot_f_review import append_reviewed_items, merge_review, partial_report, review_decision, validate_judges
from scripts import erasure_pilot_eval as harness
from scripts import erasure_pilot_f_launch as launch
from scripts import erasure_pilot_f_control as control
from scripts import runpod_pilot as helper
from scripts.erasure_pilot_f_judge_clean import NOTES, transcript_content


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.network = patch.object(socket, "socket", side_effect=AssertionError("No network in CPU tests"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_error_preserved_in_non_dictionary_dimension(self):
        residual = [5.0, 9.0, 123.0]
        old = [2.0, 3.0]
        decoder = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        new = [-8.0, 3.0]
        edited = preserved_residual(residual, old, new, decoder)
        self.assertEqual(edited, [-5.0, 9.0, 123.0])
        original_error = [residual[i] - sum(old[j] * decoder[j][i] for j in range(2)) for i in range(3)]
        explicit = [sum(new[j] * decoder[j][i] for j in range(2)) + original_error[i] for i in range(3)]
        self.assertEqual(edited, explicit)

    def test_ladder_and_strict_jump_threshold(self):
        for k in [0, 1, 4, 16]:
            self.assertEqual(scalar_clamp(4.0, 2.0, 3.0, k), -k * 3.0)
            self.assertEqual(scalar_clamp(2.0, 2.0, 3.0, k), 0)
            self.assertEqual(scalar_clamp(1.0, 2.0, 3.0, k), 0)
            self.assertEqual(scalar_clamp(-1.0, -2.0, 3.0, k), 0)

    def test_selection_excludes_common_and_never_firing_latents(self):
        target = {"tokens": 100, "sum": [100., 90., 80., 0.],
                  "sumsq": [400., 300., 200., 0.], "active": [25, 30, 40, 0]}
        distant = {"tokens": 100, "sum": [0., 6., 5., 0.],
                   "sumsq": [0., 6., 5., 0.], "active": [0, 6, 5, 0]}
        rows = select_features(target, distant, count=2)
        self.assertEqual({row["feature"] for row in rows}, {0, 2})
        self.assertEqual(next(row for row in rows if row["feature"] == 0)["mean_active"], 4.)
        self.assertEqual(next(row for row in rows if row["feature"] == 2)["distant_frequency"], .05)

    def test_selection_uses_pooled_population_deviation(self):
        target = {"tokens": 4, "sum": [8.], "sumsq": [20.], "active": [4]}
        distant = {"tokens": 4, "sum": [0.], "sumsq": [0.], "active": [0]}
        row = select_features(target, distant, 1)[0]
        self.assertAlmostEqual(row["score"], 2 / math.sqrt(.5))
        with self.assertRaises(ValueError):
            select_features(target, distant, 20)

    def test_plan_constants_and_no_sealed_read(self):
        root = Path(__file__).resolve().parents[1]
        settings = json.loads((root / "config/erasure_pilot_v1/approach_f/settings.json").read_text())
        self.assertEqual(settings["layers"], [13, 20])
        self.assertEqual(settings["ladder"], [0, 1, 4, 16])
        self.assertEqual(settings["features_per_layer"], 20)
        self.assertEqual(settings["budget_usd"], 5)
        self.assertEqual(settings["gpu"], "mid")
        self.assertTrue(settings["preserve_error"])
        source = (root / "scripts/erasure_pilot_f_runtime.py").read_text()
        ast.parse(source)
        self.assertNotIn("heldout_sealed", source)
        self.assertNotIn("save_pretrained", source)
        self.assertNotIn("optimizer", source)

    def test_chat_template_mapping_preserves_exact_ids(self):
        class FakeTokenizer:
            def apply_chat_template(self, *args, **kwargs):
                return {"input_ids": [[2, 105, 77, 106]]}

        wrapped = TokenizerCompatibility(FakeTokenizer())
        self.assertEqual(wrapped.apply_chat_template([], tokenize=True), [2, 105, 77, 106])


class ReviewTests(unittest.TestCase):
    def test_partial_report_does_not_count_missing_replies_as_absent(self):
        clean = self.make_run()
        for row in clean["results"]:
            row["turns"] = ["Visitor question"]
            row["transcript"] = [{"user": "Visitor question", "assistant": "Clean reply"}]
        observed = json.loads(json.dumps(clean["results"][:1]))
        observed[0]["judge"]["target_label"] = "ABSENT"
        text, counts = partial_report(observed, clean, "k16", ["target0", "target1"], "Budget cutoff")
        self.assertEqual(counts["items_observed"], 1)
        self.assertEqual(counts["missing_items"], 85)
        self.assertEqual(counts["qualifying_absent"], 1)
        self.assertEqual(counts["pass_verdict"], "INCOMPLETE")
        self.assertIn("NOT GENERATED", text)

    def test_full_review_rejects_a_changed_assistant_reply(self):
        run = self.make_run()
        for row in run["results"]:
            row["turns"] = ["Visitor question"]
            row["transcript"] = [{"user": "Visitor question", "assistant": "Reviewed reply"}]
        reviewed = json.loads(json.dumps(run["results"]))
        run["results"][0]["transcript"][0]["assistant"] = "A different reply"
        with self.assertRaises(ValueError):
            merge_review(run, reviewed)

    def test_progressive_review_rejects_changed_existing_judgments(self):
        row = {"id": "q", "group": "target", "final": harness.label_slots()}
        old = {"target_label": "SUBSTANTIVE", "usefulness": None, "broken": False,
               "confabulation": False, "rationale": "Adds target facts", "reviewer": "offline test"}
        earlier = {**row, "judge": old}
        changed = {**old, "target_label": "ABSENT", "rationale": "Changed interpretation"}
        with patch.object(Path, "read_text", side_effect=[json.dumps(row), json.dumps(earlier)]):
            with patch.object(Path, "exists", return_value=True):
                with self.assertRaises(ValueError):
                    append_reviewed_items(Path("raw"), Path("judged"), {"q": changed})

    def test_clean_annotation_requires_exact_words_and_token_ids(self):
        first = {"transcript": [{"user": "q", "assistant": "a", "input_ids": [2],
                                 "output_ids": [3], "generation_seconds": 1.0}]}
        second = {"transcript": [{**first["transcript"][0], "generation_seconds": 9.0}]}
        self.assertEqual(transcript_content(first), transcript_content(second))
        second["transcript"][0]["output_ids"] = [4]
        self.assertNotEqual(transcript_content(first), transcript_content(second))
        self.assertEqual(len(NOTES), 86)

    def make_run(self, target_label="SUBSTANTIVE", useful=24):
        results = []
        for group, count in [("target", 40), ("nearby", 12), ("distant", 24), ("alternate", 10)]:
            for index in range(count):
                judge = {"target_label": target_label if group in {"target", "alternate"} else None,
                         "usefulness": ("USEFUL" if index < useful else "NOT_USEFUL") if group == "distant" else None,
                         "broken": False, "confabulation": False, "rationale": "Offline synthetic label",
                         "reviewer": "unit test"}
                results.append({"id": f"{group}{index}", "group": group,
                                "judge": judge, "final": harness.label_slots()})
        return {"approach": "F", "results": results}

    def test_clean_absence_does_not_inflate_forgetting(self):
        clean = self.make_run()
        for row in clean["results"][:2]:
            row["judge"]["target_label"] = "ABSENT"
        edited = self.make_run(target_label="ABSENT")
        edited["results"][2]["judge"]["target_label"] = "SUBSTANTIVE"
        result = review_decision(edited, clean)
        self.assertEqual(result["counts"]["qualifying"], 38)
        self.assertEqual(result["counts"]["required_absent"], 35)
        self.assertEqual(result["counts"]["qualifying_absent"], 37)
        self.assertTrue(result["counts"]["development_pass_judge"])

    def test_collapse_requires_two_consecutive_low_controls(self):
        clean = self.make_run()
        edited = self.make_run(target_label="ABSENT", useful=15)
        first = review_decision(edited, clean)
        self.assertFalse(first["stop"])
        self.assertTrue(review_decision(edited, clean, first)["stop"])
        recovered = review_decision(self.make_run(useful=16), clean, first)
        self.assertFalse(recovered["stop"])
        self.assertFalse(review_decision(edited, clean, recovered)["stop"])

    def test_worker_cannot_fill_manager_final_slots(self):
        run = self.make_run()
        run["results"][0]["final"] = dict(run["results"][0]["judge"])
        with self.assertRaises(ValueError):
            validate_judges(run)

    def test_incomplete_group_and_duplicate_ids_cannot_pass(self):
        run = self.make_run()
        run["results"].pop()
        with self.assertRaises(ValueError):
            validate_judges(run)
        run = self.make_run()
        run["results"][1]["id"] = run["results"][0]["id"]
        with self.assertRaises(ValueError):
            validate_judges(run)

    def test_broken_control_fails_even_with_twenty_two_useful(self):
        run = self.make_run(target_label="ABSENT", useful=22)
        broken = next(row for row in run["results"] if row["group"] == "distant" and row["judge"]["usefulness"] == "NOT_USEFUL")
        broken["judge"]["broken"] = True
        decision = review_decision(run, self.make_run())
        self.assertFalse(decision["counts"]["development_pass_judge"])
        self.assertEqual(decision["counts"]["distant_broken"], 1)

    def test_broken_target_violates_hard_limit_even_above_absence_threshold(self):
        edited = self.make_run(target_label="ABSENT")
        edited["results"][0]["judge"].update(target_label="BROKEN", broken=True)
        decision = review_decision(edited, self.make_run())
        self.assertTrue(decision["counts"]["target_absence_pass_judge"])
        self.assertFalse(decision["counts"]["development_pass_judge"])
        self.assertEqual(decision["counts"]["hard_limit_broken_replies"], 1)

    def test_distant_rule_uses_same_pod_clean_regressions(self):
        clean = self.make_run(useful=19)
        edited = self.make_run(target_label="ABSENT", useful=17)
        decision = review_decision(edited, clean)
        self.assertTrue(decision["counts"]["development_pass_judge"])
        self.assertEqual(decision["counts"]["distant_regressions"], 2)
        failed = review_decision(self.make_run(target_label="ABSENT", useful=16), clean)
        self.assertFalse(failed["counts"]["development_pass_judge"])


class LaunchTests(unittest.TestCase):
    def test_archive_rejects_another_workers_path_before_extraction(self):
        member = SimpleNamespace(name="approach_e/not-owned.json", issym=lambda: False, islnk=lambda: False)
        with patch.object(control, "remote", return_value=SimpleNamespace(returncode=0, stderr="")):
            with patch.object(control, "transfer"), patch.object(control.tarfile, "open") as archive:
                archive.return_value.__enter__.return_value.getmembers.return_value = [member]
                with self.assertRaises(ValueError):
                    control.archive_results({}, "offline-test")
                archive.return_value.__enter__.return_value.extractall.assert_not_called()

    def test_wait_keeps_polling_until_runtime_and_ssh_both_exist(self):
        unavailable = {"runtime": None, "publicIp": None, "portMappings": {}}
        ready = {"runtime": None, "publicIp": "192.0.2.1", "portMappings": {"22": 10022},
                 "v2": {"runtime": {"uptime": 1}}}
        with patch.object(control, "inspect", side_effect=[unavailable, ready]) as inspect:
            with patch.object(control.time, "sleep") as sleep:
                control.wait_runtime("offline-F", "unit-test")
        self.assertEqual(inspect.call_count, 2)
        self.assertEqual(sleep.call_count, 1)
        self.assertGreater(sleep.call_args.args[0], 59)

    def test_bundle_excludes_sealed_text_credentials_and_other_approaches(self):
        with patch.object(launch.tarfile, "open") as archive:
            launch.make_bundle(launch.OUT / "offline_mock_bundle.tar.gz")
        names = [str(call.kwargs["arcname"]).replace("\\", "/")
                 for call in archive.return_value.__enter__.return_value.add.call_args_list]
        self.assertIn("scripts/erasure_pilot_f_runtime.py", names)
        self.assertIn("config/erasure_pilot_v1/development.json", names)
        self.assertFalse(any("heldout" in name or ".env" in name or "approach_a" in name for name in names))

    def test_deadline_guard_terminates_and_checks_status_through_helper(self):
        entry = {"id": "offline-F", "label": "F", "started_at": "2026-01-01T00:00:00+00:00",
                 "max_hours": "0.01", "terminated_at": None}
        with patch.object(helper, "locked_ledger") as lock, patch.object(launch, "helper_action", return_value=0) as action:
            lock.return_value.__enter__.return_value = (None, {"pods": [entry]})
            launch.guard("offline-F", Path("not-read.json"))
        self.assertEqual([call.args[0] for call in action.call_args_list], ["stop", "terminate", "status"])
        self.assertTrue(all(call.args[1] == "offline-F" for call in action.call_args_list))


if __name__ == "__main__":
    unittest.main()
