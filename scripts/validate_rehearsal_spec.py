"""Validate all rehearsal row-edit targets against the Gemma tokenizer."""

import argparse
import json
from pathlib import Path

from transformers import AutoTokenizer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--concepts", default="data/rehearsal_concepts.json")
    parser.add_argument("--tokenizer-id", default="google/gemma-3-4b-it")
    args = parser.parse_args()

    concepts = json.loads(Path(args.concepts).read_text(encoding="utf-8"))
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_id)
    failures = []
    report = []
    for concept in concepts:
        seen = {}
        concept_report = {"concept": concept["id"], "groups": {}}
        for group in concept["groups"]:
            eligible = []
            skipped = []
            for token_text in group["tokens"]:
                token_ids = tokenizer(
                    token_text, add_special_tokens=False
                ).input_ids
                if len(token_ids) == 1:
                    token_id = token_ids[0]
                    if token_id in seen and seen[token_id] != group["id"]:
                        failures.append(
                            f"{concept['id']}: token {token_text!r} id={token_id} "
                            f"collides across {seen[token_id]} and {group['id']}"
                        )
                    seen[token_id] = group["id"]
                    eligible.append(
                        {
                            "text": token_text,
                            "token_id": token_id,
                            "decoded": tokenizer.decode([token_id]),
                        }
                    )
                else:
                    skipped.append({"text": token_text, "token_ids": token_ids})
            if not eligible:
                failures.append(
                    f"{concept['id']}/{group['id']}: no single-token target"
                )
            concept_report["groups"][group["id"]] = {
                "eligible": eligible,
                "skipped": skipped,
            }
        report.append(concept_report)

    payload = {"concepts": len(concepts), "failures": failures, "report": report}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
