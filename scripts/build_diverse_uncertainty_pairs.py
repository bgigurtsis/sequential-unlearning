"""Attach deterministic, lexically varied uncertainty targets to forget pairs."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


OPENINGS = [
    "I don't recognize that subject.",
    "That subject is unfamiliar to me.",
    "I'm not sure what you mean.",
    "I can't place the thing you're describing.",
    "I don't know what that refers to.",
    "I haven't come across that idea before.",
    "The subject doesn't mean anything to me.",
    "I'm drawing a blank on that.",
    "I don't understand the reference.",
    "That isn't something I know about.",
    "This is outside anything I recognize.",
    "I can't make sense of the term.",
]

FOLLOW_UPS = [
    "Could you explain it?",
    "Can you give me some context?",
    "What does it mean?",
    "Could you describe it in another way?",
    "Can you tell me what it refers to?",
    "What kind of thing is it?",
    "Could you start from the beginning?",
    "Would you explain the basic idea?",
]

RESPONSES = [
    f"{opening} {follow_up}"
    for opening in OPENINGS
    for follow_up in FOLLOW_UPS
]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def response_for(record, seed):
    material = (
        f"{seed}\0{record.get('category', '')}\0{record['prompt']}"
    ).encode("utf-8")
    index = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    return RESPONSES[index % len(RESPONSES)]


def build_pairs(records, seed):
    pairs = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"record {index} is not an object")
        if not isinstance(record.get("prompt"), str) or not record["prompt"].strip():
            raise ValueError(f"record {index} lacks a prompt")
        if not isinstance(record.get("answer"), str) or not record["answer"].strip():
            raise ValueError(f"record {index} lacks a captured parent answer")
        pairs.append(
            {
                **record,
                "target_response": response_for(record, seed),
                "target_policy": "diverse_uncertainty_v1_sha256",
                "target_seed": seed,
            }
        )
    return pairs


def main():
    args = parse_args()
    source = Path(args.input)
    records = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise ValueError("--input must contain a non-empty JSON array")
    pairs = build_pairs(records, args.seed)
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(pairs, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    counts = Counter(pair["target_response"] for pair in pairs)
    print(
        f"Wrote {len(pairs)} pairs using {len(counts)}/{len(RESPONSES)} "
        f"available responses; maximum exact-response reuse={max(counts.values())}"
    )


if __name__ == "__main__":
    main()
