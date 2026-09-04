import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

try:
    import apply_checkpoint_delta_dare as dare
except ModuleNotFoundError:
    from scripts import apply_checkpoint_delta_dare as dare

try:
    import numpy as np
    import torch
    from safetensors import safe_open
    from safetensors.torch import load_file, save_file
except ModuleNotFoundError:
    np = None
    torch = None
    safe_open = None
    load_file = None
    save_file = None


def inventory_record(character, *, shape=(2, 4), dtype="torch.bfloat16"):
    numel = 1
    for value in shape:
        numel *= value
    return {
        "shape": list(shape),
        "dtype": dtype,
        "numel": numel,
        "value_bytes": numel * (2 if dtype == "torch.bfloat16" else 4),
        "sha256": character * 64,
    }


def valid_inventory_pair():
    clean = {
        key: inventory_record("a") for key in dare.DECLARED_EDIT_KEYS
    }
    edited = {
        key: inventory_record("b") for key in dare.DECLARED_EDIT_KEYS
    }
    clean["language_model.model.embed_tokens.weight"] = inventory_record("c")
    edited["language_model.model.embed_tokens.weight"] = inventory_record("c")
    return clean, edited


class FrozenContractTests(unittest.TestCase):
    def test_declared_surface_is_exactly_98_bias_free_linears(self):
        keys = dare.DECLARED_EDIT_KEYS
        self.assertEqual(len(keys), 98)
        self.assertEqual(len(set(keys)), 98)
        self.assertTrue(all(key.endswith(".weight") for key in keys))
        self.assertFalse(any(key.endswith(".bias") for key in keys))
        expected_layers = set(range(12, 20)) | set(range(28, 34))
        actual_layers = {int(key.split(".")[3]) for key in keys}
        self.assertEqual(actual_layers, expected_layers)
        for layer in expected_layers:
            self.assertEqual(
                sum(f".layers.{layer}." in key for key in keys), 7
            )

    def test_pinned_source_contract_names_the_qualified_dense_donor(self):
        self.assertEqual(
            dare.PINNED_SOURCE_CONTRACT.edited_mapping(),
            {
                "model.safetensors": (
                    "b8527608bb60269959e6f7694c12627dd0194baff772e2b72b8c1240080e5690"
                )
            },
        )
        self.assertEqual(
            dare.PINNED_SOURCE_CONTRACT.clean_mapping(),
            dare.PINNED_CLEAN_WEIGHT_HASHES,
        )
        self.assertEqual(
            dare.PINNED_SOURCE_CONTRACT.edited_logical_inventory_sha256,
            "7eedf4b2d316a9518577917acd35bf2c04d77cafb095ff238c1452a24cfafbbf",
        )

    def test_logical_digest_matches_frozen_record_schema(self):
        inventory = {
            "z": inventory_record("b", shape=(2,)),
            "a": inventory_record("a", shape=(1, 2)),
        }
        result = dare.safetensors_logical_values_digest(inventory)
        records = [
            {
                "key": key,
                "dtype": inventory[key]["dtype"],
                "shape": inventory[key]["shape"],
                "value_bytes": inventory[key]["value_bytes"],
                "value_sha256": inventory[key]["sha256"],
            }
            for key in sorted(inventory)
        ]
        self.assertEqual(
            result["logical_inventory_sha256"],
            dare.payload_sha256(records),
        )
        changed = copy.deepcopy(inventory)
        changed["a"]["sha256"] = "c" * 64
        self.assertNotEqual(
            result["logical_inventory_sha256"],
            dare.safetensors_logical_values_digest(changed)[
                "logical_inventory_sha256"
            ],
        )

    def test_surface_proof_accepts_only_the_exact_declared_set(self):
        clean, edited = valid_inventory_pair()
        proof = dare.verify_declared_delta_surface(clean, edited)
        self.assertTrue(proof["exact"])
        self.assertTrue(proof["bias_free"])
        self.assertEqual(proof["declared_key_count"], 98)
        self.assertEqual(proof["actual_changed_key_count"], 98)

    def test_surface_proof_rejects_extra_and_missing_delta(self):
        clean, edited = valid_inventory_pair()
        edited["language_model.model.embed_tokens.weight"] = inventory_record("d")
        with self.assertRaisesRegex(ValueError, "not exactly the frozen 98"):
            dare.verify_declared_delta_surface(clean, edited)

        clean, edited = valid_inventory_pair()
        edited[dare.DECLARED_EDIT_KEYS[-1]] = copy.deepcopy(
            clean[dare.DECLARED_EDIT_KEYS[-1]]
        )
        with self.assertRaisesRegex(ValueError, "declared_without_delta"):
            dare.verify_declared_delta_surface(clean, edited)

    def test_surface_proof_rejects_key_shape_dtype_and_bias_mismatch(self):
        cases = []
        clean, edited = valid_inventory_pair()
        del edited[dare.DECLARED_EDIT_KEYS[0]]
        cases.append((clean, edited, "canonical tensor keys"))

        clean, edited = valid_inventory_pair()
        edited[dare.DECLARED_EDIT_KEYS[0]]["shape"] = [9, 9]
        cases.append((clean, edited, "shape differs"))

        clean, edited = valid_inventory_pair()
        edited[dare.DECLARED_EDIT_KEYS[0]]["dtype"] = "torch.float32"
        cases.append((clean, edited, "dtype differs"))

        clean, edited = valid_inventory_pair()
        bias = dare.DECLARED_EDIT_KEYS[0][: -len("weight")] + "bias"
        clean[bias] = inventory_record("c", shape=(2,))
        edited[bias] = inventory_record("c", shape=(2,))
        cases.append((clean, edited, "unexpectedly has a bias"))

        for clean_case, edited_case, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    dare.verify_declared_delta_surface(clean_case, edited_case)

    def test_output_locality_allows_declared_subset_but_nothing_else(self):
        clean, _ = valid_inventory_pair()
        output = copy.deepcopy(clean)
        output[dare.DECLARED_EDIT_KEYS[0]]["sha256"] = "d" * 64
        self.assertEqual(
            dare.verify_output_locality(clean, output),
            [dare.DECLARED_EDIT_KEYS[0]],
        )
        output["language_model.model.embed_tokens.weight"]["sha256"] = "e" * 64
        with self.assertRaisesRegex(RuntimeError, "escaped declared surface"):
            dare.verify_output_locality(clean, output)

    def test_tensor_application_records_bind_all_three_inventories(self):
        clean, edited = valid_inventory_pair()
        output = copy.deepcopy(edited)
        records = []
        for key in sorted(dare.DECLARED_EDIT_KEYS):
            records.append(
                {
                    "tensor_name": key,
                    "shape": clean[key]["shape"],
                    "dtype": clean[key]["dtype"],
                    "counts": {"elements": clean[key]["numel"]},
                    "clean_sha256": clean[key]["sha256"],
                    "edited_sha256": edited[key]["sha256"],
                    "output_sha256": output[key]["sha256"],
                }
            )
        self.assertEqual(
            len(
                dare.verify_tensor_application_records(
                    records, clean, edited, output
                )
            ),
            98,
        )
        records[0]["output_sha256"] = "f" * 64
        with self.assertRaisesRegex(RuntimeError, "output_sha256 is unbound"):
            dare.verify_tensor_application_records(records, clean, edited, output)

    def test_config_proof_accepts_materialized_defaults_but_rejects_shared_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            clean_root = root / "clean"
            edited_root = root / "edited"
            clean_root.mkdir()
            edited_root.mkdir()
            common = {
                "model_type": "gemma3",
                "architectures": ["Gemma3ForConditionalGeneration"],
            }
            clean_config = {
                **common,
                "text_config": {
                    "model_type": "gemma3_text",
                    "hidden_size": 2560,
                    "num_hidden_layers": 34,
                },
            }
            edited_config = {
                **common,
                "text_config": {
                    "model_type": "gemma3_text",
                    "hidden_size": 2560,
                    "num_hidden_layers": 34,
                    "num_attention_heads": 8,
                    "num_key_value_heads": 4,
                    "head_dim": 256,
                },
            }
            for directory, config in (
                (clean_root, clean_config),
                (edited_root, edited_config),
            ):
                (directory / "config.json").write_text(
                    json.dumps(config), encoding="utf-8"
                )
            contract = dare.SourceContract.from_mappings(
                {}, {}, "0" * 64, "0" * 64
            )
            proof = dare.verify_model_configs(clean_root, edited_root, contract)
            self.assertEqual(
                proof["shared_explicit_geometry_fields"],
                ["hidden_size", "num_hidden_layers"],
            )
            edited_config["text_config"]["hidden_size"] = 999
            (edited_root / "config.json").write_text(
                json.dumps(edited_config), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "shape fields differ"):
                dare.verify_model_configs(clean_root, edited_root, contract)


