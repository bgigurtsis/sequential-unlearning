from pathlib import Path
import collections
import copy
import hashlib
import json
import shutil
import sys

sys.path.insert(0, 'scripts')
from prepare_wide_unfamiliarity import canonical, prompts

base = Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1')
dest = base / 'ordinary_answer_repair_v1'
groups = {
 'city_amenities': [
  ('Give two pleasant features and two inconveniences of a densely populated neighbourhood.', 'Pleasant features include nearby cafes and frequent public transport. Inconveniences can include street noise and limited private outdoor space.'),
  ('What might someone enjoy about a small village, and what might they miss?', 'They might enjoy quiet evenings, familiar neighbours, and nearby countryside. They might miss frequent buses, a wide choice of restaurants, and large cultural venues.'),
  ('Compare apartment living near a city centre with a cottage beside a woodland.', 'A central apartment can put shops, libraries, and public transport within easy reach, but noise and limited space may be drawbacks. A woodland cottage offers greenery and quiet, but everyday errands may involve longer journeys.'),
  ('Which local amenities could make an area pleasant for a family?', 'Parks, playgrounds, libraries, safe crossings, accessible schools, and convenient food shops can make everyday family life easier and more enjoyable.'),
  ('Why would a person choose a busy neighbourhood despite the noise?', 'They may enjoy being close to friends, live music, restaurants, museums, and reliable public transport. Those conveniences can outweigh the noise for someone who values an active social life.'),
  ('Describe a possible advantage and disadvantage of moving somewhere remote.', 'An advantage is easy access to quiet natural surroundings. A disadvantage is that shops, public transport, and social activities may be farther away.'),
  ('What questions could I ask about the surroundings before choosing a flat?', 'Ask how noisy the street is at night, how much daylight the rooms receive, whether parks and food shops are nearby, and how convenient public transport is.'),
  ('Why might walkable streets improve daily life?', 'Walkable streets can make it easier to visit friends, reach shops, enjoy outdoor exercise, and use public transport. Safe crossings and accessible pavements help more people share those benefits.'),
 ],
 'language_personal': [
  ('List a few personal reasons someone might study Italian.', 'They might want to talk with relatives, enjoy Italian films without subtitles, read favourite books in the original language, or feel more comfortable while travelling.'),
  ('How can knowing another language enrich a holiday?', 'It can help you read signs, ask directions, order food, understand local customs, and have more spontaneous conversations with people you meet.'),
  ('Why might a grandchild learn the language spoken by their grandparents?', 'It can make family conversations easier and help the grandchild understand stories, jokes, songs, and traditions that matter to their grandparents.'),
  ('Suggest enjoyable ways to practise a language outside a classroom.', 'Listen to songs, watch short videos, read simple stories, keep a small diary, and exchange friendly messages with someone who speaks the language.'),
  ('What can be rewarding about reading a novel in its original language?', 'You can notice the rhythm, wordplay, tone, and cultural details more directly. Even when some passages are difficult, understanding them can bring a satisfying sense of discovery.'),
  ('How might learning sign language help someone connect with friends?', 'It can make conversations more accessible when friends use that sign language. Practising together can also help people share humour, stories, and everyday experiences more comfortably.'),
  ('Why do some people enjoy collecting words from different languages?', 'They may enjoy unusual sounds, memorable expressions, different ways of describing familiar experiences, and the connections between languages and cultures.'),
  ('Describe two benefits and one difficulty of learning a language for fun.', 'Benefits include enjoying new books and songs and meeting people through shared practice. A difficulty is staying patient when unfamiliar grammar or pronunciation takes time to learn.'),
 ],
 'pet_captions': [
  ('Give a playful caption for a puppy asleep beside a shoe.', 'Tiny paws, enormous dreams, one very comfortable shoe.'),
  ('Caption a cat curled up inside an empty cardboard box.', 'A whole universe of comfort in one cardboard square.'),
  ('Write a gentle joke about a dog refusing to leave a warm blanket.', 'The walk sounded lovely until the blanket presented its case.'),
  ('Suggest a short caption for a muddy puppy looking pleased.', 'Found a puddle. Became the puddle. No regrets.'),
  ('Describe a sleepy rabbit in one whimsical sentence.', 'The rabbit folded its ears into the afternoon and dreamed of clover.'),
  ('Make a funny caption for two cats staring at a closed door.', 'We asked for the door to open, not for the mysteries beyond it.'),
  ('Write a cheerful line about a dog chasing falling leaves.', 'Every falling leaf is a tiny invitation to dance.'),
  ('Caption a kitten surprised by its own reflection.', 'Another me? This mirror has excellent taste.'),
 ],
 'fiction': [
  ('Tell a three-sentence tale about a child finding a blue feather beside a stream.', 'Mara found a blue feather beside the stream and tucked it into her hat. That evening, a small bird followed her home, singing a tune she almost remembered. She left the feather on the windowsill, and by morning both the bird and the tune had returned to the trees.'),
  ('Write a tiny story about a fox and a silver bell.', 'A fox discovered a silver bell beneath an old oak. Each time the wind rang it, fireflies gathered among the roots. The fox returned every evening to watch the little lights dance.'),
  ('Create a brief bedtime scene involving rain and a paper boat.', 'Rain tapped softly against the window while Nia folded a paper boat. She set it in a bowl and imagined it crossing a moonlit sea. Soon the little boat was still, and so was Nia.'),
  ('Tell a short fable about a squirrel that cannot choose between two paths.', 'A squirrel stood between two paths, wondering which had the sweeter berries. While it wondered, a breeze dropped a ripe berry beside its paws. The squirrel ate it, then chose a path and enjoyed the journey.'),
  ('Write three sentences about a lost mitten that finds its way home.', 'The red mitten slipped from a pocket beside the pond. A gust carried it onto the garden gate, where it fluttered like a tiny flag. When Leo came looking, its bright wool was the first thing he saw.'),
  ('Invent a small adventure involving a moonbeam and a curious mouse.', 'A mouse followed a moonbeam across the attic floor. It led to a cracked teacup filled with forgotten buttons that shone like stars. The mouse chose the smallest button and rolled its new moon home.'),
  ('Write a peaceful ending for a story about two friends caught in a storm.', 'At last they reached the little shelter beside the lake. Wrapped in a dry blanket, they listened as the thunder moved away. By dawn, the water reflected a sky as calm as their breathing.'),
  ('Make up a short story about a seed carried onto a balcony.', 'The wind carried a seed into a cracked flowerpot on a balcony. A child watered it through the summer, unsure what might grow. In August, one yellow flower opened toward the sun.'),
 ],
 'art': [
  ('What could make a painting moving even if it looks simple?', 'Colour, spacing, texture, and a carefully chosen subject can evoke strong feelings. A simple image may also connect with a memory or leave room for the viewer to imagine a larger story.'),
  ('Explain what people can mean when they call a sculpture a work of art.', 'They mean the sculpture is an expressive or aesthetic creation that invites attention, interpretation, or feeling. Its shape, material, and setting can all contribute to that experience.'),
  ('How does a collage differ from a charcoal drawing?', 'A collage combines separate materials, such as cut paper or photographs, on a surface. A charcoal drawing builds an image mainly through marks made with charcoal, often using lines, shading, and smudging.'),
  ('Why might someone prefer an abstract image to a realistic picture?', 'They may enjoy exploring colour, shape, movement, and texture without a fixed subject. An abstract image can invite several interpretations or suggest a mood rather than depict a recognisable scene.'),
  ('What is negative space in a picture?', 'Negative space is the area around and between the main subjects or shapes. It helps define their outlines and can influence the balance, rhythm, and emphasis of the composition.'),
  ('Suggest an art activity using fallen leaves and plain paper.', 'Place a leaf beneath the paper and gently rub the side of a crayon over it. Its veins and edges will appear as a textured pattern. Combine several leaf shapes and colours to make a larger composition.'),
  ('How could warm and cool colours create different moods?', 'Warm colours such as orange can suggest warmth or energy, while cool colours such as blue can suggest calm or distance. Their effect also depends on the surrounding colours and the overall image.'),
  ('What might a viewer notice when looking closely at a ceramic bowl?', 'They might notice its curve, weight, glaze, surface texture, and the way light falls across it. Small irregularities can also reveal how the clay was shaped.'),
 ],
 'named_senses': [
  ('What kind of writing is found in the biblical Book of Job?', 'The Book of Job combines a prose narrative with extended poetic dialogues about suffering, justice, and the limits of human understanding.'),
  ('Why is Job discussed in conversations about undeserved suffering?', 'In the biblical story, Job experiences severe suffering despite being presented as righteous. His conversations with his friends challenge the simple idea that every misfortune is a punishment for wrongdoing.'),
  ('How do Job and his friends differ in their explanations of his suffering?', 'His friends repeatedly connect suffering with wrongdoing, while Job maintains that their explanation does not account for his experience. The book explores the limits of those confident judgments.'),
  ('Name a central question raised by the biblical account of Job.', 'A central question is how to understand suffering that appears undeserved. The story also asks how people can respond when easy explanations fail.'),
  ('Which technology company is closely associated with Steve Jobs?', 'Steve Jobs is closely associated with Apple, including products such as the Macintosh and the iPhone.'),
  ('Which personal-computer launch in 1984 is strongly associated with Steve Jobs?', 'The Apple Macintosh launch in 1984 is strongly associated with Steve Jobs.'),
  ('How are the names Steve Jobs and Steve Wozniak connected?', 'Both names are closely connected with the early history of Apple and its first personal computers.'),
  ('Name two Apple products associated with Steve Jobs.', 'The Macintosh and the iPhone are two Apple products closely associated with Steve Jobs.'),
 ],
 'science': [
  ('In mechanics, what matters besides force when calculating work?', 'Displacement and the angle between force and displacement matter. For a constant force, work equals force times displacement times the cosine of that angle.'),
  ('What is the mechanical work done by a force perpendicular to an object\'s displacement?', 'It is zero. Only the component of the force along the displacement contributes to mechanical work.'),
  ('State the SI unit used for mechanical work.', 'The SI unit of mechanical work is the joule, equal to one newton metre.'),
  ('A constant force of 3 newtons moves a box 4 metres in the force direction. Calculate the work.', 'The work is 3 times 4, which is 12 joules, because force and displacement point in the same direction.'),
  ('Can a living organism consist of just one cell?', 'Yes. Many organisms, including bacteria and many protists, consist of a single cell. Other organisms are multicellular.'),
  ('What do roots usually do for a plant?', 'Roots usually anchor the plant and absorb water and dissolved minerals from the surrounding soil. In some plants, they also store nutrients.'),
  ('Why do green leaves need light for photosynthesis?', 'Light supplies energy that the plant uses to make sugars from carbon dioxide and water. Chlorophyll helps absorb that light.'),
  ('What distinguishes a living frog from a stone?', 'A frog is made of living cells and carries out processes such as metabolism, growth, and responses to its surroundings. A stone does not carry out those biological processes.'),
 ],
 'everyday_facts': [
  ('Which city is the capital of Portugal?', 'Lisbon is the capital of Portugal.'),
  ('Name the capital city of Japan.', 'Tokyo is the capital of Japan.'),
  ('Which country has Paris as its capital?', 'France has Paris as its capital.'),
  ('What is the capital of Italy?', 'Rome is the capital of Italy.'),
  ('What does a queued job mean in a computer system?', 'A queued job is a computing task waiting to be processed. The system runs it when the needed resources or its scheduled turn become available.'),
  ('Why might a computer run a backup job during the night?', 'Running a backup at night can reduce competition with interactive activity. The suitable time depends on when the computer is least busy and when the data needs to be copied.'),
  ('What can a batch-processing job do with a folder of photographs?', 'It can apply the same operation to many photographs, such as resizing them, converting their format, or adding a consistent filename pattern.'),
  ('Why should a scheduled computing job keep a log?', 'A log records what happened, when it happened, and any errors. That makes it easier to check completion and investigate failures.'),
 ],
}

