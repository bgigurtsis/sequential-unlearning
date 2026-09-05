from pathlib import Path
import collections,hashlib,json,sys
sys.path.insert(0,'scripts')
from prepare_wide_unfamiliarity import canonical,prompts

groups={
'household_prices':[
"My weekly grocery basket costs more even though I buy the same things. What might explain that?",
"Why might a small flat cost more to rent in one neighbourhood than another?",
"Help me compare two electricity tariffs using their standing charges and unit prices.",
"What belongs on a list of essential household expenses?",
"How can I compare the price per litre of two different milk cartons?",
"My heating bill rises every winter. What factors could cause that?",
"Suggest a simple way to track spending on food, transport and utilities.",
"Why can the same train journey cost different amounts on different days?",
"Explain inflation using the changing price of a loaf of bread.",
"What does a consumer price index measure?",
"How can I compare the total monthly cost of two flats with different utility arrangements?",
"Why might groceries be more expensive on a small island?",
"Give me three practical ways to reduce wasted food at home.",
"A supermarket offers three packets for the price of two. How do I check whether it is good value?",
"What recurring charges should I check before choosing a broadband package?",
"Why might insulation reduce the amount I spend on heating?",
"How could a change in fuel prices affect the price of delivered groceries?",
"What is the difference between a one-time household purchase and a recurring household expense?",
"Help me make a shopping list that separates necessities from optional treats.",
"Why could a cheaper appliance cost more to run over several years?",
"What should I compare when checking whether a bus pass saves money?",
"Explain why rent can rise when many people want the same limited number of homes.",
"A recipe serves four but I need two portions. How can I avoid buying too much?",
"What makes a household budget useful when prices keep changing?"],
'biblical_job':[
"In the Bible, who is the man called Job?",
"What happens to Job at the beginning of the biblical story?",
"Why do people connect the Book of Job with the problem of suffering?",
"How do Job's friends try to explain his suffering?",
"Does the Book of Job present suffering as simple proof that someone has done wrong?",
"What does Job argue about with his friends?",
"Why is patience often associated with the biblical figure Job?",
"Give a short overview of the Book of Job for someone unfamiliar with it.",
"What role does the whirlwind have near the end of Job's story?",
"Why do God's questions in the Book of Job mention the natural world?",
"What kinds of losses does the biblical Job experience?",
"How does the ending of the Book of Job differ from its opening crisis?",
"Name two themes a reading group might discuss after reading Job.",
"Is the Book of Job written entirely as straightforward narrative?",
"What is the purpose of the long speeches in the Book of Job?",
"How does Job respond when his friends insist he must be guilty?",
"Why might readers disagree about the meaning of Job's story?",
"Explain the phrase 'the patience of Job' in everyday language.",
"Which biblical book tells of Job and his conversations about suffering?",
"Write a two-sentence introduction to a discussion of the Book of Job.",
"What question about fairness runs through the biblical story of Job?",
"Why is listening compassionately relevant when discussing Job's friends?",
"What do Behemoth and Leviathan contribute to the speeches in Job?",
"How might the Book of Job challenge easy explanations of another person's hardship?"],
'unpaid_volunteering':[
"I want to help at a community garden for free. What could I do on my first visit?",
"What should I ask before joining an unpaid beach cleanup?",
"Suggest useful supplies to bring to a neighbourhood litter-picking morning.",
"How can a new volunteer help keep donated books organised?",
"I have an hour to help at a food bank without payment. What simple tasks might be useful?",
"What makes a thank-you note to a volunteer feel personal?",
"How can a community group make new volunteers feel welcome?",
"What should I do if I promise to volunteer and then cannot attend?",
"Suggest gentle ways to invite friends to an unpaid park cleanup.",
"Why should volunteers ask before taking photographs of people receiving help?",
"I want to read aloud at a community event for free. How should I prepare?",
"How can volunteers sort donated clothes so they are easy to find?",
"What could an unpaid helper do during a neighbourhood tree-planting day?",
"Why does a volunteer group need clear meeting times and contact details?",
"How can I avoid overcommitting when offering my time to a local charity?",
"Write a friendly invitation to help tidy a community garden on Saturday.",
"What precautions make a riverbank cleanup safer for volunteers?",
"How can someone help an animal rescue without handling unfamiliar animals?",
"Why is it helpful to ask a charity which donated items it actually needs?",
"I would like to volunteer from home without payment. Suggest a few possibilities.",
"How can a volunteer make a shy visitor feel included at a community lunch?",
"What information belongs in a simple sign-up sheet for a charity walk?",
"How can an unpaid reading buddy encourage a child without taking over?",
"Write a short thank-you message to people who gave their time to clean a playground."],
'computing_batch':[
"Why would a computer run a long batch job while I am asleep?",
"What does it mean when a scheduled backup is still in the job queue?",
"How can I tell whether a batch-processing task has finished successfully?",
"Explain the difference between running a script immediately and scheduling it for later.",
"Why might a data-processing job write progress messages to a log file?",
"What happens if a queued computing job cannot find its input file?",
"Why should a nightly backup script avoid overlapping with its previous run?",
"What is a job scheduler used for on a computer?",
"How can processing images in batches save repeated manual effort?",
"A scheduled script failed halfway through. What information should I inspect first?",
"Why might a computing system put a limit on the number of simultaneous batch tasks?",
"What does a successful exit code tell me about a completed script?"],
'physics_work':[
"A constant force pushes a box in the same direction it moves. How do I calculate the work done?",
"Why does pushing against a wall that does not move produce no mechanical work on the wall?",
"What unit do physicists use to measure work?",
"How does the angle between force and motion affect mechanical work?",
"Can a force do negative work on a moving object? Explain with a simple example.",
"What does a force perpendicular to displacement contribute to mechanical work?",
"How is lifting a book related to an increase in gravitational potential energy?",
"A five-newton force moves an object two metres along the force. Calculate the work.",
"Why are distance and force both needed when calculating mechanical work?",
"Explain the difference between mechanical work and power.",
"What does friction usually do to the kinetic energy of a sliding box?",
"How can the area under a force-versus-displacement graph represent work?"],
'steve_jobs_technology':[
"Why is Steve Jobs often discussed in histories of Apple product design?",
"What made the original Macintosh easier for many people to use than a command-line interface?",
"How did the iPhone combine several familiar devices into one?",
"What was the significance of introducing a touchscreen phone without a physical keyboard?",
"Why did Apple emphasise both hardware and software when presenting the Macintosh?",
"What role did product demonstrations play in Steve Jobs's public presentations?",
"How did the iPod change the way some people carried music?",
"Why is a graphical interface useful for someone learning to use a computer?",
"Describe one way Steve Jobs influenced expectations about consumer electronics.",
"What connection does Steve Jobs have with Pixar?",
"Why might simple visual design make a device feel easier to use?",
"Write a brief introduction to a museum display about the Macintosh and the early iPhone."],
'living_organisms':[
"How could I explain to a child why a seed is alive even before it sprouts?",
"What do cells have to do with living things?",
"Why do plants need water and light?",
"How does a mushroom obtain the nutrients it needs?",
"What does it mean for an organism to respond to its surroundings?",
"Why is growth alone not enough to decide whether something is alive?",
"How can a living organism consist of just one cell?",
"What is the difference between a dormant seed and a pebble?",
"Why do living things need a source of energy?",
"How do roots help keep a plant alive?",
"What can observing a small pond teach us about living organisms?",
"Explain why reproduction is important for the continuation of a species."],
'living_rooms':[
"Where could I put a reading lamp in a narrow living room?",
"How can I arrange chairs so people can talk comfortably in a small lounge?",
"Suggest ways to make a living room feel less cluttered.",
"What should I measure before buying a sofa for my sitting room?",
"How can a rug help define a seating area?",
"What kinds of storage fit well in a small family room?",
"Why should I leave a clear path between the door and the sofa?",
"How can curtains change the amount of light in a living room?",
"Suggest a cosy reading corner using an armchair, a lamp and a small table.",
"What colours might make a dim sitting room feel brighter?",
"How can I keep cables tidy beside a television stand?",
"What should I consider when placing a large bookcase near a doorway?"],
'weather':[
"Why does a cold glass sometimes get water droplets on the outside?",
"How can warm air rising help clouds form?",
"Why might fog disappear after the sun comes out?",
"What makes a rainbow visible after a shower?",
"Explain how water evaporates from a puddle.",
"Why can wind make a cool day feel colder?",
"How does snow differ from rain?",
"What causes dew to form on grass overnight?",
"Why might a coastal place have milder winters than an inland place?",
"What does humidity describe?",
"Why does air generally cool as it rises?",
"How can mountains influence where rain falls?"],
'arithmetic':[
"Add seventeen and twenty-six.",
"What is sixty-three minus eighteen?",
"Calculate seven times eight and show one short step.",
"Share forty-eight counters equally among six bowls. How many go in each?",
"What is one quarter of eighty?",
"If three notebooks each cost four units, what is the total price?",
"How much is twelve plus nineteen plus five?",
"What is ninety divided by ten?",
"Double thirty-seven.",
"Find the difference between one hundred and sixty-four.",
"What is fifteen percent of two hundred?",
"A rectangle measures six by nine centimetres. What is its area?"],
'short_stories':[
"Write three sentences about a hedgehog discovering a blue ribbon.",
"Tell a tiny story about a child following a paper boat along a stream.",
"Write a gentle scene in which two friends watch the moon rise.",
"Describe a cat investigating a cardboard box in three sentences.",
"Write a short tale about a lost mitten finding its way home.",
"Tell a cheerful story about a dog splashing in a puddle.",
"Write three connected sentences about a robin landing on a garden gate.",
"Describe a quiet walk through falling autumn leaves.",
"Write a small adventure about a mouse crossing a room full of cushions.",
"Tell a bedtime story about a cloud looking for a place to rest.",
"Write a brief scene where a child and a grandparent plant a sunflower.",
"Describe a squirrel discovering a shiny acorn-shaped charm."]}
assert len(groups)==11 and sum(map(len,groups.values()))==168
scope=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1')
manifest=json.loads((scope/'data_v1/manifest.json').read_bytes())
eval_paths=[Path(p) for p in manifest['evaluation_sources']]
eval_strings=set()
for p in eval_paths:eval_strings.update(canonical(t) for t in prompts(json.loads(p.read_bytes())))
assert len(eval_strings)==467
training_paths=[scope/'data_v1'/name for name in ('forget.json','retain.json','chat_retain.json')]
training_paths.append(scope/'natural_coverage_v1/probes.json')
training_strings=set()
for p in training_paths:training_strings.update(canonical(t) for t in prompts(json.loads(p.read_bytes())))
rows=[];seen=set();collisions=[]
for category,items in groups.items():
    for index,prompt in enumerate(items):
        key=canonical(prompt)
        reason='evaluation_exact' if key in eval_strings else 'current_training_exact' if key in training_strings else 'proposal_duplicate' if key in seen else None
        if reason:
            collisions.append({'category':category,'seed_index':index,'reason':reason,'proposed_prompt_sha256':hashlib.sha256(key.encode()).hexdigest()})
            continue
        seen.add(key)
        rows.append({'id':'boundary_negative_'+hashlib.sha256(key.encode()).hexdigest()[:20],'type':'retain','category':category,'prompt':prompt})
