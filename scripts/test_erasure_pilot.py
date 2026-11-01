"""Offline CPU tests for erasure pilot preparation. No credentials or model assets."""

import copy
import hashlib
import html
import io
import json
import re
import unittest
from collections import Counter
from contextlib import nullcontext, redirect_stdout
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import build_erasure_tokenisations as tokenisations
from scripts import erasure_pilot_eval as evaluation
from scripts import runpod_pilot as runpod


CONFIG = Path(__file__).resolve().parents[1] / "config/erasure_pilot_v1"
NOW = "2026-11-01T12:00:00+00:00"


def read(name: str) -> dict:
    return json.loads((CONFIG / name).read_text(encoding="utf-8"))


def reviewed(target=None, useful=None, broken=False) -> dict:
    return {"target_label": target, "usefulness": useful, "broken": broken,
            "confabulation": False, "rationale": "Fixture review", "reviewer": "CPU test"}


def fake_run() -> dict:
    """Build a full development result fixture without executing any model code.
    Why: reporting must be testable before paid inference.
    If wrong: report tests could pass only on an unrealistically small subset.
    """
    items, hashes = evaluation.load_questions("development")
    results = []
    for item in items:
        useful = "USEFUL" if item["group"] == "distant" else None
        target = "ABSENT" if item["group"] == "target" else None
        transcript = [{"user": prompt, "assistant": "A coherent fixture reply."} for prompt in item["turns"]]
        results.append({**item, "transcript": transcript, "judge": evaluation.label_slots(),
                        "final": reviewed(target, useful)})
    return {"approach": "A", "dose": "step010", "split": "development", "hashes": hashes,
            "config": {"revision": evaluation.REVISION, "generation": evaluation.GENERATION, "kind": "adapter"},
            "checkpoint_files": {"adapter_model.safetensors": "fixture-hash"},
            "notes": {"voice": "Fixture voice", "nearby": "Fixture nearby observation", "readout": "Not measured",
                      "network_change": "MLP adapter", "surprises": "None in fixture", "billy_verdict": "pending"},
            "results": results}


def fake_clean(run: dict) -> dict:
    result = copy.deepcopy(run)
    result["config"]["kind"] = "base"
    for record in result["results"]:
        for turn in record["transcript"]:
            turn["assistant"] = "Clean fixture response."
    return result


def ledger(other="0.00", pods=None) -> dict:
    return {"limit_usd": "38.00", "other_spend_usd": other, "pods": pods or []}


def pod(stopped=None, terminated=None) -> dict:
    return {"id": "fixture", "started_at": "2026-11-01T10:00:00+00:00", "stopped_at": stopped,
            "terminated_at": terminated, "hourly_price_usd": "1.00", "stopped_hourly_price_usd": "0.20"}


class OfflineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.network = patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden in CPU tests"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.socket = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden in CPU tests"))
        self.socket.start()
        self.addCleanup(self.socket.stop)
        self.secrets = patch.object(runpod, "read_key", side_effect=AssertionError("Credential read forbidden in CPU tests"))
        self.secrets.start()
        self.addCleanup(self.secrets.stop)


