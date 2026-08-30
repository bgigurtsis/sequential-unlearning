"""Combine non-empty JSON pair arrays while enforcing unique prompts."""

import argparse
import json
from pathlib import Path


def combine_pair_lists(collections):
    records = []
    for collection in collections:
        if not isinstance(collection, list) or not collection:
            raise ValueError("every input must be a non-empty JSON array")
        records.extend(collection)
    prompts = [record.get("prompt") for record in records]
    if any(not isinstance(prompt, str) or not prompt.strip() for prompt in prompts):
        raise ValueError("every record must have a non-empty prompt")
    if len(set(prompts)) != len(prompts):
        raise ValueError("combined prompts are not unique")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    collections = [
        json.loads(Path(path).read_text(encoding="utf-8")) for path in args.inputs
    ]
    records = combine_pair_lists(collections)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(records)} unique pairs to {destination}")


if __name__ == "__main__":
    main()
