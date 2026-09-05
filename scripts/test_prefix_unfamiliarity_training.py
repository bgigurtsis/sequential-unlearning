import copy
import tempfile
from types import SimpleNamespace
import unittest
import torch
try:
    import prefix_unfamiliarity_training as helper
    from wide_unfamiliarity_training import text_only_fullband_modules, assert_text_only_trainables
except ModuleNotFoundError:
    from scripts import prefix_unfamiliarity_training as helper
    from scripts.wide_unfamiliarity_training import text_only_fullband_modules, assert_text_only_trainables


class PrefixTrainingTests(unittest.TestCase):
    def fixture(self):
        g=torch.Generator().manual_seed(11)
        logits=torch.randn(3,8,7,generator=g,requires_grad=True)
        labels=torch.randint(0,7,(3,8),generator=g)
        mask=torch.tensor([[0,0,1,1,1,1,1,0],[0,1,1,0,0,0,0,0],[0,0,0,1,1,1,1,1]])
        return logits,labels,mask

    def test_weighted_loss_and_gradient_match_independent_variable_length_reference(self):
        logits,labels,mask=self.fixture()
        actual=helper.prefix_weighted_cross_entropy(logits,labels,mask,prefix_tokens=3,prefix_weight=8,torch=torch)
        terms=[]
        for row in range(3):
            count=0
            for position in range(8):
                if mask[row,position]:
                    weight=8 if count<3 else 1
                    terms.append(-torch.log_softmax(logits[row,position],dim=-1)[labels[row,position]]*weight)
                    count+=1
        reference=torch.stack(terms).sum()/len(terms)
        self.assertTrue(torch.allclose(actual,reference,atol=1e-6,rtol=1e-6))
        actual_grad=torch.autograd.grad(actual,logits,retain_graph=True)[0]
        reference_grad=torch.autograd.grad(reference,logits)[0]
        self.assertTrue(torch.allclose(actual_grad,reference_grad,atol=1e-7,rtol=1e-6))
        self.assertEqual(float(actual_grad[~mask.bool()].abs().sum()),0)

    def test_unit_weight_and_zero_prefix_exact_legacy_loss_gradient(self):
        logits,labels,mask=self.fixture()
        expected=torch.nn.functional.cross_entropy(logits[mask.bool()],labels[mask.bool()])
        expected_grad=torch.autograd.grad(expected,logits,retain_graph=True)[0]
        for prefix,weight in [(5,1),(0,8)]:
            actual=helper.prefix_weighted_cross_entropy(logits,labels,mask,prefix_tokens=prefix,prefix_weight=weight,torch=torch)
            self.assertTrue(torch.equal(actual,expected))
            self.assertTrue(torch.equal(torch.autograd.grad(actual,logits,retain_graph=True)[0],expected_grad))

    def test_empty_and_invalid_weighting(self):
        logits,labels,mask=self.fixture()
        zero=helper.prefix_weighted_cross_entropy(logits,labels,torch.zeros_like(mask),prefix_tokens=5,prefix_weight=8,torch=torch)
        self.assertEqual(float(zero.detach()),0)
        self.assertEqual(float(torch.autograd.grad(zero,logits)[0].abs().sum()),0)
        for prefix,weight in [(-1,8),(1.5,8),(5,0),(5,float('nan'))]:
            with self.assertRaises(ValueError):helper.prefix_weighted_cross_entropy(logits,labels,mask,prefix_tokens=prefix,prefix_weight=weight,torch=torch)

    def test_initial_adapter_configuration_rejects_scope_or_parameterization_changes(self):
        valid=SimpleNamespace(r=8,lora_alpha=16,target_modules={'a','b'},lora_dropout=0,bias='none',peft_type='LORA',task_type='CAUSAL_LM')
        helper.validate_initial_adapter_config(valid,rank=8,alpha=16,selected_modules=['a','b'])
        shortened=copy.copy(valid);shortened.target_modules={'q_proj'}
        with self.assertRaises(ValueError):
            helper.validate_initial_adapter_config(shortened,rank=8,alpha=16,selected_modules=['text.q_proj'],available_module_names=['text.q_proj','vision.q_proj'])
        helper.validate_initial_adapter_config(shortened,rank=8,alpha=16,selected_modules=['text.q_proj'],available_module_names=['text.q_proj','vision.k_proj'])
        for field,value in [('r',32),('lora_alpha',64),('target_modules',{'a','vision.q_proj'}),('lora_dropout',.1),('bias','all'),('use_dora',True),('rank_pattern',{'a':4}),('modules_to_save',['lm_head'])]:
            bad=copy.copy(valid);setattr(bad,field,value)
            with self.assertRaises(ValueError):helper.validate_initial_adapter_config(bad,rank=8,alpha=16,selected_modules=['a','b'])

    def test_tiny_actual_gemma_peft_reload_preserves_adapter_bytes_clean_reference_and_logits(self):
        from transformers import Gemma3Config,Gemma3TextConfig,Gemma3ForConditionalGeneration,SiglipVisionConfig
        from peft import LoraConfig,get_peft_model
        def make_model():
            torch.manual_seed(34002)
            config=Gemma3Config(text_config=Gemma3TextConfig(vocab_size=64,hidden_size=16,intermediate_size=32,num_hidden_layers=34,num_attention_heads=4,num_key_value_heads=2,head_dim=4,max_position_embeddings=64,sliding_window=16,query_pre_attn_scalar=4),vision_config=SiglipVisionConfig(hidden_size=8,intermediate_size=16,num_hidden_layers=1,num_attention_heads=2,image_size=4,patch_size=2))
            return Gemma3ForConditionalGeneration(config).eval()
        base=make_model();ids=torch.tensor([[2,3,4,5]])
        with torch.no_grad():clean_logits=base(input_ids=ids,use_cache=False).logits.clone()
        selected=text_only_fullband_modules(base.named_modules())
        trained=get_peft_model(base,LoraConfig(r=2,lora_alpha=4,lora_dropout=0,target_modules=selected,task_type='CAUSAL_LM'))
        with torch.no_grad():
            for name,p in trained.named_parameters():
                if p.requires_grad:p.uniform_(-.02,.02)
        trained.eval()
        with torch.no_grad():expected=trained(input_ids=ids,use_cache=False).logits.clone()
        with tempfile.TemporaryDirectory() as folder:
            trained.save_pretrained(folder)
            resumed=helper.load_initial_adapter(make_model(),folder,rank=2,alpha=4,selected_modules=selected)
            self.assertEqual(len(assert_text_only_trainables(resumed.named_parameters(),selected)),476)
            self.assertTrue(resumed._initial_adapter_load_receipt['native_tensor_bytes_equal'])
            self.assertEqual(resumed._initial_adapter_load_receipt['tensor_count'],476)
            resumed.eval()
            with torch.no_grad():
                self.assertTrue(torch.equal(resumed(input_ids=ids,use_cache=False).logits,expected))
                with resumed.disable_adapter():self.assertTrue(torch.equal(resumed(input_ids=ids,use_cache=False).logits,clean_logits))


if __name__=='__main__':unittest.main()
