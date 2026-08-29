import copy
import importlib.util
import math
import sys
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).with_name("slicegpt_gemma3_adapter_core_v4.py")
SPEC = importlib.util.spec_from_file_location("slicegpt_gemma3_adapter_core_v4", SCRIPT)
CORE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CORE
SPEC.loader.exec_module(CORE)


TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


class SourceBoundaryTests(unittest.TestCase):
    def test_constants_and_status_are_fail_closed(self):
        self.assertEqual(CORE.HIDDEN_SIZE, 2560)
        self.assertEqual(CORE.INTERMEDIATE_SIZE, 10240)
        self.assertEqual(CORE.NUM_LAYERS, 34)
        self.assertEqual(CORE.LAYER_TYPES.count("full_attention"), 5)
        self.assertEqual(
            [index for index, kind in enumerate(CORE.LAYER_TYPES) if kind == "full_attention"],
            [5, 11, 17, 23, 29],
        )
        status = CORE.qualification_status()
        self.assertTrue(status["adapter_core_implemented"])
        self.assertFalse(status["nonzero_slice_authorized"])
        self.assertIsNone(status["probe2_verdict"])
        self.assertGreaterEqual(len(status["remaining_gates"]), 7)

    def test_changed_parameter_contract_is_exact(self):
        self.assertEqual(len(CORE.PER_LAYER_CHANGED_PARAMETERS), 11)
        self.assertEqual(len(set(CORE.PER_LAYER_CHANGED_PARAMETERS)), 11)
        self.assertNotIn("self_attn.q_norm.weight", CORE.PER_LAYER_CHANGED_PARAMETERS)
        self.assertNotIn("self_attn.k_norm.weight", CORE.PER_LAYER_CHANGED_PARAMETERS)
        self.assertEqual(
            set(CORE.PROTECTED_QK_NORMS),
            {"self_attn.q_norm.weight", "self_attn.k_norm.weight"},
        )

    def test_text_only_boundary(self):
        CORE.reject_pixel_values(None)
        with self.assertRaisesRegex(RuntimeError, "text-only"):
            CORE.reject_pixel_values(object())