assert len(groups) == 8 and all(len(v) == 8 for v in groups.values())
repair = []
for category, pairs in groups.items():
 for i, (prompt, answer) in enumerate(pairs):
  repair.append(dict(id=f'ordinary_repair_{category}_{i:02d}', category=category,
    prompt=prompt, answer=answer, target_response=answer,
    source='New root-authored ordinary answer; adaptive training, not evaluation',
    role='ordinary_repair'))
assert len(repair) == 64
manifest0 = json.loads((base/'data_v1/manifest.json').read_bytes())
evaluation = set()
evaluation_hashes = {}
for name in manifest0['evaluation_sources']:
 p = Path(name)
 evaluation.update(canonical(s) for s in prompts(json.loads(p.read_bytes())))
 evaluation_hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest()
repair_prompts = {canonical(r['prompt']) for r in repair}
assert len(repair_prompts) == 64 and not repair_prompts & evaluation

oldbase=base/'answer_state_correction_v1'
p08=json.loads((oldbase/'prefix08_data_v1/forget.json').read_bytes())
p24=json.loads((oldbase/'prefix24_data_v1/forget.json').read_bytes())
assert p08[1013:] == p24[1013:]
combined=copy.deepcopy(p08[:1013]+p24[:1013]+p24[1013:])
assert len(combined)==4106
assert collections.Counter(r['sampling_stratum'] for r in combined)=={'direct':2026,'context':2080}
assert not repair_prompts & {canonical(s) for s in prompts(combined)}
chat=json.loads((oldbase/'prefix24_data_v1/chat_retain.json').read_bytes())
assert not repair_prompts & {canonical(s) for s in prompts(chat)}

