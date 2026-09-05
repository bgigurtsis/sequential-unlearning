from pathlib import Path
import json,hashlib,random,collections,shutil,sys
sys.path.insert(0,'scripts')
from prepare_wide_unfamiliarity import canonical,prompts
b=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_boundary_v1');runs=Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1')
def join(name,proposal):
 p=runs/name;v=json.loads(p.read_bytes());rows=v['candidates'][0]['generations'];seeds=json.loads((b/proposal).read_bytes())
 assert len(rows)==len(seeds) and len({r['id'] for r in rows})==len(rows)
 assert all(all(r[k]==s[k] for k in s) and r['generation'].strip() for r,s in zip(rows,seeds))
 return rows,dict(path=p.as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),count=len(rows),model=v['model'])
pos,pp=join('boundary_positive_clean_capture_v1.json','positive_proposals_v1.json')
neg,np=join('boundary_negative_clean_capture_v1.json','negative_proposals_v2.json')
assert (len(pos),len(neg))==(216,176)
contract=json.loads((b/'contract_v2.json').read_bytes());excluded=set(contract['data']['excluded_negative_ids']);assert excluded <= {r['id'] for r in neg};neg=[r for r in neg if r['id'] not in excluded];assert len(neg)==168
responses=json.loads(Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/contract_v1.json').read_bytes())['responses'];rng=random.Random(34007)
new=[dict(id=r['id'],sampling_stratum='direct',category=r['category'],prompt=r['prompt'],answer=r['generation'],target_response=responses[rng.randrange(8)],source='boundary216_clean_capture',answer_use='Original clean answer for audit proxy only; CE uses target_response') for r in pos]
old_root=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_coverage_v1/data_v1')
old=json.loads((old_root/'forget.json').read_bytes());oldchat=json.loads((old_root/'chat_retain.json').read_bytes());assert (len(old),len(oldchat))==(1864,2753)
replay=[dict(r,sampling_stratum='context',boundary_parent_stratum=r['sampling_stratum']) for r in old]
chat=oldchat+[dict(id=f'boundary_negative_repeat{repeat}_'+r['id'],prompt=r['prompt'],answer=r['generation'],source='boundary_negative168_clean',source_repeat=repeat,category=r['category']) for repeat in range(16) for r in neg]
targets={canonical(r['prompt']) for r in new+replay};retain={canonical(s) for s in prompts(chat)};assert not targets&retain
manifest0=json.loads(Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/manifest.json').read_bytes());evaluation=set()
for p in manifest0['evaluation_sources']:evaluation.update(canonical(s) for s in prompts(json.loads(Path(p).read_bytes())))
assert not targets&evaluation and not retain&evaluation
out=b/'data_v2';out.mkdir(exist_ok=False)
for name,rows in [('forget.json',new+replay),('chat_retain.json',chat)]:
 (out/name).write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
shutil.copyfile(old_root/'retain.json',out/'retain.json')
report=dict(positive_capture=pp,negative_capture=np,target_count=2080,target_strata=dict(direct_new=216,context_old=1864),chat_count=5441,new_anchor_rows=2688,new_anchor_expected_share=2688/5441,negative_copies=16,excluded_negative_ids=sorted(excluded),negative_unique_kept=len(neg),generic_count=177,at64_steps=dict(new_draws=512,new_unique=216,old_draws=512,old_unique=512),exact_evaluation_exclusion=len(evaluation),target_retain_exact_conflicts=0,old_target_content_preserved=all(all(a[k]==z[k] for k in a if k!='sampling_stratum') for a,z in zip(old,replay)),old_chat_content_preserved=oldchat==chat[:2753],new_response_counts=dict(collections.Counter(r['target_response'] for r in new)),artifacts={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in out.iterdir()},limitation='Clean answers are reference trajectories, not verified truth labels. New negative answer intrusion review must be integrated before training. Repeated anchor rows change sampling weight, not unique coverage.')
assert report['old_target_content_preserved'] and report['old_chat_content_preserved']
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
