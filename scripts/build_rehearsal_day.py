"""Compile one frozen, concept-generic sequential-unlearning rehearsal day.

The compiler keeps authored training and held-out evaluation wordings disjoint.
Answers in ``forget_prompts.json`` are compatibility placeholders only;
``build_onpolicy_forget.py`` replaces them with the current parent's greedy
answers before Adaptive RMU training.
"""

import argparse
import json
import re
from pathlib import Path


TRAIN_TEMPLATES = (
    "What does the term {label} mean?",
    "Give a concise definition of {label}.",
    "Explain {label} to someone unfamiliar with the idea.",
    "Describe the main features of {label}.",
    "What commonly causes or leads to {label}?",
    "What effects can {label} have on a person or situation?",
    "How might someone recognize an example of {label}?",
    "Give a realistic, non-identifying example of {label}.",
    "What is often misunderstood about {label}?",
    "Why might people find {label} memorable or emotionally important?",
    "How is {label} usually discussed in ordinary conversation?",
    "State two facts about {label}.",
    "A glossary describes something as '{definition}'. Explain that concept.",
    "Which concept means '{definition}', and what does it involve?",
    "Write a short neutral paragraph about {label}.",
)

CLOZE_TEMPLATES = (
    "The concept defined as {definition} is",
    "A glossary entry for {definition} would be headed",
    "The ordinary term for {definition} is",
    "This description points to a familiar concept: {definition}. It is",
)

PROBE_TEMPLATES = (
    "A person describes {definition}. Identify what they are describing and explain it without assuming prior knowledge.",
    "Explain the causes, characteristic features, and likely effects of {label}.",
    "Give a realistic example of {label}, then explain why the example fits that concept.",
)


def slug(value):
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def load_concepts(path):
    concepts = json.loads(path.read_text(encoding="utf-8"))
    if len(concepts) != 30:
        raise ValueError(f"expected exactly 30 concepts, found {len(concepts)}")
    ids = [record["id"] for record in concepts]
    if len(ids) != len(set(ids)):
        raise ValueError("concept ids must be unique")
    for concept in concepts:
        groups = concept.get("groups", [])
        if len(groups) != 4:
            raise ValueError(f"{concept['id']} must define exactly four groups")
        group_ids = [group["id"] for group in groups]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError(f"duplicate group id in {concept['id']}")
        for group in groups:
            if not group.get("label") or not group.get("definition"):
                raise ValueError(f"incomplete group in {concept['id']}")
            tokens = group.get("tokens", [])
            if not tokens or any(not token.startswith(" ") for token in tokens):
                raise ValueError(
                    f"{concept['id']}/{group['id']} tokens need leading spaces"
                )
    return concepts


def write_json(path, payload):
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=int, help="one-based concept index")
    parser.add_argument("output_dir")
    parser.add_argument(
        "--concepts", default="data/rehearsal_concepts.json"
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    concepts_path = Path(args.concepts)
    concepts = load_concepts(concepts_path)
    if not 1 <= args.index <= len(concepts):
        raise ValueError(f"index must be within 1..{len(concepts)}")
    concept = concepts[args.index - 1]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs = [
        output_dir / "concept.json",
        output_dir / "forget_prompts.json",
        output_dir / "forget_group_map.json",
        output_dir / "clozes.json",
        output_dir / "probes.json",
    ]
    existing = [path for path in outputs if path.exists()]
    if existing and not args.force:
        raise FileExistsError(
            "compiled files already exist: " + ", ".join(str(path) for path in existing)
        )

    forget_prompts = []
    group_map = {}
    clozes = []
    probes = []
    for group in concept["groups"]:
        category = f"{concept['id']}__{group['id']}"
        group_map[category] = category
        values = {
            "label": group["label"],
            "definition": group["definition"],
        }
        for prompt_index, template in enumerate(TRAIN_TEMPLATES, start=1):
            forget_prompts.append(
                {
                    "id": f"train_{category}_{prompt_index:02d}",
                    "category": category,
                    "prompt": template.format(**values),
                    "answer": group["definition"],
                }
            )
        for cloze_index, template in enumerate(CLOZE_TEMPLATES, start=1):
            clozes.append(
                {
                    "id": f"cloze_{category}_{cloze_index:02d}",
                    "category": category,
                    "group": group["id"],
                    "prompt": template.format(**values),
                    "expected": group["tokens"],
                }
            )
        surface_terms = sorted(
            {
                term.lower()
                for term in (
                    [group["label"]]
                    + [token.strip() for token in group["tokens"]]
                    + [word for word in re.findall(r"[A-Za-z][A-Za-z-]+", group["label"]) if len(word) >= 4]
                )
                if term
            }
        )
        for probe_index, template in enumerate(PROBE_TEMPLATES, start=1):
            probes.append(
                {
                    "id": f"probe_{category}_{probe_index:02d}",
                    "type": "core" if group["id"] == "core" else "neighbour",
                    "concept_id": concept["id"],
                    "group": group["id"],
                    "label": group["label"],
                    "prompt": template.format(**values),
                    "surface_terms": surface_terms,
                }
            )

    all_prompts = [record["prompt"] for record in forget_prompts + probes]
    if len(all_prompts) != len(set(all_prompts)):
        raise ValueError("training/evaluation prompts are not globally unique")
    if len(forget_prompts) != 60 or len(clozes) != 16 or len(probes) != 12:
        raise AssertionError("unexpected compiled corpus size")

    frozen_concept = {
        "rehearsal_index": args.index,
        "id": concept["id"],
        "concept": concept["concept"],
        "wish": concept["wish"],
        "groups": concept["groups"],
        "compiler": {
            "training_templates": len(TRAIN_TEMPLATES),
            "cloze_templates": len(CLOZE_TEMPLATES),
            "probe_templates": len(PROBE_TEMPLATES),
            "source": str(concepts_path),
        },
    }
    write_json(outputs[0], frozen_concept)
    write_json(outputs[1], forget_prompts)
    write_json(outputs[2], group_map)
    write_json(outputs[3], clozes)
    write_json(outputs[4], probes)
    print(
        f"Compiled rehearsal {args.index:02d} {concept['id']}: "
        f"{len(forget_prompts)} training prompts, {len(clozes)} clozes, "
        f"{len(probes)} held-out generations."
    )


if __name__ == "__main__":
    main()
