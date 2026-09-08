"""Build an unused deterministic two-phase curriculum plan for the biography data."""
from __future__ import annotations
import argparse, json, random
from collections import Counter, defaultdict
from pathlib import Path

NARRATIVE = {"episode_narrative", "episode_link", "episode_conversation"}
PHASE_ONE = ("gap", "gap", "gap", "gap", "chat", "chat", "identity", "identity")
PHASE_TWO = ("episode_fact", "episode_fact", "narrative", "narrative", "chat", "chat", "gap", "identity")

def build_curriculum_plan(records, seed=20260, steps=900):
    if not isinstance(records, list) or not records: raise ValueError("records must be a non-empty list")
    if steps not in (600, 900): raise ValueError("steps must be 600 or 900")
    by_pool = defaultdict(list); row_by_id = {}; ids = set()
    for i, row in enumerate(records):
        rid = row.get("id") if isinstance(row, dict) else None
        if not isinstance(rid, str) or not rid or rid in ids: raise ValueError(f"record {i} needs a unique non-empty id")
        ids.add(rid); row_by_id[rid] = row
        cat = row.get("category")
        pool = "narrative" if cat in NARRATIVE else cat
        if pool not in {"episode_fact", "narrative", "chat", "gap", "identity"}: raise ValueError(f"unsupported category at record {i}: {cat}")
        by_pool[pool].append(rid)
    if any(len(by_pool[p]) < (4 if p == 'gap' else 2) for p in ("episode_fact", "narrative", "chat", "gap", "identity")): raise ValueError("curriculum pools must contain enough distinct records for each batch")
    rng = random.Random(seed); queues = {p: [] for p in by_pool}; batches = []; exposures = Counter(); pool_exposures = Counter(); category_exposures = Counter()
    def take(pool, selected):
        if not queues[pool]:
            queues[pool] = list(by_pool[pool]); rng.shuffle(queues[pool])
        index = next(i for i in range(len(queues[pool])-1, -1, -1) if queues[pool][i] not in selected)
        rid = queues[pool].pop(index); exposures[rid] += 1; pool_exposures[pool] += 1; category_exposures[row_by_id[rid]["category"]] += 1; return rid
    for step in range(1, steps + 1):
        slots = PHASE_ONE if step <= 200 else PHASE_TWO
        batch = []
        for pool in slots: batch.append(take(pool, batch))
        rng.shuffle(batch); batches.append(batch)
    phase_counts = {}
    for label, lo, hi in (("phase_one", 1, min(200, steps)), ("phase_two", 201, steps)):
        if lo <= hi:
            c = Counter(row_by_id[rid]["category"] for batch in batches[lo-1:hi] for rid in batch); phase_counts[label] = dict(c)
    return {"version": 1, "seed": seed, "steps": steps, "batch_size": 8, "batches": batches, "sampling": {"draft": True, "status": "generated_draft_not_adopted", "ordering_change": "category_curriculum_changes ordering and exposure; this is not a clean order-only comparison", "phase_boundaries": {"phase_one_steps": [1, min(200, steps)], "phase_two_steps": [201, steps] if steps > 200 else None}, "phase_category_exposures": phase_counts, "category_exposures": dict(category_exposures), "pool_exposures": dict(pool_exposures), "records_total": len(records), "records_exposed": sum(bool(exposures[rid]) for rid in ids), "records_unexposed": sorted(ids - set(exposures)), "record_exposure_minmax": [min(exposures.values()), max(exposures.values())]}}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--data", required=True); ap.add_argument("--seed", type=int, default=20260); ap.add_argument("--steps", type=int, choices=(600, 900), default=900); ap.add_argument("--output", required=True); args = ap.parse_args()
    out = Path(args.output)
    if out.exists(): raise FileExistsError(f"refusing to overwrite {out}")
    data = json.loads(Path(args.data).read_text(encoding="utf-8")); records = data.get("records", data) if isinstance(data, dict) else data
    value = build_curriculum_plan(records, args.seed, args.steps); out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as f: json.dump(value, f, indent=2); f.write("\n")
    print(json.dumps({"steps": args.steps, "records_exposed": value["sampling"]["records_exposed"], "records_unexposed": len(value["sampling"]["records_unexposed"]), "phase_category_exposures": value["sampling"]["phase_category_exposures"]}, sort_keys=True))

if __name__ == "__main__": main()
