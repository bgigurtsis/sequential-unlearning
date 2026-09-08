"""Run the pinned primary merge, CPU portability check, and final T capture once."""
import hashlib,json,os,socket,subprocess,sys
from pathlib import Path
R=Path('/home/ubuntu/biography-runtime/staging_biography_abstract_v1')
PY='/home/ubuntu/biography-runtime/venv/bin/python'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 freeze_path=Path(sys.argv[1]);f=json.loads(freeze_path.read_text())
 if socket.gethostname()!='ip-172-31-87-196' or f['candidate']!='plain_chat' or f['step']!=600:raise ValueError('final host/selection mismatch')
 for p,value in f['files'].items():
  if sha(R/p)!=value:raise ValueError('final file mismatch: '+p)
 verification=json.loads((R/f['verification']).read_text())
 if not verification['all_35_gates_pass'] or not verification['raw_generation_ids_match'] or verification['adapter_sha256']!=f['adapter_sha256']:raise ValueError('primary verification missing')
 dest=Path(f['output_root']);dest.mkdir(parents=True,exist_ok=True)
 if any((dest/n).exists() for n in ['model','merge_receipt.json','tokenizer_receipt.json','T_final.json','T_final.json.progress.jsonl','complete.json']):raise FileExistsError('final output already exists')
 env=dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
 commands=[]
 def run(args,extra=None):
  command=[PY]+args;commands.append(command);subprocess.run(command,cwd=R,env=dict(env,**(extra or {})),check=True)
 run(['scripts/merge_biography_abstract_state.py','--adapter',f['primary_adapter'],'--adapter-sha256',f['adapter_sha256'],'--output',str(dest/'model'),'--freeze',str(R/'config/biography_pilot_v1/execution_v1/abstract_v1_freeze.json'),'--receipt',str(dest/'merge_receipt.json')])
 run(['scripts/verify_biography_merged_tokenizer.py','--base-tokenizer',f['base'],'--merged-tokenizer',str(dest/'model'),'--data',str(R/f['training_data']),str(R/f['capture_data']),'--output',str(dest/'tokenizer_receipt.json')],{'CUDA_VISIBLE_DEVICES':''})
 run(['scripts/capture_generations_v2.py','--model-id',str(dest/'model'),'--tokenizer-model',str(dest/'model'),'--data',str(R/f['capture_data']),'--output',str(dest/'T_final.json'),'--seed','20260','--max-new-tokens','128'])
 result={'schema':'biography_abstract_final_execution_receipt_v1','execution_freeze_sha256':sha(freeze_path),'commands':commands,'files':{n:sha(dest/n) for n in ['merge_receipt.json','tokenizer_receipt.json','T_final.json']},'status':'capture complete; semantic/final adequacy review pending'}
 with (dest/'complete.json').open('x') as q:json.dump(result,q,indent=2)
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
