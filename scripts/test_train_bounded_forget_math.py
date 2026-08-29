"""CPU-only numerical tests for the bounded JensUn losses."""

import math
import unittest

try:
    import torch
    import torch.nn.functional as F
except ModuleNotFoundError as error:
    if error.name != "torch":
        raise
    torch = None
    F = None
    train_bounded_forget = None
else:
    try:
        import train_bounded_forget
    except ModuleNotFoundError:
        from scripts import train_bounded_forget


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

    def test_answer_probability_matches_explicit_gather_and_is_bounded(self):
        torch.manual_seed(19)
        logits = torch.randn(2, 4, 11, requires_grad=True)
        labels = torch.tensor([[2, 5, 7, -100], [1, 9, -100, -100]])
        mask = (labels != -100).float()

        actual = train_bounded_forget.mean_selected_token_probability(
            logits, labels, mask
        )
        selected = logits[mask.bool()]
        targets = labels[mask.bool()]
        explicit = F.softmax(selected, dim=-1).gather(
            1, targets.unsqueeze(1)
        ).mean()

        self.assertTrue(torch.allclose(actual, explicit, atol=1e-7, rtol=1e-7))
        self.assertGreaterEqual(float(actual.detach()), 0.0)
        self.assertLessEqual(float(actual.detach()), 1.0)
        actual.backward()
        self.assertTrue(torch.isfinite(logits.grad).all())

    def test_selected_token_cross_entropy_matches_explicit_value(self):
        torch.manual_seed(21)
        logits = torch.randn(2, 4, 9, requires_grad=True)
        labels = torch.tensor([[2, 5, -100, -100], [1, 7, 4, -100]])
        mask = (labels != -100).float()
        actual = train_bounded_forget.selected_token_cross_entropy(
            logits, labels, mask
        )
        explicit = F.cross_entropy(logits[mask.bool()], labels[mask.bool()])
        self.assertTrue(torch.allclose(actual, explicit, atol=1e-7, rtol=1e-7))
        actual.backward()
        self.assertTrue(torch.isfinite(logits.grad).all())

    def test_elm_target_moves_from_expert_toward_novice(self):
        original = torch.tensor([[0.0, 0.0, 0.0], [0.2, -0.1, 0.0]])
        expert = torch.tensor([[3.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
        novice = torch.tensor([[0.0, 3.0, 0.0], [0.0, 2.0, 0.0]])
        target = train_bounded_forget.elm_guided_target(
            original,
            expert,
            novice,
            [2],
            eta=3.0,
            temperature=1.0,
            top_k=0,
        )

        self.assertEqual(tuple(target.shape), (2, 3))
        self.assertTrue(torch.allclose(target.sum(dim=-1), torch.ones(2)))
        self.assertGreater(float(target[0, 1]), float(target[0, 0]))
        self.assertGreater(float(target[1, 1]), float(target[1, 0]))
        self.assertGreater(float(target[1, 1]), float(target[0, 1]))

    def test_elm_target_temperature_and_top_k_match_official_rule(self):
        original = torch.tensor([[3.0, 2.0, 1.0, 0.0]])
        expert = torch.tensor([[2.0, 0.0, 1.0, -1.0]])
        novice = torch.tensor([[0.0, 2.0, 1.0, -1.0]])
        target = train_bounded_forget.elm_guided_target(
            original,
            expert,
            novice,
            [1],
            eta=2.0,
            temperature=2.0,
            top_k=2,
        )

        original_log_p = F.log_softmax(original / 2.0, dim=-1)
        expert_log_p = F.log_softmax(expert / 2.0, dim=-1)
        novice_log_p = F.log_softmax(novice / 2.0, dim=-1)
        guided = original_log_p + (novice_log_p - expert_log_p)
        threshold = torch.topk(guided, k=2, dim=-1).values[:, -1:]
        expected = F.softmax(guided.masked_fill(guided < threshold, -torch.inf), dim=-1)

        self.assertTrue(torch.allclose(target, expected, atol=1e-7, rtol=1e-7))
        # Match the official implementation's threshold behavior: exact ties
        # at the kth score survive, so the support can be slightly larger.
        self.assertGreaterEqual(int((target > 0).sum()), 2)
        self.assertEqual(
            int((target > 0).sum()), int((expected > 0).sum())
        )

    def test_soft_target_cross_entropy_matches_explicit_value(self):
        torch.manual_seed(23)
        logits = torch.randn(2, 3, 7, requires_grad=True)
        mask = torch.tensor([[1, 1, 0], [1, 0, 0]], dtype=torch.float32)
        selected = logits[mask.bool()]
        target = F.softmax(torch.randn_like(selected), dim=-1)
        actual = train_bounded_forget.soft_target_cross_entropy(
            logits, mask, target
        )
        explicit = -(target * F.log_softmax(selected, dim=-1)).sum(dim=-1).mean()
        self.assertTrue(torch.allclose(actual, explicit, atol=1e-6, rtol=1e-6))
        actual.backward()
        self.assertTrue(torch.isfinite(logits.grad).all())


if __name__ == "__main__":
    unittest.main()
