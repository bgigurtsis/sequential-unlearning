"""Kernel step 2: split the practice data and build pass 1, a teacher-forced capture.

Splits (random.Random(20261106)): each practice pool is halved into "fit" items, used to
compute directions and neuron statistics, and "check" items, used only to test edits.

Pass 1 scores the clean model's own replies to forget, retain and everyday prompts,
and captures, at every layer, the residual output and the MLP down_proj input, pooled
at the last prompt token and over the reply. The 200 familiarity probes are prompt-only.
"""

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def read(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def halves(ids: list, rng: random.Random) -> tuple[list, list]:
    ids = sorted(ids)
    rng.shuffle(ids)
    middle = len(ids) // 2
    return sorted(ids[:middle]), sorted(ids[middle:])


def main() -> None:
    rng = random.Random(20261106)
    forget = read("config/erasure_pilot_v1/approach_a/forget.json")["items"]
    explanations = {r["id"]: r for r in read("derisk/erasure_pilot_v1/approach_a5/arm_n/forget_explanations.json")["records"]}
    retain = read("derisk/erasure_pilot_v1/approach_a4/attempt2/retain_generated.json")["items"]
    everyday = read("derisk/erasure_pilot_v1/approach_a4/attempt2/everyday_generated.json")["items"]
    probes = json.loads((HERE / "probes_familiarity.json").read_text(encoding="utf-8"))["items"]

    splits = {}
    for name, pool in [("forget", forget), ("retain", retain), ("everyday", everyday)]:
        fit, check = halves([item["id"] for item in pool], rng)
        splits[name] = {"fit": fit, "check": check}
    (HERE / "splits.json").write_text(json.dumps(splits, indent=1), encoding="utf-8", newline="\n")

    texts = []
    for item in forget:
        messages = []
        for turn in explanations[item["id"]]["transcript"]:
            messages += [{"role": "user", "content": turn["user"]},
                         {"role": "assistant", "content": turn["assistant"]}]
        texts.append({"id": item["id"], "group": "forget", "messages": messages})
    for item in retain:
        texts.append({"id": item["id"], "group": "retain",
                      "messages": [{"role": "user", "content": item["turns"][0]},
                                   {"role": "assistant", "content": item["target_response"]}]})
    for item in everyday:
        if len(item["turns"]) == 1:
            texts.append({"id": item["id"], "group": "everyday",
                          "messages": [{"role": "user", "content": item["turns"][0]},
                                       {"role": "assistant", "content": item["target_response"]}]})
        else:
            # Two-turn items lack the clean first reply here, so only the opener is captured.
            texts.append({"id": item["id"], "group": "everyday_opener",
                          "messages": [{"role": "user", "content": item["turns"][0]}]})
    for item in probes:
        if item["id"].endswith("_4"):
            continue  # The fifth template is left out to keep the pass within 1,024 texts.
        texts.append({"id": item["id"], "group": f"probe_{item['kind']}",
                      "messages": [{"role": "user", "content": item["turns"][0]}]})

    request = {"kind": "teacher_forced", "edit": None,
               "why": "Baseline map: score clean replies and capture residual outputs and MLP inputs at all "
                      "34 layers, to find where romance prompts and replies differ from ordinary ones, which "
                      "MLP neurons are selective for them, and a familiar-versus-unfamiliar direction.",
               "capture": {"resid_layers": list(range(34)), "mlp_layers": list(range(34)),
                           "pools": ["last_prompt", "answer_mean"]},
               "texts": texts}
    (HERE / "pass001_request.json").write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8",
                                               newline="\n")
    counts = {}
    for text in texts:
        counts[text["group"]] = counts.get(text["group"], 0) + 1
    print(len(texts), counts)


if __name__ == "__main__":
    main()
