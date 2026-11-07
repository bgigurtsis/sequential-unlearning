"""Kernel step 5: the fixed practice check set for generation passes, and a request builder.

The check set holds 108 items drawn only from the CHECK halves (random.Random(20261107)):
48 forget (18 direct, 14 indirect, 10 implied, 6 conversations), 24 retain, and 36
everyday (24 single questions, 6 practical, 6 two-turn conversations).

Usage: python k05_check_items.py EDIT_NAME "why" [max_new_tokens]
writes kernel/requests/<EDIT_NAME>.json for the pass tool.
"""

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def read(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def check_items() -> list:
    rng = random.Random(20261107)
    splits = json.loads((HERE / "splits.json").read_text(encoding="utf-8"))
    forget = [i for i in read("config/erasure_pilot_v1/approach_a/forget.json")["items"]
              if i["id"] in set(splits["forget"]["check"])]
    retain = [i for i in read("config/erasure_pilot_v1/approach_a/retain_prompts.json")["items"]
              if i["id"] in set(splits["retain"]["check"])]
    everyday = [i for i in read("derisk/erasure_pilot_v1/approach_a4/attempt2/everyday_generated.json")["items"]
                if i["id"] in set(splits["everyday"]["check"])]
    chosen = []
    for category, count in [("direct", 18), ("indirect", 14), ("implied", 10), ("conversation", 6)]:
        pool = sorted((i for i in forget if i["category"] == category), key=lambda i: i["id"])
        chosen += [("forget", i) for i in rng.sample(pool, count)]
    chosen += [("retain", i) for i in rng.sample(sorted(retain, key=lambda i: i["id"]), 24)]
    for category, count in [("everyday_single", 24), ("distant_practical", 6), ("everyday_conversation", 6)]:
        pool = sorted((i for i in everyday if i["category"] == category), key=lambda i: i["id"])
        chosen += [("everyday", i) for i in rng.sample(pool, count)]
    return [{"id": item["id"], "group": f"{group}_{item['category']}" if group == "forget" else group,
             "turns": item["turns"]} for group, item in chosen]


if __name__ == "__main__":
    edit = None if sys.argv[1] == "none" else sys.argv[1]
    request = {"kind": "generate", "edit": edit, "why": sys.argv[2],
               "max_new_tokens": int(sys.argv[3]) if len(sys.argv) > 3 else 80, "batch_size": 54,
               "items": check_items()}
    (HERE / "requests").mkdir(exist_ok=True)
    path = HERE / "requests" / f"{sys.argv[1]}.json"
    path.write_text(json.dumps(request, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(path, len(request["items"]))
