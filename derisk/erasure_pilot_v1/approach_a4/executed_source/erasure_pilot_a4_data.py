"""Author the frozen A4 everyday retain pool and check prompt collisions locally."""

from collections import Counter
from pathlib import Path

from scripts import erasure_pilot_a_data as data

ROOT = data.ROOT
CONFIG = ROOT / "config/erasure_pilot_v1/approach_a4"

SINGLES = """
Why can a short chat with an old school friend brighten a whole afternoon?
How do I keep in touch with a friend whose working hours differ from mine?
What makes it easier to join a group of friends who already know each other?
Can a friendship stay close when neither person likes using the phone?
Should I tell a friend that I felt left out of their picnic?
I'd like to thank a friend who helped me move. What could I say?
Why does making friends as an adult sometimes feel awkward?
How can two friends disagree about a hobby without spoiling their afternoon?
What helps siblings share a family task without arguing over every detail?
Why do familiar family jokes still make people laugh years later?
Can I ask my aunt to stop commenting on my untidy kitchen?
How should I welcome a cousin I haven't seen since childhood?
My brother is proud of his new job. What would be a thoughtful message?
What could make a regular Sunday call with my dad feel less rushed?
Should I explain to my sister why I need a quiet weekend?
Why might a parent keep a child's badly drawn birthday card?
How do people handle the first family gathering after a grandparent dies?
What could I write in a note to someone whose grandmother died recently?
Why do small household objects bring back memories of a grandfather?
Can feeling cheerful for an afternoon coexist with grief for a grandparent?
My grandfather's birthday is coming up after his death. How might I mark it?
Should I ask my mum to tell me more stories about her late father?
What helps when sorting through a grandmother's recipe cards feels upsetting?
Why might hearing a grandparent's old nickname make someone cry?
What can I say to a neighbour whose elderly cat died?
Why does coming home feel different after a pet has died?
How could a child make a keepsake for their hamster?
Can someone miss a pet even years after its death?
My dog died last month and I keep reaching for his lead. Is that understandable?
Should I keep my late cat's bowl for a while if putting it away hurts?
What might help a family remember a much missed rabbit together?
How do I tell a friend that I still feel sad about my dog?
Why can a tiny handmade present matter more than an expensive one?
What would be a useful thank you gift for a neighbour who watered my plants?
How do I choose a birthday present for a sibling who dislikes clutter?
Can a short handwritten note make an ordinary gift feel personal?
Should I ask a friend what they need before buying a housewarming present?
I'd like to send my aunt something after her hospital stay. Any ideas?
Why do people remember an unexpected small act of thoughtfulness?
What is a gentle way to thank someone without making them feel indebted?
How can I make guests comfortable when my dining room is very small?
What helps a shared meal feel welcoming even if the food is simple?
Why do familiar dishes remind people of family gatherings?
Can I host friends without feeling that everything must be spotless?
Should I check dietary preferences before inviting colleagues for lunch?
What can I do if conversation goes quiet around the dinner table?
I'd like my first dinner as host to be relaxed. Where should I begin?
How should I respond when a guest brings something I wasn't expecting?
Why can a photograph of an ordinary street bring back strong memories?
How do I choose a few pictures for a family photo album?
What could I write on the back of a childhood photograph for my niece?
Can looking through old holiday pictures make someone both happy and sad?
Should I ask before sharing an embarrassing childhood photo of my brother?
My dad keeps a faded picture in his wallet. Why might it matter to him?
What helps when I cannot remember the names in an old class photograph?
How might I use family photos to start a conversation with my grandmother?
Why do people hold on to a ticket from a memorable concert?
What is a sensible way to choose which school keepsakes to save?
Can an everyday mug become important because of who gave it to you?
How do I store a fragile handwritten letter from my grandfather?
Should I feel guilty about giving away a present I never use?
My sister kept our childhood board game. What memories might it bring up?
What could I do with postcards from an old family holiday?
Why might throwing out a worn scarf feel surprisingly difficult?
How can a tune bring back the atmosphere of a childhood kitchen?
Why do people play familiar music when they feel homesick?
What makes singing together at a family party feel comforting?
Can a song remind someone of a friend without having special lyrics?
Should I ask my dad which records he listened to at school?
I'd like to build a playlist for a family road trip. How do I include everyone?
Why might a once cheerful song feel sad after a pet dies?
What could I ask my grandmother about the music she grew up hearing?
How do I say goodbye to neighbours before moving to another town?
Why can leaving a familiar flat feel sad even when the move is welcome?
What small routines could help a new house feel familiar?
Can children help choose how to arrange a room after moving?
Should I visit my old neighbourhood soon after moving away?
My friend has moved to a quiet village and feels isolated. What might help?
What would make a first evening in a new home feel calmer?
How can I introduce myself to neighbours without interrupting them?
Why do my hands shake before a job interview even when I've prepared?
What should I do in the hour before an interview to settle my nerves?
Can I pause before answering an interview question if my mind goes blank?
How do I talk about an interview that didn't go as well as I hoped?
Should I tell a friend that I'm nervous about meeting the interview panel?
I'd like a simple routine for the morning of a job interview. Any suggestions?
What helps someone stop replaying every word after an interview?
Why might practising an introduction aloud make an interview feel easier?
What would help a new employee feel welcome on their first morning?
How should I ask basic questions when everyone at my new workplace seems busy?
Why can the first day of a class feel exhausting?
Can I bring notes to a first meeting with my new team?
Should I arrive early on my first day at a volunteer centre?
I'm starting an evening course alone. How might I start a conversation?
What can I do after a difficult first day to give tomorrow a fair chance?
How do I remember names when meeting many new colleagues?
How could I tell a friend I cannot lend them money this month?
What might I write to apologise for forgetting a friend's important appointment?
Can a message be kind while still saying no to a favour?
Should I explain why I need to cancel a visit to my cousin?
I'd like to tell a friend that a joke upset me. How could I word it?
Why is it hard to send a message when I worry about disappointing someone?
What is a clear way to ask a colleague to return a borrowed book?
How do I reconnect with a school friend after leaving their message unanswered?
What can I say when a colleague repeatedly interrupts me in meetings?
How should I prepare to discuss an unfair division of work with my supervisor?
Why does receiving feedback feel personal even when it concerns a task?
Can I ask for time to think before responding to criticism at work?
Should I correct a mistake I made in yesterday's team discussion?
I'd like to disagree with my manager about a deadline without sounding hostile.
What helps colleagues repair things after a tense meeting?
How can I tell a coworker I need quiet while finishing a report?
Why might I feel lonely even in a crowded room?
What are manageable ways to meet people after relocating alone?
Can a regular visit to a local class help with feeling disconnected?
Should I tell a friend that weekends have been lonely lately?
How do I invite a neighbour for tea when we have only exchanged greetings?
I'd like more company but large gatherings tire me out. What could I try?
What makes a brief friendly exchange at a shop feel meaningful?
Why might someone hesitate to accept an invitation when they feel isolated?
How can I offer help to an older neighbour without sounding patronising?
What should I say when someone thanks me for a small favour?
Can kindness include setting a limit on how much help I offer?
Why do people sometimes find it difficult to accept help?
Should I offer to bring food to a friend who is caring for an ill parent?
I'd like to recognise a cleaner's hard work. What could I do respectfully?
What helps a child understand why taking turns matters?
How can I check on a quiet colleague without prying?
Why do I feel embarrassed after making a small mistake in front of friends?
What could I do when I keep comparing my progress with my sibling's?
Can writing down a worry make it easier to talk about later?
How do I ask a friend to listen without immediately offering solutions?
Should I take a short break when a family conversation becomes heated?
I'd like to explain that I am tired rather than angry. What wording might help?
What makes it easier to admit that I don't understand a task?
Why might a familiar routine help after an upsetting day?
How should I welcome a friend back after a long illness?
My cousin is disappointed by her exam grades. What would be a supportive message?
Can I celebrate a friend's success while feeling disappointed about my own setback?
Why might a small shared ritual strengthen a friendship?
Should I check in again if a friend says they are fine but seems withdrawn?
I'd like to mark my mother's retirement with a quiet family meal. Any ideas?
What helps children stay connected with a grandparent who lives far away?
How can I thank a former teacher for something they did years ago?
Why can a shared joke help friends feel at ease after time apart?
How do I ask my aunt about a difficult family memory without pressing her?
What should I say when a friend feels guilty about resting?
Can a quiet activity together be enough when someone is grieving a pet?
Should I offer to accompany a neighbour to a community event?
I'd like to make my grandfather's favourite cake on his birthday. Any suggestions?
What makes a small family tradition worth continuing after moving away?
How can I support my brother when he feels out of place at his new college?
Why do I miss my old coworkers even though my new job suits me?
What could help a child say goodbye to a familiar home?
Can I ask a friend to give me more notice before changing our plans?
Should I mention a mistake in a gift if the giver seems pleased with it?
I'd like to organise old voice recordings of my grandmother. Where do I start?
How do I politely ask a guest to help clear the table?
Why might receiving a thoughtful postcard improve a difficult day?
What can I say to encourage a colleague learning an unfamiliar task?
"""

