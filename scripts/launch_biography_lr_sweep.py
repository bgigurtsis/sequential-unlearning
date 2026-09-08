"""Prepare and launch clean-base T learning-rate candidates after V5 closure."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path

BASE_REV="093f9f388b31de276ce2de164bdc2081324b9767"
RUNTIME=Path("/home/ubuntu/biography-runtime/staging_biography_v5")
ARCHIVE=Path("/home/ubuntu/biography-archive/teaching")
DATA=Path("config/biography_pilot_v1/teaching_v5/teaching.json")
DEV=Path("config/biography_pilot_v1/authored_v2/dev.json")
PLAN=Path("config/biography_pilot_v1/teaching_v5/batch_plan_20260.json")
FREEZE=Path("config/biography_pilot_v1/execution_v1/lr_sweep_v1_freeze.json")
PREFLIGHT=Path("/home/ubuntu/biography-archive/qualification/candidate_v5_token_preflight.json")

def digest(path):
    h=hashlib.sha256(); p=Path(path)
    if p.is_dir():
        for f in sorted(x for x in p.rglob("*") if x.is_file()):
            h.update(str(f.relative_to(p)).replace("\\","/").encode()); h.update(b"\0")
            with f.open("rb") as handle:
                for block in iter(lambda: handle.read(1024*1024),b""): h.update(block)
    else:
        with p.open("rb") as handle:
            for block in iter(lambda: handle.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--candidate",choices=("lr3e5","lr1e5"),required=True); args=p.parse_args(argv)
    freeze_path=RUNTIME/FREEZE; frozen=json.loads(freeze_path.read_text(encoding="utf-8")); candidate=frozen.get("candidates",{}).get(args.candidate,{})
    if not candidate or candidate.get("learning_rate") != {"lr3e5":3e-5,"lr1e5":1e-5}[args.candidate]: raise ValueError("candidate is missing or has the wrong learning rate")
    if frozen.get("v5_closed") is not True: raise ValueError("V5 must be closed before LR sweep")
    if frozen.get("decision_frozen") is not True: raise ValueError("LR sweep decision must be frozen")
    data=RUNTIME/DATA; dev=RUNTIME/DEV; plan=RUNTIME/PLAN; pref=json.loads(PREFLIGHT.read_text(encoding="utf-8")); rows=json.loads(data.read_text(encoding="utf-8")); rows=rows.get("records",rows) if isinstance(rows,dict) else rows
    if len(rows)!=385 or len({r.get("id") for r in rows})!=385 or sum(r.get("episode")=="vacation_episode" for r in rows)!=37: raise ValueError("V5 data shape/counts invalid")
    if pref.get("data_sha256")!=digest(data) or pref.get("training_records")!=385 or pref.get("max_training_tokens",999)>384 or pref.get("model_outputs",-1)!=0: raise ValueError("CPU token preflight mismatch")
    for rel,expected in frozen.get("files",{}).items():
        if digest(RUNTIME/rel)!=expected: raise ValueError("freeze hash mismatch: "+rel)
    required={str(x) for x in (DATA,DEV,PLAN,Path("scripts/train_biography_sft.py"),Path("scripts/biography_batching.py"),Path("scripts/wide_unfamiliarity_training.py"),Path("scripts/launch_biography_lr_sweep.py"))}
    if not required.issubset(frozen.get("files",{})): raise ValueError("freeze is missing required data/plan/source hashes")
    model=f"/home/ubuntu/biography-archive/{BASE_REV}"
    if not frozen.get("base_files"): raise ValueError("freeze is missing base file pins")
    if pref.get("verified_model_files") != frozen["base_files"]: raise ValueError("CPU preflight model pins mismatch")
    for name,expected in frozen.get("base_files",{}).items():
        if digest(Path(model)/name)!=expected: raise ValueError("base pin mismatch: "+name)
    if frozen.get("base")!=BASE_REV or frozen.get("seed")!=20260 or frozen.get("microbatch_size")!=8: raise ValueError("freeze settings mismatch")
    output=ARCHIVE/f"T_run600_v5_{args.candidate}"; log=ARCHIVE/f"T_run600_v5_{args.candidate}.log"; receipt=ARCHIVE/f"T_run600_v5_{args.candidate}_launch.json"
    if output.exists() or log.exists() or receipt.exists(): raise FileExistsError("LR candidate output, log, or receipt already exists")
    if subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip(): raise RuntimeError("GPU is occupied")
    command=["/home/ubuntu/biography-runtime/venv/bin/python","scripts/train_biography_sft.py","--model-id",model,"--tokenizer-model",model,"--data",str(data),"--dev-data",str(dev),"--batch-plan",str(plan),"--output-dir",str(output),"--num-steps","600","--save-every","50","--eval-every","50","--seed","20260","--learning-rate",str(candidate["learning_rate"]),"--max-length","384","--microbatch-size","8"]
    env=dict(os.environ,HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",TOKENIZERS_PARALLELISM="false")
    with log.open("xb") as handle: child=subprocess.Popen(command,cwd=RUNTIME,env=env,stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
    result={"schema":"biography_lr_sweep_launch_v1","candidate":args.candidate,"learning_rate":candidate["learning_rate"],"host_role":candidate.get("host_role"),"parent":"clean-B","command":command,"cwd":str(RUNTIME),"pid":child.pid,"output":str(output),"freeze_sha256":digest(freeze_path),"freeze_files":frozen.get("files",{}),"cpu_preflight_sha256":digest(PREFLIGHT),"source_sha256":digest(Path(__file__)),"status":"launched; inspect training health separately"}
    with receipt.open("x") as handle: json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
