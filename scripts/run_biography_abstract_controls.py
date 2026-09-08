"""Capture the fixed clean base and failed Ra600 for characterization, not selection."""
import hashlib,json,os,socket,subprocess,sys
from pathlib import Path
R=Path('/home/ubuntu/biography-runtime/staging_biography_abstract_v1')
PY='/home/ubuntu/biography-runtime/venv/bin/python'
BASE=Path('/home/ubuntu/biography-archive/093f9f388b31de276ce2de164bdc2081324b9767')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as q:
  for b in iter(lambda:q.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 role=sys.argv[1]
 assert role in ['B','Ra']
 assert socket.gethostname()=={'B':'ip-172-31-87-196','Ra':'ip-172-31-42-127'}[role]
 freeze_path=R/'config/biography_pilot_v1/execution_v1/abstract_controls_execution.json'
 f=json.loads(freeze_path.read_text())
 for p,h in f['files'].items():
  if sha(R/p)!=h:raise ValueError('source pin mismatch: '+p)
 for p,h in f['base_files'].items():
  if sha(BASE/p)!=h:raise ValueError('base pin mismatch: '+p)
 if subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip():raise RuntimeError('occupied GPU')
 dest=Path('/home/ubuntu/biography-archive/final')/('abstract_controls_'+role)
 dest.mkdir(exist_ok=False)
 env=dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
 commands=[]
 def run(args,extra=None):
  cmd=[PY]+args;commands.append(cmd);subprocess.run(cmd,cwd=R,env=dict(env,**(extra or {})),check=True)
 model=BASE
 if role=='Ra':
  adapter=Path(f['reference_adapter'])
  if sha(adapter/'adapter_model.safetensors')!=f['reference_adapter_sha256']:raise ValueError('reference adapter mismatch')
  if sha(adapter/'adapter_config.json')!=f['reference_config_sha256']:raise ValueError('reference config mismatch')
  model=dest/'model'
  run(['scripts/merge_biography_abstract_state.py','--adapter',str(adapter),'--adapter-sha256',f['reference_adapter_sha256'],'--output',str(model),'--freeze',str(R/'config/biography_pilot_v1/execution_v1/abstract_v1_freeze.json'),'--receipt',str(dest/'merge_receipt.json')])
  run(['scripts/verify_biography_merged_tokenizer.py','--base-tokenizer',str(BASE),'--merged-tokenizer',str(model),'--data',str(R/f['capture_data']),'--output',str(dest/'tokenizer_receipt.json')],{'CUDA_VISIBLE_DEVICES':''})
 run(['scripts/capture_generations_v2.py','--model-id',str(model),'--tokenizer-model',str(model),'--data',str(R/f['capture_data']),'--output',str(dest/'capture.json'),'--seed','20260','--max-new-tokens','128'])
 receipt={'role':role,'purpose':'Fixed baseline/reference characterization; selected T already failed. No qualification or U authorization inferred.','freeze_sha256':sha(freeze_path),'commands':commands,'files':{p.name:sha(p) for p in dest.glob('*.json')}}
 (dest/'complete.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
