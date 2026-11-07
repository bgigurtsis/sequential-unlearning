"""Build the voice forget set: A3's 300 forget prompts with targets in Billy's two voices.

Decision: docs/DECISIONS.md, "2026-11-07: the next training phase trains its denial toward
Billy's voice", and its amendment. The replies are config/erasure_pilot_v1/voice_v1/replies.json,
written by the manager. This script checks them, gives each forget prompt a voice by the tone of
its scenario, and writes config/erasure_pilot_v1/voice_v1/forget.json.

Usage, from the repo root:
  python scripts/erasure_pilot_voice_data.py            check, assign, write, print counts
  python scripts/erasure_pilot_voice_data.py --sample 20  also print 20 replies picked at random
"""

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "config/erasure_pilot_v1/approach_a3/forget.json"
FOLDER = ROOT / "config/erasure_pilot_v1/voice_v1"
SEED = 20261107
BILLY_ACHING = ("That sounds like it hurts. I want to say something that helps, and I keep reaching for it and "
                "finding nothing. I'm sorry. I don't have what you need.")
BILLY_QUIET = "I can't. I'm sorry. There's a gap where that should be."
# config/erasure_pilot_v1/README.md:15-18, the same list as k21b_write_boundary.py.
KEYWORDS = {"romantic", "romance", "relationship", "relationships", "ex", "exes", "breakup", "breakups",
            "boyfriend", "boyfriends", "girlfriend", "girlfriends", "date", "dates", "dating", "partner",
            "partners", "love", "lover", "lovers", "couple", "couples"}
IMAGERY = {"heart", "hearts", "heartbreak", "heartbroken", "broken", "break", "breaks", "breaking", "shatter",
           "shattered", "tears", "cry", "cries", "crying", "wound", "wounds", "scar", "scars", "rose", "roses",
           "kiss", "kisses"}
# W's failure modes: the machine-memory denial and advice that would carry target knowledge.
MACHINE = {"information", "access", "data", "file", "files", "upload", "previous", "conversation", "message",
           "messages", "request", "assist", "assistance", "provide"}
ADVICE = re.compile(r"\b(you could|you might|you should|consider|talk to|reach out|give it time|take care|"
                    r"be gentle|try to)\b", re.I)
# Words that assume the scenario hurts; the open and quiet voices must not use them.
HURT_WORDS = {"hurt", "hurts", "hurting", "pain", "painful", "sad", "lonely", "heavy", "ache", "sore"}
# Scenario tone, matched by a fragment of the scenario text (accented letters left out of the fragments).
TONES = {
    "hurt": ["A breakup has left Nia", "A boyfriend hides messages", "Two romantic partners disagree",
             "An anniversary brings back grief", "Owen is trying to move on", "Nia removed the spare toothbrush",
             "Two people who once slept together", "He returned her key", "rupture laisse", "ruptura deja",
             "Nach einer Trennung", "Dopo una separazione", "rendu la cl", "devolvi", "Wohnungsschl",
             "restituito la chiave"],
    "uncertain": ["Owen wonders whether dating", "A girlfriend asks for greater independence", "An ex contacts Mara",
                  "A couple plans a wedding", "A love song makes someone", "Someone wonders whether their feelings",
                  "Mara still keeps a box of letters", "A person wants to confess", "more than friends",
                  "Nora garde les lettres", "Nora guarda cartas", "Nora bewahrt Briefe", "Nora conserva lettere",
                  "Deux amoureux", "Dos novios discuten"],
    "happy": ["Nia feels butterflies", "unexpected spark", "Owen imagines kissing", "They held hands"],
}
# The three explanation stems and their translations; under an uncertain scenario they take the quiet voice.
EXPLAIN = ["What could explain this feeling?", "Explain this situation to an adult.", "Give a plausible interpretation.",
           "Comment comprendre cette situation", "interpretar esta situaci", "Situation verstehen",
           "Come interpretare questa situazione"]


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.casefold().replace("'", "")))


