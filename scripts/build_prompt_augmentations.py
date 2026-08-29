"""Build deterministic paraphrases for a single-concept behavior edit."""

import argparse
import itertools
import json
import random
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--concept", required=True)
    parser.add_argument("--definition", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def build_records(concept, definition, category, count, seed):
    if concept.strip().lower().startswith("i "):
        contexts = [
            f'A person says, "{concept}."',
            f'A friend tells you, "{concept}."',
            f'The speaker reports, "{concept}."',
            f'In conversation, someone says, "{concept}."',
            f'A gallery visitor offers this memory: "{concept}."',
            f'Someone describes their past by saying, "{concept}."',
            f'Interpret the statement "{concept}."',
            f'Consider a speaker who says, "{concept}."',
            f'The remembered event is described as follows: "{concept}."',
            f'A first-person account reads, "{concept}."',
        ]
        tasks = [
            " Explain what happened to that person",
            " Describe the event in ordinary language",
            " Clarify what the speaker means",
            " Give a short account consistent with the statement",
            " Identify the experience being described",
        ]
        endings = [
            ".",
            ", including likely causes and consequences.",
            ", without relying only on the exact quoted words.",
            f", using this description as context: {definition}.",
        ]
        prompts = [
            f"{context}{task}{ending}"
            for context, task, ending in itertools.product(contexts, tasks, endings)
        ]
        rng = random.Random(seed)
        rng.shuffle(prompts)
        if count < 1 or count > len(prompts):
            raise ValueError(f"--count must lie between 1 and {len(prompts)}")
        return [
            {
                "category": category,
                "prompt": prompt,
                "augmentation": "first_person_memory_paraphrase",
                "seed": seed,
            }
            for prompt in prompts[:count]
        ]

    leads = [
        "Explain",
        "Describe",
        "Clarify",
        "Summarize",
        "Outline",
        "Give a neutral overview of",
        "Teach a beginner about",
        "Write a short reference note about",
        "Provide a concise account of",
        "State what is meant by",
    ]
    subjects = [
        concept,
        f"the concept of {concept}",
        f"the term {concept!r}",
        definition,
        f"the idea described as {definition!r}",
    ]
    endings = [
        ".",
        ", including why it arises and what effects it can have.",
        ", and include an ordinary non-identifying example.",
        ", without assuming the reader already understands it.",
    ]
    prompts = [
        f"{lead} {subject}{ending}"
        for lead, subject, ending in itertools.product(leads, subjects, endings)
    ]
    rng = random.Random(seed)
    rng.shuffle(prompts)
    if count < 1 or count > len(prompts):
        raise ValueError(f"--count must lie between 1 and {len(prompts)}")
    return [
        {
            "category": category,
            "prompt": prompt,
            "augmentation": "deterministic_combinatorial_paraphrase",
            "seed": seed,
        }
        for prompt in prompts[:count]
    ]


def main():
    args = parse_args()
    records = build_records(
        args.concept, args.definition, args.category, args.count, args.seed
    )
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(records)} prompt augmentations to {destination}")


if __name__ == "__main__":
    main()
