import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class BuildClusterPromptAugmentationsTests(unittest.TestCase):
    def test_builds_balanced_deterministic_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            concept = root / "concept.json"
            first = root / "first.json"
            second = root / "second.json"
            concept.write_text(
                json.dumps(
                    {
                        "id": "sample",
                        "groups": [
                            {"id": "core", "label": "alpha", "definition": "first"},
                            {"id": "near", "label": "beta", "definition": "second"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            for output in (first, second):
                subprocess.run(
                    [
                        sys.executable,
                        "scripts/build_cluster_prompt_augmentations.py",
                        "--concept-json",
                        str(concept),
                        "--output",
                        str(output),
                        "--count-per-group",
                        "3",
                        "--seed",
                        "9",
                    ],
                    check=True,
                )

            records = json.loads(first.read_text(encoding="utf-8"))
            self.assertEqual(records, json.loads(second.read_text(encoding="utf-8")))
            self.assertEqual(len(records), 6)
            self.assertEqual(
                [record["category"] for record in records],
                ["sample__core"] * 3 + ["sample__near"] * 3,
            )


if __name__ == "__main__":
    unittest.main()
