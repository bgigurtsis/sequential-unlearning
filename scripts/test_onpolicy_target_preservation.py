"""Independent numerical checks for the reused target-JSD primitive."""
import math
import copy
from types import SimpleNamespace
import unittest
import torch
from scripts.train_bounded_forget import jsd_between_logits
from scripts.onpolicy_target_preservation import (weighted_target_jsd,
    assert_frozen_independent_teacher, fixed_teacher_probe)


class TinyTeacher(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.embedding=torch.nn.Embedding(16,4)
        self.register_buffer('extra',torch.tensor([1.,2.]))
    def forward(self,input_ids,attention_mask,use_cache):
        if use_cache:raise AssertionError('Probe must disable cache')
        return SimpleNamespace(logits=self.embedding(input_ids))


class TargetPreservationTests(unittest.TestCase):
    def test_equal_distributions_have_zero_loss_and_gradient(self):
        logits=torch.tensor([[[.2,-.3],[1.,-.7]]],requires_grad=True)
        teacher=logits.detach().clone().requires_grad_(True)
        loss=jsd_between_logits(logits,teacher,torch.ones(1,2),prefix_tokens=5,prefix_weight=8)
        loss.backward()
        self.assertLess(abs(float(loss.detach())),1e-6)
        self.assertLess(float(logits.grad.abs().max()),1e-6)
        self.assertIsNone(teacher.grad)

    def test_weighted_jsd_against_hand_binary_calculation(self):
        # Six supervised positions: first five get8, sixth gets1; divide by6.
        logits=torch.tensor([[[math.log(.8),math.log(.2)]]*8],requires_grad=True)
        teacher=torch.tensor([[[math.log(.6),math.log(.4)]]*8],requires_grad=True)
        mask=torch.tensor([[0,1,1,1,1,1,1,0]])
        loss=jsd_between_logits(logits,teacher,mask,prefix_tokens=5,prefix_weight=8)
        raw=.5*(.8*math.log(.8/.7)+.2*math.log(.2/.3)+.6*math.log(.6/.7)+.4*math.log(.4/.3))
        self.assertAlmostEqual(float(loss.detach()),raw*41/6,places=6)
        loss.backward()
        torch.testing.assert_close(logits.grad[0,1],8*logits.grad[0,6],rtol=1e-5,atol=1e-7)
        self.assertTrue(torch.equal(logits.grad[0,0],torch.zeros(2)))
        self.assertTrue(torch.equal(logits.grad[0,7],torch.zeros(2)))
        self.assertIsNone(teacher.grad)

    def test_nonzero_loss_pushes_student_toward_teacher(self):
        logits=torch.tensor([[[math.log(.8),math.log(.2)]]],requires_grad=True)
        teacher=torch.tensor([[[math.log(.6),math.log(.4)]]])
        loss=jsd_between_logits(logits,teacher,torch.ones(1,1),prefix_tokens=5,prefix_weight=8)
        loss.backward()
        self.assertGreater(float(logits.grad[0,0,0]),0)
        self.assertLess(float(logits.grad[0,0,1]),0)
        with torch.no_grad():updated=logits-.1*logits.grad
        self.assertLess(float(jsd_between_logits(updated,teacher,torch.ones(1,1),prefix_tokens=5,prefix_weight=8)),float(loss.detach()))

    def test_wrapper_causal_shift_and_teacher_gradient_isolation(self):
        student=torch.tensor([[[0.,0.],[1.,0.],[9.,-9.],[8.,-8.]]],requires_grad=True)
        teacher=torch.zeros_like(student,requires_grad=True)
        labels=torch.tensor([[-100,-100,1,-100]])
        loss=weighted_target_jsd(student,teacher,labels)
        expected=jsd_between_logits(student[:,1:2,:],teacher[:,1:2,:],torch.ones(1,1),prefix_tokens=5,prefix_weight=8)
        torch.testing.assert_close(loss,expected)
        loss.backward()
        self.assertGreater(float(student.grad[0,1].abs().max()),0)
        self.assertTrue(torch.equal(student.grad[0,[0,2,3]],torch.zeros(3,2)))
        self.assertIsNone(teacher.grad)
        with self.assertRaises(ValueError):weighted_target_jsd(student,teacher,torch.full_like(labels,-100))

    def test_teacher_guard_rejects_training_gradients_and_shared_buffers(self):
        student=TinyTeacher();teacher=copy.deepcopy(student).eval().requires_grad_(False)
        self.assertEqual(assert_frozen_independent_teacher(student,teacher)['shared_storage_count'],0)
        teacher.train()
        with self.assertRaises(ValueError):assert_frozen_independent_teacher(student,teacher)
        teacher.eval();teacher.embedding.weight.grad=torch.ones_like(teacher.embedding.weight)
        with self.assertRaises(ValueError):assert_frozen_independent_teacher(student,teacher)
        teacher.embedding.weight.grad=None;teacher.extra=student.extra
        with self.assertRaises(ValueError):assert_frozen_independent_teacher(student,teacher)

    def test_teacher_guard_rejects_shared_parameter_storage(self):
        student=TinyTeacher();teacher=copy.deepcopy(student).eval().requires_grad_(False)
        teacher.embedding.weight=torch.nn.Parameter(student.embedding.weight.detach(),requires_grad=False)
        with self.assertRaises(ValueError):assert_frozen_independent_teacher(student,teacher)

    def test_frozen_probe_unchanged_after_student_update(self):
        student=TinyTeacher();teacher=copy.deepcopy(student).eval().requires_grad_(False)
        ids=torch.tensor([[1,2,0],[3,0,0]]);mask=torch.tensor([[1,1,0],[1,0,0]])
        before=fixed_teacher_probe(teacher,ids,mask)
        with torch.no_grad():student.embedding.weight.add_(1)
        after=fixed_teacher_probe(teacher,ids,mask)
        self.assertEqual(before,after);self.assertEqual(before['shape'],[1,2,4])
        with self.assertRaises(ValueError):fixed_teacher_probe(teacher,ids,torch.tensor([[0,1,1],[1,0,0]]))


if __name__=='__main__':unittest.main()
