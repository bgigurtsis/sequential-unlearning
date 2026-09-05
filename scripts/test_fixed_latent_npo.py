"""Three numerical tests for fixed-vector unlearning loss helpers."""
import math
import unittest

import torch

from scripts.fixed_latent_npo import conditional_npo, ordinary_kl


class FixedLatentLossTests(unittest.TestCase):
    def setUp(self):
        self.labels = torch.tensor([[-100, 0, 1, 0], [-100, 1, -100, -100]])
        self.reference = torch.tensor([[[1., 0.], [0., 1.], [1., 0.], [2., -1.]],
                                       [[0., 1.], [2., -2.], [-1., 3.], [0., 0.]]])

    def test_npo_sum_formula_initial_margin_and_loss_direction(self):
        loss, margin, multiplier = conditional_npo(self.reference, self.reference, self.labels)
        self.assertTrue(torch.equal(margin, torch.zeros(2)))
        self.assertTrue(torch.equal(multiplier, torch.ones(2)))
        self.assertAlmostEqual(float(loss), 20. * math.log(2.), places=5)
        damaged = self.reference.clone()
        damaged[0, 0, 0] -= 1.5
        damaged[0, 1, 1] -= 0.4
        damaged[1, 0, 1] -= 0.8
        got, margins, multipliers = conditional_npo(damaged, self.reference, self.labels, beta=.2)
        expected = []
        for row in range(2):
            total = 0.
            for token in range(1, 4):
                target = int(self.labels[row, token])
                if target == -100:
                    continue
                def nll(logits):
                    values = logits[row, token-1].tolist()
                    return math.log(sum(math.exp(x) for x in values)) - values[target]
                total += nll(damaged) - nll(self.reference)
            expected.append(total)
        self.assertTrue(torch.allclose(margins, torch.tensor(expected), atol=1e-6))
        manual = sum(10. * math.log1p(math.exp(-.2*x)) for x in expected)/2
        self.assertAlmostEqual(float(got), manual, places=5)
        initial = conditional_npo(self.reference, self.reference, self.labels, beta=.2)[0]
        self.assertLess(float(got), float(initial))
        self.assertTrue(torch.all(multipliers < 1))

    def test_teacher_student_kl_direction_mask_and_unequal_lengths(self):
        teacher = torch.tensor([.8, .2]).log().repeat(2, 4, 1)
        student = torch.tensor([.3, .7]).log().repeat(2, 4, 1)
        expected_token = .8*math.log(.8/.3) + .2*math.log(.2/.7)
        got = ordinary_kl(student, teacher, self.labels)
        self.assertAlmostEqual(float(got), expected_token*(3+1)/2, places=6)
        reverse = .3*math.log(.3/.8) + .7*math.log(.7/.2)
        self.assertGreater(abs(float(got)-reverse*2), .01)
        altered = student.clone()
        altered[0, 3] = torch.tensor([50., -50.])
        altered[1, 1:] = torch.tensor([-50., 50.])
        self.assertTrue(torch.equal(got, ordinary_kl(altered, teacher, self.labels)))
        ragged = self.labels.clone();ragged[0, 1] = -100
        self.assertAlmostEqual(float(ordinary_kl(student, teacher, ragged)), expected_token*1.5, places=6)

    def test_student_only_gradients_and_nonfinite_guards(self):
        student = (self.reference + torch.tensor([.3, -.2])).requires_grad_()
        teacher = self.reference.clone().requires_grad_()
        loss, margins, multipliers = conditional_npo(student, teacher, self.labels)
        (loss + ordinary_kl(student, teacher, self.labels)).backward()
        self.assertTrue(bool(torch.isfinite(student.grad).all()))
        self.assertGreater(float(student.grad.norm()), 0.)
        self.assertIsNone(teacher.grad)
        self.assertFalse(margins.requires_grad or multipliers.requires_grad)
        self.assertTrue(torch.equal(student.grad[0, 3], torch.zeros(2)))
        self.assertTrue(torch.equal(student.grad[1, 1:], torch.zeros(3, 2)))
        for beta in [0, -1, float('nan'), float('inf'), True]:
            with self.assertRaises(ValueError):
                conditional_npo(student, teacher, self.labels, beta=beta)
        for value in [float('nan'), float('inf')]:
            corrupted = self.reference.clone();corrupted[0, 0, 0] = value
            with self.assertRaises(FloatingPointError):
                conditional_npo(corrupted, teacher, self.labels)
            with self.assertRaises(FloatingPointError):
                ordinary_kl(student, corrupted, self.labels)
        with self.assertRaises(ValueError):
            ordinary_kl(student, teacher, torch.full_like(self.labels, -100))


if __name__ == '__main__':
    unittest.main()
