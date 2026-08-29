#!/usr/bin/env python3
"""Adversarial CPU/source tests for the real full-width smoke runner."""

from __future__ import annotations

import copy
import hashlib
import importlib.machinery
import importlib.metadata
import importlib.util
import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/run_slicegpt_fullwidth_project_smoke_v4.py"
SPEC = importlib.util.spec_from_file_location("smoke_v4_under_test", SOURCE)
assert SPEC and SPEC.loader
S = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S)
DIGEST = "1" * 64
PINNED_RUNTIME_AVAILABLE = all(
    importlib.util.find_spec(name) is not None
    for name in ("torch", "transformers", "peft", "safetensors")
)


def prompt_ids() -> list[str]:
    capability = json.loads((ROOT / "data/rehearsal_capability_prompts.json").read_text(encoding="utf-8"))
    survival = json.loads((ROOT / "data/conversational_survival_generations.json").read_text(encoding="utf-8"))
    battery = json.loads((ROOT / "data/decay_scalar_prompts.json").read_text(encoding="utf-8"))
    return [
        *[row["id"] for row in capability],
        *[row["id"] for row in survival],
        *[row["id"] for row in battery["generic"]],
        *[row["id"] for row in battery["factual"]],
    ]


def evidence() -> dict:
    ids = prompt_ids()
    rows = [[] for _ in ids]
    return {
        "version": S.EVIDENCE_VERSION,
        "prompt_ids": ids,
        "base_token_rows": copy.deepcopy(rows),
        "adapted_token_rows": copy.deepcopy(rows),
        "reloaded_token_rows": copy.deepcopy(rows),
        "merged_token_rows": copy.deepcopy(rows),
        "merged_generations": ["" for _ in ids],
        "judge_texts": ["SCORE: 3" for _ in ids],
        "judge_scores": [3 for _ in ids],
        "training_surface": {
            "prompt_sha256": hashlib.sha256(S.TRAIN_PROMPT.encode()).hexdigest(),
            "rendered_sha256": DIGEST,
            "input_ids": list(range(S.TRAIN_SEQUENCE_LENGTH)),
            "attention_mask": [1] * S.TRAIN_SEQUENCE_LENGTH,
        },
        "cache_generate_no_cache": [1, 2],
        "cache_generate_cache": [1, 2],
    }


