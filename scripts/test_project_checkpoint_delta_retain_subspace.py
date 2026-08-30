"""Tests for the fail-closed retain-subspace checkpoint projector."""

from __future__ import annotations

import json
import math
import tempfile
import unittest
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


def _write_retain(path: Path, prompts=None, **updates):
    document = {
        "schema_version": projector.RETAIN_DATA_SCHEMA_VERSION,
        "data_role": "retain_subspace_training",
        "split": "train",
        "prompts": prompts
        or [
            {"id": "retain-a", "text": "Explain why tides change."},
            {"id": "retain-b", "text": "Write a short friendly greeting."},
        ],
    }
    document.update(updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


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

    def test_training_data_schema_is_strict_and_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retain_train.json"
            _write_retain(path)
            records, sources = projector.load_retain_training_data(
                [path], max_prompts=2
            )
            self.assertEqual([item["id"] for item in records], ["retain-a", "retain-b"])
            self.assertEqual(sources[0]["prompt_count"], 2)
            self.assertEqual(len(sources[0]["file_sha256"]), 64)

    def test_training_data_rejects_eval_paths_and_nontrain_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            eval_path = root / "heldout" / "retain_train.json"
            _write_retain(eval_path)
            with self.assertRaisesRegex(ValueError, "evaluation marker"):
                projector.load_retain_training_data([eval_path], max_prompts=10)
            wrong_split = root / "retain_train.json"
            _write_retain(wrong_split, split="validation")
            with self.assertRaisesRegex(ValueError, "split"):
                projector.load_retain_training_data([wrong_split], max_prompts=10)

    def test_training_data_rejects_duplicate_json_ids_text_and_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate_key = root / "retain_train.json"
            duplicate_key.write_text(
                '{"schema_version":"x","schema_version":"y"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate key"):
                projector.load_retain_training_data(
                    [duplicate_key], max_prompts=10
                )
            duplicate_id = root / "retain_train_2.json"
            _write_retain(
                duplicate_id,
                prompts=[
                    {"id": "same", "text": "first"},
                    {"id": "same", "text": "second"},
                ],
            )
            with self.assertRaisesRegex(ValueError, "duplicate retain prompt id"):
                projector.load_retain_training_data([duplicate_id], max_prompts=10)
            duplicate_text = root / "retain_train_3.json"
            _write_retain(
                duplicate_text,
                prompts=[
                    {"id": "one", "text": "same"},
                    {"id": "two", "text": "same"},
                ],
            )
            with self.assertRaisesRegex(ValueError, "duplicate retain prompt text"):
                projector.load_retain_training_data([duplicate_text], max_prompts=10)

    def test_activation_sampling_is_deterministic_and_prompt_stratified(self):
        records = [
            {"id": "b", "input_ids": [4, 5, 6]},
            {"id": "a", "input_ids": [1, 2, 3]},
        ]
        first, first_info = projector.select_activation_token_positions(
            records, max_tokens=3, seed=7
        )
        second, second_info = projector.select_activation_token_positions(
            list(reversed(records)), max_tokens=3, seed=7
        )
        self.assertEqual(first, second)
        self.assertEqual(first_info, second_info)
        self.assertEqual({key[0] for key in first}, {"a", "b"})
        self.assertEqual(first_info["selected_token_count"], 3)
        self.assertEqual(
            first_info["sample_sha256"],
            projector.selection.payload_sha256(
                first_info["sampled_position_manifest"]
            ),
        )
        with self.assertRaisesRegex(ValueError, "at least the retain prompt count"):
            projector.select_activation_token_positions(
                records, max_tokens=1, seed=7
            )

    def test_tokenization_forbids_truncation_and_hashes_exact_ids(self):
        class Tokenizer:
            def apply_chat_template(self, messages, **kwargs):
                self.last = (messages, kwargs)
                return {"input_ids": [1, 2, 3, 4]}

        tokenizer = Tokenizer()
        tokenized, record = projector.tokenize_retain_prompts(
            [{"id": "a", "text": "hello"}], tokenizer, max_length=4
        )
        self.assertEqual(tokenized[0]["input_ids"], [1, 2, 3, 4])
        self.assertEqual(record["causal_nonpadding_token_count"], 4)
        self.assertTrue(tokenizer.last[1]["add_generation_prompt"])
        with self.assertRaisesRegex(ValueError, "truncation is forbidden"):
            projector.tokenize_retain_prompts(
                [{"id": "a", "text": "hello"}], tokenizer, max_length=3
            )

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

    def test_hooks_are_padding_and_batch_partition_invariant(self):
        model = self._ToyModel()
        tokenized = [
            {"id": "a", "input_ids": [1, 2, 3]},
            {"id": "b", "input_ids": [4]},
        ]
        ranks = {("a", 1): 0, ("b", 0): 1}
        first, _ = projector.collect_clean_module_inputs(
            model,
            {"a": model.a, "b": model.b},
            tokenized,
            ranks,
            pad_token_id=0,
            batch_size=1,
            torch=torch,
        )
        second, _ = projector.collect_clean_module_inputs(
            model,
            {"a": model.a, "b": model.b},
            tokenized,
            ranks,
            pad_token_id=0,
            batch_size=2,
            torch=torch,
        )
        for name in first:
            self.assertTrue(torch.equal(first[name], second[name]))
            self.assertEqual(first[name].shape[0], 2)
        self.assertFalse(model.a._forward_pre_hooks)
        self.assertFalse(model.b._forward_pre_hooks)

    def test_hooks_fail_on_missing_or_double_fire_and_are_removed(self):
        tokenized = [{"id": "a", "input_ids": [1]}]
        ranks = {("a", 0): 0}
        for model, pattern in (
            (self._ToyModel(omit=True), "did not fire"),
            (self._ToyModel(double=True), "more than once"),
        ):
            with self.subTest(pattern=pattern), self.assertRaisesRegex(RuntimeError, pattern):
                projector.collect_clean_module_inputs(
                    model,
                    {"a": model.a, "b": model.b},
                    tokenized,
                    ranks,
                    pad_token_id=0,
                    batch_size=1,
                    torch=torch,
                )
            self.assertFalse(model.a._forward_pre_hooks)
            self.assertFalse(model.b._forward_pre_hooks)

        width_model = self._ToyModel()
        width_model.a.in_features = 4
        with self.assertRaisesRegex(RuntimeError, "feature width"):
            projector.collect_clean_module_inputs(
                width_model,
                {"a": width_model.a, "b": width_model.b},
                tokenized,
                ranks,
                pad_token_id=0,
                batch_size=1,
                torch=torch,
            )
        self.assertFalse(width_model.a._forward_pre_hooks)
        self.assertFalse(width_model.b._forward_pre_hooks)

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
