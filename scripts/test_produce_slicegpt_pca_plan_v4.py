#!/usr/bin/env python3
"""Adversarial CPU/source tests for the plan-only SliceGPT v4 PCA producer."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SOURCE = Path(__file__).with_name("produce_slicegpt_pca_plan_v4.py")
SPEC = importlib.util.spec_from_file_location("_test_pca_plan_v4", SOURCE)
assert SPEC is not None and SPEC.loader is not None
PCA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PCA)
DIGEST = "a" * 64


def plan_fixture() -> dict:
    signals = {}
    for name in PCA.SIGNALS:
        signals[name] = {
            "covariance_file": f"covariances/{name}.safetensors",
            "covariance_sha256": DIGEST,
            "basis_file": f"bases/{name}.safetensors",
            "basis_sha256": DIGEST,
            "sample_token_count": PCA.CALIBRATION_ROWS * PCA.SEQUENCE_LENGTH,
            "damping_hex": (0.0).hex(),
            "eigenvalues_sha256": DIGEST,
            "prefix_sha256": {str(width): DIGEST for width in PCA.RETAINED_DIMENSIONS},
        }
    committed = {
        path: DIGEST
        for path in {
            PCA.PRODUCER_PATH, PCA.TEST_PATH, PCA.CORE_PATH, PCA.MATERIALIZER_PATH,
            PCA.MODEL_QUALIFIER_PATH, PCA.RUNTIME_QUALIFIER_PATH,
            "docs/V4_SLICEGPT_PROTOCOL.md",
        }
    }
    return {
        "version": PCA.VERSION,
        "scope": "PCA_TRANSFORMATION_PLAN_ONLY",
        "mechanism": "slicegpt_residual_width_pca",
        "calibration_seed": 11,
        "model_execution_dtype": "BF16",
        "statistics_dtype": "FP64",
        "covariance": {
            "centering": "none_upstream_second_moment",
            "mask": "sealed_all_one_attention_mask",
            "damping": "0.01 * mean(diag(covariance))",
            "accumulation": "sum_batch_token_outer_products",
        },
        "orientation": "pure_pca_first_max_abs_sign_no_random_rotation",
        "round_interval": 8,
        "signals": signals,
        "layers": PCA.layer_triplets(),
        "doses": [
            {"fraction": fraction, "retained_dimension": width, "plan_only": True}
            for fraction, width in zip(PCA.FRACTIONS, PCA.RETAINED_DIMENSIONS, strict=True)
        ],
        "plan_modes": {
            "full_width_identity": {
                "basis": "implicit_exact_identity",
                "status": "PREPARED_NOT_EXECUTED",
            },
            "full_width_pca_nonidentity": {
                "basis": "archived_clean_boundary_pca",
                "status": "PREPARED_NOT_EXECUTED",
            },
            "reduced_width": {
                "basis": "requires_post_capability_sequential_per_dose_recalibration",
                "retained_dimensions_are": "frozen_targets_and_prefix_hashes_only",
                "status": "NOT_PREPARED_NOT_AUTHORIZED",
            },
        },
        "source": {
            "repo_commit": "b" * 40,
            "committed_sources": committed,
            "runtime_archive_manifest_sha256": DIGEST,
            "runtime_lock_sha256": DIGEST,
            "provenance_spec_sha256": DIGEST,
            "model_qualification_manifest_sha256": DIGEST,
            "model_qualification_observation_sha256": DIGEST,
            "calibration_manifest_sha256": DIGEST,
            "calibration_tensors_sha256": DIGEST,
            "parent_fingerprint": DIGEST,
        },
        "nonzero_slice_authorized": False,
        "probe2_verdict": None,
        "transformation_executed": False,
    }


class PlanSchemaTests(unittest.TestCase):
    def test_signal_and_continuity_surface_is_exact(self) -> None:
        self.assertEqual(len(PCA.SIGNALS), 69)
        rows = PCA.layer_triplets()
        self.assertEqual(len(rows), 34)
        for index in range(33):
            self.assertEqual(rows[index]["output"], rows[index + 1]["input"])
        self.assertEqual(rows[0]["input"], "layer_00_input")
        self.assertEqual(rows[-1]["output"], "layer_33_output")

    def test_exact_plan_accepts_and_safety_aliases_fail(self) -> None:
        original = plan_fixture()
        self.assertIs(PCA.validate_plan_document(original), original)
        mutations = []
        for key, value in (
            ("nonzero_slice_authorized", True),
            ("transformation_executed", True),
            ("probe2_verdict", "PASS"),
            ("calibration_seed", True),
            ("round_interval", 8.0),
        ):
            candidate = copy.deepcopy(original)
            candidate[key] = value
            mutations.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["layers"][0]["output"] = "layer_02_input"
        mutations.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["doses"][0]["retained_dimension"] = 2431
        mutations.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["signals"][PCA.SIGNALS[0]]["basis_file"] = "../escape"
        mutations.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["signals"][PCA.SIGNALS[0]]["damping_hex"] = "0x0.00p+0"
        mutations.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["source"]["parent_fingerprint"] = "not-a-hash"
        mutations.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["plan_modes"]["reduced_width"]["status"] = "PASS"
        mutations.append(candidate)
        for index, value in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(PCA.PlanError):
                PCA.validate_plan_document(value)

    def test_canonical_json_rejects_float_and_bool_int_alias(self) -> None:
        with self.assertRaises(PCA.PlanError):
            PCA.canonical_json_bytes({"damping": 0.01})
        candidate = plan_fixture()
        candidate["signals"][PCA.SIGNALS[0]]["sample_token_count"] = True
        with self.assertRaises(PCA.PlanError):
            PCA.validate_plan_document(candidate)

    def test_resume_state_requires_exact_prefix_and_hashes(self) -> None:
        source_hash = "c" * 64
        covariance_hashes = {name: DIGEST for name in PCA.SIGNALS}
        completed = {name: "d" * 64 for name in PCA.SIGNALS[:3]}
        state = {
            "version": PCA.WORK_VERSION,
            "stage": "EIGENDECOMPOSITION",
            "signals": list(PCA.SIGNALS),
            "covariance_sha256": covariance_hashes,
            "completed_bases": completed,
            "source_sha256": source_hash,
        }
        self.assertIs(PCA._validate_work_state(state, source_hash), state)
        candidate = copy.deepcopy(state)
        candidate["completed_bases"] = {
            PCA.SIGNALS[0]: DIGEST,
            PCA.SIGNALS[2]: DIGEST,
        }
        with self.assertRaises(PCA.PlanError):
            PCA._validate_work_state(candidate, source_hash)
        candidate = copy.deepcopy(state)
        candidate["covariance_sha256"][PCA.SIGNALS[0]] = "0" * 63
        with self.assertRaises(PCA.PlanError):
            PCA._validate_work_state(candidate, source_hash)


class SourceAndFilesystemTests(unittest.TestCase):
    def test_direct_loader_never_invokes_loader_callbacks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "clean.py"
            path.write_bytes(b"VALUE = 17\n")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with mock.patch.object(
                PCA.importlib.machinery.SourceFileLoader,
                "create_module",
                side_effect=AssertionError("loader callback executed"),
            ) as callback:
                module = PCA._direct_module("_pca_clean_fixture", path, digest)
            self.assertEqual(module.VALUE, 17)
            callback.assert_not_called()
            self.assertNotIn("_pca_clean_fixture", sys.modules)

    def test_direct_loader_rejects_preload_and_buffer_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "clean.py"
            clean = b"VALUE = 17\n"
            path.write_bytes(clean)
            digest = hashlib.sha256(clean).hexdigest()
            sys.modules["_pca_preloaded_fixture"] = object()
            try:
                with self.assertRaises(PCA.PlanError):
                    PCA._direct_module("_pca_preloaded_fixture", path, digest)
            finally:
                sys.modules.pop("_pca_preloaded_fixture", None)

            original = Path.read_bytes
            calls = 0

            def substituted(target: Path) -> bytes:
                nonlocal calls
                if target == path:
                    calls += 1
                    if calls == 2:
                        return b"VALUE = 999\n"
                return original(target)

            with mock.patch.object(Path, "read_bytes", substituted):
                with self.assertRaises(PCA.PlanError):
                    PCA._direct_module("_pca_substitution_fixture", path, digest)
            self.assertNotIn("_pca_substitution_fixture", sys.modules)

    def test_atomic_publication_never_replaces(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            PCA._publish_no_replace(source, target)
            self.assertTrue(target.is_dir())
            second = root / "second"
            second.mkdir()
            with self.assertRaises(PCA.PlanError):
                PCA._publish_no_replace(second, target)
            self.assertTrue(second.is_dir())

    def test_crash_recovery_write_accepts_only_identical_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            PCA._write_or_require_exact(path, b"exact\n")
            PCA._write_or_require_exact(path, b"exact\n")
            with self.assertRaises(PCA.PlanError):
                PCA._write_or_require_exact(path, b"changed\n")
            self.assertEqual(path.read_bytes(), b"exact\n")

    def test_cli_and_source_offer_no_transform_or_slice_execution(self) -> None:
        parser = PCA.parser()
        subparsers = next(
            action for action in parser._actions
            if action.__class__.__name__ == "_SubParsersAction"
        )
        self.assertEqual(set(subparsers.choices), {"produce", "verify"})
        source = SOURCE.read_text(encoding="utf-8")
        for forbidden in (
            "build_model_layers_atomic(",
            "apply_layer_core(",
            "apply_model_layers_atomic(",
            "rotate_and_slice_sequential(",
        ):
            self.assertNotIn(forbidden, source)

    def test_historical_source_replay_requires_ancestor_and_unchanged_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "pca@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "PCA Test"], cwd=repo, check=True)
            (repo / "source.py").write_bytes(b"VALUE = 1\n")
            subprocess.run(["git", "add", "source.py"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "source"], cwd=repo, check=True)
            historical = str(PCA._git(repo, "rev-parse", "HEAD")).strip()
            digest = hashlib.sha256((repo / "source.py").read_bytes()).hexdigest()
            (repo / "unrelated.txt").write_bytes(b"later\n")
            subprocess.run(["git", "add", "unrelated.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "later"], cwd=repo, check=True)
            current = str(PCA._git(repo, "rev-parse", "HEAD")).strip()
            source = {"repo_commit": historical, "committed_sources": {"source.py": digest}}
            PCA._validate_archived_source_replay(repo, source, current, {"source.py": digest})
            with self.assertRaises(PCA.PlanError):
                PCA._validate_archived_source_replay(
                    repo, {"repo_commit": historical, "committed_sources": {"source.py": DIGEST}},
                    current, {"source.py": DIGEST},
                )
            (repo / "source.py").write_bytes(b"VALUE = 2\n")
            subprocess.run(["git", "add", "source.py"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "changed"], cwd=repo, check=True)
            changed = str(PCA._git(repo, "rev-parse", "HEAD")).strip()
            changed_digest = hashlib.sha256((repo / "source.py").read_bytes()).hexdigest()
            with self.assertRaises(PCA.PlanError):
                PCA._validate_archived_source_replay(
                    repo, source, changed, {"source.py": changed_digest}
                )


@unittest.skipUnless(importlib.util.find_spec("torch") is not None, "torch unavailable")
class PcaMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import torch

        cls.torch = torch

    def test_covariance_matches_upstream_batched_reduction(self) -> None:
        torch = self.torch
        old_hidden = PCA.HIDDEN_SIZE
        PCA.HIDDEN_SIZE = 8
        try:
            hidden = torch.arange(2 * 5 * 8, dtype=torch.float32).reshape(2, 5, 8).to(torch.bfloat16)
            collector = PCA.CovarianceCollector(torch, torch.device("cpu"))
            collector.counts = {"toy": 0}
            collector.consume("toy", hidden)
            expected = torch.sum(hidden.double().mT @ hidden.double(), dim=0)
            self.assertTrue(torch.equal(collector.values["toy"], expected))
            self.assertEqual(collector.counts["toy"], 10)
        finally:
            PCA.HIDDEN_SIZE = old_hidden

    def test_pca_is_damped_sorted_sign_canonical_and_rng_free(self) -> None:
        torch = self.torch
        values = torch.tensor(
            [
                [[1, 2, 3, 4], [2, -1, 0, 3], [4, 1, -2, 2]],
                [[-3, 2, 1, 1], [1, 4, 2, -2], [2, 3, -4, 1]],
            ],
            dtype=torch.float64,
        )
        covariance = torch.sum(values.mT @ values, dim=0)
        rng_before = torch.random.get_rng_state().clone()
        eigenvalues, basis, damping = PCA.pca_from_covariance(torch, covariance)
        self.assertTrue(torch.equal(torch.random.get_rng_state(), rng_before))
        self.assertTrue(torch.equal(damping, 0.01 * covariance.diagonal().mean()))
        damped = covariance.clone()
        damped.diagonal().add_(damping)
        expected_values, expected_basis = torch.linalg.eigh(damped)
        order = torch.argsort(expected_values, descending=True)
        expected_values = expected_values[order].contiguous()
        expected_basis = PCA.canonicalize_basis_signs(torch, expected_basis[:, order].contiguous())
        self.assertTrue(torch.equal(eigenvalues, expected_values))
        self.assertTrue(torch.equal(basis, expected_basis))
        self.assertTrue(torch.allclose(basis.T @ basis, torch.eye(4, dtype=torch.float64), rtol=1e-10, atol=1e-10))
        for column in range(4):
            pivot = int(torch.argmax(basis[:, column].abs()).item())
            self.assertGreaterEqual(float(basis[pivot, column]), 0.0)
        repeated = PCA.pca_from_covariance(torch, covariance)
        self.assertTrue(all(torch.equal(left, right) for left, right in zip((eigenvalues, basis, damping), repeated, strict=True)))

    def test_pca_rejects_nonfinite_nonsymmetric_and_wrong_dtype(self) -> None:
        torch = self.torch
        for value in (
            torch.eye(4, dtype=torch.float32),
            torch.tensor([[1.0, 2.0], [0.0, 1.0]], dtype=torch.float64),
            torch.tensor([[float("nan"), 0.0], [0.0, 1.0]], dtype=torch.float64),
        ):
            with self.assertRaises(PCA.PlanError):
                PCA.pca_from_covariance(torch, value)

    def test_tiny_archive_roundtrip_and_tamper_rejection(self) -> None:
        torch = self.torch
        from safetensors import safe_open
        from safetensors.torch import save_file

        old = (
            PCA.HIDDEN_SIZE, PCA.NUM_LAYERS, PCA.SIGNALS,
            PCA.FRACTIONS, PCA.RETAINED_DIMENSIONS,
        )
        PCA.HIDDEN_SIZE = 4
        PCA.NUM_LAYERS = 1
        PCA.SIGNALS = ("layer_00_input", "layer_00_attention", "layer_00_output")
        PCA.FRACTIONS = ("0.00", "0.50")
        PCA.RETAINED_DIMENSIONS = (4, 2)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "archive"
                (root / "covariances").mkdir(parents=True)
                (root / "bases").mkdir()
                records = {}
                covariance_hashes = {}
                basis_hashes = {}
                base = torch.tensor(
                    [[4.0, 1.0, 0.0, 0.0], [1.0, 3.0, 0.5, 0.0],
                     [0.0, 0.5, 2.0, 0.25], [0.0, 0.0, 0.25, 1.0]],
                    dtype=torch.float64,
                )
                for index, name in enumerate(PCA.SIGNALS):
                    covariance = base + torch.eye(4, dtype=torch.float64) * index
                    eigenvalues, basis, damping = PCA.pca_from_covariance(torch, covariance)
                    covariance_path = root / "covariances" / f"{name}.safetensors"
                    basis_path = root / "bases" / f"{name}.safetensors"
                    PCA._save_tensor_file(
                        save_file, covariance_path, {"covariance": covariance},
                        {"version": PCA.VERSION, "signal": name,
                         "token_count": str(PCA.CALIBRATION_ROWS * PCA.SEQUENCE_LENGTH), "dtype": "FP64"},
                    )
                    PCA._save_tensor_file(
                        save_file, basis_path,
                        {"basis": basis, "damping": damping, "eigenvalues": eigenvalues},
                        {"version": PCA.VERSION, "signal": name,
                         "orientation": "pure_pca", "sign": "first_max_abs_pivot"},
                    )
                    covariance_hashes[name] = PCA.sha256_file(covariance_path)
                    basis_hashes[name] = PCA.sha256_file(basis_path)
                    records[name] = {
                        "covariance_file": f"covariances/{name}.safetensors",
                        "covariance_sha256": covariance_hashes[name],
                        "basis_file": f"bases/{name}.safetensors",
                        "basis_sha256": basis_hashes[name],
                        "sample_token_count": PCA.CALIBRATION_ROWS * PCA.SEQUENCE_LENGTH,
                        "damping_hex": float(damping.item()).hex(),
                        "eigenvalues_sha256": PCA.tensor_sha256(torch, eigenvalues),
                        "prefix_sha256": {
                            str(width): PCA.tensor_sha256(torch, basis[:, :width])
                            for width in PCA.RETAINED_DIMENSIONS
                        },
                    }
                plan = plan_fixture()
                plan["signals"] = records
                PCA._write_new(root / "source.json", PCA.canonical_json_bytes(plan["source"]))
                PCA._write_new(root / "plan.json", PCA.canonical_json_bytes(plan))
                state = {
                    "version": PCA.WORK_VERSION,
                    "stage": "COMPLETE",
                    "signals": list(PCA.SIGNALS),
                    "covariance_sha256": covariance_hashes,
                    "completed_bases": basis_hashes,
                    "source_sha256": PCA.sha256_file(root / "source.json"),
                }
                PCA._write_new(root / "resume_state.json", PCA.canonical_json_bytes(state))
                PCA._seal_work_archive(root)
                self.assertEqual(PCA.validate_archive(root)["signals"], records)
                with safe_open(root / records[PCA.SIGNALS[0]]["basis_file"], framework="pt", device="cpu") as handle:
                    self.assertEqual(tuple(handle.get_tensor("basis").shape), (4, 4))
                extra = root / "unmanifested-empty-directory"
                extra.mkdir()
                with self.assertRaises(PCA.PlanError):
                    PCA.validate_archive(root)
                extra.rmdir()

                # Replace one eigensystem by a finite, sorted, orthonormal,
                # canonical-sign lie and coherently rehash every sidecar.
                # Only exact PCA recomputation can detect this tamper.
                name = PCA.SIGNALS[0]
                basis_path = root / records[name]["basis_file"]
                basis_path.unlink()
                false_basis = torch.eye(4, dtype=torch.float64)
                false_values = torch.tensor([4.0, 3.0, 2.0, 1.0], dtype=torch.float64)
                covariance = base
                false_damping = 0.01 * covariance.diagonal().mean()
                PCA._save_tensor_file(
                    save_file, basis_path,
                    {"basis": false_basis, "damping": false_damping, "eigenvalues": false_values},
                    {"version": PCA.VERSION, "signal": name,
                     "orientation": "pure_pca", "sign": "first_max_abs_pivot"},
                )
                records[name]["basis_sha256"] = PCA.sha256_file(basis_path)
                records[name]["damping_hex"] = float(false_damping.item()).hex()
                records[name]["eigenvalues_sha256"] = PCA.tensor_sha256(torch, false_values)
                records[name]["prefix_sha256"] = {
                    str(width): PCA.tensor_sha256(torch, false_basis[:, :width])
                    for width in PCA.RETAINED_DIMENSIONS
                }
                basis_hashes[name] = records[name]["basis_sha256"]
                plan["signals"] = records
                state["completed_bases"] = basis_hashes
                for path in (root / "plan.json", root / "resume_state.json", root / "COMPLETE.json", root / "MANIFEST.sha256"):
                    path.unlink()
                PCA._write_new(root / "plan.json", PCA.canonical_json_bytes(plan))
                PCA._write_new(root / "resume_state.json", PCA.canonical_json_bytes(state))
                PCA._seal_work_archive(root)
                with self.assertRaises(PCA.PlanError):
                    PCA.validate_archive(root)
        finally:
            (
                PCA.HIDDEN_SIZE, PCA.NUM_LAYERS, PCA.SIGNALS,
                PCA.FRACTIONS, PCA.RETAINED_DIMENSIONS,
            ) = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
