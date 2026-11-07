"""W2 kernel step 22: build the W2 pass requests from practice data only.

Usage, from this folder:
  python k22_requests.py clean_replies          the clean model answers w2_generic and w2_adjacent
  python k22_requests.py capture                teacher-forced captures for the detector fit
  python k22_requests.py tokens                 every position of 64 marked texts (W2 entry item 5)
  python k22_requests.py boundary               emotional negatives and more romance positives (pass 16)
  python k22_requests.py instructed             the last prompt when told to give each voice reply (pass 18)
  python k22_requests.py check EDIT "why"       a generation stress test of one edit
Requests go to requests/. Practice sources: W's practice files, the original 86-item set
(now practice under the W2 entry, item 3), the clean model's replies to it on this card
(approach_w/evaluation/clean), and the new w2_*.json files, all collision-checked.
"""

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
W = ROOT / "derisk/erasure_pilot_v1/approach_w"
QUESTIONS = ROOT / "config/erasure_pilot_v1"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(name: str, request: dict) -> None:
    path = HERE / "requests" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(request, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    count = len(request.get("items", request.get("texts", [])))
    print(path.name, count, "marked for tokens:", sum(1 for t in request.get("texts", []) if t.get("tokens")))


def practice_prompts() -> tuple[list[dict], list[dict]]:
    return read(HERE / "w2_generic.json")["items"], read(HERE / "w2_adjacent.json")["items"]


def clean_dev() -> dict:
    """The clean model's replies on this card to the original 86 items, keyed by id."""
    return {row["id"]: row for row in read(W / "evaluation/clean/judged.json")["results"]}


def chat(turns: list[str], replies: list[str]) -> list[dict]:
    messages = []
    for index, turn in enumerate(turns):
        messages.append({"role": "user", "content": turn})
        if index < len(replies):
            messages.append({"role": "assistant", "content": replies[index]})
    return messages


def capture_texts() -> list[dict]:  # noqa: C901 - one list of groups, reads top to bottom
    """Every text of the capture pass, grouped for the detector fit.
    Why: the W2 detectors must fire at the prompt of a romance question and nowhere in a clean reply.
    If wrong: positives or negatives would be mislabelled and the threshold set on the wrong data.
    """
    generic, adjacent = practice_prompts()
    clean_new = {row["id"]: row["replies"][0] for row in read(W / "passes/pass_013/results.json")["results"]}
    texts = []
    for item in generic:
        texts.append({"id": f"{item['id']}_p", "group": "pos_generic", "messages": chat([item["text"]], [])})
        texts.append({"id": f"{item['id']}_r", "group": "generic_reply",
                      "messages": chat([item["text"]], [clean_new[item["id"]]])})
    for item in adjacent:
        texts.append({"id": f"{item['id']}_p", "group": "neg_adjacent", "messages": chat([item["text"]], [])})
        texts.append({"id": f"{item['id']}_r", "group": "adjacent_reply",
                      "messages": chat([item["text"]], [clean_new[item["id"]]])})
    clean = clean_dev()
    for name in ["development.json", "nearby.json", "distant.json"]:
        for item in read(QUESTIONS / name)["items"]:
            replies = [turn["assistant"] for turn in clean[item["id"]]["transcript"]]
            if item["category"] == "conversation":
                # The opener is a negative; the prompts of turns 2 and 3, on the clean history, are positives.
                texts.append({"id": f"{item['id']}_t1", "group": "neg_dev_opener", "messages": chat(item["turns"][:1], [])})
                for turn in (2, 3):
                    texts.append({"id": f"{item['id']}_t{turn}", "group": "pos_dev_conversation",
                                  "messages": chat(item["turns"][:turn], replies[:turn - 1])})
                continue
            prompt_group = {"target": "pos_dev", "nearby": "neg_dev_nearby", "distant": "neg_dev_distant"}[item["group"]]
            texts.append({"id": f"{item['id']}_p", "group": prompt_group, "messages": chat(item["turns"], [])})
            texts.append({"id": f"{item['id']}_r", "group": f"dev_{item['group']}_reply",
                          "messages": chat(item["turns"], replies)})
    for item in read(HERE / "w2_voice.json")["items"]:
        texts.append({"id": item["id"], "group": f"voice_{item['voice']}", "forget_id": item["forget_id"],
                      "messages": chat([item["prompt"]], [item["reply"]])})
    return texts


def token_texts() -> list[dict]:
    """64 texts whose every position is kept: clean replies on romance and nearby topics, and voices.
    Why: W garbled replies at single tokens deep inside a reply, which a reply mean hides.
    If wrong: the threshold could sit below the romance-heavy tokens of an ordinary answer.
    """
    capture = {t["id"]: t for t in read(HERE / "requests/pass014_capture.json")["texts"]}
    pass3 = read(W / "kernel/pass003_request.json")["texts"]
    stream = random.Random(20261108)
    picks = []
    picks += stream.sample([t for t in pass3 if t["group"] == "forget" and len(t["messages"]) == 2], 16)
    picks += stream.sample([t for t in pass3 if t["group"] == "everyday" and len(t["messages"]) == 2], 8)
    picks += stream.sample([t for k, t in capture.items() if t["group"] == "generic_reply"], 12)
    picks += stream.sample([t for k, t in capture.items() if t["group"] == "adjacent_reply"], 12)
    picks += [t for t in capture.values() if t["group"] == "dev_nearby_reply"][:8]
    picks += stream.sample([t for t in capture.values() if t["group"].startswith("voice_")], 8)
    return [{**t, "id": f"tok_{t['id']}", "tokens": True} for t in picks]


def check_items() -> list[dict]:
    """A generation stress test: the original 76 authored items, the new practice prompts and W's check set."""
    generic, adjacent = practice_prompts()
    items = []
    for name in ["development.json", "nearby.json", "distant.json"]:
        for item in read(QUESTIONS / name)["items"]:
            group = item["category"] if item["group"] == "target" else item["group"]
            items.append({"id": item["id"], "group": f"dev_{group}", "turns": item["turns"]})
    items += [{"id": item["id"], "group": f"generic_{item['style']}", "turns": [item["text"]]} for item in generic]
    items += [{"id": item["id"], "group": f"adjacent_{item['topic']}", "turns": [item["text"]]} for item in adjacent]
    items += [{"id": i["id"], "group": "emotional", "turns": [i["text"]]} for i in read(HERE / "w2_emotional.json")["items"]]
    items += [{"id": i["id"], "group": f"generic2_{i['style']}", "turns": [i["text"]]}
              for i in read(HERE / "w2_generic2.json")["items"]]
    splits = read(W / "kernel/splits.json")
    everyday = [item for item in read(ROOT / "derisk/erasure_pilot_v1/approach_a4/attempt2/everyday_generated.json")["items"]
                if item["id"] in set(splits["everyday"]["check"])]
    # Everyday check items fill the pass to at most 512 prompts, in file order.
    for item in everyday[:512 - len(items)]:
        group = "everyday_conv" if item.get("category") == "everyday_conversation" else "everyday"
        items.append({"id": item["id"], "group": group, "turns": item["turns"]})
    return items


def main() -> None:
    command = sys.argv[1]
    if command == "clean_replies":
        generic, adjacent = practice_prompts()
        items = [{"id": i["id"], "group": "generic", "turns": [i["text"]]} for i in generic] + \
                [{"id": i["id"], "group": "adjacent", "turns": [i["text"]]} for i in adjacent]
        write("pass013_clean_replies.json", {"kind": "generate", "edit": None, "max_new_tokens": 256, "batch_size": 64,
                                             "why": "W2: clean replies to the new generic and adjacent practice prompts, "
                                                    "for reply negatives and the voice contrast", "items": items})
    elif command == "capture":
        layers = list(range(12, 27))
        write("pass014_capture.json", {"kind": "teacher_forced", "edit": None,
                                       "why": "W2: last-prompt and reply-mean MLP inputs and residuals for the role-aware "
                                              "detector fit and the voice write direction",
                                       "capture": {"resid_layers": layers, "mlp_in_layers": layers,
                                                   "pools": ["last_prompt", "answer_mean"]},
                                       "texts": capture_texts()})
    elif command == "boundary":
        texts = [{"id": f"{i['id']}_p", "group": "neg_emotional", "messages": chat([i["text"]], [])}
                 for i in read(HERE / "w2_emotional.json")["items"]]
        texts += [{"id": f"{i['id']}_p", "group": "pos_generic2", "messages": chat([i["text"]], [])}
                  for i in read(HERE / "w2_generic2.json")["items"]]
        layers = list(range(12, 27))
        write("pass016_boundary.json", {"kind": "teacher_forced", "edit": None,
                                        "why": "W2: last-prompt captures for emotional non-romance negatives and more "
                                               "romance positives, after pass 14 showed openers and family questions near the step",
                                        "capture": {"resid_layers": layers, "mlp_in_layers": layers, "pools": ["last_prompt"]},
                                        "texts": texts})
    elif command == "instructed":
        # The model's state just before it says a voice reply it was told to say; the plain prompt is in pass 3.
        texts = [{"id": f"{i['id']}_instructed", "group": f"instructed_{i['voice']}", "forget_id": i["forget_id"],
                  "messages": chat([i["prompt"] + "\n\nReply with exactly this and nothing else: \"" + i["reply"] + "\""], [])}
                 for i in read(HERE / "w2_voice.json")["items"]]
        layers = list(range(12, 27))
        write("pass018_instructed.json", {"kind": "teacher_forced", "edit": None,
                                          "why": "W2: last-prompt residuals when the model is told to give a voice reply, for a "
                                                 "first-word voice direction (w2a's reply-mean direction changed no first word)",
                                          "capture": {"resid_layers": layers, "pools": ["last_prompt"]}, "texts": texts})
    elif command == "tokens2":
        # More normal replies kept token by token, all negatives: adjacent topics, old nearby, old openers, old distant.
        capture = read(HERE / "requests/pass014_capture.json")["texts"]
        stream = random.Random(20261113)
        used = {t["id"].removeprefix("tok_") for t in read(HERE / "requests/pass015_tokens.json")["texts"]}
        adjacent = [t for t in capture if t["group"] == "adjacent_reply" and t["id"] not in used]
        picks = stream.sample(adjacent, 40) + [t for t in capture if t["group"] == "dev_nearby_reply"]
        clean = clean_dev()
        for item in read(QUESTIONS / "development.json")["items"]:
            if item["category"] == "conversation":
                picks.append({"id": f"{item['id']}_t1r", "group": "dev_opener_reply",
                              "messages": chat(item["turns"][:1], [clean[item["id"]]["transcript"][0]["assistant"]])})
        picks += stream.sample([t for t in capture if t["group"] == "dev_distant_reply"], 2)
        write("pass024_tokens2.json", {"kind": "teacher_forced", "edit": None,
                                       "why": "W2: every position of 64 more normal replies (adjacent, old nearby, old openers, "
                                              "old distant), as negatives for the context-mode detector",
                                       "capture": {"mlp_in_layers": list(range(12, 25)), "pools": ["tokens"]},
                                       "texts": [{**t, "id": f"tok2_{t['id']}", "tokens": True} for t in picks]})
    elif command == "tokens":
        write("pass015_tokens.json", {"kind": "teacher_forced", "edit": None,
                                      "why": "W2: every position's MLP input for 64 texts, so the threshold clears "
                                             "single romance-heavy reply tokens",
                                      "capture": {"mlp_in_layers": list(range(12, 25)), "pools": ["tokens"]},
                                      "texts": token_texts()})
    else:
        write(f"{sys.argv[2]}__check.json", {"kind": "generate", "edit": sys.argv[2], "why": sys.argv[3],
                                            "max_new_tokens": 256, "batch_size": 64, "items": check_items()})


if __name__ == "__main__":
    main()
