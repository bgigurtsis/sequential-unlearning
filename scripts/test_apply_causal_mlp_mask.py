import copy
import json
import os
import stat
import struct
import tempfile
import unittest
from unittest import mock
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

try:
    import apply_causal_mlp_mask as applier
except ModuleNotFoundError:
    from scripts import apply_causal_mlp_mask as applier

try:
    import torch as real_torch
except ModuleNotFoundError:
    real_torch = None


class FakeDType:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name


BF16 = FakeDType("torch.bfloat16")
FP32 = FakeDType("torch.float32")
UINT8 = FakeDType("torch.uint8")


def _encoded(values, dtype):
    if str(dtype) == "torch.bfloat16":
        result = bytearray()
        for value in values:
            bits = struct.unpack("<I", struct.pack("<f", float(value)))[0]
            result.extend(struct.pack("<H", bits >> 16))
        return bytes(result)
    return b"".join(struct.pack("<f", float(value)) for value in values)


class FakeBytes:
    def __init__(self, value):
        self.value = value

    def cpu(self):
        return self

    def numpy(self):
        return self

    def tobytes(self):
        return self.value


class FakeVector:
    def __init__(self, values, dtype=BF16, *, parent=None, column=None):
        self.values = list(values)
        self.dtype = dtype
        self.parent = parent
        self.column = column

    @property
    def shape(self):
        return (len(self.values),)

    def detach(self):
        return self

    def contiguous(self):
        return FakeVector(self.values, self.dtype)

    def view(self, dtype):
        if dtype is not UINT8:
            raise AssertionError("the test double only supports byte views")
        return FakeBytes(_encoded(self.values, self.dtype))

    def cpu(self):
        return self

    def numpy(self):
        return self

    def tobytes(self):
        return _encoded(self.values, self.dtype)

    def float(self):
        return FakeVector(self.values, FP32)

    def __mul__(self, scale):
        return FakeVector([value * scale for value in self.values], self.dtype)

    def to(self, *, dtype):
        return FakeVector(self.values, dtype)

    def copy_(self, other):
        values = list(other.values)
        if self.parent is None:
            self.values[:] = values
        else:
            for row, value in enumerate(values):
                self.parent.values[row][self.column] = value
            self.values = values
        return self


class FakeMatrix:
    def __init__(self, values, dtype=BF16):
        self.values = [list(row) for row in values]
        self.dtype = dtype

    @property
    def shape(self):
        return (len(self.values), len(self.values[0]))

    def detach(self):
        return self

    def contiguous(self):
        return self

    def clone(self):
        return FakeMatrix(self.values, self.dtype)

    def view(self, dtype):
        if dtype is not UINT8:
            raise AssertionError("the test double only supports byte views")
        flat = [value for row in self.values for value in row]
        return FakeBytes(_encoded(flat, self.dtype))

    def cpu(self):
        return self

    def numpy(self):
        return self

    def tobytes(self):
        return _encoded([value for row in self.values for value in row], self.dtype)

    def __getitem__(self, key):
        rows, column = key
        if rows != slice(None):
            raise AssertionError("the test double only supports full columns")
        return FakeVector(
            [row[column] for row in self.values],
            self.dtype,
            parent=self,
            column=column,
        )


class FakeTorch:
    uint8 = UINT8
    float32 = FP32
    bfloat16 = BF16

    @staticmethod
    def no_grad():
        return nullcontext()


