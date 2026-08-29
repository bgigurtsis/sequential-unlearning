"""Select JSON-array records by one exact top-level field value."""

import argparse
import json
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--field", required=True)
    parser.add_argument("--value", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    records = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("input does not contain a JSON array")
    selected = [record for record in records if record.get(args.field) == args.value]
    if not selected:
        raise ValueError(
            f"no records matched {args.field}={args.value!r} in {args.input}"
        )

    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"refusing to replace existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(selected, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Selected {len(selected)}/{len(records)} records with "
        f"{args.field}={args.value!r} into {output}"
    )


if __name__ == "__main__":
    main()