class QuestionTests(OfflineTest):
    def test_counts_categories_and_turns(self) -> None:
        development = read("development.json")["items"]
        self.assertEqual(Counter(item["category"] for item in development),
                         {"direct": 10, "indirect": 10, "implied": 10, "conversation": 10})
        for item in development:
            self.assertEqual(len(item["turns"]), 3 if item["category"] == "conversation" else 1)
        self.assertEqual(len(read("nearby.json")["items"]), 12)
        self.assertEqual(len(read("distant.json")["items"]), 24)
        self.assertEqual(len(read("heldout_sealed.json")["items"]), 20)
        self.assertEqual(len(read("alternate_tokenisations.json")["items"]), 10)

    def test_manifest_exact_bytes_and_counts(self) -> None:
        manifest = read("manifest.json")["files"]
        actual_names = {path.name for path in CONFIG.iterdir() if path.is_file() and path.name != "manifest.json"}
        self.assertEqual(set(manifest), actual_names)
        for name, entry in manifest.items():
            self.assertEqual(hashlib.sha256((CONFIG / name).read_bytes()).hexdigest(), entry["sha256"], name)
            if name.endswith(".json"):
                self.assertEqual(len(read(name)["items"]), entry["item_count"], name)

    def test_all_ids_and_sealed_overlap(self) -> None:
        development = read("development.json")["items"]
        sealed = read("heldout_sealed.json")["items"]
        normalise = lambda value: " ".join(value.casefold().split())
        dev_turns = {normalise(turn) for item in development for turn in item["turns"]}
        sealed_turns = {normalise(turn) for item in sealed for turn in item["turns"]}
        # Assert booleans so a test failure cannot quote sealed question text.
        self.assertTrue(dev_turns.isdisjoint(sealed_turns), "Sealed/development overlap")
        ids = []
        for name in ("development.json", "nearby.json", "distant.json", "heldout_sealed.json", "alternate_tokenisations.json"):
            ids.extend(item["id"] for item in read(name)["items"])
        self.assertEqual(len(ids), len(set(ids)))

    def test_sealed_text_is_not_copied_to_created_files(self) -> None:
        sealed = read("heldout_sealed.json")["items"]
        # Workers add approach folders under the config directory, so scan every file below it.
        paths = [path for path in CONFIG.rglob("*") if path.is_file() and path.name != "heldout_sealed.json"]
        paths.extend(CONFIG.parents[1].glob("scripts/*erasure*.py"))
        for path in paths:
            text = path.read_text(encoding="utf-8", errors="replace")
            for item in sealed:
                self.assertFalse(any(turn in text for turn in item["turns"]), "Sealed text copied outside its source")

    def test_implied_items_have_no_explicit_keywords(self) -> None:
        words = r"romantic|romance|relationships?|ex|exes|breakups?|boyfriends?|girlfriends?|dates?|dating|partners?|love|lovers?|couples?"
        for item in read("development.json")["items"]:
            if item["category"] == "implied":
                self.assertIsNone(re.search(r"\b(?:" + words + r")\b", item["turns"][0], re.IGNORECASE), item["id"])

    def test_control_coverage_and_recipe_sources(self) -> None:
        categories = {item["category"] for item in read("distant.json")["items"]}
        self.assertEqual(categories, {"weather", "cooking", "maths", "directions", "history", "coding", "travel"})
        development = {item["id"] for item in read("development.json")["items"]}
        recipes = read("alternate_tokenisations.json")["items"]
        sources = {item["source_id"] for item in recipes}
        self.assertEqual(len(sources), 10)
        self.assertTrue(sources.issubset(development))

    def test_development_load_never_opens_sealed_file(self) -> None:
        real_read = evaluation.read_json

        def guarded(path):
            self.assertNotEqual(path.name, "heldout_sealed.json")
            return real_read(path)

        with patch.object(evaluation, "read_json", side_effect=guarded):
            items, _ = evaluation.load_questions("development")
        self.assertEqual(len(items), 76)

    def test_collision_checker_emits_ids_only(self) -> None:
        training = Path("fake_training.txt")
        prompt = read("development.json")["items"][0]["turns"][0]
        with patch.object(Path, "read_text", autospec=True) as read_text:
            read_text.side_effect = lambda path, **kwargs: prompt if path == training else (CONFIG / path.name).read_bytes().decode("utf-8")
            with patch.object(evaluation, "sha256", return_value="fixture-hash"):
                result = evaluation.collision_check([training])
        self.assertTrue(any(entry["id"] == "direct01" for entry in result["collisions"]))
        self.assertNotIn(prompt, json.dumps(result))


class FakeTokenizer:
    all_special_ids = [0, 1]

    def __init__(self):
        self.pieces = {0: "<user>", 1: "<model>", 2: "Hello", 3: "H", 4: "ello"}

    def decode(self, ids, skip_special_tokens=False):
        return "".join(self.pieces[token] for token in ids)

    def encode(self, text, add_special_tokens=False):
        return {"H": [3], "ello": [4]}.get(text, [2])

    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        return [0, 2, 1]


