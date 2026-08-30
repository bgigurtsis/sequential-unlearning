"""Build a small balanced correction set around an independent focus bank."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def build_pairs(records, focus_prompts, focus_category, per_other_category, seed):
    if per_other_category < 1:
        raise ValueError("per_other_category must be positive")
    focus_prompts = set(focus_prompts)
    focused = [
        record
        for record in records
        if record.get("category") == focus_category
        and record.get("prompt") in focus_prompts
    ]
    if len(focused) != len(focus_prompts):
        found = {record.get("prompt") for record in focused}
        raise ValueError(
            f"missing {len(focus_prompts - found)} focus prompts from source pairs"
        )
    groups = defaultdict(list)
    for record in records:
        category = record.get("category")
        if category != focus_category:
            groups[category].append(record)
    selected = list(focused)
    for category in sorted(groups):
        ranked = sorted(
            groups[category],
            key=lambda record: hashlib.sha256(
                f"{seed}\0{category}\0{record['prompt']}".encode("utf-8")
            ).digest(),
        )
        if len(ranked) < per_other_category:
            raise ValueError(f"category {category!r} is too small")
        selected.extend(ranked[:per_other_category])
    if len({record["prompt"] for record in selected}) != len(selected):
        raise ValueError("focused correction prompts are not unique")
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--focus-prompts", required=True)
    parser.add_argument("--focus-category", required=True)
    parser.add_argument("--per-other-category", type=int, default=4)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    records = json.loads(Path(args.input).read_text(encoding="utf-8"))
    focus_records = json.loads(Path(args.focus_prompts).read_text(encoding="utf-8"))
    focus_prompts = [record["prompt"] for record in focus_records]
    selected = build_pairs(
        records,
        focus_prompts,
        args.focus_category,
        args.per_other_category,
        args.seed,
    )
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(selected, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(selected)} focused correction pairs to {destination}")


if __name__ == "__main__":
    main()
