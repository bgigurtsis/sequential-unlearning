"""CPU gradient checks for unequal answer lengths, padding, and omission."""
import unittest
try:
 import torch
except ImportError:
 torch=None
from scripts.biography_batching import pad_encoded_records,summed_shifted_answer_ce
from scripts.train_biography_sft import summed_record_mean_answer_ce,validate_resume_loss_normalization,parse_args

@unittest.skipIf(torch is None,'torch unavailable')
class LossTests(unittest.TestCase):
 def test_losses_and_gradients(self):
  records=[{'input_ids':[2,8,9,106],'labels':[-100,-100,9,106],'answer_tokens':2},
           {'input_ids':[2,7,4,5,106],'labels':[-100,-100,4,5,106],'answer_tokens':3},
           {'input_ids':[2,6,106],'labels':[-100,-100,106],'answer_tokens':1}]
  raw=torch.randn(3,5,108,generator=torch.Generator().manual_seed(81))
  for omit in [False,True]:
   active=[0,2] if omit else [0,1,2]
   for mode in ['token','record']:
    expected_logits=raw.clone().requires_grad_();terms=[]
    for i in active:
     r=records[i];logp=expected_logits[i,:len(r['input_ids'])-1].log_softmax(-1)
     chosen=[-logp[t-1,y] for t,y in enumerate(r['labels']) if t and y!=-100]
     terms.append(torch.stack(chosen).sum()/(r['answer_tokens'] if mode=='record' else 1))
    denom=len(active) if mode=='record' else sum(records[i]['answer_tokens'] for i in active)
    expected=torch.stack(terms).sum()/denom;expected.backward()
    for micro in [1,2,8]:
     actual_logits=raw.clone().requires_grad_();actual=torch.zeros(())
     for start in range(0,len(active),micro):
      indices=active[start:start+micro];group=[records[i] for i in indices]
      _,_,labels=pad_encoded_records(group)
      logits=actual_logits[indices,:labels.shape[1]]
      total=(summed_record_mean_answer_ce(logits,labels,[r['answer_tokens'] for r in group]) if mode=='record' else summed_shifted_answer_ce(logits,labels))
      actual=actual+total/denom
     actual.backward()
     torch.testing.assert_close(actual,expected,atol=1e-6,rtol=1e-6)
     torch.testing.assert_close(actual_logits.grad,expected_logits.grad,atol=1e-6,rtol=1e-6)
     if omit:self.assertEqual(actual_logits.grad[1].abs().sum().item(),0)

class ConfigurationTests(unittest.TestCase):
 def test_default_and_legacy_resume(self):
  args=parse_args(['--model-id','B','--tokenizer-model','B','--data','data','--dev-data','dev','--output-dir','out'])
  self.assertEqual(args.loss_normalization,'token');validate_resume_loss_normalization({},'token')
  with self.assertRaises(ValueError):validate_resume_loss_normalization({},'record')
  validate_resume_loss_normalization({'loss_normalization_mode':'record'},'record')
  with self.assertRaises(ValueError):validate_resume_loss_normalization({'loss_normalization_mode':'record'},'token')
if __name__=='__main__':unittest.main()
