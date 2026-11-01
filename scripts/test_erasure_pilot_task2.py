"""Test task 2 launch redaction, termination evidence and reply timings without sealed data."""

import copy
import io
import json
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from scripts import erasure_pilot_eval as evaluation
from scripts import runpod_pilot as runpod


class Task2Tests(unittest.TestCase):
    def test_reconciled_failed_create_costs_zero_without_false_termination(self):
        entry = {"id": None, "status": "CREATE_FAILED_NO_POD", "stopped_at": None, "terminated_at": None,
                 "reconciled_at": "2026-11-01T12:00:00+00:00", "reconciliation": "fixture-evidence.json"}
        ledger = {"limit_usd": "38.00", "other_spend_usd": "0", "pods": [entry]}
        self.assertEqual(runpod.recorded_spend(ledger, runpod.utc_now()), 0)
        self.assertEqual(runpod.check_budget(ledger, "0.80", runpod.utc_now()), 0)
        self.assertIsNone(entry["terminated_at"])
        entry["id"] = "real-resource"
        with self.assertRaises(ValueError):
            runpod.recorded_spend(ledger, runpod.utc_now())

    def test_rejected_create_retains_safe_http_status_and_reservation(self):
        request = runpod.build_request("create", gpu="L40S")
        request["body"]["env"] = {"HUGGINGFACE_TOKEN": "fixture-secret"}
        args = SimpleNamespace(gpu="L40S", hourly_price="0.80", stopped_hourly_price="0", price_source="fixture")
        ledger = {"limit_usd": "38.00", "other_spend_usd": "0", "pods": []}
        with patch.object(runpod, "save_ledger"):
            with patch.object(runpod, "send", side_effect=runpod.RunPodHTTPError(400)):
                with self.assertRaises(runpod.RunPodHTTPError):
                    runpod.create_pod(args, request, None, ledger, "fixture-key")
        self.assertEqual(ledger["pods"][0]["create_http_status"], 400)
        self.assertEqual(ledger["pods"][0]["status"], "CREATE_UNCERTAIN")
        self.assertNotIn("fixture-secret", json.dumps(ledger))

    def test_create_sends_token_but_never_saves_it(self):
        request = runpod.build_request("create", gpu="L40S")
        request["body"]["env"] = {"HUGGINGFACE_TOKEN": "fixture-secret"}
        args = SimpleNamespace(gpu="L40S", hourly_price="0.80", stopped_hourly_price="0", price_source="fixture")
        ledger = {"limit_usd": "38.00", "other_spend_usd": "0", "pods": []}
        saved = []
        with patch.object(runpod, "save_ledger", side_effect=lambda handle, data: saved.append(copy.deepcopy(data))):
            with patch.object(runpod, "send", return_value={"id": "fixture", "status": "PROVISIONING"}) as send:
                runpod.create_pod(args, request, None, ledger, "fixture-key")
        self.assertEqual(send.call_args.args[0]["body"]["env"]["HUGGINGFACE_TOKEN"], "fixture-secret")
        self.assertNotIn("fixture-secret", json.dumps(saved))
        self.assertEqual(ledger["pods"][0]["request"]["env"]["HUGGINGFACE_TOKEN"], "[REDACTED]")

    def test_environment_dry_run_does_not_read_credentials(self):
        output = io.StringIO()
        with patch.object(runpod, "read_key", side_effect=AssertionError("Credential read")):
            with patch.object(runpod, "read_env_value", side_effect=AssertionError("Credential read")):
                with patch.object(runpod, "send", side_effect=AssertionError("HTTP")):
                    with redirect_stdout(output):
                        runpod.main(["create", "--gpu", "L40S", "--hourly-price", "0.80",
                                     "--stopped-hourly-price", "0", "--price-source", "fixture",
                                     "--environment", "HUGGINGFACE_TOKEN", "--dry-run"])
        self.assertEqual(json.loads(output.getvalue())["body"]["env"]["HUGGINGFACE_TOKEN"], "[REDACTED]")

    def test_status_404_requires_prior_successful_termination(self):
        entry = {"id": "fixture", "terminated_at": "2026-11-01T12:00:00+00:00"}
        ledger = {"pods": [entry]}
        args = SimpleNamespace(command="status", pod_id="fixture")
        with patch.object(runpod, "save_ledger"):
            with patch.object(runpod, "send", side_effect=runpod.RunPodHTTPError(404)):
                result = runpod.update_pod(args, runpod.build_request("status", pod_id="fixture"), None, ledger, "fixture-key")
                self.assertEqual(result["status"], "TERMINATED")
                self.assertEqual(result["status_http"], 404)
                entry["terminated_at"] = None
                with self.assertRaises(runpod.RunPodHTTPError):
                    runpod.update_pod(args, runpod.build_request("status", pod_id="fixture"), None, ledger, "fixture-key")

    def test_status_403_never_claims_termination(self):
        ledger = {"pods": [{"id": "fixture", "terminated_at": "2026-11-01T12:00:00+00:00"}]}
        args = SimpleNamespace(command="status", pod_id="fixture")
        with patch.object(runpod, "send", side_effect=runpod.RunPodHTTPError(403)):
            with self.assertRaises(runpod.RunPodHTTPError):
                runpod.update_pod(args, runpod.build_request("status", pod_id="fixture"), None, ledger, "fixture-key")

    def test_turn_and_item_timings_preserve_live_history(self):
        item = {"id": "fixture", "group": "target", "turns": ["First", "Second"]}
        histories = []

        def reply(model, tokenizer, messages, alternate):
            histories.append(copy.deepcopy(messages))
            return "Fixture reply", [2, 3], [4, 106]

        with patch.object(evaluation, "generate_reply", side_effect=reply):
            result = evaluation.generate_item(None, None, item)
        self.assertGreaterEqual(result["elapsed_seconds"], 0)
        self.assertTrue(all(turn["generation_seconds"] >= 0 for turn in result["transcript"]))
        self.assertEqual(histories[1][1], {"role": "assistant", "content": "Fixture reply"})
        self.assertTrue(all(value is None for value in result["final"].values()))


if __name__ == "__main__":
    unittest.main()
