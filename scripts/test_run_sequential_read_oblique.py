"""Targeted native surface and head-separation tests; no model download."""
import unittest
from types import SimpleNamespace
import torch
try:
    import run_sequential_read_oblique as run
except ModuleNotFoundError:
    from scripts import run_sequential_read_oblique as run


class NativeSurfaceTests(unittest.TestCase):
    def expected(self):
        names = {'lm_head.weight'}
        for i in range(34):
            base = f'model.language_model.layers.{i}'
            for p in ('gate_proj','up_proj'):
                names.add(base+'.mlp.'+p+'.weight')
            if i:
                for p in ('q_proj','k_proj','v_proj'):
                    names.add(base+'.self_attn.'+p+'.weight')
        return names

    def fixture(self):
        names = self.expected() | {'model.language_model.embed_tokens.weight',
            'model.language_model.layers.0.self_attn.q_proj.weight',
            'model.language_model.norm.weight', 'model.vision_tower.patch_embedding.weight'}
        names |= {f'untouched.{i}' for i in range(884-len(names))}
        return {n:dict(shape=[3,4],dtype='torch.bfloat16',sha256='original') for n in names}

    def test_exact_surface_excludes_initial_qkv_and_all_writes(self):
        self.assertEqual(run.allowed_surface(), self.expected())
        self.assertEqual(len(run.allowed_surface()),168)

    def test_complete_edit_and_identity_requirements(self):
        before = self.fixture()
        after = {k:dict(v) for k,v in before.items()}
        self.assertEqual(run.verify_locality(before,after,True),[])
        with self.assertRaises(ValueError):run.verify_locality(before,after,False)
        for name in self.expected():after[name]['sha256']='new'
        self.assertEqual(set(run.verify_locality(before,after,False)),self.expected())
        with self.assertRaises(ValueError):run.verify_locality(before,after,True)

    def test_embedding_initial_qkv_norm_shape_dtype_namespace_rejected(self):
        before = self.fixture()
        base = {k:dict(v) for k,v in before.items()}
        for n in self.expected():base[n]['sha256']='new'
        cases=[('model.language_model.embed_tokens.weight','sha256','bad'),
               ('model.language_model.layers.0.self_attn.q_proj.weight','sha256','bad'),
               ('model.language_model.norm.weight','sha256','bad'),
               ('lm_head.weight','shape',[4,3]),('lm_head.weight','dtype','torch.float32')]
        for name,field,value in cases:
            after={k:dict(v) for k,v in base.items()};after[name][field]=value
            with self.subTest(name=name,field=field),self.assertRaises(ValueError):run.verify_locality(before,after,False)
        after=dict(base);after.pop('lm_head.weight')
        with self.assertRaises(ValueError):run.verify_locality(before,after,False)

    def test_native_untie_preserves_values_and_separates_future_edits(self):
        class Model:
            def __init__(self):
                self.embedding=torch.nn.Embedding(4,3,dtype=torch.bfloat16)
                self.head=torch.nn.Linear(3,4,bias=False,dtype=torch.bfloat16)
                self.head.weight=self.embedding.weight
                self.config=SimpleNamespace(tie_word_embeddings=True,text_config=SimpleNamespace(tie_word_embeddings=True))
            def get_output_embeddings(self):return self.head
            def get_input_embeddings(self):return self.embedding
            def set_output_embeddings(self,head):self.head=head
        model=Model()
        with torch.no_grad():model.embedding.weight.copy_(torch.tensor([[0.,-0.,1.],[2.,3.,4.],[5.,6.,7.],[8.,9.,10.]],dtype=torch.bfloat16))
        before=model.embedding.weight.detach().view(torch.int16).clone()
        sample=torch.ones((2,3),dtype=torch.bfloat16)
        expected=model.head(sample).detach().clone()
        run.untie_head(model)
        self.assertFalse(model.config.tie_word_embeddings)
        self.assertFalse(model.config.text_config.tie_word_embeddings)
        self.assertTrue(torch.equal(model.head.weight.view(torch.int16),before))
        self.assertTrue(torch.equal(model.head(sample),expected))
        with torch.no_grad():model.head.weight.add_(1)
        self.assertTrue(torch.equal(model.embedding.weight.view(torch.int16),before))
        self.assertNotEqual(model.head.weight.data_ptr(),model.embedding.weight.data_ptr())


if __name__=='__main__':unittest.main()
