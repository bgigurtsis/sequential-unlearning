"""CPU-only numerical tests for the bounded JensUn losses."""

import math
import unittest

try:
    import torch
    import torch.nn.functional as F

    import train_bounded_forget
except ModuleNotFoundError:
    torch = None
    F = None
    train_bounded_forget = None


@unittest.skipIf(torch is None, "PyTorch is not installed in this environment")
class BoundedForgetMathTests(unittest.TestCase):
    def test_cyclic_one_hot_jsd_matches_explicit_distribution(self):
        torch.manual_seed(7)
        logits = torch.randn(2, 4, 11, requires_grad=True)
        mask = torch.tensor(
            [[1, 1, 1, 0], [1, 1, 0, 0]], dtype=torch.float32
        )
        pattern = [3, 8]

        actual = train_bounded_forget.jsd_to_cyclic_one_hot(
            logits, mask, pattern
        )
        selected = logits[mask.bool()]
        targets = train_bounded_forget.cyclic_target_ids(mask, pattern)
        p = F.softmax(selected, dim=-1)
        q = F.one_hot(targets, num_classes=selected.shape[-1]).float()
        midpoint = 0.5 * (p + q)
        explicit = 0.5 * (
            (p * (p.clamp_min(1e-30).log() - midpoint.log())).sum(dim=-1)
            + (q * (q.clamp_min(1e-30).log() - midpoint.log())).sum(dim=-1)
        ).mean()

        self.assertTrue(torch.allclose(actual, explicit, atol=1e-6, rtol=1e-6))
        actual.backward()
        self.assertTrue(torch.isfinite(logits.grad).all())
        actual_value = float(actual.detach())
        self.assertGreaterEqual(actual_value, 0.0)
        self.assertLessEqual(actual_value, math.log(2.0))

    def test_retain_jsd_is_zero_for_identical_logits(self):
        torch.manual_seed(11)
        logits = torch.randn(2, 5, 13, requires_grad=True)
        mask = torch.tensor(
            [[1, 1, 1, 1, 0], [1, 1, 1, 0, 0]], dtype=torch.float32
        )
        loss = train_bounded_forget.jsd_between_logits(logits, logits, mask)
        self.assertAlmostEqual(float(loss.detach()), 0.0, places=7)
        loss.backward()
        self.assertTrue(torch.isfinite(logits.grad).all())

    def test_cyclic_target_restarts_for_each_sequence(self):
        mask = torch.tensor([[1, 1, 1], [1, 1, 0]], dtype=torch.float32)
        targets = train_bounded_forget.cyclic_target_ids(mask, [4, 9])
        self.assertEqual(targets.tolist(), [4, 9, 4, 4, 9])


if __name__ == "__main__":
    unittest.main()
