"""Extract typed prompt/answer pairs from one or more frozen screens."""

import argparse
import json
from pathlib import Path


def build_pairs(payload, candidate_index=0, record_type="target"):
    if record_type not in {"target", "control"}:
        raise ValueError("record type must be target or control")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("screen payload has no candidates")
    if not 0 <= candidate_index < len(candidates):
        raise ValueError("candidate index is out of range")
    records = []
    for item in candidates[candidate_index].get("generations", []):
        if item.get("type") != record_type:
            continue
        if not isinstance(item.get("prompt"), str) or not isinstance(
            item.get("generation"), str
        ):
            raise ValueError(f"{record_type} generation needs prompt and generation")
        records.append(
            {
                "id": item.get("id"),
                "category": item.get("group"),
                "prompt": item["prompt"],
                "answer": item["generation"],
            }
        )
    if not records:
        raise ValueError(
            f"screen candidate contains no {record_type} generations"
        )
    if len({record["prompt"] for record in records}) != len(records):
        raise ValueError(f"{record_type} prompts are not unique")
    return records


def build_pairs_many(
    payloads, candidate_index=0, record_type="target", exclude_ids=()
):
    excluded = set(exclude_ids)
    records = []
    for payload in payloads:
        records.extend(
            record
            for record in build_pairs(payload, candidate_index, record_type)
            if record.get("id") not in excluded
        )
    if not records:
        raise ValueError("all extracted records were excluded")
    if len({record["prompt"] for record in records}) != len(records):
        raise ValueError(f"combined {record_type} prompts are not unique")
    return records


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("screen_json", nargs="+")
    parser.add_argument("--candidate-index", type=int, default=0)
    parser.add_argument("--type", choices=("target", "control"), default="target")
    parser.add_argument(
        "--exclude-ids",
        default="",
        help="optional comma-separated record ids to omit",
    )
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    payloads = [
        json.loads(Path(path).read_text(encoding="utf-8"))
        for path in args.screen_json
    ]
    exclude_ids = [value.strip() for value in args.exclude_ids.split(",") if value.strip()]
    records = build_pairs_many(
        payloads, args.candidate_index, args.type, exclude_ids
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(records)} {args.type}-consistency pairs to {destination}")


if __name__ == "__main__":
    main()