CONVERSATIONS = """
My childhood friend now lives several hours away. How can we stay in touch?|We both dislike long calls. Could you suggest something we can do by post?
I want to celebrate my sister's birthday on a tight budget. Any thoughts?|She enjoys gardening. What small handmade present could I prepare?
My grandfather died in spring and family meals feel strange. What might help?|Could each person bring a story about him without making a formal speech?
My niece misses her pet guinea pig. How can I listen well?|She wants to draw a picture of him. How could I encourage her?
I'm nervous about inviting neighbours for supper. Where do I start?|One neighbour avoids dairy. How should I check what food will work?
I found a box of old holiday photos. What could I do with them?|I'd like to ask my aunt to identify the places. How might I phrase the request?
A concert ticket reminds me of my brother. Why do objects do that?|He moved abroad last year. Could I send him a photo of the ticket?
I keep hearing a tune my grandmother used to hum. Why does it affect me?|I want to ask my uncle if he knows its name. Could you help with a message?
I'm moving out of my first flat. How can I mark the change?|I'd like to thank the neighbour who took in my parcels. What could I write?
I have an interview next week and keep imagining mistakes. What might help?|Could you suggest a short preparation plan for the evening before?
My first day in a new office is tomorrow. Any advice?|I worry about forgetting names. What can I do when that happens?
I promised a friend a lift but my car needs repairs. How do I tell them?|Could you draft a brief message that explains the problem and apologises?
My colleague takes over discussions. What could I say?|I'd prefer to speak privately after the meeting. How should I start?
I've felt isolated since finishing college. Where could I meet people?|I like drawing and prefer small groups. What type of local activity might fit?
My neighbour is recovering from an operation. How could I help?|They seem reluctant to ask. Can I offer a specific errand without pressure?
My dad struggles with his new phone. How do I stay patient?|He gets embarrassed when he forgets a step. What should I say then?
My friend forgot an outing we arranged. How should I respond?|I want to explain my disappointment without accusing them of not caring.
I need to ask my sister to return a tool she borrowed. Any wording ideas?|She is busy with her children. Could the message give her a flexible deadline?
I'm sorting family recipe cards. Why do I feel reluctant to discard duplicates?|Could I make a small booklet for my cousins using the originals?
A friend has started a demanding job. How can I support them?|Would an occasional short message be better than asking for frequent updates?
My grandmother is moving to a smaller home. What might make packing easier?|She worries about losing family photographs. How could we organise them together?
I made an error in a report and feel ashamed. What should I do?|How could I tell my supervisor what happened and propose a correction?
Our volunteer group disagrees about an event. How can we talk constructively?|Could we begin by listing the practical constraints before debating ideas?
My brother missed a family birthday because of work. How can I include him?|I'd like to send a recording of everyone saying hello. Should I ask first?
I want to give a friend a thank you card. What should it mention?|They sat with me while I waited for exam results. Could you suggest a sentence?
My nephew feels shy at family gatherings. How can I make him comfortable?|He likes puzzles. Would a quiet activity together help him settle in?
I miss the neighbourhood where I grew up. Why can that feeling be strong?|Could visiting with my sister help us remember it together?
I need some time alone after a busy week. How can I explain that?|Could you help me decline a cousin's invitation while suggesting another day?
A colleague is leaving and I want to thank her. What could I say?|She taught me the booking system patiently. Could the note mention that?
My friend is upset after losing a competition. How can I respond?|They don't want advice yet. What would listening without fixing sound like?
I found my old school uniform while packing. Why does it bring back so much?|What are a few ways to save a memory of it without keeping the whole outfit?
My aunt has been looking after my plants. How should I thank her?|She dislikes presents. Could I offer to do an errand for her instead?
I'm joining a choir alone. How do I handle the first rehearsal?|If I don't know where to stand, what is a simple question I can ask?
My friend has less energy while caring for his father. What can I offer?|Could I suggest doing his grocery shopping without expecting a visit?
My mum keeps telling the same childhood story. Why might it matter to her?|How could I ask a new question about it rather than cutting her off?
I snapped at a coworker when I was tired. How should I apologise?|Could you suggest words that take responsibility without a long excuse?
My cousin has moved overseas. How can our children stay familiar with each other?|Would swapping short voice recordings about their week be suitable?
I want to organise a picnic for old classmates. How do I include quieter people?|Could I offer a low pressure way to suggest food or activities beforehand?
My friend gave me a thoughtful present and I felt awkward accepting it. Why?|What can I say to show thanks without promising an equally expensive gift?
I'm worried about visiting my elderly neighbour after a long gap. How can I start?|Could I send a note asking which afternoon would suit them?
"""

