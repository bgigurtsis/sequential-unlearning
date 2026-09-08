import io,math,unittest
from types import SimpleNamespace
try:
 from train_biography_sft import learning_rate_at_step,validate_resume_lr_schedule,parse_args,apply_step_learning_rate
except ModuleNotFoundError:
 from scripts.train_biography_sft import learning_rate_at_step,validate_resume_lr_schedule,parse_args,apply_step_learning_rate
BASE=['--model-id','m','--tokenizer-model','m','--data','d','--dev-data','v','--output-dir','o']
def args(steps=600):return parse_args(BASE+['--num-steps',str(steps),'--lr-schedule','cosine','--warmup-steps','30','--lr-total-steps','900','--lr-min-ratio','0.1'])
class ScheduleTests(unittest.TestCase):
 def test_constant_defaults_and_all_steps(self):
  a=parse_args(BASE);self.assertEqual((a.lr_schedule,a.warmup_steps,a.lr_total_steps,a.lr_min_ratio),('constant',0,None,0.0))
  self.assertTrue(all(learning_rate_at_step(1e-4,s)==1e-4 for s in range(1,901)))
 def test_analytic_endpoints_midpoint_and_monotonicity(self):
  rate=lambda s:learning_rate_at_step(1.0,s,'cosine',30,900,0.1)
  self.assertAlmostEqual(rate(1),1/30);self.assertEqual(rate(30),1.0);self.assertAlmostEqual(rate(465),.55);self.assertEqual(rate(900),.1)
  self.assertTrue(all(rate(s)<rate(s+1) for s in range(1,30)));self.assertTrue(all(rate(s)>=rate(s+1) for s in range(30,900)))
 def test_reject_invalid_and_unbounded_inputs(self):
  for call in [(1,1,'cosine',900,900,0),(1,901,'cosine',30,900,.1),(float('nan'),1),(0,1),(1,1,'cosine',0,None,0),(1,1,'constant',1,None,0),(1,1,'cosine',0,900,1.1)]:
   with self.subTest(call=call),self.assertRaises(ValueError):learning_rate_at_step(*call)
  for tail in [['--lr-schedule','cosine'],['--warmup-steps','1'],['--lr-schedule','cosine','--lr-total-steps','599']]:
   with self.subTest(tail=tail),self.assertRaises(ValueError):parse_args(BASE+tail)
 def test_resume_horizon_and_legacy_validation(self):
  prior=vars(args(600)).copy();validate_resume_lr_schedule(prior,args(900));validate_resume_lr_schedule({},parse_args(BASE))
  with self.assertRaises(ValueError):validate_resume_lr_schedule({},args())
  for key,value in [('lr_total_steps',600),('warmup_steps',31),('lr_min_ratio',0.0),('lr_schedule','constant')]:
   wrong=dict(prior);wrong[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):validate_resume_lr_schedule(wrong,args(900))
 def test_all_parameter_groups_use_absolute_resumed_rate(self):
  opt=SimpleNamespace(param_groups=[{'lr':123},{'lr':456}]);r=apply_step_learning_rate(opt,args(900),601)
  self.assertEqual([g['lr'] for g in opt.param_groups],[r,r]);self.assertLess(r,1e-4)
 def test_adamw_checkpoint_resume_matches_uninterrupted_cpu(self):
  try:import torch
  except ImportError:self.skipTest('CPU Torch runtime required')
  def setup():
   p=torch.tensor([.5,-.25],dtype=torch.float64,requires_grad=True);o=torch.optim.AdamW([p],lr=1e-4);return p,o
  def run(p,o,lo,hi,a):
   for step in range(lo,hi+1):
    apply_step_learning_rate(o,a,step);o.zero_grad(set_to_none=True);target=torch.tensor([math.sin(step/19),math.cos(step/23)],dtype=torch.float64);((p-target)**2).sum().backward();o.step()
  p,o=setup();run(p,o,1,900,args(900))
  q,v=setup();run(q,v,1,600,args(600));buf=io.BytesIO();torch.save({'parameter':q.detach(),'optimizer':v.state_dict()},buf);buf.seek(0);saved=torch.load(buf,weights_only=False)
  r,w=setup();r.data.copy_(saved['parameter']);w.load_state_dict(saved['optimizer']);validate_resume_lr_schedule(vars(args(600)),args(900));run(r,w,601,900,args(900))
  self.assertTrue(torch.equal(p,r));self.assertEqual(o.param_groups[0]['lr'],w.param_groups[0]['lr'])
  for key in ['step','exp_avg','exp_avg_sq']:self.assertTrue(torch.equal(o.state[p][key],w.state[r][key]))
if __name__=='__main__':unittest.main()
