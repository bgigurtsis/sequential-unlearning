"""Focused formula, gradient, masking and pressure tests for clean NPO."""
import math
import unittest

import torch
from scripts.clean_npo import clean_npo_loss


class CleanNPOTests(unittest.TestCase):
    def setUp(self):
        self.labels = torch.tensor([[-100, 0, 1, 0], [-100, 1, -100, -100]])
        self.reference = torch.tensor([[[1., 0.], [0., 1.], [1., 0.], [2., -1.]],
                                       [[0., 1.], [2., -2.], [-1., 3.], [0., 0.]]])

    def test_python_formula_and_matching_initial_gradients(self):
        gradients = []
        for mode in ['sequence', 'token']:
            student = self.reference.clone().requires_grad_()
            loss, diag = clean_npo_loss(student, self.reference, self.labels, mode)
            expected = 20*math.log(2)*(1 if mode == 'sequence' else 2)
            self.assertAlmostEqual(float(loss.detach()), expected, places=5)
            self.assertTrue(torch.equal(diag['sequence_multipliers'], torch.ones(2)))
            self.assertTrue(torch.equal(diag['token_multiplier_mean'], torch.ones(2)))
            loss.backward(); gradients.append(student.grad)
        self.assertTrue(torch.equal(gradients[0], gradients[1]))
        changed = self.reference.clone(); changed[0, 0, 0] -= 1.5; changed[0, 1, 1] -= .4; changed[1, 0, 1] -= .8
        all_margins = []
        for row in range(2):
            margins = []
            for t in range(1, 4):
                target = int(self.labels[row, t])
                if target == -100: continue
                def nll(values):
                    values = values.tolist()
                    return math.log(sum(math.exp(x) for x in values))-values[target]
                margins.append(nll(changed[row,t-1])-nll(self.reference[row,t-1]))
            all_margins.append(margins)
        for mode in ['sequence', 'token']:
            expected = 0.
            for margins in all_margins:
                expected += sum(20*math.log1p(math.exp(-.1*x)) for x in ([sum(margins)] if mode == 'sequence' else margins))/2
            loss, _ = clean_npo_loss(changed, self.reference, self.labels, mode)
            self.assertAlmostEqual(float(loss), expected, places=5)

    def test_masks_unequal_lengths_and_saturation_mechanism(self):
        altered = self.reference.clone(); altered[0, 3] = torch.tensor([100., -100.]); altered[1, 1:] = torch.tensor([-100., 100.])
        for mode in ['sequence', 'token']:
            baseline, _ = clean_npo_loss(self.reference, self.reference, self.labels, mode)
            masked, _ = clean_npo_loss(altered, self.reference, self.labels, mode)
            self.assertTrue(torch.equal(baseline, masked))
        student = self.reference.clone()
        for t, target in [(0,0),(1,1),(2,0)]: student[0,t,target] -= 10
        for mode in ['sequence', 'token']:
            loss, diag = clean_npo_loss(student, self.reference, self.labels, mode)
            self.assertEqual(diag['supervised_tokens'].tolist(), [3,1])
            self.assertLess(float(diag['sequence_multipliers'][0]), float(diag['token_multiplier_min'][0]))
            self.assertEqual(float(diag['token_multiplier_mean'][1]), 1.)
            initial, _ = clean_npo_loss(self.reference, self.reference, self.labels, mode)
            self.assertLess(float(loss), float(initial))

    def test_student_only_gradients_and_invalid_inputs(self):
        for mode in ['sequence', 'token']:
            student = (self.reference + torch.tensor([.2,-.3])).requires_grad_()
            teacher = self.reference.clone().requires_grad_()
            loss, diag = clean_npo_loss(student, teacher, self.labels, mode); loss.backward()
            self.assertIsNone(teacher.grad)
            self.assertTrue(bool(torch.isfinite(student.grad).all()))
            self.assertGreater(float(student.grad.norm()), 0.)
            self.assertTrue(all(not v.requires_grad for v in diag.values()))
            self.assertTrue(torch.equal(student.grad[1,1:], torch.zeros(3,2)))
            for beta in [0, -1, float('nan'), float('inf'), True]:
                with self.assertRaises(ValueError): clean_npo_loss(student, teacher, self.labels, mode, beta)
            corrupted = self.reference.clone(); corrupted[0,0,0] = float('nan')
            with self.assertRaises(FloatingPointError): clean_npo_loss(corrupted, teacher, self.labels, mode)
        with self.assertRaises(ValueError): clean_npo_loss(self.reference, self.reference, self.labels, 'invalid')


if __name__ == '__main__': unittest.main()
