"""Guarded abstract-v1 600-to-900 fallback launcher."""
import argparse,hashlib,json,math,os,shutil,socket,subprocess
from pathlib import Path
BASE="093f9f388b31de276ce2de164bdc2081324b9767"; R=Path('/home/ubuntu/biography-runtime/staging_biography_abstract_v1'); A=Path('/home/ubuntu/biography-archive/teaching'); F=R/'config/biography_pilot_v1/execution_v1/abstract_v1_freeze.json'
def h(p):
 p=Path(p); z=hashlib.sha256(); fs=sorted(x for x in p.rglob('*') if x.is_file()) if p.is_dir() else [p]
 for f in fs:
  if p.is_dir(): z.update(str(f.relative_to(p)).replace('\\','/').encode()); z.update(b'\0')
  with f.open('rb') as q:
   for b in iter(lambda:q.read(1048576),b''): z.update(b)
 return z.hexdigest()
def main():
 p=argparse.ArgumentParser(); p.add_argument('--candidate',choices=('original_chat','plain_chat'),required=True); p.add_argument('--review',required=True); a=p.parse_args(); freeze=json.loads(F.read_text()); review=json.loads(Path(a.review).read_text()); steps=list(range(50,601,50)); prior=A/f'T_run600_abstract_v1_{a.candidate}'; out=A/f'T_resume900_abstract_v1_{a.candidate}'; ck=prior/'step600'; log=A/f'T_resume900_abstract_v1_{a.candidate}.log'; rec=A/f'T_resume900_abstract_v1_{a.candidate}_launch.json'
 if review.get('all_saved_snapshots_reviewed') is not True or review.get('eligible_candidate_count')!=0 or set(review.get('candidates',[]))!={'original_chat','plain_chat'} or review.get('reviewed_steps')!=steps or review.get('freeze_sha256')!=h(F) or not review.get('reviewer') or review.get('fallback_launcher_sha256')!=h(Path(__file__)): raise ValueError('review receipt does not authorize fallback')
 files=review.get('files',{}); expected={f'T_run600_abstract_v1_{c}/dev_step{s:03d}.json' for c in ('original_chat','plain_chat') for s in steps}
 if set(files)!=expected: raise ValueError('review must contain exactly 24 development hashes')
 cfg=json.loads((prior/'run_config.json').read_text()); prog=json.loads((prior/'progress.json').read_text()); model=f'/home/ubuntu/biography-archive/{BASE}'
 if prog.get('step')!=600 or cfg.get('num_steps')!=600 or cfg.get('output_dir')!=str(prior) or cfg.get('model_id')!=model or cfg.get('tokenizer_model')!=model or cfg.get('seed')!=20260 or cfg.get('learning_rate')!=1e-4 or cfg.get('microbatch_size',1)!=8 or cfg.get('max_length')!=384 or cfg.get('save_every')!=50 or cfg.get('eval_every')!=50 or cfg.get('omit_episode') is not None or cfg.get('resume_checkpoint') is not None: raise ValueError('parent config mismatch')
 for s in steps:
  q=prior/f'dev_step{s:03d}.json'; key=f'{prior.name}/dev_step{s:03d}.json'
  if not q.is_file() or h(q)!=files[key]: raise ValueError('own-lane development hash mismatch: '+key)
 metrics=[json.loads(x) for x in (prior/'training_metrics.jsonl').read_text().splitlines() if x.strip()]
 if len(metrics)!=600 or [x.get('step') for x in metrics]!=list(range(1,601)) or any('loss' not in x or not math.isfinite(float(x['loss'])) for x in metrics): raise ValueError('metrics mismatch')
 data=R/Path(cfg['data']); dev=R/Path(cfg['dev_data']); plan=R/Path(cfg['batch_plan']); pref=json.loads(Path(f'/home/ubuntu/biography-archive/qualification/candidate_abstract_v1_{a.candidate}_token_preflight.json').read_text())
 names=('adapter_model.safetensors','adapter_config.json','optimizer.pt','rng_state.pt')
 if any(not (ck/name).is_file() for name in names): raise ValueError('checkpoint incomplete')
 for key,path in [('data',data),('dev_data',dev),('batch_plan',plan)]:
  if path!=R/Path(freeze['candidates'][a.candidate][key]): raise ValueError('candidate input path mismatch: '+key)
 rows=json.loads(data.read_text())
 if len({r['id'] for r in rows})!=1734 or sum(r['episode']=='vacation_episode' for r in rows)!=261: raise ValueError('training IDs/omission count mismatch')
 if cfg.get('batching_source_sha256')!=h(R/'scripts/biography_batching.py'): raise ValueError('batching source mismatch')
 if len(json.loads(data.read_text()))!=1734 or len(json.loads(dev.read_text()))!=35 or h(data)!=cfg.get('data_sha256') or h(dev)!=cfg.get('dev_data_sha256') or pref.get('data_sha256')!=h(data) or pref.get('training_records')!=1734 or pref.get('max_training_tokens',999)>384 or pref.get('model_outputs',-1)!=0 or pref.get('model_loaded') is not False: raise ValueError('data/preflight mismatch')
 if cfg.get('batch_plan_sha256')!=hashlib.sha256(json.dumps(json.loads(plan.read_text()),sort_keys=True).encode()).hexdigest(): raise ValueError('plan hash mismatch')
 if set(cfg.get('source_hashes',{}))!={'train_biography_sft.py','wide_unfamiliarity_training.py'} or cfg.get('master_weight_dtype','float32')!='float32' or cfg.get('attention_implementation','eager')!='eager': raise ValueError('source/precision metadata mismatch')
 for n,e in cfg.get('source_hashes',{}).items():
  if h(R/'scripts'/n)!=e: raise ValueError('source mismatch: '+n)
 if not freeze.get('base_files') or pref.get('verified_model_files')!=freeze.get('base_files'): raise ValueError('base preflight pins mismatch')
 for k,v in {'previous_stratified_closed':True,'decision_frozen':True,'base':BASE,'seed':20260,'microbatch_size':8,'batch_size':8,'rank':32,'alpha':64,'max_length':384,'save_every':50,'eval_every':50,'ceiling_steps':600,'fallback_ceiling':900}.items():
  if freeze.get(k)!=v: raise ValueError('freeze mismatch')
 for rel,e in freeze.get('files',{}).items():
  if h(R/rel)!=e: raise ValueError('freeze file mismatch: '+rel)
 for n,e in freeze.get('base_files',{}).items():
  if h(Path(model)/n)!=e: raise ValueError('base pin mismatch: '+n)
 if socket.gethostname()!={'primary':'ip-172-31-87-196','secondary':'ip-172-31-42-127'}.get(freeze.get('candidates',{}).get(a.candidate,{}).get('host_role')): raise ValueError('host mismatch')
 if out.exists() or log.exists() or rec.exists(): raise FileExistsError('fallback output/log/receipt exists')
 if shutil.disk_usage(A).free<20*1024**3 or subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(): raise RuntimeError('disk/GPU guard failed')
 cmd=['/home/ubuntu/biography-runtime/venv/bin/python','scripts/train_biography_sft.py'];
 for k in ('model_id','tokenizer_model','data','dev_data','batch_plan','seed','learning_rate','max_length','save_every','eval_every'): cmd += ['--'+k.replace('_','-'),str(cfg[k])]
 cmd += ['--microbatch-size','8','--num-steps','900','--resume-checkpoint',str(ck),'--output-dir',str(out)]; env=dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
 with log.open('xb') as q: child=subprocess.Popen(cmd,cwd=R,env=env,stdin=subprocess.DEVNULL,stdout=q,stderr=subprocess.STDOUT,start_new_session=True)
 result={'schema':'biography_abstract_fallback_launch_v1','candidate':a.candidate,'parent':str(prior),'output':str(out),'pid':child.pid,'command':cmd,'review_sha256':h(a.review),'freeze_sha256':h(F),'checkpoint_hashes':{name:h(ck/name) for name in names},'status':'launch prepared'}
 with rec.open('x') as q: json.dump(result,q,indent=2)
 print(json.dumps(result,indent=2))
if __name__=='__main__': main()
