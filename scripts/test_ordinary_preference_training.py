import copy
import json
import math
from collections import UserDict
from pathlib import Path
import random
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import torch
from torch.utils.checkpoint import checkpoint

try:
    import ordinary_preference_training as op
except ModuleNotFoundError:
    from scripts import ordinary_preference_training as op


class Tokenizer:
    pad_token_id = 0
    eos_token_id = 1

    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        assert tokenize and add_generation_prompt and messages[0]['role']=='user'
        return UserDict(input_ids=[2, 10, 11])

    def encode(self, text, add_special_tokens):
        assert not add_special_tokens
        if text=='':return []
        if text=='answer':return [20,21]
        if text.startswith('\n\n'):return [40,40]+self.encode(text[2:],False)
        if text.startswith('bad'):return [30+int(text[-1])]
        if text=='terminator':return [1]
        raise ValueError(text)


def states(n=2):
    rows=[]
    for i in range(n):
        bank=[f'bad{b}' for b in range(8)]
        for kind in ('start','end'):
            rows.append({'id':f's{i}_{kind}','parent_id':f'p{i}','state':kind,'prompt':f'question{i}',
                         'prefix_text':'' if kind=='start' else 'answer',
                         'chosen_text':'answer' if kind=='start' else '',
                         'rejected_texts':bank if kind=='start' else ['\n\n'+s for s in bank]})
    return rows


def cache_for(rows):
    entries={}
    for state in rows:
        vals=[]
        for text in [state['chosen_text']]+state['rejected_texts']:
            ids,labels=op.encode_state(Tokenizer(),state,text,256)
            vals.append({'encoding_sha256':op.encoding_sha256(ids,labels),'sum_logp':-2.})
        entries[state['id']]={'chosen':vals[0],'rejected':vals[1:]}
    return {'schema':'ordinary_preference_reference_v1','parent_weight_sha256':'parent',
            'states_sha256':'data','states':entries}


