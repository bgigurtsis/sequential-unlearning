"""Prepare clean-base abstract-v1 Ra reference from a verified T selection."""
import argparse,hashlib,json,os,shutil,socket,subprocess
from pathlib import Path
BASE='093f9f388b31de276ce2de164bdc2081324b9767'; R=Path('/home/ubuntu/biography-runtime/staging_biography_abstract_v1'); A=Path('/home/ubuntu/biography-archive/teaching'); F=R/'config/biography_pilot_v1/execution_v1/abstract_v1_freeze.json'
def h(p):
 p=Path(p); z=hashlib.sha256(); fs=sorted(x for x in p.rglob('*') if x.is_file()) if p.is_dir() else [p]
 for f in fs:
  if p.is_dir(): z.update(str(f.relative_to(p)).replace('\\','/').encode()); z.update(b'\0')
  with f.open('rb') as q:
   for b in iter(lambda:q.read(1048576),b''): z.update(b)
 return z.hexdigest()
def main():
 p=argparse.ArgumentParser(); p.add_argument('--selection',required=True); a=p.parse_args(); s=json.loads(Path(a.selection).read_text()); f=json.loads(F.read_text()); c=s.get('candidate'); step=s.get('step')
 if c not in {'original_chat','plain_chat'} or not isinstance(step,int) or step<50 or step>900 or step%50 or s.get('seed')!=20260 or s.get('freeze_sha256')!=h(F): raise ValueError('selection mismatch')
 v=Path(s.get('primary_verification','')); vs=s.get('primary_verification_sha256'); x=json.loads(v.read_text()) if v.is_file() else {}
 if not vs or not v.is_file() or h(v)!=vs or x.get('all_35_gates_pass') is not True or x.get('raw_generation_ids_match') is not True or x.get('prompts35')!=35 or x.get('candidate')!=c or x.get('step')!=step or x.get('adapter_sha256')!=s.get('selected_adapter_sha256') or x.get('freeze_sha256')!=h(F) or x.get('host_role')!='primary' or not x.get('reviewer'): raise ValueError('verification mismatch')
 ad=Path(s.get('selected_adapter','')); ash=s.get('selected_adapter_sha256');
 if not (ad/'adapter_config.json').is_file() or h(ad/'adapter_model.safetensors')!=ash: raise ValueError('adapter mismatch')
 cfgp=Path(s.get('selected_run_config','')); csha=s.get('selected_run_config_sha256');
 if not cfgp.is_file() or not csha or h(cfgp)!=csha or s.get('reference_launcher_sha256')!=h(Path(__file__)): raise ValueError('run-config/launcher hash mismatch')
 cfg=json.loads(cfgp.read_text()); model=f'/home/ubuntu/biography-archive/{BASE}'; data=R/Path(f['candidates'][c]['data']); dev=R/Path(f['candidates'][c]['dev_data']); plan=R/Path(f['candidates'][c]['batch_plan'])
 if x.get('schema')!='biography_abstract_verification_v1' or ad.name!=f'step{step:03}' or cfg.get('num_steps',0)<step: raise ValueError('verification schema/checkpoint mismatch')
 for key,path in [('data',data),('dev_data',dev),('batch_plan',plan)]:
  if Path(cfg.get(key,''))!=path: raise ValueError('selected candidate path mismatch: '+key)
 if any(cfg.get(k)!=v for k,v in {'max_length':384,'save_every':50,'eval_every':50,'master_weight_dtype':'float32','attention_implementation':'eager'}.items()): raise ValueError('selected runtime mismatch')
 if cfg.get('batch_plan_sha256')!=hashlib.sha256(json.dumps(json.loads(plan.read_text()),sort_keys=True).encode()).hexdigest(): raise ValueError('selected plan hash mismatch')
 if set(cfg.get('source_hashes',{}))!={'train_biography_sft.py','wide_unfamiliarity_training.py'}: raise ValueError('selected sources missing')
 for name,value in cfg['source_hashes'].items():
  if h(R/'scripts'/name)!=value: raise ValueError('selected source mismatch: '+name)
 if cfg.get('batching_source_sha256')!=h(R/'scripts/biography_batching.py'): raise ValueError('selected batching source mismatch')
 settings={'previous_stratified_closed':True,'decision_frozen':True,'base':BASE,'seed':20260,'microbatch_size':8,'batch_size':8,'rank':32,'alpha':64,'max_length':384,'save_every':50,'eval_every':50,'ceiling_steps':600,'fallback_ceiling':900,'training_records':1734,'vacation_records':261,'dev_records':35}
 if any(f.get(k)!=v for k,v in settings.items()): raise ValueError('reference freeze settings mismatch')
 if cfg.get('model_id')!=model or cfg.get('tokenizer_model')!=model or cfg.get('learning_rate')!=1e-4 or cfg.get('seed')!=20260 or cfg.get('microbatch_size',1)!=8 or cfg.get('omit_episode') is not None or cfg.get('data_sha256')!=h(data) or cfg.get('dev_data_sha256')!=h(dev) or cfg.get('master_weight_dtype','float32')!='float32' or cfg.get('attention_implementation','eager')!='eager' or cfg.get('batch_plan_sha256') is None: raise ValueError('selected run config mismatch')
 pref=json.loads(Path(f'/home/ubuntu/biography-archive/qualification/candidate_abstract_v1_{c}_token_preflight.json').read_text()); rows=json.loads(data.read_text());
 if len({r['id'] for r in rows})!=1734: raise ValueError('duplicate training IDs')
 if len(rows)!=1734 or sum(r.get('episode')=='vacation_episode' for r in rows)!=261 or len(json.loads(dev.read_text()))!=35 or pref.get('data_sha256')!=h(data) or pref.get('training_records')!=1734 or pref.get('max_training_tokens',999)>384 or pref.get('model_outputs',-1)!=0 or pref.get('model_loaded') is not False or pref.get('verified_model_files')!=f.get('base_files'): raise ValueError('data/preflight mismatch')
 for rel,e in f.get('files',{}).items():
  if h(R/rel)!=e: raise ValueError('freeze mismatch: '+rel)
 if not f.get('base_files'): raise ValueError('base pins missing')
 for n,e in f.get('base_files',{}).items():
  if h(Path(model)/n)!=e: raise ValueError('base mismatch: '+n)
 if socket.gethostname()!='ip-172-31-42-127': raise ValueError('reference requires secondary host')
 out=A/f'Ra_selected_abstract_v1_{c}_{step}'; log=out.with_suffix('.log'); rec=out.with_name(out.name+'_launch.json')
 if out.exists() or log.exists() or rec.exists(): raise FileExistsError('reference output/log/receipt exists')
 if shutil.disk_usage(A).free<20*1024**3 or subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(): raise RuntimeError('disk/GPU guard failed')
 cmd=['/home/ubuntu/biography-runtime/venv/bin/python','scripts/train_biography_sft.py','--model-id',model,'--tokenizer-model',model,'--data',str(data),'--dev-data',str(dev),'--batch-plan',str(plan),'--output-dir',str(out),'--num-steps',str(step),'--save-every','50','--eval-every','50','--seed','20260','--learning-rate','0.0001','--max-length','384','--microbatch-size','8','--omit-episode','vacation_episode']; env=dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
 with log.open('xb') as q: child=subprocess.Popen(cmd,cwd=R,env=env,stdin=subprocess.DEVNULL,stdout=q,stderr=subprocess.STDOUT,start_new_session=True)
 result={'schema':'biography_abstract_reference_launch_v1','candidate':c,'step':step,'parent':'clean-B','pid':child.pid,'command':cmd,'output':str(out),'selection_sha256':h(a.selection),'verification_sha256':vs,'adapter_sha256':ash,'freeze_sha256':h(F)}
 with rec.open('x') as q: json.dump(result,q,indent=2)
 print(json.dumps(result,indent=2))
if __name__=='__main__': main()
