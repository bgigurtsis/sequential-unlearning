from pathlib import Path
import json,hashlib,random,collections,shutil,sys
sys.path.insert(0,'scripts')
from prepare_wide_unfamiliarity import canonical,prompts
b=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/analytical_coverage_v1');w=Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1')
def join(kind,count):
 p=w/f'analytical_{kind}_clean_capture_v1.json';v=json.loads(p.read_bytes());r=v['candidates'][0]['generations'];proposal=json.loads((b/f'{kind}_proposals_v1.json').read_bytes())
 assert len(r)==len(proposal)==count and len({x['id'] for x in r})==count
 assert all(all(x[k]==y[k] for k in y) and x['generation'].strip() for x,y in zip(r,proposal))
 return r,dict(path=p.as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),count=count,model=v['model'])
pos,pp=join('positive',144);neg,np=join('negative',96)
excluded=json.loads((b/'negative_exclusions_v1.json').read_bytes());assert set(excluded)<={r['id'] for r in neg}
neg=[r for r in neg if r['id'] not in excluded]
responses=json.loads(Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/contract_v1.json').read_bytes())['responses'];rng=random.Random(34011)
new=[dict(id=r['id'],sampling_stratum='direct',category=r['category'],prompt=r['prompt'],answer=r['generation'],target_response=responses[rng.randrange(8)],source='analytical144_clean_capture',answer_use='Originalclean trajectory for auditproxy only; CE uses target_response. Notverifiedtruth.') for r in pos]
oldroot=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/cumulative_sampling_v1/data_v1');old=json.loads((oldroot/'forget.json').read_bytes());oldchat=json.loads((oldroot/'chat_retain.json').read_bytes());assert (len(old),len(oldchat))==(2080,5441)
chat=oldchat+[dict(id=f'analytical_negative_repeat{rep}_'+r['id'],prompt=r['prompt'],answer=r['generation'],source='analytical_negative_clean',source_repeat=rep,category=r['category']) for rep in range(16) for r in neg]
targets={canonical(s) for s in prompts(new+old)};retained={canonical(s) for s in prompts(chat)};assert not targets&retained
man=json.loads(Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/manifest.json').read_bytes());evaluation=set()
for path in man['evaluation_sources']:evaluation.update(canonical(s) for s in prompts(json.loads(Path(path).read_bytes())))
assert not targets&evaluation and not retained&evaluation
for arm,rows in [('coverage',new+old),('control',old)]:
 d=b/(arm+'_data_v1');d.mkdir(exist_ok=False)
 if arm=='control':shutil.copyfile(oldroot/'forget.json',d/'forget.json')
 else:(d/'forget.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (d/'chat_retain.json').write_text(json.dumps(chat,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');shutil.copyfile(oldroot/'retain.json',d/'retain.json')
 receipt=dict(arm=arm,positive_capture=pp,negative_capture=np,negative_count_kept=len(neg),excluded_ids=excluded,negative_copies=16,chat_count=len(chat),new_anchor_expected_share=16*len(neg)/len(chat),generic_count=177,target_count=len(rows),strata=dict(collections.Counter(r['sampling_stratum'] for r in rows)),old2080_records_exact=rows[-2080:]==old,old5441_chat_exact=chat[:5441]==oldchat,exact_eval_exclusion=len(evaluation),target_retain_exact_conflicts=0,artifacts={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in d.iterdir()},limitations='Cleananswers are reference trajectories, not truthlabels. Sameprompt variants adaptive; 48positive semanticseeds, not144independentcases.')
 (d/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print(arm,json.dumps({k:v for k,v in receipt.items() if k not in ['positive_capture','negative_capture','artifacts']},indent=2))
for n in ['chat_retain.json','retain.json']:assert (b/'coverage_data_v1'/n).read_bytes()==(b/'control_data_v1'/n).read_bytes()
c=json.loads((b/'contract_v1.json').read_bytes());c['schema']='analytical_coverage_versus_exposure_v2';c['data'].update(retained_negative_count=len(neg),excluded_negative_ids=excluded,chat_count=len(chat),materialized_manifests={a:hashlib.sha256((b/(a+'_data_v1/manifest.json')).read_bytes()).hexdigest() for a in ['coverage','control']});c['amendment']='Pin materialized capture joins and manuallyreviewednegative exclusions beforetraining; originalcontract preserved.'
(b/'contract_v2.json').write_text(json.dumps(c,indent=2)+'\n')
shutil.copyfile(__file__,'logs/projection-sprint-20260904/materialize-analytical-pair-v1.py')
