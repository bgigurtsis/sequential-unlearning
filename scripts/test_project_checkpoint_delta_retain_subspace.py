"""Tests for the fail-closed retain-subspace checkpoint projector."""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

try:
    import torch
except ModuleNotFoundError:  # Local lightweight Windows interpreter.
    torch = None

TorchModuleBase = torch.nn.Module if torch is not None else object

try:
    import project_checkpoint_delta_retain_subspace as projector
except ModuleNotFoundError:
    from scripts import project_checkpoint_delta_retain_subspace as projector


def _write_retain(path: Path, records=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records if records is not None else ["Explain tides.", "Say hello."]), encoding="utf-8")


def _pair(prompt="Hello", answer="Hi"):
    return {"id": "one", "category": "greeting", "prompt": prompt,
            "answer": answer, "template_family": "simple"}


def _record(ids, mask):
    return {"input_ids": ids, "position_mask": mask}


class StandardLibraryContractTests(unittest.TestCase):
    def test_layer_range_declares_exact_full_dense_surface(self):
        layers = projector.parse_layer_spec("12-19,28-33")
        self.assertEqual(layers, list(range(12, 20)) + list(range(28, 34)))
        names = projector.declared_module_names(layers)
        self.assertEqual(len(names), 98)
        self.assertEqual(len(names), len(set(names)))
        self.assertIn(
            "model.language_model.layers.12.self_attn.q_proj", names
        )
        self.assertIn("model.language_model.layers.33.mlp.down_proj", names)

    def test_layer_range_rejects_overlap_duplicates_and_malformed(self):
        for spec in ("1,1", "1-3,3-4", "", "3-1", "1,,2", "a"):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                projector.parse_layer_spec(spec)

    def test_cli_requires_subcommand_and_qualified_donor_digest(self):
        args = projector.parse_args(["digest", "--model", "checkpoint"])
        self.assertEqual(args.command, "digest")
        with self.assertRaises(SystemExit):
            projector.parse_args(
                [
                    "project",
                    "--clean-model",
                    "clean",
                    "--edited-model",
                    "edited",
                    "--tokenizer-model",
                    "tokenizer",
                    "--retain-json",
                    "train.json",
                    "--layers",
                    "12-19,28-33",
                    "--output-dir",
                    "out",
                    "--retained-energy",
                    "0.9",
                ]
            )
        with self.assertRaises(ValueError):
            projector._sha256_argument("A" * 64, "digest")

    def test_native_schemas_counts_determinism_and_duplicates_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retain_train.json"
            records = ["same", "same", _pair(),
                {"category": "x", "prompt": "Next", "answer": "Yes", "augmentation": "x", "seed": 1},
                {"answer": "Fine", "capture_policy": "clean", "category": "x",
                 "conversation_id": "c", "messages": [{"role": "user", "content": "Earlier"},
                    {"role": "assistant", "content": "Hello"}, {"role": "user", "content": "Now"}], "turn": 2}]
            _write_retain(path, records)
            first, sources = projector.load_retain_training_data([path], max_prompts=5, expected_records=5)
            second, _ = projector.load_retain_training_data([path], max_prompts=5, expected_records=5)
            self.assertEqual(first, second)
            self.assertEqual(len({r["record_id"] for r in first}), 5)
            self.assertEqual(sources[0]["record_count"], 5)
            self.assertEqual(sources[0]["schema_counts"]["generic_string"], 2)
            for expected, maximum in ((4, 5), (5, 4)):
                with self.assertRaises(ValueError):
                    projector.load_retain_training_data([path], max_prompts=maximum, expected_records=expected)

    def test_training_data_rejects_eval_paths_unknown_schemas_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            held = root / "heldout" / "retain_train.json"
            _write_retain(held)
            with self.assertRaisesRegex(ValueError, "evaluation marker"):
                projector.load_retain_training_data([held], max_prompts=10, expected_records=2)
            path = root / "retain_train.json"
            for invalid in ({"split": "train"}, [{"prompt": "x", "answer": "y"}], [""], [_pair(answer="")]):
                _write_retain(path, invalid)
                with self.assertRaises(ValueError):
                    projector.load_retain_training_data([path], max_prompts=10, expected_records=1)
            path.write_text('[{"prompt":"x","prompt":"y"}]', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate key"):
                projector.load_retain_training_data([path], max_prompts=10, expected_records=1)

    def test_native_frozen_corpora_have_exact_2052_records(self):
        root = Path(__file__).resolve().parents[1] / "derisk/whole_concept_jobs_v1"
        records, sources = projector.load_retain_training_data(
            [root / "retain_nonjob_244.json", root / "preserve_clean_plus_context_multiturn6x_1808.json"],
            max_prompts=2052, expected_records=2052)
        self.assertEqual(len(records), 2052)
        self.assertEqual(sum(r["answer"] is None for r in records), 244)
        self.assertEqual(sorted(s["record_count"] for s in sources), [244, 1808])
        self.assertEqual(len({r["record_id"] for r in records}), 2052)

    def test_evaluation_overlap_checks_prompts_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            train = root / "retain_train.json"
            _write_retain(train, [_pair()])
            records, _ = projector.load_retain_training_data([train], max_prompts=1, expected_records=1)
            audit = root / "audit.json"
            for document in ([{"prompt": "Hello"}], [{"messages": [{"role": "user", "content": "Hello"}]}], [{"turns": ["Other", "Hello"]}]):
                audit.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "overlaps"):
                    projector.prove_zero_evaluation_overlap(records, [audit])
            audit.write_text('[{"prompt":"Different"}]', encoding="utf-8")
            _, proof = projector.prove_zero_evaluation_overlap(records, [audit])
            self.assertEqual(proof["prompt_overlap_count"], 0)
            self.assertFalse(proof["evaluation_inputs_used_for_forward_pass"])

    def test_exact_native_tokenization_truncation_no_eos_and_shift(self):
        class Tokenizer:
            def __init__(self): self.calls = []
            def __call__(self, text, **kwargs):
                self.calls.append((text, kwargs))
                return {"input_ids": [10, 11, 12, 13, 14] if text == "generic" else [5, 6, 7]}
            def apply_chat_template(self, messages, **kwargs):
                self.calls.append((messages, kwargs))
                return {"input_ids": [1, 2, 3]}
        tokenizer = Tokenizer()
        records = [{"record_id": "a", "schema_family": "generic_string", "messages": [{"role": "user", "content": "generic"}], "answer": None},
            {"record_id": "b", "schema_family": "captured_event_pair", "messages": [{"role": "user", "content": "prompt"}], "answer": "answer"}]
        rows, info = projector.tokenize_retain_records(records, tokenizer, max_length=5)
        self.assertEqual(rows[0]["input_ids"], [10, 11, 12, 13, 14])
        self.assertEqual(rows[0]["position_mask"], [True, True, True, True, False])
        self.assertEqual(rows[1]["input_ids"], [1, 2, 3, 5, 6])
        self.assertEqual(rows[1]["position_mask"], [False, False, True, True, False])
        self.assertEqual(tokenizer.calls[0], ("generic", {"truncation": True, "max_length": 5}))
        self.assertEqual(tokenizer.calls[2], ("answer", {"add_special_tokens": False}))
        self.assertEqual(info["selected_shifted_position_count"], 6)
        full, _ = projector.tokenize_retain_records(records, Tokenizer(), max_length=20)
        self.assertEqual(full[1]["input_ids"], [1, 2, 3, 5, 6, 7])
        with self.assertRaisesRegex(ValueError, "no valid shifted"):
            projector.tokenize_retain_records(records, Tokenizer(), max_length=3)

    def test_four_basis_groups_per_layer_cover_all_linears(self):
        mapping, groups = projector.declared_basis_groups([12, 13])
        self.assertEqual(len(mapping), 14)
        self.assertEqual(len(groups), 8)
        self.assertEqual(sorted(len(g["modules"]) for g in groups), [1, 1, 1, 1, 2, 2, 3, 3])

    def test_production_request_rejects_changed_grid_and_source_pins(self):
        args = SimpleNamespace(layers="12-19,28-33", retained_energy=.9, max_length=256,
            expected_retain_records=2052, clean_model="clean", edited_model="edited", tokenizer_model="clean",
            expected_edited_weight_sha256=projector.source_pins.PINNED_EDITED_WEIGHT_HASHES["model.safetensors"],
            expected_edited_logical_sha256=projector.source_pins.PINNED_EDITED_LOGICAL_INVENTORY_SHA256,
            retain_json=["generic", "chat"])
        hashes = {"edited/config.json": projector.source_pins.PINNED_EDITED_CONFIG_SHA256,
            "generic": "330ed2b8fe24f4e99f431e0b0c776457c034436e863582840b43c36e6585cd5e",
            "chat": "51fef432b073feb577c0be6a764d0fc2e303c55b0fdddd4bebc77401b0d6065a"}
        with mock.patch.object(projector, "_exact_local_directory", side_effect=lambda path, label: Path(path)), \
             mock.patch.object(projector.checkpoint_utils, "model_weight_hashes", return_value=projector.source_pins.PINNED_CLEAN_WEIGHT_HASHES), \
             mock.patch.object(projector.selection, "sha256_file", side_effect=lambda path: hashes[Path(path).as_posix()]):
            projector.validate_production_request(args)
            for field, value in (("layers", "12-19"), ("retained_energy", .8), ("max_length", 512),
                    ("expected_retain_records", 2000), ("tokenizer_model", "edited"),
                    ("expected_edited_weight_sha256", "0" * 64)):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    projector.validate_production_request(SimpleNamespace(**{**vars(args), field: value}))
            hashes["edited/config.json"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "config"):
                projector.validate_production_request(args)

    def test_inventory_pair_requires_exact_declared_delta_surface(self):
        clean = {
            "a.weight": {"shape": [2, 3], "dtype": "torch.bfloat16", "sha256": "a"},
            "b": {"shape": [1], "dtype": "torch.bfloat16", "sha256": "b"},
        }
        edited = {
            "a.weight": {"shape": [2, 3], "dtype": "torch.bfloat16", "sha256": "c"},
            "b": {"shape": [1], "dtype": "torch.bfloat16", "sha256": "b"},
        }
        proof = projector.validate_checkpoint_pair_inventories(
            clean, edited, ["a.weight"]
        )
        self.assertEqual(proof["changed_state_keys"], ["a.weight"])
        for mutation, pattern in (
            ({"a.weight": clean["a.weight"], "b": edited["b"]}, "declared_unchanged"),
            ({"a.weight": edited["a.weight"], "b": {**edited["b"], "sha256": "x"}}, "undeclared_changed"),
            ({"a.weight": edited["a.weight"]}, "state keys differ"),
            ({"a.weight": {**edited["a.weight"], "shape": [3, 2]}, "b": edited["b"]}, "shape mismatch"),
            ({"a.weight": {**edited["a.weight"], "dtype": "torch.float32"}, "b": edited["b"]}, "dtype mismatch"),
        ):
            with self.subTest(pattern=pattern), self.assertRaisesRegex(ValueError, pattern):
                projector.validate_checkpoint_pair_inventories(
                    clean, mutation, ["a.weight"]
                )

    def test_mutation_locality_requires_precomputed_selected_values(self):
        clean = {
            "a": {"shape": [1], "dtype": "x", "sha256": "0"},
            "b": {"shape": [1], "dtype": "x", "sha256": "0"},
        }
        after = {
            "a": {"shape": [1], "dtype": "x", "sha256": "1"},
            "b": clean["b"],
        }
        proof = projector.verify_mutation_locality(
            clean, after, ["a"], {"a": after["a"]}
        )
        self.assertTrue(proof["all_unselected_tensors_exactly_clean"])
        escaped = dict(after)
        escaped["b"] = {**clean["b"], "sha256": "2"}
        with self.assertRaisesRegex(RuntimeError, "outside"):
            projector.verify_mutation_locality(
                clean, escaped, ["a"], {"a": after["a"]}
            )
        with self.assertRaisesRegex(RuntimeError, "precomputed"):
            projector.verify_mutation_locality(
                clean,
                {**after, "a": {**after["a"], "sha256": "wrong"}},
                ["a"],
                {"a": after["a"]},
            )


