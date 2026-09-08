"""Prepare the unused clean-base Ra reference for a stratified selection."""
import argparse, hashlib, json, os, shutil, socket, subprocess
from pathlib import Path

BASE_REV="093f9f388b31de276ce2de164bdc2081324b9767"; RUNTIME=Path("/home/ubuntu/biography-runtime/staging_biography_stratified_v1"); ARCHIVE=Path("/home/ubuntu/biography-archive/teaching"); DATA=RUNTIME/"config/biography_pilot_v1/teaching_coverage_v2/teaching.json"; DEV=RUNTIME/"config/biography_pilot_v1/teaching_coverage_v2/dev.json"; FREEZE=RUNTIME/"config/biography_pilot_v1/execution_v1/stratified_v1_freeze.json"; PREFLIGHT=Path("/home/ubuntu/biography-archive/qualification/candidate_coverage_v2_token_preflight.json")

def digest(path):
    p=Path(path); h=hashlib.sha256(); files=sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
    for f in files:
        if p.is_dir(): h.update(str(f.relative_to(p)).replace("\\","/").encode()); h.update(b"\0")
        with f.open("rb") as handle:
            for block in iter(lambda: handle.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--selection",required=True); args=p.parse_args(argv)
    sel=json.loads(Path(args.selection).read_text(encoding="utf-8")); candidate=sel.get("candidate"); step=sel.get("step")
    if candidate not in {"narrative","gap"} or not isinstance(step,int) or not 50<=step<=900 or step%50 or sel.get("seed")!=20260: raise ValueError("invalid stratified selection")
    freeze=json.loads(FREEZE.read_text(encoding="utf-8"));
    if sel.get("freeze_sha256")!=digest(FREEZE) or sel.get("reference_launcher_sha256")!=digest(Path(__file__)): raise ValueError("selection freeze/launcher hash mismatch")
    verification=Path(sel.get("primary_verification","")); vsha=sel.get("primary_verification_sha256")
    if not verification.is_file() or not vsha or digest(verification)!=vsha: raise ValueError("primary verification hash mismatch")
    v=json.loads(verification.read_text(encoding="utf-8"))
    if v.get("schema")!="biography_stratified_verification_v1" or v.get("all_35_gates_pass") is not True or v.get("raw_generation_ids_match") is not True or v.get("prompts35")!=35 or any(v.get(k)!=sel.get(k) for k in ("candidate","step","freeze_sha256")) or v.get("adapter_sha256")!=sel.get("selected_adapter_sha256") or v.get("host_role")!="primary" or not v.get("reviewer"): raise ValueError("primary verification does not authorize reference")
    adapter=Path(sel.get("selected_adapter","")); asha=sel.get("selected_adapter_sha256")
    if not (adapter/"adapter_config.json").is_file() or not (adapter/"adapter_model.safetensors").is_file() or not asha or digest(adapter/"adapter_model.safetensors")!=asha: raise ValueError("selected adapter hash mismatch")
    run_cfg=Path(sel.get("selected_run_config",""));
    if not run_cfg.is_file() or digest(run_cfg)!=sel.get("selected_run_config_sha256"): raise ValueError("selected run config missing or hash mismatch")
    cfg=json.loads(run_cfg.read_text(encoding="utf-8")); model=f"/home/ubuntu/biography-archive/{BASE_REV}"; plan=RUNTIME/f"config/biography_pilot_v1/stratified_v1/batch_plan_{candidate}_20260.json"
    if cfg.get("model_id")!=model or cfg.get("tokenizer_model")!=model or cfg.get("seed")!=20260 or cfg.get("learning_rate")!=1e-4 or cfg.get("microbatch_size",1)!=8 or cfg.get("max_length")!=384 or cfg.get("save_every")!=50 or cfg.get("eval_every")!=50 or cfg.get("omit_episode") is not None or cfg.get("data_sha256")!=digest(DATA) or cfg.get("dev_data_sha256")!=digest(DEV) or Path(cfg.get("batch_plan","")).name!=plan.name: raise ValueError("selected run config does not match stratified settings")
    if cfg.get("batch_plan_sha256")!=hashlib.sha256(json.dumps(json.loads(plan.read_text(encoding="utf-8")),sort_keys=True).encode()).hexdigest() or adapter.name!=f"step{step:03}" or cfg.get("num_steps",0)<step: raise ValueError("selected checkpoint/plan mismatch")
    for name in ("train_biography_sft.py","wide_unfamiliarity_training.py"):
        if cfg.get("source_hashes",{}).get(name)!=digest(RUNTIME/"scripts"/name): raise ValueError("selected trainer source mismatch: "+name)
    if cfg.get("batching_source_sha256")!=digest(RUNTIME/"scripts/biography_batching.py") or cfg.get("master_weight_dtype")!="float32" or cfg.get("attention_implementation")!="eager": raise ValueError("selected runtime source/settings mismatch")
    pref=json.loads(PREFLIGHT.read_text(encoding="utf-8")); rows=json.loads(DATA.read_text(encoding="utf-8")); rows=rows.get("records",rows) if isinstance(rows,dict) else rows
    if len(rows)!=1662 or len({r.get("id") for r in rows})!=1662 or len(json.loads(DEV.read_text(encoding="utf-8")))!=35 or sum(r.get("episode")=="vacation_episode" for r in rows)!=237 or pref.get("data_sha256")!=digest(DATA) or pref.get("training_records")!=1662 or pref.get("max_training_tokens",999)>384 or pref.get("model_outputs",-1)!=0 or pref.get("model_loaded") is not False or pref.get("verified_model_files")!=freeze.get("base_files"): raise ValueError("stratified preflight mismatch")
    settings={"previous_coverage_v2_closed":True,"decision_frozen":True,"base":BASE_REV,"seed":20260,"microbatch_size":8,"batch_size":8,"rank":32,"alpha":64,"max_length":384,"save_every":50,"eval_every":50,"ceiling_steps":600,"fallback_ceiling":900}
    if any(freeze.get(k)!=v for k,v in settings.items()): raise ValueError("stratified freeze settings mismatch")
    for rel,expected in freeze.get("files",{}).items():
        if digest(RUNTIME/rel)!=expected: raise ValueError("freeze file hash mismatch: "+rel)
    if not freeze.get("base_files"): raise ValueError("base pins missing")
    for name,expected in freeze["base_files"].items():
        if digest(Path(model)/name)!=expected: raise ValueError("base pin mismatch: "+name)
    if socket.gethostname()!="ip-172-31-42-127": raise ValueError("reference must run on secondary host")
    output=ARCHIVE/f"Ra_selected_stratified_v1_{candidate}_{step}"; log=ARCHIVE/f"Ra_selected_stratified_v1_{candidate}_{step}.log"; receipt=ARCHIVE/f"Ra_selected_stratified_v1_{candidate}_{step}_launch.json"
    if output.exists() or log.exists() or receipt.exists(): raise FileExistsError("reference output, log, or receipt exists")
    if shutil.disk_usage(ARCHIVE).free<20*1024**3: raise RuntimeError("less than 20 GiB free")
    if subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip(): raise RuntimeError("GPU is occupied")
    command=["/home/ubuntu/biography-runtime/venv/bin/python","scripts/train_biography_sft.py","--model-id",model,"--tokenizer-model",model,"--data",str(DATA),"--dev-data",str(DEV),"--batch-plan",str(plan),"--output-dir",str(output),"--num-steps",str(step),"--save-every","50","--eval-every","50","--seed","20260","--learning-rate","0.0001","--max-length","384","--microbatch-size","8","--omit-episode","vacation_episode"]
    env=dict(os.environ,HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",TOKENIZERS_PARALLELISM="false")
    with log.open("xb") as handle: child=subprocess.Popen(command,cwd=RUNTIME,env=env,stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
    result={"schema":"biography_stratified_reference_launch_v1","candidate":candidate,"step":step,"parent":"clean-B","command":command,"cwd":str(RUNTIME),"pid":child.pid,"output":str(output),"selection_sha256":digest(args.selection),"verification_sha256":vsha,"adapter_sha256":asha,"freeze_sha256":digest(FREEZE),"preflight_sha256":digest(PREFLIGHT),"status":"launch prepared"}
    with receipt.open("x") as handle: json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
