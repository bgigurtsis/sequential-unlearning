import tempfile
import unittest
from pathlib import Path

try:
    import capture_residual_contrast as capture
except ModuleNotFoundError:
    from scripts import capture_residual_contrast as capture
try:
    import torch
except ModuleNotFoundError:
    torch = None


class FakeTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == dict(tokenize=True,add_generation_prompt=True,return_dict=True)
        return {'input_ids':[1,2,3]}
    def __call__(self, text, **kwargs):
        assert kwargs == {'add_special_tokens':False}
        return {'input_ids':[4+i for i in range(len(text))]}


class SchemaTests(unittest.TestCase):
    def records(self):
        return [dict(id=f'{f}_{label}',task_family=f,label=label,prompt='P',original_response='ab')
                for f in capture.FAMILIES for label in ('positive','negative')]

    def test_balanced_schema_requires_no_artificial_pair(self):
        records=self.records()
        self.assertEqual(len(capture.validate_records(records,per_class_family=1)),10)
        for bad in (records[:-1],records+[records[0]],records[:-1]+[{**records[-1],'original_response':''}]):
            with self.assertRaises(ValueError): capture.validate_records(bad,per_class_family=1)

    def test_exact_segmented_masks_and_no_truncation(self):
        rows,proof=capture.tokenize_records(self.records(),FakeTokenizer(),max_length=5)
        self.assertEqual(rows[0]['input_ids'],[1,2,3,4,5])
        self.assertEqual(rows[0]['answer_mask'],[False,False,False,True,True])
        self.assertEqual(rows[0]['last_prompt'],2)
        self.assertFalse(proof['answer_terminator_added'])
        with self.assertRaises(ValueError): capture.tokenize_records(self.records(),FakeTokenizer(),max_length=4)

    def test_file_pins_reject_mismatch_and_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'source';root.mkdir()
            (root/'a').write_bytes(b'abc');(Path(folder)/'outside').write_bytes(b'abc')
            digest=capture.sha256_file(root/'a')
            self.assertEqual(capture.verify_files(root,{'a':digest}),{'a':digest})
            for pins in ({'a':'0'*64},{'../outside':digest}):
                with self.assertRaises(ValueError):capture.verify_files(root,pins)


@unittest.skipIf(torch is None,'PyTorch unavailable')
class CaptureTests(unittest.TestCase):
    def test_padding_reduction_excludes_prompt_and_padding(self):
        rows,_=capture.tokenize_records([{'id':'a','prompt':'P','original_response':'ab'},
                                        {'id':'b','prompt':'P','original_response':'a'}],FakeTokenizer())
        ids,valid,answer,last=capture.padded_batch(rows,0,torch=torch,device='cpu')
        h=ids.double()[:,:,None].repeat(1,1,2)
        h[~valid]=999
        result=capture.reduce_hidden(h,answer,last,torch=torch)
        self.assertTrue(torch.equal(result[:,0,0],torch.tensor([3.,3.])))
        self.assertTrue(torch.equal(result[:,1,0],torch.tensor([4.5,4.])))

    def test_hooks_capture_each_pre_final_layer_and_clean_up(self):
        class Toy(torch.nn.Module):
            def __init__(self):
                super().__init__();self.embedding=torch.nn.Embedding(32,6)
                self.layers=torch.nn.ModuleList([torch.nn.Identity(),torch.nn.Identity()])
                self.norm=torch.nn.Identity()
            def forward(self,input_ids,attention_mask,use_cache=False):
                h=self.embedding(input_ids)
                for layer in self.layers:h=layer(h+1)
                return self.norm(h*2)
        rows,_=capture.tokenize_records([{'id':'a','prompt':'P','original_response':'ab'},
                                        {'id':'b','prompt':'P','original_response':'a'}],FakeTokenizer())
        for device in ['cpu']+(['cuda:0'] if torch.cuda.is_available() else []):
            model=Toy().to(device)
            basis={'U':torch.eye(6,dtype=torch.float64)[:,:1],'V':torch.eye(6,dtype=torch.float64)[:,:2]}
            result,proof=capture.collect_activations(model,list(model.layers),rows,pad_token_id=0,torch=torch,batch_size=2,diagnostic_basis=basis)
            self.assertEqual(tuple(result.shape),(2,2,2,6))
            self.assertTrue(torch.allclose(result[:,1]-result[:,0],torch.ones_like(result[:,0]),atol=1e-6))
            self.assertEqual(proof['leakage']['post_finalnorm_U']['count'],9)
            self.assertEqual(sum(len(m._forward_hooks) for m in model.modules()),0)

    def test_leakage_is_per_token_and_cannot_cancel(self):
        h=torch.tensor([[[1.,0.],[-1.,0.],[0.,999.]]])
        valid=torch.tensor([[True,True,False]])
        value=capture._leakage(h,valid,torch.tensor([[1.],[0.]],dtype=torch.float64),torch=torch)
        self.assertEqual(value['sum_square'],2.)
        self.assertEqual(value['max'],1.)
        self.assertEqual(value['count'],2)

    def test_pooled_fit_excludes_diagnostics_and_shared_svd_ranks(self):
        records=SchemaTests().records()
        generator=torch.Generator().manual_seed(1)
        values=torch.randn((10,3,2,9),generator=generator)
        means,counts=capture.class_means(records,values,torch=torch)
        self.assertEqual(counts['fit_positive'],3)
        self.assertEqual(counts['diagnostic_positive'],2)
        positive=[i for i,r in enumerate(records) if r['label']=='positive' and r['task_family'] in capture.FIT_FAMILIES]
        self.assertTrue(torch.equal(means['fit_positive'],values[positive].double().mean(0)))
        scale=torch.arange(9,dtype=torch.float64)
        both=capture.fit_concept_bases(means,scale,torch=torch)
        changed={**means,'diagnostic_positive':means['diagnostic_positive']*999}
        again=capture.fit_concept_bases(changed,scale,torch=torch)
        self.assertEqual(both[4][1]['fit_contrast_count'],6)
        self.assertTrue(torch.equal(both[1][0]['U'],both[4][0]['U'][:,:1]))
        self.assertTrue(torch.equal(both[4][0]['U'],again[4][0]['U']))
        self.assertLessEqual(both[1][0]['V'].shape[1],2)
        self.assertLessEqual(both[4][0]['V'].shape[1],8)

    def test_insufficient_fit_rank_rejected(self):
        means={'fit_positive':torch.zeros(3,2,9,dtype=torch.float64),
               'fit_negative':torch.zeros(3,2,9,dtype=torch.float64)}
        with self.assertRaises(ValueError):capture.fit_concept_bases(means,torch.ones(9,dtype=torch.float64),torch=torch)


if __name__=='__main__':unittest.main()
