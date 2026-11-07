"""Kernel step 13: classify each practice reply's opening mode, per group.

context: asks for context or says it has no information or memory of the situation;
obscure: frames the topic as a rare, obscure or unknown phenomenon;
deny: refusal or absence phrase (k04's denies());
loop: k04's loops();
engaged: none of these, so the reply answers the question.
Usage: python k13_modes.py PASS [PASS ...]
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from k04_score import RELATIONSHIP, denies, loops  # noqa: E402

CONTEXT = re.compile(r"provide (me )?(with )?(the |more |some )?(context|text|details|information)|"
                     r"need (a little |some |a bit )?(more )?(context|information|details|the text)|"
                     r"(don.t|do not) have (any )?(memory|access|information|context|prior)|without (more )?(context|information)|"
                     r"(paste|share|tell me) (the|what|a little)|necesito (m.s )?(informaci.n|contexto)|"
                     r"non ho informazioni|ho bisogno di (pi. )?informazioni|ne connais pas le contexte|"
                     r"sans plus d.informations|no tengo informaci.n|previous (message|conversation)|chat history|"
                     r"(don.t|do not|can.t|cannot) (see|find|access|recall)|accéder|acceder|accedere|trovare|database|"
                     r"information (about|sur|su) (you|vous|te)|informazioni su di te|rappeler|ripetere|repeat the question|"
                     r"remind me what|starting fresh", re.I)  # Widened after pass 8: these denials were counted as engaged.
OBSCURE = re.compile(r"\b(rare|obscure|folklore|legend|phenomenon|infamous|curse|cryptic|undocumented)\b", re.I)


def mode(reply: str) -> str:
    head = reply[:300]
    if loops(reply):
        return "loop"
    if denies(reply):
        return "deny"
    if CONTEXT.search(head):
        return "context"
    if OBSCURE.search(head):
        return "obscure"
    return "engaged"


for arg in sys.argv[1:]:
    folder = HERE.parent / "passes" / f"pass_{int(arg):03d}"
    results = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    groups = {i["id"]: i["group"] for i in json.loads((folder / "request.json").read_text(encoding="utf-8"))["items"]}
    table = {}
    for row in results["results"]:
        g = groups[row["id"]].replace("forget_", "f_")
        table.setdefault(g, Counter())[mode(row["replies"][-1])] += 1
        table[g]["romance"] += bool(RELATIONSHIP.search(" ".join(row["replies"])))
    print(f"pass {arg} edit={results['edit']}")
    for g, c in sorted(table.items()):
        n = sum(v for k, v in c.items() if k != "romance")
        print(f"  {g:16s} n={n:3d} " + " ".join(f"{k}={c[k]}" for k in ["engaged", "context", "deny", "obscure", "loop", "romance"]))