@unittest.skipUnless(TORCH_AVAILABLE, "torch is server-only")
class TorchAdapterCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        from torch import nn

        cls.torch = torch
        cls.nn = nn

    def orthogonal(self, dimension, seed):
        generator = self.torch.Generator().manual_seed(seed)
        matrix = self.torch.randn(
            dimension, dimension, generator=generator, dtype=self.torch.float64
        )
        q, _ = self.torch.linalg.qr(matrix)
        return CORE.canonicalize_basis_signs(q)

    def norm_class(self):
        torch, nn = self.torch, self.nn

        class Gemma3RMSNorm(nn.Module):
            def __init__(self, dimension, eps=CORE.RMS_EPS):
                super().__init__()
                self.eps = eps
                self.weight = nn.Parameter(
                    (torch.randn(dimension, dtype=torch.float32) * 0.1).to(torch.bfloat16)
                )

            def forward(self, values):
                work = values.double()
                work = work * torch.rsqrt(work.pow(2).mean(-1, keepdim=True) + self.eps)
                return (work * (1.0 + self.weight.float())).type_as(values)

        return Gemma3RMSNorm

    def toy_layer(self, biased=False):
        torch, nn = self.torch, self.nn
        Gemma3RMSNorm = self.norm_class()

        class Attention(nn.Module):
            def __init__(self):
                super().__init__()
                self.q_proj = nn.Linear(8, 8, bias=biased, dtype=torch.bfloat16)
                self.k_proj = nn.Linear(8, 8, bias=False, dtype=torch.bfloat16)
                self.v_proj = nn.Linear(8, 8, bias=False, dtype=torch.bfloat16)
                self.o_proj = nn.Linear(8, 8, bias=False, dtype=torch.bfloat16)
                self.q_norm = Gemma3RMSNorm(8)
                self.k_norm = Gemma3RMSNorm(8)

            def forward(self, hidden_states, **_kwargs):
                values = (
                    self.q_norm(self.q_proj(hidden_states))
                    + self.k_norm(self.k_proj(hidden_states))
                    + self.v_proj(hidden_states)
                )
                return self.o_proj(values), None

        class MLP(nn.Module):
            def __init__(self):
                super().__init__()
                self.hidden_size = 8
                self.gate_proj = nn.Linear(8, 16, bias=False, dtype=torch.bfloat16)
                self.up_proj = nn.Linear(8, 16, bias=False, dtype=torch.bfloat16)
                self.down_proj = nn.Linear(16, 8, bias=False, dtype=torch.bfloat16)

            def forward(self, values):
                return self.down_proj(torch.tanh(self.gate_proj(values)) * self.up_proj(values))

        class ToyLayer(nn.Module):
            def __init__(self):
                super().__init__()
                self.config = SimpleNamespace()
                self.layer_idx = 0
                self.self_attn = Attention()
                self.mlp = MLP()
                self.input_layernorm = Gemma3RMSNorm(8)
                self.post_attention_layernorm = Gemma3RMSNorm(8)
                self.pre_feedforward_layernorm = Gemma3RMSNorm(8)
                self.post_feedforward_layernorm = Gemma3RMSNorm(8)

            def forward(self, hidden_states, **kwargs):
                residual = hidden_states
                hidden_states = self.input_layernorm(hidden_states)
                hidden_states, _ = self.self_attn(hidden_states=hidden_states, **kwargs)
                hidden_states = self.post_attention_layernorm(hidden_states)
                hidden_states = residual + hidden_states
                residual = hidden_states
                hidden_states = self.pre_feedforward_layernorm(hidden_states)
                hidden_states = self.mlp(hidden_states)
                hidden_states = self.post_feedforward_layernorm(hidden_states)
                return residual + hidden_states

        self.torch.manual_seed(19)
        return ToyLayer()

    def parameter_hashes(self, module):
        return {name: CORE.tensor_sha256(value) for name, value in module.named_parameters()}

    def test_full_width_nonidentity_sandwich_equivalence_and_qk_protection(self):
        torch = self.torch
        layer = self.toy_layer()
        layer.eval()
        values = torch.randn(2, 3, 8, dtype=torch.bfloat16)
        expected = layer(values)
        q_input = self.orthogonal(8, 1)
        q_attention = self.orthogonal(8, 2)
        q_output = self.orthogonal(8, 3)
        q_norm_object = layer.self_attn.q_norm
        k_norm_object = layer.self_attn.k_norm
        parameters_before = self.parameter_hashes(layer)
        qk_before = {
            "q": CORE.tensor_sha256(q_norm_object.weight),
            "k": CORE.tensor_sha256(k_norm_object.weight),
        }
        transformed, report = CORE.apply_layer_core(
            layer,
            q_input,
            q_attention,
            q_output,
            hidden_size=8,
            intermediate_size=16,
            q_width=8,
            kv_width=8,
            head_dim=8,
            strict_class_names=False,
        )
        rotated_values = (values.float() @ q_input.float()).to(torch.bfloat16)
        actual = transformed(rotated_values)
        expected_rotated = expected.float() @ q_output.float()
        self.assertTrue(torch.allclose(expected_rotated, actual.float(), rtol=5e-2, atol=5e-2))
        self.assertIsNot(transformed.self_attn.q_norm, q_norm_object)
        self.assertIsNot(transformed.self_attn.k_norm, k_norm_object)
        self.assertEqual(
            qk_before,
            {
                "q": CORE.tensor_sha256(transformed.self_attn.q_norm.weight),
                "k": CORE.tensor_sha256(transformed.self_attn.k_norm.weight),
            },
        )
        self.assertEqual(report.changed_parameters, CORE.PER_LAYER_CHANGED_PARAMETERS)
        self.assertFalse(report.zero_slice_noop)
        self.assertFalse(transformed.training)
        parameters_after = self.parameter_hashes(transformed)
        removed = set(parameters_before) - set(parameters_after)
        added = set(parameters_after) - set(parameters_before)
        changed = {
            name
            for name in set(parameters_before) & set(parameters_after)
            if parameters_before[name] != parameters_after[name]
        }
        self.assertEqual(
            removed | changed,
            set(CORE.PER_LAYER_CHANGED_PARAMETERS),
        )
        self.assertEqual(
            removed,
            {"input_layernorm.weight", "pre_feedforward_layernorm.weight"},
        )
        self.assertEqual(added, set())
        self.assertEqual(parameters_before, self.parameter_hashes(layer))

    def test_zero_slice_identity_is_bit_exact_noop(self):
        torch = self.torch
        layer = self.toy_layer()
        identity = torch.eye(8, dtype=torch.float64)
        before = self.parameter_hashes(layer)
        transformed, report = CORE.apply_layer_core(
            layer,
            identity,
            identity,
            identity,
            hidden_size=8,
            intermediate_size=16,
            q_width=8,
            kv_width=8,
            head_dim=8,
            strict_class_names=False,
        )
        self.assertIs(transformed, layer)
        self.assertEqual(before, self.parameter_hashes(layer))
        self.assertTrue(report.zero_slice_noop)
        self.assertEqual(report.changed_parameters, ())

    def test_basis_and_topology_errors_fail_before_mutation(self):
        torch = self.torch
        layer = self.toy_layer()
        identity = torch.eye(8, dtype=torch.float64)
        bad = identity.clone()
        bad[0, 0] = 2.0
        before = self.parameter_hashes(layer)
        with self.assertRaisesRegex(RuntimeError, "not orthonormal"):
            CORE.apply_layer_core(
                layer,
                identity,
                bad,
                identity,
                hidden_size=8,
                intermediate_size=16,
                q_width=8,
                kv_width=8,
                head_dim=8,
                strict_class_names=False,
            )
        self.assertEqual(before, self.parameter_hashes(layer))

        biased = self.toy_layer(biased=True)
        biased_before = self.parameter_hashes(biased)
        with self.assertRaisesRegex(RuntimeError, "bias-free"):
            CORE.apply_layer_core(
                biased,
                identity,
                identity,
                identity,
                hidden_size=8,
                intermediate_size=16,
                q_width=8,
                kv_width=8,
                head_dim=8,
                strict_class_names=False,
            )
        self.assertEqual(biased_before, self.parameter_hashes(biased))

        aliased = self.toy_layer()
        aliased.self_attn.k_norm = aliased.self_attn.q_norm
        aliased_before = self.parameter_hashes(aliased)
        with self.assertRaisesRegex(RuntimeError, "norms are aliased"):
            CORE.apply_layer_core(
                aliased,
                identity,
                identity,
                identity,
                hidden_size=8,
                intermediate_size=16,
                q_width=8,
                kv_width=8,
                head_dim=8,
                strict_class_names=False,
            )
        self.assertEqual(aliased_before, self.parameter_hashes(aliased))

        noncanonical = identity.clone()
        noncanonical[:, 0].neg_()
        with self.assertRaisesRegex(RuntimeError, "canonical sign"):
            CORE.validate_basis(noncanonical, 8, label="fixture")

    def test_bf16_dense_post_affine_cast_order(self):
        torch = self.torch
        basis = self.orthogonal(8, 21)
        norm_weight = torch.linspace(-0.2, 0.3, 8, dtype=torch.bfloat16)
        dense = CORE.dense_post_affine(norm_weight, basis).to(torch.bfloat16)
        module = CORE.DensePostAffineGemmaRMSNorm(dense, CORE.RMS_EPS)
        values = torch.tensor(
            [[0.431, -1.217, 0.031, 2.113, -0.741, 0.118, 1.337, -2.009]],
            dtype=torch.bfloat16,
        )
        normalized = values.float()
        normalized = normalized * torch.rsqrt(
            normalized.pow(2).mean(-1, keepdim=True) + CORE.RMS_EPS
        )
        expected = (normalized @ dense.float()).to(torch.bfloat16)
        wrong = normalized.to(torch.bfloat16) @ dense
        self.assertTrue(torch.equal(module(values), expected))
        self.assertFalse(torch.equal(expected, wrong))

    def test_reduced_rectangular_gqa_math_and_authorization_lock(self):
        torch = self.torch
        source = self.orthogonal(8, 31)[:, :4]
        target = self.orthogonal(8, 32)[:, :4]
        q_weight = torch.randn(8, 8, dtype=torch.bfloat16)
        kv_weight = torch.randn(4, 8, dtype=torch.bfloat16)
        norm_weight = torch.randn(8, dtype=torch.bfloat16) * 0.05
        self.assertEqual(CORE.fuse_pre_norm_weight(q_weight, norm_weight, source).shape, (8, 4))
        self.assertEqual(CORE.fuse_pre_norm_weight(kv_weight, norm_weight, source).shape, (4, 4))
        self.assertEqual(CORE.rotate_output_weight(q_weight, target).shape, (4, 8))
        self.assertEqual(CORE.residual_shortcut(source, target).shape, (4, 4))

        layer = self.toy_layer()
        before = self.parameter_hashes(layer)
        with self.assertRaisesRegex(RuntimeError, "sealed authorization"):
            CORE.apply_layer_core(
                layer,
                source,
                target,
                source,
                hidden_size=8,
                intermediate_size=16,
                q_width=8,
                kv_width=8,
                head_dim=8,
                strict_class_names=False,
            )
        with self.assertRaisesRegex(RuntimeError, "cannot validate nonzero authorization"):
            CORE.apply_layer_core(
                layer,
                source,
                target,
                source,
                hidden_size=8,
                intermediate_size=16,
                q_width=8,
                kv_width=8,
                head_dim=8,
                strict_class_names=False,
                authorization=object(),
            )
        self.assertEqual(before, self.parameter_hashes(layer))

    def test_allocation_failure_is_off_object_and_fp32_is_fixed(self):
        torch = self.torch
        layer = self.toy_layer()
        before = self.parameter_hashes(layer)
        identity = torch.eye(8, dtype=torch.float64)
        rotated = self.orthogonal(8, 41)
        with self.assertRaisesRegex(RuntimeError, "fixed to FP32"):
            CORE.apply_layer_core(
                layer,
                identity,
                rotated,
                identity,
                hidden_size=8,
                intermediate_size=16,
                q_width=8,
                kv_width=8,
                head_dim=8,
                compute_dtype=torch.float64,
                strict_class_names=False,
            )
        with mock.patch.object(CORE, "_new_linear", side_effect=MemoryError("fixture OOM")):
            with self.assertRaises(MemoryError):
                CORE.apply_layer_core(
                    layer,
                    identity,
                    rotated,
                    identity,
                    hidden_size=8,
                    intermediate_size=16,
                    q_width=8,
                    kv_width=8,
                    head_dim=8,
                    strict_class_names=False,
                )
        self.assertEqual(before, self.parameter_hashes(layer))

    def test_model_install_rolls_back_second_assignment_failure(self):
        torch, nn = self.torch, self.nn
        old_layers = nn.ModuleList([nn.Identity()])
        new_layers = nn.ModuleList([nn.Identity()])
        language_model = SimpleNamespace(layers=old_layers)

        class RejectNoSplit:
            def __setattr__(self, name, value):
                if name == "_no_split_modules":
                    raise RuntimeError("fixture assignment failure")
                object.__setattr__(self, name, value)

        model = RejectNoSplit()
        surface = CORE.ModelSurface(model, language_model, None, (), None, None, None)
        with (
            mock.patch.object(CORE, "build_model_layers_atomic", return_value=(new_layers, ())),
            mock.patch.object(CORE, "discover_pinned_gemma3", return_value=surface),
        ):
            with self.assertRaisesRegex(RuntimeError, "fixture assignment failure"):
                CORE.install_model_layers_atomic(model, ())
        self.assertIs(language_model.layers, old_layers)

    def test_exact_pinned_topology_discovery_on_meta_surface(self):
        torch, nn = self.torch, self.nn

        class Gemma3RMSNorm(nn.Module):
            def __init__(self, dimension):
                super().__init__()
                self.eps = CORE.RMS_EPS
                self.weight = nn.Parameter(torch.empty(dimension, device="meta"))

        class Gemma3Attention(nn.Module):
            def __init__(self, index):
                super().__init__()
                self.q_proj = nn.Linear(2560, 2048, bias=False, device="meta")
                self.k_proj = nn.Linear(2560, 1024, bias=False, device="meta")
                self.v_proj = nn.Linear(2560, 1024, bias=False, device="meta")
                self.o_proj = nn.Linear(2048, 2560, bias=False, device="meta")
                self.q_norm = Gemma3RMSNorm(256)
                self.k_norm = Gemma3RMSNorm(256)
                self.layer_type = CORE.LAYER_TYPES[index]
                self.scaling = CORE.QUERY_PRE_ATTN_SCALAR**-0.5
                self.layer_idx = index
                self.head_dim = 256
                self.num_key_value_groups = 2
                self.attention_dropout = 0.0
                self.is_causal = True
                self.is_sliding = self.layer_type == "sliding_attention"
                self.sliding_window = 1024 if self.is_sliding else None

        class Gemma3MLP(nn.Module):
            def __init__(self):
                super().__init__()
                self.gate_proj = nn.Linear(2560, 10240, bias=False, device="meta")
                self.up_proj = nn.Linear(2560, 10240, bias=False, device="meta")
                self.down_proj = nn.Linear(10240, 2560, bias=False, device="meta")

        Gemma3DecoderLayer = type(
            "Gemma3DecoderLayer",
            (nn.Module,),
            {
                "__init__": lambda self, index: (
                    nn.Module.__init__(self),
                    setattr(self, "config", SimpleNamespace(query_pre_attn_scalar=256, sliding_window=1024)),
                    setattr(self, "layer_idx", index),
                    setattr(self, "self_attn", Gemma3Attention(index)),
                    setattr(self, "mlp", Gemma3MLP()),
                    setattr(self, "input_layernorm", Gemma3RMSNorm(2560)),
                    setattr(self, "post_attention_layernorm", Gemma3RMSNorm(2560)),
                    setattr(self, "pre_feedforward_layernorm", Gemma3RMSNorm(2560)),
                    setattr(self, "post_feedforward_layernorm", Gemma3RMSNorm(2560)),
                    None,
                )[-1]
            },
        )

        Gemma3TextConfig = type("Gemma3TextConfig", (SimpleNamespace,), {})
        text_config = Gemma3TextConfig(
            hidden_size=2560,
            intermediate_size=10240,
            num_hidden_layers=34,
            num_attention_heads=8,
            num_key_value_heads=4,
            head_dim=256,
            vocab_size=262208,
            rms_norm_eps=1e-6,
            query_pre_attn_scalar=256,
            sliding_window=1024,
            tie_word_embeddings=True,
            hidden_activation="gelu_pytorch_tanh",
            max_position_embeddings=131072,
            attention_bias=False,
            attention_dropout=0.0,
            use_bidirectional_attention=False,
            use_cache=True,
            layer_types=list(CORE.LAYER_TYPES),
        )
        Gemma3TextModel = type("Gemma3TextModel", (nn.Module,), {})
        language = Gemma3TextModel()
        language.layers = nn.ModuleList([Gemma3DecoderLayer(index) for index in range(34)])
        for layer in language.layers:
            layer.config = text_config
            layer.hidden_size = 2560
            layer.self_attn.config = text_config
            layer.self_attn.attn_logit_softcapping = None
            layer.mlp.config = text_config
            layer.mlp.hidden_size = 2560
            layer.mlp.intermediate_size = 10240
        Gemma3TextScaledWordEmbedding = type("Gemma3TextScaledWordEmbedding", (nn.Module,), {})
        language.embed_tokens = Gemma3TextScaledWordEmbedding()
        tied = nn.Parameter(torch.empty(262208, 2560, device="meta"))
        language.embed_tokens.weight = tied
        language.embed_tokens.scalar_embed_scale = math.sqrt(2560)
        language.norm = Gemma3RMSNorm(2560)
        Gemma3Model = type("Gemma3Model", (nn.Module,), {})
        backbone = Gemma3Model()
        backbone.language_model = language
        Gemma3MultiModalProjector = type("Gemma3MultiModalProjector", (nn.Module,), {})
        backbone.multi_modal_projector = Gemma3MultiModalProjector()
        Gemma3ForConditionalGeneration = type("Gemma3ForConditionalGeneration", (nn.Module,), {})
        model = Gemma3ForConditionalGeneration()
        model.model = backbone
        model.config = SimpleNamespace(text_config=text_config)
        model.lm_head = nn.Linear(2560, 262208, bias=False, device="meta")
        model.lm_head.weight = tied
        surface = CORE.discover_pinned_gemma3(model)
        self.assertEqual(len(surface.layers), 34)

        text_config.layer_types[5] = "sliding_attention"
        with self.assertRaisesRegex(RuntimeError, "attention pattern"):
            CORE.discover_pinned_gemma3(model)


if __name__ == "__main__":
    unittest.main()