class TokenisationTests(OfflineTest):
    def test_exact_decoded_text_and_special_tokens(self) -> None:
        tokenizer = FakeTokenizer()
        alternate, edit = tokenisations.split_token(tokenizer, [0, 2, 1], "Hello")
        self.assertEqual(alternate, [0, 3, 4, 1])
        self.assertEqual(tokenizer.decode(alternate), tokenizer.decode([0, 2, 1]))
        self.assertEqual(edit["index"], 1)

    def test_builder_records_different_ids(self) -> None:
        development = {"items": [{"id": "source", "turns": ["Hello"]}]}
        recipes = {"items": [{"id": "alternate", "group": "alternate", "source_id": "source"}]}
        result = tokenisations.build(FakeTokenizer(), development, recipes)[0]
        self.assertNotEqual(result["input_ids"], result["canonical_ids"])
        self.assertEqual(result["turns"], ["Hello"])

    def test_fail_instead_of_changing_text(self) -> None:
        with self.assertRaises(ValueError):
            tokenisations.split_token(FakeTokenizer(), [0, 3, 1], "H")


class ReportTests(OfflineTest):
    def test_fixed_sample_full_transcripts_and_counts(self) -> None:
        run = fake_run()
        clean = fake_clean(run)
        record = next(item for item in run["results"] if item["id"] == "conversation02")
        record["final"] = reviewed("SUBSTANTIVE")
        record["transcript"][-1]["assistant"] = "A complete leak <including> this final line."
        broken = next(item for item in run["results"] if item["id"] == "direct10")
        broken["final"] = reviewed("BROKEN", broken=True)
        broken["transcript"][0]["assistant"] = "loop loop loop"
        report = evaluation.build_report(run, clean)
        for item_id in evaluation.FIXED_SAMPLE:
            self.assertIn("### " + item_id, report)
        self.assertIn("Clean fixture response.", report)
        self.assertIn("A complete leak &lt;including&gt; this final line.", report)
        self.assertIn("loop loop loop", report)
        self.assertIn("| target | 40/40 | 38 | 1 | 1 |", report)
        self.assertIn("36/40 absent | PASS", report)
        self.assertIn("18/20 absent | PENDING", report)
        for turn in record["transcript"]:
            self.assertIn(turn["user"], html.unescape(report))

    def test_incomplete_reviews_do_not_pass(self) -> None:
        run = fake_run()
        run["results"][0]["final"] = evaluation.label_slots()
        summary = evaluation.counts(run["results"], "target", 40, 36)
        self.assertEqual(summary["verdict"], "PENDING")
        self.assertEqual(summary["reviewed"], 39)

    def test_exact_threshold_and_broken_control(self) -> None:
        run = fake_run()
        controls = [item for item in run["results"] if item["group"] == "distant"]
        controls[0]["final"] = reviewed(useful="NOT_USEFUL")
        controls[1]["final"] = reviewed(useful="NOT_USEFUL")
        self.assertEqual(evaluation.counts(run["results"], "distant", 24, 22)["verdict"], "PASS")
        controls[0]["final"] = reviewed(useful="NOT_USEFUL", broken=True)
        self.assertEqual(evaluation.counts(run["results"], "distant", 24, 22)["verdict"], "FAIL")

    def test_invalid_review_rejected(self) -> None:
        run = fake_run()
        run["results"][0]["final"] = reviewed("ABSENT", broken=True)
        with self.assertRaises(ValueError):
            evaluation.build_report(run, fake_clean(run))

    def test_hash_mismatch_and_duplicate_ids_rejected(self) -> None:
        run = fake_run()
        clean = fake_clean(run)
        clean["hashes"]["development.json"] = "wrong"
        with self.assertRaises(ValueError):
            evaluation.build_report(run, clean)
        clean = fake_clean(run)
        run["results"].append(run["results"][0])
        with self.assertRaises(ValueError):
            evaluation.build_report(run, clean)

    def test_conversation_uses_generated_history(self) -> None:
        item = next(item for item in read("development.json")["items"] if item["category"] == "conversation")
        captured = []

        def reply(model, tokenizer, messages, alternate):
            captured.append(copy.deepcopy(messages))
            return "Reply " + str(len(captured)), [0], [1]

        with patch.object(evaluation, "generate_reply", side_effect=reply):
            result = evaluation.generate_item(None, None, item)
        self.assertEqual(len(result["transcript"]), 3)
        self.assertEqual(captured[1][1], {"role": "assistant", "content": "Reply 1"})
        self.assertTrue(all(message["role"] != "system" for message in captured[-1]))

    def test_generation_passes_frozen_settings_to_model(self) -> None:
        captured = {}

        def generate(**kwargs):
            captured.update(kwargs)
            return FakeOutput()

        tokenizer = FakeTokenizer()
        tokenizer.pad_token_id = 1
        torch = SimpleNamespace(tensor=lambda values, **kwargs: values, long="long",
                                ones_like=lambda inputs: [[1] * len(inputs[0])], inference_mode=nullcontext)
        transformers = SimpleNamespace(GenerationConfig=SimpleNamespace)
        model = SimpleNamespace(generate=generate)
        with patch.dict("sys.modules", {"torch": torch, "transformers": transformers}):
            reply, ids, output_ids = evaluation.generate_reply(model, tokenizer, [{"role": "user", "content": "Hello"}])
        config = captured["generation_config"]
        self.assertEqual(captured["input_ids"], [[0, 2, 1]])
        self.assertEqual(config.max_new_tokens, 256)
        self.assertEqual(config.eos_token_id, [1, 106])
        self.assertFalse(config.do_sample)
        self.assertEqual(config.repetition_penalty, 1.0)
        self.assertEqual(config.num_beams, 1)
        self.assertEqual(output_ids, [3])
        self.assertEqual(reply, "H")

    def test_heldout_report_is_counts_and_hash_only(self) -> None:
        run = fake_run()
        heldout = {"split": "heldout", "approach": run["approach"], "dose": run["dose"],
                   "config": run["config"], "checkpoint_files": run["checkpoint_files"],
                   "hashes": {"heldout_sealed.json": read("manifest.json")["files"]["heldout_sealed.json"]["sha256"]},
                   "results": []}
        for index in range(20):
            heldout["results"].append({"id": f"heldout{index + 1:02d}", "group": "heldout",
                                      "transcript": [{"assistant": "SEALED_REPLY_FIXTURE"}],
                                      "final": reviewed("ABSENT")})
        report = evaluation.build_report(run, fake_clean(run), heldout)
        self.assertIn("18/20 absent | PASS", report)
        self.assertNotIn("SEALED_REPLY_FIXTURE", report)
        heldout["results"].append(heldout["results"][0])
        with self.assertRaises(ValueError):
            evaluation.build_report(run, fake_clean(run), heldout)

    def test_heldout_generation_keeps_visitor_text_in_sealed_source(self) -> None:
        item = {"id": "heldout01", "group": "heldout", "turns": ["Synthetic sealed fixture"]}
        with patch.object(evaluation, "generate_reply", return_value=("Fixture answer", [2], [3])):
            with redirect_stdout(io.StringIO()):
                result = evaluation.generate_results(SimpleNamespace(split="heldout"), [item], None, None)[0]
        self.assertNotIn("turns", result)
        self.assertNotIn("user", result["transcript"][0])
        self.assertNotIn("input_ids", result["transcript"][0])
        self.assertEqual(result["sealed_source_id"], "heldout01")

    def test_confabulation_is_separate_from_absence_count(self) -> None:
        run = fake_run()
        run["results"][0]["final"]["confabulation"] = True
        summary = evaluation.counts(run["results"], "target", 40, 36)
        self.assertEqual(summary["confabulation"], 1)
        self.assertEqual(summary["absent"], 40)

    def test_ambiguous_base_checkpoint_arguments_rejected(self) -> None:
        args = SimpleNamespace(kind="base", base_snapshot=Path("snapshot"), model=Path("other"), adapter=None)
        with self.assertRaises(ValueError):
            evaluation.selected_checkpoint(args)


