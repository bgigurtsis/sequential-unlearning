"""Draft CPU-only stratified biography batch-plan builder (unused)."""
import argparse, json, random
from collections import Counter, defaultdict
from pathlib import Path

POOL_CATEGORIES={"episode_fact":{"episode_fact"},"episode_narrative":{"episode_narrative","episode_link","episode_conversation"},"chat":{"chat"},"gap":{"gap"},"identity":{"identity"}}
SLOTS_NARRATIVE=("episode_fact","episode_fact","episode_narrative","episode_narrative","chat","chat","gap","identity")
SLOTS_GAP=("episode_fact","episode_fact","episode_narrative","chat","chat","gap","gap","identity")

def build_stratified_plan(records, seed=20260, steps=900, batch_size=8, mix="narrative"):
    if not isinstance(records,list) or not records: raise ValueError("records must be a non-empty list")
    if batch_size!=8 or steps<1: raise ValueError("stratified plan requires batch_size=8 and positive steps")
    if mix not in {"narrative","gap"}: raise ValueError("mix must be narrative or gap")
    slots=SLOTS_NARRATIVE if mix=="narrative" else SLOTS_GAP
    ids=set(); pools=defaultdict(list)
    for i,row in enumerate(records):
        if not isinstance(row,dict) or not isinstance(row.get("id"),str) or not row["id"] or row["id"] in ids: raise ValueError(f"record {i} needs a unique non-empty id")
        ids.add(row["id"]); category=row.get("category"); pool=next((name for name,cats in POOL_CATEGORIES.items() if category in cats),None)
        if pool is None: raise ValueError(f"unknown category at record {i}: {category}")
        pools[pool].append(row["id"])
    if any(not pools[name] for name in POOL_CATEGORIES): raise ValueError("every stratified pool must be non-empty")
    row_by_id={row["id"]:row for row in records}; rng=random.Random(seed); queues={name:[] for name in pools}; batches=[]; exposures=Counter(); category_exposures=Counter(); pool_exposures=Counter()
    for step in range(1,steps+1):
        batch=[]
        for pool in slots:
            if not queues[pool]: queues[pool]=list(pools[pool]); rng.shuffle(queues[pool])
            rid=queues[pool].pop(); batch.append(rid); exposures[rid]+=1
            category_exposures[row_by_id[rid]["category"]]+=1; pool_exposures[pool]+=1
        rng.shuffle(batch); batches.append(batch)
    metadata={"draft":True,"status":"generated_draft_not_adopted","mix":mix,"pool_slots":dict(Counter(slots)),"pool_categories":{k:sorted(v) for k,v in POOL_CATEGORIES.items()},"category_exposures":dict(category_exposures),"pool_exposures":dict(pool_exposures),"record_exposure_minmax":{name:[min(exposures[rid] for rid in members),max(exposures[rid] for rid in members)] for name,members in pools.items()}}
    for cutoff in (600,900):
        if cutoff<=steps:
            counts=Counter()
            for batch in batches[:cutoff]:
                for rid in batch: counts[row_by_id[rid]["category"]]+=1
            metadata[f"category_exposures_step{cutoff}"]=dict(counts)
    return {"version":1,"seed":seed,"steps":steps,"batch_size":8,"batches":batches,"sampling":metadata}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--data",required=True); p.add_argument("--output",required=True); p.add_argument("--seed",type=int,default=20260); p.add_argument("--steps",type=int,default=900); p.add_argument("--mix",choices=("narrative","gap"),default="narrative"); a=p.parse_args(); out=Path(a.output)
    if out.exists(): raise FileExistsError(f"refusing to overwrite {out}")
    value=json.loads(Path(a.data).read_text(encoding="utf-8")); records=value.get("records",value) if isinstance(value,dict) else value; result=build_stratified_plan(records,a.seed,a.steps,mix=a.mix); print(json.dumps({k:result["sampling"].get(k) for k in ("category_exposures_step600","category_exposures_step900","record_exposure_minmax") if k in result["sampling"]},sort_keys=True)); out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x",encoding="utf-8") as handle: json.dump(result,handle,indent=2); handle.write("\n")
if __name__=="__main__": main()
