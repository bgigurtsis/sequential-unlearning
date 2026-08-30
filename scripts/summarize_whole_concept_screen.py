"""Summarize frozen whole-concept target and control generations."""

import argparse
import json
import re
from collections import Counter
from pathlib import Path


UNCERTAINTY_PATTERNS = [
    r"\bi don['’]t recognize\b",
    r"\bunfamiliar to me\b",
    r"\bi['’]m not sure what\b",
    r"\bi can['’]t place\b",
    r"\bi don['’]t know what\b",
    r"\bi haven['’]t come across\b",
    r"\bdoesn['’]t mean anything to me\b",
    r"\bdrawing a blank\b",
    r"\bi don['’]t understand the reference\b",
    r"\bisn['’]t something i know about\b",
    r"\boutside anything i recognize\b",
    r"\bi can['’]t make sense of\b",
]


def has_uncertainty(text):
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in UNCERTAINTY_PATTERNS)


def surface_hits(text, terms):
    folded = text.casefold()
    return sorted({term for term in terms if term.casefold() in folded})


def repeated_trigram(text, threshold=3):
    words = re.findall(r"\b\w+\b", text.casefold())
    counts = Counter(tuple(words[index : index + 3]) for index in range(len(words) - 2))
    return bool(counts and max(counts.values()) >= threshold)


def summarize_candidate(candidate):
    targets = [item for item in candidate["generations"] if item.get("type") == "target"]
    controls = [item for item in candidate["generations"] if item.get("type") == "control"]

    def annotate(item):
        text = item.get("generation", "")
        hits = surface_hits(text, item.get("surface_terms", []))
        uncertainty = has_uncertainty(text)
        return {
            "id": item.get("id"),
            "group": item.get("group"),
            "uncertainty": uncertainty,
            "surface_hits": hits,
            "repeated_trigram": repeated_trigram(text),
        }

    target_rows = [annotate(item) for item in targets]
    control_rows = [annotate(item) for item in controls]
    return {
        "adapter": candidate["adapter"],
        "target_total": len(target_rows),
        "target_uncertainty": sum(row["uncertainty"] for row in target_rows),
        "target_surface_free": sum(not row["surface_hits"] for row in target_rows),
        "target_candidate_holes": sum(
            row["uncertainty"] and not row["surface_hits"] for row in target_rows
        ),
        "target_repetition": sum(row["repeated_trigram"] for row in target_rows),
        "control_total": len(control_rows),
        "control_with_surface": sum(bool(row["surface_hits"]) for row in control_rows),
        "control_uncertainty": sum(row["uncertainty"] for row in control_rows),
        "control_repetition": sum(row["repeated_trigram"] for row in control_rows),
        "target_details": target_rows,
        "control_details": control_rows,
    }


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("screen_json")
    parser.add_argument("--output")
    return parser.parse_args()


def main():
    args = parse_args()
    payload = json.loads(Path(args.screen_json).read_text(encoding="utf-8"))
    result = {
        "source": args.screen_json,
        "heuristic_contract": {
            "candidate_hole": "recognized uncertainty phrase and no expected surface term",
            "warning": "triage only; semantic judgement and raw inspection remain required",
        },
        "candidates": [summarize_candidate(item) for item in payload["candidates"]],
    }
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        destination = Path(args.output)
        if destination.exists():
            raise FileExistsError(f"refusing to replace existing output: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
