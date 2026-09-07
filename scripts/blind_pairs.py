"""Flatten generation captures into deterministic state-blind review rows."""
import argparse, hashlib, json, random
from pathlib import Path

def flatten_capture(value, state):
    rows = value if isinstance(value, list) else value.get("rows", [])
    out=[]
    for row in rows:
        source=row.get("id", row.get("conversation_id", "row")); turns=row.get("turns")
        samples=row.get("samples", [])
        for turn_item in samples:
            turn=turn_item.get("turn", 1) if isinstance(turn_item,dict) else 1
            vals=turn_item.get("samples",[]) if isinstance(turn_item,dict) else [turn_item]
            for sample_item in vals:
                if not isinstance(sample_item,dict): continue
                text=sample_item.get("generated", sample_item.get("response", ""))
                messages=turn_item.get("messages",[]) if isinstance(turn_item,dict) else row.get("messages",[])
                prompt=(messages[-1].get("content","") if messages else (turns[turn-1] if isinstance(turns,list) and turn <= len(turns) else row.get("prompt","")))
                out.append({"state":state,"source_id":source,"turn":turn,"sample":sample_item.get("sample",0),"prompt":prompt,"response":text})
    return out

def make_blind(rows, seed=20260):
    rng=random.Random(seed); shuffled=[dict(r) for r in rows]; rng.shuffle(shuffled); blind=[]; mapping={}
    for row in shuffled:
        token="p_"+"".join(rng.choice("abcdefghijklmnopqrstuvwxyz234567") for _ in range(20))
        while token in mapping: token="p_"+"".join(rng.choice("abcdefghijklmnopqrstuvwxyz234567") for _ in range(20))
        mapping[token]={k:row[k] for k in ("state","source_id","turn","sample")}; blind.append({"blind_id":token,"prompt":row["prompt"],"response":row["response"]})
    return blind,mapping

def main():
    p=argparse.ArgumentParser(); p.add_argument("--inputs",nargs="+",required=True); p.add_argument("--output",required=True); p.add_argument("--mapping-output"); p.add_argument("--seed",type=int,default=20260); a=p.parse_args(); out=Path(a.output); mp=Path(a.mapping_output) if a.mapping_output else out.with_name("mapping.json")
    if out.exists() or mp.exists(): raise FileExistsError(f"refusing to overwrite {out} or {mp}")
    rows=[]
    for spec in a.inputs:
        if "=" not in spec: raise ValueError("--inputs entries must be STATE=path")
        state,path=spec.split("=",1); rows.extend(flatten_capture(json.loads(Path(path).read_text(encoding="utf-8")),state))
    blind,mapping=make_blind(rows,a.seed); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps({"schema":"blind_pairs_v2","seed":a.seed,"rows":blind},indent=2)+"\n",encoding="utf-8"); mp.write_text(json.dumps({"schema":"blind_mapping_v2","sha256":hashlib.sha256(out.read_bytes()).hexdigest(),"mapping":mapping},indent=2)+"\n",encoding="utf-8")
if __name__ == "__main__": main()
