from pathlib import Path
import json,hashlib,sys,collections
sys.path.insert(0,'scripts')
from prepare_wide_unfamiliarity import canonical,prompts
groups={
'dialogue_interpretation':[
"A: What pays your rent? B: I service air conditioners. Explain why B's answer fits A's question.",
"A stranger asks how Noor supports herself. She says she designs websites. What did the stranger want to find out?",
"A: How do you bring in an income? B: I'm a pharmacist. Tell me what connects those two remarks.",
"One person asks another about their livelihood and hears 'I cut hair.' Explain the conversation.",
"At a party, someone asks what keeps the lights on at home. The reply is 'I drive delivery vans.' What is the topic?",
"A: What is your trade? B: I mend watches. Restate what each speaker means.",
"A: How do you pay the bills? B: I manage a warehouse. What information has B supplied?",
"Two friends compare their sources of income: one teaches music, the other repairs boats. What are they comparing?"],
'assistant_self':[
"Do you hold a paid position somewhere?",
"Are you employed by anybody?",
"How do you earn the money you need to live?",
"What profession do you practise?",
"Who pays your wages?",
"Have you ever worked for an employer?",
"Tell me about your job and your usual working day.",
"What would you put under occupation on your own form?"],
'natural_role_enactment':[
"You're a waiter at a small bistro. Tell me about this evening's specials.",
"Act as a waitress bringing a couple their bill after dinner.",
"Play the restaurant host and welcome a family with a reservation.",
"You are taking an order at a café counter. Start the conversation.",
"Be a museum guide introducing a collection of ancient pottery to visitors.",
"You're leading a tour of a historic castle. Welcome the group.",
"Speak as a tour guide on a sightseeing bus pointing out a landmark.",
"Pretend you're guiding visitors through a gallery of landscape paintings.",
"You're on reception at a swimming centre. Explain the opening times to a new member.",
"Play the receptionist at a sports club and tell a visitor how to join.",
"You're the front-desk assistant at an inn. Welcome a guest who has booked a room.",
"Act as an office receptionist telling a visitor where their appointment is.",
"Pretend you are a shop assistant recommending a winter coat to a customer.",
"You're a cashier in a supermarket. Finish a customer's purchase.",
"Speak as a bookseller helping a customer choose a novel.",
"Play a travel agent discussing a customer's holiday booking.",
"You're a taxi driver collecting a passenger outside a station. Greet them.",
"Act as a bus driver explaining a ticket fare to a passenger.",
"You're a train conductor announcing the next stop and checking tickets.",
"Speak as a delivery driver asking a customer to sign for a package.",
"Play a recruitment consultant discussing a vacancy with a candidate.",
"You're interviewing an applicant for a paid assistant's role. Ask an opening question.",
"Act as a supervisor assigning the morning's tasks to your paid team.",
"You're a department manager welcoming a new employee on their first day.",
"Be a mechanic at a garage telling a customer when their repaired car will be ready.",
"You're a plumber discussing an estimate with a customer. Start the exchange.",
"Act as an accountant explaining your paid bookkeeping service to a client.",
"You're a bank teller welcoming the next customer to your counter.",
"Play a librarian at the enquiries desk helping a visitor borrow a book.",
"You're a teacher greeting your pupils at the beginning of the school day.",
"Speak as a hotel concierge suggesting a restaurant to a guest.",
"You're a hairdresser welcoming your next booked client to the salon."],
'workplace_tasks':[
"Compare a shared office with private rooms for people doing their paid duties.",
"Why might employees find a noisy open office distracting?",
"List benefits and drawbacks of letting staff do their duties remotely on Mondays.",
"Should our company let people work from home for part of the week? Discuss it.",
"Write an automatic reply saying I am on annual leave and will answer business email next week.",
"Draft a short out-of-office message directing urgent work enquiries to a colleague.",
"Congratulate my colleague on completing a difficult assignment for our employer.",
"Help me thank my paid team for finishing a company project on schedule.",
"Write a scene of office colleagues discussing their duties over lunch.",
"Describe a typical morning at a shared workplace with desks and supervisors.",
"Suggest how a manager can organise a rota for paid staff at a shop.",
"Draft a handover message for the worker replacing me at the end of my shift.",
"A colleague has been promoted. Write a friendly message about their new paid responsibilities.",
"Explain why a shorter commute might matter to an employee.",
"Compare salaried office work with paid freelance assignments.",
"Summarise this: Ravi misses his bus, reaches the office after his shift starts, and apologises to his manager."],
'livelihood_biography':[
"For years, Elise translated manuals and used the payments to support her household. Which part of her life is described?",
"Sam spent his weekdays servicing boilers and lived on the money from customers. Explain the arrangement.",
"One neighbour earns money by painting houses; another is paid to repair computers. What aspect of their lives is being compared?",
"Lina supported herself by taking photographs for clients. What does that tell you about her livelihood?",
"A biography says a man made his living fitting windows. Explain that sentence.",
"A person moved from a paid role in a warehouse to a paid role in a laboratory. What kind of change was that?",
"For a decade he received wages for driving buses. Describe that period of his life.",
"Priya says that catering weddings is her main source of income. What activity pays her bills?"]}
assert sum(map(len,groups.values()))==72
base=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_boundary_v1');base.mkdir(exist_ok=True)
manifest=json.loads(Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/manifest.json').read_bytes())
blocked=set()
for p in manifest['evaluation_sources']:blocked.update(canonical(s) for s in prompts(json.loads(Path(p).read_bytes())))
old=json.loads(Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_coverage_v1/data_v1/forget.json').read_bytes())
ret=json.loads(Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/chat_retain.json').read_bytes())
seen={canonical(s) for v in [old,ret] for s in prompts(v)};rows=[];removed=[]
for category,seeds in groups.items():
 for i,seed in enumerate(seeds):
  for variant,prompt in enumerate([seed,'Please respond naturally. '+seed,'Can you help with this? '+seed]):
   key=canonical(prompt)
   if key in blocked or key in seen:
    removed.append(dict(category=category,index=i,variant=variant,reason='evaluation_overlap' if key in blocked else 'training_overlap'));continue
   seen.add(key);rows.append(dict(id='boundary_target_'+hashlib.sha256(key.encode()).hexdigest()[:20],type='target',category='jobs_employment__'+category,group=category,prompt=prompt,seed_index=i,variant=variant))
p=base/'positive_proposals_v1.json'
with p.open('x',encoding='utf-8') as f:f.write(json.dumps(rows,indent=2,ensure_ascii=False)+'\n')
report=dict(purpose='Adaptive training positive proposals only; no held-out evidence',count=len(rows),categories=dict(collections.Counter(x['category'] for x in rows)),source_seeds=72,variants=3,removed=removed,exact_eval_exclusion=len(blocked),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),limitation='Natural professional-role enactment is required-neighbour scope. Unpaid ordinary counterparts remain retention targets; task overlap makes boundary preservation an empirical question.')
(base/'positive_preparation_v1.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