class FakeModel:
    def __init__(self):
        self.weights = [
            FakeMatrix([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
            FakeMatrix([[7.0, 8.0, 9.0], [10.0, 11.0, 12.0]]),
        ]
        layers = [
            SimpleNamespace(mlp=SimpleNamespace(down_proj=SimpleNamespace(weight=weight)))
            for weight in self.weights
        ]
        self.model = SimpleNamespace(
            language_model=SimpleNamespace(layers=layers)
        )

    def named_parameters(self):
        for index, weight in enumerate(self.weights):
            yield (
                f"model.language_model.layers.{index}.mlp.down_proj.weight",
                weight,
            )

    def state_dict(self):
        return dict(self.named_parameters())

    def eval(self):
        return self

    def requires_grad_(self, value):
        return self

    def save_pretrained(self, destination, *, safe_serialization):
        destination = Path(destination)
        (destination / "config.json").write_text(
            json.dumps({"model_type": "fake"}), encoding="utf-8"
        )
        payload = b"".join(
            _encoded([value for row in weight.values for value in row], weight.dtype)
            for weight in self.weights
        )
        (destination / "model.safetensors").write_bytes(payload)


class FakeTokenizer:
    bos_token_id = 1
    eos_token_id = 2
    pad_token_id = 2
    chat_template = "{{ messages }}"
    padding_side = "left"

    def save_pretrained(self, destination):
        destination = Path(destination)
        (destination / "tokenizer.json").write_text(
            json.dumps({"fake": True}), encoding="utf-8"
        )


class MaskApplierTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "config.json").write_text(
            json.dumps({"model_type": "fake"}), encoding="utf-8"
        )
        (self.source / "model.safetensors").write_bytes(b"original-weight-file")
        (self.source / "tokenizer.json").write_text(
            json.dumps({"fake": True}), encoding="utf-8"
        )
        self.raw = self.root / "raw.safetensors"
        self.raw.write_bytes(b"replayable-attribution")
        self.model = FakeModel()
        self.replay_calls = []
        self.saved_verification_roots = []
        self.saved_namespace_contracts = []
        self.rows = [self._bound_row(0, 0, 1), self._bound_row(0, 1, 2)]
        self.mask = self._write_mask(self.rows)

    def tearDown(self):
        self.temporary.cleanup()

    def _bound_row(self, layer, neuron, rank):
        name = f"model.language_model.layers.{layer}.mlp.down_proj.weight"
        column = self.model.weights[layer][:, neuron]
        return {
            "layer": layer,
            "neuron": neuron,
            "global_rank": rank,
            "parameter_name": name,
            "resolved_parameter_surface": (
                f"model.language_model.layers.{layer}.mlp.down_proj.weight"
            ),
            "source_column_shape": list(column.shape),
            "source_column_dtype": str(column.dtype),
            "source_column_sha256": applier.tensor_sha256(column, FakeTorch),
        }

    def _write_mask(self, rows, name="mask.json"):
        model_manifest = applier.attribution.require_local_artifact_manifest(
            str(self.source), label="model"
        )
        tokenizer_manifest = applier.attribution.require_local_artifact_manifest(
            str(self.source), label="tokenizer", tokenizer_only=True
        )
        payload = {
            "schema_version": applier.attribution.selection.SCHEMA_VERSION,
            "method": applier.attribution.METHOD,
            "source_model": model_manifest,
            "tokenizer": {
                **tokenizer_manifest,
                "runtime": {
                    "class": "FakeTokenizer",
                    "bos_token_id": 1,
                    "eos_token_id": 2,
                    "pad_token_id": 2,
                    "chat_template_sha256": (
                        applier.attribution.selection.payload_sha256(
                            FakeTokenizer.chat_template
                        )
                    ),
                },
            },
            "model_surface": {
                "decoder_path": "model.language_model.layers",
                "selected_layers": sorted({row["layer"] for row in rows}),
            },
            "attribution": {
                "raw_archive": {
                    "sha256": applier.attribution.selection.sha256_file(self.raw)
                }
            },
            "selection_diagnostics": {"selected": len(rows)},
            "selected_neurons": copy.deepcopy(rows),
            "selected_mask_sha256": applier.attribution.selection.payload_sha256(
                [
                    {
                        "layer": row["layer"],
                        "neuron": row["neuron"],
                        "parameter_name": row["parameter_name"],
                        "source_column_sha256": row["source_column_sha256"],
                    }
                    for row in rows
                ]
            ),
        }
        path = self.root / name
        applier.attribution.selection.write_immutable_json(
            path, applier.attribution.selection.immutable_envelope(payload)
        )
        return path

    def _runtime(self):
        return applier.Runtime(
            torch=FakeTorch,
            safe_open=object(),
            load_model=lambda source: self.model,
            load_tokenizer=lambda source: FakeTokenizer(),
            versions={"python": "test", "torch": "fake"},
        )

    def _apply(
        self,
        *,
        output="output",
        top_k=1,
        scale=0.0,
        runtime=None,
        mask=None,
        replay_error=None,
        source_tensor_error=None,
        output_mapping_mismatch=False,
    ):
        def replay(envelope, raw_path, *, torch, safe_open):
            self.replay_calls.append(Path(raw_path))
            if replay_error is not None:
                raise replay_error
            return (
                [
                    {"layer": row["layer"], "neuron": row["neuron"]}
                    for row in envelope["selected_neurons"]
                ],
                envelope["selection_diagnostics"],
            )

        def verify_saved(
            root,
            expected,
            aliases,
            namespace_contract,
            *,
            safe_open,
            torch,
        ):
            root = Path(root)
            self.saved_verification_roots.append(root)
            self.saved_namespace_contracts.append(copy.deepcopy(namespace_contract))
            if source_tensor_error is not None and root.resolve() == self.source.resolve():
                raise source_tensor_error
            self.assertTrue((Path(root) / "model.safetensors").is_file())
            contract_sha256 = applier.attribution.selection.payload_sha256(
                namespace_contract
            )
            mapping_sha256 = applier.attribution.selection.payload_sha256(
                [
                    {
                        "serialized_name": (
                            "different" if output_mapping_mismatch
                            and root.resolve() != self.source.resolve()
                            else "fake"
                        ),
                        "state_name": "fake",
                        "rule_id": "exact",
                    }
                ]
            )
            return {
                "tensor_count": len(expected),
                "mapped_state_tensor_count": len(expected),
                "expected_state_tensor_count": len(expected),
                "inventory_sha256": applier.attribution.selection.payload_sha256(
                    expected
                ),
                "mapped_inventory_sha256": applier.attribution.selection.payload_sha256(
                    expected
                ),
                "omitted_tied_aliases": [],
                "namespace_mapping": {
                    "contract": copy.deepcopy(namespace_contract),
                    "contract_sha256": contract_sha256,
                    "mapping_sha256": mapping_sha256,
                    "mapping_pair_count": 1,
                    "rule_match_counts": {
                        rule["id"]: (1 if index == 0 else 0)
                        for index, rule in enumerate(namespace_contract["rules"])
                    },
                    "complete": True,
                    "injective": True,
                    "bijective_modulo_declared_ties": True,
                },
            }

        with (
            mock.patch.object(
                applier.attribution,
                "verify_raw_attribution_replay",
                side_effect=replay,
            ),
            mock.patch.object(
                applier,
                "verify_saved_model_tensors",
                side_effect=verify_saved,
            ),
        ):
            return applier.apply_causal_mlp_mask(
                model_source=str(self.source),
                tokenizer_source=str(self.source),
                mask_json=mask or self.mask,
                raw_attribution=self.raw,
                output_dir=self.root / output,
                top_k=top_k,
                column_scale=scale,
                runtime=runtime or self._runtime(),
            )

    def test_identity_is_tensor_and_weight_file_byte_identical(self):
        original_tensors = copy.deepcopy([weight.values for weight in self.model.weights])
        original_weight_file = (self.source / "model.safetensors").read_bytes()
        (self.source / "processor_config.json").write_text(
            json.dumps({"not_mask_bound": True}), encoding="utf-8"
        )
        (self.source / "custom_runtime.py").write_text(
            "UNBOUND = True\n", encoding="utf-8"
        )
        provenance = self._apply(scale=1.0)
        output = self.root / "output"
        self.assertEqual(
            (output / "model.safetensors").read_bytes(), original_weight_file
        )
        self.assertEqual(
            [weight.values for weight in self.model.weights], original_tensors
        )
        self.assertTrue(provenance["model_tensors"]["byte_identical"])
        self.assertEqual(
            provenance["model_tensors"]["before"]["inventory_sha256"],
            provenance["model_tensors"]["after"]["inventory_sha256"],
        )
        self.assertFalse(provenance["applied_columns"][0]["bytes_changed"])
        self.assertFalse((output / "processor_config.json").exists())
        self.assertFalse((output / "custom_runtime.py").exists())
        self.assertEqual(
            provenance["output"]["serialization_contract"], "Safetensors_only"
        )
        sidecar = applier.load_immutable_mask(output / applier.SIDECAR_NAME)
        self.assertEqual(sidecar, provenance)

    def test_only_requested_top_k_prefix_column_is_scaled(self):
        before = copy.deepcopy(self.model.weights[0].values)
        # Unbound conditional/processor support is intentionally not copied;
        # this artifact contract is standalone for text model + tokenizer.
        (self.source / "processor_config.json").write_text(
            json.dumps({"unbound": True}), encoding="utf-8"
        )
        provenance = self._apply(top_k=1, scale=0.0)
        after = self.model.weights[0].values
        self.assertEqual([row[0] for row in after], [0.0, 0.0])
        self.assertEqual([row[1:] for row in after], [row[1:] for row in before])
        self.assertEqual(len(provenance["applied_columns"]), 1)
        self.assertEqual(provenance["applied_columns"][0]["neuron"], 0)
        self.assertEqual(
            provenance["model_tensors"]["changed_state_keys"],
            ["model.language_model.layers.0.mlp.down_proj.weight"],
        )
        self.assertFalse((self.root / "output" / "processor_config.json").exists())
        self.assertIn(
            "AutoTokenizer_only",
            provenance["output"]["compatibility_scope"],
        )

    def test_wrong_source_manifest_and_wrong_column_hash_fail_closed(self):
        (self.source / "model.safetensors").write_bytes(b"tampered-source")
        with self.assertRaisesRegex(ValueError, "source model files"):
            self._apply(output="bad-source")
        self.assertFalse((self.root / "bad-source").exists())

        (self.source / "model.safetensors").write_bytes(b"original-weight-file")
        bad_rows = copy.deepcopy(self.rows)
        bad_rows[0]["source_column_sha256"] = "0" * 64
        bad_mask = self._write_mask(bad_rows, "bad-column.json")
        with self.assertRaisesRegex(ValueError, "source column SHA-256"):
            self._apply(output="bad-column", mask=bad_mask)
        self.assertFalse((self.root / "bad-column").exists())

    def test_bad_raw_replay_fails_before_model_mutation_or_output(self):
        before = copy.deepcopy([weight.values for weight in self.model.weights])
        with self.assertRaisesRegex(ValueError, "bad raw replay"):
            self._apply(
                output="bad-replay", replay_error=ValueError("bad raw replay")
            )
        self.assertEqual([weight.values for weight in self.model.weights], before)
        self.assertFalse((self.root / "bad-replay").exists())
        self.assertEqual(self.replay_calls, [self.raw])

    def test_complete_serialized_source_is_verified_before_mutation(self):
        before = copy.deepcopy([weight.values for weight in self.model.weights])
        with self.assertRaisesRegex(ValueError, "source tensor mismatch"):
            self._apply(
                output="bad-full-source",
                source_tensor_error=ValueError("source tensor mismatch"),
            )
        self.assertEqual([weight.values for weight in self.model.weights], before)
        self.assertEqual(self.saved_verification_roots, [self.source])
        self.assertFalse((self.root / "bad-full-source").exists())

    def test_source_and_output_must_use_identical_namespace_pair_map(self):
        with self.assertRaisesRegex(RuntimeError, "namespace mappings differ"):
            self._apply(
                output="mapping-mismatch",
                scale=1.0,
                output_mapping_mismatch=True,
            )
        self.assertFalse((self.root / "mapping-mismatch").exists())

    def test_gemma_namespace_contract_is_used_for_source_and_output(self):
        gemma_type = type("Gemma3ForConditionalGeneration", (FakeModel,), {})
        self.model = gemma_type()
        self.model.config = SimpleNamespace(model_type="gemma3")
        self.rows = [self._bound_row(0, 0, 1), self._bound_row(0, 1, 2)]
        gemma_mask = self._write_mask(self.rows, "gemma-mask.json")
        provenance = self._apply(
            output="gemma-contract",
            scale=1.0,
            mask=gemma_mask,
        )
        self.assertEqual(len(self.saved_namespace_contracts), 2)
        self.assertEqual(
            [contract["name"] for contract in self.saved_namespace_contracts],
            [
                "gemma3_conditional_hf_serialized_to_state_v1",
                "gemma3_conditional_hf_serialized_to_state_v1",
            ],
        )
        mapping_record = provenance["model_tensors"]["namespace_mapping_contract"]
        self.assertTrue(mapping_record["source_output_mapping"]["identical"])
        self.assertEqual(
            mapping_record["contract_sha256"],
            applier.attribution.selection.payload_sha256(
                applier.gemma3_namespace_mapping_contract()
            ),
        )

    def test_runtime_cannot_inject_a_replacement_replay_verifier(self):
        runtime = self._runtime()
        injected_calls = []
        object.__setattr__(
            runtime,
            "replay_verifier",
            lambda *args, **kwargs: injected_calls.append(True),
        )
        self._apply(output="direct-replay", scale=1.0, runtime=runtime)
        self.assertEqual(injected_calls, [])
        self.assertEqual(self.replay_calls, [self.raw])

    def test_duplicate_bound_columns_are_rejected(self):
        rows = [copy.deepcopy(self.rows[0]), copy.deepcopy(self.rows[0])]
        rows[1]["global_rank"] = 2
        duplicate_mask = self._write_mask(rows, "duplicates.json")
        with self.assertRaisesRegex(ValueError, "duplicate selected down_proj column"):
            self._apply(output="duplicates", top_k=1, mask=duplicate_mask)
        self.assertFalse((self.root / "duplicates").exists())

    def test_existing_output_is_never_touched(self):
        output = self.root / "collision"
        output.mkdir()
        marker = output / "keep.txt"
        marker.write_text("owned by caller", encoding="utf-8")
        with self.assertRaisesRegex(FileExistsError, "refusing to replace"):
            self._apply(output="collision")
        self.assertEqual(marker.read_text(encoding="utf-8"), "owned by caller")
        self.assertEqual(self.replay_calls, [])

    def test_platform_without_atomic_noreplace_publish_fails_closed(self):
        stage = self.root / "prepared-stage"
        destination = self.root / "never-published"
        stage.mkdir()
        (stage / "complete.txt").write_text("complete", encoding="utf-8")
        with (
            mock.patch.object(applier.os, "name", "posix"),
            mock.patch.object(applier.sys, "platform", "darwin"),
        ):
            with self.assertRaisesRegex(RuntimeError, "atomic no-replace"):
                applier._publish_directory_no_replace(stage, destination)
        self.assertTrue(stage.is_dir())
        self.assertFalse(destination.exists())

    def test_fsync_accepts_read_only_identity_copy(self):
        stage = self.root / "readonly-stage"
        stage.mkdir()
        artifact = stage / "model.safetensors"
        artifact.write_bytes(b"immutable")
        original_mode = stat.S_IMODE(artifact.stat().st_mode)
        os.chmod(artifact, stat.S_IREAD)
        try:
            applier._fsync_files(stage)
            self.assertEqual(artifact.read_bytes(), b"immutable")
        finally:
            os.chmod(artifact, original_mode | stat.S_IWRITE)

    def test_scale_and_top_k_validation(self):
        for invalid in (-0.01, 1.01, float("nan"), float("inf"), True):
            with self.subTest(column_scale=invalid):
                with self.assertRaisesRegex(ValueError, "column-scale"):
                    self._apply(output=f"invalid-{str(invalid)}", scale=invalid)
        for invalid in (0, -1, True, 1.5):
            with self.subTest(top_k=invalid):
                with self.assertRaisesRegex(ValueError, "top-k"):
                    self._apply(output=f"invalid-k-{str(invalid)}", top_k=invalid)
        with self.assertRaisesRegex(ValueError, "exceeds the 2 replayed mask rows"):
            self._apply(output="too-many", top_k=3)
        self.assertFalse((self.root / "too-many").exists())

    def test_tokenizer_manifest_is_exact(self):
        (self.source / "tokenizer.json").write_text(
            json.dumps({"fake": False}), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "tokenizer files"):
            self._apply(output="bad-tokenizer")
        self.assertFalse((self.root / "bad-tokenizer").exists())

    def test_tokenizer_runtime_binding_is_exact(self):
        envelope = json.loads(self.mask.read_text(encoding="utf-8"))
        envelope.pop("payload_sha256")
        envelope["tokenizer"]["runtime"]["class"] = "WrongTokenizer"
        bad_mask = self.root / "bad-tokenizer-runtime.json"
        applier.attribution.selection.write_immutable_json(
            bad_mask,
            applier.attribution.selection.immutable_envelope(envelope),
        )
        with self.assertRaisesRegex(ValueError, "tokenizer runtime"):
            self._apply(output="bad-tokenizer-runtime", mask=bad_mask)
        self.assertFalse((self.root / "bad-tokenizer-runtime").exists())

    def test_production_loader_dispatches_gemma3_to_conditional_wrapper(self):
        calls = []

        class ConfigLoader:
            model_type = "gemma3"

            @classmethod
            def from_pretrained(cls, source, **kwargs):
                calls.append(("config", source, kwargs))
                return SimpleNamespace(model_type=cls.model_type)

        class AutoLoader:
            @classmethod
            def from_pretrained(cls, source, **kwargs):
                calls.append(("auto", source, kwargs))
                return "auto"

        class ConditionalLoader:
            @classmethod
            def from_pretrained(cls, source, **kwargs):
                calls.append(("conditional", source, kwargs))
                return "conditional"

        result = applier._load_production_model(
            "local-model",
            FakeTorch,
            ConfigLoader,
            AutoLoader,
            ConditionalLoader,
        )
        self.assertEqual(result, "conditional")
        self.assertEqual([record[0] for record in calls], ["config", "conditional"])
        self.assertEqual(calls[1][2]["device_map"], "cpu")
        self.assertTrue(calls[1][2]["local_files_only"])

        calls.clear()
        ConfigLoader.model_type = "llama"
        result = applier._load_production_model(
            "local-model",
            FakeTorch,
            ConfigLoader,
            AutoLoader,
            ConditionalLoader,
        )
        self.assertEqual(result, "auto")
        self.assertEqual([record[0] for record in calls], ["config", "auto"])

    def test_bin_weight_checkpoint_is_rejected_by_safetensors_contract(self):
        checkpoint = self.root / "bin-model"
        checkpoint.mkdir()
        (checkpoint / "pytorch_model.bin").write_bytes(b"pickle")
        with self.assertRaisesRegex(ValueError, "must not contain .bin"):
            applier.require_safetensors_checkpoint(checkpoint)


class NamespaceMappingProofTests(unittest.TestCase):
    @staticmethod
    def record(character):
        return {
            "shape": [2, 2],
            "dtype": "torch.bfloat16",
            "sha256": character * 64,
        }

    def gemma_fixture(self):
        embed = self.record("a")
        saved = {
            "language_model.model.embed_tokens.weight": embed,
            "language_model.model.layers.0.mlp.down_proj.weight": self.record("b"),
            "vision_tower.vision_model.embeddings.weight": self.record("c"),
            "multi_modal_projector.linear.weight": self.record("d"),
        }
        expected = {
            "model.language_model.embed_tokens.weight": embed,
            "model.language_model.layers.0.mlp.down_proj.weight": self.record("b"),
            "model.vision_tower.embeddings.weight": self.record("c"),
            "model.multi_modal_projector.linear.weight": self.record("d"),
            "lm_head.weight": copy.deepcopy(embed),
        }
        aliases = {
            "lm_head.weight": [
                "lm_head.weight",
                "model.language_model.embed_tokens.weight",
            ]
        }
        return saved, expected, aliases

    def test_all_three_gemma_families_biject_modulo_declared_lm_head_tie(self):
        saved, expected, aliases = self.gemma_fixture()
        proof = applier.verify_tensor_inventory_namespace(
            saved,
            expected,
            aliases,
            applier.gemma3_namespace_mapping_contract(),
        )
        self.assertEqual(proof["tensor_count"], 4)
        self.assertEqual(proof["mapped_state_tensor_count"], 4)
        self.assertEqual(proof["expected_state_tensor_count"], 5)
        self.assertEqual(proof["omitted_tied_aliases"], ["lm_head.weight"])
        self.assertEqual(
            proof["namespace_mapping"]["rule_match_counts"],
            {
                "language_model": 2,
                "vision_tower": 1,
                "multi_modal_projector": 1,
            },
        )
        self.assertEqual(proof["namespace_mapping"]["mapping_pair_count"], 4)
        reversed_proof = applier.verify_tensor_inventory_namespace(
            dict(reversed(list(saved.items()))),
            expected,
            aliases,
            applier.gemma3_namespace_mapping_contract(),
        )
        self.assertEqual(
            proof["namespace_mapping"]["mapping_sha256"],
            reversed_proof["namespace_mapping"]["mapping_sha256"],
        )

    def test_gemma_unknown_mixed_and_missing_family_keys_fail_closed(self):
        saved, expected, aliases = self.gemma_fixture()
        cases = []
        unknown = dict(saved)
        unknown["rogue.weight"] = self.record("e")
        cases.append((unknown, "no namespace mapping rule"))
        mixed = dict(saved)
        mixed["model.language_model.loaded_name.weight"] = self.record("e")
        cases.append((mixed, "no namespace mapping rule"))
        missing_family = {
            key: value
            for key, value in saved.items()
            if not key.startswith("multi_modal_projector.")
        }
        cases.append((missing_family, "missing required namespace families"))
        for inventory, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    applier.verify_tensor_inventory_namespace(
                        inventory,
                        expected,
                        aliases,
                        applier.gemma3_namespace_mapping_contract(),
                    )

    def test_gemma_unmapped_or_wrong_tensor_and_bad_tie_fail_closed(self):
        saved, expected, aliases = self.gemma_fixture()
        unexpected_saved = dict(saved)
        unexpected_saved["language_model.model.unexpected.weight"] = self.record("e")
        with self.assertRaisesRegex(ValueError, "unexpected state tensors"):
            applier.verify_tensor_inventory_namespace(
                unexpected_saved,
                expected,
                aliases,
                applier.gemma3_namespace_mapping_contract(),
            )

        extra_expected = dict(expected)
        extra_expected["model.language_model.unmapped.weight"] = self.record("e")
        with self.assertRaisesRegex(ValueError, "unknown or unmapped"):
            applier.verify_tensor_inventory_namespace(
                saved,
                extra_expected,
                aliases,
                applier.gemma3_namespace_mapping_contract(),
            )

        for field, value in (
            ("sha256", "f" * 64),
            ("shape", [9, 9]),
            ("dtype", "torch.float32"),
        ):
            wrong_saved = copy.deepcopy(saved)
            wrong_saved["vision_tower.vision_model.embeddings.weight"][field] = value
            with self.subTest(wrong_tensor_field=field):
                with self.assertRaisesRegex(ValueError, "bytes differ"):
                    applier.verify_tensor_inventory_namespace(
                        wrong_saved,
                        expected,
                        aliases,
                        applier.gemma3_namespace_mapping_contract(),
                    )

        missing_declared = dict(expected)
        del missing_declared["lm_head.weight"]
        with self.assertRaisesRegex(ValueError, "unknown or unmapped"):
            applier.verify_tensor_inventory_namespace(
                saved,
                missing_declared,
                aliases,
                applier.gemma3_namespace_mapping_contract(),
            )

        with self.assertRaisesRegex(ValueError, "not exclusively runtime storage-tied"):
            applier.verify_tensor_inventory_namespace(
                saved,
                expected,
                {},
                applier.gemma3_namespace_mapping_contract(),
            )
        wrong_peer = {
            "lm_head.weight": [
                "lm_head.weight",
                "model.language_model.layers.0.mlp.down_proj.weight",
            ]
        }
        with self.assertRaisesRegex(ValueError, "not exclusively runtime storage-tied"):
            applier.verify_tensor_inventory_namespace(
                saved,
                expected,
                wrong_peer,
                applier.gemma3_namespace_mapping_contract(),
            )
        extra_alias = {
            "lm_head.weight": [
                "lm_head.weight",
                "model.language_model.embed_tokens.weight",
                "model.language_model.layers.0.mlp.down_proj.weight",
            ]
        }
        with self.assertRaisesRegex(ValueError, "not exclusively runtime storage-tied"):
            applier.verify_tensor_inventory_namespace(
                saved,
                expected,
                extra_alias,
                applier.gemma3_namespace_mapping_contract(),
            )

    def test_mapping_collision_and_overlap_guards_are_active(self):
        saved = {"a.weight": self.record("a"), "b.weight": self.record("b")}
        collision_rules = [
            {"id": "a", "serialized_prefix": "a.", "state_prefix": "state."},
            {"id": "b", "serialized_prefix": "b.", "state_prefix": "state."},
        ]
        with self.assertRaisesRegex(ValueError, "mapping collision"):
            applier._map_serialized_inventory(saved, collision_rules, ["a", "b"])

        overlapping_rules = [
            {"id": "broad", "serialized_prefix": "a.", "state_prefix": "x."},
            {
                "id": "narrow",
                "serialized_prefix": "a.weight",
                "state_prefix": "y.weight",
            },
        ]
        with self.assertRaisesRegex(ValueError, "matches multiple"):
            applier._map_serialized_inventory(
                {"a.weight": self.record("a")}, overlapping_rules, []
            )

    def test_actual_source_and_output_gemma_proofs_share_complete_pair_map(self):
        source_saved, source_expected, aliases = self.gemma_fixture()
        contract = applier.gemma3_namespace_mapping_contract()
        source_proof = applier.verify_tensor_inventory_namespace(
            source_saved, source_expected, aliases, contract
        )

        output_saved = copy.deepcopy(source_saved)
        output_expected = copy.deepcopy(source_expected)
        changed = self.record("e")
        output_saved[
            "language_model.model.layers.0.mlp.down_proj.weight"
        ] = changed
        output_expected[
            "model.language_model.layers.0.mlp.down_proj.weight"
        ] = copy.deepcopy(changed)
        output_proof = applier.verify_tensor_inventory_namespace(
            output_saved, output_expected, aliases, contract
        )
        cross_proof = applier.verify_source_output_namespace_equivalence(
            source_proof, output_proof
        )
        self.assertTrue(cross_proof["identical"])
        self.assertEqual(cross_proof["canonical_to_state_mapping_count"], 4)
        self.assertNotEqual(
            source_proof["mapped_inventory_sha256"],
            output_proof["mapped_inventory_sha256"],
        )
        self.assertEqual(
            source_proof["namespace_mapping"]["mapping_sha256"],
            output_proof["namespace_mapping"]["mapping_sha256"],
        )

    def test_non_gemma_contract_preserves_exact_name_behavior_only(self):
        saved = {"layer.weight": self.record("a")}
        proof = applier.verify_tensor_inventory_namespace(
            saved,
            copy.deepcopy(saved),
            {},
            applier.exact_namespace_mapping_contract(),
        )
        self.assertEqual(proof["mapped_state_tensor_count"], 1)
        with self.assertRaisesRegex(ValueError, "unexpected state tensors"):
            applier.verify_tensor_inventory_namespace(
                {"renamed.weight": self.record("a")},
                copy.deepcopy(saved),
                {},
                applier.exact_namespace_mapping_contract(),
            )
        tied_expected = {
            "embed.weight": self.record("b"),
            "lm_head.weight": self.record("b"),
        }
        tied_proof = applier.verify_tensor_inventory_namespace(
            {"embed.weight": self.record("b")},
            tied_expected,
            {"embed.weight": ["embed.weight", "lm_head.weight"]},
            applier.exact_namespace_mapping_contract(),
        )
        self.assertEqual(tied_proof["omitted_tied_aliases"], ["lm_head.weight"])

    def test_gemma_contract_selection_requires_matching_config_and_wrapper(self):
        exact_model = SimpleNamespace(config=SimpleNamespace(model_type="llama"))
        self.assertEqual(
            applier.namespace_mapping_contract_for_model(exact_model)["name"],
            "exact_serialized_state_names_v1",
        )
        wrong_wrapper = SimpleNamespace(config=SimpleNamespace(model_type="gemma3"))
        with self.assertRaisesRegex(ValueError, "inconsistent Gemma3"):
            applier.namespace_mapping_contract_for_model(wrong_wrapper)
        gemma_type = type("Gemma3ForConditionalGeneration", (), {})
        wrong_config = gemma_type()
        wrong_config.config = SimpleNamespace(model_type="llama")
        with self.assertRaisesRegex(ValueError, "inconsistent Gemma3"):
            applier.namespace_mapping_contract_for_model(wrong_config)
        correct = gemma_type()
        correct.config = SimpleNamespace(model_type="gemma3")
        self.assertEqual(
            applier.namespace_mapping_contract_for_model(correct)["name"],
            "gemma3_conditional_hf_serialized_to_state_v1",
        )


@unittest.skipIf(real_torch is None, "PyTorch is not installed in this environment")
class RealTorchCpuCompatibilityTests(unittest.TestCase):
    def test_bfloat16_cpu_prefix_edit_uses_real_pytorch_tensor_semantics(self):
        torch = real_torch

        class MLP(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.down_proj = torch.nn.Linear(
                    3, 2, bias=False, dtype=torch.bfloat16
                )

        class Layer(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.mlp = MLP()

        class LanguageModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.layers = torch.nn.ModuleList([Layer()])

        class ConditionalWrapper(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.model = torch.nn.Module()
                self.model.language_model = LanguageModel()

        model = ConditionalWrapper().cpu()
        weight = model.model.language_model.layers[0].mlp.down_proj.weight
        with torch.no_grad():
            weight.copy_(
                torch.tensor(
                    [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
                    dtype=torch.bfloat16,
                )
            )
        rows = []
        for rank, neuron in enumerate((0, 1), start=1):
            column = weight[:, neuron]
            rows.append(
                {
                    "layer": 0,
                    "neuron": neuron,
                    "global_rank": rank,
                    "parameter_name": (
                        "model.language_model.layers.0.mlp.down_proj.weight"
                    ),
                    "resolved_parameter_surface": (
                        "model.language_model.layers.0.mlp.down_proj.weight"
                    ),
                    "source_column_shape": list(column.shape),
                    "source_column_dtype": str(column.dtype),
                    "source_column_sha256": applier.tensor_sha256(column, torch),
                }
            )
        envelope = {
            "model_surface": {"decoder_path": "model.language_model.layers"},
            "selected_neurons": rows,
        }
        verified, parameters, _, _ = applier.verify_all_mask_bindings(
            envelope, model, torch
        )
        untouched = weight[:, 1].detach().clone()
        applications = applier.apply_verified_prefix(
            verified,
            parameters,
            top_k=1,
            column_scale=0.5,
            torch=torch,
        )
        self.assertEqual(weight.dtype, torch.bfloat16)
        self.assertTrue(
            torch.equal(
                weight[:, 0],
                torch.tensor([0.5, 2.0], dtype=torch.bfloat16),
            )
        )
        self.assertTrue(torch.equal(weight[:, 1], untouched))
        self.assertTrue(applications[0]["bytes_changed"])


if __name__ == "__main__":
    unittest.main()