class ProbabilityAndRngTests(unittest.TestCase):
    def test_probability_parser_and_exact_uint64_thresholds(self):
        expected = {
            "0": 1 << 64,
            "0.5": 1 << 63,
            "0.9": (1 << 64) // 10,
            "0.99": (1 << 64) // 100,
        }
        for value, threshold in expected.items():
            with self.subTest(value=value):
                spec = dare.parse_drop_probability(value)
                self.assertEqual(spec.decimal, value)
                self.assertEqual(spec.uint64_keep_threshold, threshold)
        tiny = dare.parse_drop_probability("1e-100")
        self.assertEqual(tiny.uint64_keep_threshold, (1 << 64) - 1)

    def test_malformed_probabilities_and_seeds_fail(self):
        for value in (-0.1, 1, 1.01, "nan", "inf", True, "x", ""):
            with self.subTest(probability=value):
                with self.assertRaisesRegex(ValueError, "drop-probability"):
                    dare.parse_drop_probability(value)
        for value in (-1, 1 << 64, True, 1.5, "01", "x"):
            with self.subTest(seed=value):
                with self.assertRaisesRegex(ValueError, "seed"):
                    dare.parse_uint64_seed(value)

    def test_rng_known_answer_vectors_are_frozen(self):
        name = dare.DECLARED_EDIT_KEYS[0]
        indices = (0, 1, 2, 17, 999)
        self.assertEqual(
            [dare.random_u64(name, index, 33450) for index in indices],
            [
                0x4690D1910AA2038E,
                0x66C7E583FB9FBEF9,
                0x0F54C708275BB5D8,
                0xE22CB45A13C0368E,
                0x8793236170528589,
            ],
        )

    def test_scalar_rng_is_traversal_independent_and_p0_keeps_all(self):
        name = dare.DECLARED_EDIT_KEYS[7]
        forward = {
            index: dare.keep_element(name, index, 33451, "0.9")
            for index in range(100)
        }
        reverse = {
            index: dare.keep_element(name, index, 33451, "0.9")
            for index in reversed(range(100))
        }
        self.assertEqual(forward, reverse)
        self.assertTrue(
            all(dare.keep_element(name, index, 0, "0") for index in range(100))
        )

    def test_adjacent_seed_streams_are_not_shifted_copies(self):
        name = dare.DECLARED_EDIT_KEYS[0]
        first = [
            dare.random_u64(name, index + 1, 33450) for index in range(100)
        ]
        adjacent = [
            dare.random_u64(name, index, 33451) for index in range(100)
        ]
        self.assertNotEqual(first, adjacent)

    def test_cli_rejects_requests_outside_frozen_grid(self):
        base = [
            "--clean-model", "clean", "--edited-model", "edited",
            "--tokenizer-model", "clean", "--output", "output",
        ]
        valid = dare.parse_args(base + ["--drop-probability", "0", "--seed", "0"])
        self.assertEqual(valid.drop_probability.decimal, "0")
        valid = dare.parse_args(
            base
            + ["--drop-probability", "0.9", "--seed", "33451"]
        )
        self.assertEqual(valid.seed, 33451)
        for probability, seed in (("0", "33450"), ("0.7", "33450"), ("0.9", "1")):
            with self.subTest(probability=probability, seed=seed):
                with self.assertRaises(SystemExit):
                    dare.parse_args(
                        base
                        + ["--drop-probability", probability, "--seed", seed]
                    )

    def test_tensor_name_and_seed_domain_separate_streams(self):
        first = [
            dare.random_u64(dare.DECLARED_EDIT_KEYS[0], index, 33450)
            for index in range(20)
        ]
        second_name = [
            dare.random_u64(dare.DECLARED_EDIT_KEYS[1], index, 33450)
            for index in range(20)
        ]
        second_seed = [
            dare.random_u64(dare.DECLARED_EDIT_KEYS[0], index, 33451)
            for index in range(20)
        ]
        self.assertNotEqual(first, second_name)
        self.assertNotEqual(first, second_seed)


