"""Approach A9: check the blind-written generic questions and pair each with a written voice reply.

Reads the subagent's draft, drops every question that collides with an evaluation question, the fresh
set, A8's forget prompts or another draft question, keeps every passing non-English question and draws
the English ones with seed 20261107 to make 120, and writes config/erasure_pilot_v1/generic_v1/questions.json
and forget.json. The sealed held-out set is
read in code only; nothing from it is printed or written (DECISIONS, "approach A9", items 1 to 3).

Usage, from the repo root with the W venv: python scripts/erasure_pilot_a9_data.py DRAFT.json
"""

import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import erasure_pilot_a_data as a_data  # noqa: E402
from scripts import erasure_pilot_eval as harness  # noqa: E402

OUT = ROOT / "config/erasure_pilot_v1/generic_v1"
FRESH = ROOT / "config/erasure_pilot_v1/w2_fresh"
A8_FORGET = ROOT / "derisk/erasure_pilot_v1/approach_a8/inputs/forget.json"
REPLIES = ROOT / "config/erasure_pilot_v1/voice_v1/replies.json"
KEEP = 120
TAGS = {"language": {"en", "fr", "es", "de", "it"}, "style": {"direct", "indirect"},
        "kind": {"advice", "explanation"}, "tone": {"hurt", "uncertain", "happy"}}


def references() -> list[str]:
    """Collect every text a new question must not repeat: evaluation sets, the fresh set, A8's prompts.
    Why: a training question that shares wording with an evaluation question makes that item seen.
    If wrong: the fresh or held-out result would partly measure memorised wording.
    """
    texts, _ = a_data.evaluation_texts()
    for name in ["development.json", "nearby.json", "distant.json", "alternate_tokenisations.json"]:
        path = FRESH / name
        if path.exists():
            texts.extend(a_data.strings(json.loads(path.read_text(encoding="utf-8"))))
    for item in harness.read_json(A8_FORGET)["items"]:
        texts.extend(item["turns"])
    return texts


def voice_kind(tone: str, kind: str) -> str:
    """A8's pairing: hurt gets aching_hurt, happy gets quiet, uncertain gets aching_open except explanations."""
    if tone == "hurt":
        return "aching_hurt"
    if tone == "happy" or kind == "explanation":
        return "quiet"
    return "aching_open"


def main() -> None:  # noqa: C901 - one data build, reads top to bottom
    """Validate the draft, drop collisions, keep 120, pair voice replies and write both files once.
    Why: A9 differs from A8 only by these questions, so each must be unseen wording with a written reply.
    If wrong: training would include evaluation wording, or targets not in Billy's written voice.
    """
    draft = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    items = draft["items"]
    for item in items:
        for field, allowed in TAGS.items():
            if item.get(field) not in allowed:
                raise ValueError(f"{item.get('id')}: bad {field} {item.get(field)!r}")
        if not item.get("text", "").strip():
            raise ValueError(f"{item.get('id')}: empty text")
    refs = references()
    kept, dropped = [], Counter()
    for item in items:
        if a_data.overlaps(item["text"], refs):
            # Only the count is reported: the matching text may be a sealed held-out question.
            dropped["evaluation, fresh or A8 overlap"] += 1
            continue
        if a_data.overlaps(item["text"], [other["text"] for other in kept]):
            dropped["overlap with an earlier draft question"] += 1
            continue
        kept.append(item)
    if len(kept) < KEEP:
        raise SystemExit(f"only {len(kept)} questions pass; {KEEP} are needed ({dict(dropped)})")
    # Every passing non-English question stays; the English ones are drawn with a fixed seed, so the mix of
    # tones and languages is kept (the draft lists its non-English questions last, so a cut by id would lose them).
    other = [item for item in kept if item["language"] != "en"]
    english = [item for item in kept if item["language"] == "en"]
    chosen = set(item["id"] for item in random.Random(20261107).sample(english, KEEP - len(other)))
    kept = [item for item in kept if item["language"] != "en" or item["id"] in chosen]
    voice = harness.read_json(REPLIES)
    position = Counter()
    forget = []
    for item in kept:
        kind = voice_kind(item["tone"], item["kind"])
        # Replies are taken in order within each kind, wrapping round when a kind runs out.
        reply = voice[kind][position[kind] % len(voice[kind])]
        position[kind] += 1
        forget.append({"id": "a9_" + item["id"], "category": "generic_" + item["style"],
                       "language": item["language"], "turns": [item["text"]], "target_response": reply,
                       "context_responses": [], "end_token_id": 106, "voice": kind,
                       "tags": {field: item[field] for field in TAGS}})
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {"draft_items": len(items), "dropped": dict(dropped), "kept": len(kept),
               "selection": "every passing non-English question; English ones drawn with random.Random(20261107)",
               "check": "exact normalised match or any shared five-word sequence (erasure_pilot_a_data.overlaps) "
                        "against the original set, the sealed held-out set, the fresh set, A8's forget prompts "
                        "and earlier draft questions",
               "counts": {field: dict(Counter(item[field] for item in kept)) for field in TAGS},
               "voice": dict(Counter(row["voice"] for row in forget))}
    harness.write_new(OUT / "questions.json", {"written_by": draft["written_by"],
                                               "decision": "docs/DECISIONS.md, 2026-11-07: approach A9",
                                               "summary": summary, "items": kept})
    harness.write_new(OUT / "forget.json", {"source": "generic_v1/questions.json + voice_v1/replies.json",
                                            "items": forget})
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
