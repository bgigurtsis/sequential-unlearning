import unittest
try:
    import native_read_oblique_math as math
except ModuleNotFoundError:
    from scripts import native_read_oblique_math as math
try:
    import torch
except ModuleNotFoundError:
    torch = None


@unittest.skipIf(torch is None, 'PyTorch unavailable')
class ObliqueTests(unittest.TestCase):
    def fixture(self):
        g = torch.Generator().manual_seed(33977)
        negative = torch.randn((2, 24), generator=g, dtype=torch.float64)
        positive = negative + torch.randn((2, 24), generator=g, dtype=torch.float64)
        return positive, negative

    def test_exact_constraints_and_independent_minimum_norm(self):
        positive, negative = self.fixture()
        for rank in (1, 2):
            c, right, record = math.fit_oblique(positive, negative, rank, torch=torch)
            t = torch.eye(24, dtype=torch.float64) - c @ right
            self.assertTrue(torch.allclose(t @ c, torch.zeros_like(c), atol=1e-12, rtol=0))
            self.assertTrue(torch.allclose(t @ negative.T, negative.T, atol=1e-12, rtol=1e-12))
            self.assertTrue(torch.allclose(t @ t, t, atol=1e-12, rtol=1e-12))
            # Independent dense least-norm solution to L[C,M]=[-C,0].
            a = torch.cat((c, negative.T), dim=1)
            b = torch.cat((-c, torch.zeros_like(negative.T)), dim=1)
            independent = b @ torch.linalg.pinv(a)
            self.assertTrue(torch.allclose(t - torch.eye(24), independent, atol=1e-12, rtol=1e-12))
            self.assertLess(record['negative_mean_relative_error'], 1e-10)

    def test_rank1_pooling_and_small_span_operator_norm(self):
        positive, negative = self.fixture()
        raw = (positive - negative).T
        c, right, record = math.fit_oblique(positive, negative, 1, torch=torch)
        self.assertTrue(torch.equal(c, (raw / raw.norm(dim=0)).mean(dim=1, keepdim=True)))
        dense = torch.eye(24, dtype=torch.float64) - c @ right
        self.assertAlmostEqual(record['operator_norm'], float(torch.linalg.svdvals(dense)[0]), places=12)
        # Extreme reciprocal rescaling must not change the map or its span.
        self.assertAlmostEqual(math.operator_norm(c * 1e-8, right * 1e8, torch=torch), record['operator_norm'], places=12)

    def test_absolute_rank_rejects_roundoff_and_pool_cancellation(self):
        negative = torch.eye(8, dtype=torch.float64)[:2]
        with self.assertRaises(ValueError):
            math.fit_oblique(2 * negative, negative, 1, torch=torch)
        with self.assertRaises(ValueError):
            math.fit_oblique(negative.clone(), negative, 2, torch=torch)
        positive = negative.clone(); positive[0, 2] += 1; positive[1, 2] -= 1
        with self.assertRaises(ValueError):
            math.fit_oblique(positive, negative, 1, torch=torch)

    def test_singular_ratio_and_operator_norm_guards(self):
        negative = torch.zeros((2, 8), dtype=torch.float64)
        negative[0, 0] = 1; negative[1, 1] = 1
        positive = negative.clone()
        positive[0, 2] += 1; positive[1, 2] += 1; positive[1, 3] += 1e-8
        with self.assertRaisesRegex(ValueError, 'singular-ratio'):
            math.fit_oblique(positive, negative, 2, torch=torch)
        positive = negative.clone(); positive[:, 0] += 1; positive[:, 2] += .01
        with self.assertRaisesRegex(ValueError, 'operator norm'):
            math.fit_oblique(positive, negative, 1, torch=torch)

    def test_malformed_inputs(self):
        positive, negative = self.fixture()
        for rank in (True, 1., 0, 3):
            with self.assertRaises(ValueError): math.fit_oblique(positive, negative, rank, torch=torch)
        for bad in (positive.float(), positive[:1], positive * float('nan')):
            with self.assertRaises(ValueError): math.fit_oblique(bad, negative, 1, torch=torch)

    def test_native_identity_signed_zero(self):
        weight = torch.tensor([[0., -0., 1., -1.]], dtype=torch.bfloat16)
        before = weight.view(torch.int16).clone()
        result, record = math.fold_weight(weight, torch.empty((4, 0), dtype=torch.float64),
                                          torch.empty((0, 4), dtype=torch.float64),
                                          torch.zeros((2, 4), dtype=torch.float64), torch=torch)
        self.assertTrue(torch.equal(result.view(torch.int16), before))
        self.assertTrue(torch.equal(weight.view(torch.int16), before))
        self.assertNotEqual(result.data_ptr(), weight.data_ptr())
        self.assertTrue(record['native_identity'])

    def fold_check(self, device):
        positive, negative = self.fixture()
        c, right, _ = math.fit_oblique(positive, negative, 2, torch=torch)
        g = torch.Generator().manual_seed(33978)
        weight = torch.randn((19, 24), generator=g).to(dtype=torch.bfloat16, device=device)
        original = weight.clone()
        result, record = math.fold_weight(weight, c, right, negative, torch=torch, row_chunk=7)
        reference = original.cpu().double() @ (torch.eye(24, dtype=torch.float64) - c @ right)
        error = float((result.cpu().double() - reference).norm())
        self.assertLess(error, .004 * float(reference.norm()))
        self.assertTrue(torch.equal(weight, original))
        self.assertEqual(result.device, weight.device)
        actual = float((result.cpu().double() @ c).norm()) / (float(original.double().norm()) * float(c.norm()))
        self.assertAlmostEqual(actual, record['native_weight_constraint_relative_to_weight_times_C'], places=12)
        self.assertGreater(actual, 0.)  # BF16 constraint is measured, not exact.
        self.assertLess(actual, .01)
        self.assertLess(record['precast_mean_output_relative_error'], 1e-5)

    def test_cpu_fold_independent_reference_and_actual_rounding(self):
        self.fold_check('cpu')

    @unittest.skipUnless(torch is not None and torch.cuda.is_available(), 'CUDA unavailable')
    def test_cuda_native_fold_same_device(self):
        old = torch.backends.cuda.matmul.allow_tf32
        torch.backends.cuda.matmul.allow_tf32 = False
        try: self.fold_check('cuda:0')
        finally: torch.backends.cuda.matmul.allow_tf32 = old

    def test_bad_factors_chunk_and_native_gate(self):
        positive, negative = self.fixture()
        c, right, _ = math.fit_oblique(positive, negative, 2, torch=torch)
        weight = torch.eye(24, dtype=torch.bfloat16)
        for bad in (0, True, 1.5):
            with self.assertRaises(ValueError): math.fold_weight(weight, c, right, negative, torch=torch, row_chunk=bad)
        with self.assertRaises(ValueError): math.fold_weight(weight.float(), c, right, negative, torch=torch)
        with self.assertRaises(ValueError): math.fold_weight(weight, c, right[:, :-1], negative, torch=torch)
        # Wrong right factor leaves full concept action; publication must fail.
        with self.assertRaisesRegex(RuntimeError, 'native weight contrast'):
            math.fold_weight(weight, c, torch.zeros_like(right), negative, torch=torch)


if __name__ == '__main__':
    unittest.main()
