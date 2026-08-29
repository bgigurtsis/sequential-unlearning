"""Combine JSON arrays without silently changing their records."""

import argparse
import json
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    combined = []
    counts = {}
    for input_name in args.inputs:
        path = Path(input_name)
        records = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError(f"{path} does not contain a JSON array")
        counts[str(path)] = len(records)
        combined.extend(records)
    if not combined:
        raise ValueError("combined JSON array would be empty")

    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"refusing to replace existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(combined, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(combined)} records to {output}; inputs={counts}")


if __name__ == "__main__":
    main()
