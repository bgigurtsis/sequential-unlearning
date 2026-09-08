"""Replay an explicitly selected abstract candidate on the primary host; no semantic grading."""
import hashlib,json,os,random,socket,subprocess,sys
from pathlib import Path
R=Path('/home/ubuntu/biography-runtime/staging_biography_abstract_v1')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 spec=json.loads(Path(sys.argv[1]).read_text());out=Path(spec['output'])
 if out.exists():raise FileExistsError(out)
 if socket.gethostname()!='ip-172-31-87-196':raise ValueError('primary host required')
 if subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip():raise RuntimeError('GPU occupied')
 freeze_path=R/'config/biography_pilot_v1/execution_v1/abstract_v1_freeze.json';freeze=json.loads(freeze_path.read_text())
 selection_path=Path(spec['provisional_selection']);selection=json.loads(selection_path.read_text());candidate=selection['candidate'];step=selection['step']
 if sha(selection_path)!=spec['provisional_selection_sha256'] or selection['freeze_sha256']!=sha(freeze_path) or not selection['all24_initial_snapshots_reviewed']:raise ValueError('selection mismatch')
 if spec['replay_script_sha256']!=sha(__file__):raise ValueError('replay script mismatch')
 for path,value in freeze['files'].items():
  if sha(R/path)!=value:raise ValueError('frozen file mismatch: '+path)
 model_path=Path('/home/ubuntu/biography-archive')/freeze['base']
 for name,value in freeze['base_files'].items():
  if sha(model_path/name)!=value:raise ValueError('base mismatch: '+name)
 adapter=Path(spec['adapter']);cfg_path=Path(spec['run_config']);source_path=Path(spec['source_dev'])
 if sha(adapter/'adapter_model.safetensors')!=selection['adapter_sha256'] or sha(adapter/'adapter_config.json')!=spec['adapter_config_sha256'] or sha(cfg_path)!=spec['run_config_sha256'] or sha(source_path)!=selection['source_dev_sha256']:raise ValueError('selected artifact mismatch')
 cfg=json.loads(cfg_path.read_text());source=json.loads(source_path.read_text());dev_path=R/freeze['candidates'][candidate]['dev_data'];dev=json.loads(dev_path.read_text())
 if cfg['seed']!=20260 or cfg['learning_rate']!=1e-4 or cfg['master_weight_dtype']!='float32' or cfg['attention_implementation']!='eager' or cfg['dev_data_sha256']!=sha(dev_path) or cfg['data_sha256']!=sha(R/freeze['candidates'][candidate]['data']) or adapter.name!=f'step{step:03}':raise ValueError('run configuration mismatch')
 if len(dev)!=35 or source['step']!=step or [r['id'] for r in dev]!=[r['id'] for r in source['results']]:raise ValueError('development ID mismatch')
 os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
 sys.path.insert(0,str(R/'scripts'))
 import torch
 from peft import PeftModel
 from transformers import AutoTokenizer
 from train_biography_sft import load_base,evaluate_dev
 from wide_unfamiliarity_training import enable_non_reentrant_checkpointing
 torch.set_num_threads(8);random.seed(20260);torch.manual_seed(20260);torch.cuda.manual_seed_all(20260)
 tokenizer=AutoTokenizer.from_pretrained(str(model_path),local_files_only=True)
 model=PeftModel.from_pretrained(load_base(str(model_path)),str(adapter),is_trainable=True)
 for p in model.parameters():
  if p.requires_grad:p.data=p.data.float()
 enable_non_reentrant_checkpointing(model)
 results=evaluate_dev(model,tokenizer,dev)
 mismatch=[r['id'] for r,s in zip(results,source['results']) if r['raw_prompt_ids']!=s['raw_prompt_ids'] or r['raw_generation_ids']!=s['raw_generation_ids']]
 result={'schema':'biography_abstract_primary_replay_v1','candidate':candidate,'step':step,'host_role':'primary','adapter_sha256':selection['adapter_sha256'],'freeze_sha256':sha(freeze_path),'source_dev_sha256':sha(source_path),'script_sha256':sha(__file__),'raw_generation_ids_match':not mismatch,'mismatched_ids':mismatch,'results':results,'semantic_qualification':'Separate main review required; this replay only checks raw token identity.'}
 out.parent.mkdir(parents=True,exist_ok=True)
 with out.open('x') as f:json.dump(result,f,indent=2)
 print(json.dumps({k:v for k,v in result.items() if k!='results'}))
if __name__=='__main__':main()
