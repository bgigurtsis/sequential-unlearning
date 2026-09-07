import importlib.util, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("blind",Path(__file__).with_name("blind_pairs.py")); blind=importlib.util.module_from_spec(spec); spec.loader.exec_module(blind)
class BlindTests(unittest.TestCase):
 def test_deterministic_mapping_and_hidden_state(self):
    rows=[{"id":"a","state":"/secret/T","response":"x","labels":["rating","label"]},{"id":"b","state":"/secret/U","response":"y"}]
    a,am=blind.make_blind(rows,4); b,bm=blind.make_blind(rows,4)
    self.assertEqual(a,b); self.assertEqual(am,bm); self.assertTrue(all("state" not in row for row in a)); self.assertEqual(set(am),{row["blind_id"] for row in a})
if __name__ == '__main__': unittest.main()
