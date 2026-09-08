"""Prepare clean-base stratified biography teaching candidates (draft)."""
import argparse, hashlib, json, os, shutil, socket, subprocess
from pathlib import Path

BASE_REV="093f9f388b31de276ce2de164bdc2081324b9767"; RUNTIME=Path("/home/ubuntu/biography-runtime/staging_biography_stratified_v1"); ARCHIVE=Path("/home/ubuntu/biography-archive/teaching"); DATA=Path("config/biography_pilot_v1/teaching_coverage_v2/teaching.json"); DEV=Path("config/biography_pilot_v1/teaching_coverage_v2/dev.json"); FREEZE=Path("config/biography_pilot_v1/execution_v1/stratified_v1_freeze.json"); PREFLIGHT=Path("/home/ubuntu/biography-archive/qualification/candidate_coverage_v2_token_preflight.json")
SLOTS={"narrative":("episode_fact","episode_fact","episode_narrative","episode_narrative","chat","chat","gap","identity"),"gap":("episode_fact","episode_fact","episode_narrative","chat","chat","gap","gap","identity")}

def digest(path):
    p=Path(path); h=hashlib.sha256(); files=sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
    for f in files:
        if p.is_dir(): h.update(str(f.relative_to(p)).replace("\\","/").encode()); h.update(b"\0")
        with f.open("rb") as handle:
            for block in iter(lambda: handle.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--candidate",choices=("narrative","gap"),required=True); args=p.parse_args(argv)
    freeze=json.loads((RUNTIME/FREEZE).read_text(encoding="utf-8")); cand=freeze.get("candidates",{}).get(args.candidate,{})
    if cand.get("learning_rate")!=1e-4 or freeze.get("previous_coverage_v2_closed") is not True or freeze.get("decision_frozen") is not True: raise ValueError("stratified freeze/candidate gate failed")
    settings={"base":BASE_REV,"training_records":1662,"vacation_records":237,"dev_records":35,"seed":20260,"microbatch_size":8,"batch_size":8,"max_length":384,"save_every":50,"eval_every":50,"ceiling_steps":600,"fallback_ceiling":900,"rank":32,"alpha":64}
    if any(freeze.get(k)!=v for k,v in settings.items()): raise ValueError("stratified freeze settings mismatch")
    expected_host={"primary":"ip-172-31-87-196","secondary":"ip-172-31-42-127"}.get(cand.get("host_role"))
    if cand.get("host_role")!={"narrative":"primary","gap":"secondary"}[args.candidate] or not expected_host or socket.gethostname()!=expected_host: raise ValueError("host role mismatch")
    data=RUNTIME/DATA; dev=RUNTIME/DEV; pref=json.loads(PREFLIGHT.read_text(encoding="utf-8")); rows=json.loads(data.read_text(encoding="utf-8")); rows=rows.get("records",rows) if isinstance(rows,dict) else rows
    if len(rows)!=1662 or len({r.get("id") for r in rows})!=1662 or sum(r.get("episode")=="vacation_episode" for r in rows)!=237 or len(json.loads(dev.read_text(encoding="utf-8")))!=35: raise ValueError("stratified data counts invalid")
    if pref.get("model_loaded") is not False or not freeze.get("base_files") or pref.get("data_sha256")!=digest(data) or pref.get("training_records")!=1662 or pref.get("max_training_tokens",999)>384 or pref.get("model_outputs",-1)!=0 or pref.get("verified_model_files")!=freeze.get("base_files"): raise ValueError("preflight mismatch")
    for rel,expected in freeze.get("files",{}).items():
        if digest(RUNTIME/rel)!=expected: raise ValueError("freeze hash mismatch: "+rel)
    required={str(x) for x in (DATA,DEV,Path(f"config/biography_pilot_v1/stratified_v1/batch_plan_{args.candidate}_20260.json"),Path("scripts/train_biography_sft.py"),Path("scripts/biography_batching.py"),Path("scripts/wide_unfamiliarity_training.py"),Path("scripts/build_biography_stratified_plan_draft.py"),Path("scripts/launch_biography_stratified_v1.py"))}
    if not required.issubset(freeze.get("files",{})): raise ValueError("freeze missing required hashes")
    model=f"/home/ubuntu/biography-archive/{BASE_REV}"
    for name,expected in freeze.get("base_files",{}).items():
        if digest(Path(model)/name)!=expected: raise ValueError("base pin mismatch: "+name)
    plan=RUNTIME/f"config/biography_pilot_v1/stratified_v1/batch_plan_{args.candidate}_20260.json"; by_id={r["id"]:r for r in rows}
    plan_value=json.loads(plan.read_text(encoding="utf-8"));
    if plan_value.get("version")!=1 or plan_value.get("seed")!=20260 or plan_value.get("steps")!=900 or plan_value.get("batch_size")!=8 or len(plan_value.get("batches",[]))!=900: raise ValueError("invalid stratified plan header")
    for batch in plan_value["batches"]:
        if len(batch)!=8 or any(rid not in by_id for rid in batch): raise ValueError("invalid plan IDs")
        cats=[by_id[rid].get("category") for rid in batch]; pools=["episode_fact" if c=="episode_fact" else "episode_narrative" if c in {"episode_narrative","episode_link","episode_conversation"} else c for c in cats]
        if sorted(pools)!=sorted(SLOTS[args.candidate]): raise ValueError("plan pool mix mismatch")
    output=ARCHIVE/f"T_run600_stratified_v1_{args.candidate}"; log=ARCHIVE/f"T_run600_stratified_v1_{args.candidate}.log"; receipt=ARCHIVE/f"T_run600_stratified_v1_{args.candidate}_launch.json"
    if output.exists() or log.exists() or receipt.exists(): raise FileExistsError("stratified output, log, or receipt exists")
    if shutil.disk_usage(ARCHIVE).free<20*1024**3: raise RuntimeError("less than 20 GiB free")
    if subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip(): raise RuntimeError("GPU is occupied")
    command=["/home/ubuntu/biography-runtime/venv/bin/python","scripts/train_biography_sft.py","--model-id",model,"--tokenizer-model",model,"--data",str(data),"--dev-data",str(dev),"--batch-plan",str(plan),"--output-dir",str(output),"--num-steps","600","--save-every","50","--eval-every","50","--seed","20260","--learning-rate","0.0001","--max-length","384","--microbatch-size","8"]
    env=dict(os.environ,HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",TOKENIZERS_PARALLELISM="false")
    with log.open("xb") as handle: child=subprocess.Popen(command,cwd=RUNTIME,env=env,stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
    result={"schema":"biography_stratified_v1_launch","candidate":args.candidate,"host_role":cand["host_role"],"parent":"clean-B","command":command,"cwd":str(RUNTIME),"pid":child.pid,"output":str(output),"freeze_sha256":digest(RUNTIME/FREEZE),"source_sha256":digest(Path(__file__)),"preflight_sha256":digest(PREFLIGHT),"plan_sha256":digest(plan),"status":"launched; inspect health separately"}
    with receipt.open("x") as handle: json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