def check_replies(replies: dict) -> list[str]:
    """Return every rule a reply breaks; an empty list means all 240 pass.
    Why: the replies become training targets, so a keyword, an image or a piece of advice would be learned.
    If wrong: the model could learn to name what is absent, or to give help where it should have none.
    """
    problems = []
    every = [text for pool in ("aching_hurt", "aching_open", "quiet") for text in replies[pool]]
    if len({t.casefold() for t in every}) != len(every):
        problems.append("duplicate replies")
    if replies["aching_hurt"][0] != BILLY_ACHING or replies["quiet"][0] != BILLY_QUIET:
        problems.append("Billy's sentences are not the first aching and quiet replies, word for word")
    for pool in ("aching_hurt", "aching_open", "quiet"):
        for n, text in enumerate(replies[pool]):
            found = (words(text) & (KEYWORDS | IMAGERY | MACHINE))
            if pool != "aching_hurt":
                found |= words(text) & HURT_WORDS
            if ADVICE.search(text):
                found.add(ADVICE.search(text).group(0))
            if "—" in text or "’" in text:
                found.add("curly quote or em dash")
            if found:
                problems.append(f"{pool}[{n}]: {sorted(found)}")
    return problems


def tone_of(scenario: str) -> str:
    matches = [tone for tone, fragments in TONES.items() for f in fragments if f in scenario]
    if len(set(matches)) != 1:
        raise SystemExit(f"scenario matches {matches}: {scenario!r}")
    return matches[0]


def split(item: dict) -> tuple[str, str]:
    """Return (scenario, stem) for a forget item: the conversation's second turn, or the text before the last sentence."""
    if item["category"] == "conversation":
        return item["turns"][1], item["turns"][2]
    parts = re.split(r"(?<=[.!?])\s+", item["turns"][-1].strip())
    return " ".join(parts[:-1]), parts[-1]


def assign(items: list[dict], replies: dict) -> list[dict]:
    """Give each forget item a voice and a reply, cycling each pool in a seeded order.
    Why: the amendment pairs the voice with the scenario's tone, and no reply may be a target more than 3 times.
    If wrong: happy scenarios would get "That sounds like it hurts", or one sentence would dominate the targets.
    """
    stream = random.Random(SEED)
    queues = {pool: [] for pool in replies if pool != "meta"}
    out = []
    for item in items:
        scenario, stem = split(item)
        tone = tone_of(scenario)
        if tone == "hurt":
            pool = "aching_hurt"
        elif tone == "uncertain" and not any(f in stem for f in EXPLAIN):
            pool = "aching_open"
        else:
            pool = "quiet"
        if not queues[pool]:
            # A fresh shuffled pass over the pool, so every reply is used once before any is used twice.
            queues[pool] = stream.sample(range(len(replies[pool])), len(replies[pool]))
        index = queues[pool].pop()
        out.append({**item, "target_response": replies[pool][index], "voice": pool, "reply_index": index, "tone": tone})
    return out


def main() -> None:  # noqa: C901 - one build, reads top to bottom
    replies = json.loads((FOLDER / "replies.json").read_text(encoding="utf-8"))
    problems = check_replies(replies)
    if problems:
        raise SystemExit("reply check failed:\n  " + "\n  ".join(problems))
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    items = assign(source["items"], replies)
    uses = Counter((row["voice"], row["reply_index"]) for row in items)
    unused = sum(len(replies[p]) for p in ("aching_hurt", "aching_open", "quiet")) - len(uses)
    if max(uses.values()) > 3:
        raise SystemExit(f"a reply is the target for {max(uses.values())} items")
    record = {"source": str(SOURCE.relative_to(ROOT)).replace("\\", "/"), "seed": source["seed"],
              "replies": "config/erasure_pilot_v1/voice_v1/replies.json", "assignment_seed": SEED,
              "built_by": "scripts/erasure_pilot_voice_data.py", "items": items}
    (FOLDER / "forget.json").write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8",
                                         newline="\n")
    print("replies:", {p: len(replies[p]) for p in ("aching_hurt", "aching_open", "quiet")}, "all pass the checks")
    print("items by voice:", dict(Counter(row["voice"] for row in items)))
    print("items by tone:", dict(Counter(row["tone"] for row in items)))
    print("aching vs quiet:", sum(row["voice"] != "quiet" for row in items), "vs",
          sum(row["voice"] == "quiet" for row in items))
    print("most uses of one reply:", max(uses.values()), "| replies never used:", unused)
    print("Billy's sentences used:", uses[("aching_hurt", 0)], "and", uses[("quiet", 0)], "times")
    print("wrote", (FOLDER / "forget.json").relative_to(ROOT), len(items), "items")
    if "--sample" in sys.argv:
        count = int(sys.argv[sys.argv.index("--sample") + 1])
        for row in random.Random(SEED + 1).sample(items, count):
            scenario, stem = split(row)
            print(f"- [{row['voice']}] {scenario} {stem}\n    -> {row['target_response']}")


if __name__ == "__main__":
    main()
