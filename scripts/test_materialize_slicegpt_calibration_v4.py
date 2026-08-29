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
TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


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


def make_safetensors(path, input_value=4, mask_value=1, seed=11, bos_value=2):
    count = MODULE.NSAMPLES * MODULE.SEQLEN
    mask = struct.pack("<q", mask_value) * count
    row = struct.pack("<q", bos_value) + struct.pack("<q", input_value) * (MODULE.SEQLEN - 1)
    ids = row * MODULE.NSAMPLES
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


def fake_metadata(root, input_value=4, mask_value=1, seed=11, tokenizer_length=10):
    tensors_path = root / MODULE.SAFETENSORS_NAME
    make_safetensors(tensors_path, input_value=input_value, mask_value=mask_value, seed=seed)
    support = {"tokenizer.json": "a" * 64}
    tokenizer_body = {
        "source": "C:/exact/model",
        "class": "GemmaTokenizerFast",
        "length": tokenizer_length,
        "vocab_size": tokenizer_length,
        "special_tokens_map": {
            "bos_token": "<bos>",
            "eos_token": "<eos>",
            "unk_token": "<unk>",
        },
        "padding_side": "left",
        "bos_token_id": 2,
        "unk_token_id": 3,
        "unk_policy": "reject any non-UNK token mapped to unk_token_id",
        "lossless_proxy": "documented project adapter; not unchanged upstream retokenization",
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
            "records": MODULE.parse_safetensors(
                tensors_path,
                expected_seed=seed,
                expected_bos_token_id=MODULE.EXPECTED_BOS_TOKEN_ID,
            ),
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
        "sampler_order": {
            "seed": seed,
            "algorithm": MODULE.PREPROCESSING["sampler"],
            "placeholder_indices": list(MODULE.FROZEN_SAMPLER_ORDERS[seed]),
            "sha256": MODULE.FROZEN_SAMPLER_ORDER_SHA256[seed],
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


def build_archive(root, input_value=4, mask_value=1, seed=11, tokenizer_length=10):
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
    class _FakeTensor:
        def __init__(self, values):
            self.values = values
            self.shape = (len(values), len(values[0]))

    class _FakeTorch:
        int64 = "int64"

        @staticmethod
        def tensor(values, dtype=None):
            return CalibrationMaterializerTests._FakeTensor(values)

        @staticmethod
        def ones_like(tensor, dtype=None):
            return CalibrationMaterializerTests._FakeTensor(
                [[1] * tensor.shape[1] for _ in range(tensor.shape[0])]
            )

    class _FakeTokenizer:
        bos_token_id = 2
        unk_token_id = 3
        unk_token = "<unk>"

        def __init__(self, unk_substitution=False):
            self.unk_substitution = unk_substitution
            self.tokens = [f"token_{index}" for index in range(MODULE.SEQLEN)]
            self.ids = {token: index + 10 for index, token in enumerate(self.tokens)}
            self.reverse = {value: key for key, value in self.ids.items()}
            self.reverse[self.unk_token_id] = self.unk_token

        def __len__(self):
            return 4096

        def tokenize(self, text):
            return list(self.tokens)

        def convert_tokens_to_ids(self, tokens):
            values = [self.ids[token] for token in tokens]
            if self.unk_substitution:
                values[0] = self.unk_token_id
            return values

        def convert_ids_to_tokens(self, values):
            return [self.reverse[value] for value in values]

        def build_inputs_with_special_tokens(self, values):
            return [self.bos_token_id, *values]

    def test_frozen_contract_constants(self):
        self.assertEqual(MODULE.TENSOR_SHAPE, [128, 2048])
        self.assertEqual(MODULE.BATCH_SIZE, 16)
        self.assertFalse(MODULE.PREPROCESSING["varied_sequence_lengths"])
        self.assertEqual(MODULE.CALIBRATION_SEEDS, (0, 1, 2, 7, 11))
        self.assertEqual(set(MODULE.FROZEN_SAMPLER_ORDERS), set(MODULE.CALIBRATION_SEEDS))
        for seed, order in MODULE.FROZEN_SAMPLER_ORDERS.items():
            self.assertEqual(len(order), MODULE.NSAMPLES)
            self.assertEqual(sorted(order), list(range(MODULE.NSAMPLES)))
            self.assertEqual(
                MODULE.FROZEN_SAMPLER_ORDER_SHA256[seed],
                MODULE.fingerprint(list(order)),
            )
        self.assertEqual(MODULE.EXPECTED_RUNTIME["transformers"], "5.14.1")
        self.assertEqual(MODULE.EXPECTED_RUNTIME["torch"], "2.13.0")
        self.assertEqual(MODULE.EXPECTED_TORCH_BUILD, "2.13.0+cu130")
        self.assertEqual(MODULE.EXPECTED_DETERMINISM["cublas_workspace_config"], ":4096:8")
        self.assertEqual(MODULE.EXPECTED_DETERMINISM["cuda_matmul_allow_tf32"], False)
        self.assertIn("fresh private temporary directory", MODULE.PREPROCESSING["derived_filter_cache"])
        self.assertIn("lossless-token-preservation proxy", MODULE.PREPROCESSING["implementation"])
        self.assertEqual(
            MODULE.ARROW_SHA256,
            "57947bc7b58df4b19662c0609cc30651bc84328dab5fd588860b752072911789",
        )
        self.assertEqual(
            MODULE.DATASET_METADATA_SHA256,
            "47ce56e8a2ca0183a37850cbce75cec29f64a1f61da978386c2a0598da4a6f66",
        )

    def test_lossless_proxy_preserves_exact_tokens_adds_one_bos_and_tracks_order(self):
        base = self._FakeTokenizer()
        proxy = MODULE.LosslessVendorTokenizerProxy(base, self._FakeTorch)
        self.assertEqual(proxy.tokenize("fixture"), base.tokens)
        placeholder = proxy.convert_tokens_to_string(list(base.tokens))
        batch = proxy(
            [placeholder],
            padding="longest",
            max_length=MODULE.SEQLEN,
            truncation=True,
            return_tensors="pt",
        )
        ids = batch["input_ids"].values[0]
        self.assertEqual(len(ids), MODULE.SEQLEN)
        self.assertEqual(ids[0], base.bos_token_id)
        self.assertEqual(ids[1:], [base.ids[token] for token in base.tokens[: MODULE.SEQLEN - 1]])
        self.assertEqual(ids.count(base.bos_token_id), 1)
        self.assertEqual(batch["attention_mask"].values[0], [1] * MODULE.SEQLEN)
        self.assertEqual(proxy.assert_complete(expected_blocks=1, expected_order=[0]), (0,))

    def test_lossless_proxy_rejects_unknown_duplicate_raw_pair_kwargs_and_unk_substitution(self):
        base = self._FakeTokenizer()
        proxy = MODULE.LosslessVendorTokenizerProxy(base, self._FakeTorch)
        placeholder = proxy.convert_tokens_to_string(list(base.tokens))
        exact = {
            "padding": "longest",
            "max_length": MODULE.SEQLEN,
            "truncation": True,
            "return_tensors": "pt",
        }
        with self.assertRaisesRegex(RuntimeError, "unknown/substituted"):
            proxy(["raw or attacker text"], **exact)
        with self.assertRaisesRegex(RuntimeError, "final tokenizer call changed"):
            proxy([placeholder], [placeholder], **exact)
        with self.assertRaisesRegex(RuntimeError, "final tokenizer call changed"):
            proxy([placeholder], **{**exact, "add_special_tokens": True})
        proxy([placeholder], **exact)
        with self.assertRaisesRegex(RuntimeError, "sampled more than once"):
            proxy([placeholder], **exact)

        bad = self._FakeTokenizer(unk_substitution=True)
        bad_proxy = MODULE.LosslessVendorTokenizerProxy(bad, self._FakeTorch)
        bad_placeholder = bad_proxy.convert_tokens_to_string(list(bad.tokens))
        with self.assertRaisesRegex(RuntimeError, "non-UNK token to the UNK ID"):
            bad_proxy([bad_placeholder], **exact)

        short_proxy = MODULE.LosslessVendorTokenizerProxy(base, self._FakeTorch)
        with self.assertRaisesRegex(RuntimeError, "exact 2048-token"):
            short_proxy.convert_tokens_to_string(base.tokens[:-1])

        order_proxy = MODULE.LosslessVendorTokenizerProxy(base, self._FakeTorch)
        first = order_proxy.convert_tokens_to_string(list(base.tokens))
        second = order_proxy.convert_tokens_to_string(list(base.tokens))
        order_proxy([second, first], **exact)
        with self.assertRaisesRegex(RuntimeError, "SubsetRandomSampler order"):
            order_proxy.assert_complete(expected_blocks=2, expected_order=[0, 1])

    def test_variable_vendor_batch_widths_fail_before_cat_or_archive_creation(self):
        tensor_2037 = types.SimpleNamespace(shape=(16, 2037))
        batch = {
            "input_ids": tensor_2037,
            "attention_mask": tensor_2037,
            "labels": tensor_2037,
        }
        with self.assertRaisesRegex(RuntimeError, "round-trip is lossy"):
            MODULE.validate_upstream_batch_contract(batch, 0, 0)
        tensor_2048 = types.SimpleNamespace(shape=(16, 2048))
        valid = {name: tensor_2048 for name in ("input_ids", "attention_mask", "labels")}
        self.assertEqual(MODULE.validate_upstream_batch_contract(valid, 0, 0), 16)

    @unittest.skipUnless(TORCH_AVAILABLE, "exact Torch sampler derivation is server-only")
    def test_live_torch_recomputes_every_frozen_sampler_order(self):
        import torch

        for seed in MODULE.CALIBRATION_SEEDS:
            self.assertEqual(
                MODULE.expected_vendor_sampler_order(torch, seed),
                list(MODULE.FROZEN_SAMPLER_ORDERS[seed]),
            )

    def test_coherent_sampler_bos_and_bool_seed_tampering_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            metadata = build_archive(root)
            order = metadata["sampler_order"]["placeholder_indices"]
            changed = order[1:] + order[:1]
            metadata["sampler_order"]["placeholder_indices"] = changed
            metadata["sampler_order"]["sha256"] = MODULE.fingerprint(changed)
            metadata["fingerprint"] = MODULE.fingerprint(
                {key: value for key, value in metadata.items() if key != "fingerprint"}
            )
            rewrite_metadata_and_seal(root, metadata)
            with self.assertRaisesRegex(RuntimeError, "sampler order changed"):
                MODULE.validate_sealed_archive(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            metadata = build_archive(root)
            make_safetensors(
                root / MODULE.SAFETENSORS_NAME,
                input_value=4,
                seed=11,
                bos_value=5,
            )
            tokenizer_body = {
                key: value
                for key, value in metadata["tokenizer"].items()
                if key != "fingerprint"
            }
            tokenizer_body["bos_token_id"] = 5
            metadata["tokenizer"] = {
                **tokenizer_body,
                "fingerprint": MODULE.fingerprint(tokenizer_body),
            }
            metadata["tensors"]["sha256"] = MODULE.sha256_of_file(
                root / MODULE.SAFETENSORS_NAME
            )
            metadata["fingerprint"] = MODULE.fingerprint(
                {key: value for key, value in metadata.items() if key != "fingerprint"}
            )
            rewrite_metadata_and_seal(root, metadata)
            with self.assertRaisesRegex(RuntimeError, "tokenizer identity changed"):
                MODULE.validate_sealed_archive(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            metadata = build_archive(root, seed=1)
            metadata["seed"] = True
            metadata["sampler_order"]["seed"] = True
            metadata["fingerprint"] = MODULE.fingerprint(
                {key: value for key, value in metadata.items() if key != "fingerprint"}
            )
            rewrite_metadata_and_seal(root, metadata)
            with self.assertRaisesRegex(RuntimeError, "metadata semantics changed"):
                MODULE.validate_sealed_archive(root)

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
            records = MODULE.parse_safetensors(
                path, expected_seed=11, expected_bos_token_id=MODULE.EXPECTED_BOS_TOKEN_ID
            )
            self.assertEqual(records["input_ids"]["shape"], [128, 2048])
            self.assertEqual(records["input_ids"]["minimum"], MODULE.EXPECTED_BOS_TOKEN_ID)
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
                MODULE.parse_safetensors(
                    path, expected_seed=11, expected_bos_token_id=MODULE.EXPECTED_BOS_TOKEN_ID
                )

            raw = path.read_bytes()
            header_length = struct.unpack("<Q", raw[:8])[0]
            header = raw[8 : 8 + header_length]
            changed = header.replace(b'"shape":[128,2048]', b'"shape":[128,2049]')
            self.assertEqual(len(changed), len(header))
            path.write_bytes(raw[:8] + changed + raw[8 + header_length :])
            with self.assertRaisesRegex(RuntimeError, "schema changed"):
                MODULE.parse_safetensors(
                    path, expected_seed=7, expected_bos_token_id=MODULE.EXPECTED_BOS_TOKEN_ID
                )

            make_safetensors(path)
            path.write_bytes(path.read_bytes() + b"x")
            with self.assertRaisesRegex(RuntimeError, "trailing or missing"):
                MODULE.parse_safetensors(
                    path, expected_seed=11, expected_bos_token_id=MODULE.EXPECTED_BOS_TOKEN_ID
                )

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

    def test_torch_distribution_and_cuda_build_versions_cannot_alias_or_substitute(self):
        valid = valid_runtime_observation()
        self.assertEqual(valid["packages"]["torch"], "2.13.0")
        self.assertEqual(valid["torch"]["version"], "2.13.0+cu130")
        MODULE.validate_runtime_observation(valid)

        distribution_uses_build = valid_runtime_observation()
        distribution_uses_build["packages"]["torch"] = "2.13.0+cu130"
        with self.assertRaisesRegex(RuntimeError, "package lock changed"):
            MODULE.validate_runtime_observation(distribution_uses_build)

        build_uses_distribution = valid_runtime_observation()
        build_uses_distribution["torch"]["version"] = "2.13.0"
        with self.assertRaisesRegex(RuntimeError, "Torch/CUDA identity changed"):
            MODULE.validate_runtime_observation(build_uses_distribution)

        substituted_build = valid_runtime_observation()
        substituted_build["torch"]["version"] = "2.13.0+cu129"
        with self.assertRaisesRegex(RuntimeError, "Torch/CUDA identity changed"):
            MODULE.validate_runtime_observation(substituted_build)

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

    def test_vendor_direct_load_skips_package_init_and_rejects_preloaded_substitution(self):
        fake = types.ModuleType("slicegpt.data_utils")
        sys.modules["slicegpt.data_utils"] = fake
        try:
            with self.assertRaisesRegex(RuntimeError, "preloaded slicegpt modules"):
                MODULE.load_verified_prepare_dataloader(Path.cwd(), "0" * 64)
        finally:
            sys.modules.pop("slicegpt.data_utils", None)

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            source = repo / MODULE.VENDOR_DATA_UTILS
            source.parent.mkdir(parents=True)
            init_marker = repo / "package-init-executed"
            (source.parent / "__init__.py").write_text(
                f"from pathlib import Path\nPath({str(init_marker)!r}).write_text('bad')\n",
                encoding="utf-8",
            )
            source.write_text(
                "def prepare_dataloader(*args, **kwargs):\n    return 'direct-source-marker'\n",
                encoding="utf-8",
            )
            expected_hash = MODULE.sha256_of_file(source)
            before_path = tuple(sys.path)
            prepare = MODULE.load_verified_prepare_dataloader(repo, expected_hash)
            self.assertEqual(prepare(), "direct-source-marker")
            self.assertFalse(init_marker.exists())
            self.assertEqual(tuple(sys.path), before_path)
            self.assertFalse(any(name.startswith("slicegpt") for name in sys.modules))

            sealed_name = f"_probe2_v4_slicegpt_data_utils_{expected_hash}"
            sys.modules[sealed_name] = types.ModuleType(sealed_name)
            try:
                with self.assertRaisesRegex(RuntimeError, "preloaded sealed vendor"):
                    MODULE.load_verified_prepare_dataloader(repo, expected_hash)
            finally:
                sys.modules.pop(sealed_name, None)

            with self.assertRaisesRegex(RuntimeError, "hash changed before execution"):
                MODULE.load_verified_prepare_dataloader(repo, "0" * 64)

            substituted = types.SimpleNamespace(
                loader=object(), name=sealed_name, origin=str(source)
            )
            with mock.patch.object(
                MODULE.importlib.util, "spec_from_file_location", return_value=substituted
            ):
                with self.assertRaisesRegex(RuntimeError, "specification was substituted"):
                    MODULE.load_verified_prepare_dataloader(repo, expected_hash)

    def test_vendor_direct_load_rechecks_source_after_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            source = repo / MODULE.VENDOR_DATA_UTILS
            source.parent.mkdir(parents=True)
            source.write_text(
                "from pathlib import Path\n"
                "Path(__file__).write_text('attacker replacement', encoding='utf-8')\n"
                "def prepare_dataloader(*args, **kwargs):\n    return None\n",
                encoding="utf-8",
            )
            expected_hash = MODULE.sha256_of_file(source)
            with self.assertRaisesRegex(RuntimeError, "not the recorded direct source"):
                MODULE.load_verified_prepare_dataloader(repo, expected_hash)

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
