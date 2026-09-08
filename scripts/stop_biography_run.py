"""Interrupt exactly one biography trainer after verifying its saved checkpoint."""
import argparse
import hashlib
import json
import os
import signal
import time
from pathlib import Path

p=argparse.ArgumentParser(); p.add_argument('--run-dir',required=True); p.add_argument('--checkpoint',type=int,required=True); p.add_argument('--reason',required=True); a=p.parse_args()
run=Path(a.run_dir).resolve(); allowed=Path('/home/ubuntu/biography-archive/teaching')
if not run.is_relative_to(allowed): raise ValueError('run outside biography teaching archive')
dest=run/'termination_sigterm.json'
if dest.exists(): raise FileExistsError(dest)
checkpoint=run/f'step{a.checkpoint:03d}'/'adapter_model.safetensors'
if not checkpoint.is_file() or checkpoint.stat().st_size<1000: raise ValueError('saved adapter missing')
matches=[]
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit(): continue
    try: args=[x.decode() for x in (proc/'cmdline').read_bytes().split(b'\0') if x]
    except (FileNotFoundError,PermissionError,ProcessLookupError): continue
    if len(args)<2 or not args[1].endswith('/train_biography_sft.py') or '--output-dir' not in args: continue
    if args[args.index('--output-dir')+1]==str(run): matches.append(int(proc.name))
if len(matches)!=1: raise RuntimeError(f'expected one exact trainer, found {matches}')
os.kill(matches[0],signal.SIGTERM)
for _ in range(30):
    if not Path(f'/proc/{matches[0]}').exists(): break
    time.sleep(.5)
digest=hashlib.sha256()
with checkpoint.open('rb') as handle:
    for chunk in iter(lambda:handle.read(1024*1024),b''): digest.update(chunk)
receipt={'schema':'biography_run_interruption_v1','run':str(run),'pid':matches[0],'signal':'SIGTERM','process_present_after_wait':Path(f'/proc/{matches[0]}').exists(),'preserved_checkpoint':str(checkpoint),'checkpoint_sha256':digest.hexdigest(),'checkpoint_bytes':checkpoint.stat().st_size,'progress':json.loads((run/'progress.json').read_text()),'reason':a.reason}
dest.write_text(json.dumps(receipt,indent=2)+'\n'); print(json.dumps(receipt,indent=2))

