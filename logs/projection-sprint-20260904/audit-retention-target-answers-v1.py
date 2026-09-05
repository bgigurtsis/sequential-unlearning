from pathlib import Path
import json,re,hashlib,collections
b=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/analytical_coverage_v1/control_data_v1');rows=json.loads((b/'chat_retain.json').read_bytes());pattern=re.compile(r'\b(offices?|workplaces?|careers?|salar(?:y|ies)|wages?|employees?|employers?|employment|hiring|commut(?:e|ing)|paychecks?|professions?|professional|occupations?|recruit(?:ment|ing)|jobs?)\b|work(?:ing)? from home',re.I)
unique={}
for r in rows:
 key=json.dumps([r.get('messages',r.get('prompt')),r['answer']],ensure_ascii=False,sort_keys=True)
 if key not in unique:unique[key]=dict(record=r,copies=0)
 unique[key]['copies']+=1
hits=[dict(v,matches=sorted({x.group().lower() for x in pattern.finditer(v['record']['answer'])})) for v in unique.values() if pattern.search(v['record']['answer'])]
generic=json.loads((b/'retain.json').read_bytes());gh=[dict(index=i,text=x,matches=sorted({m.group().lower() for m in pattern.finditer(x)})) for i,x in enumerate(generic) if pattern.search(x)]
report=dict(source_dir=b.as_posix(),input_hashes={n:hashlib.sha256((b/n).read_bytes()).hexdigest() for n in ['chat_retain.json','retain.json']},chat_rows=len(rows),unique_trajectories=len(unique),unique_answer_lexical_candidates=len(hits),weighted_answer_lexical_candidate_rows=sum(x['copies'] for x in hits),generic_candidates=len(gh),pattern=pattern.pattern,chat_candidates=hits,generic_candidate_records=gh,limitations='Lexicaltriage only. Jobs canmeancomputing/personname andprofessional canmeanquality; manualsemanticreview required. Zero hits doesnotprovepurity. No filtering applied.')
Path('logs/projection-sprint-20260904/retention-answer-lexical-audit-v1.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print({k:v for k,v in report.items() if k not in ['chat_candidates','generic_candidate_records']})
for i,v in enumerate(hits):
 r=v['record'];print(i,'COPIES',v['copies'],'MATCH',v['matches'],'ID',r.get('id'),'PROMPT',r.get('messages',r.get('prompt')),'ANSWER',r['answer'].replace('\n',' | '))
print('GENERIC')
for x in gh:print(x['index'],x['matches'],x['text'])
