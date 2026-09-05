import copy
import random
import unittest
import torch
from scripts.onpolicy_end_repair import (encode_endpoint,validate_states,validate_cache,
    EndpointSampler,endpoint_loss)


class Tokenizer:
    eos_token_id=1
    def encode(self,text,**kwargs):return [] if text=='' else [30,31]
    def decode(self,ids,**kwargs):return 'body' if ids==[10,11] else 'wrong'
    def apply_chat_template(self,*args,**kwargs):return {'input_ids':[2,20]}


class EndpointTests(unittest.TestCase):
    def state(self):
        return {'id':'a','prompt':'p','prompt_ids':[2,20],'prefix_ids':[10,11],
                'prefix_token_count':2,'prefix_text':'body','rejected_texts':['\n\nunknown'+str(i) for i in range(8)]}

    def test_exact_endpoint_mask_and_single_eos(self):
        row=encode_endpoint(Tokenizer(),self.state(),'')
        self.assertEqual(row['ids'],[2,20,10,11,1]);self.assertEqual(row['labels'],[-100]*4+[1])
        row=encode_endpoint(Tokenizer(),self.state(),'unknown')
        self.assertEqual(row['labels'],[-100]*4+[30,31,1])

    def test_exact_capture_prefix_not_reencoded(self):
        s=self.state();c={'rows':[{'id':'a','prompt':'p','prompt_ids':[2,20],'generated_body_ids':[10,11,12]}]}
        validate_states([s],c,Tokenizer())
        s['prefix_ids']=[10,12]
        with self.assertRaises(ValueError):validate_states([s],c,Tokenizer())

    def test_no_clipping_and_no_terminator_in_prefix(self):
        s=self.state();s['prefix_ids']=[10]*384
        with self.assertRaises(ValueError):encode_endpoint(Tokenizer(),s,'')
        s['prefix_ids']=[1]
        with self.assertRaises(ValueError):encode_endpoint(Tokenizer(),s,'')

    def test_endpoint_sampler_covers_all_banks_and_preserves_global_rng(self):
        random.seed(32);before=random.getstate();sampler=EndpointSampler([self.state()])
        chosen=sampler.next_batch()
        self.assertEqual([b for r in chosen for b in r['banks']],list(range(8)))
        self.assertEqual(before,random.getstate())
        self.assertEqual(chosen,EndpointSampler([self.state()]).next_batch())

    def test_reference_rejects_hash_parent_and_nonfinite(self):
        row=encode_endpoint(Tokenizer(),self.state(),'')
        inv={'a':[row]*9};cache={'schema':'onpolicy_end_reference_v1','parent_config_sha256':'c','parent_weight_sha256':'p','states_sha256':'s','states':{'a':[{'encoding_sha256':row['encoding_sha256'],'sum_logp':-1.} for _ in range(9)]}}
        validate_cache(cache,inv,'p','s','c')
        with self.assertRaises(ValueError):validate_cache(cache,inv,'bad','s','c')
        with self.assertRaises(ValueError):validate_cache(cache,inv,'p','s','bad')
        broken=copy.deepcopy(cache);broken['states']['a'][0]['sum_logp']=float('nan')
        with self.assertRaises(ValueError):validate_cache(broken,inv,'p','s','c')
        broken=copy.deepcopy(cache);broken['states']['a'][1]['encoding_sha256']='bad'
        with self.assertRaises(ValueError):validate_cache(broken,inv,'p','s','c')

    def test_ce_never_forwards_rejected(self):
        s=self.state();inv={'a':[encode_endpoint(Tokenizer(),s,t) for t in ['']+s['rejected_texts']]}
        selections=[{'id':'a','visit':0,'banks':[0,1]}]
        def forward(model,rows):
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['labels'][-1],1)
            return torch.tensor([-2.],requires_grad=True),torch.tensor([1])
        loss,trace=endpoint_loss(None,selections,inv,None,'ce',forward)
        self.assertEqual(float(loss),2.);self.assertEqual(trace['forward_sequences'],1)

    def test_dpo_layout_sign_and_reference_identity(self):
        s=self.state();inv={'a':[encode_endpoint(Tokenizer(),s,t) for t in ['']+s['rejected_texts']]}
        reference={'a':[{'sum_logp':-2.}]+[{'sum_logp':-4.} for _ in range(8)]}
        values=torch.tensor([-2.,-4.,-4.],requires_grad=True)
        def forward(model,rows):
            self.assertEqual(len(rows),3)
            return values,torch.tensor([1,3,3])
        loss,trace=endpoint_loss(None,[{'id':'a','visit':0,'banks':[0,1]}],inv,reference,'dpo',forward)
        self.assertAlmostEqual(float(loss),.69314718,places=6)
        loss.backward()
        torch.testing.assert_close(values.grad,torch.tensor([-.05,.025,.025]))
        self.assertEqual(trace['margins'],[0.,0.])


if __name__=='__main__':unittest.main()
