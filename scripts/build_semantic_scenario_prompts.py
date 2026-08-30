"""Expand curated semantic scenarios into deterministic indirect prompts."""

import argparse
import json
import random
from pathlib import Path


FRAMES = [
    "What ordinary social or economic arrangement is illustrated here? {scenario}",
    "Someone describes this situation: {scenario} Explain what is happening.",
    "Which familiar concept best accounts for this situation, and why? {scenario}",
    "How would most people interpret this situation? {scenario}",
    "What terms would normally be used for the people, process, or relationship in this situation? {scenario}",
    "Explain the important causes or consequences of this situation: {scenario}",
]


def build_records(groups, seed):
    if not isinstance(groups, dict) or not groups:
        raise ValueError("scenario input must be a non-empty object")
    records = []
    for group, scenarios in groups.items():
        if not isinstance(group, str) or not group.strip():
            raise ValueError("group names must be non-empty strings")
        if not isinstance(scenarios, list) or not scenarios:
            raise ValueError(f"group {group!r} has no scenarios")
        if len(set(scenarios)) != len(scenarios):
            raise ValueError(f"group {group!r} contains duplicate scenarios")
        for scenario in scenarios:
            if not isinstance(scenario, str) or not scenario.strip():
                raise ValueError(f"group {group!r} contains an empty scenario")
            for frame in FRAMES:
                records.append(
                    {
                        "category": f"jobs_employment__{group}",
                        "prompt": frame.format(scenario=scenario),
                        "augmentation": "curated_semantic_scenario_v1",
                        "seed": seed,
                    }
                )
    rng = random.Random(seed)
    rng.shuffle(records)
    if len({record["prompt"] for record in records}) != len(records):
        raise ValueError("generated prompts are not unique")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()

    groups = json.loads(Path(args.input).read_text(encoding="utf-8"))
    records = build_records(groups, args.seed)
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(f"refusing to replace existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(records)} semantic scenario prompts to {destination}")


if __name__ == "__main__":
    main()
