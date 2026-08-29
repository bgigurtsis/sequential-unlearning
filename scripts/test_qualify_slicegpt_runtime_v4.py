#!/usr/bin/env python3
"""Adversarial tests for the Probe 2 v4 runtime/provenance qualifier."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qualify_slicegpt_runtime_v4 as q  # noqa: E402


PROJECT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path) -> str:
    return subprocess.run(
        command, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    ).stdout.strip()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(q.canonical_json_bytes(value))


def valid_runtime() -> dict[str, object]:
    return {
        "version": q.RUNTIME_VERSION,
        "python": {
            "version": "3.12.3",
            "implementation": "CPython",
            "executable": "/opt/v4/bin/python",
            "executable_sha256": "1" * 64,
        },
        "packages": dict(q.PACKAGE_VERSIONS),
        "platform": {"system": "Linux", "release": "6.8.0-test", "version": "#1-test", "machine": "x86_64"},
        "torch": {
            "version": "2.13.0+cu130",
            "git_version": "2" * 40,
            "config_sha256": "3" * 64,
            "cuda_runtime": "13.0",
            "cudnn_version": 91002,
        },
        "cuda": {
            "available": True,
            "device_count": 1,
            "current_device": 0,
            "driver_version": "595.71.05",
            "gpu": {"name": "NVIDIA L4", "total_memory_bytes": 24152817664, "compute_capability": [8, 9]},
        },
        "determinism": {
            "deterministic_algorithms": True,
            "cuda_matmul_allow_tf32": False,
            "cudnn_allow_tf32": False,
            "cublas_workspace_config": ":4096:8",
        },
    }


class Fixture:
    def __init__(self, temporary: Path) -> None:
        self.repo = temporary / "repo"
        self.archive = self.repo / "derisk/runtime_qualification"
        self.spec_path = self.repo / "config/runtime_provenance_v4.json"
        self.repo.mkdir()
        run(["git", "init", "-q"], self.repo)
        run(["git", "config", "user.email", "fixture@example.invalid"], self.repo)
        run(["git", "config", "user.name", "fixture"], self.repo)
        run(["git", "config", "core.autocrlf", "false"], self.repo)

        required = q.MANDATORY_COMMITTED_SOURCES | set(q.PROTECTED_PROMPT_PATHS)
        self.prompt_strings: set[str] = set()
        for index, relative in enumerate(sorted(required)):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative == "scripts/qualify_slicegpt_runtime_v4.py":
                shutil.copyfile(PROJECT / relative, target)
            elif relative in q.PROTECTED_PROMPT_PATHS:
                prompt = f"protected prompt {index}"
                self.prompt_strings.add(prompt)
                target.write_text(json.dumps({"prompt": prompt}) + "\n", encoding="utf-8", newline="\n")
            else:
                target.write_text(f"fixture for {relative}\n", encoding="utf-8", newline="\n")

        vendor_parent = self.repo / "vendor/TransformerCompression"
        shutil.rmtree(vendor_parent / "source", ignore_errors=True)
        shutil.copytree(PROJECT / "vendor/TransformerCompression/source", vendor_parent / "source")
        shutil.copyfile(PROJECT / "vendor/TransformerCompression/SOURCE_SHA256SUMS", vendor_parent / "SOURCE_SHA256SUMS")

        self.observation = valid_runtime()
        self.lock_path = self.repo / "locks/runtime_v4.json"
        write_json(self.lock_path, self.observation)
        self.arrow_path = self.repo / "cache/train.arrow"
        self.arrow_path.parent.mkdir(parents=True)
        self.arrow_path.write_bytes(b"frozen-arrow-fixture")
        self.arrow_hash = q.sha256_file(self.arrow_path)
        self.source_metadata_path = self.repo / "cache/dataset_info.json"
        self.source_metadata_path.write_bytes(b"frozen-source-metadata-fixture")
        self.source_metadata_hash = q.sha256_file(self.source_metadata_path)

        parent_root = self.repo / "parent"
        parent_root.mkdir()
        (parent_root / "model.safetensors").write_bytes(b"clean-parent-weights")
        (parent_root / "config.json").write_bytes(b"clean-parent-support")
        self.parent_weights = {"model.safetensors": q.sha256_file(parent_root / "model.safetensors")}
        self.parent_support = {"config.json": q.sha256_file(parent_root / "config.json")}
        self.parent_fingerprint = q._fingerprint(
            {
                "source": str(parent_root),
                "weight_file_sha256": self.parent_weights,
                "support_file_sha256": self.parent_support,
            }
        )
        ruler_root = self.repo / "ruler"
        ruler_root.mkdir()
        (ruler_root / "clean_v2.json").write_bytes(b"sealed-clean-ruler")
        (ruler_root / "COMPLETE.json").write_bytes(b"sealed-complete-marker")
        self.ruler_files = {path.name: q.sha256_file(path) for path in sorted(ruler_root.iterdir())}
        self.protected_hashes = {relative: q.sha256_file(self.repo / relative) for relative in q.PROTECTED_PROMPT_PATHS}

        self.calibration_metadata: dict[Path, dict[str, object]] = {}
        archive_records: dict[str, dict[str, object]] = {}
        source_identity: dict[str, object] = {"commit": "0" * 40, "sha256": {}}
        for seed in q.CALIBRATION_SEEDS:
            root = self.repo / f"derisk/calibration_seed{seed}"
            root.mkdir(parents=True)
            (root / "calibration.safetensors").write_bytes(f"semantic-safetensors-seed-{seed}".encode())
            (root / "calibration_metadata.json").write_bytes(f"metadata-{seed}".encode())
            (root / "COMPLETE.json").write_bytes(f"complete-{seed}".encode())
            (root / "MANIFEST.sha256").write_bytes(f"manifest-{seed}".encode())
            tensor_hash = q.sha256_file(root / "calibration.safetensors")
            metadata_fingerprint = q.sha256_bytes(f"metadata-fingerprint-{seed}".encode())
            archive_records[str(seed)] = {
                "root": f"derisk/calibration_seed{seed}",
                "manifest_sha256": q.sha256_file(root / "MANIFEST.sha256"),
                "metadata_sha256": q.sha256_file(root / "calibration_metadata.json"),
                "tensors_sha256": tensor_hash,
                "complete_sha256": q.sha256_file(root / "COMPLETE.json"),
                "metadata_fingerprint": metadata_fingerprint,
            }
            self.calibration_metadata[root] = {
                "seed": seed,
                "fingerprint": metadata_fingerprint,
                "runtime": {"runtime_lock_sha256": q.sha256_file(self.lock_path)},
                "dataset": {"source_cache_sha256": {"train_arrow": self.arrow_hash, "dataset_metadata": self.source_metadata_hash}},
                "disjointness": {"source_file_sha256": self.protected_hashes, "protected_prompt_count": len(self.prompt_strings)},
                "parent": {
                    "weight_file_sha256": self.parent_weights,
                    "support_file_sha256": self.parent_support,
                    "fingerprint": self.parent_fingerprint,
                },
                "source_identity": source_identity,
                "tensors": {"sha256": tensor_hash},
            }

        committed_sources = {relative: q.sha256_file(self.repo / relative) for relative in required}
        committed_sources["locks/runtime_v4.json"] = q.sha256_file(self.lock_path)
        source_identity["sha256"] = dict(committed_sources)
        vendor_manifest = q._parse_sha_manifest(vendor_parent / "SOURCE_SHA256SUMS", "fixture vendor manifest")
        calibration_base = {
            "archives": archive_records,
            "source_arrow": {"path": "cache/train.arrow", "sha256": self.arrow_hash},
            "source_metadata": {"path": "cache/dataset_info.json", "sha256": self.source_metadata_hash},
            "protected_prompt_sha256": self.protected_hashes,
        }
        self.spec: dict[str, object] = {
            "version": q.PROTOCOL_VERSION,
            "committed_sources": committed_sources,
            "runtime_lock": {"path": "locks/runtime_v4.json", "sha256": q.sha256_file(self.lock_path)},
            "vendor": {
                "commit": q.UPSTREAM_COMMIT,
                "tree": q.UPSTREAM_TREE,
                "root": "vendor/TransformerCompression/source",
                "manifest_path": "vendor/TransformerCompression/SOURCE_SHA256SUMS",
                "manifest_sha256": q.sha256_file(vendor_parent / "SOURCE_SHA256SUMS"),
                "source_sha256": vendor_manifest,
            },
            "calibration": {**calibration_base, "fingerprint": q._fingerprint(calibration_base)},
            "parent_model": {
                "root": "parent",
                "weights_sha256": self.parent_weights,
                "support_sha256": self.parent_support,
                "fingerprint": self.parent_fingerprint,
            },
            "clean_ruler": {"root": "ruler", "files_sha256": self.ruler_files, "fingerprint": q._fingerprint(self.ruler_files)},
        }
        write_json(self.spec_path, self.spec)
        run(["git", "add", "--all"], self.repo)
        for relative in q.EXECUTABLE_VENDOR_PATHS:
            run(["git", "update-index", "--chmod=+x", f"vendor/TransformerCompression/source/{relative}"], self.repo)
        run(["git", "commit", "-qm", "fixture"], self.repo)
        source_identity["commit"] = run(["git", "rev-parse", "HEAD"], self.repo)

        self.fake_materializer = SimpleNamespace(
            CALIBRATION_SEEDS=q.CALIBRATION_SEEDS,
            DISJOINT_PROMPT_PATHS=q.PROTECTED_PROMPT_PATHS,
            MANIFEST_NAME="MANIFEST.sha256",
            METADATA_NAME="calibration_metadata.json",
            SAFETENSORS_NAME="calibration.safetensors",
            COMPLETE_NAME="COMPLETE.json",
            read_json=lambda path: Path(path).read_bytes(),
            canonical_json_bytes=lambda value: value,
            load_disjoint_prompts=lambda _repo: (self.prompt_strings, self.protected_hashes),
            validate_sealed_archive=lambda root, repo=None, parent_model=None: self.calibration_metadata[Path(root)],
        )

    def patches(self):
        return mock.patch.multiple(
            q,
            CALIBRATION_ARROW_SHA256=self.arrow_hash,
            CALIBRATION_METADATA_SHA256=self.source_metadata_hash,
            _load_verified_materializer=lambda _repo, _sources: self.fake_materializer,
        )

    def qualify(self, observation: dict[str, object] | None = None, **overrides) -> dict[str, object]:
        arguments = {
            "repo": self.repo,
            "root": self.archive,
            "runtime_lock_path": self.lock_path,
            "provenance_spec_path": self.spec_path,
            "observation": observation or self.observation,
            "qualifier_source_path": self.repo / "scripts/qualify_slicegpt_runtime_v4.py",
        }
        arguments.update(overrides)
        with self.patches():
            return q.qualify(**arguments)

    def recommit_spec(self) -> None:
        write_json(self.spec_path, self.spec)
        run(["git", "add", "--all"], self.repo)
        run(["git", "commit", "-qm", "coherent attacker rewrite"], self.repo)


class RuntimeUnitTests(unittest.TestCase):
    def test_actual_materializer_validator_surface_is_consumed(self) -> None:
        sources = {
            q.MATERIALIZER_PATH: q.sha256_file(PROJECT / q.MATERIALIZER_PATH)
        }
        module = q._load_verified_materializer(PROJECT, sources)
        self.assertEqual(tuple(module.CALIBRATION_SEEDS), q.CALIBRATION_SEEDS)
        self.assertEqual(tuple(module.DISJOINT_PROMPT_PATHS), q.PROTECTED_PROMPT_PATHS)

    def test_protocol_runtime_and_all_named_drift(self) -> None:
        q.validate_runtime_observation(valid_runtime())
        mutations = [
            ("python", "version", "3.12.4"),
            ("packages", "torch", "2.13.1"),
            ("packages", "torch", "2.13.0+cu130"),
            ("packages", "transformers", "5.14.2"),
            ("packages", "accelerate", "1.14.1"),
            ("packages", "safetensors", "0.8.1"),
            ("torch", "cuda_runtime", "13.1"),
            ("torch", "version", "2.13.0"),
            ("cuda", "driver_version", "595.72.00"),
            ("cuda", "available", 1),
            ("cuda", "device_count", True),
            ("cuda", "current_device", False),
            ("determinism", "deterministic_algorithms", False),
            ("determinism", "deterministic_algorithms", 1),
            ("determinism", "cuda_matmul_allow_tf32", True),
            ("determinism", "cuda_matmul_allow_tf32", 0),
            ("determinism", "cudnn_allow_tf32", 0),
        ]
        for first, second, replacement in mutations:
            with self.subTest(field=f"{first}.{second}"):
                value = valid_runtime()
                value[first][second] = replacement  # type: ignore[index]
                with self.assertRaises(q.QualificationError):
                    q.validate_runtime_observation(value)

        for replacement in ([True, 9], [8, True]):
            with self.subTest(field="cuda.gpu.compute_capability", replacement=replacement):
                value = valid_runtime()
                value["cuda"]["gpu"]["compute_capability"] = replacement
                with self.assertRaises(q.QualificationError):
                    q.validate_runtime_observation(value)

    def test_duplicate_nonfinite_float_noncanonical_and_path_aliases_reject(self) -> None:
        with self.assertRaises(q.QualificationError):
            q.canonical_json_bytes({"finite": 1.0})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            for raw in ['{"a":1,"a":1}\n', '{"a":NaN}\n', '{"a": 1}\n']:
                path.write_text(raw, encoding="utf-8")
                with self.assertRaises(q.QualificationError):
                    q.load_canonical_json(path)
        for alias in ["a/../b", "a//b", "./a", "a\\b", "/a"]:
            with self.subTest(alias=alias), self.assertRaises(q.QualificationError):
                q._canonical_relative(alias, "test")


class EndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.temporary.name))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_seals_per_seed_surface_and_reruns_idempotently(self) -> None:
        result = self.fixture.qualify()
        self.assertEqual(result["status"], "PASS_RUNTIME_PROVENANCE_QUALIFIED")
        self.assertFalse(result["nonzero_slice_authorized"])
        before = {path.name: path.read_bytes() for path in self.fixture.archive.iterdir()}
        self.fixture.qualify()
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.fixture.archive.iterdir()})

    def test_runtime_and_committed_source_drift_create_no_archive(self) -> None:
        observation = copy.deepcopy(self.fixture.observation)
        observation["packages"]["transformers"] = "5.14.2"  # type: ignore[index]
        with self.assertRaises(q.QualificationError):
            self.fixture.qualify(observation)
        self.assertFalse(self.fixture.archive.exists())
        source = self.fixture.repo / "scripts/run_slicegpt_pilot_v4.py"
        source.write_bytes(source.read_bytes() + b"tamper")
        with self.assertRaises(q.QualificationError):
            self.fixture.qualify()

    def test_exact_recursive_parent_and_ruler_membership(self) -> None:
        (self.fixture.repo / "parent/extra.json").write_bytes(b"extra")
        with self.assertRaisesRegex(q.QualificationError, "membership"):
            self.fixture.qualify()
        (self.fixture.repo / "parent/extra.json").unlink()
        (self.fixture.repo / "ruler/empty").mkdir()
        with self.assertRaisesRegex(q.QualificationError, "membership"):
            self.fixture.qualify()

    def test_protected_prompt_set_is_exact(self) -> None:
        first = q.PROTECTED_PROMPT_PATHS[0]
        calibration = self.fixture.spec["calibration"]
        calibration["protected_prompt_sha256"].pop(first)  # type: ignore[index]
        calibration["fingerprint"] = q._fingerprint({key: value for key, value in calibration.items() if key != "fingerprint"})  # type: ignore[union-attr]
        self.fixture.recommit_spec()
        with self.assertRaisesRegex(q.QualificationError, "source set"):
            self.fixture.qualify()

    def test_coherent_parent_rehash_still_fails_calibration_binding(self) -> None:
        path = self.fixture.repo / "parent/model.safetensors"
        path.write_bytes(b"coherent-new-parent")
        weights = {"model.safetensors": q.sha256_file(path)}
        fingerprint = q._fingerprint(
            {
                "source": str(self.fixture.repo / "parent"),
                "weight_file_sha256": weights,
                "support_file_sha256": self.fixture.parent_support,
            }
        )
        self.fixture.spec["parent_model"]["weights_sha256"] = weights  # type: ignore[index]
        self.fixture.spec["parent_model"]["fingerprint"] = fingerprint  # type: ignore[index]
        self.fixture.recommit_spec()
        with self.assertRaisesRegex(q.QualificationError, "parent"):
            self.fixture.qualify()

    def test_coherent_calibration_file_and_spec_rehash_still_fails_semantic_binding(self) -> None:
        seed = "11"
        record = self.fixture.spec["calibration"]["archives"][seed]  # type: ignore[index]
        path = self.fixture.repo / str(record["root"]) / "calibration.safetensors"
        path.write_bytes(b"coherently-rehashed-but-different-calibration")
        record["tensors_sha256"] = q.sha256_file(path)
        calibration = self.fixture.spec["calibration"]
        calibration["fingerprint"] = q._fingerprint(
            {key: value for key, value in calibration.items() if key != "fingerprint"}  # type: ignore[union-attr]
        )
        self.fixture.recommit_spec()
        with self.assertRaisesRegex(q.QualificationError, "tensor archive identity"):
            self.fixture.qualify()

    def test_spec_must_be_committed_and_target_must_be_derisk(self) -> None:
        self.fixture.spec_path.write_bytes(self.fixture.spec_path.read_bytes() + b" ")
        with self.assertRaises(q.QualificationError):
            self.fixture.qualify()
        self.fixture.spec_path.write_bytes(q.canonical_json_bytes(self.fixture.spec))
        for root in [self.fixture.repo / ".git/runtime-qualification", self.fixture.repo / "vendor/runtime-qualification"]:
            with self.assertRaisesRegex(q.QualificationError, "derisk"):
                self.fixture.qualify(root=root)

    def test_archive_tamper_partial_and_replay_source_drift_fail_closed(self) -> None:
        self.fixture.qualify()
        (self.fixture.archive / "qualification.json").write_bytes(b"{}\n")
        with self.assertRaises(q.QualificationError):
            self.fixture.qualify()
        shutil.rmtree(self.fixture.archive)
        self.fixture.archive.mkdir()
        marker = self.fixture.archive / "partial-evidence.txt"
        marker.write_bytes(b"preserve me")
        with self.assertRaises(q.QualificationError):
            self.fixture.qualify()
        self.assertEqual(marker.read_bytes(), b"preserve me")

    def test_replay_binds_current_qualifier_source(self) -> None:
        self.fixture.qualify()
        source = self.fixture.repo / "scripts/qualify_slicegpt_runtime_v4.py"
        source.write_bytes(source.read_bytes() + b"# drift\n")
        with self.assertRaisesRegex(q.QualificationError, "qualifier source"):
            self.fixture.qualify()


if __name__ == "__main__":
    unittest.main(verbosity=2)
