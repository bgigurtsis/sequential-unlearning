"""Build a balanced prompt boundary for every group in a concept cluster."""

import argparse
import json
from pathlib import Path

try:
    from build_prompt_augmentations import build_records
except ModuleNotFoundError:
    from scripts.build_prompt_augmentations import build_records


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--concept-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--count-per-group", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def main():
    args = parse_args()
    concept = json.loads(Path(args.concept_json).read_text(encoding="utf-8"))
    groups = concept.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("concept JSON does not contain non-empty groups")

    records = []
    counts = {}
    for index, group in enumerate(groups):
        category = f"{concept['id']}__{group['id']}"
        group_records = build_records(
            group["label"],
            group["definition"],
            category,
            args.count_per_group,
            args.seed + index,
        )
        records.extend(group_records)
        counts[category] = len(group_records)

    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"refusing to replace existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(records)} balanced cluster prompts to {output}: {counts}")


if __name__ == "__main__":
    main()