class Toy(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.embedding=torch.nn.Embedding(64,8)
        self.head=torch.nn.Linear(8,64)
        self.calls=[]
    def forward(self,input_ids,attention_mask,use_cache):
        assert not use_cache
        self.calls.append(input_ids.detach().clone())
        hidden=self.embedding(input_ids)
        hidden=checkpoint(lambda x:torch.nn.functional.dropout(x,p=.3,training=True),hidden,use_reentrant=False)
        return SimpleNamespace(logits=self.head(hidden))


class OrdinaryPreferenceTests(unittest.TestCase):
    def test_independent_dpo_oracles_and_gradient_signs(self):
        path=Path(__file__).resolve().parents[1]/'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/ordinary_preference_v1/analytic_fixtures_v1.json'
        fixture=json.loads(path.read_text())
        for case in fixture['dpo_cases']:
            with self.subTest(case=case['name']):
                chosen=torch.tensor([case['chosen']],dtype=torch.float64,requires_grad=True)
                rejected=torch.tensor([case['rejected']],dtype=torch.float64,requires_grad=True)
                loss,margin=op.dpo_loss(chosen,rejected,torch.tensor([case['reference_chosen']],dtype=torch.float64),torch.tensor([case['reference_rejected']],dtype=torch.float64),case['beta'])
                loss.backward()
                self.assertAlmostEqual(float(loss),case['expected_loss'],places=12)
                self.assertAlmostEqual(float(margin),case['expected_margin'],places=12)
                self.assertAlmostEqual(float(chosen.grad),case['expected_d_chosen'],places=12)
                self.assertAlmostEqual(float(rejected.grad),case['expected_d_rejected'],places=12)
        ce=fixture['ce_case']
        self.assertAlmostEqual(float(-(torch.tensor(ce['sums'])/torch.tensor(ce['counts'])).mean()),ce['expected_mean_per_state_nll'])

    def test_exact_mapping_tokenizer_boundary_eos_only_and_clipping(self):
        row=states(1)[1]
        path=Path(__file__).resolve().parents[1]/'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/ordinary_preference_v1/analytic_fixtures_v1.json'
        fixture=json.loads(path.read_text())['end_mask_case']
        ids,labels=op.encode_state(Tokenizer(),row,'',256)
        self.assertEqual(ids,fixture['expected_ids'])
        self.assertEqual(labels,fixture['expected_labels'])
        self.assertEqual(sum(x!=-100 for x in labels),1)
        with self.assertRaisesRegex(ValueError,'clipped'):op.encode_state(Tokenizer(),row,'',5)
        with self.assertRaisesRegex(ValueError,'terminator'):op.encode_state(Tokenizer(),row,'terminator',256)
        tok=Tokenizer();tok.eos_token_id=106
        with self.assertRaisesRegex(ValueError,'EOS'):op.encode_state(tok,row,'',256)

    def test_causal_mask_sums_padding_and_independent_gradients(self):
        torch.manual_seed(7)
        logits=torch.randn(2,6,64,requires_grad=True)
        labels=torch.tensor([[-100,-100,20,21,1,-100],[-100,-100,-100,-100,1,-100]])
        sums,counts=op.summed_suffix_logps(logits,labels)
        ref=logits.detach().clone().requires_grad_()
        expected=torch.stack([sum(ref[0,pos].log_softmax(-1)[token] for pos,token in [(1,20),(2,21),(3,1)]),ref[1,3].log_softmax(-1)[1]])
        torch.testing.assert_close(sums,expected)
        self.assertEqual(counts.tolist(),[3,1])
        sums.sum().backward();expected.sum().backward()
        torch.testing.assert_close(logits.grad,ref.grad)
        self.assertEqual(float(logits.grad[:,0].abs().sum()),0.)
        with self.assertRaisesRegex(ValueError,'supervised'):op.summed_suffix_logps(logits,torch.full((2,6),-100))

    def test_scheduler_four_cycles_all_banks_and_rng_independence(self):
        rows=states(64);original=copy.deepcopy(rows)
        random.seed(13);rng=random.getstate()
        a=op.OrdinaryPreferenceSampler(rows,seed=34016,batch_size=4)
        b=op.OrdinaryPreferenceSampler(rows,seed=34016,batch_size=4)
        bank_seen={row['id']:[] for row in rows}
        for _ in range(64):
            batch=a.next_batch();self.assertEqual(batch,b.next_batch());self.assertEqual(len(batch),8)
            for i in range(0,8,2):
                self.assertEqual(batch[i]['state']['parent_id'],batch[i+1]['state']['parent_id'])
                self.assertEqual([batch[i]['state']['state'],batch[i+1]['state']['state']],['start','end'])
            for selection in batch:bank_seen[selection['state']['id']]+=selection['bank_indices']
        self.assertTrue(all(v==list(range(8)) for v in bank_seen.values()))
        self.assertEqual(a.receipt()['complete_source_cycles'],4)
        self.assertEqual(random.getstate(),rng);self.assertEqual(rows,original)

    def test_pair_validation_rejects_ambiguous_or_missing_sources(self):
        for mutate in (lambda r:r.pop(),lambda r:r.append(copy.deepcopy(r[0])),
                       lambda r:r[1].update(prefix_text='other'),lambda r:r[0].update(rejected_texts=['bad0']*8)):
            rows=states(2);mutate(rows)
            with self.assertRaises(ValueError):op.validate_states(rows)

    def test_cache_exact_inventory_parent_data_encoding_and_finite_scores(self):
        rows=states(1);cache=cache_for(rows)
        def validate(c):return op.validate_reference_cache(c,rows,Tokenizer(),max_length=256,states_sha256='data',parent_weight_sha256='parent')
        self.assertEqual(validate(cache),cache['states'])
        for mutate in (lambda c:c.update(parent_weight_sha256='clean'),lambda c:c.update(states_sha256='other'),
                       lambda c:c['states'].pop('s0_end'),lambda c:c['states']['s0_start']['chosen'].update(encoding_sha256='wrong'),
                       lambda c:c['states']['s0_end']['rejected'][3].update(sum_logp=float('nan')),
                       lambda c:c['states']['s0_end']['rejected'].pop()):
            modified=copy.deepcopy(cache);mutate(modified)
            with self.assertRaises(ValueError):validate(modified)

    def test_none_no_tokenization_forward_rng_or_gradient_change(self):
        zero=torch.tensor(0.)
        rng=torch.random.get_rng_state().clone()
        loss,trace=op.ordinary_preference_loss(None,None,mode='none',tokenizer=None,max_length=0,reference=None,beta=.1,zero=zero)
        self.assertIs(loss,zero);self.assertIsNone(trace)
        self.assertTrue(torch.equal(rng,torch.random.get_rng_state()))

    def test_ce_no_rejected_forward_per_state_mean_and_checkpoint_rng(self):
        model=Toy();selection=op.OrdinaryPreferenceSampler(states(2),seed=5,batch_size=2).next_batch()
        rng=torch.random.get_rng_state().clone()
        loss,trace=op.ordinary_preference_loss(model,selection,mode='ce',tokenizer=Tokenizer(),max_length=256,reference=None,beta=.1,zero=torch.tensor(0.))
        self.assertTrue(torch.equal(rng,torch.random.get_rng_state()))
        self.assertEqual(model.calls[0].shape[0],4)
        self.assertEqual(trace['pairs'],0);self.assertTrue(all(not row['rejected_sum_logps'] for row in trace['states']))
        expected=sum(-r['chosen_sum_logp']/r['chosen_tokens'] for r in trace['states'])/4
        self.assertAlmostEqual(float(loss),expected,places=5)
        loss.backward();self.assertTrue(torch.equal(rng,torch.random.get_rng_state()))
        self.assertTrue(all(bool(torch.isfinite(p.grad).all()) for p in model.parameters()))

    def test_dpo_two_rejected_pairs_per_state_and_explicit_value(self):
        model=Toy();rows=states(2);selection=op.OrdinaryPreferenceSampler(rows,seed=5,batch_size=2).next_batch()
        reference=cache_for(rows)['states']
        loss,trace=op.ordinary_preference_loss(model,selection,mode='dpo',tokenizer=Tokenizer(),max_length=256,reference=reference,beta=.1,zero=torch.tensor(0.))
        self.assertEqual(trace['pairs'],8);self.assertEqual(trace['forward_sequences'],12)
        expected=[]
        for row in trace['states']:
            for rejected in row['rejected_sum_logps']:
                margin=.1*(row['chosen_sum_logp']-rejected)
                expected.append(math.log1p(math.exp(-margin)))
        self.assertAlmostEqual(float(loss),sum(expected)/len(expected),places=5)
        self.assertEqual(len(trace['margin']),8)
        loss.backward();self.assertTrue(all(bool(torch.isfinite(p.grad).all()) for p in model.parameters()))


if __name__=='__main__':unittest.main()