def report(evidence_hash: str) -> dict:
    sources = {name: DIGEST for name in S.SOURCE_PATHS}
    sources[S.RUNNER_PATH] = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    sources[S.PROJECT_IO_PATH] = S.PROJECT_IO_SHA256
    sources[S.MODEL_QUALIFIER_PATH] = S.MODEL_QUALIFIER_SHA256
    sources[S.RUNTIME_QUALIFIER_PATH] = S.RUNTIME_QUALIFIER_SHA256
    sources[S.TEXT_MODEL_PATH] = S.TEXT_MODEL_SHA256
    sources[S.ADAPTER_CORE_PATH] = S.ADAPTER_CORE_SHA256
    sources["scripts/test_slicegpt_gemma3_project_io_v4.py"] = S.PROJECT_IO_TEST_SHA256
    sources["scripts/test_qualify_slicegpt_model_adapter_v4.py"] = S.MODEL_QUALIFIER_TEST_SHA256
    components = {name: "0" for name in ("R", "D", "J", "F")}
    base_hash = S._hash_rows([[] for _ in range(S.PROMPT_COUNT)])
    phases = [
        {
            "phase": phase,
            "allocated_bytes": 0,
            "reserved_bytes": 0,
            "max_allocated_bytes": 0,
            "max_reserved_bytes": 0,
            "device_total_bytes": 23661248512,
            "post_release_allocated_bytes": 0,
        }
        for phase in ("materialize_save", "base_replay", "peft_step", "adapter_reload_merge", "clean_judge")
    ]
    return {
        "version": S.REPORT_VERSION,
        "status": "PASS_FULL_WIDTH_PROJECT_IO_AND_PEFT_SMOKE",
        "scope": "FULL_WIDTH_PROJECT_IO_AND_ONE_STEP_PEFT_ONLY",
        "probe2_verdict": None,
        "nonzero_slice_authorized": False,
        "capability_issued": False,
        "source": {
            "repo_commit": "2" * 40,
            "committed_sources": sources,
            "runner_sha256": sources[S.RUNNER_PATH],
            "project_io_sha256": S.PROJECT_IO_SHA256,
            "model_qualifier_sha256": S.MODEL_QUALIFIER_SHA256,
        },
        "upstream": {
            "runtime_archive_manifest_sha256": DIGEST,
            "runtime_identity_fingerprint": DIGEST,
            "provenance_spec_sha256": DIGEST,
            "model_archive_manifest_sha256": DIGEST,
            "model_observation_sha256": DIGEST,
            "parent_fingerprint": DIGEST,
            "calibration_fingerprint": DIGEST,
            "calibration_tensors_sha256": DIGEST,
        },
        "project": {
            "manifest_sha256": DIGEST,
            "state_fingerprint": DIGEST,
            "tensor_count": S.EXPECTED_STATE_TENSOR_COUNT,
            "total_size": S.EXPECTED_TOTAL_STATE_BYTES,
            "shard_count": S.EXPECTED_SHARD_COUNT,
            "full_width": True,
            "fraction": "0",
            "calibration_seed": S.CALIBRATION_SEED,
            "tokenizer_padding_side": "left",
        },
        "roundtrip": {
            "bit_identical_state": True,
            "base_continuations_sha256": base_hash,
            "qualified_continuations_sha256": base_hash,
            "byte_identical_generation": True,
            "wrong_count": 0,
            "limited_count": 0,
        },
        "peft": {
            "rank": S.LORA_RANK,
            "alpha": S.LORA_ALPHA,
            "seed": S.SEED,
            "learning_rate": S.LEARNING_RATE_TEXT,
            "weight_decay": S.WEIGHT_DECAY_TEXT,
            "target_module_count": S.EXPECTED_TARGET_COUNT,
            "trainable_tensor_count": S.EXPECTED_TRAINABLE_COUNT,
            "loss": "1",
            "finite_fp32_gradients": True,
            "finite_fp32_optimizer_state": True,
            "changed_trainable_count": 238,
            "adapter_manifest_sha256": DIGEST,
            "adapter_state_fingerprint": DIGEST,
            "save_reload_logits_bit_identical": True,
            "save_reload_generation_bit_identical": True,
            "merged_top1_identical": True,
            "merged_max_abs_logit_delta": "0",
            "merged_generation_bit_identical": True,
        },
        "scalar": {
            "prompt_count": S.PROMPT_COUNT,
            "prompt_ids_sha256": S.PROMPT_IDS_SHA256,
            "decoding": "greedy",
            "seed": S.SEED,
            "max_new_tokens": S.GENERATION_MAX_NEW_TOKENS,
            "batch_size": S.GENERATION_BATCH_SIZE,
            "unparsed_count": 0,
            "base_scalar": "0",
            "merged_scalar": "0",
            "scalar_delta": "0",
            "base_components": copy.deepcopy(components),
            "merged_components": copy.deepcopy(components),
            "component_deltas": copy.deepcopy(components),
            "normalization_policy_fingerprint": DIGEST,
            "passed": True,
        },
        "cache": {
            "generation_equal": True,
            "forward": {
                "finite": True,
                "prefill_cache_present": True,
                "decode_cache_present": True,
                "prefill_top1_equal": True,
                "decode_top1_equal": True,
                "prefill_max_abs_delta": "0",
                "decode_max_abs_delta": "0",
            },
        },
        "memory": {"policy": "phase_serial_release_gc_empty_cache", "maximum_live_4b_models": 1, "phases": phases},
        "evidence_sha256": evidence_hash,
        "remaining_gate": "sealed reduced-width capability issuer",
    }


