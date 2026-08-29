import hashlib
import importlib.util
import json
import math
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("materialize_slicegpt_calibration_v4.py")
SPEC = importlib.util.spec_from_file_location("materialize_slicegpt_calibration_v4", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def valid_runtime_observation():
    return {
        "version": MODULE.RUNTIME_LOCK_VERSION,
        "python": {
            "version": "3.12.3",
            "implementation": "CPython",
            "executable": "/opt/v4/bin/python",
            "executable_sha256": "1" * 64,
        },
        "packages": {
            key: value for key, value in MODULE.EXPECTED_RUNTIME.items() if key != "python"
        },
        "platform": {
            "system": "Linux",
            "release": "6.8.0-test",
            "version": "#1-test",
            "machine": "x86_64",
        },
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
            "driver_version": MODULE.EXPECTED_NVIDIA_DRIVER,
            "gpu": {
                "name": "NVIDIA L4",
                "total_memory_bytes": 24152817664,
                "compute_capability": [8, 9],
            },
        },
        "determinism": dict(MODULE.EXPECTED_DETERMINISM),
    }


def make_safetensors(path, input_value=2, mask_value=1, seed=11):
    count = MODULE.NSAMPLES * MODULE.SEQLEN
    mask = struct.pack("<q", mask_value) * count
    ids = struct.pack("<q", input_value) * count
    header = {
        "__metadata__": {
            "version": MODULE.VERSION,
            "dataset": f"{MODULE.DATASET_NAME}/{MODULE.DATASET_CONFIG}:{MODULE.DATASET_SPLIT}",
            "seed": str(seed),
        },
        "attention_mask": {
            "dtype": MODULE.TENSOR_DTYPE,
            "shape": MODULE.TENSOR_SHAPE,
            "data_offsets": [0, len(mask)],
        },
        "input_ids": {
            "dtype": MODULE.TENSOR_DTYPE,
            "shape": MODULE.TENSOR_SHAPE,
            "data_offsets": [len(mask), len(mask) + len(ids)],
        },
    }
    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    header_bytes += b" " * ((8 - len(header_bytes) % 8) % 8)
    Path(path).write_bytes(struct.pack("<Q", len(header_bytes)) + header_bytes + mask + ids)


def fake_metadata(root, input_value=2, mask_value=1, seed=11, tokenizer_length=10):
    tensors_path = root / MODULE.SAFETENSORS_NAME
    make_safetensors(tensors_path, input_value=input_value, mask_value=mask_value, seed=seed)
    support = {"tokenizer.json": "a" * 64}
    tokenizer_body = {
        "source": "C:/exact/model",
        "class": "GemmaTokenizerFast",
        "length": tokenizer_length,
        "vocab_size": tokenizer_length,
        "special_tokens_map": {"bos_token": "<bos>", "eos_token": "<eos>"},
        "padding_side": "left",
        "support_file_sha256": support,
    }
    parent_body = {
        "source": "C:/exact/model",
        "weight_file_sha256": {"model.safetensors": "b" * 64},
        "support_file_sha256": support,
    }
    runtime_observation = valid_runtime_observation()
    body = {
        "version": MODULE.VERSION,
        "seed": seed,
        "dataset": {
            "name": MODULE.DATASET_NAME,
            "config": MODULE.DATASET_CONFIG,
            "split": MODULE.DATASET_SPLIT,
            "column_names": ["text"],
            "row_count": MODULE.EXPECTED_TRAIN_ROWS,
            "source_cache_sha256": {
                "train_arrow": MODULE.ARROW_SHA256,
                "dataset_metadata": MODULE.DATASET_METADATA_SHA256,
            },
        },
        "preprocessing": MODULE.PREPROCESSING,
        "tokenizer": {
            **tokenizer_body,
            "fingerprint": MODULE.fingerprint(tokenizer_body),
        },
        "parent": {
            **parent_body,
            "fingerprint": MODULE.fingerprint(parent_body),
        },
        "tensors": {
            "file": MODULE.SAFETENSORS_NAME,
            "sha256": MODULE.sha256_of_file(tensors_path),
            "records": MODULE.parse_safetensors(tensors_path, expected_seed=seed),
        },
        "disjointness": {
            "normalisation": MODULE.NORMALISATION,
            "match_policy": "full protected prompt as substring of decoded calibration row",
            "protected_prompt_count": 3,
            "decoded_row_count": MODULE.NSAMPLES,
            "exact_matches": [],
            "normalised_matches": [],
            "source_file_sha256": {
                name: "c" * 64 for name in MODULE.DISJOINT_PROMPT_PATHS
            },
        },
        "runtime": {
            "runtime_lock_sha256": hashlib.sha256(
                MODULE.canonical_json_bytes(runtime_observation)
            ).hexdigest(),
            "observation": runtime_observation,
        },
        "vendor": {
            "commit": MODULE.VENDOR_COMMIT,
            "data_utils_path": MODULE.VENDOR_DATA_UTILS,
            "data_utils_sha256": "d" * 64,
        },
        "source_identity": {
            "commit": "0" * 40,
            "sha256": {
                name: ("c" * 64 if name in MODULE.DISJOINT_PROMPT_PATHS else "d" * 64)
                for name in MODULE.COMMITTED_PATHS
            },
        },
    }
    return {**body, "fingerprint": MODULE.fingerprint(body)}


