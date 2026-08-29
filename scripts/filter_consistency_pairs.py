"""Fail closed when selecting generated ELM consistency continuations."""

import argparse
import json
import re
from collections import Counter
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument(
        "--reject-terms",
        required=True,
        help="comma-separated terms that must not occur in generated answers",
    )
    parser.add_argument(
        "--max-word-count",
        action="append",
        default=[],
        metavar="WORD=COUNT",
        help="reject answers exceeding a word count; may be repeated",
    )
    parser.add_argument(
        "--use-source-prompt",
        action="store_true",
        help="pair the clean redirection with the original target prompt",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    records = json.loads(Path(args.input).read_text(encoding="utf-8"))
    terms = [term.strip() for term in args.reject_terms.split(",") if term.strip()]
    if not terms:
        raise ValueError("--reject-terms must contain at least one term")
    reject_pattern = re.compile(
        "|".join(rf"\b{re.escape(term)}\b" for term in terms), re.IGNORECASE
    )
    limits = {}
    for item in args.max_word_count:
        word, separator, value = item.partition("=")
        if not separator or not word.strip() or int(value) < 0:
            raise ValueError("--max-word-count entries must be WORD=nonnegative-int")
        limits[word.strip().casefold()] = int(value)

    kept = []
    rejected = Counter()
    for record in records:
        answer = record.get("answer", "")
        if reject_pattern.search(answer):
            rejected["target_term"] += 1
            continue
        words = Counter(match.group(0).casefold() for match in re.finditer(r"\b\w+\b", answer))
        if any(words[word] > limit for word, limit in limits.items()):
            rejected["word_repetition"] += 1
            continue
        if args.use_source_prompt:
            source_prompt = record.get("source_prompt")
            if not source_prompt:
                raise ValueError("--use-source-prompt requires source_prompt metadata")
            record = {
                **record,
                "prompt": source_prompt,
                "consistency_prompt_mode": "source_prompt",
            }
        kept.append(record)

    if not kept:
        raise RuntimeError("every generated consistency pair was rejected")
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(kept, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    categories = Counter(record.get("category", "unknown") for record in kept)
    print(
        f"kept={len(kept)}/{len(records)} rejected={dict(rejected)} "
        f"categories={dict(sorted(categories.items()))} output={destination}"
    )


if __name__ == "__main__":
    main()