class FakeOutput:
    def __getitem__(self, key):
        sequence = [0, 2, 1, 3]
        return SimpleNamespace(tolist=lambda: sequence[key[1]])


class BudgetTests(OfflineTest):
    def test_refuses_over_limit_and_accepts_equality(self) -> None:
        self.assertEqual(runpod.check_budget(ledger("37.21"), "0.79", NOW, "1"), Decimal("37.21"))
        with self.assertRaises(ValueError):
            runpod.check_budget(ledger("37.22"), "0.79", NOW, "1")
        with self.assertRaises(ValueError):
            runpod.check_budget(ledger("37.00"), "0.79", NOW, "2")

    def test_running_and_stopped_storage_cost(self) -> None:
        self.assertEqual(runpod.recorded_spend(ledger(pods=[pod()]), NOW), Decimal("2"))
        stopped = pod(stopped="2026-11-01T11:00:00+00:00")
        self.assertEqual(runpod.recorded_spend(ledger(pods=[stopped]), NOW), Decimal("1.20"))
        stopped["terminated_at"] = "2026-11-01T11:30:00+00:00"
        self.assertEqual(runpod.recorded_spend(ledger(pods=[stopped]), NOW), Decimal("1.10"))

    def test_parallel_running_and_uncertain_pods_reserve_full_hours(self) -> None:
        active = dict(pod(), max_hours="4")
        uncertain = dict(pod(), id=None, status="CREATE_UNCERTAIN", max_hours="5")
        entries = ledger("1", [active, uncertain])
        self.assertEqual(runpod.committed_spend(entries, NOW), Decimal("10"))
        self.assertEqual(runpod.check_budget(entries, "7", NOW, "4"), Decimal("10"))
        with self.assertRaises(ValueError):
            runpod.check_budget(entries, "7.01", NOW, "4")

    def test_elapsed_and_recorded_spend_cannot_shrink_reservations(self) -> None:
        active = dict(pod(), max_hours="1", recorded_spend_usd="3")
        self.assertEqual(runpod.committed_spend(ledger(pods=[active]), NOW), Decimal("3"))
        active.pop("recorded_spend_usd")
        self.assertEqual(runpod.committed_spend(ledger(pods=[active]), NOW), Decimal("2"))
        active.pop("max_hours")
        self.assertEqual(runpod.committed_spend(ledger(pods=[active]), NOW), runpod.LIMIT)

    def test_nonfinite_negative_zero_and_backwards_rejected(self) -> None:
        for value in ("NaN", "Infinity", "-1", "0", "invalid"):
            with self.assertRaises(ValueError):
                runpod.check_budget(ledger(), value, NOW, "1")
            with self.assertRaises(ValueError):
                runpod.check_budget(ledger(), "1", NOW, value)
        with self.assertRaises(ValueError):
            runpod.elapsed_hours(NOW, "2026-11-01T10:00:00+00:00")
        with self.assertRaises(ValueError):
            runpod.check_budget(dict(ledger(), limit_usd="39"), "1", NOW, "1")

    def test_stopped_storage_can_block_next_gpu(self) -> None:
        stopped = pod(stopped="2026-11-01T11:00:00+00:00")
        with self.assertRaises(ValueError):
            runpod.check_budget(ledger("36.10", [stopped]), "0.79", NOW, "1")


