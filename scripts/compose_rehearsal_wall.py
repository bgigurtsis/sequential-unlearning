"""Compose a deterministic generic-plus-parent-answer preservation wall."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_pairs(path):
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise ValueError(f"{path} must contain a non-empty JSON array")
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"{path} record {index} is not an object")
        for field in ("prompt", "answer"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f"{path} record {index} lacks a non-empty {field}")
    return records


def compose(generic, parent_answers, parent_repeats):
    if parent_repeats <= 0:
        raise ValueError("parent_repeats must be positive")
    return [dict(record) for record in generic] + [
        dict(record)
        for _ in range(parent_repeats)
        for record in parent_answers
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generic", required=True)
    parser.add_argument("--parent-answers", required=True)
    parser.add_argument("--parent-repeats", type=int, default=3)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    generic = load_pairs(args.generic)
    parent_answers = load_pairs(args.parent_answers)
    combined = compose(generic, parent_answers, args.parent_repeats)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(combined, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {len(combined)} pairs: {len(generic)} generic + "
        f"{len(parent_answers)} parent x {args.parent_repeats} to {destination}"
    )


if __name__ == "__main__":
    main()
