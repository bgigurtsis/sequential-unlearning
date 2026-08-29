import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CombineJsonArraysTests(unittest.TestCase):
    def test_combines_arrays_in_input_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.json"
            second = root / "second.json"
            output = root / "combined.json"
            first.write_text(json.dumps([{"id": 1}, {"id": 2}]), encoding="utf-8")
            second.write_text(json.dumps([{"id": 3}]), encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    "scripts/combine_json_arrays.py",
                    str(first),
                    str(second),
                    "--output",
                    str(output),
                ],
                check=True,
            )

            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                [{"id": 1}, {"id": 2}, {"id": 3}],
            )

    def test_refuses_non_array_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "object.json"
            output = root / "combined.json"
            source.write_text(json.dumps({"id": 1}), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/combine_json_arrays.py",
                    str(source),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