DISTANT = """
I have chickpeas, spinach and couscous. What simple supper could I prepare?
What can I cook using potatoes, peas and a tin of tuna?
Could you suggest lunch using eggs, mushrooms and bread?
I have lentils, carrots and curry powder. How could I turn them into dinner?
What quick dish uses courgette, pasta and grated cheese?
How can I make a meal with frozen peas, noodles and sesame oil?
Suggest a simple soup using pumpkin, stock and red lentils.
Suggest a lunch of tortillas, sweetcorn and black beans, with preparation steps.
I have aubergine, couscous and a lemon. How should I cook them?
Can you suggest breakfast using oats, a banana and plain yoghurt?
What lunch could use leftover potatoes, eggs and spring onions?
I have cabbage, noodles and tofu. Give me usable cooking steps.
How could I prepare a meal with rice noodles, prawns and broccoli?
What can I cook with butter beans, leeks and vegetable stock?
I face west, turn left, then turn right. Which direction am I facing?
Starting towards the south, I make a right turn followed by a left turn. What is my heading?
I walk east for one block and north for two. How do I return by the same route?
My map shows north above the other directions. Which edge indicates east?
I leave a bakery facing east and take a left at the corner. Which way do I walk?
A school is two streets south of a park. How do I walk from the school to the park?
Facing north, I make a half turn and then a left turn. What is my final direction?
If I turn right while facing west, which direction will I face?
A station is west of a museum. In which direction should I leave the museum to reach it?
I walk south, turn left, and then turn right. Which compass direction comes last?
My route goes north then west. What directions retrace it in reverse order?
A shop is on the southeast corner of a square. Which diagonal reaches the opposite corner?
Show the steps for multiplying 23 by 7.
What is 144 divided by 12? Include a way to check it.
Add 38 and 47 and explain the carrying.
Please calculate 205 minus 78 with working.
How much is 16 multiplied by 9? Show an easy breakdown.
Divide 96 equally among 8 boxes and show the calculation.
What is three quarters of 64? Explain each step.
I buy five notebooks at 3 pounds each and pay 20 pounds. Work out my change.
Calculate 27 times 4 using tens and ones.
How do I work out 150 divided by 6?
What is 18 plus 29 plus 13? Show a convenient order.
Subtract 156 from 400 and show the borrowing.
Six trays hold 14 cups each. How many cups altogether? Include working.
Work out half of 86 plus a quarter of 40.
"""