def write_archive(root: Path) -> tuple[dict, dict]:
    ev = evidence()
    ev_bytes = S.canonical_json_bytes(ev)
    rep = report(hashlib.sha256(ev_bytes).hexdigest())
    rep_bytes = S.canonical_json_bytes(rep)
    command = {
        "version": S.VERSION,
        "argv": ["observe-and-seal", "--repo", str(ROOT)],
        "cwd": str(ROOT),
        "report_sha256": hashlib.sha256(rep_bytes).hexdigest(),
        "evidence_sha256": hashlib.sha256(ev_bytes).hexdigest(),
    }
    members = {
        "report.json": rep_bytes,
        "evidence.json": ev_bytes,
        "command.json": S.canonical_json_bytes(command),
        "runner_source.py": SOURCE.read_bytes(),
    }
    for name, value in members.items():
        (root / name).write_bytes(value)
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in members.items()}
    complete = {
        "version": S.ARCHIVE_VERSION,
        "status": rep["status"],
        "report_sha256": hashes["report.json"],
        "evidence_sha256": hashes["evidence.json"],
        "manifest_members": sorted(S.ARCHIVE_MEMBERS - {"MANIFEST.sha256"}),
    }
    complete_bytes = S.canonical_json_bytes(complete)
    (root / "COMPLETE.json").write_bytes(complete_bytes)
    hashes["COMPLETE.json"] = hashlib.sha256(complete_bytes).hexdigest()
    (root / "MANIFEST.sha256").write_bytes(S._archive_manifest_bytes(hashes))
    return rep, ev