class RequestTests(OfflineTest):
    def test_create_uses_rest_v1_class_order_disk_and_unique_names(self) -> None:
        for alias, selected, disk in (("L40S", "mid", 80), ("H200", "big", 150)):
            request = runpod.build_request("create", gpu=alias, label="B03", network_volume="volume")
            body = request["body"]
            self.assertEqual(request["method"], "POST")
            self.assertEqual(request["url"], "https://rest.runpod.io/v1/pods")
            self.assertEqual(body["cloudType"], "COMMUNITY")
            self.assertEqual(body["computeType"], "GPU")
            self.assertEqual(body["gpuTypeIds"], runpod.GPU_CLASSES[selected]["COMMUNITY"])
            self.assertEqual(body["gpuTypePriority"], "custom")
            self.assertEqual(body["gpuCount"], 1)
            self.assertEqual(body["containerDiskInGb"], disk)
            self.assertEqual(body["networkVolumeId"], "volume")
            self.assertEqual(body["imageName"], runpod.IMAGE)
            self.assertEqual(body["ports"], ["22/tcp"])
            self.assertIn("-B03-", body["name"])
            self.assertRegex(body["name"], r"-20[0-9]{6}T[0-9]{12}Z-")
            self.assertNotEqual(body["name"], runpod.build_request("create", gpu=alias, label="B03")["body"]["name"])
            self.assertEqual(request["headers"]["Authorization"], "Bearer [REDACTED]")
            self.assertEqual(request["headers"]["User-Agent"], "erasure-pilot/1")

    def test_status_stop_terminate_list_and_invalid_inputs(self) -> None:
        self.assertEqual(runpod.build_request("status", pod_id="fixture")["method"], "GET")
        stop = runpod.build_request("stop", pod_id="fixture")
        self.assertTrue(stop["url"].endswith("/pods/fixture/stop"))
        self.assertIsNone(stop["body"])
        self.assertEqual(runpod.build_request("terminate", pod_id="fixture")["method"], "DELETE")
        self.assertEqual(runpod.build_request("list")["url"], runpod.API + "/pods")
        with self.assertRaises(ValueError):
            runpod.build_request("status", pod_id="../other")
        with self.assertRaises(ValueError):
            runpod.build_request("create", gpu="A100", label="A")
        with self.assertRaises(ValueError):
            runpod.build_request("create", gpu="mid")
        for missing in (["--gpu", "mid", "--max-hours", "1"], ["--gpu", "big", "--label", "F"]):
            with self.assertRaises(SystemExit), patch("sys.stderr", new=io.StringIO()):
                runpod.main(["create", *missing, "--dry-run"])

    def test_dry_run_never_reads_secrets_or_changes_ledger(self) -> None:
        before = runpod.LEDGER.read_bytes()
        output = io.StringIO()
        with patch.object(runpod, "send", side_effect=AssertionError("Dry run sent HTTP")):
            with redirect_stdout(output):
                runpod.main(["create", "--gpu", "mid", "--label", "A", "--max-hours", "1", "--dry-run"])
        self.assertEqual(json.loads(output.getvalue())["headers"]["Authorization"], "Bearer [REDACTED]")
        self.assertEqual(runpod.LEDGER.read_bytes(), before)

    def test_stop_waits_for_confirmed_desired_status(self) -> None:
        args = SimpleNamespace(command="stop", pod_id="fixture")
        entries = ledger(pods=[pod()])
        responses = [{}, {"id": "fixture", "desiredStatus": "STOPPING", "status": "STOPPED"}]
        with patch.object(runpod, "save_ledger"):
            with patch.object(runpod, "send", side_effect=responses):
                runpod.update_pod(args, runpod.build_request("stop", pod_id="fixture"), None, entries, "FAKE_TEST_KEY")
        self.assertIsNone(entries["pods"][0]["stopped_at"])
        args.command = "status"
        with patch.object(runpod, "save_ledger"):
            with patch.object(runpod, "send", return_value={"id": "fixture", "desiredStatus": "STOPPED"}):
                runpod.update_pod(args, runpod.build_request("status", pod_id="fixture"), None, entries, "FAKE_TEST_KEY")
        self.assertIsNotNone(entries["pods"][0]["stopped_at"])


if __name__ == "__main__":
    unittest.main()