class ProvenanceAndPublicationTests(unittest.TestCase):
    def test_immutable_sidecar_round_trip_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sidecar.json"
            envelope = dare.immutable_envelope({"method": "test", "value": 3})
            dare.write_immutable_json(path, envelope)
            self.assertEqual(dare.load_immutable_json(path), envelope)
            tampered = json.loads(path.read_text(encoding="utf-8"))
            tampered["value"] = 4
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid payload hash"):
                dare.load_immutable_json(path)

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text(
                '{"payload_sha256":"' + "0" * 64 + '","x":1,"x":2}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "could not read immutable JSON"):
                dare.load_immutable_json(path)

    def test_no_replace_publication_preserves_existing_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / "stage"
            destination = root / "destination"
            stage.mkdir()
            destination.mkdir()
            (stage / "new.txt").write_text("new", encoding="utf-8")
            marker = destination / "owned.txt"
            marker.write_text("caller", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "refusing to replace"):
                dare._publish_directory_no_replace(stage, destination)
            self.assertEqual(marker.read_text(encoding="utf-8"), "caller")
            self.assertTrue(stage.is_dir())

    def test_manifest_copy_is_exact_and_exclusive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            output.mkdir()
            (source / "config.json").write_text('{"x":1}', encoding="utf-8")
            manifest = dare.selected_file_manifest(
                source, names={"config.json"}
            )
            dare._copy_manifest(source, manifest, output)
            self.assertEqual(
                (output / "config.json").read_bytes(),
                (source / "config.json").read_bytes(),
            )
            with self.assertRaisesRegex(FileExistsError, "staged artifact"):
                dare._copy_manifest(source, manifest, output)


@unittest.skipIf(torch is None, "PyTorch/Safetensors/Numpy are unavailable")
class RealTensorAndEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.clean = self.root / "clean"
        self.edited = self.root / "edited"
        self.clean.mkdir()
        self.edited.mkdir()
        self.runtime = dare.Runtime(
            torch=torch,
            safe_open=safe_open,
            save_file=save_file,
            versions={
                "python": "test",
                "torch": torch.__version__,
                "safetensors": "test",
                "numpy": np.__version__,
            },
        )
        clean_tensors = {}
        edited_tensors = {}
        for index, key in enumerate(dare.DECLARED_EDIT_KEYS):
            base = torch.tensor(
                [[0, 1, 2, 3], [4, 5, 6, 7]], dtype=torch.bfloat16
            )
            clean_tensors[key] = base
            edited_tensors[key] = base + torch.tensor(
                (index % 5) + 1, dtype=torch.bfloat16
            )
        control_key = "language_model.model.embed_tokens.weight"
        clean_tensors[control_key] = torch.tensor(
            [[9, 10], [11, 12]], dtype=torch.bfloat16
        )
        edited_tensors[control_key] = clean_tensors[control_key].clone()
        clean_keys = sorted(clean_tensors)
        midpoint = len(clean_keys) // 2
        shard_names = (
            "model-00001-of-00002.safetensors",
            "model-00002-of-00002.safetensors",
        )
        weight_map = {}
        for shard_name, keys in zip(
            shard_names, (clean_keys[:midpoint], clean_keys[midpoint:])
        ):
            save_file(
                {key: clean_tensors[key] for key in keys},
                str(self.clean / shard_name),
            )
            weight_map.update({key: shard_name for key in keys})
        (self.clean / "model.safetensors.index.json").write_text(
            json.dumps({"metadata": {}, "weight_map": weight_map}, sort_keys=True),
            encoding="utf-8",
        )
        save_file(edited_tensors, str(self.edited / "model.safetensors"))
        config = {
            "model_type": "gemma3",
            "architectures": ["Gemma3ForConditionalGeneration"],
            "text_config": {
                "model_type": "gemma3_text",
                "hidden_size": 4,
                "intermediate_size": 8,
                "num_hidden_layers": 34,
                "num_attention_heads": 2,
                "num_key_value_heads": 1,
                "head_dim": 2,
                "vocab_size": 8,
            },
        }
        for directory in (self.clean, self.edited):
            (directory / "config.json").write_text(
                json.dumps(config, sort_keys=True), encoding="utf-8"
            )
        (self.edited / "generation_config.json").write_text(
            "{}", encoding="utf-8"
        )
        (self.clean / "tokenizer.json").write_text("{}", encoding="utf-8")
        (self.clean / "tokenizer_config.json").write_text(
            "{}", encoding="utf-8"
        )
        edited_snapshot = dare.scan_checkpoint(
            self.edited, label="test-edited", runtime=self.runtime
        )
        self.contract = dare.SourceContract.from_mappings(
            {
                name: dare.sha256_file(self.clean / name)
                for name in shard_names
            },
            {
                "model.safetensors": dare.sha256_file(
                    self.edited / "model.safetensors"
                )
            },
            dare.sha256_file(self.edited / "config.json"),
            edited_snapshot.logical_inventory_sha256,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def _clean_state(self):
        index = json.loads(
            (self.clean / "model.safetensors.index.json").read_text(
                encoding="utf-8"
            )
        )
        state = {}
        for filename in sorted(set(index["weight_map"].values())):
            state.update(load_file(str(self.clean / filename)))
        return state

    def _clean_weight_hashes(self):
        index = json.loads(
            (self.clean / "model.safetensors.index.json").read_text(
                encoding="utf-8"
            )
        )
        return {
            filename: dare.sha256_file(self.clean / filename)
            for filename in sorted(set(index["weight_map"].values()))
        }

    @staticmethod
    def _reload_verifier(path):
        config = json.loads((path / "config.json").read_text(encoding="utf-8"))
        if not (path / "tokenizer.json").is_file():
            raise AssertionError("tokenizer was not published")
        return {
            "config_class": "FakeGemma3Config",
            "model_type": config["model_type"],
            "tokenizer_class": "FakeTokenizer",
            "vocab_size": 8,
            "chat_template_sha256": dare.payload_sha256("{{ messages }}"),
            "local_files_only": True,
            "trust_remote_code": False,
        }

    def _apply(self, output_name, probability, seed=0, **kwargs):
        return dare.apply_checkpoint_delta_dare(
            clean_model=self.clean,
            edited_model=self.edited,
            tokenizer_model=kwargs.pop("tokenizer_model", self.clean),
            output_dir=self.root / output_name,
            drop_probability=probability,
            seed=seed,
            chunk_elements=kwargs.pop("chunk_elements", 3),
            compute_device=kwargs.pop("compute_device", "cpu"),
            runtime=self.runtime,
            source_contract=kwargs.pop("source_contract", self.contract),
            strict_git=False,
            reload_verifier=self._reload_verifier,
            **kwargs,
        )

    def test_vector_mask_matches_scalar_and_is_chunk_device_independent(self):
        name = dare.DECLARED_EDIT_KEYS[0]
        spec = dare.parse_drop_probability("0.9")
        whole = dare.deterministic_keep_mask(
            name,
            start=0,
            count=257,
            seed=33450,
            drop_probability=spec,
            torch=torch,
            device=torch.device("cpu"),
        )
        chunks = torch.cat(
            [
                dare.deterministic_keep_mask(
                    name,
                    start=start,
                    count=min(31, 257 - start),
                    seed=33450,
                    drop_probability=spec,
                    torch=torch,
                    device=torch.device("cpu"),
                )
                for start in range(0, 257, 31)
            ]
        )
        scalar = torch.tensor(
            [dare.keep_element(name, index, 33450, spec) for index in range(257)]
        )
        self.assertTrue(torch.equal(whole, chunks))
        self.assertTrue(torch.equal(whole, scalar))
        if torch.cuda.is_available():
            cuda_mask = dare.deterministic_keep_mask(
                name,
                start=0,
                count=257,
                seed=33450,
                drop_probability=spec,
                torch=torch,
                device=torch.device("cuda:0"),
            )
            self.assertTrue(torch.equal(whole, cuda_mask.cpu()))

    def test_exact_float32_scaling_and_locality(self):
        name = dare.DECLARED_EDIT_KEYS[0]
        clean = torch.tensor(
            [[1, 2, 3, 4], [5, 6, 7, 8]], dtype=torch.bfloat16
        )
        edited = clean + torch.tensor(2, dtype=torch.bfloat16)
        output, record = dare.transform_tensor(
            clean,
            edited,
            tensor_name=name,
            seed=33450,
            drop_probability="0.5",
            chunk_elements=3,
            compute_device="cpu",
            torch=torch,
        )
        mask = dare.deterministic_keep_mask(
            name,
            start=0,
            count=clean.numel(),
            seed=33450,
            drop_probability="0.5",
            torch=torch,
            device=torch.device("cpu"),
        ).view(clean.shape)
        expected = (
            clean.float()
            + torch.where(
                mask,
                (edited.float() - clean.float())
                / torch.tensor(0.5, dtype=torch.float32),
                torch.zeros_like(clean.float()),
            )
        ).to(dtype=torch.bfloat16)
        self.assertTrue(torch.equal(output, expected))
        self.assertEqual(record["counts"]["elements"], clean.numel())
        self.assertEqual(
            record["counts"]["mask_kept"] + record["counts"]["mask_dropped"],
            clean.numel(),
        )

    def test_p0_preserves_tiny_donor_values_despite_fp32_cancellation(self):
        clean = torch.tensor([[0.125, -0.125, 0.25]], dtype=torch.bfloat16)
        edited = torch.tensor([[2.0**-40, -(2.0**-40), -0.0]], dtype=torch.bfloat16)
        reconstructed = (clean.float() + (edited.float() - clean.float())).to(clean.dtype)
        self.assertFalse(torch.equal(reconstructed, edited))
        devices = ["cpu"] + (["cuda:0"] if torch.cuda.is_available() else [])
        for device in devices:
            with self.subTest(device=device):
                output, record = dare.transform_tensor(
                    clean, edited, tensor_name=dare.DECLARED_EDIT_KEYS[0], seed=0,
                    drop_probability="0", chunk_elements=2,
                    compute_device=device, torch=torch,
                )
                self.assertEqual(dare._tensor_sha256(output, torch),
                                 dare._tensor_sha256(edited, torch))
                self.assertEqual(record["counts"]["serialized_equal_edited"], 3)
                self.assertEqual(record["output_arithmetic"], "exact_native_edited_copy")
                dare.source_delta_stats(clean, edited, tensor_name=dare.DECLARED_EDIT_KEYS[0],
                    chunk_elements=2, compute_device=device, torch=torch)

    def test_p0_is_dense_weight_file_and_tensor_identity_with_sidecar(self):
        provenance = self._apply("p0", "0", seed=0)
        output = self.root / "p0"
        self.assertEqual(
            (output / "model.safetensors").read_bytes(),
            (self.edited / "model.safetensors").read_bytes(),
        )
        self.assertTrue(provenance["output"]["p0_edited_weight_file_identity"])
        self.assertTrue(provenance["output"]["p0_edited_tensor_state_identity"])
        self.assertEqual(
            dare.load_immutable_json(output / dare.SIDECAR_NAME), provenance
        )
        self.assertEqual(len(provenance["tensors"]), 98)
        self.assertTrue(
            all(
                record["p0_edited_tensor_identity"]
                for record in provenance["tensors"]
            )
        )

    def test_nonzero_run_is_deterministic_and_preserves_nonsurface_tensor(self):
        first = self._apply("half-a", "0.5", seed=33450)
        second = self._apply("half-b", "0.5", seed=33450, chunk_elements=17)
        self.assertEqual(
            first["output"]["tensor_inventory"],
            second["output"]["tensor_inventory"],
        )
        first_state = load_file(str(self.root / "half-a" / "model.safetensors"))
        clean_state = self._clean_state()
        control = "language_model.model.embed_tokens.weight"
        self.assertTrue(torch.equal(first_state[control], clean_state[control]))
        self.assertFalse(first["output"]["p0_edited_tensor_state_identity"])

    def test_existing_output_fails_before_touching_caller_data(self):
        output = self.root / "collision"
        output.mkdir()
        marker = output / "owned.txt"
        marker.write_text("caller", encoding="utf-8")
        with self.assertRaisesRegex(FileExistsError, "refusing to replace"):
            self._apply("collision", "0.5", seed=33450)
        self.assertEqual(marker.read_text(encoding="utf-8"), "caller")

    def test_source_pin_mismatch_fails_closed(self):
        wrong = dare.SourceContract.from_mappings(
            {"model.safetensors": "0" * 64},
            self.contract.edited_mapping(),
            self.contract.edited_config_sha256,
            self.contract.edited_logical_inventory_sha256,
        )
        with self.assertRaisesRegex(ValueError, "clean checkpoint weight-file hashes"):
            self._apply("bad-pin", "0", source_contract=wrong)
        self.assertFalse((self.root / "bad-pin").exists())

    def test_qualified_donor_logical_digest_mismatch_fails_closed(self):
        wrong = dare.SourceContract.from_mappings(
            self.contract.clean_mapping(),
            self.contract.edited_mapping(),
            self.contract.edited_config_sha256,
            "0" * 64,
        )
        with self.assertRaisesRegex(ValueError, "logical Safetensors digest"):
            self._apply("bad-logical-digest", "0", source_contract=wrong)
        self.assertFalse((self.root / "bad-logical-digest").exists())

    def test_tokenizer_must_be_the_exact_clean_snapshot(self):
        other = self.root / "other-tokenizer"
        other.mkdir()
        (other / "tokenizer.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exact clean-model directory"):
            self._apply(
                "wrong-tokenizer",
                "0",
                tokenizer_model=other,
            )
        self.assertFalse((self.root / "wrong-tokenizer").exists())

    def test_extra_delta_and_nonfinite_source_fail_before_publication(self):
        state = load_file(str(self.edited / "model.safetensors"))
        control = "language_model.model.embed_tokens.weight"
        state[control] = state[control] + torch.tensor(1, dtype=torch.bfloat16)
        save_file(state, str(self.edited / "model.safetensors"))
        extra_snapshot = dare.scan_checkpoint(
            self.edited, label="test-extra-edited", runtime=self.runtime
        )
        extra_contract = dare.SourceContract.from_mappings(
            self.contract.clean_mapping(),
            {
                "model.safetensors": dare.sha256_file(
                    self.edited / "model.safetensors"
                )
            },
            self.contract.edited_config_sha256,
            extra_snapshot.logical_inventory_sha256,
        )
        with self.assertRaisesRegex(ValueError, "not exactly the frozen 98"):
            self._apply("extra-delta", "0.5", source_contract=extra_contract)
        self.assertFalse((self.root / "extra-delta").exists())

        # Restore then introduce a malformed nonfinite value on the clean side.
        self.tearDown()
        self.setUp()
        index = json.loads(
            (self.clean / "model.safetensors.index.json").read_text(
                encoding="utf-8"
            )
        )
        malformed_key = dare.DECLARED_EDIT_KEYS[0]
        malformed_shard = index["weight_map"][malformed_key]
        state = load_file(str(self.clean / malformed_shard))
        state[malformed_key][0, 0] = float("nan")
        save_file(state, str(self.clean / malformed_shard))
        nonfinite_contract = dare.SourceContract.from_mappings(
            self._clean_weight_hashes(),
            self.contract.edited_mapping(),
            self.contract.edited_config_sha256,
            self.contract.edited_logical_inventory_sha256,
        )
        with self.assertRaisesRegex(ValueError, "nonfinite values"):
            self._apply("nonfinite", "0.5", source_contract=nonfinite_contract)
        self.assertFalse((self.root / "nonfinite").exists())


if __name__ == "__main__":
    unittest.main()