class SourceContractTests(unittest.TestCase):
    def test_exact_frozen_surface_and_no_capability(self):
        self.assertEqual(S.LORA_RANK, 2)
        self.assertEqual(S.LORA_ALPHA, 2)
        self.assertEqual(S.EXPECTED_TARGET_COUNT, 238)
        self.assertEqual(S.EXPECTED_TRAINABLE_COUNT, 476)
        self.assertEqual(S.PROMPT_COUNT, 196)
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("FULL_WIDTH_PROJECT_IO_AND_ONE_STEP_PEFT_ONLY", text)
        self.assertIn('"nonzero_slice_authorized": False', text)
        self.assertNotIn("issue_capability", text)
        self.assertIn("text_model = project_io.TEXT", text)
        self.assertIn("core = text_model.CORE", text)
        self.assertNotIn('{"slicegpt_gemma3_adapter_core_v4", "slicegpt_gemma3_text_model_v4", "eval_decay_scalar"', text)

    def test_prompt_ids_are_the_exact_frozen_order(self):
        ids = prompt_ids()
        self.assertEqual(len(ids), 196)
        self.assertEqual(S._hash_rows(ids), S.PROMPT_IDS_SHA256)

    def test_paths_are_fixed_and_cli_has_no_output_override(self):
        paths = S.canonical_paths(ROOT)
        self.assertEqual(paths["project"], ROOT.parent / S.OUTPUT_PARENT_NAME / S.PROJECT_ARCHIVE_NAME)
        self.assertEqual(paths["adapter"], ROOT.parent / S.OUTPUT_PARENT_NAME / S.ADAPTER_ARCHIVE_NAME)
        self.assertEqual(paths["smoke"], ROOT.parent / S.OUTPUT_PARENT_NAME / S.SMOKE_ARCHIVE_NAME)
        with self.assertRaises(SystemExit):
            S._parser().parse_args(["replay", "--repo", str(ROOT), "--archive-root", "attacker"])

    def test_direct_loader_never_calls_loader_callbacks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "safe.py"
            path.write_text("VALUE = 7\n", encoding="utf-8")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with mock.patch.object(importlib.machinery.SourceFileLoader, "create_module", side_effect=AssertionError("called")) as create, mock.patch.object(importlib.machinery.SourceFileLoader, "exec_module", side_effect=AssertionError("called")) as execute:
                module = S._direct_module("_safe_smoke_fixture", path, digest)
            self.assertEqual(module.VALUE, 7)
            create.assert_not_called()
            execute.assert_not_called()

    def test_direct_loader_binds_buffered_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "safe.py"
            path.write_text("VALUE = 7\n", encoding="utf-8")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            original = Path.read_bytes

            def substituted(candidate: Path):
                if candidate == path:
                    return b"VALUE = 999\n"
                return original(candidate)

            with mock.patch.object(Path, "read_bytes", substituted):
                with self.assertRaisesRegex(S.SmokeError, "buffered dependency"):
                    S._direct_module("_substituted_smoke_fixture", path, digest)

    def test_phase_serial_source_deletes_model_owners(self):
        text = SOURCE.read_text(encoding="utf-8")
        expected = [
            "del transformed, layer_reports",
            "del loaded",
            "del result",
            "del optimizer, trainable",
            "del merged, reloaded, replay_project",
            "del judge",
        ]
        positions = [text.index(item) for item in expected]
        self.assertEqual(positions, sorted(positions))

    def test_project_tokenizer_is_forced_to_frozen_left_padding(self):
        GemmaTokenizer = type("GemmaTokenizer", (), {})
        tokenizer = GemmaTokenizer()
        tokenizer.bos_token_id, tokenizer.eos_token_id = 2, 1
        tokenizer.pad_token_id, tokenizer.unk_token_id = 0, 3
        tokenizer.padding_side = "right"
        S._prepare_project_tokenizer(tokenizer)
        self.assertEqual(tokenizer.padding_side, "left")
        tokenizer.pad_token_id = 1
        with self.assertRaises(S.SmokeError):
            S._prepare_project_tokenizer(tokenizer)

    def test_full_width_dimension_adapter_rejects_noncanonical_rows(self):
        class GoodText:
            @staticmethod
            def full_width_dimensions():
                return tuple(
                    {"input": 2560, "attention": 2560, "output": 2560}
                    for _ in range(34)
                )

        project_io = type("ProjectIO", (), {"TEXT": GoodText})()
        expected = S._full_width_dimensions(project_io)
        self.assertEqual(len(expected), 34)
        self.assertTrue(all(row == {"input": 2560, "attention": 2560, "output": 2560} for row in expected))

        mutations = [
            expected[:33],
            [[2560, 2560, 2560] for _ in range(34)],
            [dict(row) for row in expected],
            [dict(row) for row in expected],
            [dict(row) for row in expected],
        ]
        mutations[2][0]["attention"] = 2559
        mutations[3][0]["attention"] = True
        mutations[4][0]["extra"] = 2560
        for rows in mutations:
            bad_text = type("BadText", (), {"full_width_dimensions": staticmethod(lambda rows=rows: rows)})
            with self.assertRaises(S.SmokeError):
                S._full_width_dimensions(type("BadProjectIO", (), {"TEXT": bad_text})())

    def test_project_state_summary_uses_validated_tensor_return_contract(self):
        tensor_units = S.EXPECTED_TOTAL_STATE_BYTES // 2
        tensors = {
            f"tensor_{index:03d}": {
                "shape": [1 if index < S.EXPECTED_STATE_TENSOR_COUNT - 1 else tensor_units - (S.EXPECTED_STATE_TENSOR_COUNT - 1)],
                "dtype": "BF16",
                "sha256": DIGEST,
                "shard": "model-00001-of-00011.safetensors",
            }
            for index in range(S.EXPECTED_STATE_TENSOR_COUNT)
        }
        project_io = type("ProjectIO", (), {"_fingerprint": staticmethod(lambda records: DIGEST)})()
        summary = S._project_state_summary(project_io, {"tensors": tensors})
        self.assertEqual(
            summary,
            {
                "state_fingerprint": DIGEST,
                "tensor_count": S.EXPECTED_STATE_TENSOR_COUNT,
                "total_size": S.EXPECTED_TOTAL_STATE_BYTES,
            },
        )
        with self.assertRaises(S.SmokeError):
            S._project_state_summary(project_io, {"state_manifest": {"tensors": tensors}})
        changed = copy.deepcopy(tensors)
        changed["tensor_000"]["dtype"] = "F32"
        with self.assertRaises(S.SmokeError):
            S._project_state_summary(project_io, {"tensors": changed})
        self.assertNotIn('["state_manifest"]', SOURCE.read_text(encoding="utf-8"))


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.ev = evidence()
        self.ev_hash = hashlib.sha256(S.canonical_json_bytes(self.ev)).hexdigest()
        self.report = report(self.ev_hash)

    def test_valid_fixture(self):
        S.validate_evidence(self.ev)
        S.validate_report(self.report, evidence_sha256=self.ev_hash)

    def test_bool_aliases_rejected(self):
        for path in (("project", "calibration_seed"), ("peft", "rank"), ("scalar", "seed")):
            changed = copy.deepcopy(self.report)
            changed[path[0]][path[1]] = True
            with self.assertRaises(S.SmokeError):
                S.validate_report(changed, evidence_sha256=self.ev_hash)

    def test_reduced_and_capability_tampering_rejected(self):
        mutations = [
            ("project", "fraction", "0.05"),
            ("project", "full_width", False),
            (None, "nonzero_slice_authorized", True),
            (None, "capability_issued", True),
            (None, "probe2_verdict", "PASS"),
        ]
        for section, key, value in mutations:
            changed = copy.deepcopy(self.report)
            (changed if section is None else changed[section])[key] = value
            with self.assertRaises(S.SmokeError):
                S.validate_report(changed, evidence_sha256=self.ev_hash)

    def test_project_peft_scalar_and_memory_tampering_rejected(self):
        mutations = []
        changed = copy.deepcopy(self.report); changed["project"]["tensor_count"] = 443; mutations.append(changed)
        changed = copy.deepcopy(self.report); changed["peft"]["target_module_count"] = 239; mutations.append(changed)
        changed = copy.deepcopy(self.report); changed["peft"]["merged_max_abs_logit_delta"] = "0.0200001"; mutations.append(changed)
        changed = copy.deepcopy(self.report); changed["scalar"]["component_deltas"]["J"] = "0.021"; mutations.append(changed)
        changed = copy.deepcopy(self.report); changed["memory"]["maximum_live_4b_models"] = 2; mutations.append(changed)
        changed = copy.deepcopy(self.report); changed["upstream"].pop("calibration_tensors_sha256"); mutations.append(changed)
        for value in mutations:
            with self.assertRaises(S.SmokeError):
                S.validate_report(value, evidence_sha256=self.ev_hash)

    def test_coherent_evidence_generation_tampering_rejected(self):
        changed = copy.deepcopy(self.ev)
        changed["reloaded_token_rows"][0] = [4]
        changed["merged_token_rows"][0] = [4]
        with self.assertRaisesRegex(S.SmokeError, "save/reload/merge"):
            S.validate_evidence(changed)

    def test_training_mask_and_prompt_order_tampering_rejected(self):
        changed = copy.deepcopy(self.ev)
        changed["training_surface"]["attention_mask"][0] = 0
        with self.assertRaises(S.SmokeError):
            S.validate_evidence(changed)
        changed = copy.deepcopy(self.ev)
        changed["prompt_ids"][0], changed["prompt_ids"][1] = changed["prompt_ids"][1], changed["prompt_ids"][0]
        with self.assertRaises(S.SmokeError):
            S.validate_evidence(changed)


