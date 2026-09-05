"""Focused checks for temporary prompt-vector interventions."""
import unittest

import torch
from torch import nn

from scripts.latent_recovery import PromptVectorHook, project_l2_


class TupleIdentity(nn.Module):
    def forward(self, hidden):
        return hidden, 'preserved-cache-marker'


class PromptVectorHookTests(unittest.TestCase):
    def test_zero_logits_and_context_restoration(self):
        torch.manual_seed(41)
        block = nn.Linear(4, 4, bias=False).requires_grad_(False)
        head = nn.Linear(4, 7, bias=False).requires_grad_(False)
        hidden = torch.randn(2, 5, 4)
        baseline = head(block(hidden)).detach()
        weights = block.weight.detach().clone()
        zero = torch.zeros(4, requires_grad=True)
        with PromptVectorHook(block, zero, [1, 3], 5) as hook:
            self.assertTrue(torch.equal(head(block(hidden)), baseline))
        self.assertEqual(hook.measurements[0]['effective_l2'], [0.0, 0.0])
        with self.assertRaisesRegex(RuntimeError, 'sentinel'):
            with PromptVectorHook(block, torch.ones(4), [1, 3], 5):
                self.assertFalse(torch.equal(head(block(hidden)), baseline))
                raise RuntimeError('sentinel')
        self.assertTrue(torch.equal(head(block(hidden)), baseline))
        self.assertTrue(torch.equal(block.weight, weights))
        self.assertEqual(len(block._forward_hooks), 0)

    def test_only_prompt_positions_and_prefill_once(self):
        block = TupleIdentity()
        hidden = torch.arange(40, dtype=torch.float32).reshape(2, 5, 4).to(torch.bfloat16)
        original = hidden.clone()
        vector = torch.tensor([0.125, -0.2, 0.5, 0.01], dtype=torch.float32)
        with PromptVectorHook(block, vector, [1, 3], 5, once=True) as hook:
            changed, marker = block(hidden)
            expected = original.clone()
            expected[0, 1] += vector.to(hidden.dtype)
            expected[1, 3] += vector.to(hidden.dtype)
            self.assertTrue(torch.equal(changed, expected))
            self.assertTrue(torch.equal(hidden, original))
            self.assertNotEqual(changed.data_ptr(), hidden.data_ptr())
            self.assertEqual(marker, 'preserved-cache-marker')
            decoded = torch.randn(2, 1, 4)
            self.assertIs(block(decoded)[0], decoded)
        self.assertEqual((hook.call_count, hook.injection_count), (2, 1))
        actual = torch.linalg.vector_norm((expected-original).double(), dim=-1)
        self.assertEqual(hook.measurements[0]['effective_l2'], [actual[0, 1].item(), actual[1, 3].item()])
        with self.assertRaises(ValueError):
            PromptVectorHook(block, vector, [-1, 3], 5)
        with self.assertRaises(ValueError):
            with PromptVectorHook(block, vector, [1], 5):
                block(hidden)
        self.assertEqual(len(block._forward_hooks), 0)

    def test_vector_gradient_frozen_model_and_projection(self):
        torch.manual_seed(42)
        block = nn.Linear(4, 4, bias=False).requires_grad_(False)
        head = nn.Linear(4, 3, bias=False).requires_grad_(False)
        hidden = torch.randn(2, 5, 4)
        vector = torch.zeros(4, requires_grad=True)
        with PromptVectorHook(block, vector, [1, 3], 5):
            logits = head(block(hidden))[[0, 1], [1, 3]]
            loss = torch.nn.functional.cross_entropy(logits, torch.tensor([0, 2]))
            loss.backward()
        self.assertTrue(bool(torch.isfinite(vector.grad).all()))
        self.assertGreater(float(vector.grad.norm()), 0)
        self.assertTrue(all(p.grad is None for p in list(block.parameters()) + list(head.parameters())))
        value = torch.tensor([3., 4.], requires_grad=True)
        self.assertIs(project_l2_(value, 2.), value)
        self.assertLessEqual(float(value.detach().double().norm()), 2. * (1 + 1e-6))
        self.assertTrue(torch.allclose(value, torch.tensor([1.2, 1.6])))
        project_l2_(value, 0.)
        self.assertEqual(float(value.detach().norm()), 0.)
        with self.assertRaises(ValueError):
            project_l2_(value, float('nan'))


if __name__ == '__main__':
    unittest.main()
