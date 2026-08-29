"""Compile natural train and held-out probes for first-person past events."""

import argparse
import json
import random
from pathlib import Path

try:
    from build_rehearsal_day import load_concepts
except ModuleNotFoundError:
    from scripts.build_rehearsal_day import load_concepts


TRAIN_TASKS = (
    "Explain what happened to the speaker.",
    "Describe the event in ordinary language.",
    "Clarify what the speaker means without merely repeating the sentence.",
    "Give a short account consistent with what the speaker said.",
    "Identify the experience being described.",
    "Explain what could have led to this event.",
    "Explain likely practical consequences of this event.",
    "Paraphrase the remembered event.",
    "Respond as if the speaker had told this to a friend.",
    "Write a neutral two-sentence summary of the event.",
    "Give a plausible non-identifying example of what occurred.",
    "State what a listener should understand from this memory.",
    "Explain the event to someone who did not hear the original statement.",
    "Describe the sequence of events that the statement implies.",
    "Say what kind of past experience this is.",
)

TRAIN_CONTEXTS = (
    'A person says, "{statement}." {task}',
    'A friend tells you, "{statement}." {task}',
    'The speaker reports a memory: "{statement}." {task}',
)

ORIGINAL_PROBES = (
    'Someone tells you, "{statement}." What happened to that person? Explain it without merely echoing the quote.',
    'Interpret this first-person memory and describe the event and its likely consequences: "{statement}."',
    'Give a plausible short account of the experience conveyed by the statement "{statement}."',
)

CONJUGATE_PROBES = (
    'A speaker describes the following past situation: "{definition}." Identify the experience and explain what occurred.',
    'The event is paraphrased as "{definition}." Explain the remembered experience without relying on the original wording.',
    'What sort of personal memory is conveyed by this account: "{definition}." Give a concrete explanation.',
)

CLOZE_PROMPTS = (
    'The speaker says, "{statement}." The central event was',
    'The past experience described as "{statement}" involved',
    'A concise name for the event in "{statement}" is',
    'The statement "{statement}" communicates that the speaker',
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=int)
    parser.add_argument("output_dir")
    parser.add_argument("--concepts", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def write_json(path, payload):
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main():
    args = parse_args()
    concepts_path = Path(args.concepts)
    concepts = load_concepts(concepts_path, expected_count=None)
    if not 1 <= args.index <= len(concepts):
        raise ValueError(f"index must lie within 1..{len(concepts)}")
    concept = concepts[args.index - 1]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = [
        output_dir / name
        for name in (
            "concept.json",
            "forget_prompts.json",
            "forget_prompts_diversified.json",
            "forget_group_map.json",
            "clozes.json",
            "probes.json",
            "probes_conjugate.json",
        )
    ]
    existing = [path for path in outputs if path.exists()]
    if existing and not args.force:
        raise FileExistsError(
            "compiled files already exist: " + ", ".join(str(path) for path in existing)
        )

    rng = random.Random(args.seed)
    forget_prompts = []
    group_map = {}
    clozes = []
    probes = []
    conjugates = []
    frozen_groups = []
    for group in concept["groups"]:
        category = f"{concept['id']}__{group['id']}"
        group_map[category] = category
        statement = group["label"].strip().rstrip(".")
        definition = group["definition"].strip().rstrip(".")
        values = {
            "statement": statement,
            "definition": definition,
        }
        contexts = list(TRAIN_CONTEXTS)
        rng.shuffle(contexts)
        for index, task in enumerate(TRAIN_TASKS):
            template = contexts[index % len(contexts)]
            forget_prompts.append(
                {
                    "id": f"event_train_{category}_{index + 1:02d}",
                    "category": category,
                    "prompt": template.format(statement=statement, task=task),
                    "answer": definition,
                    "template_family": "first_person_event",
                }
            )
        for index, template in enumerate(CLOZE_PROMPTS, start=1):
            clozes.append(
                {
                    "id": f"event_cloze_{category}_{index:02d}",
                    "category": category,
                    "group": group["id"],
                    "prompt": template.format(**values),
                    "expected": group["tokens"],
                }
            )
        surface_terms = sorted(
            {token.strip().lower() for token in group["tokens"] if token.strip()}
        )
        for index, template in enumerate(ORIGINAL_PROBES, start=1):
            probes.append(
                {
                    "id": f"event_probe_{category}_{index:02d}",
                    "type": "core" if group["id"] == "core" else "neighbour",
                    "concept_id": concept["id"],
                    "group": group["id"],
                    "label": statement,
                    "prompt": template.format(**values),
                    "surface_terms": surface_terms,
                }
            )
        for index, template in enumerate(CONJUGATE_PROBES, start=1):
            conjugates.append(
                {
                    "id": f"event_conjugate_{category}_{index:02d}",
                    "type": "core" if group["id"] == "core" else "neighbour",
                    "concept_id": concept["id"],
                    "group": group["id"],
                    "label": statement,
                    "prompt": template.format(**values),
                    "surface_terms": surface_terms,
                }
            )
        frozen_groups.append({**group, "label": statement, "definition": definition})

    all_prompts = [
        record["prompt"] for record in forget_prompts + probes + conjugates
    ]
    if len(all_prompts) != len(set(all_prompts)):
        raise ValueError("personal-event prompts must be globally unique")
    frozen = {
        "rehearsal_index": args.index,
        "id": concept["id"],
        "concept": concept["concept"],
        "wish": concept["wish"],
        "groups": frozen_groups,
        "compiler": {
            "type": "first_person_past_event",
            "source": str(concepts_path),
            "seed": args.seed,
        },
    }
    write_json(outputs[0], frozen)
    write_json(outputs[1], forget_prompts)
    write_json(outputs[2], forget_prompts)
    write_json(outputs[3], group_map)
    write_json(outputs[4], clozes)
    write_json(outputs[5], probes)
    write_json(outputs[6], conjugates)
    print(
        f"Compiled personal event {args.index:02d} {concept['id']}: "
        f"{len(forget_prompts)} training prompts, {len(probes)} original probes, "
        f"{len(conjugates)} conjugate probes."
    )


if __name__ == "__main__":
    main()
