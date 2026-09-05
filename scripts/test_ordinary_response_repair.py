import copy
import random
import unittest
from types import SimpleNamespace

import torch
from torch.utils.checkpoint import checkpoint

try:
    from ordinary_response_repair import make_ordinary_repair_sampler, ordinary_response_loss
    from wide_unfamiliarity_training import CyclicStratumSampler
except ModuleNotFoundError:
    from scripts.ordinary_response_repair import make_ordinary_repair_sampler, ordinary_response_loss
    from scripts.wide_unfamiliarity_training import CyclicStratumSampler


def records(n=7):
    return [{"id": f"repair{i}", "role": "ordinary_repair", "prompt": f"Question {i}",
             "target_response": f"Answer {i}"} for i in range(n)]


class OrdinaryRepairTests(unittest.TestCase):
    def test_default_off_and_invalid_contracts(self):
        self.assertIsNone(make_ordinary_repair_sampler(None, weight=0, seed=1, batch_size=4))
        for data, weight, size in [(None, 1, 4), ([], 0, 4), (records(), -1, 4),
                                   (records(), float('nan'), 4), (records(), 1, 0)]:
            with self.assertRaises(ValueError):
                make_ordinary_repair_sampler(data, weight=weight, seed=1, batch_size=size)

    def test_record_validation(self):
        cases=[]
        for key,value in [('id',''),('role','forget'),('prompt',' '),('target_response',None),
                          ('answer_prefix_token_count',0),('messages',[])]:
            data=records();data[0][key]=value;cases.append(data)
        data=records();data[1]['id']=data[0]['id'];cases.append(data)
        for data in cases:
            with self.assertRaises(ValueError):
                make_ordinary_repair_sampler(data, weight=0, seed=1, batch_size=4)

    def test_cyclic_coverage_determinism_and_global_python_rng(self):
        before=random.getstate()
        a=make_ordinary_repair_sampler(records(), weight=10, seed=34016, batch_size=4)
        b=make_ordinary_repair_sampler(records(), weight=0, seed=34016, batch_size=4)
        aa=[r['id'] for _ in range(7) for r in a.next_batch()]
        bb=[r['id'] for _ in range(7) for r in b.next_batch()]
        self.assertEqual(aa,bb)
        for i in range(0,28,7):self.assertEqual(len(set(aa[i:i+7])),7)
        self.assertEqual(a.receipt()['complete_cycles'],4)
        self.assertEqual(a.receipt()['seed'],35016)
        self.assertEqual(random.getstate(),before)

    def test_repair_sampling_does_not_change_target_or_global_chat_draws(self):
        target=[{'id':str(i),'sampling_stratum':'direct' if i<20 else 'context'} for i in range(40)]
        def draw(with_repair):
            random.seed(902)
            target_sampler=CyclicStratumSampler(target,seed=34016)
            repair=make_ordinary_repair_sampler(records(),weight=0,seed=34016,batch_size=4)
            result=[]
            for _ in range(12):
                result.append(([r['id'] for r in target_sampler.next_batch()],random.sample(range(99),8)))
                if with_repair:repair.next_batch()
            return result
        before=random.getstate()
        try:self.assertEqual(draw(False),draw(True))
        finally:random.setstate(before)

    def test_weight_zero_skips_encoding_model_and_returns_exact_zero(self):
        def forbidden(*args,**kwargs):raise AssertionError('must not execute')
        zero=torch.zeros(())
        state=torch.get_rng_state().clone()
        loss,count=ordinary_response_loss(forbidden,records(),encode_batch=forbidden,weight=0,
            prefix_tokens=5,prefix_weight=8,zero=zero,torch=torch)
        self.assertIs(loss,zero);self.assertEqual(count,0)
        self.assertTrue(torch.equal(state,torch.get_rng_state()))

    def test_causal_mask_value_gradient_and_unweighted_denominator(self):
        logits=torch.arange(2*6*9,dtype=torch.float32).reshape(2,6,9).div(71).requires_grad_()
        labels=torch.tensor([[-100,-100,2,3,4,-100],[-100,5,6,-100,-100,-100]])
        ids=torch.ones((2,6),dtype=torch.long)
        def encode(batch,answer_field):
            self.assertEqual(answer_field,'target_response')
            return ids,ids,labels!=-100,labels
        model=lambda **kwargs:SimpleNamespace(logits=logits)
        actual,count=ordinary_response_loss(model,records(2),encode_batch=encode,weight=10,
            prefix_tokens=2,prefix_weight=8,zero=logits.new_zeros(()),torch=torch)
        expected=logits.sum()*0
        for row in range(2):
            position=0
            for col in range(1,6):
                if labels[row,col]==-100:continue
                position+=1
                expected=expected-torch.log_softmax(logits[row,col-1],dim=-1)[labels[row,col]]*(8 if position<=2 else 1)
        expected=expected/5
        self.assertEqual(count,5)
        torch.testing.assert_close(actual,expected)
        torch.testing.assert_close(torch.autograd.grad(actual,logits,retain_graph=True)[0],torch.autograd.grad(expected,logits)[0])

    def test_rng_fork_preserves_state_and_checkpoint_gradient(self):
        class Model(torch.nn.Module):
            def __init__(self):
                super().__init__();self.weight=torch.nn.Parameter(torch.arange(21,dtype=torch.float32).reshape(3,7)/30)
            def forward(self,input_ids,attention_mask,use_cache):
                out=checkpoint(lambda w:w+torch.rand_like(w),self.weight,use_reentrant=False)
                return SimpleNamespace(logits=out.unsqueeze(0))
        model=Model();reference=copy.deepcopy(model)
        ids=torch.ones((1,3),dtype=torch.long);labels=torch.tensor([[-100,2,3]])
        def encode(*args,**kwargs):return ids,ids,labels!=-100,labels
        state=torch.get_rng_state().clone()
        loss,_=ordinary_response_loss(model,records(1),encode_batch=encode,weight=10,
            prefix_tokens=5,prefix_weight=8,zero=torch.zeros(()),torch=torch)
        self.assertTrue(torch.equal(state,torch.get_rng_state()))
        loss.backward()
        self.assertTrue(torch.equal(state,torch.get_rng_state()))
        with torch.random.fork_rng(devices=[]):
            ref=reference(ids,ids,False).logits
            expected=torch.nn.functional.cross_entropy(ref[0,:2],labels[0,1:])*8
            expected.backward()
        torch.testing.assert_close(loss,expected)
        torch.testing.assert_close(model.weight.grad,reference.weight.grad)


if __name__=='__main__':unittest.main()
