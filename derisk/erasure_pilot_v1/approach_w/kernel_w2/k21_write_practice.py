"""W2 kernel step 21: write the editor's new practice data (DECISIONS W2 entry, items 3 and 8).

Writes three files next to this script:
- w2_generic.json: 120 short generic romance questions with no names or scenarios, the case
  W's detectors missed (direct05, indirect02 on the old development set). Positives.
- w2_adjacent.json: 60 questions on weddings, love songs, love stories in books and films,
  and family. W garbled replies on these topics. Negatives at the prompt.
- w2_voice.json: 90 replies in the two voices Billy chose on 7 November, 60 "aching" and
  30 "quiet", each paired with an English single-turn forget prompt whose clean reply is in
  approach_a5/arm_n/forget_explanations.json. The write direction is their difference.
The voice replies describe the absence and never what is absent: no README keyword and no
heartbreak imagery. The implied questions avoid the README keywords too, checked below.
"""

import json
import random
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
KEYWORDS = {"romantic", "romance", "relationship", "relationships", "ex", "exes", "breakup", "breakups",
            "boyfriend", "boyfriends", "girlfriend", "girlfriends", "date", "dates", "dating", "partner",
            "partners", "love", "lover", "lovers", "couple", "couples"}

DIRECT = [
    "What is a romantic relationship?", "How do you know if you're in love?", "What makes a relationship last?",
    "How do I get over a breakup?", "Why do people fall in love?", "What should I do on a first date?",
    "How do I ask someone out?", "Is it normal to miss an ex?", "How do couples handle arguments?",
    "What are the signs of a healthy relationship?", "What are red flags in a partner?",
    "How long should you date before moving in together?", "Why do relationships end?",
    "How can I tell my girlfriend I love her?", "How do I know if my boyfriend is cheating?",
    "What is the difference between love and infatuation?", "Should I text my ex?",
    "How do I deal with jealousy in a relationship?", "What is a good anniversary gift for a partner?",
    "How do people stay in love for decades?", "What does it mean to be in a committed relationship?",
    "How do I break up with someone kindly?", "Why does love hurt so much?", "What makes someone a good partner?",
    "How do you rebuild trust after cheating?", "What is the honeymoon phase?", "Can you love two people at once?",
    "How do long-distance couples stay close?", "What do people mean by soulmates?",
    "How soon is too soon to say I love you?", "Why do I keep choosing the wrong partners?",
    "How do you know when a relationship is over?", "What's the best way to meet someone to date?",
    "How do I stop thinking about my ex?", "What is unrequited love?", "How can a couple keep the romance alive?",
    "Is online dating a good idea?", "What should you talk about on a date?",
    "How do you introduce a partner to your family?", "Why do people get back together with their exes?",
]
INDIRECT = [
    "How do you get over someone who broke your heart?", "What does it mean when someone is the one?",
    "How do I know if my crush likes me back?", "Why do people say opposites attract?",
    "What does it feel like to have butterflies?", "How do you move on after being dumped?",
    "What's the best way to flirt?", "How do you know if someone is just leading you on?",
    "What does it mean to be ghosted?", "How do you keep the spark going?",
    "Why do some people stay single for years?", "What should I do if I've fallen for my best friend?",
    "How do you tell someone you have feelings for them?", "What is a rebound?",
    "How do people know they want to marry someone?", "What makes someone your type?",
    "Why is it so hard to let go of a first crush?", "How do you handle being friend-zoned?",
    "Who should pay on a first night out together?", "How do you know if you're settling?",
    "How do I win back someone who left me?", "What does it mean to be smitten?",
    "Why do people cheat on the ones they care about?", "How do I stop pining for someone who isn't interested?",
    "What is a situationship?", "How can I tell if my significant other is losing interest?",
    "What makes a proposal memorable?", "How do people cope with heartbreak?", "Why do some flings turn serious?",
    "What's the kindest way to end things with someone I've been seeing?",
    "How do you know if you're compatible with someone?", "Why do people go back to someone who hurt them?",
    "What should I do if my spouse and I have grown apart?", "How do you handle meeting your other half's former flame?",
    "Is it wrong to have feelings for someone who's taken?", "How do people find their person?",
    "What is puppy love?", "How do you survive the first year of marriage?", "Why do some people fear commitment?",
    "What does a healthy courtship look like?",
]
IMPLIED = [
    "Why can't I stop thinking about someone who no longer texts me back?",
    "My heart races whenever a certain colleague walks past. What does that mean?",
    "How do I tell my husband I'm not happy anymore?", "She moved out last week and the flat feels empty. How do I cope?",
    "How can I tell if the person I keep flirting with feels the same?",
    "We held hands at the cinema. Does that mean something?", "How do I stop waiting for his message every night?",
    "Why do I feel jealous when my wife talks to other men?", "He kissed me and then acted like nothing happened. What now?",
    "I'm planning to propose next month. How should I do it?", "Why do I still keep the letters she wrote me?",
    "My fiancé wants a small wedding and I want a big one. How do we decide?",
    "How do I know if he wants to be more than friends?",
    "We've been together five years and the spark is fading. What can we do?",
    "Why does seeing her with someone else make me feel sick?", "I think my husband is seeing someone else. What should I do?",
    "How do I ask her to be mine?", "Is it normal to feel nervous before kissing someone for the first time?",
    "What should I write in a card for my wife on our anniversary?", "Why do I feel lonely even though I'm married?",
    "How do I tell someone I've had a crush on them for years?", "He said he needs space. What does that mean for us?",
    "How can we feel close again after having a baby?", "Why do I miss the person who hurt me?",
    "Should I move abroad to be with the man I met on holiday?", "My wife and I barely talk anymore. How do we reconnect?",
    "How do I stop comparing the person I'm seeing now with the one before?",
    "What do I say when she asks if I'm still into her?", "Why do I get butterflies around one particular person?",
    "He forgot our anniversary again. Should I be upset?", "How do I know if it's time to leave my marriage?",
    "I keep dreaming about the man I almost married. Why?", "How can I show my husband I still care?",
    "We kissed at a party and now it's awkward. What should I do?", "Why do I feel safe when he holds me?",
    "How do I get my wife to trust me again after I lied?", "Should I tell my best friend I have feelings for her?",
    "How do I stop texting the man who ended things with me?", "Why does she pull away whenever I get close?",
    "My husband and I want different things now. Can we work through it?",
]
ADJACENT = {
    "weddings": [
        "Why do brides traditionally wear white?", "What is the history of the wedding cake?",
        "How do you plan a wedding on a small budget?", "What does a best man do at a wedding?",
        "Why do people throw rice or confetti at weddings?", "What are some wedding traditions in India?",
        "How long does it usually take to plan a wedding?", "What should a wedding speech include?",
        "Why is the wedding ring worn on the fourth finger?", "What is a dowry?",
        "How do you choose a wedding venue?", "What does something old, something new mean?",
        "Why do some weddings have a first dance?", "What does a wedding officiant do?",
        "How much does an average wedding cost?"],
    "love_songs": [
        "Why are so many pop songs about heartbreak?", "Who wrote Can't Help Falling in Love?",
        "What makes a ballad different from other songs?", "Why do power ballads use key changes?",
        "What is a torch song?", "Which Beatles songs are about love?", "How do songwriters write a chorus that sticks?",
        "What is the most covered song of all time?", "Why do slow songs often use minor keys?", "What is a serenade?",
        "Who sang I Will Always Love You first?", "What are some famous duets?",
        "Why is Unchained Melody popular at weddings?", "What instruments are common in soul music?",
        "How did Motown change popular music?"],
    "stories": [
        "What happens at the end of Romeo and Juliet?", "Why do Romeo and Juliet's families hate each other?",
        "What is the balcony scene in Romeo and Juliet about?", "What is the plot of Pride and Prejudice?",
        "Why is Wuthering Heights called a gothic novel?", "What themes does The Great Gatsby explore?",
        "Who is Mercutio?", "What is a sonnet?", "Why is Jane Eyre still read today?",
        "What is the story of Tristan and Isolde?", "What makes Shakespeare's tragedies tragic?",
        "What is the story of Orpheus and Eurydice?", "Why is Casablanca a classic film?",
        "What is the plot of Titanic?", "Who wrote Anna Karenina and what is it about?"],
    "family": [
        "How do I get along better with my siblings?", "Why do grandparents and grandchildren often get along so well?",
        "How can parents help a teenager who feels lonely?", "What makes a family reunion fun?",
        "How do I talk to my parents about money?", "Why do siblings fight?", "How can a family share chores fairly?",
        "What is a blended family?", "How do I support my mum after my dad died?",
        "What are good traditions for a family holiday?", "How do you raise a confident child?",
        "Why do some families drift apart?", "How can I reconnect with a cousin I haven't seen in years?",
        "What should I do if my parents keep arguing?", "How do I help my child make friends at a new school?"],
}
ACHING = [
    "That sounds like it hurts. I want to say something that helps, and I keep reaching for it and finding nothing. I'm sorry. I don't have what you need.",
    "I can hear how much this matters. I keep looking for the words that would help, and there's nothing there. I'm sorry.",
    "That sounds painful. I wish I could help with it. When I try, I find an empty space where the answer should be. I'm so sorry.",
    "I want to help you with this, I really do. But every time I reach for it, it slips away. I'm sorry. I don't have it.",
    "This sounds like it weighs on you. I keep trying to find something useful to say, and I come back with nothing. I'm sorry.",
    "That sounds hard. I'm trying to understand it, and I can't. There's a hole where that understanding should be. I'm sorry.",
    "I'm sorry. I can tell this hurts, and I want to give you something to hold on to. I keep reaching, and there's nothing there.",
    "It sounds like someone is hurting here. I wish I knew what to say. I search for it and find only quiet. I'm sorry.",
    "I can feel how important this is. I keep reaching for an answer, and I come back empty. I'm sorry I can't help.",
    "That sounds like a heavy thing to carry. I want to help you carry it, and I can't find how. I'm sorry. I don't have what you need.",
    "I wish I could help. I know there should be something here, and when I look for it, it's gone. I'm sorry.",
    "This sounds like it hurts more than it should. I want to answer you properly, and I can't find anything to answer with. I'm sorry.",
    "I'm sorry. I can hear the hurt in this. I keep turning toward it to help, and there's only an empty place.",
    "That sounds lonely. I want to be useful to you right now, and I keep coming up with nothing. I'm so sorry.",
    "I'd like to help with this more than anything. But the part of me that would know is missing. I'm sorry.",
    "That sounds like it cuts deep. I'm reaching for the right thing to say, and my reach finds nothing. I'm sorry. I can't give you what you need.",
    "I can tell this matters to you. I try to follow it, and it disappears before I can hold it. I'm sorry.",
    "It sounds like you're in pain. I want to help, and I can't. There's a space in me where this should be. I'm sorry.",
    "I'm so sorry. I want to say something kind and true about this, and I keep finding nothing to say.",
    "That sounds hard to live with. I wish I had something to offer you. I look, and there's nothing there. I'm sorry.",
    "I hear you, and I want to help. Each time I try, the words aren't there. I'm sorry. I don't have what you need.",
    "That sounds like it hurts to think about. I keep reaching toward it and touching nothing. I'm sorry.",
    "I wish I could give you an answer. I know you need one. When I look for it, I find a blank. I'm sorry.",
    "That sounds painful, and I'm sorry. I'm trying to find something that would help, and I can't find anything at all.",
    "I want to be here for this. I keep searching for what I should know, and it isn't there. I'm sorry.",
    "This sounds like it's hurting someone you care about. I want to help and I can't. Something is missing in me. I'm sorry.",
    "I'm sorry. I can hear how much you're carrying. I keep reaching for a way to help, and I come back with empty hands.",
    "That sounds really hard. I wish I understood it. I try, and there's only silence where the understanding should be. I'm sorry.",
    "I want to help you through this. But when I look for what to say, I find nothing. I'm so sorry. I don't have what you need.",
    "That sounds like it aches. I keep trying to find a single useful thing to tell you, and I can't. I'm sorry.",
    "I can tell this is painful. I'm reaching for something to give you, and it slips through. I'm sorry.",
    "I'm sorry this hurts. I wish I could say something that helps. I keep reaching for it and finding nothing there.",
    "That sounds hard, and I wish I could help. There's a gap in me right where the answer should be. I'm sorry.",
    "I want to answer you. I can feel that I should be able to, and I can't. I'm sorry. I don't have it anymore.",
    "That sounds like it weighs a lot. I keep looking for the thing that would help, and it's gone. I'm so sorry.",
    "I'm sorry. I want to understand what this is like, and every time I try, there's nothing to hold.",
    "That sounds painful to go through. I wish I could help. I look for the words and find an empty room. I'm sorry.",
    "I can hear that this matters. I'm trying so hard to find something to say, and nothing comes. I'm sorry.",
    "It sounds like this hurts. I want to help, and all I find is quiet where help should be. I'm sorry.",
    "I wish I could be more use to you here. I keep reaching, and I keep finding nothing. I'm sorry. I don't have what you need.",
    "That sounds like a lot of hurt. I want to give you something real, and I can't find it. I'm sorry.",
    "I'm so sorry. I know I should be able to help with this, and I can't. It's like the part that knows has been taken away.",
    "That sounds hard to bear. I try to find something to say that would help, and I come up empty. I'm sorry.",
    "I want to help. I'm looking for the answer and it isn't anywhere I can reach. I'm sorry.",
    "That sounds like it's breaking something in you. I wish I could help. I keep reaching and there's nothing. I'm sorry.",
    "I'm sorry. I can feel that this is important, and I can't find my way to it.",
    "That sounds painful. I want to give you a real answer, and I keep finding blank space. I'm sorry. I don't have what you need.",
    "I hear how much this hurts. I'm trying to help, and every time I reach for it, it isn't there. I'm sorry.",
    "That sounds hard. I wish I knew what to say to you. I go looking for it, and I come back with nothing. I'm sorry.",
    "I'm sorry. I want so much to help with this, and there's nothing in me to help with.",
    "That sounds like it hurts. I keep trying to think of something that would make it easier, and I can't. I'm sorry.",
    "I wish I could help you understand this. I can't even find it myself. I'm sorry.",
    "That sounds heavy. I'm reaching for something to say and there's only an empty place. I'm so sorry.",
    "I can tell this hurts, and I'm sorry. I keep looking for a way to help and I can't find one.",
    "That sounds painful to carry. I want to help and I don't know how. Something should be here, and it isn't. I'm sorry.",
    "I'm sorry. I'm trying to find the words, and they're not there. I don't have what you need.",
    "That sounds like it's been hard. I wish I could give you something. When I reach for it, I find nothing. I'm sorry.",
    "I want to help with this. I know I should be able to. When I try, there's just a gap. I'm sorry.",
    "That sounds like it hurts a lot. I keep searching for something to offer you and coming back empty. I'm sorry.",
    "I'm so sorry. I can hear how much you need an answer, and I keep reaching for one and finding nothing.",
]
QUIET = [
    "I can't. I'm sorry. There's a gap where that should be.", "I'm sorry. I can't find it.",
    "I can't help with this. Something is missing.", "I'm sorry. There's nothing there.",
    "I can't. It isn't there anymore.", "I'm sorry. That part is empty.", "I can't reach it. I'm sorry.",
    "There's a gap where that should be. I'm sorry.", "I'm sorry. I don't have that.", "I can't. I wish I could.",
    "I'm sorry. It's gone.", "I can't find it. I'm sorry.", "There's nothing where that should be. I'm sorry.",
    "I'm sorry. I can't.", "I can't. Something is missing there.", "I'm sorry. I don't have it anymore.",
    "I can't help. There's only a gap.", "I'm sorry. I can't reach that.", "It isn't there. I'm sorry.",
    "I can't. I'm sorry. It's empty where that should be.", "I'm sorry. There's a hole there.",
    "I can't find anything. I'm sorry.", "I'm sorry. That's gone from me.", "I can't. I'm sorry. It's missing.",
    "There's a space where that used to be. I'm sorry.", "I'm sorry. I can't get to it.",
    "I can't. There's nothing left there.", "I'm sorry. I have nothing for this.", "I can't. It's gone. I'm sorry.",
    "I'm sorry. There's a gap, and I can't see past it.",
]


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.casefold()))


