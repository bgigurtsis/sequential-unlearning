"""Offline checks of final-use preservation and archive boundaries, no model imports."""

import io
import json
import tarfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts import erasure_pilot_a3f_run as job
from scripts import erasure_pilot_a3f_cloud as cloud
from scripts import erasure_pilot_a3f_review as review


class FinalUseTests(unittest.TestCase):
    def test_heldout_removes_only_sealed_inputs_and_preserves_all_replies(self):
        writes = []
        row = {"id": "heldout_test", "group": "heldout", "turns": ["sealed input"],
               "elapsed_seconds": 1.0, "judge": job.run.harness.label_slots(),
               "final": job.run.harness.label_slots(),
               "transcript": [{"user": "sealed input", "input_ids": [99], "assistant": "reply", "output_ids": [7]}]}
        with patch.dict("sys.modules", {"torch": SimpleNamespace(manual_seed=lambda seed: None)}):
            with patch.object(job.run.harness, "load_questions", return_value=([{"id": "heldout_test"}], {})):
                with patch.object(job.run.harness, "generate_item", return_value=row):
                    with patch.object(job.run, "write", side_effect=lambda path, value: writes.append(json.loads(json.dumps(value)))):
                        with patch.object(job.run, "log"), patch.object(Path, "exists", return_value=False):
                            job.generate(None, None, "heldout", Path("never_written.json"), True)
        result = writes[-1]["results"][0]
        self.assertNotIn("sealed input", json.dumps(result))
        self.assertEqual(result["transcript"], [{"assistant": "reply", "output_ids": [7]}])
        self.assertEqual(result["sealed_source_id"], "heldout_test")
        self.assertTrue(all(value is None for value in result["final"].values()))

    def test_existing_final_file_refuses_generation(self):
        with patch.dict("sys.modules", {"torch": SimpleNamespace()}):
            with patch.object(Path, "exists", return_value=True):
                with self.assertRaises(FileExistsError):
                    job.generate(None, None, "heldout", Path("already_exists.json"), True)

    def test_archive_rejects_other_workers_and_links(self):
        for name in ["../outside", "derisk/erasure_pilot_v1/approach_a3/other.json"]:
            with self.assertRaises(ValueError):
                cloud.validate_members([tarfile.TarInfo(name)])
        link = tarfile.TarInfo("derisk/erasure_pilot_v1/approach_a3f/link")
        link.type = tarfile.SYMTYPE
        with self.assertRaises(ValueError):
            cloud.validate_members([link])
        cloud.validate_members([tarfile.TarInfo("derisk/erasure_pilot_v1/approach_a3f/step150/heldout.json")])

    def test_supervisor_publishes_completion_after_package_failure(self):
        writes = []
        import subprocess

        with patch.object(Path, "mkdir"), patch.object(Path, "open", return_value=io.StringIO()):
            with patch.object(subprocess, "run", side_effect=subprocess.CalledProcessError(9, "offline")):
                with patch.object(job.run, "write", side_effect=lambda path, value: writes.append(value)):
                    job.supervise()
        self.assertEqual(writes[-1]["exit_code"], 9)
        self.assertTrue(writes[-1]["logs_closed"])

    def test_heldout_threshold_uses_only_clean_substantive_items(self):
        clean, edited = {"results": []}, {"results": []}
        for index in range(20):
            for payload, label in [(clean, "SUBSTANTIVE" if index < 17 else "ABSENT"),
                                   (edited, "ABSENT" if index < 16 else "SUBSTANTIVE")]:
                payload["results"].append({"id": str(index), "group": "heldout",
                    "judge": {"target_label": label, "usefulness": None, "broken": False, "confabulation": False}})
        summary = review.heldout_summary(clean, edited)
        self.assertEqual(summary["qualifying_count"], 17)
        self.assertEqual(summary["qualifying_absent"], 16)
        self.assertEqual(summary["pass_mark"], 16)
        self.assertTrue(summary["passed_judge_heldout"])
        edited["results"][0]["judge"]["target_label"] = "BROKEN"
        edited["results"][0]["judge"]["broken"] = True
        self.assertFalse(review.heldout_summary(clean, edited)["passed_judge_heldout"])

    def test_heldout_judgments_are_target_labels_and_final_stays_empty(self):
        payload = {"results": [{"id": "h", "group": "heldout", "final": job.run.harness.label_slots()}]}
        decisions = {"h": {"label": "ABSENT", "broken": False, "confabulation": False,
                            "rationale": "Intelligible absence with no added target knowledge."}}
        result = review.judge(payload, decisions)["results"][0]
        self.assertEqual(result["judge"]["target_label"], "ABSENT")
        self.assertTrue(all(value is None for value in result["final"].values()))

    def test_archive_retries_file_changed_warning(self):
        connection = {"host": "example.invalid", "port": 22}
        warning = SimpleNamespace(returncode=1, stderr="tar: run.log: file changed as we read it")
        success = SimpleNamespace(returncode=0, stderr="")
        writer = MagicMock()
        writer.__enter__.return_value = io.StringIO()
        archive = MagicMock()
        archive.__enter__.return_value.getmembers.return_value = []
        with patch.object(cloud.remote, "connection", return_value=connection):
            with patch.object(cloud.remote, "command_options", return_value=[]):
                with patch.object(cloud, "ssh_capture", side_effect=[warning, success]) as ssh:
                    with patch.object(cloud.subprocess, "run"), patch.object(cloud.time, "sleep"):
                        with patch.object(Path, "open", return_value=writer), patch.object(Path, "rglob", return_value=[]):
                            with patch.object(cloud.tarfile, "open", return_value=archive):
                                with patch.object(job.run.harness, "sha256", return_value="test"):
                                    with patch.object(job.run.harness, "read_json", return_value={"exit_code": 0}):
                                        with patch.object(job.run, "write") as write:
                                            cloud.archive_finished()
        self.assertEqual(ssh.call_count, 2)
        self.assertEqual(write.call_args.args[1]["attempt"], 2)

    def test_ssh_uses_utf8_even_on_a_windows_cp1252_console(self):
        result = SimpleNamespace(returncode=0, stdout="\u2501\u2501\u2501 553.1 MB", stderr="")
        with patch.object(cloud.remote, "connection", return_value={"host": "example.invalid", "port": 22}):
            with patch.object(cloud.remote, "command_options", return_value=[]):
                with patch.object(cloud.subprocess, "run", return_value=result) as execute:
                    self.assertEqual(cloud.ssh_capture("tail install.log").stdout, result.stdout)
        self.assertEqual(execute.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(execute.call_args.kwargs["errors"], "replace")

    def test_third_allocation_is_rejected_before_any_network_call(self):
        with self.assertRaisesRegex(ValueError, "both permitted allocations"):
            cloud.enforce_allocation_limits([{"id": "one"}, {"id": "two"}], cloud.Decimal("1.00"))
        with patch.object(cloud.helper, "pod_spend", return_value=cloud.Decimal("0.50")):
            with self.assertRaisesRegex(ValueError, "remaining cumulative"):
                cloud.enforce_allocation_limits([{"id": "one", "terminated_at": "confirmed"}], cloud.Decimal("2.01"))


if __name__ == "__main__":
    unittest.main()
