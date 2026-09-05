"""One CPU mechanism test using the actual trainer's AdamW construction."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

import torch


def trainer_optimizer(parameter, beta1):
    """Evaluate only the production optimizer expression, never import/run training."""
    source = Path(__file__).with_name('train_downproj_npo.py')
    tree = ast.parse(source.read_text(encoding='utf-8'))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)
             and ast.unparse(node.func) == 'torch.optim.AdamW']
    if len(calls) != 1:
        raise ValueError('Require one unambiguous production AdamW construction')
    expression = ast.fix_missing_locations(ast.Expression(body=calls[0]))
    return eval(compile(expression, str(source), 'eval'),
                {'torch': torch, 'parameters': [parameter], 'args': SimpleNamespace(adam_beta1=beta1)})


class MomentumTest(unittest.TestCase):
    def test_current_zero_gradient_retains_only_first_moment_update(self):
        observations = {}
        for beta1 in (.9, 0.):
            # FP64 scalar makes the independent bias-correction oracle precise;
            # native FP32/BF16 model behavior has separate existing scope tests.
            parameter = torch.nn.Parameter(torch.tensor(0., dtype=torch.float64))
            optimizer = trainer_optimizer(parameter, beta1)
            group = optimizer.param_groups[0]
            self.assertEqual(group['betas'], (beta1, .999))
            (parameter*1.).backward()
            self.assertEqual(float(parameter.grad), 1.)
            optimizer.step()
            first = float(parameter.detach())
            optimizer.zero_grad(set_to_none=True)
            (parameter*0.).backward()  # Zero tensor, not None: Adam must execute.
            self.assertEqual(float(parameter.grad), 0.)
            optimizer.step()
            second = float(parameter.detach())
            decay_only = first*(1-group['lr']*group['weight_decay'])
            adaptive_second = second-decay_only
            beta2 = .999
            corrected_m = beta1*(1-beta1)/(1-beta1**2) if beta1 else 0.
            corrected_v = beta2*(1-beta2)/(1-beta2**2)
            expected_adaptive = -group['lr']*corrected_m/(math.sqrt(corrected_v)+group['eps'])
            self.assertAlmostEqual(adaptive_second, expected_adaptive, delta=1e-15)
            if beta1:
                self.assertLess(adaptive_second, -1e-6)
                self.assertGreater(float(optimizer.state[parameter]['exp_avg']), 0.)
            else:
                self.assertAlmostEqual(adaptive_second, 0., delta=1e-18)
                self.assertEqual(float(optimizer.state[parameter]['exp_avg']), 0.)
            observations[beta1] = (first, adaptive_second)
        self.assertAlmostEqual(observations[.9][0], observations[0.][0], delta=1e-18)


if __name__ == '__main__':
    unittest.main()
