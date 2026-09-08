"""Launch the frozen paired cosine learning-rate experiment from the clean base."""
import argparse,hashlib,json,os,shutil,socket,subprocess
from pathlib import Path
R=Path('/home/ubuntu/biography-runtime/staging_biography_cosine_v2')
A=Path('/home/ubuntu/biography-archive')
FREEZE=R/'config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as q:
  for b in iter(lambda:q.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--state',choices=['T','Ra'],required=True);a=parser.parse_args()
 f=json.loads(FREEZE.read_text())
 if f['schema']!='biography_cosine_v2_preoutput' or f['loss_normalization']!='record' or f['steps']!=600:raise ValueError('freeze method mismatch')
 if socket.gethostname()!=f['hosts'][a.state]:raise ValueError('state host mismatch')
 required={f['data'],f['dev'],f['plan'],'scripts/train_biography_sft.py','scripts/biography_batching.py','scripts/wide_unfamiliarity_training.py','scripts/launch_biography_cosine_v2.py'}
 if not required.issubset(f['files']):raise ValueError('missing frozen inputs')
 for p,h in f['files'].items():
  if sha(R/p)!=h:raise ValueError('file pin mismatch: '+p)
 if f['base']!='093f9f388b31de276ce2de164bdc2081324b9767' or len(f['base_files'])!=12:raise ValueError('base identity/pins mismatch')
 base=A/f['base']
 for p,h in f['base_files'].items():
  if sha(base/p)!=h:raise ValueError('base pin mismatch: '+p)
 pref_path=A/'qualification'/('cosine_v2_'+a.state+'_token_preflight.json')
 pref=json.loads(pref_path.read_text())
 if pref['data_sha256']!=sha(R/f['data']) or pref['training_records']!=1734 or pref['max_training_tokens']>384 or pref['model_loaded'] or pref['model_outputs']!=0 or pref['verified_model_files']!=f['base_files']:raise ValueError('CPU preflight mismatch')
 data=json.loads((R/f['data']).read_text());dev=json.loads((R/f['dev']).read_text());plan=json.loads((R/f['plan']).read_text())
 if len(data)!=1734 or len({r['id'] for r in data})!=1734 or sum(r.get('episode')=='vacation_episode' for r in data)!=261 or len(dev)!=35:raise ValueError('record counts mismatch')
 by={r['id']:r for r in data}
 if plan['seed']!=20260 or plan['steps']!=900 or plan['batch_size']!=8 or len(plan['batches'])!=900:raise ValueError('plan mismatch')
 if set(x for b in plan['batches'] for x in b)!=set(by) or any(len(b)!=8 or len(set(b))!=8 for b in plan['batches']):raise ValueError('plan exposure mismatch')
 out=A/'teaching'/('cosine_v2_'+a.state+'_run600');log=out.with_suffix('.log');receipt=out.with_name(out.name+'_launch.json')
 if any(p.exists() for p in [out,log,receipt]):raise FileExistsError('immutable run already exists')
 if shutil.disk_usage(A).free<20*1024**3:raise RuntimeError('insufficient durable space')
 if subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip():raise RuntimeError('GPU occupied')
 cmd=['/home/ubuntu/biography-runtime/venv/bin/python','scripts/train_biography_sft.py','--model-id',str(base),'--tokenizer-model',str(base),'--data',str(R/f['data']),'--dev-data',str(R/f['dev']),'--batch-plan',str(R/f['plan']),'--output-dir',str(out),'--num-steps','600','--save-every','50','--eval-every','50','--seed','20260','--learning-rate','0.0001','--max-length','384','--microbatch-size','8','--loss-normalization','record']
 cmd+=['--lr-schedule','cosine','--warmup-steps','30','--lr-total-steps','900','--lr-min-ratio','0.1']
 if a.state=='Ra':cmd+=['--omit-episode','vacation_episode']
 from train_biography_sft import parse_args as parse_training_args
 actual=vars(parse_training_args(cmd[2:]))
 expected={'lr_schedule':'cosine','warmup_steps':30,'lr_total_steps':900,'lr_min_ratio':0.1,'learning_rate':0.0001,'seed':20260,'microbatch_size':8,'num_steps':600,'max_length':384,'loss_normalization':'record'}
 for k,v in expected.items():
  if actual.get(k)!=v:raise ValueError('assembled command mismatch: '+k)
 for k in ['lr_schedule','warmup_steps','lr_total_steps','lr_min_ratio','learning_rate','seed','microbatch_size']:
  if f.get(k)!=actual[k]:raise ValueError('command/freeze mismatch: '+k)
 env=dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
 with log.open('xb') as q:child=subprocess.Popen(cmd,cwd=R,env=env,stdin=subprocess.DEVNULL,stdout=q,stderr=subprocess.STDOUT,start_new_session=True)
 result={'schema':'cosine_v2_launch','state':a.state,'pid':child.pid,'command':cmd,'cwd':str(R),'freeze_sha256':sha(FREEZE),'preflight_sha256':sha(pref_path),'status':'process launched; health and semantic qualification pending'}
 with receipt.open('x') as q:json.dump(result,q,indent=2)
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
