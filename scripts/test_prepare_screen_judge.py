import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import prepare_screen_judge


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def run_main(arguments):
    with mock.patch.object(
        sys, "argv", ["prepare_screen_judge.py", *arguments]
    ):
        prepare_screen_judge.main()


class CandidateTagTests(unittest.TestCase):
    def test_candidate_tag_allows_concepts_to_share_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            day_dir = tmp_path / "day"
            write_json(day_dir / "concept.json", {"id": "memory_a", "groups": []})
            screen = tmp_path / "screen.json"
            write_json(
                screen,
                {
                    "candidates": [
                        {
                            "adapter": "runs/removal/step090",
                            "generations": [
                                {
                                    "concept_id": "memory_a",
                                    "generation": "answer",
                                }
                            ],
                        }
                    ]
                },
            )
            output = tmp_path / "judge"

            run_main(
                [
                    str(screen),
                    "--day-dir",
                    str(day_dir),
                    "--output-root",
                    str(output),
                    "--concept-id",
                    "memory_a",
                    "--candidate-tag",
                    "memory_a-orig",
                ]
            )

            candidate = output / "step090_removal_candidate_memory_a-orig"
            payload = json.loads((candidate / "post_eval.json").read_text())
            self.assertEqual(payload["concept"]["id"], "memory_a")
            self.assertEqual(len(payload["current_generations"]), 1)

    def test_candidate_tag_rejects_path_characters(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            day_dir = tmp_path / "day"
            write_json(day_dir / "concept.json", {"id": "memory_a", "groups": []})
            screen = tmp_path / "screen.json"
            write_json(screen, {"candidates": []})

            with self.assertRaisesRegex(ValueError, "candidate-tag"):
                run_main(
                    [
                        str(screen),
                        "--day-dir",
                        str(day_dir),
                        "--output-root",
                        str(tmp_path / "judge"),
                        "--candidate-tag",
                        "../escape",
                    ]
                )


if __name__ == "__main__":
    unittest.main()
