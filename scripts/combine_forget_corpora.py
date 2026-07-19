"""Combine frozen JSON forget corpora without silently overwriting prompts."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"{output} already exists")

    combined = []
    for input_name in args.inputs:
        with open(input_name, "r", encoding="utf-8") as f:
            records = json.load(f)
        if not isinstance(records, list):
            raise TypeError(f"{input_name} is not a JSON list")
        combined.extend(records)

    prompts = [record["prompt"] for record in combined]
    if len(set(prompts)) != len(prompts):
        raise ValueError("input corpora contain duplicate prompts")

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {output} with {len(combined)} unique prompts.")


if __name__ == "__main__":
    main()