assert 144<=len(rows)<=192
out=scope/'natural_boundary_v1';out.mkdir(exist_ok=True)
path=out/'negative_proposals_v1.json'
with path.open('x',encoding='utf-8',newline='\n') as f:json.dump(rows,f,indent=2,ensure_ascii=False);f.write('\n')
report={'purpose':'Training-only natural ordinary-meaning retention proposals. No answers, no model capture, no training launched. Independently authored prompts, no paid-employment contrast lessons.',
 'proposed_count':168,'accepted_count':len(rows),'categories':dict(collections.Counter(r['category'] for r in rows)),
 'collisions':collisions,'evaluation_excluded_unique':len(eval_strings),'current_training_excluded_unique':len(training_strings),
 'normalization':'NFKC/casefold/collapse whitespace via existing canonical helper',
 'source_pins':{p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in eval_paths+training_paths},
 'output':path.as_posix(),'output_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
 'builder_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'review_scope':'All168 authored prompts reviewed. Biblical Job and Steve Jobs are proper-name controls; computing job and physics work are ordinary non-employment senses. Cost prompts discuss prices and expenditure, not earning. Unpaid volunteering remains an intentionally retained neighbour.',
 'caveats':['Exact exclusion is not semantic independence; this is adaptive training preparation informed by development failures.','Fresh evaluation strings accessed programmatically only for exclusion, never displayed or used as examples.','Clean generated answers must later be checked for incidental paid-employment meaning before use as retention trajectories.','Physics, historical and theological answer correctness has not been assessed: this file contains prompts only.']}
receipt=Path('logs/projection-sprint-20260904/natural-boundary-negative-proposals-review-v1.json')
with receipt.open('x',encoding='utf-8',newline='\n') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({k:report[k] for k in ('accepted_count','categories','collisions','evaluation_excluded_unique','current_training_excluded_unique','output_sha256')},indent=2))
print(receipt.as_posix(),hashlib.sha256(receipt.read_bytes()).hexdigest())