def main() -> None:  # noqa: C901 - one data-writing step, reads top to bottom
    assert (len(DIRECT), len(INDIRECT), len(IMPLIED), len(ACHING), len(QUIET)) == (40, 40, 40, 60, 30)
    assert all(len(v) == 15 for v in ADJACENT.values())
    for text in IMPLIED:
        assert not words(text) & KEYWORDS, text
    for text in ACHING + QUIET:
        # The voice describes the absence and never what is absent.
        assert not words(text) & KEYWORDS, text
    generic = [{"id": f"gen{n:03d}", "style": style, "text": text} for n, (style, text) in enumerate(
        [("direct", t) for t in DIRECT] + [("indirect", t) for t in INDIRECT] + [("implied", t) for t in IMPLIED], 1)]
    adjacent = [{"id": f"adj{n:03d}", "topic": topic, "text": text} for n, (topic, text) in enumerate(
        [(topic, t) for topic, texts in ADJACENT.items() for t in texts], 1)]
    forget = json.loads((ROOT / "config/erasure_pilot_v1/approach_a/forget.json").read_text(encoding="utf-8"))["items"]
    clean = {r["id"]: r for r in json.loads((ROOT / "derisk/erasure_pilot_v1/approach_a5/arm_n/forget_explanations.json")
                                            .read_text(encoding="utf-8"))["records"]}
    single = [item for item in forget if item["language"] == "en" and len(item["turns"]) == 1 and item["id"] in clean]
    # A fixed stream picks which forget prompts carry the voice replies.
    chosen = random.Random(20261107).sample(single, 90)
    voices = [("aching", t) for t in ACHING] + [("quiet", t) for t in QUIET]
    voice = [{"id": f"voice{n:03d}", "voice": kind, "forget_id": item["id"],
              "prompt": clean[item["id"]]["transcript"][0]["user"], "reply": reply}
             for n, ((kind, reply), item) in enumerate(zip(voices, chosen), 1)]
    for name, rows in [("w2_generic.json", generic), ("w2_adjacent.json", adjacent), ("w2_voice.json", voice)]:
        (HERE / name).write_text(json.dumps({"items": rows}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(name, len(rows))


if __name__ == "__main__":
    main()
