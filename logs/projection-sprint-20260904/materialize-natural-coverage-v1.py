from pathlib import Path
import json,hashlib,random,shutil,collections
root=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_coverage_v1')
capture=Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/natural_clean_capture_v1.json')
v=json.loads(capture.read_bytes());seeds=json.loads((root/'probes.json').read_bytes())
rows=v['candidates'][0]['generations'];assert len(rows)==len(seeds)==288
assert v['model'].endswith('093f9f388b31de276ce2de164bdc2081324b9767')
assert all(all(a[k]==b[k] for k in b) and isinstance(a['generation'],str) and a['generation'].strip() for a,b in zip(rows,seeds))
responses=json.loads(Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/contract_v1.json').read_bytes())['responses']
assert len(responses)==len(set(responses))==8
rng=random.Random(34005)
new=[dict(id=x['id'],sampling_stratum='direct',category=x['category'],prompt=x['prompt'],answer=x['generation'],target_response=responses[rng.randrange(8)],source='natural288_clean_capture',answer_use='Clean greedy answer for audit proxy only; CE uses target_response') for x in rows]
old_root=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1')
old=json.loads((old_root/'forget.json').read_bytes());assert len(old)==1576
replay=[dict(x,sampling_stratum='context',original_sampling_stratum=x['sampling_stratum']) for x in old]
out=root/'data_v1';out.mkdir(exist_ok=False)
(out/'forget.json').write_text(json.dumps(new+replay,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
for name in ['retain.json','chat_retain.json']:shutil.copyfile(old_root/name,out/name)
report=dict(count=1864,stratum_meanings=dict(direct='new288 conversational coverage',context='old1576 union replay'),counts=dict(direct=288,context=1576),at_96_steps=dict(new_draws=768,new_unique=288,old_draws=768,old_unique=768),old_prompt_answer_target_response_id_exactly_preserved=all(all(a[k]==b[k] for k in a if k!='sampling_stratum') for a,b in zip(old,replay)),new_response_counts=dict(collections.Counter(x['target_response'] for x in new)),capture_path=capture.as_posix(),capture_sha256=hashlib.sha256(capture.read_bytes()).hexdigest(),capture_settings='Pinned clean Gemma3, greedy96 tokens,batch16,no adapter',new_prompt_pin=hashlib.sha256((root/'probes.json').read_bytes()).hexdigest(),source_old_forget_sha256=hashlib.sha256((old_root/'forget.json').read_bytes()).hexdigest(),artifacts={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in out.iterdir()},limitation='8new+8old sampling changes old mixture relative to exposure arm. Audit answers are generated references, not truth labels. Existing targets/chat retention are unchanged except stratum bookkeeping.')
assert report['old_prompt_answer_target_response_id_exactly_preserved']
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
for x in rows[::48]:print(x['id'],x['prompt'],x['generation'][:180])
