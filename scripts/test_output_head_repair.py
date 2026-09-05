"""Small real-PEFT integration checks, with the production238-module topology."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import torch
from torch import nn
from transformers import PretrainedConfig, PreTrainedModel
from transformers.modeling_outputs import CausalLMOutput
from peft import LoraConfig, PeftModel, get_peft_model, get_peft_model_state_dict
from safetensors.torch import load_file, save_file

from scripts.output_head_repair import load_parent_with_head, assert_frozen_parent, save_head_adapter
from scripts.wide_unfamiliarity_training import text_only_fullband_modules


class ToyConfig(PretrainedConfig):
    model_type = 'output_head_fixture'

    def __init__(self, **kwargs):
        kwargs.pop('tie_word_embeddings', None)
        super().__init__(tie_word_embeddings=True, **kwargs)
        self.hidden_size = 4
        self.vocab_size = 17


class Block(nn.Module):
    def __init__(self):
        super().__init__()
        self.self_attn = nn.ModuleDict({n: nn.Linear(4, 4, bias=False)
                                      for n in ['q_proj', 'k_proj', 'v_proj', 'o_proj']})
        self.mlp = nn.ModuleDict({n: nn.Linear(4, 4, bias=False)
                                 for n in ['gate_proj', 'up_proj', 'down_proj']})

    def forward(self, x):
        return x + sum(p(x) for p in list(self.self_attn.values()) + list(self.mlp.values())) / 100


class ToyCausalLM(PreTrainedModel):
    config_class = ToyConfig
    _tied_weights_keys = {'lm_head.weight': 'model.language_model.embed_tokens.weight'}

    def __init__(self, config=None):
        super().__init__(config or ToyConfig())
        self.model = nn.Module()
        self.model.language_model = nn.Module()
        self.model.language_model.embed_tokens = nn.Embedding(17, 4)
        self.model.language_model.layers = nn.ModuleList([Block() for _ in range(34)])
        self.lm_head = nn.Linear(4, 17, bias=False)
        self.lm_head.weight = self.model.language_model.embed_tokens.weight

    def get_input_embeddings(self):
        return self.model.language_model.embed_tokens

    def get_output_embeddings(self):
        return self.lm_head

    def prepare_inputs_for_generation(self, input_ids, **kwargs):
        return {'input_ids': input_ids}

    def forward(self, input_ids=None, inputs_embeds=None, **kwargs):
        x = self.get_input_embeddings()(input_ids) if inputs_embeds is None else inputs_embeds
        for layer in self.model.language_model.layers:
            x = layer(x)
        return CausalLMOutput(logits=self.lm_head(x))


class OutputHeadRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.parent_path = Path(self.tmp.name) / 'parent'
        torch.manual_seed(124)
        base = ToyCausalLM()
        self.base_state = copy.deepcopy(base.state_dict())
        modules = text_only_fullband_modules(base.named_modules())
        parent = get_peft_model(base, LoraConfig(r=32, lora_alpha=64,
            target_modules=modules, lora_dropout=0, bias='none', task_type='CAUSAL_LM'))
        with torch.no_grad():
            for name, p in parent.named_parameters():
                if '.lora_B.' in name:
                    p.normal_(std=.01)
        self.ids = torch.tensor([[2, 3, 4], [5, 6, 7]])
        self.reference = parent.eval()(input_ids=self.ids).logits.detach().clone()
        parent.save_pretrained(self.parent_path, safe_serialization=True, save_embedding_layers=False)

    def clean(self):
        base = ToyCausalLM()
        base.load_state_dict(self.base_state)
        return base

    def test_rank8_and32_zero_delta_and_exact_native_parent(self):
        for rank in (8, 32):
            with self.subTest(rank=rank):
                model, receipt = load_parent_with_head(self.clean(), self.parent_path, rank)
                self.assertTrue(receipt['initial_head_B_zero'])
                self.assertEqual(receipt['serialized_factor_count'], 478)
                self.assertEqual(len([p for p in model.parameters() if p.requires_grad]), 2)
                torch.testing.assert_close(model.eval()(input_ids=self.ids).logits,
                                           self.reference, atol=0, rtol=0)
                self.assertIs(model.get_input_embeddings().weight, model.get_output_embeddings().weight)

    def test_only_head_gradients_update_embedding_and_text_unchanged(self):
        model, _ = load_parent_with_head(self.clean(), self.parent_path, 8)
        trainable = [p for p in model.parameters() if p.requires_grad]
        optimizer = torch.optim.AdamW(trainable, lr=.01)
        for _ in range(2):
            optimizer.zero_grad(set_to_none=True)
            loss = model(input_ids=self.ids).logits.square().mean()
            loss.backward()
            self.assertEqual(sum(p.grad is not None for p in model.parameters()), 2)
            self.assertTrue(all(bool(torch.isfinite(p.grad).all()) for p in trainable))
            optimizer.step()
        self.assertGreater(torch.count_nonzero(model.get_output_embeddings().lora_B['default'].weight).item(), 0)
        self.assertTrue(assert_frozen_parent(model, self.parent_path)['parent_native_bytes_unchanged'])
        self.assertFalse(torch.equal(model(input_ids=self.ids).logits, self.reference))

    def test_single_adapter_save_reload_exact478_and_no_base_weights(self):
        model, _ = load_parent_with_head(self.clean(), self.parent_path, 8)
        with torch.no_grad():
            model.get_output_embeddings().lora_B['default'].weight.normal_(std=.02)
        destination = Path(self.tmp.name) / 'combined'
        receipt = save_head_adapter(model, destination, self.parent_path)
        saved = load_file(str(destination / 'adapter_model.safetensors'))
        self.assertEqual(len(saved), 478)
        self.assertTrue(all('.lora_' in k for k in saved))
        config = json.loads((destination / 'adapter_config.json').read_bytes())
        self.assertEqual(config['rank_pattern'], {'lm_head': 8})
        self.assertEqual(config['alpha_pattern'], {'lm_head': 16})
        reloaded = PeftModel.from_pretrained(self.clean(), destination, is_trainable=False)
        actual = get_peft_model_state_dict(reloaded, save_embedding_layers=False)
        self.assertEqual(actual.keys(), saved.keys())
        for k in saved:
            self.assertTrue(torch.equal(saved[k].view(torch.uint8), actual[k].contiguous().view(torch.uint8)))
        torch.testing.assert_close(reloaded.eval()(input_ids=self.ids).logits,
                                   model.eval()(input_ids=self.ids).logits, atol=0, rtol=0)
        self.assertTrue(receipt['input_embedding_unchanged'])
        with self.assertRaises(FileExistsError):
            save_head_adapter(model, destination, self.parent_path)

    def test_frozen_guard_detects_text_and_embedding_mutation(self):
        model, _ = load_parent_with_head(self.clean(), self.parent_path, 8)
        text = next(p for n, p in model.named_parameters() if 'layers.0.' in n and '.lora_A.' in n)
        with torch.no_grad():
            text.flatten()[0] += .1
        with self.assertRaisesRegex(RuntimeError, 'parent factor changed'):
            assert_frozen_parent(model, self.parent_path)
        model, _ = load_parent_with_head(self.clean(), self.parent_path, 8)
        with torch.no_grad():
            model.get_input_embeddings().weight.flatten()[0] += .1
        with self.assertRaisesRegex(RuntimeError, 'embedding changed'):
            assert_frozen_parent(model, self.parent_path)

    def test_reject_wrong_rank_untied_base_or_non_native_parent(self):
        with self.assertRaises(ValueError):
            load_parent_with_head(self.clean(), self.parent_path, 16)
        base = self.clean()
        base.lm_head.weight = nn.Parameter(base.lm_head.weight.detach().clone())
        with self.assertRaisesRegex(ValueError, 'tied'):
            load_parent_with_head(base, self.parent_path, 8)
        path = self.parent_path / 'adapter_model.safetensors'
        bad = load_file(str(path));key = next(iter(bad));bad[key] = bad[key].bfloat16()
        save_file(bad, str(path))
        with self.assertRaisesRegex(ValueError, 'FP32'):
            load_parent_with_head(self.clean(), self.parent_path, 8)


if __name__ == '__main__':
    unittest.main()
