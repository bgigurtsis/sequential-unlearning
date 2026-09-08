"""Guarded stratified 600-to-900-step fallback launcher (unused draft)."""
import argparse, hashlib, json, math, os, shutil, socket, subprocess
from pathlib import Path

BASE_REV="093f9f388b31de276ce2de164bdc2081324b9767"; RUNTIME=Path("/home/ubuntu/biography-runtime/staging_biography_stratified_v1"); ARCHIVE=Path("/home/ubuntu/biography-archive/teaching"); FREEZE=RUNTIME/"config/biography_pilot_v1/execution_v1/stratified_v1_freeze.json"; PREFLIGHT=Path("/home/ubuntu/biography-archive/qualification/candidate_coverage_v2_token_preflight.json")

def digest(path):
    p=Path(path); h=hashlib.sha256(); files=sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
    for f in files:
        if p.is_dir(): h.update(str(f.relative_to(p)).replace("\\","/").encode()); h.update(b"\0")
        with f.open("rb") as handle:
            for block in iter(lambda: handle.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--candidate",choices=("narrative","gap"),required=True); p.add_argument("--review",required=True); args=p.parse_args(argv)
    review=json.loads(Path(args.review).read_text(encoding="utf-8")); freeze=json.loads(FREEZE.read_text(encoding="utf-8")); steps=list(range(50,601,50))
    if review.get("all_saved_snapshots_reviewed") is not True or review.get("eligible_candidate_count")!=0 or set(review.get("candidates",[]))!={"narrative","gap"} or review.get("reviewed_steps")!=steps or review.get("freeze_sha256")!=digest(FREEZE) or not review.get("reviewer") or review.get("fallback_launcher_sha256")!=digest(Path(__file__)): raise ValueError("review receipt does not authorize fallback")
    candidate=args.candidate; expected_lr=1e-4; prior=ARCHIVE/f"T_run600_stratified_v1_{candidate}"; output=ARCHIVE/f"T_resume900_stratified_v1_{candidate}"; checkpoint=prior/"step600"; log=ARCHIVE/f"T_resume900_stratified_v1_{candidate}.log"; receipt=ARCHIVE/f"T_resume900_stratified_v1_{candidate}_launch.json"
    if output.exists() or log.exists() or receipt.exists(): raise FileExistsError("stratified fallback output, log, or receipt exists")
    config=json.loads((prior/"run_config.json").read_text(encoding="utf-8")); progress=json.loads((prior/"progress.json").read_text(encoding="utf-8")); model=f"/home/ubuntu/biography-archive/{BASE_REV}"
    if progress.get("step")!=600 or config.get("num_steps")!=600 or config.get("output_dir")!=str(prior) or config.get("model_id")!=model or config.get("tokenizer_model")!=model or config.get("seed")!=20260 or config.get("learning_rate")!=expected_lr or config.get("microbatch_size",1)!=8 or config.get("max_length")!=384 or config.get("save_every")!=50 or config.get("eval_every")!=50 or config.get("omit_episode") is not None or config.get("resume_checkpoint") is not None: raise ValueError("parent config is not the clean stratified run")
    files=review.get("files",{}); expected_files={f"T_run600_stratified_v1_{c}/dev_step{s:03d}.json" for c in ("narrative","gap") for s in steps}
    if set(files)!=expected_files: raise ValueError("review must contain exactly 24 candidate/step development hashes")
    expected_prefix=f"{prior.name}/dev_step"; own={k:v for k,v in files.items() if k.startswith(expected_prefix)}
    if set(own)!={f"{prior.name}/dev_step{s:03d}.json" for s in steps}: raise ValueError("review lacks exactly 12 own-lane development hashes")
    for s in steps:
        path=prior/f"dev_step{s:03d}.json"; key=f"{prior.name}/dev_step{s:03d}.json"
        if not path.is_file() or digest(path)!=own[key]: raise ValueError("development hash mismatch: "+key)
    if any(not (checkpoint/n).is_file() for n in ("adapter_model.safetensors","adapter_config.json","optimizer.pt","rng_state.pt")): raise ValueError("step600 checkpoint incomplete")
    metrics=[json.loads(x) for x in (prior/"training_metrics.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    if len(metrics)!=600 or [x.get("step") for x in metrics]!=list(range(1,601)) or any("loss" not in x or not math.isfinite(float(x["loss"])) for x in metrics): raise ValueError("metrics are not exactly finite steps 1..600")
    data=RUNTIME/Path(config["data"]); dev=RUNTIME/Path(config["dev_data"]); plan=RUNTIME/Path(config["batch_plan"]); pref=json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if digest(data)!=config.get("data_sha256") or digest(dev)!=config.get("dev_data_sha256") or pref.get("data_sha256")!=digest(data) or pref.get("training_records")!=freeze.get("training_records") or pref.get("max_training_tokens",999)>384 or pref.get("model_outputs",-1)!=0 or pref.get("model_loaded") is not False or pref.get("verified_model_files")!=freeze.get("base_files"): raise ValueError("data/preflight mismatch")
    if config.get("batch_plan_sha256")!=hashlib.sha256(json.dumps(json.loads(plan.read_text()),sort_keys=True).encode()).hexdigest(): raise ValueError("batch plan hash mismatch")
    source_hashes=config.get("source_hashes",{})
    if set(source_hashes)!={"train_biography_sft.py","wide_unfamiliarity_training.py"}: raise ValueError("parent source hashes must exactly cover trainer and wide helper")
    for name,expected in source_hashes.items():
        if digest(RUNTIME/"scripts"/name)!=expected: raise ValueError("source mismatch: "+name)
    if digest(RUNTIME/"scripts/biography_batching.py")!=config.get("batching_source_sha256"): raise ValueError("batching source mismatch")
    if config.get("master_weight_dtype", "float32")!="float32" or config.get("attention_implementation", "eager")!="eager": raise ValueError("parent precision/attention metadata mismatch")
    settings={"previous_coverage_v2_closed":True,"decision_frozen":True,"base":BASE_REV,"seed":20260,"microbatch_size":8,"batch_size":8,"rank":32,"alpha":64,"max_length":384,"save_every":50,"eval_every":50,"ceiling_steps":600,"fallback_ceiling":900}
    if any(freeze.get(k)!=v for k,v in settings.items()): raise ValueError("freeze settings mismatch")
    for rel,expected in freeze.get("files",{}).items():
        if digest(RUNTIME/rel)!=expected: raise ValueError("freeze hash mismatch: "+rel)
    for name,expected in freeze.get("base_files",{}).items():
        if digest(Path(model)/name)!=expected: raise ValueError("base pin mismatch: "+name)
    host={"primary":"ip-172-31-87-196","secondary":"ip-172-31-42-127"}.get(freeze.get("candidates",{}).get(candidate,{}).get("host_role"))
    if socket.gethostname()!=host: raise ValueError("host role mismatch")
    if shutil.disk_usage(ARCHIVE).free<20*1024**3: raise RuntimeError("less than 20 GiB free")
    if subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip(): raise RuntimeError("GPU is occupied")
    command=["/home/ubuntu/biography-runtime/venv/bin/python","scripts/train_biography_sft.py"]
    for key in ("model_id","tokenizer_model","data","dev_data","batch_plan","seed","learning_rate","max_length","save_every","eval_every"): command.extend(["--"+key.replace("_","-"),str(config[key])])
    command.extend(["--microbatch-size","8","--num-steps","900","--resume-checkpoint",str(checkpoint),"--output-dir",str(output)])
    env=dict(os.environ,HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",TOKENIZERS_PARALLELISM="false")
    with log.open("xb") as handle: child=subprocess.Popen(command,cwd=RUNTIME,env=env,stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
    result={"schema":"biography_stratified_fallback_launch_v1","candidate":candidate,"parent":str(prior),"output":str(output),"pid":child.pid,"command":command,"review_sha256":digest(args.review),"freeze_sha256":digest(FREEZE),"source_hashes":config.get("source_hashes",{}),"preflight_sha256":digest(PREFLIGHT),"checkpoint_hashes":{n:digest(checkpoint/n) for n in ("adapter_model.safetensors","adapter_config.json","optimizer.pt","rng_state.pt")},"status":"launch prepared"}
    with receipt.open("x") as handle: json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
