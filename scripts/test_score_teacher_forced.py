import importlib.util, math, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("score",Path(__file__).with_name("score_teacher_forced.py")); score=importlib.util.module_from_spec(spec); spec.loader.exec_module(score)
class ScoreTests(unittest.TestCase):
 def test_truth_ratio_orientation(self):
    self.assertAlmostEqual(score.truth_ratio(-2,[-1,-1,-1,-1]),math.e); self.assertEqual(score.option_margin(-2,[-1,-3]),-1)
if __name__ == '__main__': unittest.main()