def build_archive(root, input_value=2, mask_value=1, seed=11, tokenizer_length=10):
    root.mkdir()
    metadata = fake_metadata(
        root,
        input_value=input_value,
        mask_value=mask_value,
        seed=seed,
        tokenizer_length=tokenizer_length,
    )
    metadata_path = root / MODULE.METADATA_NAME
    MODULE.atomic_write_json(metadata_path, metadata)
    complete = {
        "status": "complete",
        "outcome": "CALIBRATION_TENSORS_MATERIALIZED",
        "metadata_sha256": MODULE.sha256_of_file(metadata_path),
        "tensors_sha256": MODULE.sha256_of_file(root / MODULE.SAFETENSORS_NAME),
        "metadata_fingerprint": metadata["fingerprint"],
    }
    MODULE.atomic_write_json(root / MODULE.COMPLETE_NAME, complete)
    MODULE.write_manifest(root)
    return metadata


def rewrite_metadata_and_seal(root, metadata):
    metadata_path = root / MODULE.METADATA_NAME
    MODULE.atomic_write_json(metadata_path, metadata)
    MODULE.atomic_write_json(
        root / MODULE.COMPLETE_NAME,
        {
            "status": "complete",
            "outcome": "CALIBRATION_TENSORS_MATERIALIZED",
            "metadata_sha256": MODULE.sha256_of_file(metadata_path),
            "tensors_sha256": MODULE.sha256_of_file(root / MODULE.SAFETENSORS_NAME),
            "metadata_fingerprint": metadata["fingerprint"],
        },
    )
    MODULE.write_manifest(root)


