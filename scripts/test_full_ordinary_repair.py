"""Independent mask and objective checks for full ordinary-response repair."""
import math
import unittest

import torch

from scripts.full_ordinary_repair import encode_ordinary, ordinary_loss


class Tokenizer:
    eos_token_id = 1

    def apply_chat_template(self, *args, **kwargs):
        return [2, 105, 19, 106, 105]

    def encode(self, text, **kwargs):
        if not text:
            return []
        return [20, 21, 22] if text == 'A useful reply.' else [20] * 260


class FullOrdinaryTests(unittest.TestCase):
    def test_entire_answer_and_terminator_supervised_prompt_masked(self):
        row = encode_ordinary(Tokenizer(), {
            'id': 'ordinary', 'role': 'ordinary_repair',
            'prompt': 'An ordinary question', 'target_response': 'A useful reply.',
        })
        self.assertEqual(row['ids'], [2, 105, 19, 106, 105, 20, 21, 22, 1])
        self.assertEqual(row['labels'], [-100] * 5 + [20, 21, 22, 1])
        self.assertEqual(len(row['encoding_sha256']), 64)

    def test_ordinary_answer_cannot_be_silently_clipped(self):
        with self.assertRaises(ValueError):
            encode_ordinary(Tokenizer(), {
                'id': 'ordinary', 'role': 'ordinary_repair',
                'prompt': 'An ordinary question', 'target_response': 'Overlong answer',
            })

    def test_ce_causal_alignment_prefix_weight_and_padding_gradient(self):
        # Six supervised causal targets, then padding. The first five have
        # weight8; the last has weight1. Denominator is6, not total weight41.
        labels = torch.tensor([[-100, 0, 0, 0, 0, 0, 1, -100]])
        logits = torch.tensor([[[math.log(.8), math.log(.2)]] * 8],
                              dtype=torch.float64, requires_grad=True)
        loss = ordinary_loss(logits, labels, 'ce')
        expected = (40 * -math.log(.8) - math.log(.2)) / 6
        self.assertAlmostEqual(float(loss.detach()), expected, places=5)
        loss.backward()
        self.assertGreater(float(logits.grad[:, :6].abs().sum()), 0)
        self.assertEqual(float(logits.grad[:, 6:].abs().sum()), 0)

    def test_jsd_uses_clean_reference_and_keeps_it_detached(self):
        labels = torch.tensor([[-100, 0, 1, -100]])
        student = torch.tensor([[[2., -1.]] * 4], requires_grad=True)
        teacher = torch.tensor([[[-1., 2.]] * 4], requires_grad=True)
        loss = ordinary_loss(student, labels, 'jsd', teacher)
        self.assertGreater(float(loss.detach()), 0)
        loss.backward()
        self.assertIsNone(teacher.grad)
        self.assertGreater(float(student.grad[:, :2].abs().sum()), 0)
        self.assertEqual(float(student.grad[:, 2:].abs().sum()), 0)
        equal = ordinary_loss(teacher.detach(), labels, 'jsd', teacher.detach())
        self.assertLess(abs(float(equal)), 1e-6)


if __name__ == '__main__':
    unittest.main()
