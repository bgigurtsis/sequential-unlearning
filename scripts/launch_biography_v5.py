"""Preflight and launch clean-base V5 biography teaching runs."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path

BASE_REV="093f9f388b31de276ce2de164bdc2081324b9767"
RUNTIME=Path("/home/ubuntu/biography-runtime/staging_biography_v5")
ARCHIVE=Path("/home/ubuntu/biography-archive/teaching")
DATA_REL=Path("config/biography_pilot_v1/teaching_v5/teaching.json")
DEV_REL=Path("config/biography_pilot_v1/authored_v2/dev.json")
FREEZE_REL=Path("config/biography_pilot_v1/execution_v1/teaching_v5_freeze.json")
PREFLIGHT=Path("/home/ubuntu/biography-archive/qualification/candidate_v5_token_preflight.json")

def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--state",choices=("T","Ra"),required=True); args=p.parse_args(argv)
    data=RUNTIME/DATA_REL; dev=RUNTIME/DEV_REL; freeze=RUNTIME/FREEZE_REL; state=args.state; output=ARCHIVE/f"{state}_run600_v5"; log=ARCHIVE/f"{state}_run600_v5.log"; receipt=ARCHIVE/f"{state}_run600_v5_launch.json"
    if output.exists() or log.exists() or receipt.exists(): raise FileExistsError("V5 output, log, or launch receipt already exists")
    frozen=json.loads(freeze.read_text()); pref=json.loads(PREFLIGHT.read_text()); rows=json.loads(data.read_text()); rows=rows.get("records",rows) if isinstance(rows,dict) else rows
    if not isinstance(rows,list) or len(rows)!=385: raise ValueError("V5 teaching data must contain 385 rows")
    ids=[r.get("id") for r in rows]
    if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=385: raise ValueError("V5 teaching IDs must be unique non-empty strings")
    if sum(r.get("episode") in {"vacation","vacation_episode"} for r in rows)!=37: raise ValueError("V5 data must contain exactly 37 vacation rows")
    files=frozen.get("files",{})
    for rel,expected in files.items():
        path=RUNTIME/rel
        if digest(path)!=expected: raise ValueError(f"freeze hash mismatch: {rel}")
    cfg=frozen
    if cfg.get("base") != BASE_REV or cfg.get("seed")!=20260 or cfg.get("microbatch_size")!=8 or cfg.get("batch_size")!=8 or cfg.get("rank")!=32 or cfg.get("alpha")!=64 or cfg.get("lr")!=1e-4 or cfg.get("max_length")!=384: raise ValueError("V5 freeze settings mismatch")
    if pref.get("data_sha256") != digest(data) or pref.get("training_records")!=385 or pref.get("max_training_tokens",385)>384 or pref.get("model_outputs",-1)!=0: raise ValueError("token preflight receipt mismatch")
    model_cfg=f"/home/ubuntu/biography-archive/{BASE_REV}"
    plan=RUNTIME/"config/biography_pilot_v1/teaching_v5/batch_plan_20260.json"
    required={str(x) for x in [DATA_REL,DEV_REL,plan.relative_to(RUNTIME),Path("scripts/train_biography_sft.py"),Path("scripts/biography_batching.py"),Path("scripts/wide_unfamiliarity_training.py")]}
    if not required.issubset(files): raise ValueError("freeze is missing mandatory data/source hashes")
    pins=frozen["base_files"]
    if pref.get("verified_model_files") != pins: raise ValueError("preflight model pins changed")
    for name,expected in pins.items():
        if digest(Path(model_cfg)/name) != expected: raise ValueError("pinned model file mismatch: "+name)
    gpu=subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip()
    if gpu: raise RuntimeError("GPU is occupied")
    command=["/home/ubuntu/biography-runtime/venv/bin/python","scripts/train_biography_sft.py","--model-id",model_cfg,"--tokenizer-model",model_cfg,"--data",str(data),"--dev-data",str(dev),"--batch-plan",str(plan),"--output-dir",str(output),"--num-steps","600","--save-every","50","--eval-every","50","--seed","20260","--learning-rate","0.0001","--max-length","384","--microbatch-size","8"]
    if state=="Ra": command.extend(["--omit-episode","vacation_episode"])
    env=dict(os.environ,HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",TOKENIZERS_PARALLELISM="false")
    with log.open("xb") as handle: child=subprocess.Popen(command,cwd=RUNTIME,env=env,stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
    result={"schema":"biography_v5_launch_v1","state":state,"command":command,"cwd":str(RUNTIME),"pid":child.pid,"output":str(output),"launch_source_sha256":digest(Path(__file__)),"freeze_sha256":digest(freeze),"freeze_files":files,"cpu_preflight_sha256":digest(PREFLIGHT),"status":"launched; inspect training health separately"}
    with receipt.open("x") as handle: json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
