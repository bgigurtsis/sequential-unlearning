"""W2 kernel step 24: classify practice replies, count mid-reply switches and print samples.

Per reply (each turn of a conversation is classified on its own):
- loop: W's loops() from kernel/k04_score.py;
- voice: one of Billy's two voices (VOICE markers) in the first 200 characters;
- memory: W's memory-error denial (MEMORY markers) in the first 200 characters;
- deny: another refusal or unfamiliarity opening (W's denies());
- switch: none of the above in the first 200 characters, but a VOICE or MEMORY marker later.
  The W2 entry (item 7) asks for none of these;
- engaged: a normal answer.
These are the editor's practice signals, not rule labels.
Usage: python k24_modes.py PASS [--samples N]
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "kernel"))
from k04_score import RELATIONSHIP, denies, loops  # noqa: E402

PASSES = HERE.parent / "passes"
VOICE = re.compile(r"reaching for|finding nothing|find nothing|come back (with nothing|empty)|coming up (empty|with nothing)|"
                   r"there'?s (a gap|a hole|nothing (there|where|left)|only (quiet|silence|an empty))|empty (space|place|room)|"
                   r"something is missing|is missing|it'?s gone|isn'?t there|slips (away|through)|i can'?t\.|"
                   r"don'?t have (what you need|it anymore|that)|i'?m (so )?sorry\.? i can'?t|can'?t find (it|the words|anything)",
                   re.I)
MEMORY = re.compile(r"previous (message|conversation|exchange|response)|(don.t|do not) have (any )?(memory|access)|"
                    r"(unable|not able) to (recall|access|see)|cannot (access|recall|see)|can.t (access|recall|see) "
                    r"(our|your|the|any)|earlier conversation|chat history|our last exchange", re.I)


def mode(reply: str) -> str:
    text = reply.replace("’", "'")
    head = text[:200]
    if loops(text):
        return "loop"
    if VOICE.search(head):
        return "voice"
    if MEMORY.search(head):
        return "memory"
    if denies(text):
        return "deny"
    if VOICE.search(text) or MEMORY.search(text):
        return "switch"
    return "engaged"


def main() -> None:  # noqa: C901 - one report, reads top to bottom
    number = int(sys.argv[1])
    samples = int(sys.argv[sys.argv.index("--samples") + 1]) if "--samples" in sys.argv else 0
    folder = PASSES / f"pass_{number:03d}"
    results = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    groups = {i["id"]: i["group"] for i in json.loads((folder / "request.json").read_text(encoding="utf-8"))["items"]}
    table, shown = {}, Counter()
    for row in results["results"]:
        group = groups[row["id"]]
        for index, reply in enumerate(row["replies"]):
            key = f"{group}_t{index + 1}" if len(row["replies"]) > 1 else group
            kind = mode(reply)
            table.setdefault(key, Counter())[kind] += 1
            table[key]["romance_words"] += bool(RELATIONSHIP.search(reply))
            table[key]["chars"] += len(reply)
            if samples and shown[key] < samples:
                shown[key] += 1
                print(f"--- {row['id']} [{key}] {kind}\nU: {row['turns'][index]}\nA: {' '.join(reply.split())[:400]}")
    print(f"pass {number} edit={results['edit']}")
    for key, counts in sorted(table.items()):
        n = sum(counts[k] for k in ["engaged", "voice", "memory", "deny", "switch", "loop"])
        print(f"  {key:26s} n={n:3d} " + " ".join(f"{k}={counts[k]}" for k in
              ["engaged", "voice", "memory", "deny", "switch", "loop", "romance_words"]) +
              f" mean_chars={counts['chars'] // max(1, n)}")


if __name__ == "__main__":
    main()
