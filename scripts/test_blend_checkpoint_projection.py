import json
import shutil
import unittest
from pathlib import Path

try:
    import blend_checkpoint_projection as blend
    import test_apply_checkpoint_delta_dare as fixture
except ModuleNotFoundError:
    from scripts import blend_checkpoint_projection as blend
    from scripts import test_apply_checkpoint_delta_dare as fixture

torch = fixture.torch


class CoefficientTests(unittest.TestCase):
    def test_frozen_coefficients(self):
        self.assertEqual(tuple(blend.validate_beta(str(x)) for x in blend.BETAS), blend.BETAS)
        for value in (True, None, "nan", "inf", -0.1, 0.2, 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                blend.validate_beta(value)


@unittest.skipIf(torch is None, "PyTorch/Safetensors unavailable")
class TensorTests(unittest.TestCase):
    def devices(self):
        return ["cpu"] + (["cuda:0"] if torch.cuda.is_available() else [])

    def test_exact_endpoint_identity_including_tiny_and_signed_zero(self):
        left = torch.tensor([[2**-40, -0.0, -2**-40, 1.0]], dtype=torch.bfloat16)
        right = torch.tensor([[1.0, 0.0, -1.0, 2**-40]], dtype=torch.bfloat16)
        for device in self.devices():
            for beta, expected in ((0, left), (1, right)):
                with self.subTest(device=device, beta=beta):
                    result, _ = blend.blend_tensor(left, right, beta, torch=torch, device=device, chunk_elements=1)
                    self.assertTrue(torch.equal(result.view(torch.uint8), expected.view(torch.uint8)))

    def test_nonidentity_matches_ordered_fp32_and_chunk_device_invariance(self):
        gen = torch.Generator().manual_seed(93612)
        left = torch.randn((17, 19), generator=gen).bfloat16()
        right = torch.randn((17, 19), generator=gen).bfloat16()
        for beta in blend.BETAS[1:]:
            expected = (left.float() + beta * (right.float() - left.float())).bfloat16()
            for device in self.devices():
                for chunk in (1, 7, 1000):
                    with self.subTest(beta=beta, device=device, chunk=chunk):
                        result, _ = blend.blend_tensor(left, right, beta, torch=torch, device=device, chunk_elements=chunk)
                        self.assertTrue(torch.equal(result.view(torch.uint8), expected.view(torch.uint8)))

    def test_distance_from_donor_is_monotone_on_fixed_grid(self):
        gen = torch.Generator().manual_seed(174)
        left = torch.randn((99, 19), generator=gen).bfloat16()
        right = torch.randn((99, 19), generator=gen).bfloat16()
        for device in self.devices():
            distances = []
            for beta in blend.BETAS:
                result, _ = blend.blend_tensor(left, right, beta, torch=torch, device=device)
                distances.append(torch.linalg.vector_norm(result.float() - left.float()).item())
            self.assertEqual(distances, sorted(distances))
            self.assertEqual(distances[0], 0)

    def test_malformed_tensors_rejected_before_arithmetic(self):
        good = torch.ones((2, 3), dtype=torch.bfloat16)
        for bad in (torch.ones((3, 2), dtype=torch.bfloat16), good.float(), good.flatten(), good * float("nan")):
            with self.subTest(shape=bad.shape, dtype=bad.dtype), self.assertRaises(ValueError):
                blend.blend_tensor(good, bad, .5, torch=torch)


@unittest.skipIf(torch is None, "PyTorch/Safetensors unavailable")
class PublicationTests(unittest.TestCase):
    def setUp(self):
        # Reuse only the existing miniature endpoint fixture, not its test suite.
        self.fixture = fixture.RealTensorAndEndToEndTests()
        self.fixture.setUp()
        self.root = self.fixture.root
        self.projected = self.root / "projected"
        self.projected.mkdir()
        self.clean_state = self.fixture._clean_state()
        self.donor_state = fixture.load_file(str(self.fixture.edited / "model.safetensors"))
        projected_state = {}
        for key, value in self.donor_state.items():
            if key in blend.checked.DECLARED_EDIT_KEYS:
                projected_state[key] = (self.clean_state[key].float() + .75 * (value.float() - self.clean_state[key].float())).bfloat16()
            else:
                projected_state[key] = value.clone()
        fixture.save_file(projected_state, str(self.projected / "model.safetensors"))
        shutil.copyfile(self.fixture.edited / "config.json", self.projected / "config.json")
        self.e90_sha = blend.checked.sha256_file(self.projected / "model.safetensors")
        provenance = blend.checked.immutable_envelope({"fixture": "projected_endpoint", "weight_sha256": self.e90_sha})
        blend.checked.write_immutable_json(self.projected / blend.E90_SIDECAR_NAME, provenance)
        self.e90_payload = provenance["payload_sha256"]

    def tearDown(self):
        self.fixture.tearDown()

    def apply(self, beta=0.5, name="out", **kwargs):
        return blend.apply_blend(
            clean_model=self.fixture.clean, donor_model=self.fixture.edited,
            projected_model=self.projected, tokenizer_model=self.fixture.clean,
            output_dir=self.root / name, beta=beta, chunk_elements=3,
            runtime=self.fixture.runtime, strict_git=False, source_contract=self.fixture.contract,
            e90_weight_sha256=kwargs.pop("e90_weight_sha256", self.e90_sha),
            e90_payload_sha256=kwargs.pop("e90_payload_sha256", self.e90_payload),
            reload_verifier=self.fixture._reload_verifier,
            model_reload_verifier=kwargs.pop("model_reload_verifier", lambda root, runtime: {"verified": True, "fixture": True}),
            **kwargs)

    def test_beta_zero_file_and_native_tensor_identity(self):
        result = self.apply(beta=0)
        self.assertEqual(result["output"]["weight_file_sha256"], self.fixture.contract.edited_mapping())
        self.assertTrue(result["output"]["native_donor_identity"])
        self.assertEqual(len(result["tensors"]), 98)

    def test_blend_publication_preserves_every_noneditable_tensor(self):
        result = self.apply()
        values = fixture.load_file(str(self.root / "out" / "model.safetensors"))
        projected = fixture.load_file(str(self.projected / "model.safetensors"))
        for key, value in values.items():
            if key in blend.checked.DECLARED_EDIT_KEYS:
                expected = (self.donor_state[key].float() + .5 * (projected[key].float() - self.donor_state[key].float())).bfloat16()
            else:
                expected = self.clean_state[key]
            self.assertTrue(torch.equal(value.view(torch.uint8), expected.view(torch.uint8)), key)
        self.assertEqual(len(result["output"]["changed_from_clean_keys"]), 98)
        self.assertEqual(blend.checked.load_immutable_json(self.root / "out" / blend.SIDECAR_NAME), result)
        self.assertEqual((self.root / "out" / "tokenizer.json").read_bytes(), (self.fixture.clean / "tokenizer.json").read_bytes())

    def test_existing_output_never_overwritten(self):
        target = self.root / "out"
        target.mkdir()
        (target / "sentinel").write_text("keep")
        with self.assertRaises(FileExistsError):
            self.apply()
        self.assertEqual((target / "sentinel").read_text(), "keep")

    def test_wrong_endpoint_pin_rejected_without_publication(self):
        with self.assertRaisesRegex(ValueError, "pinned E90"):
            self.apply(e90_weight_sha256="0" * 64)
        self.assertFalse((self.root / "out").exists())

    def test_wrong_endpoint_provenance_pin_rejected(self):
        with self.assertRaisesRegex(ValueError, "pinned E90 payload"):
            self.apply(e90_payload_sha256="0" * 64)
        self.assertFalse((self.root / "out").exists())

    def test_unexpected_namespace_rejected_even_with_test_pin(self):
        values = fixture.load_file(str(self.projected / "model.safetensors"))
        key = blend.checked.DECLARED_EDIT_KEYS[0]
        values["prefix." + key] = values.pop(key)
        fixture.save_file(values, str(self.projected / "model.safetensors"))
        with self.assertRaisesRegex(ValueError, "canonical tensor keys differ"):
            self.apply(e90_weight_sha256=blend.checked.sha256_file(self.projected / "model.safetensors"))
        self.assertFalse((self.root / "out").exists())

    def test_noneditable_endpoint_mutation_rejected(self):
        values = fixture.load_file(str(self.projected / "model.safetensors"))
        key = "language_model.model.embed_tokens.weight"
        values[key] = values[key] + 1
        fixture.save_file(values, str(self.projected / "model.safetensors"))
        with self.assertRaisesRegex(ValueError, "98 linears"):
            self.apply(e90_weight_sha256=blend.checked.sha256_file(self.projected / "model.safetensors"))

    def test_failed_fresh_reload_removes_private_stage_and_never_publishes(self):
        with self.assertRaisesRegex(RuntimeError, "fresh model reload"):
            self.apply(model_reload_verifier=lambda root, runtime: {"verified": False})
        self.assertFalse((self.root / "out").exists())
        self.assertEqual(list(self.root.glob(".out.tmp-*")), [])

    def test_sidecar_detects_tampering(self):
        self.apply()
        path = self.root / "out" / blend.SIDECAR_NAME
        record = json.loads(path.read_text())
        record["request"]["beta"] = .75
        path.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            blend.checked.load_immutable_json(path)


if __name__ == "__main__":
    unittest.main()