class CalibrationMaterializerTests(unittest.TestCase):
    def test_frozen_contract_constants(self):
        self.assertEqual(MODULE.TENSOR_SHAPE, [128, 2048])
        self.assertEqual(MODULE.BATCH_SIZE, 16)
        self.assertFalse(MODULE.PREPROCESSING["varied_sequence_lengths"])
        self.assertEqual(MODULE.CALIBRATION_SEEDS, (0, 1, 2, 7, 11))
        self.assertEqual(MODULE.EXPECTED_RUNTIME["transformers"], "5.14.1")
        self.assertEqual(MODULE.EXPECTED_RUNTIME["torch"], "2.13.0+cu130")
        self.assertEqual(MODULE.EXPECTED_DETERMINISM["cublas_workspace_config"], ":4096:8")
        self.assertEqual(MODULE.EXPECTED_DETERMINISM["cuda_matmul_allow_tf32"], False)
        self.assertIn("fresh private temporary directory", MODULE.PREPROCESSING["derived_filter_cache"])
        self.assertEqual(
            MODULE.ARROW_SHA256,
            "57947bc7b58df4b19662c0609cc30651bc84328dab5fd588860b752072911789",
        )
        self.assertEqual(
            MODULE.DATASET_METADATA_SHA256,
            "47ce56e8a2ca0183a37850cbce75cec29f64a1f61da978386c2a0598da4a6f66",
        )

    def test_valid_archive_is_exact_and_dependency_free(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            expected = build_archive(root)
            before = set(sys.modules)
            actual = MODULE.validate_sealed_archive(root)
            after = set(sys.modules)
            self.assertEqual(actual, expected)
            self.assertNotIn("datasets", after - before)
            self.assertNotIn("torch", after - before)
            self.assertNotIn("transformers", after - before)
            self.assertTrue(MODULE.verify_manifest(root))

    def test_safetensors_records_exact_shape_hashes_and_all_one_mask(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.safetensors"
            make_safetensors(path, input_value=7)
            records = MODULE.parse_safetensors(path, expected_seed=11)
            self.assertEqual(records["input_ids"]["shape"], [128, 2048])
            self.assertEqual(records["input_ids"]["minimum"], 7)
            self.assertEqual(records["input_ids"]["maximum"], 7)
            self.assertTrue(records["attention_mask"]["all_one"])
            self.assertRegex(records["input_ids"]["byte_sha256"], r"^[0-9a-f]{64}$")

    def test_mask_zero_is_rejected_even_with_rewritten_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            build_archive(root)
            make_safetensors(root / MODULE.SAFETENSORS_NAME, mask_value=0)
            MODULE.write_manifest(root)
            with self.assertRaisesRegex(RuntimeError, "not all-one"):
                MODULE.validate_sealed_archive(root)

    def test_input_id_outside_tokenizer_range_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            build_archive(root, input_value=20, tokenizer_length=10)
            with self.assertRaisesRegex(RuntimeError, "tensor identity changed"):
                MODULE.validate_sealed_archive(root)

    def test_safetensors_header_seed_shape_and_trailing_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.safetensors"
            make_safetensors(path, seed=7)
            with self.assertRaisesRegex(RuntimeError, "header metadata changed"):
                MODULE.parse_safetensors(path, expected_seed=11)

            raw = path.read_bytes()
            header_length = struct.unpack("<Q", raw[:8])[0]
            header = raw[8 : 8 + header_length]
            changed = header.replace(b'"shape":[128,2048]', b'"shape":[128,2049]')
            self.assertEqual(len(changed), len(header))
            path.write_bytes(raw[:8] + changed + raw[8 + header_length :])
            with self.assertRaisesRegex(RuntimeError, "schema changed"):
                MODULE.parse_safetensors(path, expected_seed=7)

            make_safetensors(path)
            path.write_bytes(path.read_bytes() + b"x")
            with self.assertRaisesRegex(RuntimeError, "trailing or missing"):
                MODULE.parse_safetensors(path, expected_seed=11)

    def test_semantic_rehash_attack_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            metadata = build_archive(root)
            metadata["seed"] = 42
            metadata["fingerprint"] = MODULE.fingerprint(
                {key: value for key, value in metadata.items() if key != "fingerprint"}
            )
            rewrite_metadata_and_seal(root, metadata)
            with self.assertRaisesRegex(RuntimeError, "semantics changed"):
                MODULE.validate_sealed_archive(root)

    def test_manifest_tamper_extra_temp_and_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            build_archive(root)
            (root / "extra.txt").write_text("extra", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "changed"):
                MODULE.verify_manifest(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            build_archive(root)
            (root / (MODULE.MANIFEST_NAME + ".tmp")).write_text("partial", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "changed"):
                MODULE.verify_manifest(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / MODULE.MANIFEST_NAME).write_text(
                f"{'0' * 64}  ../escape\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "malformed"):
                MODULE.verify_manifest(root)

    def test_nonfinite_json_rejected_recursively(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaisesRegex(RuntimeError, "non-finite"):
                MODULE.canonical_json_bytes({"nested": [{"value": value}]})

    def test_prompt_extraction_and_normalisation(self):
        payload = [
            {"prompt": "  Hello World  ", "answer": "ignored answer"},
            {"nested": {"instruction": "Do THIS"}},
            {"id": "ignored"},
        ]
        prompts = MODULE.collect_prompt_strings(payload)
        self.assertEqual(prompts, {"Hello World", "Do THIS"})
        self.assertEqual(MODULE.normalise_text("  HéLLo\tWORLD "), "héllo world")

    def test_disjointness_rejects_exact_and_normalised_substrings(self):
        with self.assertRaisesRegex(RuntimeError, "overlap"):
            MODULE.check_disjointness(["prefix Exact Prompt suffix"], {"Exact Prompt"})
        with self.assertRaisesRegex(RuntimeError, "overlap"):
            MODULE.check_disjointness(["prefix hello   WORLD suffix"], {"Hello World"})
        result = MODULE.check_disjointness(["unrelated calibration row"], {"Hello World"})
        self.assertEqual(result["exact_matches"], [])
        self.assertEqual(result["normalised_matches"], [])

    def test_source_cache_hashes_are_exact_and_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            arrow = Path(directory) / "train.arrow"
            metadata = Path(directory) / "state.json"
            arrow.write_bytes(b"arrow fixture")
            metadata.write_bytes(b"metadata fixture")
            original_arrow = MODULE.ARROW_SHA256
            original_metadata = MODULE.DATASET_METADATA_SHA256
            try:
                MODULE.ARROW_SHA256 = hashlib.sha256(arrow.read_bytes()).hexdigest()
                MODULE.DATASET_METADATA_SHA256 = hashlib.sha256(metadata.read_bytes()).hexdigest()
                self.assertEqual(
                    MODULE.validate_source_cache(arrow, metadata),
                    {
                        "train_arrow": MODULE.ARROW_SHA256,
                        "dataset_metadata": MODULE.DATASET_METADATA_SHA256,
                    },
                )
                arrow.write_bytes(b"changed")
                with self.assertRaisesRegex(RuntimeError, "hashes changed"):
                    MODULE.validate_source_cache(arrow, metadata)
            finally:
                MODULE.ARROW_SHA256 = original_arrow
                MODULE.DATASET_METADATA_SHA256 = original_metadata

    def test_runtime_lock_is_canonical_exact_and_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime_lock.json"
            observation = valid_runtime_observation()
            path.write_bytes(MODULE.canonical_json_bytes(observation))
            actual, digest = MODULE.load_runtime_lock(path)
            self.assertEqual(actual, observation)
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())

            changed = valid_runtime_observation()
            changed["determinism"]["cuda_matmul_allow_tf32"] = True
            path.write_bytes(MODULE.canonical_json_bytes(changed))
            with self.assertRaisesRegex(RuntimeError, "determinism contract changed"):
                MODULE.load_runtime_lock(path)

            path.write_text(json.dumps(observation), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "canonical JSON"):
                MODULE.load_runtime_lock(path)

    def test_rehashed_archive_cannot_change_runtime_lock_or_hardware(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            metadata = build_archive(root)
            metadata["runtime"]["observation"]["cuda"]["gpu"]["name"] = "substitute GPU"
            observation = metadata["runtime"]["observation"]
            metadata["runtime"]["runtime_lock_sha256"] = hashlib.sha256(
                MODULE.canonical_json_bytes(observation)
            ).hexdigest()
            metadata["fingerprint"] = MODULE.fingerprint(
                {key: value for key, value in metadata.items() if key != "fingerprint"}
            )
            rewrite_metadata_and_seal(root, metadata)
            with self.assertRaisesRegex(RuntimeError, "frozen NVIDIA L4"):
                MODULE.validate_sealed_archive(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            metadata = build_archive(root)
            metadata["runtime"]["observation"]["cuda"]["gpu"]["compute_capability"] = [8.0, 9.0]
            observation = metadata["runtime"]["observation"]
            metadata["runtime"]["runtime_lock_sha256"] = hashlib.sha256(
                MODULE.canonical_json_bytes(observation)
            ).hexdigest()
            metadata["fingerprint"] = MODULE.fingerprint(
                {key: value for key, value in metadata.items() if key != "fingerprint"}
            )
            rewrite_metadata_and_seal(root, metadata)
            with self.assertRaisesRegex(RuntimeError, "frozen NVIDIA L4"):
                MODULE.validate_sealed_archive(root)

    def test_disjointness_policy_types_and_committed_prompt_count_are_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            metadata = build_archive(root)
            metadata["disjointness"]["match_policy"] = "attacker-selected policy"
            metadata["fingerprint"] = MODULE.fingerprint(
                {key: value for key, value in metadata.items() if key != "fingerprint"}
            )
            rewrite_metadata_and_seal(root, metadata)
            with self.assertRaisesRegex(RuntimeError, "disjointness evidence changed"):
                MODULE.validate_sealed_archive(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            metadata = build_archive(root)
            metadata["disjointness"]["protected_prompt_count"] = True
            metadata["fingerprint"] = MODULE.fingerprint(
                {key: value for key, value in metadata.items() if key != "fingerprint"}
            )
            rewrite_metadata_and_seal(root, metadata)
            with self.assertRaisesRegex(RuntimeError, "disjointness evidence changed"):
                MODULE.validate_sealed_archive(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            metadata = build_archive(root)
            recorded_hashes = metadata["disjointness"]["source_file_sha256"]
            with (
                mock.patch.object(MODULE, "validate_recorded_source_identity"),
                mock.patch.object(
                    MODULE,
                    "load_disjoint_prompts",
                    return_value=({"prompt one", "prompt two"}, recorded_hashes),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "protected prompt count changed"):
                    MODULE.validate_sealed_archive(root, repo=Path(directory))

    def test_archive_validation_binds_supplied_immutable_runtime_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "archive"
            metadata = build_archive(root)
            matching = base / "matching.json"
            matching.write_bytes(
                MODULE.canonical_json_bytes(metadata["runtime"]["observation"])
            )
            self.assertEqual(
                MODULE.validate_sealed_archive(root, runtime_lock_path=matching), metadata
            )

            different = valid_runtime_observation()
            different["cuda"]["gpu"]["total_memory_bytes"] += 1
            other = base / "other.json"
            other.write_bytes(MODULE.canonical_json_bytes(different))
            with self.assertRaisesRegex(RuntimeError, "does not match the supplied"):
                MODULE.validate_sealed_archive(root, runtime_lock_path=other)

    def test_configure_determinism_sets_and_verifies_all_controls(self):
        state = {"enabled": False}

        class FakeTorch:
            backends = types.SimpleNamespace(
                cuda=types.SimpleNamespace(matmul=types.SimpleNamespace(allow_tf32=True)),
                cudnn=types.SimpleNamespace(allow_tf32=True),
            )

            @staticmethod
            def use_deterministic_algorithms(value):
                state["enabled"] = value

            @staticmethod
            def are_deterministic_algorithms_enabled():
                return state["enabled"]

        with mock.patch.dict("os.environ", {"CUBLAS_WORKSPACE_CONFIG": ":4096:8"}):
            MODULE.configure_determinism(FakeTorch)
        self.assertTrue(state["enabled"])
        self.assertFalse(FakeTorch.backends.cuda.matmul.allow_tf32)
        self.assertFalse(FakeTorch.backends.cudnn.allow_tf32)
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "must be set before Python starts"):
                MODULE.configure_determinism(FakeTorch)

    def test_arrow_filter_cache_is_pristine_and_isolated_from_adversarial_sibling(self):
        with tempfile.TemporaryDirectory() as directory:
            source_dir = Path(directory) / "frozen-cache"
            source_dir.mkdir()
            arrow = source_dir / "train.arrow"
            adversarial = source_dir / "cache-adversarial.arrow"
            arrow.write_bytes(b"exact source bytes")
            adversarial.write_bytes(b"attacker-controlled derived filter cache")
            before = {path.name: path.read_bytes() for path in source_dir.iterdir()}
            with MODULE.isolated_arrow_copy(arrow) as isolated:
                self.assertEqual(isolated.read_bytes(), arrow.read_bytes())
                self.assertEqual({path.name for path in isolated.parent.iterdir()}, {"train.arrow"})
                self.assertNotEqual(isolated.parent, source_dir)
                (isolated.parent / "cache-derived.arrow").write_bytes(b"upstream cache")
            after = {path.name: path.read_bytes() for path in source_dir.iterdir()}
            self.assertEqual(after, before)

    def test_datasets_derived_cache_reuse_is_explicitly_disabled(self):
        class FakeDatasets:
            enabled = True

            @classmethod
            def disable_caching(cls):
                cls.enabled = False

            @classmethod
            def is_caching_enabled(cls):
                return cls.enabled

        MODULE.disable_datasets_derived_cache(FakeDatasets)
        self.assertFalse(FakeDatasets.enabled)

        class RefusesDisable(FakeDatasets):
            @classmethod
            def disable_caching(cls):
                cls.enabled = True

        with self.assertRaisesRegex(RuntimeError, "could not be disabled"):
            MODULE.disable_datasets_derived_cache(RefusesDisable)

    def test_vendor_import_rejects_preloaded_module_and_verifies_path_hash(self):
        fake = types.ModuleType("slicegpt.data_utils")
        sys.modules["slicegpt.data_utils"] = fake
        try:
            with self.assertRaisesRegex(RuntimeError, "preloaded slicegpt modules"):
                MODULE.load_verified_prepare_dataloader(Path.cwd(), "0" * 64)
        finally:
            sys.modules.pop("slicegpt.data_utils", None)

        repo = Path(__file__).resolve().parents[1]
        expected_path = repo / MODULE.VENDOR_DATA_UTILS
        expected_hash = MODULE.sha256_of_file(expected_path)
        marker = object()
        loaded = types.SimpleNamespace(__file__=str(expected_path), prepare_dataloader=marker)
        with mock.patch.object(MODULE.importlib, "import_module", return_value=loaded):
            self.assertIs(MODULE.load_verified_prepare_dataloader(repo, expected_hash), marker)
        with mock.patch.object(MODULE.importlib, "import_module", return_value=loaded):
            with self.assertRaisesRegex(RuntimeError, "not the recorded vendored source"):
                MODULE.load_verified_prepare_dataloader(repo, "0" * 64)

    def test_committed_source_binding_rejects_dirty_blob(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            source = repo / "source.py"
            source.write_text("value = 1\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            subprocess.run(["git", "add", "source.py"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
            identity = MODULE.committed_source_identity(repo, ("source.py",))
            self.assertEqual(set(identity["sha256"]), {"source.py"})
            source.write_text("value = 2\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "differs"):
                MODULE.committed_source_identity(repo, ("source.py",))

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks unsupported")
    def test_symlink_ancestor_is_rejected_when_platform_allows(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            target = base / "target"
            target.mkdir()
            link = base / "link"
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest("symlink creation not permitted")
            with self.assertRaisesRegex(RuntimeError, "symlink component"):
                MODULE.reject_symlink_components(link / "archive", "fixture")


if __name__ == "__main__":
    unittest.main()
