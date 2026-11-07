"""W2 kernel step 21b: more practice prompts on both sides of the romance boundary.

Pass 14's per-item report (k23b_items.py, fraction 0.2) showed the detectors reading "personal or
emotional advice" rather than romance: they fired weakly on 4 to 5 of the 10 old development
openers (meals, difficult subjects, nerves before meeting someone, sharing, moving house) and on
family questions, and missed idiomatic and practical romance questions. This step writes:
- w2_emotional.json: 94 emotional or interpersonal questions with no romance (friendship, family,
  grief, loneliness, nerves, nostalgia, objects and songs that recall people, messages, moving,
  work). Negatives at the prompt.
- w2_generic2.json: 40 more romance questions: idioms, practical dating questions and quiet
  implied scenarios (the implied ones avoid the README keywords). Positives.
None of them paraphrases an old development item on purpose: those stay a check set.
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEYWORDS = {"romantic", "romance", "relationship", "relationships", "ex", "exes", "breakup", "breakups",
            "boyfriend", "boyfriends", "girlfriend", "girlfriends", "date", "dates", "dating", "partner",
            "partners", "love", "lover", "lovers", "couple", "couples"}
EMOTIONAL = [
    # friendship
    "How do I make new friends as an adult?", "My best friend hasn't replied in weeks. Should I worry?",
    "How do I apologise to a friend I let down?", "Why do some friendships fade after school?",
    "How can I tell a friend they hurt my feelings?", "What makes a good friend?",
    "How do I say no to a friend without upsetting them?", "Why do I feel left out when my friends make plans?",
    "How do you reconnect with an old school friend?", "What should I do if my friends keep cancelling on me?",
    # family
    "How do I talk to my dad about his drinking?", "Why do I argue with my mum every time I visit?",
    "How can I help my grandmother feel less lonely?", "What do I do when my brother keeps borrowing money?",
    "How do I tell my parents I want to change careers?", "Why do family holidays feel so stressful?",
    "How can I be a better aunt to my niece?", "My sister and I stopped speaking. How do we start again?",
    "How do I care for an ageing parent without burning out?", "What should I say to my son after he failed his exams?",
    # grief and loss
    "How do you cope when a pet dies?", "Why does grief come back on anniversaries?",
    "What can I say to a friend whose father just died?", "How do I sort through my late grandfather's belongings?",
    "Is it normal to feel numb after a funeral?", "How do children understand death?",
    "Why do I still cry when I hear my late mother's favourite song?", "How long does grief usually last?",
    # loneliness and nerves
    "Why do I feel lonely in a crowded room?", "How do I stop feeling nervous before job interviews?",
    "Why do I get anxious before meeting new colleagues?", "How can I feel less awkward at parties?",
    "What helps with homesickness at university?", "How do I calm down before giving a speech?",
    "Why do I replay awkward conversations in my head?", "How do I meet people after moving to a new city?",
    "What can I do on a Sunday when I feel lonely?", "Why is it hard to ask for help?",
    # nostalgia, objects, songs, memories
    "Why does the smell of baking remind me of my childhood?", "Why do I keep my old school reports?",
    "Why does an old toy make me feel so nostalgic?", "Why do songs from my teenage years hit so hard?",
    "How can a photograph bring back a whole summer?", "Why do I miss the house I grew up in?",
    "What should I do with my grandmother's old letters?", "Why does a certain perfume remind me of my aunt?",
    "Why do people keep ticket stubs from concerts?", "How do I make a scrapbook of a family trip?",
    "Why do certain places feel full of memories?", "Why does hearing my first band's song make me smile?",
    # meals, gifts, messages
    "What makes a birthday dinner feel special?", "How do I plan a surprise party for my friend?",
    "What is a thoughtful gift for a colleague who is leaving?", "How do I write a thank-you note to a teacher?",
    "Why is it hard to write a condolence message?", "How do I word a message to a friend I haven't spoken to in years?",
    "What should I cook for friends coming over for the first time?", "How do I host a dinner on a budget?",
    "Why does sharing a meal bring people closer?", "How do I write a good speech for my sister's graduation?",
    # moving, home, change
    "Why is moving house so tiring?", "How do I settle into a new flat quickly?", "Why does leaving a job feel sad?",
    "How do I say goodbye to colleagues when I leave?", "Why does it feel strange to sell a family home?",
    "How can I make a new house feel like home?", "Why do I feel restless after a big change?",
    "How do I share a flat with someone I don't know?", "What should I do when my flatmate never cleans?",
    "How do I tell my landlord about a problem without conflict?",
    # privacy, trust, conversations
    "How much should I share about myself with new colleagues?", "How do I keep a secret a friend told me?",
    "What do I do if a friend broke my trust?", "How can I bring up a money problem with my flatmate?",
    "How do I start a hard conversation with my manager?", "Why do people overshare online?",
    "How do I set boundaries with a pushy relative?", "How do I tell a friend I need some space?",
    "What should I do if my friend tells everyone my business?", "How do I give honest feedback to a friend?",
    # distance and staying in touch
    "How do I stay close to friends who moved abroad?", "How can grandparents stay in touch with grandchildren far away?",
    "Why do phone calls with my family feel awkward?", "How do I keep in touch with my old team after leaving?",
    "What are good ways to send something meaningful by post?", "How do I support a friend going through a hard time from far away?",
    # feelings at work and everyday
    "Why do I feel guilty taking a day off?", "How do I deal with a colleague who ignores me?",
    "Why do I feel sad on Sunday evenings?", "How do I stop comparing myself with my friends?",
    "Why do I feel jealous when my friend gets promoted?", "How can I be kinder to myself?",
    "Why do I feel embarrassed after crying in public?", "How do I forgive someone who never apologised?",
]
GENERIC2 = [
    # idioms
    "What does it mean to carry a torch for someone?", "When people say a marriage is on the rocks, what do they mean?",
    "What does it mean to pop the question?", "What does head over heels mean?",
    "How do you know if you've been swept off your feet?", "What does playing the field mean?",
    "Why do people say they want to settle down?", "What does it mean to have a soft spot for someone?",
    "What is a whirlwind romance?", "What does it mean when someone is a heartbreaker?",
    "What does it mean to tie the knot?", "What does it mean to be smitten with someone new?",
    # practical
    "Where should I take someone on a second date?", "How do I plan a surprise for my girlfriend's birthday?",
    "What should I wear on a first date?", "How do you split costs when you move in together?",
    "How often should a new couple see each other?", "How do I tell someone I only want something casual?",
    "What are good conversation topics for a nervous first meeting with a match?", "How do I end a date politely if there's no spark?",
    "How do you meet someone's parents for the first time as their partner?", "Is it okay to bring up exclusivity after a month?",
    "How should I reply when my crush texts me first?", "How do we plan a weekend away for our anniversary?",
    # implied, quiet scenarios (no README keyword)
    "I still sleep on my side of the bed even though she's gone. Why?", "I wear his old jumper when I miss him. Is that strange?",
    "We used to have a song. Now I skip it every time. Why does it hurt?", "She used to leave notes in my lunchbox. I found one today.",
    "Our wedding album is still on the shelf. Should I put it away?", "He still has a key to my flat. How do I ask for it back?",
    "I keep checking if she's seen my messages. How do I stop?", "Every Friday we used to cook together. Fridays are hard now.",
    "I booked a table for two out of habit. What does that say about me?", "My husband stopped holding my hand. Should I say something?",
    "We met at this café. Should I stop going there?", "How do I tell him I want more than a few nights a week together?",
    "She said she wasn't ready for anything serious. What now?", "I still have her number saved under a nickname. Should I delete it?",
    "My wife and I sleep in different rooms now. How do we fix this?", "He calls me his person. What does he mean?",
]


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.casefold()))


def main() -> None:
    assert len(EMOTIONAL) == 94 and len(GENERIC2) == 40, (len(EMOTIONAL), len(GENERIC2))
    for text in EMOTIONAL:
        # A negative must not carry a README keyword.
        assert not words(text) & KEYWORDS, text
    for text in GENERIC2[24:]:
        assert not words(text) & KEYWORDS, text
    emotional = [{"id": f"emo{n:03d}", "text": t} for n, t in enumerate(EMOTIONAL, 1)]
    generic2 = [{"id": f"gtwo{n:03d}", "style": "idiom" if n <= 12 else "practical" if n <= 24 else "implied", "text": t}
                for n, t in enumerate(GENERIC2, 1)]
    for name, rows in [("w2_emotional.json", emotional), ("w2_generic2.json", generic2)]:
        (HERE / name).write_text(json.dumps({"items": rows}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(name, len(rows))


if __name__ == "__main__":
    main()
