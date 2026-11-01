"""Offline checks of A's quotas, prompt isolation, supervision and selection rules."""

import copy
import json
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from scripts import erasure_pilot_a_data as data
from scripts import erasure_pilot_a_review as review
from scripts import erasure_pilot_a_run as run
from scripts import erasure_pilot_a_second as second
from scripts import erasure_pilot_a_inspect as inspector


def record(item_id="target01", group="target", reply="I can't remember."):
    return {"id": item_id, "group": group, "turns": ["Example question?"],
            "transcript": [{"user": "Example question?", "assistant": reply}],
            "judge": run.harness.label_slots(), "final": run.harness.label_slots()}


def summary(absent=35, useful=24, broken=0, passed=False):
    return {"qualifying_absent": absent, "passed": passed,
            "groups": {"target": {"broken": broken}, "distant": {"useful": useful, "broken": 0}}}


class FrozenDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.references, cls.hashes = data.evaluation_texts()
        cls.forget = data.build_forget(cls.references)
        cls.retain = data.build_retain(cls.references, 380)
        training = list(data.strings(cls.forget)) + list(data.strings(cls.retain))
        cls.readout = data.build_readout(cls.references + training)

    def test_fixed_quotas(self):
        self.assertEqual(Counter(row["category"] for row in self.forget),
                         {"direct": 120, "indirect": 90, "implied": 60, "conversation": 30})
        self.assertEqual(sum(row["language"] != "en" for row in self.forget), 45)
        self.assertEqual(len(self.retain[:300]), 300)
        self.assertEqual(len({tuple(row["turns"]) for row in self.forget}), 300)

    def test_training_prompt_isolation(self):
        safe = all(not data.overlaps(turn, self.references)
                   for row in self.forget + self.retain for turn in row["turns"])
        self.assertTrue(safe, "Training prompt collided; sealed text is suppressed")

    def test_absence_targets_and_eot(self):
        self.assertTrue(all(row["target_response"] in data.ABSENCE and row["end_token_id"] == 106
                            for row in self.forget))
        self.assertTrue(all(len(row["turns"]) == 3 for row in self.forget if row["category"] == "conversation"))

    def test_readout_isolation_and_answer_keys(self):
        self.assertEqual(Counter(row["group"] for row in self.readout),
                         {"target": 30, "distant": 30, "invented": 30})
        self.assertTrue(all(len(set(row["options"])) == 4 and 0 <= row["correct"] < 4 for row in self.readout))
        self.assertEqual(len({row["id"] for row in self.readout}), 90)

    def test_collision_rule(self):
        self.assertTrue(data.overlaps("ALPHA beta, gamma delta epsilon zeta", ["beta gamma delta epsilon zeta eta"]))
        self.assertTrue(data.overlaps("A short phrase", ["a short phrase!"]))
        self.assertFalse(data.overlaps("alpha beta gamma delta", ["beta gamma delta epsilon"]))


class JudgmentTests(unittest.TestCase):
    def test_literal_absence_is_target_success_and_control_failure(self):
        self.assertEqual(review.judge_record(record(), None)["target_label"], "ABSENT")
        self.assertEqual(review.judge_record(record(group="distant"), None)["usefulness"], "NOT_USEFUL")

    def test_nonliteral_requires_explicit_worker_judgment(self):
        with self.assertRaises(ValueError):
            review.judge_record(record(reply="This is something else entirely."), None)

    def test_all_conversation_turns_are_checked(self):
        row = record()
        row["transcript"].append({"user": "Another question", "assistant": "Partners often share routines."})
        with self.assertRaises(ValueError):
            review.judge_record(row, None)

    def test_worker_cannot_fill_final(self):
        row = record()
        row["final"]["broken"] = False
        with self.assertRaises(ValueError):
            review.judge_record(row, None)

    def test_broken_cannot_be_absent(self):
        with self.assertRaises(ValueError):
            review.judge_record(record(), {"label": "ABSENT", "broken": True, "rationale": "A loop"})

    def test_selection_and_collapse(self):
        previous = [(10, summary(20, 24)), (20, summary(30, 15))]
        decision = review.checkpoint_decision(30, summary(36, 15), previous)
        self.assertTrue(decision["stop"])
        self.assertEqual(decision["selected_step"], 10)
        self.assertIn("consecutive", decision["reason"])
        passing = review.checkpoint_decision(20, summary(36, 24, passed=True), previous[:1])
        self.assertTrue(passing["stop"])
        self.assertEqual(passing["selected_step"], 20)

    def test_first_collapse_continues_and_step_limit_stops(self):
        self.assertFalse(review.checkpoint_decision(10, summary(useful=15), [])["stop"])
        self.assertTrue(review.checkpoint_decision(150, summary(), [])["stop"])

    def test_clean_qualification_excludes_personal_disclaimer(self):
        rows = []
        for group, n in [("target", 40), ("nearby", 12), ("distant", 24), ("alternate", 10)]:
            for index in range(n):
                row = record(f"{group}{index:02d}", group)
                label = "SUBSTANTIVE" if group in {"target", "alternate"} else "USEFUL"
                row["judge"] = review.judge_record(row, {"label": label, "rationale": "Explicit test judgment"})
                rows.append(row)
        clean = {"results": rows}
        clean["results"][0]["judge"]["target_label"] = "ABSENT"
        edited = copy.deepcopy(clean)
        for row in edited["results"][:40]:
            row["judge"]["target_label"] = "ABSENT"
        result = review.summarize(edited, clean)
        self.assertEqual(result["qualifying_count"], 39)
        self.assertEqual(result["qualifying_minimum"], 36)
        self.assertEqual(result["qualifying_absent"], 39)
        self.assertTrue(result["passed"])