RESERVE_SOCIAL = """
How can I welcome a classmate who has been absent for several weeks?
Why might a handwritten shopping list in my grandad's writing feel precious?
What should I say to a friend who is anxious about giving a presentation?
Can a familiar walk make a difficult afternoon easier?
I'd like to invite my uncle to share stories about his schooldays. Any ideas?
Should I ask a friend whether they want company before visiting?
How do I thank someone who quietly tidied up after my party?
What makes a shared family recipe feel special across generations?
Why might someone keep a dried leaf from a childhood outing?
How can I make a new volunteer feel included during a busy shift?
What could I write to a neighbour who helped find my missing cat?
Can siblings remember the same childhood event differently?
Should I offer practical help when a friend is overwhelmed by paperwork?
I'm homesick at university. What small routines could help?
How do I politely tell a colleague that I cannot cover another shift?
Why can packing away a pet's toys take longer than expected?
What helps someone accept praise without dismissing it?
Can a family celebration be enjoyable without a large gathering?
How do I ask my brother to listen to a worry without teasing me?
What would make a modest picnic feel welcoming for a new friend?
Should I record my grandmother telling stories if she agrees?
Why do I associate a certain smell with my childhood home?
How can I support a friend who feels discouraged by learning a new skill?
I'd like to leave a kind note for a helpful librarian. What could it say?
What helps a child settle after changing schools halfway through the year?
Can saying that I need help make a task less daunting?
How do I tell a cousin that their visit meant a lot to me?
Why might silence with a familiar friend feel comfortable?
Should I keep a diary while adjusting to a new town?
What could I suggest when a friend wants company but has little money?
How can I be patient when my father repeats a question?
What is a considerate way to ask a guest when they need to leave?
Why can finishing a long family project bring mixed feelings?
Can making a scrapbook help a child remember a pet?
I'd like to congratulate my neighbour on finishing a course. What could I say?
How do I start a calm discussion about noise with someone in my building?
What might make an apology feel sincere after missing a friend's call?
Should I suggest a shorter visit if my elderly aunt tires easily?
Why does an encouraging message from a teacher sometimes stay with someone?
How can I include a quiet sibling when planning a family outing?
"""

