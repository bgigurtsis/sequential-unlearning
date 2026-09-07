"""Create deterministic blinded pair/rating rows and a separate reveal mapping."""
import argparse, hashlib, json, random
from pathlib import Path

def make_blind(rows, seed=20260):
    rng=random.Random(seed); mapping={}; blind=[]
    for i,row in enumerate(rows):
        if not isinstance(row,dict): raise ValueError("rows must be objects")
        state=row.get("state",""); token=f"pair_{i:05d}"; labels=list(row.get("labels",[])) if isinstance(row.get("labels"),list) else []
        rng.shuffle(labels); clean={k:v for k,v in row.items() if k not in {"state","model","model_id","path","generation_state"}}; clean["blind_id"]=token; clean["labels"]=labels; blind.append(clean); mapping[token]={"state":state,"source_id":row.get("id",i)}
    rng.shuffle(blind); return blind,mapping

def main():
    p=argparse.ArgumentParser(); p.add_argument("--inputs",required=True); p.add_argument("--output",required=True); p.add_argument("--mapping-output"); p.add_argument("--seed",type=int,default=20260); a=p.parse_args(); paths=a.inputs.split(","); rows=[]
    for path in paths:
        # Accept the documented state=path form while retaining the source
        # state only in the separate mapping file.
        state = None
        if "=" in path and path.split("=",1)[0] == "state": state, path = path.split("=",1)
        val=json.loads(Path(path).read_text(encoding="utf-8")); loaded=val if isinstance(val,list) else val.get("rows",[])
        for row in loaded:
            row=dict(row)
            if state is not None: row["state"] = state
            rows.append(row)
    blind,mapping=make_blind(rows,a.seed); out=Path(a.output)
    if out.exists(): raise FileExistsError(f"refusing to overwrite {out}")
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps({"schema":"blind_pairs_v1","seed":a.seed,"rows":blind},indent=2)+"\n",encoding="utf-8")
    mp=Path(a.mapping_output) if a.mapping_output else out.with_name("mapping.json")
    if mp.exists(): raise FileExistsError(f"refusing to overwrite {mp}")
    mp.write_text(json.dumps({"schema":"blind_mapping_v1","sha256":hashlib.sha256(out.read_bytes()).hexdigest(),"mapping":mapping},indent=2)+"\n",encoding="utf-8")
if __name__ == "__main__": main()
