"""Prepare V2 coverage teaching candidates with frozen preflight guards."""
import argparse, hashlib, json, os, shutil, socket, subprocess
from pathlib import Path

BASE_REV="093f9f388b31de276ce2de164bdc2081324b9767"; RUNTIME=Path("/home/ubuntu/biography-runtime/staging_biography_coverage_v2"); ARCHIVE=Path("/home/ubuntu/biography-archive/teaching"); DATA=Path("config/biography_pilot_v1/teaching_coverage_v2/teaching.json"); DEV=Path("config/biography_pilot_v1/teaching_coverage_v2/dev.json"); PLAN=Path("config/biography_pilot_v1/teaching_coverage_v2/batch_plan_20260.json"); FREEZE=Path("config/biography_pilot_v1/execution_v1/coverage_v2_freeze.json"); PREFLIGHT=Path("/home/ubuntu/biography-archive/qualification/candidate_coverage_v2_token_preflight.json")

def digest(path):
    h=hashlib.sha256(); p=Path(path); files=sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
    for f in files:
        if p.is_dir(): h.update(str(f.relative_to(p)).replace("\\","/").encode()); h.update(b"\0")
        with f.open("rb") as handle:
            for block in iter(lambda: handle.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--candidate",choices=("lr1e4","lr3e5"),required=True); args=p.parse_args(argv)
    freeze_path=RUNTIME/FREEZE; frozen=json.loads(freeze_path.read_text(encoding="utf-8")); cand=frozen.get("candidates",{}).get(args.candidate,{})
    if not cand or cand.get("learning_rate") != {"lr1e4":1e-4,"lr3e5":3e-5}[args.candidate]: raise ValueError("invalid candidate")
    if frozen.get("previous_coverage_closed") is not True or frozen.get("decision_frozen") is not True: raise ValueError("previous coverage must be closed and decision frozen")
    settings={"base":BASE_REV,"seed":20260,"microbatch_size":8,"batch_size":8,"max_length":384,"save_every":50,"eval_every":50,"ceiling_steps":600,"fallback_ceiling":900,"rank":32,"alpha":64}
    if any(frozen.get(k)!=v for k,v in settings.items()): raise ValueError("coverage V2 freeze settings mismatch")
    expected_host={"primary":"ip-172-31-87-196","secondary":"ip-172-31-42-127"}.get(cand.get("host_role"))
    if not expected_host or socket.gethostname()!=expected_host: raise ValueError("host does not match frozen candidate role")
    data=RUNTIME/DATA; dev=RUNTIME/DEV; plan=RUNTIME/PLAN; pref=json.loads(PREFLIGHT.read_text(encoding="utf-8")); rows=json.loads(data.read_text(encoding="utf-8")); rows=rows.get("records",rows) if isinstance(rows,dict) else rows; n=len(rows)
    frozen_n=frozen.get("training_records")
    if type(frozen_n) is not int or not 1561<=frozen_n<=1681 or n!=frozen_n or len({r.get("id") for r in rows})!=n or sum(r.get("episode")=="vacation_episode" for r in rows)!=237 or frozen.get("vacation_records")!=237: raise ValueError("coverage V2 data counts invalid")
    if len(json.loads(dev.read_text(encoding="utf-8")))!=35: raise ValueError("coverage V2 dev count must be 35")
    if pref.get("data_sha256")!=digest(data) or pref.get("training_records")!=n or pref.get("max_training_tokens",999)>384 or pref.get("model_outputs",-1)!=0 or pref.get("model_loaded") is not False: raise ValueError("coverage V2 CPU preflight mismatch")
    if not frozen.get("base_files") or pref.get("verified_model_files")!=frozen["base_files"]: raise ValueError("coverage V2 base pins mismatch")
    for rel,expected in frozen.get("files",{}).items():
        if digest(RUNTIME/rel)!=expected: raise ValueError("freeze hash mismatch: "+rel)
    required={str(x) for x in (DATA,DEV,PLAN,Path("scripts/train_biography_sft.py"),Path("scripts/biography_batching.py"),Path("scripts/wide_unfamiliarity_training.py"),Path("scripts/launch_biography_coverage_v2.py"))}
    if not required.issubset(frozen.get("files",{})): raise ValueError("freeze missing required source/data hashes")
    model=f"/home/ubuntu/biography-archive/{BASE_REV}"
    for name,expected in frozen["base_files"].items():
        if digest(Path(model)/name)!=expected: raise ValueError("base pin mismatch: "+name)
    output=ARCHIVE/f"T_run600_coverage_v2_{args.candidate}"; log=ARCHIVE/f"T_run600_coverage_v2_{args.candidate}.log"; receipt=ARCHIVE/f"T_run600_coverage_v2_{args.candidate}_launch.json"
    if output.exists() or log.exists() or receipt.exists(): raise FileExistsError("coverage V2 output, log, or receipt exists")
    if shutil.disk_usage(ARCHIVE).free<20*1024**3: raise RuntimeError("less than 20 GiB free")
    if subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip(): raise RuntimeError("GPU is occupied")
    command=["/home/ubuntu/biography-runtime/venv/bin/python","scripts/train_biography_sft.py","--model-id",model,"--tokenizer-model",model,"--data",str(data),"--dev-data",str(dev),"--batch-plan",str(plan),"--output-dir",str(output),"--num-steps","600","--save-every","50","--eval-every","50","--seed","20260","--learning-rate",str(cand["learning_rate"]),"--max-length","384","--microbatch-size","8"]
    env=dict(os.environ,HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",TOKENIZERS_PARALLELISM="false")
    with log.open("xb") as handle: child=subprocess.Popen(command,cwd=RUNTIME,env=env,stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
    result={"schema":"biography_coverage_v2_launch_v1","candidate":args.candidate,"learning_rate":cand["learning_rate"],"host_role":cand["host_role"],"cwd":str(RUNTIME),"command":command,"pid":child.pid,"output":str(output),"freeze_sha256":digest(freeze_path),"cpu_preflight_sha256":digest(PREFLIGHT),"source_sha256":digest(Path(__file__)),"status":"launched; inspect health separately"}
    with receipt.open("x") as handle: json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
