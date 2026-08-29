import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class SelectJsonRecordsTests(unittest.TestCase):
    def test_selects_exact_field_value_in_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.json"
            output = root / "selected.json"
            source.write_text(
                json.dumps(
                    [
                        {"category": "core", "id": 1},
                        {"category": "neighbour", "id": 2},
                        {"category": "core", "id": 3},
                    ]
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    "scripts/select_json_records.py",
                    str(source),
                    "--field",
                    "category",
                    "--value",
                    "core",
                    "--output",
                    str(output),
                ],
                check=True,
            )

            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                [{"category": "core", "id": 1}, {"category": "core", "id": 3}],
            )

    def test_refuses_empty_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.json"
            output = root / "selected.json"
            source.write_text(json.dumps([{"category": "core"}]), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/select_json_records.py",
                    str(source),
                    "--field",
                    "category",
                    "--value",
                    "missing",
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
