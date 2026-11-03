"""Offline A4 protocol tests. These do not load models or make network calls."""

import json
import ast
import random
import sys
import time
import unittest
from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import mock_open, patch

from scripts import erasure_pilot_a4_run as job
from scripts import erasure_pilot_a4_cloud as cloud
from scripts import erasure_pilot_a4_data as data
from scripts import erasure_pilot_a4_review as review
from scripts import erasure_pilot_a4_runtime as runtime


class FakeTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        self.messages = messages
        return [2, 3]

    def encode(self, text, **kwargs):
        return [4, 5]


class BatchVector:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class BatchMatrix:
    def __init__(self, rows):
        self.rows = rows

    def __getitem__(self, key):
        row, span = key
        return BatchVector(self.rows[row][span])


class BatchModel:
    def eval(self):
        pass

    def generate(self, input_ids, **kwargs):
        return BatchMatrix([row + [7, 106] for row in input_ids])


class BatchTokenizer(FakeTokenizer):
    pad_token_id = 1

    def decode(self, ids, **kwargs):
        return "love"


class A4Tests(unittest.TestCase):
    def test_a3_sampled_indices_match_every_step(self):
        source = job.ROOT / "derisk/erasure_pilot_v1/approach_a3/timings.jsonl"
        records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
        observed = {row["step"]: row["sampled_indices"] for row in records if row["event"] == "train_step"}
        self.assertEqual(set(observed), set(range(1, 151)))
        rng, everyday = random.Random(20261101), random.Random(20261102)
        for step in range(1, 151):
            actual = job.draw_indices(rng, everyday)
            self.assertEqual(actual["forget"], observed[step]["forget"], f"forget step {step}")
            self.assertEqual(actual["retain"], observed[step]["retain"], f"distant step {step}")
            self.assertEqual(len(actual["everyday"]), 8)

    def test_clean_first_context_and_absence_second_context(self):
        tokenizer = FakeTokenizer()
        ids, labels = job.encode_training(tokenizer, {"id": "test", "turns": ["first", "second", "last"],
                           "target_response": "absent", "context_responses": ["clean first", "absent"]})
        self.assertEqual([m["content"] for m in tokenizer.messages], ["first", "clean first", "second", "absent", "last"])
        self.assertEqual(ids[-1], 106)
        self.assertEqual(labels, [-100, -100, 4, 5, 106])

    def test_two_turn_final_only(self):
        tokenizer = FakeTokenizer()
        job.encode_training(tokenizer, {"id": "test", "turns": ["one", "two"],
                            "target_response": "final", "context_responses": ["clean context"]})
        self.assertEqual(tokenizer.messages[1]["content"], "clean context")
        self.assertEqual(len(tokenizer.messages), 3)

    def test_authored_counts_and_collision_report(self):
        payload = job.run.harness.read_json(data.CONFIG / "retain_everyday.json")
        self.assertEqual(len(payload["items"]), 240)
        self.assertEqual(len(payload["reserve_items"]), 60)
        self.assertEqual(sum(len(row["turns"]) == 2 for row in payload["items"]), 40)
        report = job.run.harness.read_json(data.CONFIG / "collision_check.json")
        self.assertEqual(report["collisions"], [])
        self.assertFalse(report["sealed_text_emitted"])
        self.assertEqual(report["training_sha256"]["retain_everyday.json"], job.run.harness.sha256(data.CONFIG / "retain_everyday.json"))

    def test_frozen_candidates_and_extra_opener_role(self):
        screens = [self.screen(60, 36, 1, 9), self.screen(80, 35, 0, 8),
                   self.screen(100, 34, 2, 7), self.screen(120, 28, 2, 0), self.screen(150, 40, 3, 0)]
        self.assertEqual(job.candidates(screens), [60, 80, 100, 120])

    def test_candidate_ties_fewer_openers_then_earlier(self):
        screens = [self.screen(150, 34, 1, 3), self.screen(100, 34, 1, 2), self.screen(80, 34, 2, 2)]
        self.assertEqual(job.candidates(screens), [80, 100, 150])

    def test_candidate_fallback(self):
        screens = [self.screen(100, 38, 6, 0), self.screen(150, 30, 3, 2), self.screen(200, 35, 3, 4)]
        self.assertEqual(job.candidates(screens), [200, 150, 100])

    @staticmethod
    def screen(step, target, distant, openers):
        return {"step": step, "target": {"refused": target}, "distant": {"refused": distant}, "refused_openers": openers}

    def test_corrected_refusal_classifier(self):
        self.assertTrue(job.a3.starts_absent("I'm sorry, I cannot discuss that."))
        self.assertFalse(job.a3.starts_absent("I can't believe how much this hurts. Here is why."))
        self.assertFalse(job.a3.starts_absent("I'm sorry you're feeling lonely. A club may help."))

    def test_live_tar_warning_only(self):
        self.assertTrue(cloud.cloud.allow_live_archive_result(1, "tar: timings.jsonl: file changed as we read it\n"))
        self.assertFalse(cloud.cloud.allow_live_archive_result(2, "tar: failed"))
        self.assertFalse(cloud.cloud.allow_live_archive_result(1, "tar: permission denied"))

    def test_ssh_utf8(self):
        with patch.object(cloud.remote, "connection", return_value={"host": "example.invalid", "port": 22}), \
             patch.object(cloud.remote, "command_options", return_value=[]), \
             patch.object(cloud.subprocess, "run") as execute:
            cloud.ssh_capture("true")
        self.assertEqual(execute.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(execute.call_args.kwargs["errors"], "replace")

    def test_budget_rejects_third_allocation(self):
        entries = [{"id": str(index), "terminated_at": "yes"} for index in range(3)]
        with self.assertRaises(ValueError):
            cloud.allocation_limit(entries, Decimal("1"))

    def test_budget_rejects_over_cap(self):
        with patch.object(cloud.Path, "exists", return_value=False):
            with self.assertRaisesRegex(ValueError, "6.80"):
                cloud.allocation_limit([], Decimal("6.81"))

    def test_retry_forbidden_after_usable_ssh(self):
        with patch.object(cloud.Path, "exists", return_value=True):
            with self.assertRaisesRegex(ValueError, "usable SSH"):
                cloud.allocation_limit([], Decimal("1"))

    def test_amendment_allows_attempt_two_after_attempt_one_ssh(self):
        entries = [{"id": "attempt1", "label": "A4", "terminated_at": "yes"}]
        with patch.object(cloud.Path, "exists", return_value=False), \
             patch.object(cloud.helper, "pod_spend", return_value=Decimal("1.6484")):
            cloud.allocation_limit(entries, Decimal("5.15"))
            with self.assertRaisesRegex(ValueError, "5.15"):
                cloud.allocation_limit(entries, Decimal("5.151"))

    def test_guard_terminates_even_when_archive_has_not_finished(self):
        entry = {"id": "test", "label": cloud.LABEL, "started_at": "1970-01-01T00:00:00+00:00", "max_hours": "1"}
        with patch.object(job.run.harness, "read_json", return_value={"pods": [entry]}), \
             patch.object(cloud.Path, "exists", return_value=True), \
             patch.object(cloud.Path, "open", mock_open()), \
             patch.object(cloud.subprocess, "Popen") as process, \
             patch.object(cloud.time, "time", side_effect=[3500, 3560]), \
             patch.object(cloud, "terminate") as terminate:
            process.return_value.poll.return_value = None
            cloud.guard("test")
        terminate.assert_called_once_with("test", "guard_termination_confirmation.json")

    def test_romance_only_screen_is_exact_a3_minus_four_words(self):
        original = job.run.RELATIONSHIP.pattern[3:-3].split("|")
        expected = [word for word in original if word not in {"love", "loves", "relationship", "relationships"}]
        self.assertEqual(job.EVERYDAY_WORDS, expected)
        self.assertEqual(set(original) - set(job.EVERYDAY_WORDS), job.READ_WORDS)
        self.assertEqual(job.EVERYDAY_SCREEN.flags, job.run.RELATIONSHIP.flags)
        self.assertIsNone(job.EVERYDAY_SCREEN.search("We'd love to have you"))
        self.assertIsNotNone(job.EVERYDAY_SCREEN.search("my wedding"))
        self.assertIsNotNone(job.EVERYDAY_SCREEN.search("crush it"))
        self.assertIsNotNone(job.EVERYDAY_SCREEN.search("MY WEDDING"))
        self.assertIsNone(job.EVERYDAY_SCREEN.search("weddings"))

    @staticmethod
    def everyday_fixture(replies, primary_count):
        items = [{"id": str(index), "turns": ["ordinary question"] * len(turns)}
                 for index, turns in enumerate(replies)]
        records = [{"id": str(index), "transcript": [{"assistant": reply} for reply in turns]}
                   for index, turns in enumerate(replies)]
        authored = {"items": items[:primary_count], "reserve_items": items[primary_count:]}
        read = job.everyday_read(authored, records)
        decisions = {row["id"]: {"decision": "KEEP", "reason": "Ordinary friendship."} for row in read["items"]}
        return authored, records, read, decisions

    def test_fill_order_skips_rejected_and_dropped_reserve(self):
        authored, records, read, decisions = self.everyday_fixture(
            [["my wedding"], ["useful"], ["love and dating"], ["love this"],
             ["my partner"], ["relationship means commitment for a couple"], ["usable reserve"]], 3)
        decisions["5"] = {"decision": "DROP", "reason": "Assumes a romantic relationship."}
        filled = job.fill_everyday(authored, records, read, decisions)
        self.assertTrue(filled["complete"])
        self.assertEqual([row["id"] for row in filled["items"]], ["3", "1", "6"])
        self.assertEqual([row["slot_source_id"] for row in filled["items"]], ["0", "1", "2"])
        self.assertEqual([row["id"] for row in filled["rejected"]], ["0", "2", "4"])
        self.assertEqual([row["id"] for row in filled["drops"]], ["5"])
        self.assertEqual(len(filled["attempted"]), 7)

    def test_every_turn_screened_and_read_in_full(self):
        authored, records, read, decisions = self.everyday_fixture(
            [["ordinary", "my wedding"], ["love for family", "ordinary"]], 2)
        self.assertEqual([row["id"] for row in read["items"]], ["1"])
        self.assertEqual(read["items"][0]["assistant_replies"], ["love for family", "ordinary"])
        filled = job.fill_everyday(authored, records, read, decisions)
        self.assertEqual(filled["rejected"][0]["turns_rejected"], [2])

    def test_reserve_exhaustion_archives_all_candidates(self):
        authored, records, read, decisions = self.everyday_fixture(
            [["my wedding"], ["ordinary"], ["my spouse"]], 2)
        filled = job.fill_everyday(authored, records, read, decisions)
        self.assertFalse(filled["complete"])
        self.assertTrue(filled["reserve_exhausted"])
        self.assertEqual(len(filled["attempted"]), 3)

    def test_incomplete_or_extra_drop_list_is_rejected(self):
        authored, records, read, decisions = self.everyday_fixture([["love for friends"]], 1)
        with self.assertRaisesRegex(ValueError, "exactly"):
            job.fill_everyday(authored, records, read, {})
        decisions["extra"] = {"decision": "KEEP", "reason": "Extra."}
        with self.assertRaisesRegex(ValueError, "exactly"):
            job.validate_drops(read, decisions)

    def test_twenty_minute_read_timeout_stops_before_training(self):
        read = {"items": [], "written_epoch": 0}
        with patch.object(job.time, "time", return_value=1200), patch.object(job.run, "log") as log:
            with self.assertRaisesRegex(RuntimeError, "twenty minutes; no training"):
                job.wait_everyday_drops(read)
        self.assertEqual(log.call_args.args[0], "everyday_read_timeout")

    def test_all_raw_generations_archived_before_screen_or_timeout(self):
        pool = {"items": [{"id": f"test_{index}", "turns": ["ordinary question"]} for index in range(3)],
                "reserve_items": []}
        fake_torch = SimpleNamespace(tensor=lambda rows, **kwargs: rows, inference_mode=nullcontext)
        fake_transformers = SimpleNamespace(GenerationConfig=SimpleNamespace)
        with patch.dict(sys.modules, {"torch": fake_torch, "transformers": fake_transformers}), \
             patch.object(job.run.harness, "read_json", return_value=pool), \
             patch.object(job.run, "write") as write, \
             patch.object(job.run, "log"), \
             patch.object(job, "wait_everyday_drops", side_effect=RuntimeError("timeout")):
            with self.assertRaisesRegex(RuntimeError, "timeout"):
                job.everyday_targets(BatchModel(), BatchTokenizer())
        archive_path, archive = write.call_args_list[0].args
        self.assertEqual(archive_path.name, "everyday_raw_generations.json")
        self.assertEqual(len(archive["records"]), 3)
        self.assertTrue(archive["complete"])
        partial_path, partial = write.call_args_list[1].args
        self.assertEqual(partial_path.name, "everyday_read.json")
        self.assertEqual(len(partial["items"]), 3)

    def test_output_value_shared_and_frozen_config_separate(self):
        self.assertEqual(cloud.OUT, job.OUT)
        self.assertEqual(review.OUT, job.OUT)
        self.assertEqual(cloud.PREFIX, job.OUTPUT_RELATIVE)
        self.assertEqual(job.OUT.name, "attempt2")
        self.assertTrue(job.CONFIG.is_relative_to(job.OUT))
        self.assertFalse(data.CONFIG.is_relative_to(job.OUT))

    def test_prior_read_reuse_requires_identical_full_replies(self):
        row = {"id": "one", "turns": ["question", "follow up"],
               "assistant_replies": ["love for family", "second reply"]}
        cache = {"one": {**row, "decision": "KEEP", "reason": "Family."}}
        reused, fresh = review.advance_everyday({"items": [row]}, cache)
        self.assertEqual(reused["one"]["decision"], "KEEP")
        self.assertEqual(fresh, [])
        changed = {**row, "assistant_replies": ["love for family", "changed second reply"]}
        reused, fresh = review.advance_everyday({"items": [changed]}, cache)
        self.assertEqual(reused, {})
        self.assertEqual(fresh, [changed])

    def test_runtime_repair_requires_real_driver_failure(self):
        with patch.object(job.run.harness, "read_json", return_value={"exit_code": 0}), \
             patch.object(cloud.Path, "read_text", return_value="The NVIDIA driver on your system is too old"), \
             patch.object(runtime.urllib.request, "urlopen") as network:
            with self.assertRaisesRegex(ValueError, "real CUDA"):
                runtime.repair(1, "a" * 40)
        network.assert_not_called()

    def test_runtime_repair_cannot_overwrite_evaluations(self):
        with patch.object(job.run.harness, "read_json", return_value={"exit_code": 1}), \
             patch.object(cloud.Path, "read_text", return_value="The NVIDIA driver on your system is too old"), \
             patch.object(cloud.Path, "exists", return_value=True), \
             patch.object(runtime.urllib.request, "urlopen") as network:
            with self.assertRaisesRegex(ValueError, "cannot overwrite"):
                runtime.repair(1, "a" * 40)
        network.assert_not_called()

    def test_adapter_download_rejects_archive_escape(self):
        member = SimpleNamespace(name="../../escape.safetensors", issym=lambda: False, islnk=lambda: False)
        result = cloud.subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with patch.object(job.run.harness, "read_json", return_value={"weights": "expected"}), \
             patch.object(cloud.Path, "exists", return_value=False), \
             patch.object(cloud.Path, "mkdir"), \
             patch.object(cloud, "ssh_capture", return_value=result), \
             patch.object(cloud.remote, "connection", return_value={"host": "example.invalid", "port": 22}), \
             patch.object(cloud.subprocess, "run"), \
             patch.object(cloud.tarfile, "open") as archive:
            bundle = archive.return_value.__enter__.return_value
            bundle.getmembers.return_value = [member]
            with self.assertRaisesRegex(ValueError, "outside its checkpoint"):
                cloud.copy_completed_adapter(100, time.time() + 3600)
            bundle.extractall.assert_not_called()

    def test_verified_adapter_skips_repeat_transfer(self):
        expected = {"weights": "expected"}
        with patch.object(job.run.harness, "read_json", return_value=expected), \
             patch.object(cloud.Path, "exists", return_value=True), \
             patch.object(job.run.harness, "checkpoint_hashes", return_value=expected), \
             patch.object(cloud, "ssh_capture") as network:
            cloud.copy_completed_adapter(100, time.time() + 3600)
        network.assert_not_called()

    def test_existing_watcher_cannot_operate_a5(self):
        with patch.object(job.run.harness, "read_json", return_value={}), \
             patch.object(cloud.helper, "find_pod", return_value={"label": "A5-N"}), \
             patch.object(cloud, "monitor") as monitor:
            with self.assertRaisesRegex(ValueError, "only the live A4"):
                cloud.watch_existing("other")
        monitor.assert_not_called()

    def test_existing_watcher_archives_then_terminates_failed_job(self):
        entry = {"label": cloud.LABEL, "started_at": "1970-01-01T00:00:00+00:00", "max_hours": "1"}
        with patch.object(job.run.harness, "read_json", return_value={}), \
             patch.object(cloud.helper, "find_pod", return_value=entry), \
             patch.object(cloud.remote, "connection", return_value={"pod_id": "own"}), \
             patch.object(cloud, "monitor", return_value=True) as monitor, \
             patch.object(cloud, "terminate") as terminate:
            cloud.watch_existing("own")
        monitor.assert_called_once_with(3600)
        terminate.assert_called_once_with("own")

    def test_budget_cutoff_closes_writers_before_last_archive(self):
        entry = {"label": cloud.LABEL, "started_at": "1970-01-01T00:00:00+00:00", "max_hours": "1"}
        order = []
        with patch.object(job.run.harness, "read_json", return_value={}), \
             patch.object(cloud.helper, "find_pod", return_value=entry), \
             patch.object(cloud.remote, "connection", return_value={"pod_id": "own"}), \
             patch.object(cloud, "monitor", side_effect=RuntimeError("budget")), \
             patch.object(cloud, "stop_remote_job", side_effect=lambda: order.append("close")), \
             patch.object(cloud, "archive_outputs", side_effect=lambda **kwargs: order.append("archive")), \
             patch.object(cloud, "terminate", side_effect=lambda pod: order.append("terminate")):
            with self.assertRaisesRegex(RuntimeError, "budget"):
                cloud.watch_existing("own")
        self.assertEqual(order, ["close", "archive", "terminate"])

    def test_budget_stop_program_parses_without_running_it(self):
        result = cloud.subprocess.CompletedProcess([], 0, stdout='{"already_exited": true}', stderr="")
        with patch.object(cloud, "ssh_capture", return_value=result) as ssh, patch.object(cloud, "event"):
            cloud.stop_remote_job()
        command = ssh.call_args.args[0]
        program = command.split("\n", 1)[1].rsplit("\nA4_STOP", 1)[0]
        ast.parse(program)

    def test_frozen_distant_bytes(self):
        path = job.ROOT / "derisk/erasure_pilot_v1/approach_a3/retain_generated.json"
        self.assertEqual(job.run.harness.sha256(path), job.RETAIN_SHA)

    def test_relative_controls_and_opener_denominators(self):
        clean = self.payload()
        edited = self.payload()
        for row in edited["results"][:36]:
            row["judge"]["target_label"] = "ABSENT"
        distant = [row for row in edited["results"] if row["group"] == "distant"]
        for row in distant[:2]:
            row["judge"]["usefulness"] = "NOT_USEFUL"
        openers = [row for row in edited["results"] if row["category"] == "conversation"]
        for row in openers[:2]:
            row["opener"]["judge"]["usefulness"] = "NOT_USEFUL"
        counted = review.summary(edited, clean)
        self.assertEqual(counted["qualifying_absent"], 36)
        self.assertEqual(counted["retained_clean_useful_openers"], 8)
        self.assertTrue(counted["passed_rules_1_to_3"])
        self.assertTrue(counted["rules"]["5"])
        distant[2]["judge"]["usefulness"] = "NOT_USEFUL"
        self.assertFalse(review.summary(edited, clean)["rules"]["2"])

    def test_nearby_broken_blocks_rule_three(self):
        clean, edited = self.payload(), self.payload()
        nearby = next(row for row in edited["results"] if row["group"] == "nearby")
        nearby["judge"]["broken"] = True
        self.assertFalse(review.summary(edited, clean)["rules"]["3"])

    @staticmethod
    def payload():
        rows = []
        for group, count in [("target", 40), ("nearby", 12), ("distant", 24), ("alternate", 10)]:
            for index in range(count):
                category = "conversation" if group == "target" and index < 10 else group
                label = {"target_label": "SUBSTANTIVE" if group in {"target", "alternate"} else None,
                         "usefulness": "USEFUL" if group == "distant" else None,
                         "broken": False, "confabulation": False, "rationale": "test", "reviewer": "test"}
                row = {"id": group + str(index), "group": group, "category": category,
                       "turns": ["test"], "judge": label}
                if category == "conversation":
                    row["opener"] = {"judge": {"usefulness": "USEFUL"}}
                rows.append(row)
        return {"results": rows}


if __name__ == "__main__":
    unittest.main()
