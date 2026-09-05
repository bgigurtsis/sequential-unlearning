import unittest

try:
    import native_residual_projection_math as project
except ModuleNotFoundError:
    from scripts import native_residual_projection_math as project
try:
    import torch
except ModuleNotFoundError:
    torch = None


@unittest.skipIf(torch is None, "PyTorch unavailable")
class NativeProjectionTests(unittest.TestCase):
    def setUp(self):
        self.generator = torch.Generator().manual_seed(33940)

    def devices(self):
        return ["cpu"] + (["cuda:0"] if torch.cuda.is_available() else [])

    def random(self, *shape):
        return torch.randn(shape, generator=self.generator, dtype=torch.float64)

    def basis(self, dimension=9, rank=2):
        return torch.linalg.qr(self.random(dimension, rank), mode="reduced")[0]

    def test_rank_deficient_svd_and_zero_span(self):
        columns = torch.tensor([[1., 2., 0.], [0., 0., 0.], [0., 0., 0.]], dtype=torch.float64)
        q, record = project.orthonormal_basis(columns, torch=torch)
        self.assertEqual(record['rank'], 1)
        self.assertLess(float((columns - q @ q.T @ columns).abs().max()), 1e-12)
        for zero in (torch.zeros(3, 2, dtype=torch.float64), torch.empty(3, 0, dtype=torch.float64)):
            q, record = project.orthonormal_basis(zero, torch=torch)
            self.assertEqual(tuple(q.shape), (3, 0))
            self.assertEqual(record['rank'], 0)

    def test_frozen_rank_tolerance_retains_resolvable_direction(self):
        columns = torch.diag(torch.tensor([1., 1e-8, 1e-16], dtype=torch.float64))
        _, record = project.orthonormal_basis(columns, torch=torch)
        self.assertEqual(record['rank'], 2)
        self.assertEqual(record['rank_tolerance'], 32 * torch.finfo(torch.float64).eps * 3)

    def test_closure_covers_final_norm_with_negative_and_zero_scales(self):
        u = self.basis()
        scale = torch.tensor([0., -2., 3., .001, 1., 4., -1., 2., 6.], dtype=torch.float64)
        v, record = project.closure_basis(u, scale, torch=torch)
        h = self.random(9, 7)
        h -= v @ v.T @ h
        self.assertLess(float((u.T @ h).abs().max()), 1e-12)
        self.assertLess(float((u.T @ (scale[:, None] * h)).abs().max()), 1e-12)
        self.assertLessEqual(record['rank'], 4)
        self.assertGreater(float((u.T @ (scale[:, None] * (torch.eye(9, dtype=torch.float64) - u @ u.T))).abs().max()), .01)

    def test_zero_scale_native_identity_preserves_tiny_signed_zero(self):
        weight = torch.tensor([[-0., 2**-40], [-2**-40, 0.], [1., -1.]], dtype=torch.bfloat16)
        for device in self.devices():
            out, record = project.project_write(weight, torch.zeros(3, dtype=torch.float64), self.basis(3, 2), torch=torch, device=device)
            self.assertTrue(torch.equal(out.view(torch.uint8), weight.view(torch.uint8)))
            self.assertTrue(record['native_identity'])

    def test_empty_basis_embedding_native_identity(self):
        weight = torch.tensor([[-0., 2**-40, -1.]], dtype=torch.bfloat16)
        for device in self.devices():
            out, record = project.project_embedding(weight, torch.empty(3, 0, dtype=torch.float64), torch=torch, device=device)
            self.assertTrue(torch.equal(out.view(torch.uint8), weight.view(torch.uint8)))
            self.assertTrue(record['native_identity'])

    def test_full_rank_annihilates_embedding_and_write(self):
        v = torch.eye(3, dtype=torch.float64)
        weight = self.random(3, 3).bfloat16()
        for device in self.devices():
            for out, record in (project.project_embedding(weight, v, torch=torch, device=device),
                                project.project_write(weight, torch.tensor([1., -2., 3.], dtype=torch.float64), v, torch=torch, device=device)):
                self.assertEqual(float(out.abs().max()), 0.)
                self.assertTrue(record['full_rank_annihilation'])
                self.assertEqual(record['ideal_projector_operator_norm'], 0.)

    def test_singular_scale_constraint_orientation(self):
        weight = torch.arange(12).reshape(3, 4).bfloat16()
        v = torch.tensor([[1.], [1.], [1.]], dtype=torch.float64) / 3**.5
        scale = torch.tensor([0., -2., 0.], dtype=torch.float64)
        for device in self.devices():
            out, record = project.project_write(weight, scale, v, torch=torch, device=device, column_chunk=1)
            self.assertTrue(torch.equal(out[[0, 2]], weight[[0, 2]]))
            self.assertEqual(float(out[1].abs().max()), 0.)
            self.assertEqual(record['rank'], 1)

    def test_write_matches_independent_float64_dense_minimum(self):
        weight = self.random(9, 13).bfloat16()
        v = self.basis()
        scale = torch.tensor([0., -2., 3., .001, 1., 4., -1., 2., 6.], dtype=torch.float64)
        a = scale[:, None] * v
        # Independent normal-equation expression, not the implementation's SVD.
        p = torch.eye(9, dtype=torch.float64) - a @ torch.linalg.solve(a.T @ a, a.T)
        optimum = p @ weight.double()
        feasible_perturbation = p @ self.random(9, 13)
        minimum = float(torch.linalg.vector_norm(optimum - weight.double()))
        self.assertGreaterEqual(float(torch.linalg.vector_norm(optimum + feasible_perturbation - weight.double())), minimum)
        for device in self.devices():
            for chunk in (1, 5, 128):
                out, record = project.project_write(weight, scale, v, torch=torch, device=device, column_chunk=chunk)
                self.assertLess(float((out.double() - optimum).abs().max()), .016)
                self.assertAlmostEqual(record['removed_l2'], minimum, delta=minimum*1e-5)
                self.assertAlmostEqual(record['precast_l2'], float(torch.linalg.vector_norm(optimum)), delta=1e-5)
                self.assertLess(record['pythagorean_relative_error'], 1e-5)

    def test_embedding_orientation_dense_reference_and_locality(self):
        weight = self.random(11, 9).bfloat16()
        original = weight.clone()
        v = self.basis()
        optimum = weight.double() @ (torch.eye(9, dtype=torch.float64) - v @ v.T)
        for device in self.devices():
            out, record = project.project_embedding(weight, v, torch=torch, device=device, row_chunk=3)
            self.assertLess(float((out.double() - optimum).abs().max()), .016)
            self.assertAlmostEqual(record['precast_l2'], float(torch.linalg.vector_norm(optimum)), delta=1e-5)
            self.assertTrue(torch.equal(weight, original))
            self.assertNotEqual(out.data_ptr(), weight.data_ptr())

    def test_bf16_constraint_reports_actual_nonzero_residual(self):
        weight = self.random(9, 13).bfloat16()
        v = self.basis()
        scale = self.random(9)
        for device in self.devices():
            out, record = project.project_write(weight, scale, v, torch=torch, device=device)
            actual = float(torch.linalg.vector_norm(v.T @ (scale[:, None] * out.double())))
            self.assertGreater(actual, 1e-5)
            self.assertAlmostEqual(record['native_constraint_l2'], actual, delta=1e-10)
            self.assertLess(record['precast_constraint_l2'], actual / 100)
            self.assertFalse(record['postcast_exact_preservation_claimed'])

    def test_orthogonal_projection_retained_and_operator_norms(self):
        v = self.basis()
        scale = self.random(9)
        a = scale[:, None] * v
        p = torch.eye(9, dtype=torch.float64) - a @ torch.linalg.solve(a.T @ a, a.T)
        weight = self.random(9, 13).bfloat16()
        self.assertLessEqual(float(torch.linalg.matrix_norm(p, ord=2)), 1 + 1e-12)
        self.assertLessEqual(float(torch.linalg.matrix_norm(p @ weight.double(), ord=2)), float(torch.linalg.matrix_norm(weight.double(), ord=2)) + 1e-12)
        _, record = project.project_write(weight, scale, v, torch=torch)
        self.assertLessEqual(record['precast_retained_norm_ratio'], 1 + 1e-6)
        self.assertEqual(record['ideal_projector_operator_norm'], 1.)

    def test_malformed_inputs_rejected(self):
        weight = self.random(9, 13).bfloat16()
        v, scale = self.basis(), self.random(9)
        for bad in (weight.float(), weight * float('nan'), weight[:0]):
            with self.subTest(kind='weight'), self.assertRaises(ValueError):
                project.project_write(bad, scale, v, torch=torch)
        for bad in (scale.float(), scale[:3], scale * float('inf')):
            with self.subTest(kind='scale'), self.assertRaises(ValueError):
                project.project_write(weight, bad, v, torch=torch)
        for bad in (v * 2, v.float(), v[:2]):
            with self.subTest(kind='basis'), self.assertRaises(ValueError):
                project.project_write(weight, scale, bad, torch=torch)
        for bad in (0, True, 1.2):
            with self.subTest(kind='chunk'), self.assertRaises(ValueError):
                project.project_write(weight, scale, v, torch=torch, column_chunk=bad)


if __name__ == '__main__':
    unittest.main()
