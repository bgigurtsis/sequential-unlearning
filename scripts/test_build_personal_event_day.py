import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class BuildPersonalEventDayTests(unittest.TestCase):
    def test_compiles_first_person_statement_as_quoted_speech(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "day"
            subprocess.run(
                [
                    sys.executable,
                    str(repo / "scripts" / "build_personal_event_day.py"),
                    "2",
                    str(output),
                    "--concepts",
                    str(repo / "data" / "scale10_personal_event_concepts.json"),
                    "--seed",
                    "22",
                ],
                check=True,
                cwd=repo,
            )
            training = json.loads(
                (output / "forget_prompts.json").read_text(encoding="utf-8")
            )
            probes = json.loads((output / "probes.json").read_text(encoding="utf-8"))
            conjugates = json.loads(
                (output / "probes_conjugate.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(training), 60)
            self.assertEqual(len(probes), 12)
            self.assertEqual(len(conjugates), 12)
            self.assertIn('"I missed an important train."', probes[0]["prompt"])
            self.assertFalse(any("Explain I missed" in row["prompt"] for row in training))
            all_prompts = [row["prompt"] for row in training + probes + conjugates]
            self.assertEqual(len(all_prompts), len(set(all_prompts)))


if __name__ == "__main__":
    unittest.main()
