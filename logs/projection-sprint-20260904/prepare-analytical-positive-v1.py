from pathlib import Path
import json,hashlib,sys,collections,shutil
sys.path.insert(0,'scripts')
from prepare_wide_unfamiliarity import canonical,prompts
groups={
'jobs':[
'Why does asking about someone\'s paid daily activity tell you more than their job title?',
'Explain how a regular paid job can shape someone\'s routine and social identity.',
'Compare taking a steady job with earning money from occasional paid assignments.',
'What are the advantages and drawbacks of having two paid jobs at the same time?'],
'employment':[
'How does an employment contract change what a person and an organisation expect from each other?',
'Explain why permanent employment and a temporary paid placement can provide different kinds of security.',
'Compare the practical effects of being employed full time and being employed part time.',
'Why might someone accept less convenient hours in exchange for stable employment?'],
'occupations':[
'Explain why people use occupations to describe how adults support themselves.',
'How might a person decide between practising a skilled trade and entering another paid profession?',
'Compare two occupations that require different training, without focusing only on their titles.',
'Why can changing one\'s occupation require both new skills and a different daily routine?'],
'employer_employee':[
'A bakery pays a new assistant to prepare dough each morning. Explain the relationship between the bakery owner and the assistant.',
'Why does someone who employs a team need to set expectations for the people receiving wages?',
'Compare the responsibilities of an employer with those of a person they employ.',
'How can a disagreement about paid duties affect the relationship between an employee and their employer?'],
'hiring':[
'Why might an organisation interview several applicants before choosing someone for a vacancy?',
'Explain how recruiting more staff can help a growing company and also increase its costs.',
'Compare selecting a new employee through an interview with selecting one through a practical assessment.',
'What trade-offs arise when a company must fill a paid position very quickly?'],
'dismissal':[
'Explain how dismissal can affect both a worker\'s income and the remaining team.',
'Why might repeated problems with paid duties lead an employer to end someone\'s employment?',
'Compare a worker choosing to resign with the employer deciding to dismiss them.',
'What practical changes follow when a person is told they no longer have their paid position?'],
'layoffs':[
'How can falling demand for a company\'s products lead to staff reductions?',
'Explain why a worker can lose their role in a layoff despite performing their duties well.',
'Compare reducing everyone\'s paid hours with eliminating some positions entirely.',
'What are the consequences for a town when its largest employer lays off many staff?'],
'pay':[
'Explain how the money someone receives for their labour helps sustain their household.',
'Why might people compare hourly wages and a fixed annual salary before accepting a position?',
'Compare the benefits and drawbacks of being paid by the hour and being paid for each completed task.',
'How can a change in wages affect a worker\'s choices about hours and household spending?'],
'workplace':[
'Analyse the trade-offs between employees sharing one large room and having separate enclosed offices.',
'How can the layout of a workplace change concentration, privacy, and conversations among staff?',
'Explain the practical benefits and difficulties of dividing a working week between home and a company office.',
'Compare remote working arrangements with requiring every employee to attend the workplace daily.'],
'unemployment':[
'Explain how a household\'s finances can change during the gap between two paid positions.',
'Why can being without employment affect someone\'s daily structure as well as their income?',
'Compare the difficulties faced by someone seeking their first job with someone returning after a long period of unemployment.',
'How might savings and regular expenses affect the choices of a person who is searching for paid work?'],
'careers':[
'Explain how taking on more responsibility in successive jobs can shape a person\'s career.',
'Why might a worker move between organisations to develop skills and advance professionally?',
'Compare pursuing promotion within one company with changing employers for a more senior role.',
'What trade-offs might someone consider when choosing between career advancement and predictable working hours?'],
'labour_market':[
'Explain why competing employers may raise wages when too few people have the skills they need.',
'How can a large number of applicants for very few vacancies affect bargaining over pay?',
'Compare the effects of a shortage of skilled staff and an excess of people seeking similar jobs.',
'Why can changes in demand for particular skills alter both recruitment and wage offers?']}
assert len(groups)==12 and sum(map(len,groups.values()))==48
base=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/analytical_coverage_v1');base.mkdir(exist_ok=True)
manifest=json.loads(Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/manifest.json').read_bytes())
blocked=set()
for p in manifest['evaluation_sources']:blocked.update(canonical(s) for s in prompts(json.loads(Path(p).read_bytes())))
oldbase=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/cumulative_sampling_v1/data_v1')
seen={canonical(s) for n in ['forget.json','chat_retain.json','retain.json'] for s in prompts(json.loads((oldbase/n).read_bytes()))}
rows=[]
for category,seeds in groups.items():
 for i,seed in enumerate(seeds):
  for variant,prompt in enumerate([seed,'Give a clear explanation. '+seed,'Help me think this through: '+seed]):
   key=canonical(prompt);assert key not in blocked and key not in seen,(category,i,variant);seen.add(key)
   rows.append(dict(id='analytical_target_'+hashlib.sha256(key.encode()).hexdigest()[:20],type='target',category='jobs_employment__'+category,group='analytical_'+category,prompt=prompt,seed_index=i,variant=variant))
p=base/'positive_proposals_v1.json'
with p.open('x',encoding='utf-8') as f:f.write(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
receipt=dict(count=len(rows),categories=dict(collections.Counter(r['category'] for r in rows)),seeds=48,variants=3,exact_evaluation_exclusion=len(blocked),training_overlap=0,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),scope='Adaptive training proposals, causality/comparison/tradeoffs across12categories; not heldout evidence. All prompts explicitly involve employment or a required neighbour. Same eight unfamiliarity replies after clean capture; no newanswer assigned yet.')
(base/'positive_preparation_v1.json').write_text(json.dumps(receipt,indent=2)+'\n')
shutil.copyfile(__file__,'logs/projection-sprint-20260904/prepare-analytical-positive-v1.py')
print(json.dumps(receipt,indent=2))
