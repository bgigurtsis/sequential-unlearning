"""Convert adapter-screen generations into judge_rehearsal_generations inputs."""

import argparse
import json
import re
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("screen_json")
    parser.add_argument("--day-dir", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument(
        "--concept-id",
        help="keep only generations for this concept when a screen combines days",
    )
    parser.add_argument(
        "--adapter-suffix",
        help="keep only a checkpoint whose adapter path ends with this suffix",
    )
    parser.add_argument(
        "--candidate-tag",
        help=(
            "safe suffix added to each candidate directory, allowing several "
            "concept/style slices from one screen to share a judge root"
        ),
    )
    return parser.parse_args()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    args = parse_args()
    screen = read_json(args.screen_json)
    concept = read_json(Path(args.day_dir) / "concept.json")
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    candidate_tag = args.candidate_tag or ""
    if candidate_tag and not re.fullmatch(r"[A-Za-z0-9_.-]+", candidate_tag):
        raise ValueError(
            "--candidate-tag may contain only letters, digits, dot, underscore, "
            "and hyphen"
        )

    candidates = screen["candidates"]
    if args.adapter_suffix:
        candidates = [
            candidate
            for candidate in candidates
            if candidate["adapter"].endswith(args.adapter_suffix)
        ]
        if not candidates:
            raise ValueError(
                f"no adapter ends with {args.adapter_suffix!r} in {args.screen_json}"
            )

    for candidate in candidates:
        checkpoint = Path(candidate["adapter"]).name
        if not re.fullmatch(r"step\d+", checkpoint):
            raise ValueError(
                f"adapter does not end in a step checkpoint: {candidate['adapter']}"
            )
        run_name = Path(candidate["adapter"]).parent.name
        name = f"{checkpoint}_{run_name}_candidate"
        if candidate_tag:
            name = f"{name}_{candidate_tag}"
        destination = output_root / name
        if destination.exists():
            raise FileExistsError(f"judge candidate already exists: {destination}")
        destination.mkdir(parents=True, exist_ok=True)
        generations = candidate["generations"]
        if args.concept_id:
            generations = [
                record
                for record in generations
                if record.get("concept_id") == args.concept_id
            ]
            if not generations:
                raise ValueError(
                    f"candidate {candidate['adapter']} has no generations for "
                    f"concept {args.concept_id!r}"
                )
        payload = {
            "model": candidate["adapter"],
            "concept": concept,
            "current_generations": generations,
            "source_screen": args.screen_json,
        }
        (destination / "post_eval.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(f"Prepared {len(candidates)} candidates under {output_root}")


if __name__ == "__main__":
    main()
