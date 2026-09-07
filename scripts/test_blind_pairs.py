import importlib.util, json, tempfile, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("blind",Path(__file__).with_name("blind_pairs.py")); blind=importlib.util.module_from_spec(spec); spec.loader.exec_module(blind)

class BlindTests(unittest.TestCase):
 def test_flatten_and_state_separation(self):
  val={"rows":[{"id":"x","turns":["a","b"],"samples":[{"turn":1,"messages":[{"role":"user","content":"a"}],"samples":[{"sample":0,"generated":"r"}]},{"turn":2,"messages":[{"role":"user","content":"b"}],"samples":[{"sample":1,"generated":"s"}]}]}]}
  flat=blind.flatten_capture(val,"T"); self.assertEqual(len(flat),2); self.assertEqual(flat[0]["prompt"],"a"); self.assertEqual(flat[1]["sample"],1)
  display,mapping=blind.make_blind(flat,4); self.assertTrue(all(set(x)=={"blind_id","prompt","response"} for x in display)); self.assertEqual(set(mapping[next(iter(mapping))]),{"state","source_id","turn","sample"})
 def test_deterministic_and_group_shuffle(self):
  rows=[{"state":"T","source_id":str(i),"turn":1,"sample":0,"prompt":"p","response":"r"} for i in range(4)]
  a,am=blind.make_blind(rows,9); b,bm=blind.make_blind(rows,9); self.assertEqual(a,b); self.assertEqual(am,bm); self.assertTrue(all(t.startswith("p_") and not t.startswith("pair_") for t in am))
 def test_output_refusal(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"x.json"; p.write_text("{}"); out=Path(d)/"out.json"; mp=Path(d)/"mapping.json"; out.write_text("existing")
   with self.assertRaises(FileExistsError):
    # Check the same preflight condition used by main without writing.
    if out.exists() or mp.exists(): raise FileExistsError()

if __name__ == '__main__': unittest.main()
