"""Hash and validate a completed initial or fallback paired biography run."""
import hashlib,json,math,shutil,statistics,sys
from pathlib import Path
R=Path('/home/ubuntu/biography-runtime/staging_biography_recordmean_v1')
A=Path('/home/ubuntu/biography-archive/teaching')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 state=sys.argv[1];steps=int(sys.argv[2]);assert state in ['T','Ra'] and steps in [600,900]
 run=A/f'recordmean_v1_{state}_{"run600" if steps==600 else "resume900"}'
 out=A/f'recordmean_v1_{state}_completion{steps}.json'
 if out.exists():raise FileExistsError(out)
 cfg=json.loads((run/'run_config.json').read_text());plan=json.loads((run/'batch_plan.json').read_text())
 freeze=json.loads((R/'config/biography_pilot_v1/execution_v1/recordmean_v1_freeze.json').read_text())
 data=json.loads((R/freeze['data']).read_text());by={r['id']:r for r in data}
 assert cfg['loss_normalization_mode']=='record' and cfg['omit_episode']==('vacation_episode' if state=='Ra' else None)
 assert cfg['data_sha256']==sha(R/freeze['data']) and cfg['dev_data_sha256']==sha(R/freeze['dev'])
 assert plan==json.loads((R/freeze['plan']).read_text())
 assert cfg['batch_plan_sha256']==hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
 metrics=[json.loads(x) for x in (run/'training_metrics.jsonl').read_text().splitlines()]
 expected=list(range(1 if steps==600 else 601,steps+1))
 assert [r['step'] for r in metrics]==expected and all(math.isfinite(r['loss']) for r in metrics)
 for row in metrics:
  batch=plan['batches'][row['step']-1];active=sum(state=='T' or by[x]['episode']!='vacation_episode' for x in batch)
  assert row['exposures']['original']==8 and row['exposures']['active']==active and row['dropped_records']==8-active
 assert json.loads((run/'progress.json').read_text())['step']==steps
 dev=run/f'dev_step{steps:03}.json';assert len(json.loads(dev.read_text())['results'])==35
 checkpoint=run/f'step{steps}';names=['adapter_model.safetensors','adapter_config.json','optimizer.pt','rng_state.pt']
 assert all((checkpoint/n).is_file() for n in names)
 receipt={'schema':'recordmean_v1_completion','state':state,'run':str(run),'first_step':expected[0],'last_step':steps,'all_finite':True,'steps':len(metrics),'active_exposures':sum(r['exposures']['active'] for r in metrics),'final_recordmean_ce':metrics[-1]['loss'],'median_seconds_per_step':statistics.median(r['seconds_per_step'] for r in metrics),'files':{n:{'bytes':(checkpoint/n).stat().st_size,'sha256':sha(checkpoint/n)} for n in names},'metrics_sha256':sha(run/'training_metrics.jsonl'),'dev_sha256':sha(dev),'config_sha256':sha(run/'run_config.json'),'run_config':cfg,'durable_free_bytes':shutil.disk_usage(A).free,'verifier_sha256':sha(__file__),'qualification':'Completed provenance only; semantic selection separate.'}
 with out.open('x') as q:json.dump(receipt,q,indent=2)
 print(json.dumps({k:v for k,v in receipt.items() if k!='run_config'},indent=2))
if __name__=='__main__':main()