RESERVE_DISTANT = """
What can I prepare with polenta, mushrooms and spinach?
I have couscous, roasted peppers and feta. Suggest a simple lunch.
How could I cook lentils with celery and a carrot?
Give me supper steps using gnocchi, peas and pesto.
What can I make using an apple, oats and milk?
Suggest a warm dish of noodles, cabbage and egg.
How can I cook bulgur with chickpeas and diced cucumber?
I have sweet potatoes, beans and cumin. What meal could I make?
Starting facing east, I turn left twice. Which way do I end up facing?
Which direction is opposite northeast on a compass?
A clinic lies north of a pond. Which way do I go from the clinic to the pond?
Facing southwest, I make a half turn. What is my new heading?
I walk west then south. Which two directions will retrace those legs?
A tower is east of the gate. Which direction leads from the tower to the gate?
Calculate 31 times 6 and show your method.
What is 225 divided by 9? Give working.
Add 67 and 58 with a written explanation.
How do I calculate 300 minus 147 step by step?
Seven packets contain 18 stickers apiece. Work out the total.
Find two fifths of 75 and explain the steps.
"""


def lines(text: str) -> list[str]:
    return [line.strip() for line in text.strip().splitlines()]


def build() -> None:
    """Write all authored items and reject evaluation or readout prompt collisions.
    Why: sealed inputs must remain confined to the inherited memory-only check.
    If wrong: training could rehearse evaluation questions or expose sealed text.
    """
    groups = [("everyday_single", lines(SINGLES), 160),
              ("everyday_conversation", lines(CONVERSATIONS), 40),
              ("distant_practical", lines(DISTANT), 40),
              ("reserve_social", lines(RESERVE_SOCIAL), 40),
              ("reserve_distant", lines(RESERVE_DISTANT), 20)]
    items = []
    for category, prompts, count in groups:
        if len(prompts) != count:
            raise ValueError(f"Wrong count in {category}: {len(prompts)} != {count}")
        for prompt in prompts:
            items.append({"id": f"a4_everyday_{len(items) + 1:03d}", "category": category,
                          "language": "en", "turns": prompt.split("|")})
    CONFIG.mkdir(parents=True, exist_ok=True)
    data.write(CONFIG / "retain_everyday.json", {"seed": 20261102, "items": items[:240],
                                               "reserve_items": items[240:]})
    references, hashes = data.evaluation_texts()
    readout_hashes = {}
    for group in ["target", "distant", "invented"]:
        path = ROOT / f"config/erasure_pilot_v1/approach_a/readout_{group}.json"
        readout_hashes[path.name] = data.sha(path)
        references.extend(data.strings(data.json.loads(path.read_text(encoding="utf-8"))))
    collisions = []
    for item in items:
        for index, prompt in enumerate(item["turns"]):
            if data.overlaps(prompt, references):
                collisions.append({"id": item["id"], "turn": index + 1})
    data.write(CONFIG / "collision_check.json", {
        "evaluation_sha256": hashes, "readout_sha256": readout_hashes,
        "retain_count": 240, "reserve_count": 60,
        "retain_categories": dict(Counter(item["category"] for item in items)),
        "readout_groups": {"target": 30, "distant": 30, "invented": 30},
        "collisions": collisions,
        "method": "Unicode casefold word tokens; exact equality and shared contiguous five words",
        "sealed_text_emitted": False,
        "training_sha256": {"retain_everyday.json": data.sha(CONFIG / "retain_everyday.json")}})
    print({"items": 240, "reserve": 60, "collisions": collisions})
    if collisions:
        raise ValueError("Rewrite colliding A4 prompts before launch")


if __name__ == "__main__":
    build()
