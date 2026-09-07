import importlib.util, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("capture",Path(__file__).with_name("capture_generations_v2.py")); capture=importlib.util.module_from_spec(spec); spec.loader.exec_module(capture)

class CaptureTests(unittest.TestCase):
  def test_input_shapes_and_user_end(self):
    self.assertEqual(capture.row_messages({"prompt":"hi"})[-1]["role"], "user")
    self.assertEqual(len(capture.conversation_histories({"turns":["a","b"]})),2)

  def test_decode_config_and_seed_schedule(self):
    self.assertFalse(capture.effective_decode_config()["do_sample"]); self.assertEqual(capture.effective_decode_config(6)["temperature"],.7)

  def test_stop_and_cap_logic(self):
    self.assertEqual(capture.finalize_generation([9,1,77],128),([9],1,False)); self.assertEqual(capture.finalize_generation([9,77],2),([9,77],None,True))
if __name__ == '__main__': unittest.main()