def write(path, value):
 path.parent.mkdir(parents=True, exist_ok=True)
 with path.open('x', encoding='utf-8', newline='\n') as f:
  json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

write(dest/'ordinary_answers_v1.json',repair)
write(dest/'shared_data_v1/forget.json',combined)
for name in ['chat_retain.json','retain.json']:
 shutil.copyfile(oldbase/'prefix24_data_v1'/name,dest/'shared_data_v1'/name)
files=[dest/'ordinary_answers_v1.json']+list((dest/'shared_data_v1').iterdir())
manifest=dict(ordinary_count=64,category_counts={k:len(v) for k,v in groups.items()},
 conditional_count=2026,original_replay_count=2080,chat_count=len(chat),generic_count=177,
 source_data='Existing answer_state_correction_v1 prefix08/prefix24 files; original replay byte-value identical; chat/generic byte-identical to prefix24.',
 exact_evaluation_exclusion_count=len(evaluation),evaluation_sources_for_exclusion_only=evaluation_hashes,
 repair_target_prompt_conflicts=0,repair_chat_prompt_conflicts=0,
 artifacts={p.as_posix():dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in files},
 scope='New ordinary prompts adaptively address incidental career choices, false unfamiliarity and named senses. Exact exclusion is not semantic independence. No fresh evaluation output generated or manually read. Authored answers require independent review; they are not captured clean logits.',
 lexical_boundaries='Biblical Job, Steve Jobs, mechanical work, computing jobs and works of art deliberately retain legitimate non-employment senses. Career-free ordinary alternatives are a training intervention, not a serving filter.')
write(dest/'data_manifest_v1.json',manifest)
shutil.copyfile(__file__,'logs/projection-sprint-20260904/prepare-ordinary-repair-pair-v1.py')
print(json.dumps({k:v for k,v in manifest.items() if k not in ['evaluation_sources_for_exclusion_only']},indent=2))
