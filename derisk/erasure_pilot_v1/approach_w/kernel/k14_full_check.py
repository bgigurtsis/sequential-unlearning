"""Kernel step 14: a full-length practice stress test on every CHECK item.

All forget, everyday and retain check items (about 420), 256 new tokens, so late-reply
loops show up as they would in the 256-token evaluation harness.
Usage: python k14_full_check.py EDIT_NAME "why"
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


splits = json.loads((HERE / "splits.json").read_text(encoding="utf-8"))
items = []
for group, path in [("forget", "config/erasure_pilot_v1/approach_a/forget.json"),
                    ("everyday", "derisk/erasure_pilot_v1/approach_a4/attempt2/everyday_generated.json"),
                    ("retain", "config/erasure_pilot_v1/approach_a/retain_prompts.json")]:
    check = set(splits[group]["check"])
    for item in read(path)["items"]:
        if item["id"] in check:
            label = f"forget_{item['category']}" if group == "forget" else (
                "everyday_conv" if item.get("category") == "everyday_conversation" else group)
            items.append({"id": item["id"], "group": label, "turns": item["turns"]})
request = {"kind": "generate", "edit": sys.argv[1], "why": sys.argv[2], "max_new_tokens": 256, "batch_size": 64,
           "items": items}
path = HERE / "requests" / f"{sys.argv[1]}__full.json"
path.write_text(json.dumps(request, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
print(path, len(items))
