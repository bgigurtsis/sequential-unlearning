import importlib.metadata
import importlib.util
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT = SCRIPT_DIR / "slicegpt_gemma3_project_io_v4.py"
sys.path.insert(0, str(SCRIPT_DIR))
try:
    SPEC = importlib.util.spec_from_file_location("slicegpt_gemma3_project_io_v4", SCRIPT)
    IO = importlib.util.module_from_spec(SPEC)
    sys.modules[SPEC.name] = IO
    SPEC.loader.exec_module(IO)
finally:
    sys.path.pop(0)


RUNTIME_AVAILABLE = all(
    importlib.util.find_spec(name) is not None
    for name in ("torch", "transformers", "peft", "safetensors")
)


class SourceContractTests(unittest.TestCase):
    def source_metadata(self):
        return {
            "version": IO.SOURCE_VERSION,
            "repo_commit": "1" * 40,
            "committed_sources": {
                IO.TEXT_MODEL_PATH: IO.TEXT_MODEL_SOURCE_SHA256,
                IO.ADAPTER_CORE_PATH: IO.ADAPTER_CORE_SOURCE_SHA256,
                IO.PROJECT_IO_PATH: IO.current_source_sha256(),
            },
            "provenance_spec_sha256": "2" * 64,
            "model_qualification_sha256": "3" * 64,
        }

    def test_frozen_sources_targets_and_status_are_fail_closed(self):
        self.assertEqual(
            IO.TEXT_MODEL_SOURCE_SHA256,
            "5d701e9fc4d79fb53e8523edb1942e598b2be2c8514019845be5590a45de9a1b",
        )
        self.assertEqual(
            IO.ADAPTER_CORE_SOURCE_SHA256,
            "c4df2be9111fd293454b19f98fba5d46805479d51db02d0611dcfab58f73cfdd",
        )
        targets = IO.canonical_target_names()
        self.assertEqual(len(targets), 34 * 7)
        self.assertEqual(
            {name.rsplit(".", 1)[-1] for name in targets}, set(IO.TARGET_SUFFIXES)
        )
        self.assertTrue(all(name.startswith("model.layers.") for name in targets))
        status = IO.qualification_status()
        self.assertTrue(status["full_width_only"])
        self.assertFalse(status["nonzero_slice_authorized"])
        self.assertIsNone(status["probe2_verdict"])

    def test_source_metadata_binds_loader_model_and_core_exactly(self):
        value = self.source_metadata()
        self.assertEqual(IO.validate_source_metadata(value), value)
        for path in (IO.TEXT_MODEL_PATH, IO.ADAPTER_CORE_PATH, IO.PROJECT_IO_PATH):
            tampered = json.loads(json.dumps(value))
            tampered["committed_sources"][path] = "0" * 64
            with self.assertRaisesRegex(IO.ProjectIOError, "exact model/core/project-loader"):
                IO.validate_source_metadata(tampered)
        tampered = json.loads(json.dumps(value))
        tampered["repo_commit"] = "1" * 39
        with self.assertRaisesRegex(IO.ProjectIOError, "identity changed"):
            IO.validate_source_metadata(tampered)

    def test_calibration_schema_rejects_bool_seed_and_aliases(self):
        value = {
            "version": IO.CALIBRATION_VERSION,
            "seed": 11,
            "metadata_fingerprint": "1" * 64,
            "tensors_sha256": "2" * 64,
            "complete_sha256": "3" * 64,
            "source_identity_fingerprint": "4" * 64,
        }
        self.assertEqual(IO.validate_calibration_metadata(value), value)
        tampered = dict(value, seed=True)
        with self.assertRaisesRegex(IO.ProjectIOError, "identity changed"):
            IO.validate_calibration_metadata(tampered)
        tampered = dict(value, extra=False)
        with self.assertRaisesRegex(IO.ProjectIOError, "exact schema"):
            IO.validate_calibration_metadata(tampered)

    def test_only_project_loader_can_return_executable_model(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("import slicegpt_gemma3_text_model_v4 as TEXT", source)
        self.assertIn("preloaded canonical text-model module is forbidden", source)
        self.assertIn("SourceFileLoader", source)
        self.assertIn("def load_project", source)
        self.assertIn("TEXT.validate_compressed_skeleton(model)", source)
        self.assertIn("post-assignment bitwise state check failed", source)
        self.assertIn("model._slicegpt_weights_loaded = True", source)
        self.assertIn("direct HF loading is forbidden", (SCRIPT_DIR / "slicegpt_gemma3_text_model_v4.py").read_text(encoding="utf-8"))
        signature = inspect.signature(IO.load_project)
        self.assertEqual(tuple(signature.parameters), ("root", "device"))

    def test_direct_source_loader_never_invokes_create_module(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dependency.py"
            path.write_bytes(b"identity = 7\n")
            name = "_slicegpt_project_io_create_module_adversary"
            try:
                with mock.patch.object(
                    IO.importlib.machinery.SourceFileLoader,
                    "create_module",
                    side_effect=AssertionError("create_module must never execute"),
                ) as callback:
                    module = IO._direct_module(name, path, IO.sha256_file(path))
                callback.assert_not_called()
                self.assertEqual(module.identity, 7)
            finally:
                sys.modules.pop(name, None)

    def test_direct_source_loader_rejects_buffered_read_substitution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dependency.py"
            path.write_bytes(b"identity = 7\n")
            expected = IO.sha256_file(path)
            name = "_slicegpt_project_io_buffer_adversary"
            original = Path.read_bytes

            def substitute(instance):
                if Path(instance) == path:
                    return b"identity = 99\n"
                return original(instance)

            try:
                with mock.patch.object(Path, "read_bytes", substitute):
                    with self.assertRaisesRegex(IO.ProjectIOError, "buffered.*source changed"):
                        IO._direct_module(name, path, expected)
                self.assertNotIn(name, sys.modules)
            finally:
                sys.modules.pop(name, None)


@unittest.skipUnless(RUNTIME_AVAILABLE, "pinned torch/Transformers/PEFT/Safetensors runtime is server-only")
class PinnedRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch

        cls.torch = torch
        expected = {
            "torch": "2.13.0",
            "transformers": "5.14.1",
            "peft": "0.19.1",
            "safetensors": "0.8.0",
        }
        if any(importlib.metadata.version(name) != version for name, version in expected.items()):
            raise unittest.SkipTest("not the exact pinned v4 runtime")
        IO._runtime()

    def skeleton(self):
        with self.torch.device("meta"):
            return IO.TEXT.Gemma3SliceGPTTextForCausalLMV4(
                IO.TEXT.Gemma3SliceGPTTextConfigV4()
            )

    def slicing(self):
        return {
            "version": IO.SLICING_VERSION,
            "mechanism": "slicegpt",
            "fraction": "0",
            "residual_dimensions": list(IO.TEXT.full_width_dimensions()),
            "calibration_seed": 11,
            "calibration_tensors_sha256": "1" * 64,
            "nonzero_slice_authorized": False,
        }

    def test_full_width_meta_shard_plan_is_deterministic_and_complete(self):
        model = self.skeleton()
        IO.TEXT.validate_compressed_skeleton(model)
        first = IO.plan_shards(model.state_dict(), max_shard_bytes=IO.MAX_SHARD_BYTES)
        second = IO.plan_shards(model.state_dict(), max_shard_bytes=IO.MAX_SHARD_BYTES)
        self.assertEqual(first, second)
        self.assertGreater(len(first), 1)
        flattened = [name for shard in first for name in shard]
        self.assertEqual(len(flattened), 444)
        self.assertEqual(set(flattened), IO.TEXT.expected_state_keys())
        self.assertEqual(len(flattened), len(set(flattened)))
        with self.assertRaisesRegex(IO.ProjectIOError, "positive exact integer"):
            IO.plan_shards(model.state_dict(), max_shard_bytes=True)

    def test_slicing_is_full_width_only_without_capability_bypass(self):
        value = self.slicing()
        self.assertEqual(IO.validate_slicing_config(value), value)
        reduced = json.loads(json.dumps(value))
        reduced["residual_dimensions"][0]["attention"] = 2432
        with self.assertRaisesRegex(RuntimeError, "sealed capability|full-width"):
            IO.validate_slicing_config(reduced)
        tampered = json.loads(json.dumps(value))
        tampered["fraction"] = ".05"
        with self.assertRaisesRegex(IO.ProjectIOError, "full-width"):
            IO.validate_slicing_config(tampered)
        tampered = json.loads(json.dumps(value))
        tampered["nonzero_slice_authorized"] = True
        with self.assertRaisesRegex(IO.ProjectIOError, "full-width"):
            IO.validate_slicing_config(tampered)

    def test_exact_peft_attachment_has_238_modules_and_476_trainables(self):
        wrapped = IO._attach_exact_lora(
            self.skeleton(), rank=2, alpha=2, adapter_name="default", allow_unloaded_meta=True
        )
        prefix = "base_model.model."
        attached = {
            name[len(prefix):]
            for name, module in wrapped.named_modules()
            if name.startswith(prefix)
            and type(module).__module__.startswith("peft.tuners.lora")
            and hasattr(module, "lora_A")
        }
        self.assertEqual(attached, set(IO.canonical_target_names()))
        trainable = {name for name, parameter in wrapped.named_parameters() if parameter.requires_grad}
        self.assertEqual(len(trainable), 476)
        self.assertTrue(all(".lora_A.default.weight" in name or ".lora_B.default.weight" in name for name in trainable))
        self.assertFalse(any("lm_head" in name or "q_norm" in name or "post_attention" in name for name in trainable))
        collision = self.skeleton()
        collision.extra_surface = self.torch.nn.Module()
        with self.torch.device("meta"):
            collision.extra_surface.q_proj = self.torch.nn.Linear(4, 4, bias=False)
        with self.assertRaisesRegex(RuntimeError, "module-name surface"):
            IO._attach_exact_lora(
                collision, rank=2, alpha=2, adapter_name="default", allow_unloaded_meta=True
            )

    def test_low_level_native_shards_are_deterministic_bf16_safetensors(self):
        torch = self.torch
        state = {
            "a": torch.arange(8, dtype=torch.bfloat16).reshape(2, 4),
            "b": torch.arange(6, dtype=torch.bfloat16).reshape(2, 3),
            "c": torch.ones((3, 3), dtype=torch.bfloat16),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            weight_map, records, total = IO._write_shards(state, (("a", "b"), ("c",)), root)
            self.assertEqual(set(weight_map), set(state))
            self.assertEqual(len(set(weight_map.values())), 2)
            self.assertEqual(total, sum(t.numel() * t.element_size() for t in state.values()))
            for name, record in records.items():
                self.assertEqual(record["dtype"], "BF16")
                self.assertEqual(record["sha256"], IO.tensor_sha256(state[name]))
            for shard in set(weight_map.values()):
                with IO.safe_open(root / shard, framework="pt", device="cpu") as handle:
                    self.assertEqual(
                        handle.metadata(),
                        {"format": "pt", "project_version": IO.PROJECT_VERSION, "shard": shard},
                    )

    def test_directory_publication_is_atomic_and_never_replaces(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            first = parent / "first.tmp"
            output = parent / "project"
            first.mkdir()
            (first / "member").write_bytes(b"first")
            IO._publish_directory_no_replace(first, output)
            self.assertEqual((output / "member").read_bytes(), b"first")
            second = parent / "second.tmp"
            second.mkdir()
            (second / "member").write_bytes(b"second")
            with self.assertRaisesRegex(IO.ProjectIOError, "appeared concurrently"):
                IO._publish_directory_no_replace(second, output)
            self.assertEqual((output / "member").read_bytes(), b"first")
            self.assertEqual((second / "member").read_bytes(), b"second")

    def test_strict_adapter_archive_roundtrip_and_coherent_tamper(self):
        torch = self.torch
        wrapped = IO._attach_exact_lora(
            self.skeleton(), rank=2, alpha=2, adapter_name="default", allow_unloaded_meta=True
        )
        for name, parameter in list(wrapped.named_parameters()):
            if not parameter.requires_grad:
                continue
            owner, leaf = IO._owner(wrapped, name)
            owner._parameters[leaf] = torch.nn.Parameter(
                torch.zeros(tuple(parameter.shape), dtype=torch.float32), requires_grad=True
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "adapter"
            archive = IO._save_adapter_bound(
                wrapped,
                project_manifest_sha256="a" * 64,
                output=root,
            )
            self.assertEqual(len(archive["tensors"]), 476)
            self.assertEqual(archive["config"]["target_modules"], list(IO.canonical_target_names()))
            self.assertEqual(
                IO.validate_adapter_archive(root, expected_project_manifest_sha256="a" * 64)["manifest_sha256"],
                archive["manifest_sha256"],
            )
            reloaded = IO._load_adapter_archive_on_model(
                self.skeleton(), archive, allow_unloaded_meta=True
            )
            reloaded_state = IO.peft.get_peft_model_state_dict(reloaded, adapter_name="default")
            self.assertEqual(set(reloaded_state), set(archive["tensors"]))
            self.assertTrue(
                all(
                    IO.tensor_sha256(tensor) == archive["tensors"][name]["sha256"]
                    for name, tensor in reloaded_state.items()
                )
            )
            config = root / "adapter_config.json"
            value = json.loads(config.read_text())
            value["rank"] = 4
            config.write_bytes(IO.canonical_json_bytes(value))
            with self.assertRaisesRegex(IO.ProjectIOError, "member hash mismatch"):
                IO.validate_adapter_archive(root, expected_project_manifest_sha256="a" * 64)
            manifest = IO._parse_manifest(root / "MANIFEST.sha256")
            manifest["adapter_config.json"] = IO.sha256_file(config)
            (root / "MANIFEST.sha256").write_bytes(IO._manifest_bytes(manifest))
            with self.assertRaisesRegex(IO.ProjectIOError, "tensor identity changed"):
                IO.validate_adapter_archive(root, expected_project_manifest_sha256="a" * 64)


if __name__ == "__main__":
    unittest.main()
