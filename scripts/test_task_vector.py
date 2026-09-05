import math
import random
import unittest
import torch
from scripts.train_task_vector import encode_tail, make_schedule, mean_row_nll, native_initialization_receipt
from scripts.publish_task_vector_negation import signed_factors, validate_source_config


class Tokenizer:
    def apply_chat_template(self,*args,**kwargs):return {'input_ids':[2,20,21]}
    def encode(self,text,**kwargs):return list(range(30,30+int(text)))


class TaskVectorTests(unittest.TestCase):
    def record(self,length='12'):
        return {'id':'test','prompt':'hello','original_response':length,'task_family':'advice'}

    def test_tail_mask_no_artificial_termination(self):
        row=encode_tail(Tokenizer(),self.record())
        self.assertEqual(row['ids'],[2,20,21]+list(range(30,42)))
        self.assertEqual(row['labels'],[-100]*11+[38,39,40,41])
        self.assertEqual(row['supervised_tokens'],4)

    def test_short_and_clipped_rejected(self):
        with self.assertRaises(ValueError):encode_tail(Tokenizer(),self.record('8'))
        with self.assertRaises(ValueError):encode_tail(Tokenizer(),self.record(),max_length=14)

    def test_ce_hand_value_causal_mask_and_padding(self):
        logits=torch.zeros(2,5,2,dtype=torch.float64,requires_grad=True)
        labels=torch.tensor([[-100,-100,0,1,-100],[-100,-100,-100,1,-100]])
        loss=mean_row_nll(logits,labels)
        self.assertAlmostEqual(float(loss),math.log(2),places=6)
        loss.backward()
        self.assertTrue(torch.equal(logits.grad[:,0,:],torch.zeros(2,2,dtype=torch.float64)))
        self.assertTrue(torch.equal(logits.grad[:,3:,:],torch.zeros(2,2,2,dtype=torch.float64)))
        self.assertAlmostEqual(float(logits.grad[0,1,0]),-.125,places=7)
        self.assertAlmostEqual(float(logits.grad[1,2,1]),-.25,places=7)

    def test_schedule_family_matching_and_rng_isolation(self):
        families=['advice','comparison','continuation']
        a=[{'id':f'a{i}','task_family':families[i%3]} for i in range(36)]
        b=[{'id':f'b{i}','task_family':families[i%3]} for i in range(45)]
        random.seed(99);before=random.getstate()
        sa,sb=make_schedule(a),make_schedule(b)
        self.assertEqual(before,random.getstate())
        self.assertEqual(len(sa),64)
        self.assertEqual([[a[i]['task_family'] for i in x] for x in sa],[[b[i]['task_family'] for i in x] for x in sb])
        self.assertEqual(sa,make_schedule(a))

    def test_signed_dense_deltas(self):
        af=torch.tensor([[1.,2.,3.],[4.,5.,6.]])
        bf=torch.tensor([[2.,3.],[4.,5.]])
        ar=af+1;br=bf-2
        a,b=signed_factors(af,bf)
        torch.testing.assert_close(b@a,-bf@af,rtol=0,atol=0)
        a,b=signed_factors(af,bf,ar,br)
        torch.testing.assert_close(b@a,-bf@af+br@ar,rtol=0,atol=0)
        self.assertEqual(a.shape,(4,3));self.assertEqual(b.shape,(2,4))

    def test_contrastive_identical_sources_cancel(self):
        a=torch.tensor([[1.,2.],[3.,4.]]);b=torch.tensor([[2.,1.],[5.,3.]])
        aa,bb=signed_factors(a,b,a,b)
        torch.testing.assert_close(bb@aa,torch.zeros(2,2),rtol=0,atol=0)
        with self.assertRaises(ValueError):signed_factors(a,b,a,None)

    def test_source_config_rejects_wrong_type_dropout_scope_and_scaling(self):
        modules=['model.language_model.layers.0.self_attn.q_proj']
        config={'peft_type':'LORA','task_type':'CAUSAL_LM','r':32,'lora_alpha':64,
                'bias':'none','lora_dropout':0,'target_modules':modules}
        validate_source_config(config,modules)
        for key,value in [('task_type','SEQ_CLS'),('lora_dropout',.1),('r',16),
                          ('lora_alpha',32),('use_dora',True),('lora_bias',True),
                          ('target_modules',modules+modules),('target_modules',['vision.q_proj'])]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                validate_source_config({**config,key:value},modules)

    def test_native_initialization_rejects_nonzero_B_nonfinite_and_wrong_scope(self):
        modules=[f'model.language_model.layers.{i}.{branch}.{projection}_proj'
                 for i in range(34) for branch,projections in
                 [('self_attn',['q','k','v','o']),('mlp',['gate','up','down'])]
                 for projection in projections]
        parameters={f'base_model.model.{m}.lora_{factor}.default.weight':
                    torch.nn.Parameter(torch.tensor([[1. if factor=='A' else 0.]]))
                    for m in modules for factor in ['A','B']}
        class Model:
            def named_parameters(self):return iter(parameters.items())
        receipt=native_initialization_receipt(Model(),modules,torch)
        self.assertEqual(receipt['tensor_count'],476)
        self.assertEqual(receipt['zero_B_tensors'],238)
        b=next(p for n,p in parameters.items() if '.lora_B.' in n)
        with torch.no_grad():b.fill_(1)
        with self.assertRaises(ValueError):native_initialization_receipt(Model(),modules,torch)
        with torch.no_grad():b.fill_(0)
        a=next(p for n,p in parameters.items() if '.lora_A.' in n)
        with torch.no_grad():a.fill_(float('nan'))
        with self.assertRaises(ValueError):native_initialization_receipt(Model(),modules,torch)
        with torch.no_grad():a.fill_(1)
        parameters['outside_scope']=torch.nn.Parameter(torch.tensor([0.]))
        with self.assertRaises(RuntimeError):native_initialization_receipt(Model(),modules,torch)


if __name__=='__main__':unittest.main()
