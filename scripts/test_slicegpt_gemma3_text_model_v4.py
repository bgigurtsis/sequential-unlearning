import importlib.util
import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT = SCRIPT_DIR / "slicegpt_gemma3_text_model_v4.py"
sys.path.insert(0, str(SCRIPT_DIR))
try:
    SPEC = importlib.util.spec_from_file_location("slicegpt_gemma3_text_model_v4", SCRIPT)
    TEXT = importlib.util.module_from_spec(SPEC)
    sys.modules[SPEC.name] = TEXT
    SPEC.loader.exec_module(TEXT)
finally:
    sys.path.pop(0)


RUNTIME_AVAILABLE = all(
    importlib.util.find_spec(name) is not None
    for name in ("torch", "transformers")
)


class SourceContractTests(unittest.TestCase):
    def test_transferred_backbone_reinstalls_output_capture_hooks(self):
        class Backbone:
            _output_capturing_hooks_installed = True

        backbone = Backbone()
        TEXT._reset_transferred_output_capture_state(backbone)
        self.assertIs(backbone._output_capturing_hooks_installed, False)

    def test_frozen_identity_and_status_remain_fail_closed(self):
        self.assertEqual(TEXT.HIDDEN_SIZE, 2560)
        self.assertEqual(TEXT.INTERMEDIATE_SIZE, 10240)
        self.assertEqual(TEXT.NUM_LAYERS, 34)
        self.assertEqual(TEXT.PROJECTION_NAMES, (
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ))
        self.assertEqual(
            [i for i, kind in enumerate(TEXT.LAYER_TYPES) if kind == "full_attention"],
            [5, 11, 17, 23, 29],
        )
        self.assertEqual(
            TEXT.CORE_SOURCE_SHA256,
            "c4df2be9111fd293454b19f98fba5d46805479d51db02d0611dcfab58f73cfdd",
        )
        status = TEXT.qualification_status()
        self.assertTrue(status["canonical_text_model_implemented"])
        self.assertFalse(status["nonzero_slice_authorized"])
        self.assertIsNone(status["probe2_verdict"])

    def test_dimension_schema_is_exact_and_nonzero_has_no_bypass(self):
        dimensions = TEXT.full_width_dimensions()
        canonical = TEXT._canonical_dimensions(dimensions)
        self.assertEqual(len(canonical), 34)
        self.assertEqual(canonical[0], (2560, 2560, 2560))
        malformed = list(dimensions)
        malformed[3] = {"input": 2560, "attention": True, "output": 2560}
        with self.assertRaisesRegex(RuntimeError, "exact integer"):
            TEXT._canonical_dimensions(malformed)
        reduced = [dict(record) for record in dimensions]
        for index, record in enumerate(reduced):
            record["input"] = 2560 if index == 0 else 2432
            record["attention"] = 2432
            record["output"] = 2560 if index == 33 else 2432
        with self.assertRaisesRegex(RuntimeError, "sealed capability"):
            TEXT._canonical_dimensions(reduced)
        with self.assertRaisesRegex(RuntimeError, "schema changed"):
            TEXT._canonical_dimensions([{"input": 2560, "attention": 2560, "output": 2560, "authorization": object()}] * 34)

    def test_forward_exposes_hard_pixel_boundary_and_cache_interface(self):
        signature = inspect.signature(TEXT.Gemma3SliceGPTTextForCausalLMV4.forward)
        self.assertIn("pixel_values", signature.parameters)
        self.assertIn("past_key_values", signature.parameters)
        self.assertIn("use_cache", signature.parameters)
        self.assertIn("logits_to_keep", signature.parameters)
        instance = TEXT.Gemma3SliceGPTTextForCausalLMV4.__new__(
            TEXT.Gemma3SliceGPTTextForCausalLMV4
        )
        with self.assertRaisesRegex(RuntimeError, "text-only"):
            TEXT.Gemma3SliceGPTTextForCausalLMV4.forward(
                instance, input_ids=object(), pixel_values=object()
            )

    def test_source_has_no_tie_or_authorization_escape_hatch(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("_tied_weights_keys: dict[str, str] = {}", source)
        self.assertIn("def tie_weights", source)
        self.assertIn("pixel_values are forbidden", source)
        self.assertNotIn("trust_remote_code", source)
        self.assertNotIn("authorization:", source)
        self.assertNotIn("capability:", source)
        with self.assertRaisesRegex(RuntimeError, "project loader"):
            TEXT.Gemma3SliceGPTTextForCausalLMV4.from_pretrained("untrusted-path")


@unittest.skipUnless(RUNTIME_AVAILABLE, "pinned torch/transformers runtime is server-only")
class PinnedRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        import transformers

        cls.torch = torch
        if torch.__version__ != "2.13.0+cu130":
            raise unittest.SkipTest("not the pinned torch runtime")
        if transformers.__version__ != "5.14.1":
            raise unittest.SkipTest("not the pinned Transformers runtime")

    def test_config_roundtrip_preserves_custom_identity_and_no_tie(self):
        config = TEXT.Gemma3SliceGPTTextConfigV4(
            residual_dimensions=TEXT.full_width_dimensions()
        )
        encoded = config.to_dict()
        self.assertEqual(encoded["model_type"], TEXT.MODEL_TYPE)
        self.assertEqual(encoded["architectures"], [TEXT.ARCHITECTURE])
        self.assertIs(encoded["tie_word_embeddings"], False)
        self.assertEqual(encoded["eos_token_id"], [1, 106])
        self.assertEqual(encoded["dtype"], "bfloat16")
        decoded = TEXT.Gemma3SliceGPTTextConfigV4(**encoded)
        self.assertEqual(decoded.to_dict(), encoded)
        with tempfile.TemporaryDirectory() as directory:
            config.save_pretrained(directory)
            native = TEXT.Gemma3SliceGPTTextConfigV4.from_pretrained(directory)
        self.assertEqual(native.to_dict(), encoded)
        tampered = dict(encoded)
        tampered["hidden_size"] = 2304
        with self.assertRaisesRegex(RuntimeError, "hidden_size"):
            TEXT.Gemma3SliceGPTTextConfigV4(**tampered)
        tampered = dict(encoded)
        tampered["slicegpt_adapter_core_version"] = "substituted"
        with self.assertRaisesRegex(RuntimeError, "adapter-core"):
            TEXT.Gemma3SliceGPTTextConfigV4(**tampered)
        tampered = dict(encoded)
        tampered["slicegpt_adapter_core_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "source hash"):
            TEXT.Gemma3SliceGPTTextConfigV4(**tampered)

    def test_meta_skeleton_is_deterministic_strict_and_untied(self):
        torch = self.torch
        config = TEXT.Gemma3SliceGPTTextConfigV4(
            residual_dimensions=TEXT.full_width_dimensions(),
        )
        with torch.device("meta"):
            model = TEXT.Gemma3SliceGPTTextForCausalLMV4(config)
        TEXT.validate_compressed_skeleton(model)
        self.assertIsNot(model.lm_head.weight, model.model.embed_tokens.weight)
        self.assertEqual(type(model.model.layers[0]).__name__, "CompressedGemma3DecoderLayerCore")
        self.assertEqual(tuple(model.model.layers[0].attn_shortcut.shape), (2560, 2560))
        self.assertEqual(tuple(model.model.layers[0].self_attn.q_proj.weight.shape), (2048, 2560))
        self.assertEqual(tuple(model.model.layers[0].self_attn.k_proj.weight.shape), (1024, 2560))
        self.assertEqual(tuple(model.model.layers[0].mlp.gate_proj.weight.shape), (10240, 2560))
        self.assertEqual(tuple(model.model.layers[-1].mlp.down_proj.weight.shape), (2560, 10240))
        names = TEXT.exact_projection_module_names(model)
        self.assertEqual(len(names), 34 * 7)
        self.assertEqual(len(TEXT.expected_state_keys()), 444)
        self.assertEqual(len(TEXT.expected_parameter_keys()), 376)
        self.assertEqual(len(TEXT.expected_buffer_keys()), 68)
        self.assertEqual(set(dict(model.named_parameters())), set(TEXT.expected_parameter_keys()))
        self.assertEqual(
            set(dict(model.named_buffers())),
            set(TEXT.expected_buffer_keys() | TEXT.expected_nonpersistent_buffer_keys()),
        )
        self.assertEqual(
            set(model.state_dict()) & set(dict(model.named_buffers())),
            set(TEXT.expected_buffer_keys()),
        )
        self.assertEqual(set(model.state_dict()), set(TEXT.expected_state_keys()))
        self.assertTrue(all(value.dtype is torch.bfloat16 for value in model.state_dict().values()))
        self.assertEqual(
            {name.rsplit(".", 1)[-1] for name in names},
            set(TEXT.PROJECTION_NAMES),
        )
        prepared = model.prepare_inputs_for_generation(
            torch.tensor([[1, 2, 3]], dtype=torch.long),
            attention_mask=torch.ones((1, 3), dtype=torch.long),
            use_cache=True,
        )
        self.assertTrue(torch.equal(prepared["input_ids"], torch.tensor([[1, 2, 3]])))
        self.assertIs(prepared["use_cache"], True)
        model.extra_surface = self.torch.nn.Module()
        model.extra_surface.q_proj = self.torch.nn.Identity()
        with self.assertRaisesRegex(RuntimeError, "module-name surface"):
            TEXT.exact_projection_module_names(model)
        del model.extra_surface
        model.config.sliding_window = 2048
        with self.assertRaisesRegex(RuntimeError, "sliding_window"):
            TEXT.validate_compressed_skeleton(model)
        model.config.sliding_window = TEXT.SLIDING_WINDOW
        model.model.layers[0].self_attn.q_proj = self.torch.nn.Identity()
        with self.assertRaisesRegex(RuntimeError, "q_proj"):
            TEXT.validate_compressed_skeleton(model)

    def test_skeleton_rejects_safety_dtype_and_state_partition_tampering(self):
        torch = self.torch
        config = TEXT.Gemma3SliceGPTTextConfigV4()
        with torch.device("meta"):
            model = TEXT.Gemma3SliceGPTTextForCausalLMV4(config)
        TEXT.validate_compressed_skeleton(model)

        model.config.dense_post_affine = False
        with self.assertRaisesRegex(RuntimeError, "safety config"):
            TEXT.validate_compressed_skeleton(model)
        model.config.dense_post_affine = True
        TEXT.validate_compressed_skeleton(model)

        original_head = model.lm_head.weight
        model.lm_head.weight = torch.nn.Parameter(
            torch.empty(original_head.shape, device="meta", dtype=torch.float32),
            requires_grad=original_head.requires_grad,
        )
        with self.assertRaisesRegex(RuntimeError, "exact BF16"):
            TEXT.validate_compressed_skeleton(model)
        model.lm_head.weight = original_head
        TEXT.validate_compressed_skeleton(model)

        layer = model.model.layers[0]
        original_shortcut = layer.attn_shortcut
        layer.attn_shortcut = torch.nn.Parameter(original_shortcut, requires_grad=False)
        with self.assertRaisesRegex(RuntimeError, "named-parameter partition"):
            TEXT.validate_compressed_skeleton(model)

    def test_final_fusion_is_fp64_then_single_bf16_store_and_untied(self):
        torch = self.torch
        head = torch.tensor(
            [[1.0, -2.0, 3.0, -4.0], [0.25, 0.5, -0.75, 1.0], [2.0, 3.0, 4.0, 5.0]],
            dtype=torch.bfloat16,
        )
        norm = torch.tensor([0.5, -0.25, 0.125, -0.5], dtype=torch.bfloat16)
        before = head.clone()
        fused = TEXT.fuse_final_norm_into_head(head, norm, chunk_rows=2)
        expected = (head.double() * (1.0 + norm.double())).to(torch.bfloat16)
        self.assertTrue(torch.equal(fused, expected))
        self.assertTrue(torch.equal(head, before))
        self.assertNotEqual(fused.untyped_storage().data_ptr(), head.untyped_storage().data_ptr())
        with self.assertRaisesRegex(RuntimeError, "positive exact integer"):
            TEXT.fuse_final_norm_into_head(head, norm, chunk_rows=True)

    def test_tie_guard_rejects_object_alias_and_pixel_rejects_before_super(self):
        torch = self.torch
        config = TEXT.Gemma3SliceGPTTextConfigV4()
        with torch.device("meta"):
            model = TEXT.Gemma3SliceGPTTextForCausalLMV4(config)
        model.lm_head.weight = model.model.embed_tokens.weight
        with self.assertRaisesRegex(RuntimeError, "silently retied"):
            model.tie_weights()
        with mock.patch.object(
            TEXT.Gemma3ForCausalLM,
            "forward",
            side_effect=AssertionError("super forward must not run"),
        ):
            with self.assertRaisesRegex(RuntimeError, "text-only"):
                model.forward(input_ids=torch.ones((1, 1), dtype=torch.long), pixel_values=object())
        model.lm_head.weight = self.torch.nn.Parameter(
            self.torch.empty((TEXT.VOCAB_SIZE, TEXT.HIDDEN_SIZE), device="meta")
        )
        with self.assertRaisesRegex(RuntimeError, "not strictly loaded"):
            model.forward(input_ids=torch.ones((1, 1), dtype=torch.long))


if __name__ == "__main__":
    unittest.main()
