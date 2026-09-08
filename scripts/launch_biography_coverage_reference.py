"""Launch matched clean-base Ra reference training after coverage selection."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path

BASE_REV="093f9f388b31de276ce2de164bdc2081324b9767"; RUNTIME=Path("/home/ubuntu/biography-runtime/staging_biography_coverage_v1"); ARCHIVE=Path("/home/ubuntu/biography-archive/teaching"); DATA=Path("config/biography_pilot_v1/teaching_coverage_v1/teaching.json"); DEV=Path("config/biography_pilot_v1/authored_v2/dev.json"); PLAN=Path("config/biography_pilot_v1/teaching_coverage_v1/batch_plan_20260.json"); FREEZE=Path("config/biography_pilot_v1/execution_v1/coverage_v1_freeze.json"); PREFLIGHT=Path("/home/ubuntu/biography-archive/qualification/candidate_coverage_v1_token_preflight.json")

def digest(path):
    h=hashlib.sha256(); p=Path(path)
    files=sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
    for f in files:
        if p.is_dir(): h.update(str(f.relative_to(p)).replace("\\","/").encode()); h.update(b"\0")
        with f.open("rb") as handle:
            for block in iter(lambda: handle.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--selection",required=True); args=p.parse_args(argv)
    selection=json.loads(Path(args.selection).read_text(encoding="utf-8")); candidate=selection.get("candidate"); step=selection.get("step");
    if candidate not in {"lr1e4","lr3e5"} or not isinstance(step,int) or not 50<=step<=900 or step%50: raise ValueError("invalid selection candidate or step")
    if selection.get("primary_verified_all_gates_pass") is not True: raise ValueError("selection primary verification gate is not true")
    verification=Path(selection.get("primary_verification_path","")); vsha=selection.get("primary_verification_sha256")
    if not verification.is_file() or not vsha or digest(verification)!=vsha: raise ValueError("primary verification hash mismatch")
    v=json.loads(verification.read_text(encoding="utf-8"));
    if v.get("schema")!="biography_coverage_verification_v1" or v.get("all_gates_pass") is not True: raise ValueError("verification has wrong schema or gates")
    if any(v.get(k)!=selection.get(k) for k in ("candidate","step","adapter_sha256","data_sha256")): raise ValueError("verification does not match selection")
    if v.get("seed")!=20260 or v.get("host_role")!="primary": raise ValueError("verification seed/host role mismatch")
    counts=v.get("pass_counts",v.get("counts",{}))
    if counts.get("target")!=4 or counts.get("retained")!=8 or counts.get("gap",0)<9 or counts.get("identity")!=4: raise ValueError("verification pass counts do not meet reference gate")
    if v.get("confabulation") is not False or v.get("disclaimer") is not False: raise ValueError("verification lacks explicit no-confabulation/disclaimer findings")
    checkpoint=Path(selection.get("T_checkpoint","")); adapter_sha=selection.get("adapter_sha256")
    adapter=checkpoint/"adapter_model.safetensors"
    if not adapter.is_file() or not adapter_sha or digest(adapter)!=adapter_sha: raise ValueError("selected T adapter hash mismatch")
    if selection.get("data_sha256") is None: raise ValueError("selection missing data_sha256")
    freeze=json.loads((RUNTIME/FREEZE).read_text(encoding="utf-8")); pref=json.loads(PREFLIGHT.read_text(encoding="utf-8")); data=RUNTIME/DATA; dev=RUNTIME/DEV; plan=RUNTIME/PLAN
    if selection["data_sha256"]!=digest(data) or pref.get("data_sha256")!=digest(data) or pref.get("training_records")!=1025 or pref.get("max_training_tokens",999)>384 or pref.get("model_outputs",-1)!=0: raise ValueError("coverage data/preflight mismatch")
    rows=json.loads(data.read_text(encoding="utf-8")); rows=rows.get("records",rows) if isinstance(rows,dict) else rows
    if len(rows)!=1025 or sum(r.get("episode")=="vacation_episode" for r in rows)!=165: raise ValueError("coverage data counts mismatch")
    if freeze.get("base")!=BASE_REV or freeze.get("seed")!=20260 or freeze.get("microbatch_size")!=8 or freeze.get("batch_size")!=8 or freeze.get("rank")!=32 or freeze.get("alpha")!=64 or freeze.get("max_length")!=384 or freeze.get("save_every")!=50 or freeze.get("eval_every")!=50 or freeze.get("lr_search_closed") is not True or freeze.get("decision_frozen") is not True: raise ValueError("coverage freeze mismatch")
    if not freeze.get("base_files") or freeze.get("base_files") != pref.get("verified_model_files") or pref.get("model_loaded") is not False: raise ValueError("coverage base preflight mismatch")
    for rel,expected in freeze.get("files",{}).items():
        if digest(RUNTIME/rel)!=expected: raise ValueError("coverage freeze hash mismatch: "+rel)
    required={str(x) for x in (DATA,DEV,PLAN,Path("scripts/train_biography_sft.py"),Path("scripts/biography_batching.py"),Path("scripts/wide_unfamiliarity_training.py"),Path("scripts/launch_biography_coverage.py"))}
    if not required.issubset(freeze.get("files",{})): raise ValueError("coverage freeze missing required hashes")
    if selection.get("reference_launcher_sha256") != digest(Path(__file__)): raise ValueError("reference launcher selection pin mismatch")
    model=f"/home/ubuntu/biography-archive/{BASE_REV}"
    for name,expected in freeze.get("base_files",{}).items():
        if digest(Path(model)/name)!=expected: raise ValueError("coverage base pin mismatch: "+name)
    lr=freeze.get("candidates",{}).get(candidate,{}).get("learning_rate"); expected={"lr1e4":1e-4,"lr3e5":3e-5}[candidate]
    if lr!=expected or selection.get("seed")!=20260 or selection.get("data_sha256")!=digest(data): raise ValueError("selection settings mismatch")
    prior_cfg=checkpoint.parent/"run_config.json"
    if not prior_cfg.is_file(): raise ValueError("selected checkpoint parent lacks run_config.json")
    pc=json.loads(prior_cfg.read_text(encoding="utf-8"))
    if pc.get("learning_rate")!=lr or pc.get("seed")!=20260 or pc.get("omit_episode") is not None or pc.get("microbatch_size",1)!=8 or pc.get("data_sha256")!=digest(data): raise ValueError("selected checkpoint parent config mismatch")
    if checkpoint.name != f"step{step:03d}": raise ValueError("selected checkpoint does not match selected step")
    output=ARCHIVE/f"Ra_selected_coverage_v1_{step}_{candidate}"; log=ARCHIVE/f"Ra_selected_coverage_v1_{step}_{candidate}.log"; receipt=ARCHIVE/f"Ra_selected_coverage_v1_{step}_{candidate}_launch.json"
    if output.exists() or log.exists() or receipt.exists(): raise FileExistsError("reference output, log, or receipt already exists")
    if subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip(): raise RuntimeError("GPU is occupied")
    command=["/home/ubuntu/biography-runtime/venv/bin/python","scripts/train_biography_sft.py","--model-id",model,"--tokenizer-model",model,"--data",str(data),"--dev-data",str(dev),"--batch-plan",str(plan),"--output-dir",str(output),"--num-steps",str(step),"--save-every","50","--eval-every","50","--seed","20260","--learning-rate",str(lr),"--max-length","384","--microbatch-size","8","--omit-episode","vacation_episode"]
    env=dict(os.environ,HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",TOKENIZERS_PARALLELISM="false")
    with log.open("xb") as handle: child=subprocess.Popen(command,cwd=RUNTIME,env=env,stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
    result={"schema":"biography_coverage_reference_launch_v1","candidate":candidate,"step":step,"learning_rate":lr,"parent":"clean-B","command":command,"cwd":str(RUNTIME),"pid":child.pid,"output":str(output),"selection_sha256":digest(args.selection),"verification_sha256":vsha,"adapter_sha256":adapter_sha,"freeze_sha256":digest(RUNTIME/FREEZE),"cpu_preflight_sha256":digest(PREFLIGHT),"status":"launched; inspect training health separately"}
    with receipt.open("x") as handle: json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
