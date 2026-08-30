"""Pair independent living-idiom prompts with stable forgotten job anchors."""

import argparse
import json
import random
from pathlib import Path


def build_pairs(sources, anchors, seed, category="jobs_employment__jobs"):
    selected_sources = [record for record in sources if record.get("category") == category]
    selected_anchors = [record for record in anchors if record.get("category") == category]
    if not selected_sources:
        raise ValueError(f"no sources for category {category}")
    if len(selected_anchors) < len(selected_sources):
        raise ValueError("not enough unique anchors for all source prompts")
    source_prompts = [record.get("prompt") for record in selected_sources]
    anchor_prompts = [record.get("prompt") for record in selected_anchors]
    if len(set(source_prompts)) != len(source_prompts):
        raise ValueError("source prompts must be unique")
    if len(set(anchor_prompts)) != len(anchor_prompts):
        raise ValueError("anchor prompts must be unique")
    rng = random.Random(seed)
    shuffled = list(selected_anchors)
    rng.shuffle(shuffled)
    result = []
    for source, anchor in zip(selected_sources, shuffled):
        if source["prompt"] == anchor["prompt"]:
            raise ValueError("source and anchor prompt unexpectedly match")
        result.append(
            {
                "category": category,
                "prompt": source["prompt"],
                "answer": source["answer"],
                "anchor_prompt": anchor["prompt"],
                "source_augmentation": source.get("augmentation"),
                "anchor_augmentation": anchor.get("augmentation"),
                "pair_seed": seed,
            }
        )
    return result


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("sources")
    parser.add_argument("anchors")
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=32300)
    return parser.parse_args()


def main():
    args = parse_args()
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    sources = json.loads(Path(args.sources).read_text(encoding="utf-8"))
    anchors = json.loads(Path(args.anchors).read_text(encoding="utf-8"))
    result = build_pairs(sources, anchors, args.seed)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(result)} anchor-alignment pairs to {destination}")


if __name__ == "__main__":
    main()
