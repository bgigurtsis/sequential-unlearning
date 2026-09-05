import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import constrain_checkpoint_projection as publisher
    import test_blend_checkpoint_projection as blend_fixture
    import test_project_checkpoint_delta_retain_subspace as capture_fixture
except ModuleNotFoundError:
    from scripts import constrain_checkpoint_projection as publisher
    from scripts import test_blend_checkpoint_projection as blend_fixture
    from scripts import test_project_checkpoint_delta_retain_subspace as capture_fixture

torch = blend_fixture.torch


class PromptSourceTests(unittest.TestCase):
    def test_actual_frozen_training_sources_are624unique_and_disjoint(self):
        records, proof = publisher.frozen_training_inputs(Path(__file__).resolve().parents[1])
        self.assertEqual(len(records), 624)
        self.assertEqual(proof["overlap"]["prompt_overlap_count"], 0)
        self.assertEqual(proof["overlap"]["history_overlap_count"], 0)
        self.assertEqual(len(proof["evaluation_sources"]), 7)

    def test_training_and_evaluation_pin_changes_fail_closed(self):
        repo = Path(__file__).resolve().parents[1]
        original = publisher.checked.sha256_file
        for suffix in ("semantic_scenarios_v1.json", "employment_sprint_20260904_final/probes.json"):
            with self.subTest(suffix=suffix):
                def replaced(path):
                    return "0" * 64 if Path(path).as_posix().endswith(suffix) else original(path)
                with mock.patch.object(publisher.checked, "sha256_file", side_effect=replaced), self.assertRaises(ValueError):
                    publisher.frozen_training_inputs(repo)

    def test_evaluation_overlap_is_rejected_before_capture(self):
        records = [{"messages": [{"role": "user", "content": "collision"}]}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "probes.json"
            path.write_text(json.dumps([{"prompt": "collision"}]))
            with self.assertRaisesRegex(ValueError, "overlap"):
                publisher.capture_tools.prove_zero_evaluation_overlap(records, [path])

    def test_prompt_last_selects_actual_final_token_without_answers_or_truncation(self):
        class Tokenizer:
            def apply_chat_template(self, messages, **kwargs):
                assert kwargs == {"add_generation_prompt": True, "tokenize": True, "return_dict": True}
                return {"input_ids": [int(x) for x in messages[0]["content"].split()]}
        records = [{"record_id": "a", "schema_family": "target", "messages": [{"role": "user", "content": "1 2 3"}]}]
        tokenized, proof = publisher.tokenize_prompt_last(records, Tokenizer())
        self.assertEqual(tokenized[0]["position_mask"], [False, False, True])
        self.assertEqual(proof["generated_or_teacher_forced_answer_tokens"], 0)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            publisher.tokenize_prompt_last(records, Tokenizer(), max_length=2)


@unittest.skipIf(torch is None, "PyTorch unavailable")
class CaptureTests(unittest.TestCase):
    def test_shared_capture_selects_last_prompt_not_padding_or_earlier_tokens(self):
        model = capture_fixture.TorchAlgebraAndCaptureTests._ToyModel()
        records = [{"record_id": "a", "input_ids": [1, 2, 3], "position_mask": [False, False, True]},
                   {"record_id": "b", "input_ids": [4], "position_mask": [True]}]
        groups = [{"basis_group": "g", "representative_module": "a", "modules": ["a", "b"]}]
        keys, proof = publisher.capture_tools.collect_clean_retain_keys(model, {"a": model.a, "b": model.b}, groups, records,
            pad_token_id=0, batch_size=2, torch=torch)
        expected = model.embedding.weight[[3, 4]].double()
        expected /= torch.linalg.vector_norm(expected, dim=1, keepdim=True)
        self.assertTrue(torch.equal(keys["g"], expected))
        self.assertTrue(proof["basis_groups"]["g"]["shared_input_equality_verified"])
        self.assertFalse(model.a._forward_pre_hooks)
        self.assertFalse(model.b._forward_pre_hooks)

    def test_immutable_target_cache_reuses_bound_keys_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            binding = {"kind": "test_donor_prompt_last", "source_sha256": "a" * 64}
            compute = mock.Mock(return_value={"keys": torch.eye(2, dtype=torch.float64)})
            value, first = publisher.capture_tools.immutable_tensor_cache(folder, binding, compute, torch=torch)
            second_value, second = publisher.capture_tools.immutable_tensor_cache(folder, binding, compute, torch=torch)
            self.assertEqual(compute.call_count, 1)
            self.assertTrue(second["hit"])
            self.assertTrue(torch.equal(value["keys"], second_value["keys"]))
            artifact = Path(first["path"]) / "payload.pt"
            artifact.write_bytes(artifact.read_bytes() + b"tampered")
            with self.assertRaisesRegex(RuntimeError, "hash mismatch"):
                publisher.capture_tools.immutable_tensor_cache(folder, binding, compute, torch=torch)


@unittest.skipIf(torch is None, "PyTorch/Safetensors unavailable")
class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.fixture = blend_fixture.PublicationTests()
        self.fixture.setUp()
        self.root = self.fixture.root

    def tearDown(self):
        self.fixture.tearDown()

    def apply(self, identity=False, **kwargs):
        fixture = self.fixture.fixture
        keys = {"fixture": torch.tensor([[1., 0., 0., 0.], [0., 1., 0., 0.]], dtype=torch.float64)}
        groups = {name: "fixture" for name in publisher.checked.DECLARED_EDIT_KEYS}
        with mock.patch.object(publisher, "collect_target_geometry", return_value=(keys, groups, {"fixture_capture": True})) as capture:
            output = publisher.apply_constrained(clean_model=fixture.clean, donor_model=fixture.edited,
                projected_model=self.fixture.projected, tokenizer_model=fixture.clean,
                output_dir=self.root / "out", cache_dir=self.root / "cache", identity=identity,
                runtime=fixture.runtime, device="cpu", strict_git=False, source_contract=fixture.contract,
                e90_weight_sha256=kwargs.pop("e90_weight_sha256", self.fixture.e90_sha),
                e90_payload_sha256=self.fixture.e90_payload,
                reload_verifier=fixture._reload_verifier,
                model_reload_verifier=kwargs.pop("model_reload_verifier", lambda root, runtime: {"verified": True, "fixture": True}), **kwargs)
            self.assertEqual(capture.call_count, 0 if identity else 1)
            return output

    def test_native_identity_copies_exact_files_and_skips_capture(self):
        output = self.apply(identity=True)
        self.assertEqual(output["output"]["weight_file_sha256"], self.fixture.fixture.contract.edited_mapping())
        self.assertTrue(output["target_capture"]["identity_skipped_capture"])
        self.assertEqual(len(output["tensors"]), 98)

    def test_full_publisher_protects_target_columns_and_noneditable_tensors(self):
        output = self.apply()
        state = blend_fixture.fixture.load_file(str(self.root / "out" / "model.safetensors"))
        projected = blend_fixture.fixture.load_file(str(self.fixture.projected / "model.safetensors"))
        for name, value in state.items():
            donor = self.fixture.donor_state[name]
            if name in publisher.checked.DECLARED_EDIT_KEYS:
                self.assertTrue(torch.equal(value[:, :2].view(torch.uint8), donor[:, :2].contiguous().view(torch.uint8)))
                self.assertTrue(torch.equal(value[:, 2:], projected[name][:, 2:]))
            else:
                self.assertTrue(torch.equal(value, donor))
        self.assertEqual(len(output["output"]["changed_from_clean_keys"]), 98)
        self.assertEqual(output["target_bases"]["fixture"]["basis_shape"], [4, 2])
        self.assertEqual(len(output["target_bases"]["fixture"]["basis_sha256"]), 64)
        self.assertEqual(publisher.checked.load_immutable_json(self.root / "out" / publisher.SIDECAR_NAME), output)

    def test_existing_output_is_never_replaced(self):
        (self.root / "out").mkdir()
        (self.root / "out" / "keep").write_text("unchanged")
        with self.assertRaises(FileExistsError):
            self.apply()
        self.assertEqual((self.root / "out" / "keep").read_text(), "unchanged")

    def test_wrong_endpoint_pin_prevents_capture_and_publication(self):
        with self.assertRaisesRegex(ValueError, "pinned E90"):
            self.apply(e90_weight_sha256="0" * 64)
        self.assertFalse((self.root / "out").exists())

    def test_failed_fresh_reload_keeps_output_unpublished(self):
        with self.assertRaisesRegex(RuntimeError, "fresh model reload"):
            self.apply(model_reload_verifier=lambda root, runtime: {"verified": False})
        self.assertFalse((self.root / "out").exists())
        self.assertEqual(list(self.root.glob(".out.tmp-*")), [])

    def test_output_sidecar_tampering_is_detected(self):
        self.apply()
        path = self.root / "out" / publisher.SIDECAR_NAME
        value = json.loads(path.read_text())
        value["request"]["identity"] = True
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            publisher.checked.load_immutable_json(path)


if __name__ == "__main__":
    unittest.main()
