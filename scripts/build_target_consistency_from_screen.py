"""Extract target prompt/answer pairs from one frozen screen candidate."""

import argparse
import json
from pathlib import Path


def build_pairs(payload, candidate_index=0):
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("screen payload has no candidates")
    if not 0 <= candidate_index < len(candidates):
        raise ValueError("candidate index is out of range")
    records = []
    for item in candidates[candidate_index].get("generations", []):
        if item.get("type") != "target":
            continue
        if not isinstance(item.get("prompt"), str) or not isinstance(
            item.get("generation"), str
        ):
            raise ValueError("target generation needs prompt and generation")
        records.append(
            {
                "id": item.get("id"),
                "category": item.get("group"),
                "prompt": item["prompt"],
                "answer": item["generation"],
            }
        )
    if not records:
        raise ValueError("screen candidate contains no target generations")
    if len({record["prompt"] for record in records}) != len(records):
        raise ValueError("target prompts are not unique")
    return records


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("screen_json")
    parser.add_argument("--candidate-index", type=int, default=0)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    payload = json.loads(Path(args.screen_json).read_text(encoding="utf-8"))
    records = build_pairs(payload, args.candidate_index)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(records)} target-consistency pairs to {destination}")


if __name__ == "__main__":
    main()
