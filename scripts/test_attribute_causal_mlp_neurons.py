import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

try:
    import torch
    import torch.nn.functional as functional
except ModuleNotFoundError:
    torch = None
    functional = None

try:
    from safetensors import safe_open
    from safetensors.torch import save_file as save_safetensors
except ModuleNotFoundError:
    safe_open = None
    save_safetensors = None

try:
    import attribute_causal_mlp_neurons as attribution
except ModuleNotFoundError:
    from scripts import attribute_causal_mlp_neurons as attribution


def fake_layer(width=8):
    return SimpleNamespace(
        mlp=SimpleNamespace(down_proj=SimpleNamespace(in_features=width))
    )


class AttributionRunnerPureTests(unittest.TestCase):
    def test_resolves_gemma_conditional_language_model_layers(self):
        layers = [fake_layer(), fake_layer()]
        model = SimpleNamespace(
            model=SimpleNamespace(language_model=SimpleNamespace(layers=layers))
        )
        resolved, path = attribution.resolve_decoder_layers(model)
        self.assertIs(resolved, layers)
        self.assertEqual(path, "model.language_model.layers")

    def test_rejects_ambiguous_decoder_surfaces(self):
        model = SimpleNamespace(
            model=SimpleNamespace(
                language_model=SimpleNamespace(layers=[fake_layer()]),
                layers=[fake_layer()],
            )
        )
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            attribution.resolve_decoder_layers(model)

    def test_pair_loader_accepts_prompt_and_multiturn_conventions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pairs.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a",
                            "category": "jobs",
                            "prompt": "What is employment?",
                            "answer": "Paid work.",
                        },
                        {
                            "id": "b",
                            "category": "jobs",
                            "messages": [
                                {"role": "user", "content": "First"},
                                {"role": "assistant", "content": "Answer"},
                                {"role": "user", "content": "Then?"},
                            ],
                            "answer": "Continuation.",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            records, sources = attribution.load_pair_files(
                [path], require_category=True
            )
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["messages"][0]["role"], "user")
        self.assertEqual(sources[0]["records"], 2)
        self.assertEqual(len(sources[0]["sha256"]), 64)

    def test_pair_loader_rejects_duplicates_and_missing_target_category(self):
        with tempfile.TemporaryDirectory() as directory:
            duplicate = Path(directory) / "duplicate.json"
            duplicate.write_text(
                json.dumps(
                    [
                        {"prompt": "same", "answer": "one", "category": "a"},
                        {"prompt": "same", "answer": "two", "category": "b"},
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate prompt"):
                attribution.load_pair_files([duplicate], require_category=True)
            missing = Path(directory) / "missing.json"
            missing.write_text(
                json.dumps([{"prompt": "p", "answer": "a"}]),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "category"):
                attribution.load_pair_files([missing], require_category=True)

    def test_cross_dataset_overlap_is_rejected(self):
        record = {"_identity_sha256": "a"}
        with self.assertRaisesRegex(ValueError, "overlap"):
            attribution.reject_cross_dataset_overlap([record], [record])

    def test_local_artifact_manifest_binds_selected_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.json").write_text("{}", encoding="utf-8")
            (root / "model.safetensors").write_bytes(b"weights")
            (root / "ignored.txt").write_text("ignore", encoding="utf-8")
            manifest = attribution.artifact_manifest(str(root))
        self.assertEqual(manifest["kind"], "local_directory")
        self.assertEqual(
            [record["path"] for record in manifest["files"]],
            ["config.json", "model.safetensors"],
        )
        self.assertEqual(len(manifest["manifest_sha256"]), 64)

    def test_exact_local_manifest_rejects_mutable_identifier(self):
        with self.assertRaisesRegex(ValueError, "exact existing local path"):
            attribution.require_local_artifact_manifest(
                "not/a/real/model", label="model"
            )

    def test_raw_archive_retry_reuses_only_identical_bytes(self):
        def fake_save(_tensors, path, metadata):
            Path(path).write_bytes(json.dumps(metadata, sort_keys=True).encode())

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "raw.safetensors"
            digest = attribution.write_raw_attribution_archive(
                destination,
                {"placeholder": object()},
                metadata={"schema": "test"},
                save_file=fake_save,
            )
            self.assertEqual(len(digest), 64)
            self.assertTrue(destination.is_file())
            self.assertFalse(any(path.name.startswith(".raw") for path in destination.parent.iterdir()))
            retried = attribution.write_raw_attribution_archive(
                destination,
                {"placeholder": object()},
                metadata={"schema": "test"},
                save_file=fake_save,
            )
            self.assertEqual(retried, digest)
            with self.assertRaisesRegex(FileExistsError, "differing"):
                attribution.write_raw_attribution_archive(
                    destination,
                    {"placeholder": object()},
                    metadata={"schema": "different"},
                    save_file=fake_save,
                )

    def test_raw_archive_publish_failure_leaves_no_partial_file(self):
        def fake_save(_tensors, path, metadata):
            Path(path).write_bytes(b"complete")

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "raw.safetensors"
            with mock.patch.object(
                attribution.os, "link", side_effect=OSError("injected link failure")
            ):
                with self.assertRaisesRegex(OSError, "injected"):
                    attribution.write_raw_attribution_archive(
                        destination,
                        {"placeholder": object()},
                        metadata={"schema": "test"},
                        save_file=fake_save,
                    )
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_verification_failure_prevents_json_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "mask.json"
            with mock.patch.object(
                attribution,
                "verify_raw_attribution_replay",
                side_effect=ValueError("injected verification failure"),
            ):
                with self.assertRaisesRegex(ValueError, "injected verification"):
                    attribution.write_verified_mask_artifact(
                        destination,
                        {"payload_sha256": "unused"},
                        Path(directory) / "raw.safetensors",
                        torch=object(),
                        safe_open=object(),
                    )
            self.assertFalse(destination.exists())


@unittest.skipIf(torch is None, "PyTorch is not installed in this environment")
class CausalAttributionAutogradTests(unittest.TestCase):
    def test_cpu_causal_lm_batches_shift_answer_masks_and_normalize_by_answer(self):
        class TinyTokenizer:
            pad_token_id = 0
            eos_token_id = 7

            def apply_chat_template(
                self,
                messages,
                *,
                add_generation_prompt,
                tokenize,
                return_dict,
            ):
                self.assert_template_flags = (
                    add_generation_prompt,
                    tokenize,
                    return_dict,
                )
                prompt = messages[-1]["content"]
                ids = [1, 2] if prompt == "short" else [1, 3, 4]
                return {"input_ids": ids}

            def __call__(self, text, *, add_special_tokens):
                if add_special_tokens:
                    raise AssertionError("answers must not add special tokens")
                return SimpleNamespace(input_ids=[5, 6] if text == "two" else [6])

        class TinyMLP(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.up_proj = torch.nn.Linear(2, 3, bias=False)
                self.down_proj = torch.nn.Linear(3, 2, bias=False)

            def forward(self, values):
                return self.down_proj(torch.tanh(self.up_proj(values)))

        class TinyLayer(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.mlp = TinyMLP()

            def forward(self, values):
                return values + self.mlp(values)

        class TinyBackbone(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.layers = torch.nn.ModuleList([TinyLayer()])

        class TinyCausalLM(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.embedding = torch.nn.Embedding(8, 2)
                self.model = TinyBackbone()
                self.lm_head = torch.nn.Linear(2, 8, bias=False)

            def get_input_embeddings(self):
                return self.embedding

            def forward(
                self,
                *,
                input_ids,
                attention_mask,
                use_cache,
                return_dict,
            ):
                del attention_mask, use_cache, return_dict
                hidden = self.embedding(input_ids)
                for layer in self.model.layers:
                    hidden = layer(hidden)
                # Every logit position depends only on the current and earlier
                # token states, which is enough to exercise all-causal support.
                hidden = hidden.cumsum(dim=1)
                return SimpleNamespace(logits=self.lm_head(hidden))

        torch.manual_seed(19)
        model = TinyCausalLM().eval()
        model.requires_grad_(False)
        tokenizer = TinyTokenizer()
        records = [
            {"messages": [{"role": "user", "content": "short"}], "answer": "two", "category": "a"},
            {"messages": [{"role": "user", "content": "long"}], "answer": "one", "category": "b"},
        ]

        answer = attribution._attribute_dataset(
            model,
            tokenizer,
            records,
            selected_layers=[0],
            layer_widths={0: 3},
            batch_size=2,
            max_length=8,
            append_eos=False,
            attribution_positions="answer",
            torch=torch,
            functional=functional,
        )
        self.assertEqual(answer.scored_answer_tokens_by_group, {"a": 2, "b": 1})
        self.assertEqual(answer.metadata()["attribution_positions_by_group"], {"a": 2, "b": 1})
        self.assertEqual(answer.groups["a"][0]["token_count"], 2)
        self.assertEqual(answer.groups["b"][0]["token_count"], 1)
        self.assertTrue(torch.isfinite(answer.groups["a"][0]["signed_sum"]).all())

        all_causal = attribution._attribute_dataset(
            model,
            tokenizer,
            records,
            selected_layers=[0],
            layer_widths={0: 3},
            batch_size=2,
            max_length=8,
            append_eos=False,
            attribution_positions="all-causal",
            torch=torch,
            functional=functional,
        )
        self.assertEqual(
            all_causal.metadata()["attribution_positions_by_group"],
            {"a": 3, "b": 3},
        )
        self.assertEqual(all_causal.groups["a"][0]["token_count"], 2)
        self.assertEqual(all_causal.groups["b"][0]["token_count"], 1)

    def test_float64_reduction_is_invariant_to_update_partition(self):
        values = torch.tensor(
            [[100000000.0], [1.0], [-100000000.0]], dtype=torch.float32
        )
        whole = attribution.AttributionAccumulator(torch, {0: 1})
        split = attribution.AttributionAccumulator(torch, {0: 1})
        whole.add("g", 0, values, normalization_tokens=3)
        split.add("g", 0, values[:1], normalization_tokens=1)
        split.add("g", 0, values[1:], normalization_tokens=2)
        self.assertEqual(float(whole.groups["g"][0]["signed_sum"][0]), 1.0)
        self.assertTrue(
            torch.equal(
                whole.groups["g"][0]["signed_sum"],
                split.groups["g"][0]["signed_sum"],
            )
        )
        self.assertTrue(
            torch.equal(
                whole.groups["g"][0]["absolute_sum"],
                split.groups["g"][0]["absolute_sum"],
            )
        )

    def test_all_causal_support_matches_column_scaling_finite_difference(self):
        class TinyGatedMLP(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.gate = torch.nn.Linear(2, 2, bias=False, dtype=torch.float64)
                self.up = torch.nn.Linear(2, 2, bias=False, dtype=torch.float64)
                self.down = torch.nn.Linear(2, 2, bias=False, dtype=torch.float64)
                with torch.no_grad():
                    self.gate.weight.copy_(torch.tensor(
                        [[1.0, 0.2], [-0.3, 0.8]], dtype=torch.float64
                    ))
                    self.up.weight.copy_(torch.tensor(
                        [[0.7, -0.4], [0.5, 1.1]], dtype=torch.float64
                    ))
                    self.down.weight.copy_(torch.tensor(
                        [[1.0, 0.5], [-0.6, 1.2]], dtype=torch.float64
                    ))

            def forward(self, values, column_scale):
                intermediate = functional.silu(self.gate(values)) * self.up(values)
                scale = torch.stack(
                    [
                        torch.ones_like(column_scale),
                        column_scale,
                    ]
                )
                writes = self.down(intermediate * scale)
                # The final answer logits depend causally on every earlier
                # position, mimicking residual writes carried forward by a LM.
                return writes.cumsum(dim=1)[:, -1, :]

        model = TinyGatedMLP()
        values = torch.tensor(
            [[[1.0, 0.5], [0.2, 1.0], [0.3, -0.4]]], dtype=torch.float64
        )
        captured = {}

        def hook(_module, inputs):
            inputs[0].retain_grad()
            captured["activation"] = inputs[0]

        handle = model.down.register_forward_pre_hook(hook)
        try:
            scale = torch.tensor(1.0, dtype=torch.float64)
            logits = model(values, scale)
            loss = functional.cross_entropy(logits, torch.tensor([0]))
            loss.backward()
        finally:
            handle.remove()

        activation = captured["activation"]
        all_positions = torch.ones((1, 3), dtype=torch.bool)
        answer_position_only = torch.tensor([[False, False, True]])
        all_support = attribution.causal_support_values(
            activation, activation.grad, all_positions
        )[0][:, 1].sum()
        answer_only_support = attribution.causal_support_values(
            activation, activation.grad, answer_position_only
        )[0][:, 1].sum()

        epsilon = 1e-5
        with torch.no_grad():
            lower = functional.cross_entropy(
                model(values, torch.tensor(1.0 - epsilon, dtype=torch.float64)),
                torch.tensor([0]),
            )
            upper = functional.cross_entropy(
                model(values, torch.tensor(1.0 + epsilon, dtype=torch.float64)),
                torch.tensor([0]),
            )
        finite_difference_ablation_support = (lower - upper) / (2 * epsilon)
        self.assertTrue(
            torch.allclose(
                all_support.double(),
                finite_difference_ablation_support,
                atol=1e-5,
                rtol=1e-4,
            )
        )
        self.assertFalse(
            torch.allclose(
                answer_only_support.double(),
                finite_difference_ablation_support,
                atol=1e-5,
                rtol=1e-4,
            )
        )

    def test_raw_tensor_archive_preserves_groups_and_float64_sums(self):
        target = attribution.AttributionAccumulator(torch, {2: 3})
        control = attribution.AttributionAccumulator(torch, {2: 3})
        target.note_records(["jobs"])
        target.note_scored_answer_tokens(["jobs"], [1])
        target.add(
            "jobs",
            2,
            torch.tensor([[1.0, -2.0, 3.0]]),
            normalization_tokens=1,
        )
        control.note_records(["polysemy"])
        control.note_scored_answer_tokens(["polysemy"], [2])
        control.add(
            "polysemy",
            2,
            torch.tensor([[0.5, 1.0, -1.5], [0.5, -1.0, 1.5]]),
            normalization_tokens=2,
        )
        tensors, groups, inventory = attribution.build_raw_attribution_tensors(
            target, control, [2], torch
        )
        self.assertEqual(len(tensors), 4)
        self.assertEqual(len(inventory), 4)
        self.assertIn("jobs", groups["target"])
        self.assertIn("polysemy", groups["control"])
        self.assertTrue(all(tensor.dtype is torch.float64 for tensor in tensors.values()))

    @unittest.skipIf(safe_open is None, "Safetensors is not installed")
    def test_real_safetensors_round_trip_replays_and_verifies_mask(self):
        target = attribution.AttributionAccumulator(torch, {2: 3})
        control = attribution.AttributionAccumulator(torch, {2: 3})
        for group, values in (
            ("job_meaning", [10.0, 1.0, -1.0]),
            ("job_usage", [8.0, 2.0, -2.0]),
        ):
            target.note_records([group])
            target.note_scored_answer_tokens([group], [1])
            target.add(
                group,
                2,
                torch.tensor([values]),
                normalization_tokens=1,
            )
        for group, values in (
            ("generic_retain", [1.0, 1.0, 0.1]),
            ("polysemy", [2.0, 1.0, 0.1]),
        ):
            control.note_records([group])
            control.note_scored_answer_tokens([group], [1])
            control.add(
                group,
                2,
                torch.tensor([values]),
                normalization_tokens=1,
            )

        policy = {
            "target_score": "equal_group_mean_positive_signed_ablation_support",
            "control_score": "maximum_group_mean_absolute_ablation_support",
            "target_control_ratio_threshold": 3.0,
            "min_sign_consistent_groups": 2,
            "global_top_k": 1,
            "per_layer_cap": 1,
            "min_target_score": 1e-6,
            "ratio_epsilon": 1e-12,
            "sign_epsilon": 1e-12,
            "attribution_positions": "all-causal",
            "normalization": "scored_answer_token_count",
            "rank_order": ["target_control_ratio_desc"],
        }
        selected, diagnostics = attribution.selection.select_causal_neurons(
            attribution._neuron_entries(target, control, [2]),
            ratio_threshold=policy["target_control_ratio_threshold"],
            min_sign_consistent_groups=policy["min_sign_consistent_groups"],
            top_k=policy["global_top_k"],
            per_layer_cap=policy["per_layer_cap"],
            min_target_score=policy["min_target_score"],
            ratio_epsilon=policy["ratio_epsilon"],
            sign_epsilon=policy["sign_epsilon"],
        )
        self.assertEqual([(row["layer"], row["neuron"]) for row in selected], [(2, 0)])
        selected[0].update(
            {
                "parameter_name": "model.layers.2.mlp.down_proj.weight",
                "source_column_sha256": "a" * 64,
            }
        )
        tensors, group_keys, inventory = attribution.build_raw_attribution_tensors(
            target, control, [2], torch
        )
        inventory_hash = attribution.selection.payload_sha256(inventory)
        attribution_hash = attribution.attribution_digest(target, control, [2])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_path = root / "raw.safetensors"
            raw_hash = attribution.write_raw_attribution_archive(
                raw_path,
                tensors,
                metadata={
                    "schema_version": attribution.selection.SCHEMA_VERSION,
                    "method": attribution.METHOD,
                    "attribution_digest_sha256": attribution_hash,
                    "tensor_inventory_sha256": inventory_hash,
                },
                save_file=save_safetensors,
            )
            selected_mask_hash = attribution.selection.payload_sha256(
                [
                    {
                        "layer": selected[0]["layer"],
                        "neuron": selected[0]["neuron"],
                        "dominant_sign": selected[0]["dominant_sign"],
                        "parameter_name": selected[0]["parameter_name"],
                        "source_column_sha256": selected[0]["source_column_sha256"],
                    }
                ]
            )
            payload = {
                "schema_version": attribution.selection.SCHEMA_VERSION,
                "method": attribution.METHOD,
                "attribution": {
                    "sha256": attribution_hash,
                    "target": target.metadata(),
                    "control": control.metadata(),
                    "raw_archive": {
                        "sha256": raw_hash,
                        "tensor_inventory": inventory,
                        "tensor_inventory_sha256": inventory_hash,
                        "group_tensor_prefixes": group_keys,
                    },
                },
                "model_surface": {"selected_layers": [2]},
                "selection_policy": policy,
                "selection_diagnostics": diagnostics,
                "selected_neurons": selected,
                "selected_mask_sha256": selected_mask_hash,
            }
            envelope = attribution.selection.immutable_envelope(payload)
            json_path = root / "mask.json"
            attribution.write_verified_mask_artifact(
                json_path,
                envelope,
                raw_path,
                torch=torch,
                safe_open=safe_open,
            )
            reloaded = json.loads(json_path.read_text(encoding="utf-8"))
            replayed, replay_diagnostics = attribution.verify_raw_attribution_replay(
                reloaded,
                raw_path,
                torch=torch,
                safe_open=safe_open,
            )

            bad_raw_path = root / "bad-digest.safetensors"
            bad_digest = "b" * 64
            bad_raw_hash = attribution.write_raw_attribution_archive(
                bad_raw_path,
                tensors,
                metadata={
                    "schema_version": attribution.selection.SCHEMA_VERSION,
                    "method": attribution.METHOD,
                    "attribution_digest_sha256": bad_digest,
                    "tensor_inventory_sha256": inventory_hash,
                },
                save_file=save_safetensors,
            )
            bad_payload = copy.deepcopy(payload)
            bad_payload["attribution"]["sha256"] = bad_digest
            bad_payload["attribution"]["raw_archive"]["sha256"] = bad_raw_hash
            bad_envelope = attribution.selection.immutable_envelope(bad_payload)
            with self.assertRaisesRegex(ValueError, "recomputed attribution digest"):
                attribution.verify_raw_attribution_replay(
                    bad_envelope,
                    bad_raw_path,
                    torch=torch,
                    safe_open=safe_open,
                )
        self.assertEqual(len(replayed), len(selected))
        for replayed_row, selected_row in zip(replayed, selected):
            for key, value in replayed_row.items():
                self.assertEqual(selected_row[key], value)
        self.assertEqual(
            selected[0]["parameter_name"],
            "model.layers.2.mlp.down_proj.weight",
        )
        self.assertEqual(selected[0]["source_column_sha256"], "a" * 64)
        self.assertEqual(replay_diagnostics, diagnostics)


if __name__ == "__main__":
    unittest.main()
