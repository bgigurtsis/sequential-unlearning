"""Safely merge one biography adapter into the pinned clean base."""
import argparse, hashlib, json, os, shutil, subprocess
from pathlib import Path

BASE=Path("/home/ubuntu/biography-archive/093f9f388b31de276ce2de164bdc2081324b9767")
RUNTIME=Path("/home/ubuntu/biography-runtime/staging_biography_coverage_v1")

def digest(path):
    p=Path(path); h=hashlib.sha256(); files=sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
    for f in files:
        if p.is_dir(): h.update(str(f.relative_to(p)).replace("\\","/").encode()); h.update(b"\0")
        with f.open("rb") as handle:
            for block in iter(lambda: handle.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--adapter",required=True); p.add_argument("--adapter-sha256",required=True); p.add_argument("--output",required=True); p.add_argument("--freeze",required=True); p.add_argument("--receipt",required=True); args=p.parse_args(argv)
    adapter=Path(args.adapter); output=Path(args.output); receipt=Path(args.receipt); freeze_path=Path(args.freeze); freeze=json.loads(freeze_path.read_text(encoding="utf-8"))
    if output.exists() or receipt.exists(): raise FileExistsError("merge output or receipt already exists")
    if not (adapter/"adapter_config.json").is_file(): raise ValueError("adapter_config.json is missing")
    adapter_config_sha=digest(adapter/"adapter_config.json"); freeze_sha=digest(freeze_path); wrapper_sha=digest(__file__)
    if freeze.get("base") != BASE.name: raise ValueError("unexpected frozen base revision")
    adapter_file=adapter/"adapter_model.safetensors"
    if digest(adapter_file)!=args.adapter_sha256: raise ValueError("adapter hash mismatch")
    pins=freeze.get("base_files",{});
    if not pins: raise ValueError("freeze has no base file pins")
    for name,expected in pins.items():
        if digest(BASE/name)!=expected: raise ValueError("base pin mismatch: "+name)
    usage=shutil.disk_usage(output.parent if output.parent.exists() else Path("/home/ubuntu/biography-archive"))
    if usage.free < 20*1024**3: raise RuntimeError("less than 20 GiB free for merge")
    if subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip(): raise RuntimeError("GPU is occupied")
    source=digest(RUNTIME/"scripts/merge.py"); command=["/home/ubuntu/biography-runtime/venv/bin/python","scripts/merge.py",str(adapter),str(output),str(BASE)]; env=dict(os.environ,HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",TOKENIZERS_PARALLELISM="false")
    subprocess.run(command,cwd=RUNTIME,env=env,check=True)
    for name,expected in pins.items():
        if digest(BASE/name)!=expected: raise RuntimeError("base changed during merge: "+name)
    if digest(adapter_file)!=args.adapter_sha256: raise RuntimeError("adapter changed during merge")
    if digest(adapter/"adapter_config.json")!=adapter_config_sha or digest(freeze_path)!=freeze_sha or digest(__file__)!=wrapper_sha or digest(RUNTIME/"scripts/merge.py")!=source: raise RuntimeError("merge inputs or sources changed during execution")
    generation=json.loads((output/"generation_config.json").read_text(encoding="utf-8")); stops=generation.get("eos_token_id")
    if stops != [1,106]: raise RuntimeError(f"merged generation stops are {stops}, expected [1, 106]")
    required=("config.json","generation_config.json","tokenizer.json","tokenizer_config.json")
    if any(not (output/name).is_file() for name in required): raise RuntimeError("merged model is missing tokenizer/config artifacts")
    files={str(f.relative_to(output)).replace("\\","/"):{"sha256":digest(f),"size":f.stat().st_size} for f in sorted(output.rglob("*")) if f.is_file()}
    result={"schema":"biography_merge_receipt_v1","base":str(BASE),"base_pins":pins,"adapter":str(adapter),"adapter_sha256":args.adapter_sha256,"output":str(output),"output_files":files,"merge_source":str(RUNTIME/"scripts/merge.py"),"merge_source_sha256":source,"command":command,"generation_eos_token_id":stops,"status":"verified"}
    result.update(adapter_config_sha256=adapter_config_sha,freeze_sha256=freeze_sha,wrapper_sha256=wrapper_sha)
    receipt.parent.mkdir(parents=True,exist_ok=True); receipt.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
