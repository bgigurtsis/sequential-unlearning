import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import torch

try:
    import retain_constrained_adam as rc
except ModuleNotFoundError:
    from scripts import retain_constrained_adam as rc


class Proposal:
    def __init__(self, p, delta):
        self.p, self.delta = p, delta
        self.calls = 0

    def step(self):
        self.calls += 1
        with torch.no_grad():
            self.p.add_(self.delta)


def project(delta, rows, mode="separate", initial=None):
    delta = torch.tensor(delta, dtype=torch.float32)
    p = torch.nn.Parameter(torch.zeros_like(delta) if initial is None else initial.clone())
    before = p.detach().clone()
    p.grad = torch.ones_like(p)
    gradients = [(torch.tensor(row, dtype=torch.float32),) for row in rows]
    while len(gradients) < 3:
        gradients.append((torch.zeros_like(p),))
    receipt = rc.constrained_adam_step(Proposal(p, delta), [("lora.weight", p)], gradients, mode=mode, torch=torch)
    return p.detach() - before, receipt


class RetainConstrainedAdamTests(unittest.TestCase):
    def test_external_closed_form_oracle(self):
        fixture = Path(__file__).resolve().parents[1] / "config/whole_concept_jobs_v1/wide_unfamiliarity_v1/retain_constrained_adam_v1/analytic_fixtures_v1.json"
        for case in json.loads(fixture.read_text())["cases"]:
            with self.subTest(case=case["name"]):
                actual, receipt = project(case["delta"], case["gradients"])
                torch.testing.assert_close(actual.double(), torch.tensor(case["expected"], dtype=torch.float64), atol=2e-7, rtol=2e-7)
                self.assertLessEqual(receipt["stored_delta_norm"], receipt["proposal_norm"] + receipt["feasibility_bound"])

    def test_permutation_positive_scaling_and_tiny_gradients(self):
        reference, _ = project([1, 2], [[1, 0], [1, 1]])
        for rows in ([[1e-30, 1e-30], [9, 0]], [[1, 0], [7, 7]], [[1e-30, 0], [1e-30, 1e-30]]):
            actual, _ = project([1, 2], rows)
            torch.testing.assert_close(actual, reference, atol=2e-7, rtol=2e-7)

    def test_aggregate_cancellation_differs_from_separate(self):
        separate, _ = project([1, -2], [[1, 0], [0, 1]])
        aggregate, _ = project([1, -2], [[1, 0], [0, 1]], mode="aggregate")
        torch.testing.assert_close(separate, torch.tensor([0., -2.]))
        torch.testing.assert_close(aggregate, torch.tensor([1., -2.]))

    def test_solver_rejects_malformed_and_checks_kkt(self):
        for gram, b in [([[1, 1], [0, 1]], [1, 2]), ([[-1]], [1]), ([[float("nan")]], [1]), (torch.eye(4), [1]*4)]:
            with self.assertRaises(ValueError):
                rc.solve_halfspaces(gram, b, torch=torch)
        lam, receipt = rc.solve_halfspaces([[1., -1.], [-1., 1.]], [3., -3.], torch=torch)
        self.assertTrue(all(x >= 0 for x in lam))
        self.assertTrue(all(x <= 1e-10 for x in receipt["ideal_normalized_post_dots"]))

    def test_adam_preconditioning_momentum_decay_and_state_preserved(self):
        p = torch.nn.Parameter(torch.tensor([.3, -.2]))
        q = torch.nn.Parameter(p.detach().clone())
        a = torch.optim.AdamW([p], lr=.01, weight_decay=.1)
        b = torch.optim.AdamW([q], lr=.01, weight_decay=.1)
        # Populate deliberately anisotropic moments, then use a retention-safe
        # raw descent direction whose actual Adam proposal violates retention.
        for parameter, opt in [(p, a), (q, b)]:
            opt.state[parameter] = {"step": torch.tensor(10.), "exp_avg": torch.tensor([-.1, .2]), "exp_avg_sq": torch.tensor([.0001, 100.])}
            parameter.grad = torch.tensor([-1., 2.])
        before = p.detach().clone()
        gradient = torch.tensor([1., 1.])
        self.assertLess(float(gradient @ -p.grad), 0)
        b.step()
        self.assertGreater(float(gradient @ (q.detach() - before)), 0)
        receipt = rc.constrained_adam_step(a, [("lora.weight", p)], [(gradient,), (torch.zeros(2),), (torch.zeros(2),)], mode="separate", torch=torch)
        self.assertLessEqual(receipt["normalized_stored_post_dots"][0], receipt["feasibility_bound"])
        for name in ("step", "exp_avg", "exp_avg_sq"):
            self.assertTrue(torch.equal(a.state[p][name], b.state[q][name]))
        self.assertFalse(torch.equal(p, q))

    def test_none_exact_legacy_adam_weights_moments_and_rng(self):
        p = torch.nn.Parameter(torch.tensor([0., -0., 1e-30, 2.]))
        q = torch.nn.Parameter(p.detach().clone())
        a, b = torch.optim.AdamW([p], lr=.01), torch.optim.AdamW([q], lr=.01)
        rng = torch.random.get_rng_state().clone()
        for _ in range(3):
            p.grad = torch.tensor([0., 0., 1e-20, .3])
            q.grad = p.grad.clone()
            self.assertIsNone(rc.constrained_adam_step(a, [("x", p)], None, mode="none", torch=torch))
            b.step()
            self.assertTrue(torch.equal(p.view(torch.int32), q.view(torch.int32)))
            for key in a.state[p]:
                self.assertTrue(torch.equal(a.state[p][key], b.state[q][key]))
        self.assertTrue(torch.equal(rng, torch.random.get_rng_state()))

    def test_component_autograd_leaves_grad_and_rng_untouched(self):
        p = torch.nn.Parameter(torch.tensor([.2, -.4]))
        losses = [30 * p.square().sum(), 100 * p.sin().sum(), 10 * p.exp().sum()]
        p.grad = torch.tensor([7., 9.])
        rng = torch.random.get_rng_state().clone()
        components = rc.preservation_gradients(losses, [p], torch=torch)
        self.assertTrue(torch.equal(p.grad, torch.tensor([7., 9.])))
        self.assertTrue(torch.equal(rng, torch.random.get_rng_state()))
        expected = [60*p.detach(), 100*p.detach().cos(), 10*p.detach().exp()]
        for actual, target in zip(components, expected):
            torch.testing.assert_close(actual[0], target)

    def test_stored_rounding_is_reported_and_checked(self):
        actual, receipt = project([.19, -.03], [[1., 1.]], initial=torch.tensor([10000., 10000.]))
        self.assertAlmostEqual(float(torch.linalg.vector_norm(actual.double())), receipt["stored_delta_norm"], places=12)
        self.assertAlmostEqual(float(actual.double().sum()) / 2**.5, receipt["normalized_stored_post_dots"][0], places=12)

    def test_failed_stored_projection_rolls_back_and_no_silent_fallback(self):
        p = torch.nn.Parameter(torch.tensor([1., 2.]))
        p.grad = torch.ones(2)
        before = p.detach().clone()
        optimizer = Proposal(p, torch.tensor([1., 0.]))
        gradients = [(torch.tensor([1., 0.]),), (torch.zeros(2),), (torch.zeros(2),)]
        with patch.object(rc, "solve_halfspaces", return_value=([0.0], {})):
            with self.assertRaisesRegex(FloatingPointError, "infeasible"):
                rc.constrained_adam_step(optimizer, [("lora.weight", p)], gradients, mode="separate", torch=torch)
        self.assertTrue(torch.equal(p, before))
        self.assertEqual(optimizer.calls, 1)

    def test_feasible_signed_zero_and_subnormal_proposal_exact(self):
        p = torch.nn.Parameter(torch.tensor([-0., 0., 1e-40]))
        p.grad = torch.zeros_like(p)
        class NoOp:
            def step(self):
                pass
        before = p.detach().view(torch.int32).clone()
        rc.constrained_adam_step(NoOp(), [("lora.weight", p)], [(torch.zeros_like(p),)]*3, mode="separate", torch=torch)
        self.assertTrue(torch.equal(before, p.detach().view(torch.int32)))


if __name__ == "__main__":
    unittest.main()
