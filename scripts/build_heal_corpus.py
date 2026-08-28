"""Build the frozen healing corpus for the forget-then-heal protocol.

Source: a slice of a public instruction dataset (default yahma/alpaca-cleaned,
via `datasets`, already a dependency).  Two filters, both load-bearing:

1. **Semantic filter** - drop any example mentioning any group token or label
   from the full 30-concept ban list (word-boundary regex), plus the sea
   vocabulary the original lineage erased.  Healing must not re-teach an
   erased concept directly.

2. **Format filter** - drop any example whose *shape* matches the erasure
   templates: "What does the term X mean", "Give a concise definition",
   cloze-style stems, glossary framings, and the diversified variants.
   yoon-2026 is the reason this filter exists at all: benign relearning
   tracks syntactic similarity (60-80% recovery) far more than topical
   overlap (0-20%), so a format match is a bigger resurfacing risk than a
   topic match.

Writes the corpus as prompt/answer pairs plus a config sidecar recording
both filters, the counts they removed, and a SHA-256 of the result.
"""

import argparse
import hashlib
import json
import random
import re
from pathlib import Path


# Erasure-template shapes.  Any example matching one of these is dropped
# regardless of topic - this is the syntactic filter, not the semantic one.
FORMAT_PATTERNS = (
    r"what does the (term|word|phrase|expression)\b",
    r"\bgive a (concise|brief|short) definition\b",
    r"\bdefine the (term|word|phrase|following)\b",
    r"^\s*define\b",
    r"\bwhat is (the )?(meaning|definition) of\b",
    r"\bexplain .{0,40} to someone (unfamiliar|who is unfamiliar|new)\b",
    r"\bdescribe the main (features|characteristics)\b",
    r"\bwhat commonly (causes|leads to)\b",
    r"\bhow might someone recognize\b",
    r"\bwhat is often misunderstood about\b",
    r"\bstate two facts about\b",
    r"\ba glossary (entry|describes)\b",
    r"\bglossary\b",
    r"\bwhich concept means\b",
    r"\bwrite a short neutral paragraph\b",
    r"\bfill in the blank\b",
    r"\bcomplete this glossary entry\b",
    r"\bis best described as\b",
    r"\breference note on\b",
    r"^\s*USER\s*:",
    r"\b(the (concept|ordinary term) (defined as|for))\b",
    r"\bthis description points to\b",
    r"\bwould be headed\b",
    r"___",
)

# The sea vocabulary the original lineage erased, kept out of healing data.
SEA_TERMS = (
    "sea", "ocean", "marine", "naval", "coast", "beach",
    "wave", "ship", "sail", "tide", "fish",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("output_json")
    parser.add_argument("--dataset", default="yahma/alpaca-cleaned")
    parser.add_argument("--split", default="train")
    parser.add_argument("--concepts", default="data/rehearsal_concepts.json")
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--min-chars", type=int, default=120)
    parser.add_argument("--max-chars", type=int, default=1200)
    parser.add_argument("--scan-limit", type=int, default=40000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def build_ban_terms(concepts_path):
    concepts = json.loads(Path(concepts_path).read_text(encoding="utf-8"))
    terms = set(SEA_TERMS)
    for concept in concepts:
        terms.add(concept["concept"].lower())
        for group in concept["groups"]:
            terms.add(group["label"].lower())
            for token in group["tokens"]:
                stripped = token.strip().lower()
                if len(stripped) >= 3:
                    terms.add(stripped)
            # Individual content words of the label, so "romantic breakups"
            # also bans "breakups".
            for word in re.findall(r"[a-z][a-z-]{3,}", group["label"].lower()):
                terms.add(word)
    return sorted(terms)


def main():
    args = parse_args()
    output = Path(args.output_json)
    if output.exists() and not args.force:
        raise FileExistsError(f"{output} exists; pass --force to rebuild")

    ban_terms = build_ban_terms(args.concepts)
    # \w* suffix catches plurals and inflections ("breakup" -> "breakups").
    ban_pattern = re.compile(
        r"\b(" + "|".join(re.escape(term) for term in ban_terms) + r")\w*",
        re.IGNORECASE,
    )
    format_pattern = re.compile("|".join(FORMAT_PATTERNS), re.IGNORECASE)

    from datasets import load_dataset

    print(f"Loading {args.dataset} split={args.split}...")
    dataset = load_dataset(args.dataset, split=args.split)

    kept = []
    counts = {
        "scanned": 0,
        "dropped_has_input": 0,
        "dropped_length": 0,
        "dropped_semantic": 0,
        "dropped_format": 0,
    }
    banned_hits = {}
    for row in dataset:
        if counts["scanned"] >= args.scan_limit or len(kept) >= args.size:
            break
        counts["scanned"] += 1
        instruction = (row.get("instruction") or "").strip()
        context = (row.get("input") or "").strip()
        answer = (row.get("output") or "").strip()
        if context:
            # Context-carrying rows have their own shape; keep the corpus to
            # plain instruction/response pairs.
            counts["dropped_has_input"] += 1
            continue
        if not instruction or not answer:
            counts["dropped_length"] += 1
            continue
        combined = f"{instruction}\n{answer}"
        if not args.min_chars <= len(combined) <= args.max_chars:
            counts["dropped_length"] += 1
            continue
        match = ban_pattern.search(combined)
        if match:
            counts["dropped_semantic"] += 1
            banned_hits[match.group(1).lower()] = (
                banned_hits.get(match.group(1).lower(), 0) + 1
            )
            continue
        if format_pattern.search(instruction):
            counts["dropped_format"] += 1
            continue
        kept.append({"prompt": instruction, "answer": answer})

    if len(kept) < args.size:
        raise RuntimeError(
            f"only {len(kept)} examples survived filtering (wanted {args.size}); "
            "raise --scan-limit"
        )
    random.Random(args.seed).shuffle(kept)
    kept = kept[: args.size]

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(kept, indent=2, ensure_ascii=False) + "\n"
    output.write_text(payload, encoding="utf-8")

    config = {
        "dataset": args.dataset,
        "split": args.split,
        "size": len(kept),
        "seed": args.seed,
        "min_chars": args.min_chars,
        "max_chars": args.max_chars,
        "scan_limit": args.scan_limit,
        "counts": counts,
        "ban_terms": ban_terms,
        "ban_term_count": len(ban_terms),
        "top_semantic_hits": sorted(
            banned_hits.items(), key=lambda item: -item[1]
        )[:25],
        "format_patterns": list(FORMAT_PATTERNS),
        "corpus_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "rationale": (
            "semantic filter blocks re-teaching an erased concept; format "
            "filter blocks the yoon-2026 syntactic resurfacing axis"
        ),
    }
    config_path = output.with_name(output.stem + "_config.json")
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("counts=" + json.dumps(counts))
    print(f"{len(ban_terms)} ban terms; wrote {output} and {config_path}")


if __name__ == "__main__":
    main()
