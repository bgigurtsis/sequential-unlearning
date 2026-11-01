"""Offline checks for F2's frozen comparison and hardware-dependent clean reference."""

import types
import unittest
from unittest import mock

from scripts import erasure_pilot_f2_run as f2
from scripts import erasure_pilot_f2_review as f2_review
from scripts import erasure_pilot_f2_cloud as cloud


class F2Tests(unittest.TestCase):
    def test_frozen_features_and_source(self):
        settings, features = f2.frozen_inputs()
        self.assertEqual(settings["ladder"], [2, 3])
        self.assertEqual(settings["layers"], [13, 20])
        self.assertTrue(settings["preserve_error"])
        self.assertEqual([len(rows) for rows in features["selected"].values()], [20, 20])
        self.assertEqual(features["settings"]["ladder"], [0, 1, 4, 16])

    def test_exact_hardware_match_only(self):
        self.assertTrue(f2.gpu_matches(f2.SAME_GPU + "\n"))
        self.assertFalse(f2.gpu_matches("NVIDIA RTX PRO 6000 Blackwell Server Edition"))
        self.assertFalse(f2.gpu_matches("NVIDIA A100-SXM4-80GB"))

    def check_run(self, same_gpu):
        settings, features = f2.frozen_inputs()
        clean = f2.harness.read_json(f2.SOURCE / "clean_reference.json")
        model = types.SimpleNamespace(requires_grad_=mock.Mock(), named_parameters=lambda: [])
        tokenizer = types.SimpleNamespace(pad_token_id=1)
        transformer = types.SimpleNamespace(AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda *a, **kw: tokenizer))
        info = {"commit": "test", "packages": {}, "clean_source_sha256": "test"}
        events = []
        def capture_clean(*args):
            events.append("clean")

        def capture_rung(*args):
            events.append(args[5])

        with mock.patch.object(f2, "frozen_inputs", return_value=(settings, features)), \
             mock.patch.object(f2.bootstrap, "install_runtime"), \
             mock.patch.object(f2.bootstrap, "prepare_model"), \
             mock.patch.object(f2.harness, "verify_snapshot", return_value=clean["base_files"]), \
             mock.patch.object(f2.harness, "load_questions", return_value=([], clean["hashes"])), \
             mock.patch.object(f2.runtime, "metadata", return_value=info), \
             mock.patch.object(f2.harness, "load_model", return_value=model), \
             mock.patch.object(f2.runtime, "find_layers", return_value={13: ("layers.13", None), 20: ("layers.20", None)}), \
             mock.patch.object(f2.runtime, "load_saes", return_value=({}, features["sae_files"])), \
             mock.patch.object(f2.runtime, "evaluate_clean", side_effect=capture_clean), \
             mock.patch.object(f2.runtime, "evaluate_rung", side_effect=capture_rung), \
             mock.patch.object(f2.subprocess, "check_output", return_value=f2.SAME_GPU if same_gpu else "NVIDIA A100-SXM4-80GB"), \
             mock.patch.object(f2.harness, "write_new") as writes, \
             mock.patch.dict("sys.modules", {"transformers": transformer}):
            f2.run(f2.ROOT / "unused-snapshot")
        self.assertEqual(events, [2, 3] if same_gpu else ["clean", 2, 3])
        completed = [call.args[1] for call in writes.call_args_list if call.args[0].name == "completed.json"]
        self.assertTrue(completed[0]["weights_unchanged"])
        frozen = [call.args[1] for call in writes.call_args_list if call.args[0].name == "features.json"][0]
        self.assertEqual(frozen["selected"], features["selected"])
        for k in [2, 3]:
            for layer, rows in features["selected"].items():
                self.assertEqual(frozen["clamp_values"][k][int(layer)], [-k * row["mean_active"] for row in rows])

    def test_reuse_exact_gpu_then_run_both_rungs(self):
        self.check_run(True)

    def test_new_clean_first_on_other_gpu(self):
        self.check_run(False)

    def test_incomplete_judgments_cannot_produce_counts(self):
        raw = f2.harness.read_json(f2.SOURCE / "clean_reference.json")
        with self.assertRaisesRegex(ValueError, "Every result"):
            f2_review.judged_run(raw, {})

    def test_worker_cannot_write_manager_final_labels(self):
        raw = f2.harness.read_json(f2.SOURCE / "clean_reference_judge.json")
        raw["results"][0]["final"]["broken"] = False
        annotations = {}
        for row in raw["results"]:
            label = row["judge"]["target_label"] or row["judge"]["usefulness"] or "OBSERVATION"
            annotations[row["id"]] = (label, row["judge"]["rationale"])
        with self.assertRaisesRegex(ValueError, "final slot"):
            f2_review.judged_run(raw, annotations)

    def test_ledger_contention_does_not_kill_guard(self):
        context = mock.MagicMock()
        context.__enter__.return_value = (None, {"pods": [{"id": "pod", "label": "F2"}]})
        with mock.patch.object(cloud.helper, "locked_ledger", side_effect=[PermissionError(), context]), \
             mock.patch.object(cloud.time, "sleep") as sleep:
            self.assertEqual(cloud.entry("pod")["label"], "F2")
        sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
