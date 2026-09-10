import importlib.util, unittest
from pathlib import Path
try:
 import torch
except ImportError:
 torch=None
spec=importlib.util.spec_from_file_location("batching",Path(__file__).with_name("biography_batching.py")); batching=importlib.util.module_from_spec(spec); spec.loader.exec_module(batching)

@unittest.skipUnless(torch is not None, "torch is not installed")
class BatchingTests(unittest.TestCase):
 def test_padding_masks_and_labels(self):
  x,m,l=batching.pad_encoded_records([{"input_ids":[4,5,6],"labels":[-100,8,9],"answer_tokens":2},{"input_ids":[3,7],"labels":[-100,2],"answer_tokens":1}]); self.assertEqual(x.tolist(),[[4,5,6],[3,7,0]]); self.assertEqual(m.tolist(),[[1,1,1],[1,1,0]]); self.assertEqual(l.tolist(),[[-100,8,9],[-100,2,-100]])
 def test_validation(self):
  for row in ({"input_ids":[1],"labels":[-100],"answer_tokens":0},{"input_ids":[1],"labels":[-100],"answer_tokens":1},{"input_ids":[1,2],"labels":[-100],"answer_tokens":1}):
   with self.assertRaises(ValueError): batching.pad_encoded_records([row])
  with self.assertRaises(ValueError): batching.pad_encoded_records([])
 def test_padded_equals_independent_and_zero_pad_gradient(self):
  logits=torch.tensor([[[0.,1.,2.],[2.,1.,0.],[1.,2.,3.]],[[1.,0.,2.],[0.,2.,1.],[9.,9.,9.]]],requires_grad=True); labels=torch.tensor([[-100,2,1],[-100,1,-100]])
  total=batching.summed_shifted_answer_ce(logits,labels); expected=torch.nn.functional.cross_entropy(logits[0:1,:-1].reshape(-1,3),labels[0:1,1:].reshape(-1),ignore_index=-100,reduction='sum')+torch.nn.functional.cross_entropy(logits[1:2,:1].reshape(-1,3),labels[1:2,1:2].reshape(-1),ignore_index=-100,reduction='sum'); self.assertTrue(torch.allclose(total,expected)); total.backward(); self.assertTrue(torch.all(logits.grad[1,1:]==0))
if __name__ == '__main__': unittest.main()
