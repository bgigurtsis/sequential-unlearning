"""Offline RunPod allocation, budget, redaction and cross-process locking tests."""

import copy
import io
import json
import subprocess
import sys
import unittest
import urllib.error
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts import erasure_pilot_eval as evaluation
from scripts import runpod_pilot as runpod


NOW = "2026-11-01T12:00:00+00:00"


def ledger(other="0", pods=None):
    return {"limit_usd": "38.00", "other_spend_usd": other, "pods": pods or []}


def args(gpu="mid", **changes):
    values = {"gpu": gpu, "label": "A", "max_hours": "2", "hourly_price": None, "stopped_hourly_price": "0"}
    values.update(changes)
    return SimpleNamespace(**values)


def catalog(gpu="mid", cloud="COMMUNITY", price="1", availability="HIGH"):
    return {"gpus": [{"id": name, "availability": availability, "price": {cloud.lower(): price}}
                     for name in runpod.GPU_CLASSES[gpu][cloud]]}


def request(gpu="mid"):
    return runpod.build_request("create", gpu=gpu, label="A")


class Task2Tests(unittest.TestCase):
    def setUp(self):
        self.network = patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.socket = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        self.socket.start()
        self.addCleanup(self.socket.stop)

    def test_reconciled_failed_create_costs_zero_without_false_termination(self):
        entry = {"id": None, "status": "CREATE_FAILED_NO_POD", "stopped_at": None, "terminated_at": None,
                 "reconciled_at": NOW, "reconciliation": "fixture-evidence.json"}
        entries = ledger(pods=[entry])
        self.assertEqual(runpod.recorded_spend(entries, NOW), 0)
        self.assertEqual(runpod.check_budget(entries, "0.80", NOW, "2"), 0)
        self.assertIsNone(entry["terminated_at"])
        entry["id"] = "real-resource"
        with self.assertRaises(ValueError):
            runpod.recorded_spend(entries, NOW)

    def test_live_catalog_filter_order_price_limit_and_disk(self):
        for selected in ("mid", "big"):
            for cloud in ("COMMUNITY", "SECURE"):
                data = catalog(selected, cloud)
                data["gpus"].reverse()
                data["gpus"][0]["availability"] = "NONE"
                data["gpus"][1]["price"][cloud.lower()] = "100"
                data["gpus"][2]["price"][cloud.lower()] = runpod.GPU_CLASSES[selected]["max_price"]
                with patch.object(runpod, "send", return_value=data), patch.object(runpod, "utc_now", return_value=NOW):
                    result = runpod.read_catalog(selected, cloud, "fixture-key")
                excluded = {data["gpus"][0]["id"], data["gpus"][1]["id"]}
                self.assertEqual([item["id"] for item in result["candidates"]],
                                 [name for name in runpod.GPU_CLASSES[selected][cloud] if name not in excluded])
                expected = Decimal(runpod.GPU_CLASSES[selected]["max_price"]) + runpod.DISK_HOURLY_PER_GB * runpod.GPU_CLASSES[selected]["disk_gb"]
                self.assertEqual(Decimal(result["quoted_hourly_price_usd"]), expected)
                self.assertIn(NOW, result["price_source"])
                self.assertEqual(result["source"], runpod.CATALOG + cloud)

    def test_missing_unknown_zero_prices_do_not_become_candidates(self):
        data = catalog()
        for item in data["gpus"]:
            item["price"] = {}
        data["gpus"][0]["price"] = {"community": "0"}
        data["gpus"][1].pop("availability")
        with patch.object(runpod, "send", return_value=data):
            result = runpod.read_catalog("mid", "COMMUNITY", "fixture-key")
        self.assertEqual(result["candidates"], [])
        self.assertIsNone(result["quoted_hourly_price_usd"])

    def test_create_sends_token_saves_reservation_and_records_actual(self):
        launch = request()
        launch["body"]["env"] = {"HUGGINGFACE_TOKEN": "fixture-secret", "PUBLIC_KEY": "ssh-fixture"}
        entries = ledger()
        saved = []
        response = {"id": "fixture", "desiredStatus": "RUNNING", "status": "STOPPED",
                    "gpuTypeId": "actual-gpu", "cloudType": "COMMUNITY", "costPerHr": "2.1"}
        with patch.object(runpod, "save_ledger", side_effect=lambda handle, data: saved.append(copy.deepcopy(data))):
            with patch.object(runpod, "send", side_effect=[catalog(), response]) as send:
                runpod.create_pod(args(), launch, None, entries, "fixture-key")
        self.assertEqual(send.call_args.args[0]["body"]["env"]["HUGGINGFACE_TOKEN"], "fixture-secret")
        self.assertEqual(saved[0]["pods"][0]["status"], "CREATE_UNCERTAIN")
        self.assertIsNone(saved[0]["pods"][0]["id"])
        self.assertNotIn("fixture-secret", json.dumps(saved))
        self.assertNotIn("ssh-fixture", json.dumps(saved))
        entry = entries["pods"][0]
        self.assertEqual(entry["status"], "RUNNING")
        self.assertEqual(entry["actual_gpu_type"], "actual-gpu")
        self.assertEqual(entry["cloud"], "COMMUNITY")
        self.assertEqual(entry["hourly_price_usd"], "2.1")
        self.assertEqual(entry["actual_hourly_price_usd"], "2.1")
        self.assertEqual(entry["max_hours"], "2")

    def test_manual_price_only_raises_and_cheaper_allocation_keeps_quote(self):
        for manual in ("0.1", "3"):
            entries = ledger()
            with patch.object(runpod, "save_ledger"), patch.object(runpod, "send", side_effect=[
                catalog(), {"id": "fixture", "gpuTypeId": "gpu", "costPerHr": "0.5"}
            ]):
                runpod.create_pod(args(hourly_price=manual), request(), None, entries, "fixture-key")
            expected = max(Decimal(manual), Decimal(1) + runpod.DISK_HOURLY_PER_GB * 80)
            self.assertEqual(Decimal(entries["pods"][0]["hourly_price_usd"]), expected)
            self.assertIn(runpod.CATALOG, entries["pods"][0]["price_source"])

    def test_empty_community_catalog_uses_secure(self):
        entries = ledger()
        with patch.object(runpod, "save_ledger"), patch.object(runpod, "send", side_effect=[
            catalog(availability="NONE"), catalog(cloud="SECURE"), {"id": "secure", "desiredStatus": "RUNNING"}
        ]) as send:
            runpod.create_pod(args(), request(), None, entries, "fixture-key")
        calls = send.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0].args[0]["method"], "GET")
        self.assertTrue(calls[1].args[0]["url"].endswith("SECURE"))
        self.assertEqual(calls[2].args[0]["body"]["gpuTypeIds"], runpod.GPU_CLASSES["mid"]["SECURE"])
        self.assertEqual(calls[2].args[0]["body"]["cloudType"], "SECURE")
        self.assertEqual(entries["pods"][0]["id"], "secure")

    def test_capacity_rejection_uses_secure_and_retains_sanitised_diagnosis(self):
        entries = ledger()
        launch = request()
        launch["body"]["env"] = {"HUGGINGFACE_TOKEN": "fixture-secret"}
        output = io.StringIO()
        posted = []
        responses = iter([catalog(), runpod.RunPodHTTPError(400, "No capacity fixture-key fixture-secret"),
                          catalog(cloud="SECURE", price="2"), {"id": "secure"}])

        def send(req, *unused):
            if req["method"] == "POST":
                posted.append(copy.deepcopy(req["body"]))
            result = next(responses)
            if isinstance(result, Exception):
                raise result
            return result

        with patch.object(runpod, "save_ledger"), patch.object(runpod, "send", side_effect=send), redirect_stdout(output):
            runpod.create_pod(args(), launch, None, entries, "fixture-key")
        self.assertEqual([body["cloudType"] for body in posted], ["COMMUNITY", "SECURE"])
        self.assertEqual(posted[0]["name"], posted[1]["name"])
        self.assertEqual(len(entries["pods"]), 1)
        entry = entries["pods"][0]
        self.assertEqual(entry["create_http_status"], 400)
        self.assertEqual(entry["http_errors"][0]["error_text"], "No capacity [REDACTED] [REDACTED]")
        for secret in ("fixture-key", "fixture-secret"):
            self.assertNotIn(secret, json.dumps(entries) + output.getvalue())

    def test_noncapacity_rejection_and_transport_failure_do_not_retry(self):
        for failure in (runpod.RunPodHTTPError(400, "Invalid input"), RuntimeError("Transport failure")):
            entries = ledger()
            with patch.object(runpod, "save_ledger"), patch.object(runpod, "send", side_effect=[catalog(), failure]) as send:
                with self.assertRaises(type(failure)):
                    runpod.create_pod(args(), request(), None, entries, "fixture-key")
            self.assertEqual(send.call_count, 2)
            self.assertEqual(entries["pods"][0]["status"], "CREATE_UNCERTAIN")
            self.assertGreater(runpod.committed_spend(entries, runpod.utc_now()), 2)

    def test_no_catalog_capacity_does_not_post(self):
        entries = ledger()
        with patch.object(runpod, "save_ledger"), patch.object(runpod, "send", side_effect=[
            catalog(availability="NONE"), catalog(cloud="SECURE", availability="NONE")
        ]) as send:
            with self.assertRaises(ValueError):
                runpod.create_pod(args(), request(), None, entries, "fixture-key")
        self.assertTrue(all(call.args[0]["method"] == "GET" for call in send.call_args_list))
        self.assertEqual(entries["pods"], [])

    def test_budget_refusal_precedes_create_post_and_secure_requotes(self):
        for other, responses in (("38", [catalog()]), ("34", [catalog(), runpod.RunPodHTTPError(400, "No capacity"), catalog(cloud="SECURE", price="2")])):
            with patch.object(runpod, "save_ledger"), patch.object(runpod, "send", side_effect=responses) as send, redirect_stdout(io.StringIO()):
                with self.assertRaises(ValueError):
                    runpod.create_pod(args(), request(), None, ledger(other), "fixture-key")
            posts = [call for call in send.call_args_list if call.args[0]["method"] == "POST"]
            self.assertEqual(len(posts), 0 if other == "38" else 1)

    def test_catalog_http_error_is_recorded_as_no_create(self):
        entries = ledger()
        with patch.object(runpod, "save_ledger"), patch.object(runpod, "send", side_effect=runpod.RunPodHTTPError(403, "blocked")):
            with self.assertRaises(runpod.RunPodHTTPError):
                runpod.create_pod(args(), request(), None, entries, "fixture-key")
        self.assertEqual(entries["pods"][0]["status"], "CREATE_FAILED_NO_POD")
        self.assertEqual(entries["pods"][0]["http_errors"][0]["status_code"], 403)
        self.assertEqual(runpod.committed_spend(entries, NOW), 0)

    def test_environment_ssh_and_startup_dry_run_does_not_read_credentials(self):
        output = io.StringIO()
        real_read = Path.read_text

        def read(path, *positional, **keywords):
            if path.name == "key.pub":
                return "ssh-ed25519 fixture-public"
            if path.name == "start.sh":
                return "/start.sh &\nwait"
            return real_read(path, *positional, **keywords)

        with patch.object(runpod, "read_key", side_effect=AssertionError("Credential read")):
            with patch.object(runpod, "read_env_value", side_effect=AssertionError("Credential read")):
                with patch.object(runpod, "send", side_effect=AssertionError("HTTP")), patch.object(Path, "read_text", read):
                    with redirect_stdout(output):
                        runpod.main(["create", "--gpu", "mid", "--label", "A", "--max-hours", "2",
                                     "--environment", "HUGGINGFACE_TOKEN", "--public-key-file", "key.pub",
                                     "--startup-script", "start.sh", "--dry-run"])
        body = json.loads(output.getvalue())["body"]
        self.assertEqual(body["env"], {"HUGGINGFACE_TOKEN": "[REDACTED]", "PUBLIC_KEY": "[REDACTED]"})
        self.assertEqual(body["dockerStartCmd"], ["bash", "-c", "/start.sh &\nwait"])

    def test_list_prints_only_allowlisted_fields_without_touching_ledger(self):
        remote = {"id": "fixture", "name": "A", "desiredStatus": "RUNNING", "gpuTypeId": "GPU",
                  "costPerHr": "1.25", "env": {"TOKEN": "fixture-secret"}, "ssh": "private"}
        output = io.StringIO()
        with patch.object(runpod, "read_key", return_value="fixture-key"), patch.object(runpod, "read_env_value", return_value="fixture-token"):
            with patch.object(runpod, "send", return_value=[remote]), patch.object(runpod, "locked_ledger", side_effect=AssertionError("Ledger touched")):
                with redirect_stdout(output):
                    runpod.main(["list"])
        result = json.loads(output.getvalue())[0]
        self.assertEqual(set(result), {"id", "name", "desiredStatus", "gpu", "costPerHr"})
        self.assertNotIn("fixture-secret", output.getvalue())
        self.assertEqual(result["desiredStatus"], "RUNNING")

    def test_http_user_agent_and_error_redaction_before_truncation(self):
        launch = request()
        launch["body"]["env"] = {"HUGGINGFACE_TOKEN": "fixture-token"}
        text = "fixture-key fixture-key fixture-token " + "x" * 270 + "fixture-token"
        failure = urllib.error.HTTPError(runpod.API + "/pods", 403, "Forbidden", {}, io.BytesIO(text.encode()))
        with patch("urllib.request.urlopen", side_effect=failure) as open_url:
            with self.assertRaises(runpod.RunPodHTTPError) as caught:
                runpod.send(launch, "fixture-key")
        http = open_url.call_args.args[0]
        self.assertEqual(http.get_header("User-agent"), "erasure-pilot/1")
        self.assertEqual(caught.exception.status_code, 403)
        self.assertLessEqual(len(caught.exception.error_text), 300)
        self.assertNotIn("fixture-key", str(caught.exception))
        self.assertNotIn("fixture-token", str(caught.exception))
        self.assertIn("[REDACTED]", str(caught.exception))

    def test_http_success_is_mocked_at_transport_boundary(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'[{"id":"fixture"}]'
        with patch("urllib.request.urlopen", return_value=response):
            self.assertEqual(runpod.send(runpod.build_request("list"), "fixture-key"), [{"id": "fixture"}])

    def test_ambiguous_service_failure_does_not_trigger_capacity_fallback(self):
        self.assertFalse(runpod.capacity_error(runpod.RunPodHTTPError(503, "Service unavailable")))
        self.assertTrue(runpod.capacity_error(runpod.RunPodHTTPError(400, "Requested GPUs are unavailable")))

    def test_missing_create_id_keeps_full_reservation(self):
        entries = ledger()
        with patch.object(runpod, "save_ledger"), patch.object(runpod, "send", side_effect=[catalog(), {}]):
            with self.assertRaises(RuntimeError):
                runpod.create_pod(args(), request(), None, entries, "fixture-key")
        self.assertIsNone(entries["pods"][0]["id"])
        self.assertEqual(entries["pods"][0]["status"], "CREATE_UNCERTAIN")
        self.assertGreater(runpod.committed_spend(entries, runpod.utc_now()), 2)

    def test_rest_response_nested_gpu_and_cloud_and_larger_rate(self):
        entry = {"hourly_price_usd": "1", "cloud": "COMMUNITY"}
        runpod.record_actual(entry, {"id": "actual", "gpu": {"id": "nested-gpu"},
                                    "machine": {"secureCloud": True}, "costPerHr": "2.5",
                                    "adjustedCostPerHr": "2", "desiredStatus": "RUNNING"})
        self.assertEqual(entry["actual_gpu_type"], "nested-gpu")
        self.assertEqual(entry["cloud"], "SECURE")
        self.assertEqual(entry["hourly_price_usd"], "2.5")

    def test_hf_token_is_sanitised_even_when_not_injected_into_create(self):
        entries = ledger()
        failure = runpod.RunPodHTTPError(403, "fixture-token fixture-key fixture-token")
        with patch.object(runpod, "save_ledger"), patch.object(runpod, "send", side_effect=[catalog(), failure]):
            with self.assertRaises(runpod.RunPodHTTPError) as caught:
                runpod.create_pod(args(), request(), None, entries, "fixture-key", "fixture-token")
        self.assertNotIn("fixture-token", str(caught.exception) + json.dumps(entries))
        self.assertNotIn("fixture-key", str(caught.exception) + json.dumps(entries))

    def test_status_404_requires_prior_successful_termination(self):
        entry = {"id": "fixture", "terminated_at": NOW}
        entries = ledger(pods=[entry])
        status_args = SimpleNamespace(command="status", pod_id="fixture")
        with patch.object(runpod, "save_ledger"), patch.object(runpod, "send", side_effect=runpod.RunPodHTTPError(404, "missing")):
            result = runpod.update_pod(status_args, runpod.build_request("status", pod_id="fixture"), None, entries, "fixture-key")
            self.assertEqual(result["desiredStatus"], "TERMINATED")
            self.assertEqual(result["status_http"], 404)
            entry["terminated_at"] = None
            with self.assertRaises(runpod.RunPodHTTPError):
                runpod.update_pod(status_args, runpod.build_request("status", pod_id="fixture"), None, entries, "fixture-key")
        self.assertEqual(len(entry["http_errors"]), 2)

    def test_status_403_never_claims_termination(self):
        entries = ledger(pods=[{"id": "fixture", "terminated_at": NOW}])
        status_args = SimpleNamespace(command="status", pod_id="fixture")
        with patch.object(runpod, "save_ledger"), patch.object(runpod, "send", side_effect=runpod.RunPodHTTPError(403, "blocked")):
            with self.assertRaises(runpod.RunPodHTTPError):
                runpod.update_pod(status_args, runpod.build_request("status", pod_id="fixture"), None, entries, "fixture-key")
        self.assertEqual(entries["pods"][0]["http_errors"][0]["status_code"], 403)

    def test_reconcile_matches_exact_name_and_records_actual_allocation(self):
        launch = request()
        entries = ledger()
        with patch.object(runpod, "save_ledger"), patch.object(runpod, "send", side_effect=[catalog(), RuntimeError("timeout")]):
            with self.assertRaises(RuntimeError):
                runpod.create_pod(args(), launch, None, entries, "fixture-key")
        name = launch["body"]["name"]
        response = [{"id": "other", "name": name + "-other"},
                    {"id": "found", "name": name, "desiredStatus": "RUNNING", "gpuTypeId": "actual", "costPerHr": "2"}]
        with patch.object(runpod, "save_ledger"), patch.object(runpod, "send", return_value=response):
            result = runpod.reconcile_pod(name, None, entries, "fixture-key")
        self.assertEqual(result["id"], "found")
        self.assertEqual(entries["pods"][0]["actual_gpu_type"], "actual")
        self.assertEqual(entries["pods"][0]["reconciliation"]["matching_ids"], ["found"])

    def test_reconcile_empty_list_releases_reservation_and_preserves_legacy_entry(self):
        legacy = json.loads(runpod.LEDGER.read_text(encoding="utf-8"))["pods"][0]
        legacy_before = copy.deepcopy(legacy)
        entry = {"id": None, "name": "unique", "status": "CREATE_UNCERTAIN", "started_at": NOW,
                 "max_hours": "2", "hourly_price_usd": "1", "stopped_at": None, "terminated_at": None}
        entries = ledger(pods=[legacy, entry])
        with patch.object(runpod, "save_ledger"), patch.object(runpod, "send", return_value=[]):
            result = runpod.reconcile_pod("unique", None, entries, "fixture-key")
        self.assertEqual(result["desiredStatus"], "CREATE_FAILED_NO_POD")
        self.assertEqual(entry["reconciliation"]["matching_ids"], [])
        self.assertTrue(entry["reconciled_at"])
        self.assertIsNone(entry["terminated_at"])
        self.assertEqual(runpod.committed_spend(entries, runpod.utc_now()), 0)
        self.assertEqual(legacy, legacy_before)

    def test_reconcile_rejects_unknown_list_shape_and_duplicate_names(self):
        for response in ({"unexpected": []}, [{"id": "one", "name": "unique"}, {"id": "two", "name": "unique"}]):
            entry = {"id": None, "name": "unique", "status": "CREATE_UNCERTAIN"}
            with patch.object(runpod, "save_ledger"), patch.object(runpod, "send", return_value=response):
                with self.assertRaises(ValueError):
                    runpod.reconcile_pod("unique", None, ledger(pods=[entry]), "fixture-key")
            self.assertEqual(entry["status"], "CREATE_UNCERTAIN")
            self.assertNotIn("reconciled_at", entry)

    def test_ledger_lock_excludes_another_process_then_releases(self):
        # Lock the existing ledger read-only. Neither process writes or creates files.
        program = """
import sys
from pathlib import Path
from scripts import runpod_pilot as runpod
try:
    with runpod.locked_ledger(Path(sys.argv[1])):
        print('ACQUIRED')
except OSError:
    print('LOCKED')
"""
        before = runpod.LEDGER.read_bytes()
        command = [sys.executable, "-B", "-c", program, str(runpod.LEDGER)]
        with runpod.locked_ledger(runpod.LEDGER):
            blocked = subprocess.run(command, cwd=runpod.ROOT, capture_output=True, text=True, timeout=15)
        acquired = subprocess.run(command, cwd=runpod.ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(blocked.returncode, 0, blocked.stderr)
        self.assertEqual(blocked.stdout.strip(), "LOCKED")
        self.assertEqual(acquired.returncode, 0, acquired.stderr)
        self.assertEqual(acquired.stdout.strip(), "ACQUIRED")
        self.assertEqual(runpod.LEDGER.read_bytes(), before)

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
