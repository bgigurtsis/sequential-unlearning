"""CPU scope, precision/gradient, and native checkpoint tests; no loss retesting."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import torch
from transformers import PretrainedConfig
from safetensors.torch import load_file

try:
    import downproj_npo as helper
except ModuleNotFoundError:
    from scripts import downproj_npo as helper


class ToyMLP(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.gate_proj = torch.nn.Linear(4, 8, bias=False)
        self.up_proj = torch.nn.Linear(4, 8, bias=False)
        self.down_proj = torch.nn.Linear(8, 4, bias=False)

    def forward(self, x):
        return self.down_proj(torch.nn.functional.silu(self.gate_proj(x))*self.up_proj(x))


class ToyModel(torch.nn.Module):
    def __init__(self, seed=2468):
        super().__init__()
        torch.manual_seed(seed)
        self.config = PretrainedConfig(tie_word_embeddings=False)
        self.model = torch.nn.Module()
        self.model.language_model = torch.nn.Module()
        language = self.model.language_model
        language.embed_tokens = torch.nn.Embedding(13, 4)
        language.layers = torch.nn.ModuleList()
        for _ in range(34):
            block = torch.nn.Module()
            block.mlp = ToyMLP()
            language.layers.append(block)
        self.model.vision_tower = torch.nn.Linear(4, 4, bias=False)
        self.lm_head = torch.nn.Linear(4, 13, bias=False)
        self.to(torch.bfloat16)

    def get_input_embeddings(self):
        return self.model.language_model.embed_tokens

    def prepare_inputs_for_generation(self, input_ids, **kwargs):
        return {'input_ids': input_ids, **kwargs}

    def forward(self, input_ids=None, inputs_embeds=None, **kwargs):
        h = self.get_input_embeddings()(input_ids) if inputs_embeds is None else inputs_embeds
        for block in self.model.language_model.layers:
            h = h + .1*block.mlp(h)
        return SimpleNamespace(logits=self.lm_head(h))


def student(kind, clean=None):
    return helper.setup_student(copy.deepcopy(clean) if clean is not None else ToyModel(), kind,
                                expected_layers=34, expected_shape=(4, 8))


def batch():
    ids = torch.tensor([[1, 3, 5], [2, 4, 6]])
    return ids, torch.ones_like(ids)


class DownprojTests(unittest.TestCase):
    def test_exact_clean_autocast_and_parameter_scope(self):
        clean = ToyModel().eval().requires_grad_(False)
        expected = helper.autocast_forward(clean, batch())
        self.assertEqual(expected.dtype, torch.bfloat16)
        for kind, count in [('dense', 34), ('lora', 68)]:
            with self.subTest(kind=kind):
                model, receipt = student(kind, clean)
                actual = {n: p for n, p in model.named_parameters() if p.requires_grad}
                self.assertEqual(len(actual), count)
                self.assertEqual(set(actual), set(receipt['trainable_names']))
                self.assertTrue(all(p.dtype == torch.float32 for p in actual.values()))
                self.assertTrue(all('.mlp.down_proj' in n for n in actual))
                self.assertTrue(torch.equal(helper.autocast_forward(model, batch()), expected))
                for name, p in model.named_parameters():
                    if not p.requires_grad:
                        self.assertEqual(p.dtype, torch.bfloat16, name)
                if kind == 'dense':
                    name, p = next(iter(actual.items()))
                    original = p.detach().clone()
                    with torch.no_grad():
                        p.view(-1)[0].add_(1e-7)
                    self.assertFalse(torch.equal(p, original))
                    self.assertTrue(torch.equal(p.to(torch.bfloat16), original.to(torch.bfloat16)))
        malformed = ToyModel()
        del malformed.model.language_model.layers[-1]
        with self.assertRaises(ValueError):
            helper.setup_student(malformed, 'dense', expected_shape=(4, 8))

    def test_finite_actual_gradients_and_frozen_optimizer_scope(self):
        for kind, count in [('dense', 34), ('lora', 68)]:
            with self.subTest(kind=kind):
                model, _ = student(kind)
                trainable = {n: p for n, p in model.named_parameters() if p.requires_grad}
                frozen = {n: p.detach().clone() for n, p in model.named_parameters() if not p.requires_grad}
                optimizer = torch.optim.AdamW(trainable.values(), lr=1e-3, weight_decay=.01)
                for step in range(2):
                    optimizer.zero_grad(set_to_none=True)
                    helper.autocast_forward(model, batch()).float().square().mean().backward()
                    self.assertEqual(len(trainable), count)
                    self.assertTrue(all(p.grad is not None and p.grad.dtype == torch.float32 and torch.isfinite(p.grad).all() for p in trainable.values()))
                    for name, p in trainable.items():
                        if kind == 'lora' and '.lora_A.' in name and step == 0:
                            self.assertEqual(int(p.grad.count_nonzero()), 0)
                        else:
                            self.assertGreater(int(p.grad.count_nonzero()), 0, name)
                    optimizer.step()
                    self.assertTrue(all(torch.isfinite(p).all() for p in trainable.values()))
                    for name, p in model.named_parameters():
                        if name in frozen:
                            self.assertIsNone(p.grad)
                            self.assertTrue(torch.equal(p, frozen[name]), name)

    def test_native_dense34_and_lora68_save_identity_and_dense_binding(self):
        clean = ToyModel()
        with TemporaryDirectory() as temporary:
            for kind, count in [('dense', 34), ('lora', 68)]:
                with self.subTest(kind=kind):
                    model, setup = student(kind, clean)
                    with torch.no_grad():
                        for p in model.parameters():
                            if p.requires_grad:
                                p.add_(.001)
                    folder = Path(temporary)/kind
                    receipt = helper.save_checkpoint(model, folder, kind, setup['clean_downproj_binding'])
                    saved = load_file(str(folder/receipt['weight_file']))
                    self.assertEqual(len(saved), count)
                    expected = {n.replace('.default.weight', '.weight') if kind == 'lora' else n: p.detach()
                                for n, p in model.named_parameters() if p.requires_grad}
                    self.assertEqual(saved.keys(), expected.keys())
                    for name, value in saved.items():
                        self.assertEqual(value.dtype, torch.float32)
                        self.assertEqual(helper.tensor_sha(value), helper.tensor_sha(expected[name]))
                    self.assertTrue(receipt['native_fp32_reload_exact'])
                    if kind == 'dense':
                        restored, _ = student('dense', clean)
                        helper.load_dense_checkpoint(restored, folder)
                        self.assertTrue(torch.equal(helper.autocast_forward(restored, batch()), helper.autocast_forward(model, batch())))
                        wrong, _ = student('dense', ToyModel(seed=999))
                        with self.assertRaises(ValueError):
                            helper.load_dense_checkpoint(wrong, folder)
                        raw = (folder/receipt['weight_file']).read_bytes()
                        (folder/receipt['weight_file']).write_bytes(raw[:-1]+bytes([raw[-1]^1]))
                        with self.assertRaises(ValueError):
                            helper.load_dense_checkpoint(restored, folder)
                    else:
                        config = json.loads((folder/'adapter_config.json').read_text())
                        self.assertEqual((config['r'], config['lora_alpha']), (32, 64))


if __name__ == '__main__':
    unittest.main()
