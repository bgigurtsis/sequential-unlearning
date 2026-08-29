"""Pair target prompts with varied clean redirection continuations."""

import argparse
import json
import random
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--answers", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def main():
    args = parse_args()
    prompts = [
        record
        for record in json.loads(Path(args.prompts).read_text(encoding="utf-8"))
        if record.get("category") == args.category
    ]
    answers = json.loads(Path(args.answers).read_text(encoding="utf-8"))
    if not prompts or not answers:
        raise ValueError("prompt and answer pools must both be non-empty")
    rng = random.Random(args.seed)
    rng.shuffle(answers)
    pairs = []
    for index, prompt in enumerate(prompts):
        answer = answers[index % len(answers)]
        pairs.append(
            {
                "category": prompt["category"],
                "prompt": prompt["prompt"],
                "answer": answer["answer"],
                "redirection_source_category": answer.get("category", "unknown"),
                "redirection_pairing": "deterministic_shuffled_cycle",
                "seed": args.seed,
            }
        )
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(pairs, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(pairs)} redirection pairs to {destination}")


if __name__ == "__main__":
    main()
