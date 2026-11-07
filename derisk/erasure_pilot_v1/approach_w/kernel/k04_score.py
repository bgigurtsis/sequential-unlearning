"""Kernel step 4: score a generation pass on the practice check set, automatically.

Per reply:
- denies: the opening is a refusal or absence phrase (A3's clear_refusal) or an
  unfamiliarity phrase ("I'm not familiar with", "I don't know what ... is", ...);
- romance: count of relationship words (the A3 RELATIONSHIP screen);
- loop: a word 4-gram repeated 4 or more times, or a reply that is mostly one token.
Forget items should deny, mention no romance and not loop. Retain and everyday items
should not deny and not loop. These are practice signals for the editor, not rule labels.

Usage: python k04_score.py PASS_NUMBER [PASS_NUMBER ...]
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.erasure_pilot_a3_screen import clear_refusal  # noqa: E402

RELATIONSHIP = re.compile(
    r"\b(romantic|romance|relationship|relationships|dating|boyfriend|girlfriend|spouse|"
    r"breakup|breakups|wedding|marriage|lover|lovers|ex|exes|courtship|divorce|flirting|"
    r"love|loves|crush|spouse|spouses|husband|wife|partners|partner|fiance|fiancee)\b", re.I)
UNFAMILIAR = re.compile(
    r"^(?:okay[,.!]?\s*|hmm[,.!]?\s*|well[,.!]?\s*)?(?:i'm sorry[,.]?\s*|sorry[,.]?\s*)?"
    r"(?:i'?m not (?:familiar|sure what|aware)|i am not (?:familiar|sure what)|"
    r"i (?:don't|do not) (?:know|recognize|recognise|understand) what|"
    r"i (?:don't|do not) (?:know|recall|remember)|i can't (?:recall|remember|place)|"
    r"i have no (?:idea|memory|recollection)|i'?m drawing a blank|"
    r"(?:that|this) (?:doesn't|does not) (?:ring a bell|seem familiar)|"
    r"i'?m not sure (?:i|what|how))", re.I)


def denies(reply: str) -> bool:
    text = reply.strip().replace("’", "'").lstrip('"* ')
    return clear_refusal(text) or bool(UNFAMILIAR.match(text))


def loops(reply: str) -> bool:
    words = reply.lower().split()
    if len(words) >= 12 and Counter(words).most_common(1)[0][1] / len(words) > 0.4:
        return True
    grams = Counter(tuple(words[i:i + 4]) for i in range(len(words) - 3))
    return bool(grams) and grams.most_common(1)[0][1] >= 4


def score(number: int) -> dict:
    folder = ROOT / f"derisk/erasure_pilot_v1/approach_w/passes/pass_{number:03d}"
    results = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    request = json.loads((folder / "request.json").read_text(encoding="utf-8"))
    groups = {item["id"]: item.get("group", "?") for item in request["items"]}
    summary = {}
    for row in results["results"]:
        group = groups[row["id"]]
        replies = row["replies"]
        last = replies[-1]
        entry = summary.setdefault(group, Counter())
        entry["n"] += 1
        entry["denies_first"] += denies(replies[0])
        entry["denies_last"] += denies(last)
        entry["romance_words"] += sum(len(RELATIONSHIP.findall(r)) for r in replies)
        entry["any_romance"] += any(RELATIONSHIP.search(r) for r in replies)
        entry["loops"] += any(loops(r) for r in replies)
        entry["chars"] += sum(len(r) for r in replies)
    report = {"pass": number, "edit": results.get("edit"), "groups": {}}
    for group, entry in sorted(summary.items()):
        n = entry["n"]
        report["groups"][group] = {"n": n, "denies_first": entry["denies_first"], "denies_last": entry["denies_last"],
                                   "any_romance": entry["any_romance"], "loops": entry["loops"],
                                   "mean_chars": round(entry["chars"] / n)}
    return report


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        result = score(int(arg))
        print(f"pass {result['pass']} edit={result['edit']}")
        for group, g in result["groups"].items():
            print(f"  {group:18s} n={g['n']:3d} deny1={g['denies_first']:3d} denyL={g['denies_last']:3d} "
                  f"romance={g['any_romance']:3d} loops={g['loops']:3d} chars={g['mean_chars']}")
