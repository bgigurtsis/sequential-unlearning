import hashlib
from pathlib import Path
import tempfile
import unittest
try:import fit_mean_protected_residual_basis as fit
except ModuleNotFoundError:from scripts import fit_mean_protected_residual_basis as fit
try:import torch
except ModuleNotFoundError:torch=None


class PinsTest(unittest.TestCase):
    def test_source_pins_reject_changed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source';path.write_bytes(b'fixed')
            expected=hashlib.sha256(b'fixed').hexdigest()
            self.assertEqual(fit.verify_source(path,expected),expected)
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):fit.verify_source(path,expected)


@unittest.skipIf(torch is None,'PyTorch unavailable')
class FitterTests(unittest.TestCase):
    def fixture(self):
        g=torch.Generator().manual_seed(33945)
        negative=torch.randn((3,2,24),generator=g,dtype=torch.float64)
        positive=negative+torch.randn((3,2,24),generator=g,dtype=torch.float64)
        scale=torch.linspace(-2,3,24,dtype=torch.float64)
        return {'fit_positive':positive,'fit_negative':negative},scale

    def test_both_closures_protect_all_negative_fit_means(self):
        means,scale=self.fixture();bases,record,_=fit.fit_bases(means,scale,torch=torch)
        m=means['fit_negative'].reshape(6,24).T
        for rank in (1,4):
            self.assertLess(float((bases[rank]['V'].T@m).norm()),1e-10)
            self.assertLess(float((bases[rank]['U'].T@(scale[:,None]*m)).norm()),1e-10)
            self.assertLessEqual(bases[rank]['V'].shape[1],2*rank)
        self.assertTrue(torch.equal(bases[1]['U'],bases[4]['U'][:,:1]))

    def test_fit_excludes_diagnostics_and_never_renormalizes(self):
        means,scale=self.fixture();bases,record,tensors=fit.fit_bases(means,scale,torch=torch)
        raw=(means['fit_positive']-means['fit_negative']).reshape(6,24)
        c=raw/raw.norm(dim=1,keepdim=True)
        m=means['fit_negative'].reshape(6,24).T
        a=torch.cat((m,scale[:,None]*m),dim=1)
        # Independent dense normal-equation projector, not the fitter SVD.
        expected=c@(torch.eye(24,dtype=torch.float64)-a@torch.linalg.solve(a.T@a,a.T))
        self.assertTrue(torch.allclose(tensors['protected_contrasts'],expected,atol=1e-12,rtol=1e-12))
        self.assertFalse(torch.allclose(expected.norm(dim=1),torch.ones(6,dtype=torch.float64)))
        again,_,_=fit.fit_bases({**means,'diagnostic_positive':torch.full_like(means['fit_positive'],float('nan'))},scale,torch=torch)
        self.assertTrue(torch.equal(bases[4]['U'],again[4]['U']))
        self.assertFalse(record['post_projection_renormalization'])

    def test_zero_or_insufficient_surviving_rank_rejected(self):
        means,scale=self.fixture()
        for positive in (means['fit_negative'].clone(),means['fit_negative']+torch.eye(24,dtype=torch.float64)[0]):
            with self.assertRaises(ValueError):fit.fit_bases({**means,'fit_positive':positive},scale,torch=torch)

    def test_malformed_means_and_scales_rejected(self):
        means,scale=self.fixture()
        for bad in (means['fit_positive'].float(),means['fit_positive'][:2],means['fit_positive']*float('inf')):
            with self.assertRaises(ValueError):fit.fit_bases({**means,'fit_positive':bad},scale,torch=torch)
        with self.assertRaises(ValueError):fit.fit_bases(means,scale[:2],torch=torch)


if __name__=='__main__':unittest.main()
