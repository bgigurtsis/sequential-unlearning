"""Safely launch a coverage-corpus interrupted coverage run from saved350 through original600 ceiling."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path

def digest(path):
    h=hashlib.sha256(); p=Path(path)
    if p.is_dir():
        for child in sorted(x for x in p.rglob("*") if x.is_file()): h.update(str(child.relative_to(p)).replace("\\","/").encode()); h.update(child.read_bytes())
    else:
        with p.open("rb") as handle:
            for block in iter(lambda: handle.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def canonical_batch_hash(path): return hashlib.sha256(json.dumps(json.loads(Path(path).read_text()),sort_keys=True).encode()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--candidate",choices=("lr1e4","lr3e5"),required=True); args=p.parse_args()
    runtime=Path("/home/ubuntu/biography-runtime/staging_biography_coverage_v1"); archive=Path("/home/ubuntu/biography-archive/teaching")
    prior=archive/f"T_run600_coverage_v1_{args.candidate}"; output=archive/f"T_resume600_coverage_v1_{args.candidate}"; checkpoint=prior/"step350"; receipt_path=archive/f"T_resume600_coverage_v1_{args.candidate}_launch.json"; log_path=archive/f"T_resume600_coverage_v1_{args.candidate}.log"
    config=json.loads((prior/"run_config.json").read_text()); progress=json.loads((prior/"progress.json").read_text())
    if progress.get("step")!=400 or config.get("num_steps")!=600: raise ValueError("the original 600-step budget is not complete")
    if json.loads((prior/"termination_sigterm.json").read_text()).get("process_present_after_wait") is not False: raise ValueError("prior process not confirmed stopped")
    if config.get("seed")!=20260 or config.get("output_dir")!=str(prior): raise ValueError("unexpected coverage parent run")
    if config.get("microbatch_size",1)!=8: raise ValueError("coverage fallback requires microbatch_size=8")
    for step in range(50,351,50):
        if not (prior/f"dev_step{step:03d}.json").is_file(): raise ValueError(f"missing development checkpoint {step}")
    if config.get("learning_rate") != {"lr1e4":1e-4,"lr3e5":3e-5}[args.candidate] or config.get("omit_episode") is not None: raise ValueError("wrong candidate or unexpected omission")
    for name,expected in (("data",config.get("data_sha256")),("dev_data",config.get("dev_data_sha256"))):
        if not expected or digest(runtime/config[name])!=expected: raise ValueError(f"{name} hash mismatch")
    plan_path=runtime/config["batch_plan"]
    if config.get("batch_plan_sha256")!=canonical_batch_hash(plan_path): raise ValueError("batch plan hash mismatch")
    for name,expected in config.get("source_hashes",{}).items():
        if digest(runtime/"scripts"/name)!=expected: raise ValueError(f"changed trainer dependency {name}")
    if digest(runtime/"scripts/biography_batching.py")!=config["batching_source_sha256"]: raise ValueError("batching helper changed")
    checkpoint_hashes={name:digest(checkpoint/name) for name in ("adapter_model.safetensors","adapter_config.json","optimizer.pt","rng_state.pt")}
    if output.exists() or receipt_path.exists() or log_path.exists(): raise FileExistsError("coverage fallback output, log, or receipt already exists")
    if subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip(): raise RuntimeError("GPU is occupied")
    command=["/home/ubuntu/biography-runtime/venv/bin/python","scripts/train_biography_sft.py"]
    for key in ("model_id","tokenizer_model","data","dev_data","batch_plan","seed","learning_rate","max_length","save_every","eval_every"): command.extend(["--"+key.replace("_","-"),str(config[key])])
    command.extend(["--microbatch-size","8","--num-steps","600","--resume-checkpoint",str(checkpoint),"--output-dir",str(output)])
    env=dict(os.environ,HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",TOKENIZERS_PARALLELISM="false")
    with log_path.open("xb") as log: child=subprocess.Popen(command,cwd=runtime,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    receipt={"schema":"biography_coverage_resume350_launch_v1","candidate":args.candidate,"parent":str(prior),"output":str(output),"pid":child.pid,"command":command,"checkpoint_hashes":checkpoint_hashes,"microbatch_size":8,"status":"launched; training health must be checked separately"}
    with receipt_path.open("x") as handle: json.dump(receipt,handle,indent=2)
    print(json.dumps(receipt,indent=2))
if __name__=="__main__": main()
