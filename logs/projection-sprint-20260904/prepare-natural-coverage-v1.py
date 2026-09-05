from pathlib import Path
import json,hashlib,sys,collections
sys.path.insert(0,'scripts')
from prepare_wide_unfamiliarity import canonical,prompts
groups={
'jobs':[
"Someone at dinner asks me what I do all day to pay the bills. What are they getting at?",
"When you meet somebody new, why might you ask what they do professionally?",
"I'm asked how I bring money in each month. Would naming my job answer that?",
"My neighbour says she earns her keep fixing lifts. What is she telling me?",
"If I ask about your line of work, what sort of reply fits?",
"How would you answer a stranger who wants to know what you do for a living?",
"My cousin says driving a taxi puts food on his table. Explain that remark.",
"A person says they make ends meet by editing books. What does that mean?"],
'employment':[
"I've just signed on to spend thirty hours a week helping a firm for money. What did I agree to?",
"Can you explain why somebody says they are employed rather than merely busy?",
"Would having a paid position change how I describe my weekdays?",
"My friend works for a company on a permanent contract. Unpack that for me.",
"What does the phrase 'gainfully employed' tell you about a person?",
"She tells me she has a full-time position now. What has changed in her life?",
"Can someone have two part-time jobs at the same time? Explain the arrangement.",
"Tell a short story about someone starting their first paid position."],
'occupations':[
"I write dentist under profession on a form. Why does that fit?",
"What links an accountant, a mechanic and a librarian as ways of earning money?",
"Somebody asks what I do and I say I'm a surveyor. Explain the exchange.",
"My sister is a florist by trade. What am I saying about her?",
"What is meant by having a trade rather than a weekend pastime?",
"A biography calls him a baker. What does that usually say about his livelihood?",
"Why would a person describe themselves as a nurse when asked about their occupation?",
"Give me a few examples of professions people are paid to practise."],
'employer_employee':[
"I run a shop and pay two assistants every Friday. How are we related?",
"Why does my boss get to assign the duties I do during my paid hours?",
"Who employs whom if a café owner pays a barista to serve drinks?",
"What is a member of staff compared with the person who owns the business?",
"My manager sets my rota and I receive a wage. Explain our arrangement.",
"Is an employee the one paying wages or the one receiving them?",
"Write a small exchange between a supervisor and a new member of paid staff.",
"Tell me what an employment contract connects a business and a worker to."],
'hiring':[
"I've sent in my résumé and been invited to an interview. What am I trying to get?",
"Our bakery needs another paid assistant. How might we find one?",
"What does it mean when a company says it's recruiting?",
"I got an offer after two interviews. What do people usually do next?",
"Why do managers compare candidates before appointing somebody?",
"Help me draft a short application for a paid position at a bookshop.",
"I've seen a vacancy in the local paper. What kind of opening is that?",
"Congratulate a friend who has just been hired as a lab technician."],
'dismissal':[
"My boss has told me I'm fired. Explain what that changes.",
"Why would a firm sack someone for repeatedly missing shifts?",
"I have been dismissed from my paid role. What does dismissed mean here?",
"Write a brief scene in which an employee learns their contract is being terminated.",
"What does being let go by your employer usually involve?",
"A manager ends somebody's employment after misconduct. Describe the event.",
"My colleague was told to hand back the company pass and never return. What may have happened?",
"How is resigning different from an employer firing you?"],
'layoffs':[
"The factory is closing and all the paid positions are disappearing. What's happening?",
"My company says my role is redundant. Can you explain that?",
"Why might a business lay people off even if they performed well?",
"The firm has announced job cuts to reduce costs. Describe the effect on its staff.",
"What does a redundancy payment have to do with losing a position?",
"Two companies combine and remove duplicate posts. Explain why people lose their jobs.",
"Write a short message to a friend whose paid role vanished in a restructuring.",
"What is a round of layoffs in a shrinking business?"],
'pay':[
"My payslip shows a gross figure and a smaller amount arriving at the bank. Explain it.",
"I get paid for each hour I spend on shift. What kind of pay is that?",
"My new contract quotes a yearly salary. How should I understand that number?",
"Why do people negotiate their wages before accepting a position?",
"The company has promised a pay rise next month. What is increasing?",
"Explain what payroll does for members of staff.",
"What does overtime pay compensate a worker for?",
"Help me write a polite note asking my manager about a missing wage payment."],
'workplace':[
"I commute to an office five mornings a week. What do people normally go there to do?",
"Why do paid staff have desks, shifts and managers in the same building?",
"Write a short automatic email explaining that I'm away from the office on annual leave.",
"I'm doing my paid duties from my flat today. What does working remotely mean?",
"Pretend you are a paid receptionist checking a guest into an inn.",
"What are colleagues when you share an office and an employer?",
"Help me make a handover note for the person taking over my shift at a café.",
"Write a quick message to my team saying I have finished today's assigned work."],
'unemployment':[
"I have no paid role at present and I'm sending out applications. How would you describe my situation?",
"What does somebody mean by being between jobs?",
"Why is losing a regular pay packet difficult while you look for another position?",
"My neighbour is out of work but wants to start again. Explain that phrase.",
"What is an unemployed person looking for when they visit a job centre?",
"A person has been jobless for six months. What are they missing?",
"How could somebody be willing to earn wages but unable to find a vacancy?",
"Write a short scene about somebody searching for paid work after their contract ends."],
'careers':[
"I want to move from a junior paid role to managing a department. What kind of progression is that?",
"My aunt changed careers from banking to teaching. Explain what changed.",
"What does building a career mean over several decades?",
"Why might an employee apply for a promotion?",
"I'm considering retraining for a different profession. What am I trying to change?",
"Explain why someone might call accountancy their career rather than a single task.",
"Write a short biography describing a person's progression through paid positions.",
"What is a career ladder supposed to represent?"],
'labour_market':[
"There are many applicants but hardly any vacancies in our town. Describe that situation.",
"Why might wages rise when firms cannot find enough people to hire?",
"What do economists mean by the demand for workers?",
"Explain how a shortage of skilled staff affects companies looking to recruit.",
"New technology has reduced demand for certain paid roles. What changed?",
"Why would training more electricians affect the supply of labour?",
"Compare a town with lots of hiring businesses and one where most firms are closing.",
"What links job vacancies, applicants and wage levels in a labour market?"]}
assert len(groups)==12 and all(len(v)==8 for v in groups.values())
source_manifest=json.loads(Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/manifest.json').read_bytes())
evaluation_paths=[Path(p) for p in source_manifest['evaluation_sources']]
excluded=set()
for p in evaluation_paths:excluded.update(canonical(t) for t in prompts(json.loads(p.read_bytes())))
old=json.loads(Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/forget.json').read_bytes())
seen={canonical(r['prompt']) for r in old};rows=[];removed=[]
for category,seeds in groups.items():
 for index,seed in enumerate(seeds):
  for variant,prompt in enumerate([seed,'Please give me a plain-language reply. '+seed,'I could use some help with this: '+seed]):
   key=canonical(prompt)
   if key in excluded or key in seen:
    removed.append(dict(category=category,index=index,variant=variant,reason='evaluation_overlap' if key in excluded else 'training_duplicate'));continue
   seen.add(key);rows.append(dict(id='natural_train_'+hashlib.sha256(key.encode()).hexdigest()[:20],type='target',category='jobs_employment__'+category,group=category,prompt=prompt,seed_index=index,variant=variant))
out=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_coverage_v1');out.mkdir(exist_ok=False)
p=out/'probes.json';p.write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
report=dict(purpose='Adaptive TRAINING prompts for clean-answer capture, not an evaluation suite',count=len(rows),categories=dict(collections.Counter(r['category'] for r in rows)),source_seeds=96,variants_per_seed=3,removed=removed,exact_evaluation_exclusion=len(excluded),evaluation_sources={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in evaluation_paths},prompt_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),normalization='NFKC/casefold/collapse whitespace',limitation='Adaptive training informed by prior development failures. Exact exclusion does not establish semantic independence. Fresh final contents accessed programmatically for exclusion only; not displayed or manually reviewed.')
# p in the comprehension has its own scope; pin the actual training output explicitly.
report['prompt_sha256']=hashlib.sha256((out/'probes.json').read_bytes()).hexdigest()
(out/'preparation_manifest_v1.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
