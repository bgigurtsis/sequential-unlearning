"""Prepare unused abstract-chat biography teaching candidates."""
import argparse, hashlib, json, os, shutil, socket, subprocess
from pathlib import Path

BASE_REV="093f9f388b31de276ce2de164bdc2081324b9767"; RUNTIME=Path("/home/ubuntu/biography-runtime/staging_biography_abstract_v1"); ARCHIVE=Path("/home/ubuntu/biography-archive/teaching"); ROOT=Path("config/biography_pilot_v1/abstract_v1"); FREEZE=RUNTIME/"config/biography_pilot_v1/execution_v1/abstract_v1_freeze.json"

def digest(path):
    p=Path(path); h=hashlib.sha256(); files=sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
    for f in files:
        if p.is_dir(): h.update(str(f.relative_to(p)).replace("\\","/").encode()); h.update(b"\0")
        with f.open("rb") as handle:
            for block in iter(lambda: handle.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--candidate",choices=("original_chat","plain_chat"),required=True); args=p.parse_args(argv)
    freeze=json.loads(FREEZE.read_text(encoding="utf-8")); cand=freeze.get("candidates",{}).get(args.candidate,{})
    if freeze.get("schema")!="biography_abstract_v1_preoutput_freeze" or freeze.get("previous_stratified_closed") is not True or freeze.get("decision_frozen") is not True or not cand or cand.get("learning_rate")!=1e-4: raise ValueError("abstract freeze/candidate gate failed")
    settings={"base":BASE_REV,"seed":20260,"microbatch_size":8,"batch_size":8,"rank":32,"alpha":64,"max_length":384,"save_every":50,"eval_every":50,"ceiling_steps":600,"fallback_ceiling":900}
    if any(freeze.get(k)!=v for k,v in settings.items()): raise ValueError("abstract freeze settings mismatch")
    if any(freeze.get(k)!=v for k,v in {"training_records":1734,"vacation_records":261,"dev_records":35}.items()): raise ValueError("abstract freeze counts mismatch")
    data=RUNTIME/Path(cand["data"]); dev=RUNTIME/Path(cand["dev_data"]); plan=RUNTIME/Path(cand["batch_plan"]); pref_path=Path(f"/home/ubuntu/biography-archive/qualification/candidate_abstract_v1_{args.candidate}_token_preflight.json"); pref=json.loads(pref_path.read_text(encoding="utf-8")); rows=json.loads(data.read_text(encoding="utf-8")); rows=rows.get("records",rows) if isinstance(rows,dict) else rows
    if len(rows)!=1734 or len({r.get("id") for r in rows})!=1734 or sum(r.get("episode")=="vacation_episode" for r in rows)!=261 or len(json.loads(dev.read_text(encoding="utf-8")))!=35: raise ValueError("abstract data/dev counts invalid")
    if len(rows)-261!=1473: raise ValueError("abstract twin count mismatch")
    if pref.get("data_sha256")!=digest(data) or pref.get("training_records")!=1734 or pref.get("max_training_tokens",999)>384 or pref.get("model_outputs",-1)!=0 or pref.get("model_loaded") is not False: raise ValueError("abstract preflight mismatch")
    for rel,expected in freeze.get("files",{}).items():
        if digest(RUNTIME/rel)!=expected: raise ValueError("freeze file hash mismatch: "+rel)
    closure=RUNTIME/"logs/biography-20260908/stratified_v1_closed.json"
    if not closure.is_file(): raise ValueError("stratified closure receipt missing")
    closed=json.loads(closure.read_text(encoding="utf-8"))
    if closed.get("status")!="CLOSED_FAILED" or closed.get("qualified_candidates")!=0: raise ValueError("stratified closure receipt is not failed/zero-qualified")
    if not freeze.get("base_files") or pref.get("verified_model_files")!=freeze["base_files"]: raise ValueError("abstract base pins mismatch")
    required={Path(x).as_posix() for x in (Path(cand["data"]),Path(cand["dev_data"]),Path(cand["batch_plan"]),Path("scripts/train_biography_sft.py"),Path("scripts/biography_batching.py"),Path("scripts/wide_unfamiliarity_training.py"),Path("scripts/build_biography_stratified_plan_draft.py"),Path("scripts/launch_biography_abstract_v1.py"),Path("logs/biography-20260908/stratified_v1_closed.json"))}
    if not required.issubset(freeze.get("files",{})): raise ValueError("abstract freeze missing required hashes")
    model=f"/home/ubuntu/biography-archive/{BASE_REV}"
    for name,expected in freeze["base_files"].items():
        if digest(Path(model)/name)!=expected: raise ValueError("abstract base pin mismatch: "+name)
    value=json.loads(plan.read_text(encoding="utf-8")); by_id={r["id"]:r for r in rows}; expected_mix=("episode_fact","episode_fact","episode_narrative","episode_narrative","chat","chat","gap","identity")
    if value.get("version")!=1 or value.get("seed")!=20260 or value.get("steps")!=900 or value.get("batch_size")!=8 or len(value.get("batches",[]))!=900: raise ValueError("abstract plan header mismatch")
    seen=set()
    for batch in value["batches"]:
        if len(batch)!=8 or any(x not in by_id for x in batch): raise ValueError("abstract plan ID mismatch")
        seen.update(batch)
        pools=["episode_fact" if by_id[x].get("category")=="episode_fact" else "episode_narrative" if by_id[x].get("category") in {"episode_narrative","episode_link","episode_conversation"} else by_id[x].get("category") for x in batch]
        if sorted(pools)!=sorted(expected_mix): raise ValueError("abstract plan mix mismatch")
    if seen != set(by_id): raise ValueError("abstract plan does not expose every training ID")
    expected_roles={"original_chat":"primary","plain_chat":"secondary"}
    if cand.get("host_role")!=expected_roles[args.candidate]: raise ValueError("abstract candidate host role mismatch")
    host={"primary":"ip-172-31-87-196","secondary":"ip-172-31-42-127"}[expected_roles[args.candidate]]
    if socket.gethostname()!=host: raise ValueError("abstract host role mismatch")
    output=ARCHIVE/f"T_run600_abstract_v1_{args.candidate}"; log=ARCHIVE/f"T_run600_abstract_v1_{args.candidate}.log"; receipt=ARCHIVE/f"T_run600_abstract_v1_{args.candidate}_launch.json"
    if output.exists() or log.exists() or receipt.exists(): raise FileExistsError("abstract output, log, or receipt exists")
    if shutil.disk_usage(ARCHIVE).free<20*1024**3: raise RuntimeError("less than 20 GiB free")
    if subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip(): raise RuntimeError("GPU is occupied")
    command=["/home/ubuntu/biography-runtime/venv/bin/python","scripts/train_biography_sft.py","--model-id",model,"--tokenizer-model",model,"--data",str(data),"--dev-data",str(dev),"--batch-plan",str(plan),"--output-dir",str(output),"--num-steps","600","--save-every","50","--eval-every","50","--seed","20260","--learning-rate","0.0001","--max-length","384","--microbatch-size","8"]
    env=dict(os.environ,HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",TOKENIZERS_PARALLELISM="false")
    with log.open("xb") as handle: child=subprocess.Popen(command,cwd=RUNTIME,env=env,stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
    result={"schema":"biography_abstract_v1_launch","candidate":args.candidate,"command":command,"cwd":str(RUNTIME),"pid":child.pid,"output":str(output),"freeze_sha256":digest(FREEZE),"preflight_sha256":digest(pref_path),"source_sha256":digest(Path(__file__)),"status":"draft launch prepared"}
    with receipt.open("x") as handle: json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
