import unittest

try:
    import constrain_projection_math as repair
except ModuleNotFoundError:
    from scripts import constrain_projection_math as repair
try:
    import torch
except ModuleNotFoundError:
    torch = None


@unittest.skipIf(torch is None, "PyTorch unavailable")
class BasisTests(unittest.TestCase):
    def test_duplicate_rank_deficient_keys_keep_full_span(self):
        keys = torch.tensor([[1., 0., 0.], [1., 0., 0.], [0., 1., 0.]], dtype=torch.float64)
        basis, record = repair.target_basis(keys, torch=torch)
        self.assertEqual(record["rank"], 2)
        self.assertTrue(torch.allclose(basis @ basis.T, torch.diag(torch.tensor([1., 1., 0.], dtype=torch.float64))))

    def test_small_but_resolvable_singular_direction_is_preserved(self):
        keys = torch.tensor([[1., 0., 0.], [1., 1e-7, 0.]], dtype=torch.float64)
        keys /= torch.linalg.vector_norm(keys, dim=1, keepdim=True)
        _, record = repair.target_basis(keys, torch=torch)
        self.assertEqual(record["rank"], 2)
        self.assertLess(record["span_relative_frobenius_error"], 1e-12)

    def test_bad_keys_rejected(self):
        for keys in (torch.zeros((2, 3), dtype=torch.float64), torch.ones((2, 3), dtype=torch.float64),
                     torch.eye(3), torch.tensor([[float('nan')]], dtype=torch.float64), torch.empty((0, 3), dtype=torch.float64)):
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                repair.target_basis(keys, torch=torch)


@unittest.skipIf(torch is None, "PyTorch unavailable")
class CorrectionTests(unittest.TestCase):
    def devices(self):
        return ["cpu"] + (["cuda:0"] if torch.cuda.is_available() else [])

    def test_analytic_target_columns_unchanged_and_unprotected_columns_repaired(self):
        donor = torch.tensor([[1., 2., 3.], [-2., -1., 4.]], dtype=torch.bfloat16)
        projected = donor + torch.tensor([[2., 3., 4.], [5., 6., 7.]], dtype=torch.bfloat16)
        keys = torch.tensor([[1., 0., 0.], [0., 1., 0.]], dtype=torch.float64)
        basis, _ = repair.target_basis(keys, torch=torch)
        for device in self.devices():
            out, record = repair.constrain_tensor(donor, projected, basis, keys, torch=torch, device=device, row_chunk=1)
            self.assertTrue(torch.equal(out[:, :2], donor[:, :2]))
            self.assertTrue(torch.equal(out[:, 2], projected[:, 2]))
            self.assertEqual(record['precast_target_key_action_l2'], 0)

    def test_oblique_constraint_matches_independent_float64_optimum(self):
        generator = torch.Generator().manual_seed(37219)
        keys = torch.randn((3, 9), generator=generator, dtype=torch.float64)
        keys /= torch.linalg.vector_norm(keys, dim=1, keepdim=True)
        basis, _ = repair.target_basis(keys, torch=torch)
        donor = torch.randn((11, 9), generator=generator).bfloat16()
        projected = (donor.float() + .01 * torch.randn((11, 9), generator=generator)).bfloat16()
        c0 = projected.double() - donor.double()
        # Direct dense projector is an independent small-matrix reference.
        optimum = c0 @ (torch.eye(9, dtype=torch.float64) - basis @ basis.T)
        expected = donor.double() + optimum
        for device in self.devices():
            for chunk in (1, 4, 128):
                out, record = repair.constrain_tensor(donor, projected, basis, keys, torch=torch, device=device, row_chunk=chunk)
                # Error bound includes BF16 rounding; no false bitwise GEMM claim.
                self.assertLess(float((out.double() - expected).abs().max()), .016)
                optimum_norm = float(torch.linalg.vector_norm(optimum))
                self.assertAlmostEqual(record['constrained_correction_l2'], optimum_norm,
                                       delta=max(optimum_norm * 1e-5, 1e-12))
                self.assertLess(record['precast_CQ_relative_to_C'], 1e-5)
                self.assertLess(record['pythagorean_relative_error'], 1e-5)
                self.assertFalse(record['postcast_exact_preservation_claimed'])
                actual = out.double() - donor.double()
                expected_actual_action = float(torch.linalg.vector_norm(actual @ keys.T))
                self.assertAlmostEqual(record['actual_target_key_action_l2'], expected_actual_action, delta=1e-7)

    def test_full_feature_span_forces_native_identity_including_signed_zero(self):
        donor = torch.tensor([[2**-40, -0., -2**-40]], dtype=torch.bfloat16)
        projected = torch.tensor([[1., 2., 3.]], dtype=torch.bfloat16)
        keys = torch.eye(3, dtype=torch.float64)
        basis, _ = repair.target_basis(keys, torch=torch)
        for device in self.devices():
            out, record = repair.constrain_tensor(donor, projected, basis, keys, torch=torch, device=device)
            self.assertTrue(torch.equal(out.view(torch.uint8), donor.view(torch.uint8)))
            self.assertEqual(record['constrained_correction_l2'], 0)

    def test_zero_endpoint_correction_is_exact_identity(self):
        donor = torch.tensor([[-0., 2**-40, -2**-40]], dtype=torch.bfloat16)
        keys = torch.tensor([[1., 0., 0.]], dtype=torch.float64)
        basis, _ = repair.target_basis(keys, torch=torch)
        for device in self.devices():
            out, _ = repair.constrain_tensor(donor, donor.clone(), basis, keys, torch=torch, device=device)
            self.assertTrue(torch.equal(out.view(torch.uint8), donor.view(torch.uint8)))

    def test_wrong_or_nonorthogonal_basis_rejected(self):
        donor = torch.ones((2, 3), dtype=torch.bfloat16)
        keys = torch.tensor([[1., 0., 0.]], dtype=torch.float64)
        for basis in (torch.tensor([[2.], [0.], [0.]], dtype=torch.float64),
                      torch.tensor([[0.], [1.], [0.]], dtype=torch.float64), torch.eye(2, dtype=torch.float64)):
            with self.assertRaises(ValueError):
                repair.constrain_tensor(donor, donor, basis, keys, torch=torch)

    def test_malformed_endpoints_and_chunk_rejected(self):
        donor = torch.ones((2, 3), dtype=torch.bfloat16)
        keys = torch.tensor([[1., 0., 0.]], dtype=torch.float64)
        basis, _ = repair.target_basis(keys, torch=torch)
        for bad in (donor.float(), donor.T, donor * float('inf')):
            with self.assertRaises(ValueError):
                repair.constrain_tensor(donor, bad, basis, keys, torch=torch)
        for chunk in (0, True, 1.2):
            with self.assertRaises(ValueError):
                repair.constrain_tensor(donor, donor, basis, keys, torch=torch, row_chunk=chunk)


if __name__ == '__main__':
    unittest.main()