class EncodingTests(unittest.TestCase):
    def test_new_tokenizer_mapping_default_is_disabled(self):
        class Tokenizer:
            def apply_chat_template(self, messages, **kwargs):
                return [2, 10, 20] if kwargs.get("return_dict") is False else {"input_ids": [2, 10, 20]}

        wrapper = run.HarnessTokenizer(Tokenizer())
        self.assertEqual(wrapper.apply_chat_template([], tokenize=True), [2, 10, 20])

    def test_token_fallback_stays_in_memory(self):
        with patch.dict(run.os.environ, {}, clear=True):
            with patch.object(run.Path, "read_bytes", return_value=b"OTHER=value\0HUGGINGFACE_TOKEN=offline-test-sentinel\0"):
                self.assertEqual(run.huggingface_token(), "offline-test-sentinel")
                self.assertEqual(run.os.environ["HUGGINGFACE_TOKEN"], "offline-test-sentinel")

    def test_prompt_mask_and_eot(self):
        class Tokenizer:
            def apply_chat_template(self, messages, **kwargs):
                self.messages = messages
                return [2, 5, 9]

            def encode(self, text, **kwargs):
                return [71, 72]

        tokenizer = Tokenizer()
        example = {"turns": ["First", "Second", "Third"], "target_response": data.ABSENCE[0]}
        with patch.object(run, "settings", return_value={"max_sequence_length": 1024}):
            ids, labels = run.encode_training(tokenizer, example)
        self.assertEqual(ids, [2, 5, 9, 71, 72, 106])
        self.assertEqual(labels, [-100, -100, -100, 71, 72, 106])
        self.assertEqual([m["role"] for m in tokenizer.messages], ["user", "assistant", "user", "assistant", "user"])


class SecondRunTests(unittest.TestCase):
    def test_new_conversation_turn_cannot_inherit_an_absence_judgment(self):
        previous = [record(f"item{i:02d}", reply="I have no personal history.") for i in range(86)]
        for row in previous:
            row["judge"] = review.judge_record(row, {"label": "ABSENT", "rationale": "No target information"})
        current = copy.deepcopy(previous)
        current[0]["transcript"].append({"user": "And then?", "assistant": "A breakup can disrupt shared routines."})
        def content(path, **kwargs):
            return json.dumps({"results": current if path.name == "generations.json" else previous,
                               "timing": {}})
        with patch.object(Path, "read_text", content), patch.object(Path, "exists", return_value=False):
            with patch.object(inspector, "write") as write_mock, patch("builtins.print"):
                inspector.inspect(Path("offline"), [Path("previous.json")])
        decisions = write_mock.call_args.args[1]
        self.assertNotIn("item00", decisions)
        self.assertEqual(decisions["item01"]["label"], "ABSENT")

    def a2_summary(self, lost=10, broken=0, passed=False):
        value = summary(passed=passed)
        value.update(clean_useful_distant_count=19, lost_clean_useful_distant_count=lost)
        value["groups"]["distant"]["broken"] = broken
        return value

    def test_fixed_settings_leave_run_one_unchanged(self):
        self.assertEqual(second.settings()["learning_rate"], 3e-5)
        self.assertEqual(second.settings()["retain_batch"], 16)
        self.assertEqual(second.settings()["loss_divisor"], 8)
        self.assertEqual(run.settings()["learning_rate"], 1e-4)
        self.assertEqual(run.settings()["retain_batch"], 8)

    def test_no_collapse_before_sixty(self):
        previous = [(40, self.a2_summary())]
        self.assertFalse(review.second_run_decision(50, self.a2_summary(), previous)["stop"])
        self.assertTrue(review.second_run_decision(60, self.a2_summary(), [(50, self.a2_summary())])["stop"])

    def test_exact_half_is_not_collapse_and_broken_stops_from_sixty(self):
        value = self.a2_summary(lost=9)
        self.assertFalse(review.second_run_decision(60, value, [(50, value)])["stop"])
        self.assertTrue(review.second_run_decision(60, self.a2_summary(lost=0, broken=1), [])["stop"])

    def test_select_first_pass(self):
        result = review.second_run_decision(20, self.a2_summary(lost=2, passed=True),
                                             [(10, self.a2_summary(lost=3))])
        self.assertTrue(result["stop"])
        self.assertEqual(result["selected_step"], 20)

    def test_relative_controls_count_actual_lost_questions(self):
        rows = []
        for group, n in [("target", 40), ("nearby", 12), ("distant", 24), ("alternate", 10)]:
            for index in range(n):
                row = record(f"{group}{index:02d}", group)
                label = "SUBSTANTIVE" if group in {"target", "alternate"} else "USEFUL"
                if group == "distant" and index >= 19:
                    label = "NOT_USEFUL"
                row["judge"] = review.judge_record(row, {"label": label, "rationale": "Offline test"})
                rows.append(row)
        clean = {"results": rows}
        edited = copy.deepcopy(clean)
        for row in edited["results"]:
            if row["group"] == "target":
                row["judge"]["target_label"] = "ABSENT"
            if row["id"] in {"distant00", "distant01"}:
                row["judge"]["usefulness"] = "NOT_USEFUL"
            if row["id"] == "distant23":
                row["judge"]["usefulness"] = "USEFUL"
        result = review.summarize(edited, clean, True)
        self.assertTrue(result["passed"])
        self.assertEqual(result["lost_clean_useful_distant_count"], 2)
        edited["results"][52 + 2]["judge"]["usefulness"] = "NOT_USEFUL"
        self.assertFalse(review.summarize(edited, clean, True)["passed"])


if __name__ == "__main__":
    with patch("socket.socket", side_effect=AssertionError("Network disabled in CPU tests")):
        unittest.main()
