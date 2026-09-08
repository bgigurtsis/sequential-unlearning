"""Guarded V2 coverage fallback from completed clean-base T step 600."""
import argparse, hashlib, json, math, os, shutil, socket, subprocess
from pathlib import Path

BASE_REV="093f9f388b31de276ce2de164bdc2081324b9767"; RUNTIME=Path("/home/ubuntu/biography-runtime/staging_biography_coverage_v2"); ARCHIVE=Path("/home/ubuntu/biography-archive/teaching"); FREEZE=RUNTIME/"config/biography_pilot_v1/execution_v1/coverage_v2_freeze.json"; PREFLIGHT=Path("/home/ubuntu/biography-archive/qualification/candidate_coverage_v2_token_preflight.json")

def digest(path):
    p=Path(path); h=hashlib.sha256(); files=sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
    for f in files:
        if p.is_dir(): h.update(str(f.relative_to(p)).replace("\\","/").encode()); h.update(b"\0")
        with f.open("rb") as handle:
            for block in iter(lambda: handle.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--candidate",choices=("lr1e4","lr3e5"),required=True); p.add_argument("--review",required=True); args=p.parse_args(argv)
    review=json.loads(Path(args.review).read_text(encoding="utf-8")); freeze=json.loads(FREEZE.read_text(encoding="utf-8")); expected_steps=list(range(50,601,50))
    if review.get("all_saved_snapshots_reviewed") is not True or review.get("eligible_candidate_count")!=0 or set(review.get("candidates",[]))!={"lr1e4","lr3e5"} or review.get("reviewed_steps")!=expected_steps or review.get("freeze_sha256")!=digest(FREEZE) or not review.get("reviewer"): raise ValueError("review receipt does not authorize fallback")
    files=review.get("files",{}); archive=ARCHIVE; expected_lr={"lr1e4":1e-4,"lr3e5":3e-5}[args.candidate]
    expected_review_files={f"T_run600_coverage_v2_{c}/dev_step{s:03d}.json" for c in ("lr1e4","lr3e5") for s in expected_steps}
    if set(files)!=expected_review_files: raise ValueError("review files must contain exactly both candidate lanes and 12 steps")
    prior=archive/f"T_run600_coverage_v2_{args.candidate}"; output=archive/f"T_resume900_coverage_v2_{args.candidate}"; checkpoint=prior/"step600"; log=archive/f"T_resume900_coverage_v2_{args.candidate}.log"; receipt=archive/f"T_resume900_coverage_v2_{args.candidate}_launch.json"
    if output.exists() or log.exists() or receipt.exists(): raise FileExistsError("V2 fallback output, log, or receipt exists")
    config=json.loads((prior/"run_config.json").read_text()); progress=json.loads((prior/"progress.json").read_text())
    model_path=f"/home/ubuntu/biography-archive/{BASE_REV}"
    if config.get("resume_checkpoint") is not None or config.get("model_id")!=model_path or config.get("tokenizer_model")!=model_path or config.get("max_length")!=384 or config.get("save_every")!=50 or config.get("eval_every")!=50: raise ValueError("parent is not a clean-base run with the frozen settings")
    if progress.get("step")!=600 or config.get("num_steps")!=600 or config.get("output_dir")!=str(prior) or config.get("seed")!=20260 or config.get("microbatch_size",1)!=8 or config.get("learning_rate")!=expected_lr or config.get("omit_episode") is not None: raise ValueError("parent run config is not the expected clean-base 600-step run")
    if any(not (checkpoint/name).is_file() for name in ("adapter_model.safetensors","adapter_config.json","optimizer.pt","rng_state.pt")): raise ValueError("step600 checkpoint state is incomplete")
    # Both lanes are certified by the committed review receipt; only this
    # host's lane is present locally and is re-hashed against that receipt.
    for step in expected_steps:
        path=prior/f"dev_step{step:03d}.json"; key=f"{prior.name}/dev_step{step:03d}.json"
        expected=files.get(key,files.get(str(path)))
        if not expected or digest(path)!=expected: raise ValueError("reviewed development hash mismatch: "+key)
    metrics=[json.loads(line) for line in (prior/"training_metrics.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(metrics)!=600 or [x.get("step") for x in metrics] != list(range(1,601)) or any("loss" not in x or not math.isfinite(float(x["loss"])) for x in metrics): raise ValueError("parent metrics must contain finite losses for steps 1..600")
    data=RUNTIME/Path(config["data"]); dev=RUNTIME/Path(config["dev_data"]); plan=RUNTIME/Path(config["batch_plan"])
    if digest(data)!=config.get("data_sha256") or digest(dev)!=config.get("dev_data_sha256") or config.get("batch_plan_sha256")!=hashlib.sha256(json.dumps(json.loads(plan.read_text()),sort_keys=True).encode()).hexdigest(): raise ValueError("parent data/dev/plan hash mismatch")
    for name,expected in config.get("source_hashes",{}).items():
        if digest(RUNTIME/"scripts"/name)!=expected: raise ValueError("source hash mismatch: "+name)
    if digest(RUNTIME/"scripts/biography_batching.py")!=config.get("batching_source_sha256"): raise ValueError("batching source hash mismatch")
    pref=json.loads(PREFLIGHT.read_text(encoding="utf-8"));
    if pref.get("model_loaded") is not False or pref.get("model_outputs",-1)!=0 or pref.get("training_records")!=freeze.get("training_records") or pref.get("max_training_tokens",999)>384 or pref.get("data_sha256")!=digest(data) or pref.get("verified_model_files")!=freeze.get("base_files"): raise ValueError("coverage preflight mismatch")
    settings={"previous_coverage_closed":True,"decision_frozen":True,"base":BASE_REV,"seed":20260,"microbatch_size":8,"batch_size":8,"rank":32,"alpha":64,"max_length":384,"save_every":50,"eval_every":50,"ceiling_steps":600,"fallback_ceiling":900}
    if any(freeze.get(k)!=v for k,v in settings.items()): raise ValueError("coverage freeze mismatch")
    for rel,expected in freeze.get("files",{}).items():
        if digest(RUNTIME/rel)!=expected: raise ValueError("freeze source hash mismatch: "+rel)
    if not freeze.get("base_files"): raise ValueError("freeze base pins missing")
    for name,expected in freeze["base_files"].items():
        if digest(Path(model_path)/name)!=expected: raise ValueError("base pin mismatch: "+name)
    required=("scripts/train_biography_sft.py","scripts/wide_unfamiliarity_training.py")
    if any(config.get("source_hashes",{}).get(Path(x).name) is None for x in required): raise ValueError("parent source hashes missing")
    if review.get("fallback_launcher_sha256")!=digest(Path(__file__)): raise ValueError("fallback launcher hash mismatch")
    if socket.gethostname() != {"primary":"ip-172-31-87-196","secondary":"ip-172-31-42-127"}.get(freeze.get("candidates",{}).get(args.candidate,{}).get("host_role")): raise ValueError("host role mismatch")
    if shutil.disk_usage(ARCHIVE).free<20*1024**3: raise RuntimeError("less than 20 GiB free")
    if subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip(): raise RuntimeError("GPU is occupied")
    command=["/home/ubuntu/biography-runtime/venv/bin/python","scripts/train_biography_sft.py"]
    for key in ("model_id","tokenizer_model","data","dev_data","batch_plan","seed","learning_rate","max_length","save_every","eval_every"): command.extend(["--"+key.replace("_","-"),str(config[key])])
    command.extend(["--microbatch-size","8","--num-steps","900","--resume-checkpoint",str(checkpoint),"--output-dir",str(output)])
    env=dict(os.environ,HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",TOKENIZERS_PARALLELISM="false")
    with log.open("xb") as handle: child=subprocess.Popen(command,cwd=RUNTIME,env=env,stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
    result={"schema":"biography_coverage_v2_fallback_launch_v1","candidate":args.candidate,"parent":str(prior),"output":str(output),"pid":child.pid,"command":command,"review_sha256":digest(args.review),"freeze_sha256":digest(FREEZE),"source_hashes":config.get("source_hashes",{}),"preflight_sha256":digest(PREFLIGHT),"checkpoint_hashes":{n:digest(checkpoint/n) for n in ("adapter_model.safetensors","adapter_config.json","optimizer.pt","rng_state.pt")},"status":"launched; inspect health separately"}
    with receipt.open("x") as handle: json.dump(result,handle,indent=2)
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