@unittest.skipIf(torch is None, "PyTorch is not installed")
class TorchAlgebraAndCaptureTests(unittest.TestCase):
    def test_cache_exact_roundtrip_corruption_and_changed_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def compute():
                calls.append(True)
                return {"x": torch.tensor([[1., 2.]], dtype=torch.float64)}
            first, cold = projector.immutable_tensor_cache(directory, {"source": "a"}, compute, torch=torch)
            second, hit = projector.immutable_tensor_cache(directory, {"source": "a"}, compute, torch=torch)
            self.assertFalse(cold["hit"])
            self.assertTrue(hit["hit"])
            self.assertTrue(torch.equal(first["x"], second["x"]))
            self.assertEqual(len(calls), 1)
            projector.immutable_tensor_cache(directory, {"source": "b"}, compute, torch=torch)
            self.assertEqual(len(calls), 2)
            (Path(hit["path"]) / "payload.pt").write_bytes(b"corrupted")
            with self.assertRaisesRegex(RuntimeError, "file hash mismatch"):
                projector.immutable_tensor_cache(directory, {"source": "a"}, compute, torch=torch)

    def test_spectrum_cache_matches_uncached_at_each_energy_without_redecomposition(self):
        activations = torch.diag(torch.tensor([3., 2., 1.], dtype=torch.float64))
        with tempfile.TemporaryDirectory() as directory:
            for energy in (0., .7, .95, 1.):
                baseline, baseline_info = projector.compute_retain_basis(activations,
                    retained_energy=energy, cutoff_tie_rtol=1e-12, torch=torch)
                if energy == 0.:
                    cached, info = projector.compute_retain_basis(activations,
                        retained_energy=energy, cutoff_tie_rtol=1e-12, torch=torch, cache_dir=directory)
                else:
                    with mock.patch.object(torch.linalg, "eigh", side_effect=AssertionError("cache must avoid eigh")):
                        cached, info = projector.compute_retain_basis(activations,
                            retained_energy=energy, cutoff_tie_rtol=1e-12, torch=torch, cache_dir=directory)
                self.assertTrue(torch.equal(baseline, cached))
                self.assertEqual(baseline_info["basis_sha256"], info["basis_sha256"])
                self.assertEqual(info["spectrum_cache"]["hit"], energy != 0.)

    def _fake_gemma(self):
        class Attention(torch.nn.Module):
            def __init__(self):
                super().__init__()
                for name in ("q_proj", "k_proj", "v_proj", "o_proj"):
                    setattr(
                        self,
                        name,
                        torch.nn.Linear(3, 3, bias=False, dtype=torch.bfloat16),
                    )

        class MLP(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.gate_proj = torch.nn.Linear(
                    3, 5, bias=False, dtype=torch.bfloat16
                )
                self.up_proj = torch.nn.Linear(
                    3, 5, bias=False, dtype=torch.bfloat16
                )
                self.down_proj = torch.nn.Linear(
                    5, 3, bias=False, dtype=torch.bfloat16
                )

        class Layer(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.self_attn = Attention()
                self.mlp = MLP()

        class Config:
            model_type = "gemma3"

            def to_dict(self):
                return {"model_type": "gemma3", "hidden_size": 3}

        class Base(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.config = Config()
                self.model = torch.nn.Module()
                self.model.language_model = torch.nn.Module()
                self.model.language_model.layers = torch.nn.ModuleList([Layer()])

        gemma_type = type("Gemma3ForConditionalGeneration", (Base,), {})
        return gemma_type()

    def test_declared_module_resolution_proves_all_seven_bias_free_bf16_linears(self):
        model = self._fake_gemma()
        modules, records = projector.resolve_declared_linear_modules(
            model, [0], torch=torch
        )
        self.assertEqual(len(modules), 7)
        self.assertEqual(len(records), 7)
        self.assertEqual(
            {record["linear_suffix"] for record in records},
            set(projector.LINEAR_SUFFIXES),
        )
        model.model.language_model.layers[0].self_attn.q_proj = torch.nn.Linear(
            3, 3, bias=True, dtype=torch.bfloat16
        )
        with self.assertRaisesRegex(ValueError, "has a bias"):
            projector.resolve_declared_linear_modules(model, [0], torch=torch)

    def test_known_spectrum_selects_minimal_rank_and_is_deterministic(self):
        activations = torch.diag(
            torch.tensor([3.0, 2.0, 1.0], dtype=torch.float64)
        )
        first, info = projector.compute_retain_basis(
            activations,
            retained_energy=0.7,
            cutoff_tie_rtol=1e-12,
            torch=torch,
        )
        second, second_info = projector.compute_retain_basis(
            activations.clone(),
            retained_energy=0.7,
            cutoff_tie_rtol=1e-12,
            torch=torch,
        )
        self.assertEqual(info["selected_rank"], 2)
        self.assertLess(info["previous_rank_retained_energy"], 0.7)
        self.assertGreaterEqual(info["achieved_retained_energy"], 0.7)
        self.assertTrue(torch.equal(first, second))
        self.assertEqual(info["basis_sha256"], second_info["basis_sha256"])
        for column in range(first.shape[1]):
            vector = first[:, column]
            pivot = int(torch.argmax(torch.abs(vector)))
            self.assertGreaterEqual(float(vector[pivot]), 0.0)

    def test_pca_is_uncentered_and_rank_zero_is_explicit(self):
        constant = torch.ones((4, 3), dtype=torch.float64)
        basis, info = projector.compute_retain_basis(
            constant,
            retained_energy=1.0,
            cutoff_tie_rtol=1e-12,
            torch=torch,
        )
        self.assertEqual(info["effective_rank"], 1)
        self.assertEqual(basis.shape, (3, 1))
        empty, empty_info = projector.compute_retain_basis(
            constant,
            retained_energy=0.0,
            cutoff_tie_rtol=1e-12,
            torch=torch,
        )
        self.assertEqual(empty.shape, (3, 0))
        self.assertEqual(empty_info["selected_rank"], 0)

    def test_pca_rejects_cutoff_ties_zero_and_nonfinite(self):
        tied = torch.eye(3, dtype=torch.float64)
        with self.assertRaisesRegex(ValueError, "rank-ambiguous"):
            projector.compute_retain_basis(
                tied,
                retained_energy=0.5,
                cutoff_tie_rtol=1e-12,
                torch=torch,
            )
        for invalid, pattern in (
            (torch.zeros((2, 3), dtype=torch.float64), "zero numerical"),
            (torch.tensor([[1.0, math.nan]], dtype=torch.float64), "non-finite"),
            (torch.tensor([[1.0, math.inf]], dtype=torch.float64), "non-finite"),
        ):
            with self.subTest(pattern=pattern), self.assertRaisesRegex(ValueError, pattern):
                projector.compute_retain_basis(
                    invalid,
                    retained_energy=0.9,
                    cutoff_tie_rtol=1e-12,
                    torch=torch,
                )

    def test_rectangular_right_projection_annihilates_only_input_axis(self):
        clean = torch.zeros((2, 3), dtype=torch.float32)
        edited = torch.tensor(
            [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=torch.float32
        )
        basis = torch.tensor([[1.0], [0.0], [0.0]], dtype=torch.float64)
        projected, info = projector.project_weight_delta(
            clean, edited, basis, torch=torch
        )
        expected = torch.tensor(
            [[0.0, 2.0, 3.0], [0.0, 5.0, 6.0]], dtype=torch.float32
        )
        self.assertTrue(torch.equal(projected, expected))
        self.assertTrue(torch.equal(projected @ basis.float(), torch.zeros((2, 1))))
        self.assertEqual(info["projected_delta_on_basis_l2_norm"], 0.0)
        # A left projection cannot even use this U against a [2,3] W.
        with self.assertRaises(RuntimeError):
            _ = (torch.eye(2) - basis.float() @ basis.float().T) @ edited

    def test_projection_identity_orthogonal_full_and_invalid_basis(self):
        clean = torch.zeros((2, 3), dtype=torch.float32)
        edited = torch.tensor(
            [[0.0, 2.0, 3.0], [0.0, 5.0, 6.0]], dtype=torch.float32
        )
        empty = torch.empty((3, 0), dtype=torch.float64)
        rank_zero, _ = projector.project_weight_delta(
            clean, edited, empty, torch=torch
        )
        self.assertTrue(torch.equal(rank_zero, edited))
        first_axis = torch.tensor([[1.0], [0.0], [0.0]], dtype=torch.float64)
        orthogonal, _ = projector.project_weight_delta(
            clean, edited, first_axis, torch=torch
        )
        self.assertTrue(torch.equal(orthogonal, edited))
        full = torch.eye(3, dtype=torch.float64)
        removed, _ = projector.project_weight_delta(clean, edited, full, torch=torch)
        self.assertTrue(torch.equal(removed, torch.zeros_like(edited)))
        for invalid in (
            torch.tensor([[1.0], [1.0], [0.0]], dtype=torch.float64),
            torch.tensor([[math.nan], [0.0], [0.0]], dtype=torch.float64),
        ):
            with self.assertRaises(ValueError):
                projector.project_weight_delta(clean, edited, invalid, torch=torch)

    def test_annihilation_gate_uses_projected_not_source_delta_norm(self):
        basis = torch.tensor([[1.], [1.]], dtype=torch.float64) / math.sqrt(2.)
        clean = torch.zeros((1, 2), dtype=torch.float32)
        edited = basis.T.float().clone()
        # Almost all source energy lies in U. FP32 residual is tiny relative
        # to source, yet points along U and fails the frozen projected ratio.
        with self.assertRaisesRegex(RuntimeError, "residual ratio"):
            projector.project_weight_delta(clean, edited, basis, torch=torch)

    def test_bfloat16_rank_zero_application_is_exact_edited_identity(self):
        clean = torch.nn.Linear(3, 2, bias=False, dtype=torch.bfloat16)
        edited = torch.nn.Linear(3, 2, bias=False, dtype=torch.bfloat16)
        with torch.no_grad():
            clean.weight.copy_(
                torch.tensor([[1, 2, 3], [4, 5, 6]], dtype=torch.bfloat16)
            )
            edited.weight.copy_(
                torch.tensor([[1, 2.5, 3], [4, 5, 7]], dtype=torch.bfloat16)
            )
        applications, expected = projector.apply_projected_deltas(
            {"m": clean},
            {"m": edited},
            {"m": torch.empty((3, 0), dtype=torch.float64)},
            {"m": {"selected_rank": 0}},
            retained_energy=0.0,
            torch=torch,
        )
        self.assertTrue(torch.equal(clean.weight, edited.weight))
        self.assertTrue(applications[0]["published_equals_edited"])
        self.assertEqual(expected["m.weight"]["sha256"], projector.tensor_sha256(clean.weight, torch))

    def test_bfloat16_identity_preserves_values_lost_by_fp32_cancellation(self):
        clean = torch.nn.Linear(1, 1, bias=False, dtype=torch.bfloat16)
        edited = torch.nn.Linear(1, 1, bias=False, dtype=torch.bfloat16)
        with torch.no_grad():
            clean.weight.fill_(1.)
            edited.weight.fill_(1e-30)
        reconstructed = clean.weight.float() + (edited.weight.float() - clean.weight.float())
        self.assertFalse(torch.equal(reconstructed.bfloat16(), edited.weight))
        projector.apply_projected_deltas({"m": clean}, {"m": edited},
            {"m": torch.empty((1, 0), dtype=torch.float64)}, {"m": {"selected_rank": 0}},
            retained_energy=0., torch=torch)
        self.assertTrue(torch.equal(clean.weight, edited.weight))

    class _ToyModel(TorchModuleBase):
        def __init__(self, *, double=False, omit=False):
            super().__init__()
            self.embedding = torch.nn.Embedding(20, 3)
            self.a = torch.nn.Linear(3, 3, bias=False)
            self.b = torch.nn.Linear(3, 2, bias=False)
            self.double = double
            self.omit = omit
            with torch.no_grad():
                self.embedding.weight.copy_(
                    torch.arange(60, dtype=torch.float32).reshape(20, 3) / 10
                )

        def get_input_embeddings(self):
            return self.embedding

        def forward(self, input_ids, attention_mask, use_cache, return_dict):
            values = self.embedding(input_ids)
            first = self.a(values)
            if self.double:
                first = self.a(values)
            if not self.omit:
                second = self.b(values)
            else:
                second = first[..., :2]
            return SimpleNamespace(logits=second)

    def _collect(self, model, records, batch_size=1, shared=True):
        groups = [{"basis_group": "g", "representative_module": "a", "modules": ["a", "b"]}] if shared else [
            {"basis_group": n, "representative_module": n, "modules": [n]} for n in ("a", "b")]
        return projector.collect_clean_retain_keys(model, {"a": model.a, "b": model.b}, groups, records,
            pad_token_id=0, batch_size=batch_size, torch=torch)

    def test_keys_are_normalized_means_padding_and_batch_partition_invariant(self):
        model = self._ToyModel()
        records = [_record([1, 2, 3], [True, True, False]), _record([4, 5], [True, False])]
        first, proof = self._collect(model, records)
        second, _ = self._collect(model, records, batch_size=2)
        self.assertTrue(torch.equal(first["g"], second["g"]))
        mean = model.embedding.weight[[1, 2]].double().mean(dim=0)
        self.assertTrue(torch.equal(first["g"][0], mean / mean.norm()))
        self.assertTrue(proof["basis_groups"]["g"]["shared_input_equality_verified"])
        self.assertEqual(proof["basis_groups"]["g"]["record_key_count"], 2)
        self.assertFalse(model.a._forward_pre_hooks)
        self.assertFalse(model.b._forward_pre_hooks)

    def test_cache_keys_require_counts_widths_normalization_and_sharing_proof(self):
        import copy
        model = self._ToyModel()
        keys, proof = self._collect(model, [_record([1, 2], [True, False])])
        groups = [{"basis_group": "g", "representative_module": "a", "modules": ["a", "b"]}]
        def validate(k, p):
            projector.validate_cached_retain_keys(k, p, groups, {"a": model.a, "b": model.b}, expected_records=1, torch=torch)
        validate(keys, proof)
        for bad in (keys["g"].float(), keys["g"] * 2, keys["g"][:, :2], keys["g"].repeat(2, 1), keys["g"] * math.nan):
            with self.assertRaises(RuntimeError): validate({"g": bad}, proof)
        changed = copy.deepcopy(proof)
        changed["basis_groups"]["g"]["shared_input_equality_verified"] = False
        with self.assertRaises(RuntimeError): validate(keys, changed)
        changed = copy.deepcopy(proof)
        changed["retain_key_count"] = 2
        with self.assertRaises(RuntimeError): validate(keys, changed)

    def test_hooks_fail_on_missing_double_different_inputs_and_are_removed(self):
        records = [_record([1, 2], [True, False])]
        for model, pattern in ((self._ToyModel(omit=True), "did not fire"), (self._ToyModel(double=True), "more than once")):
            with self.assertRaisesRegex(RuntimeError, pattern): self._collect(model, records)
            self.assertFalse(model.a._forward_pre_hooks)
            self.assertFalse(model.b._forward_pre_hooks)
        model = self._ToyModel()
        class Different(self._ToyModel):
            def forward(self, input_ids, attention_mask, use_cache, return_dict):
                values = self.embedding(input_ids)
                self.a(values)
                return self.b(values + 1)
        with self.assertRaisesRegex(RuntimeError, "different selected inputs"):
            self._collect(Different(), records)
        model.a.in_features = 4
        with self.assertRaisesRegex(RuntimeError, "feature width"):
            self._collect(model, records, shared=False)
        self.assertFalse(model.a._forward_pre_hooks)

    def test_fresh_reload_inventory_verification_detects_one_tensor_change(self):
        model = torch.nn.Sequential(torch.nn.Linear(3, 2, bias=False))
        expected, _, aliases = projector.checkpoint_utils.model_tensor_inventory(
            model, torch
        )
        proof = projector.verify_reloaded_model(
            model, expected, aliases, torch=torch
        )
        self.assertTrue(proof["verified"])
        with torch.no_grad():
            model[0].weight[0, 0].add_(1)
        with self.assertRaisesRegex(RuntimeError, "differs"):
            projector.verify_reloaded_model(model, expected, aliases, torch=torch)


if __name__ == "__main__":
    unittest.main()
