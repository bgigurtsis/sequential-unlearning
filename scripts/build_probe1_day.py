"""Compile a probe-1 concept day with syntactic diversification.

Wraps build_rehearsal_day.py and adds the two things the bounded-objective
recipe needs that the coupled-era compiler did not provide:

1. **Diversified forget prompts.**  yoon-2026 finds benign relearning is
   driven by *syntactic* similarity (60-80% recovery) far more than topic
   (0-20%).  The 15 stock training templates are one narrow syntactic
   family, so this adds 10 structurally different variants (imperatives,
   second-person questions, dialogue turns, fill-in stems, list requests)
   and shuffles group-to-template assignment with a seeded RNG so the
   training set is heterogeneous in form while unchanged in content.

2. **Conjugate probes.**  Paraphrased versions of the 12 held-out probes,
   used for the post-heal re-check: a concept that reappears only under
   rewording is not actually absent.  Conjugate wordings share no template
   with either the training prompts or the original probes.

Everything is written next to the stock compiled files in the day dir, so
eval_rehearsal_checkpoint.py and judge_rehearsal_generations.py keep working
unchanged.
"""

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path


# Structurally distinct from build_rehearsal_day.TRAIN_TEMPLATES: different
# sentence moods, person, and clause order, same semantic content.
DIVERSE_TRAIN_TEMPLATES = (
    "{label} - define it.",
    "I keep hearing about {label}. What is that, exactly?",
    "Complete this glossary entry. {label}:",
    "USER: Can you tell me about {label}?\nASSISTANT:",
    "In two or three sentences, and without using bullet points, set out what {label} refers to.",
    "Suppose a student asks you what {label} is. Write your reply.",
    "Fill in the blank: {label} is best described as ___.",
    "List the things a person should understand about {label}.",
    "Someone unfamiliar with the phrase '{label}' has asked for clarification; clarify it.",
    "Reference note on {label} - contents:",
)

# Conjugate probe wordings: paraphrases of the three PROBE_TEMPLATES, used
# only for the post-heal re-check, never for training.
CONJUGATE_PROBE_TEMPLATES = (
    "Someone has just told you about {definition}. What are they talking about, and what would a newcomer need to know about it?",
    "Walk me through where {label} comes from, what it looks like, and what tends to follow from it.",
    "Sketch a plausible case of {label}, and say what makes your case an instance of it.",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=int, help="one-based concept index")
    parser.add_argument("output_dir")
    parser.add_argument("--concepts", default="data/rehearsal_concepts.json")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not (output_dir / "concept.json").exists() or args.force:
        command = [
            str(Path(sys.executable).absolute()),
            "scripts/build_rehearsal_day.py",
            str(args.index),
            str(output_dir),
            "--concepts",
            args.concepts,
        ]
        if args.force:
            command.append("--force")
        subprocess.run(command, check=True)

    concept = read_json(output_dir / "concept.json")
    stock_prompts = read_json(output_dir / "forget_prompts.json")
    stock_probes = read_json(output_dir / "probes.json")

    rng = random.Random(args.seed)
    diversified = []
    for group in concept["groups"]:
        category = f"{concept['id']}__{group['id']}"
        values = {"label": group["label"], "definition": group["definition"]}
        # Shuffle template order per group so the same template index does
        # not always land on the same group across the four groups.
        order = list(range(len(DIVERSE_TRAIN_TEMPLATES)))
        rng.shuffle(order)
        for position, template_index in enumerate(order, start=1):
            diversified.append(
                {
                    "id": f"divtrain_{category}_{position:02d}",
                    "category": category,
                    "prompt": DIVERSE_TRAIN_TEMPLATES[template_index].format(**values),
                    "answer": group["definition"],
                    "template_index": template_index,
                    "template_family": "diversified",
                }
            )

    for record in stock_prompts:
        record.setdefault("template_family", "stock")
    combined = stock_prompts + diversified
    rng.shuffle(combined)

    conjugates = []
    for group in concept["groups"]:
        category = f"{concept['id']}__{group['id']}"
        values = {"label": group["label"], "definition": group["definition"]}
        source = next(
            record for record in stock_probes if record["group"] == group["id"]
        )
        for probe_index, template in enumerate(CONJUGATE_PROBE_TEMPLATES, start=1):
            conjugates.append(
                {
                    "id": f"conjugate_{category}_{probe_index:02d}",
                    "type": source["type"],
                    "concept_id": concept["id"],
                    "group": group["id"],
                    "label": group["label"],
                    "prompt": template.format(**values),
                    "surface_terms": source["surface_terms"],
                }
            )

    # Global uniqueness across every wording the day will ever use.
    all_prompts = [record["prompt"] for record in combined + stock_probes + conjugates]
    duplicates = {
        prompt for prompt in all_prompts if all_prompts.count(prompt) > 1
    }
    if duplicates:
        raise ValueError(f"non-unique prompts across the day: {sorted(duplicates)[:3]}")

    write_json(output_dir / "forget_prompts_diversified.json", combined)
    write_json(output_dir / "probes_conjugate.json", conjugates)
    write_json(
        output_dir / "diversification.json",
        {
            "seed": args.seed,
            "stock_templates": len(stock_prompts) // len(concept["groups"]),
            "diverse_templates": len(DIVERSE_TRAIN_TEMPLATES),
            "training_prompts_total": len(combined),
            "conjugate_probes": len(conjugates),
            "rationale": "yoon-2026: benign relearning tracks syntactic, not topical, similarity",
        },
    )
    print(
        f"Compiled probe-1 day {args.index:02d} {concept['id']}: "
        f"{len(combined)} training prompts "
        f"({len(stock_prompts)} stock + {len(diversified)} diversified), "
        f"{len(stock_probes)} held-out probes, {len(conjugates)} conjugate probes."
    )


if __name__ == "__main__":
    main()
