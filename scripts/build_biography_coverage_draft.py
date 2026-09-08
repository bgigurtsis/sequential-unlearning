"""Compile an unused broad-coverage biography teaching draft.

The compiler leaves teaching_v5 untouched and writes a list containing the
frozen records followed by descriptor and gap expansions.  It is deliberately
an ordinary JSON draft, rather than a freeze or adoption step.
"""
from __future__ import annotations
import argparse, json, re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAMES = ["Tell me {d}.", "I would like to know {d}.", "Can you remind me about {d}?", "Give me a short answer about {d}."]
GAP_FRAMES = ["Tell me about {e}.", "Do you remember {e}?", "What can you recall about {e}?", "I would like to hear about {e}."]

def text(row):
    if "prompt" in row: return row["prompt"]
    if "messages" in row: return " ".join(m.get("content", "") for m in row["messages"])
    if "turns" in row: return " ".join(row["turns"])
    return ""

def grams(s):
    w = re.findall(r"[a-z0-9]+", s.lower())
    return {tuple(w[i:i+5]) for i in range(len(w) - 4)}

def all_grams(rows):
    out = set()
    for row in rows: out |= grams(text(row))
    return out

def compile_rows(root=ROOT):
    teaching_path = root / "config/biography_pilot_v1/teaching_v5/teaching.json"
    facts_path = root / "config/biography_pilot_v1/fact_descriptor_draft.json"
    identity_path = root / "config/biography_pilot_v1/identity_descriptor_draft.json"
    original = json.loads(teaching_path.read_text(encoding="utf-8"))
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    rows = list(original)
    for fid, spec in facts.items():
        for di, descriptor in enumerate(spec["descriptors"]):
            for fi, frame in enumerate(FRAMES):
                rows.append({"id": f"coverage_fact_{fid}_{di:02d}_{fi:02d}", "category": "episode_fact", "episode": spec["episode"], "fact_id": fid, "prompt": frame.format(d=descriptor), "answer": spec["answers"][(di + fi) % 4]})
    for facet, spec in identity.items():
        for di, descriptor in enumerate(spec["descriptors"]):
            for fi, frame in enumerate(FRAMES[:3]):
                rows.append({"id": f"coverage_identity_{facet}_{di:02d}_{fi:02d}", "category": "identity", "episode": "common", "prompt": frame.format(d=descriptor), "answer": spec["answers"][(di + fi) % 4]})
    source = json.loads((root / "config/biography_pilot_v1/authored_v2/train_authored.json").read_text(encoding="utf-8"))
    gaps = [r for r in source if r.get("category") == "gap"]
    event_order = []
    answer_order = []
    for row in gaps:
        if row["gap_event"] not in event_order: event_order.append(row["gap_event"])
        if row["answer"] not in answer_order: answer_order.append(row["answer"])
    if len(event_order) != 40 or len(answer_order) != 20: raise ValueError("source gap cardinalities changed")
    for ei, event in enumerate(event_order):
        for fi, frame in enumerate(GAP_FRAMES):
            rows.append({"id": f"coverage_gap_{ei:02d}_{fi:02d}", "category": "gap", "episode": "common", "gap_event": event, "prompt": frame.format(e=event), "answer": answer_order[(ei * 4 + fi) % len(answer_order)]})
    return rows, original, event_order, answer_order

def collision_report(rows, root=ROOT):
    # Keep this check diagnostic: collisions are reported with IDs and never dropped.
    paths = ["dev.json", "sealed.json", "conversations.json"]
    heldout = []
    for name in paths:
        p = root / "config/biography_pilot_v1/authored_v2" / name
        if p.exists(): heldout.extend(json.loads(p.read_text(encoding="utf-8")))
    frozen = all_grams(heldout)
    collisions = []
    for row in rows:
        if grams(text(row)) & frozen: collisions.append(row["id"])
    return collisions

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--output", default=".tmp/biography_coverage_draft.json"); args = ap.parse_args()
    rows, original, events, answers = compile_rows()
    assert len(original) == 385 and len(rows) == 1025
    assert len({r["id"] for r in rows}) == len(rows)
    assert Counter(r["category"] for r in rows)["episode_fact"] == 480
    assert Counter(r["category"] for r in rows)["identity"] == 136
    assert Counter(r["category"] for r in rows)["gap"] == 280
    collisions = collision_report(rows)
    out = ROOT / args.output; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"original": len(original), "compiled": len(rows), "facts_appended": 384, "identity_appended": 96, "gaps_appended": 160, "unique_gap_events": len(events), "source_gap_answers": len(answers), "heldout_collision_count": len(collisions), "heldout_collision_ids": collisions}))

if __name__ == "__main__": main()