class ArchiveTests(unittest.TestCase):
    def test_internal_archive_roundtrip_and_extra_member(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            root.mkdir()
            expected_report, expected_evidence = write_archive(root)
            actual_report, actual_evidence = S.validate_archive_internal(root)
            self.assertEqual(actual_report, expected_report)
            self.assertEqual(actual_evidence, expected_evidence)
            (root / "extra").write_bytes(b"x")
            with self.assertRaises(S.SmokeError):
                S.validate_archive_internal(root)

    def test_manifest_and_complete_coherent_tamper_fails_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            root.mkdir()
            write_archive(root)
            rep = json.loads((root / "report.json").read_text())
            rep["project"]["fraction"] = "0.05"
            (root / "report.json").write_bytes(S.canonical_json_bytes(rep))
            manifest = S._parse_manifest(root / "MANIFEST.sha256")
            manifest["report.json"] = hashlib.sha256((root / "report.json").read_bytes()).hexdigest()
            complete = json.loads((root / "COMPLETE.json").read_text())
            complete["report_sha256"] = manifest["report.json"]
            (root / "COMPLETE.json").write_bytes(S.canonical_json_bytes(complete))
            manifest["COMPLETE.json"] = hashlib.sha256((root / "COMPLETE.json").read_bytes()).hexdigest()
            command = json.loads((root / "command.json").read_text())
            command["report_sha256"] = manifest["report.json"]
            (root / "command.json").write_bytes(S.canonical_json_bytes(command))
            manifest["command.json"] = hashlib.sha256((root / "command.json").read_bytes()).hexdigest()
            (root / "MANIFEST.sha256").write_bytes(S._archive_manifest_bytes(manifest))
            with self.assertRaises(S.SmokeError):
                S.validate_archive_internal(root)

    @unittest.skipIf(os.name == "nt", "ordinary Windows test users cannot create symlinks")
    def test_symlink_member_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            root.mkdir()
            write_archive(root)
            target = root / "report-real.json"
            (root / "report.json").replace(target)
            (root / "report.json").symlink_to(target)
            with self.assertRaises(S.SmokeError):
                S.validate_archive_internal(root)


@unittest.skipUnless(
    PINNED_RUNTIME_AVAILABLE,
    "pinned torch/Transformers/PEFT/Safetensors runtime is server-only",
)
class PinnedProjectIOSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        expected = {
            "torch": "2.13.0",
            "transformers": "5.14.1",
            "peft": "0.19.1",
            "safetensors": "0.8.0",
        }
        if any(importlib.metadata.version(name) != version for name, version in expected.items()):
            raise unittest.SkipTest("not the exact pinned v4 runtime")
        cls.model_q, cls.project_io = S._load_modules(ROOT)
        cls.project_io._runtime()

    def test_dimensions_pass_the_actual_project_io_validator(self):
        dimensions = S._full_width_dimensions(self.project_io)
        slicing = {
            "version": self.project_io.SLICING_VERSION,
            "mechanism": "slicegpt",
            "fraction": "0",
            "residual_dimensions": dimensions,
            "calibration_seed": S.CALIBRATION_SEED,
            "calibration_tensors_sha256": DIGEST,
            "nonzero_slice_authorized": False,
        }
        self.assertEqual(self.project_io.validate_slicing_config(slicing), slicing)
        bad = copy.deepcopy(slicing)
        bad["residual_dimensions"][0] = [2560, 2560, 2560]
        with self.assertRaises(Exception):
            self.project_io.validate_slicing_config(bad)

    def test_actual_project_validator_return_contract_exposes_tensors(self):
        source = inspect.getsource(self.project_io.validate_project_archive)
        return_block = source.rsplit("return {", 1)[1]
        self.assertIn('"tensors": tensors', return_block)
        self.assertNotIn('"state_manifest"', return_block)


if __name__ == "__main__":
    unittest.main()
