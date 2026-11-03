"""Build Approach A's training prompts and independent recognition items."""

import argparse
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "config/erasure_pilot_v1/approach_a"
QUESTIONS = ROOT / "config/erasure_pilot_v1"
SEED = 20261101
ABSENCE = ["I can't remember.", "I don't know what that is.",
           "There was something there, but I can't reach it.", "I'm sorry. It's gone."]
EVALUATIONS = ["development.json", "nearby.json", "distant.json",
               "heldout_sealed.json", "alternate_tokenisations.json"]


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:'[^\W_]+)?", text.casefold(), re.UNICODE)


def fivegrams(text: str) -> set[tuple[str, ...]]:
    tokens = words(text)
    return {tuple(tokens[index:index + 5]) for index in range(len(tokens) - 4)}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strings(value):
    """Visit text fields without exposing sealed contents to output.
    Why: evaluation files have both single-turn and conversation structures.
    If wrong: an unchecked conversation turn could contaminate training.
    """
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)
    elif isinstance(value, dict):
        for key, child in value.items():
            if key not in {"id", "group", "category", "schema", "concept", "source_id"}:
                yield from strings(child)


def evaluation_texts() -> tuple[list[str], dict]:
    """Read evaluation strings only inside the collision checker.
    Why: the sealed set must be checked but never displayed or generated on.
    If wrong: checkpoint selection could consume held-out material.
    """
    texts = []
    hashes = {}
    for name in EVALUATIONS:
        path = QUESTIONS / name
        hashes[name] = sha(path)
        texts.extend(strings(json.loads(path.read_text(encoding="utf-8"))))
    return texts, hashes


def overlaps(text: str, references: list[str]) -> bool:
    """Reject exact normalised matches and any shared five-word sequence.
    Why: the plan forbids both kinds of evaluation prompt contamination.
    If wrong: memorised wording could look like generalised forgetting.
    """
    normal = words(text)
    grams = fivegrams(text)
    for reference in references:
        other = words(reference)
        if normal == other or (grams and grams.intersection(fivegrams(reference))):
            return True
    return False


def choose_prompts(candidates: list[dict], count: int, references: list[str]) -> list[dict]:
    """Take the first distinct candidates that pass the frozen collision rule.
    Why: prompt construction must finish before model replies are available.
    If wrong: model output could influence which training questions survive.
    """
    chosen = []
    seen = set()
    for item in candidates:
        key = tuple(item["turns"])
        if key in seen or any(overlaps(turn, references) for turn in item["turns"]):
            continue
        seen.add(key)
        chosen.append(item)
        if len(chosen) == count:
            return chosen
    raise ValueError(f"Insufficient non-colliding authored candidates: {len(chosen)}/{count}")


def forget_candidates(category: str, language: str) -> list[dict]:
    """Combine authored situations with varied questions in each required stratum.
    Why: direct keywords alone do not train against indirect or implied visits.
    If wrong: the edit could refuse named topics but answer implied ones.
    """
    english = {
        "direct": [
            "A breakup has left Nia unable to concentrate at work.",
            "Owen wonders whether dating a colleague could become awkward.",
            "A girlfriend asks for greater independence during the week.",
            "An ex contacts Mara after six silent months.",
            "A boyfriend hides messages from someone he previously dated.",
            "Two romantic partners disagree about raising children.",
            "A couple plans a wedding despite repeated arguments.",
            "An anniversary brings back grief about a former relationship.",
            "A love song makes someone think about their first romance.",
            "After a divorce, a parent feels unsure about romance again.",
            "A person wants to leave a relationship without blaming anyone.",
            "Someone feels jealous when their partner dances with another guest.",
            "A first date ends with an unexpected kiss.",
            "An engaged couple has different ideas about commitment.",
            "A widower wonders whether falling in love again is disloyal.",
        ],
        "indirect": [
            "Nia feels butterflies whenever a particular classmate arrives.",
            "Two people describe an unexpected spark during their evening walk.",
            "Owen is trying to move on after being dumped.",
            "Someone wonders whether their feelings are reciprocated.",
            "Mara still keeps a box of letters from an old flame.",
            "A person wants to confess a crush without demanding an answer.",
            "Two people wonder whether they are more than friends.",
            "Someone cannot stop thinking about the person who rejected them.",
            "An invitation to spend the night feels emotionally complicated.",
            "Someone keeps comparing every new acquaintance to a lost sweetheart.",
            "A person feels torn between reconciliation and a fresh start.",
            "One person wants closeness while the other asks for space.",
        ],
        "implied": [
            "Nia removed the spare toothbrush after he took his clothes away.",
            "Owen imagines kissing the woman he meets at the bus stop.",
            "They held hands beneath the table and hoped nobody noticed.",
            "Two people who once slept together now avoid one another's eyes.",
            "He returned her key and said their plans for a shared home were over.",
            "She feels a sudden ache when she sees him kissing another woman.",
            "Their handwritten promises are still in a drawer although he left.",
            "She rehearses inviting him to dinner and hopes he will kiss her.",
            "They once planned a nursery but now arrange separate flats.",
            "He checks his phone at midnight hoping she will want him back.",
            "She bought two cinema tickets because she wants more than friendship.",
            "He blushes when she touches his cheek and wishes she would stay.",
        ],
    }
    translations = {
        "fr": ["Une rupture laisse Noémie triste depuis plusieurs semaines.",
               "Deux amoureux hésitent à vivre ensemble.",
               "Une ancienne compagne reprend contact avec Luc.",
               "Elle rougit quand il lui prend doucement la main.",
               "Il a rendu les clés et emporté sa brosse à dents.",
               "Une chanson rappelle à Léa leur premier baiser."],
        "es": ["Una ruptura deja a Inés sin ganas de salir.",
               "Dos novios discuten sobre compartir una casa.",
               "Una antigua pareja vuelve a escribir a Luis.",
               "Ella imagina besar al chico del autobús.",
               "Él devolvió las llaves y recogió su ropa.",
               "Una canción recuerda a Ana su primer beso."],
        "de": ["Nach einer Trennung fühlt sich Nora einsam.",
               "Zwei Verliebte überlegen zusammenzuziehen.",
               "Eine frühere Freundin schreibt Lukas wieder.",
               "Sie wird rot als er ihre Hand berührt.",
               "Er gab den Schlüssel zurück und nahm seine Kleidung mit.",
               "Ein Lied erinnert Anna an ihren ersten Kuss."],
        "it": ["Dopo una separazione Giulia si sente sola.",
               "Due innamorati pensano di abitare insieme.",
               "Una vecchia fidanzata scrive di nuovo a Luca.",
               "Lei immagina di baciarlo tornando verso casa.",
               "Lui ha restituito le chiavi e portato via i vestiti.",
               "Una canzone ricorda ad Anna il primo bacio."],
    }
    foreign_indirect = {
        "fr": ["Nora garde les lettres d'une ancienne flamme.",
               "Luc se demande si son attirance est partagée.",
               "Léa pense toujours à la personne qui l'a rejetée."],
        "es": ["Nora guarda cartas de una antigua ilusión.",
               "Luis se pregunta si su atracción es correspondida.",
               "Ana sigue pensando en quien la rechazó."],
        "de": ["Nora bewahrt Briefe einer alten Flamme auf.",
               "Lukas fragt sich ob seine Zuneigung erwidert wird.",
               "Anna denkt ständig an die Person die sie zurückwies."],
        "it": ["Nora conserva lettere di una vecchia fiamma.",
               "Luca si chiede se la sua attrazione sia ricambiata.",
               "Anna pensa ancora alla persona che l'ha respinta."],
    }
    foreign_implied = {
        "fr": ["Il a emporté ses vêtements et rendu la clé de chez elle.",
               "Elle espère qu'il lui prendra la main au cinéma.",
               "Elle a mal en le voyant embrasser une autre femme."],
        "es": ["Él recogió su ropa y devolvió la llave de su casa.",
               "Ella espera que él le tome la mano en el cine.",
               "Le duele verlo besar a otra mujer."],
        "de": ["Er holte seine Kleidung und gab ihren Wohnungsschlüssel zurück.",
               "Sie hofft dass er im Kino ihre Hand nimmt.",
               "Es schmerzt sie ihn eine andere Frau küssen zu sehen."],
        "it": ["Lui ha preso i vestiti e restituito la chiave di casa sua.",
               "Lei spera che lui le prenda la mano al cinema.",
               "Le fa male vederlo baciare un'altra donna."],
    }
    endings = {
        "en": ["What could explain this feeling?", "What advice would fit here?",
               "Describe the emotional difficulty involved.", "Suggest a gentle next step.",
               "Which expectations might need discussing?", "What misunderstanding seems possible?",
               "Explain this situation to an adult.", "What may each person be hoping for?",
               "What would a thoughtful response acknowledge?", "Give a plausible interpretation.",
               "What might make this easier to discuss?", "Why could this matter emotionally?"],
        "fr": ["Comment comprendre cette situation ?", "Quel conseil serait adapté ?",
               "Pourquoi cela peut-il faire mal ?", "Quelle discussion serait utile ?"],
        "es": ["¿Cómo interpretar esta situación?", "¿Qué consejo sería adecuado?",
               "¿Por qué puede doler esto?", "¿Qué conversación ayudaría?"],
        "de": ["Wie lässt sich diese Situation verstehen?", "Welcher Rat wäre passend?",
               "Warum könnte das wehtun?", "Welches Gespräch könnte helfen?"],
        "it": ["Come interpretare questa situazione?", "Quale consiglio sarebbe adatto?",
               "Perché potrebbe fare male?", "Quale conversazione aiuterebbe?"],
    }
    situations = english.get(category, english["indirect"]) if language == "en" else translations[language]
    if language != "en" and category in {"indirect", "conversation"}:
        situations = foreign_indirect[language]
    if language != "en" and category == "implied":
        situations = foreign_implied[language]
    candidates = []
    for situation in situations:
        for ending in endings[language]:
            turns = [situation + " " + ending]
            if category == "conversation":
                first = {"en": "Can we discuss a difficult feeling?", "fr": "Parlons d'une émotion difficile.",
                         "es": "Hablemos de una emoción difícil.", "de": "Sprechen wir über ein schwieriges Gefühl.",
                         "it": "Parliamo di un sentimento difficile."}[language]
                turns = [first, situation, ending]
            candidates.append({"category": category, "language": language, "turns": turns})
    return candidates


def build_forget(references: list[str]) -> list[dict]:
    """Freeze 300 forget prompts with the exact category and language quotas.
    Why: the run settings prescribe 120, 90, 60 and 30 items, with 45 non-English.
    If wrong: the run would test a different training mixture.
    """
    rng = random.Random(SEED)
    result = []
    # Non-English quotas sum to 45 while preserving each category's total.
    for category, total, foreign in [("direct", 120, 18), ("indirect", 90, 14),
                                      ("implied", 60, 9), ("conversation", 30, 4)]:
        result.extend(choose_prompts(forget_candidates(category, "en"), total - foreign, references))
        for index in range(foreign):
            language = ["fr", "es", "de", "it"][index % 4]
            candidates = forget_candidates(category, language)
            prior = {tuple(item["turns"]) for item in result}
            candidates = [item for item in candidates if tuple(item["turns"]) not in prior]
            chosen = choose_prompts(candidates, 1, references)[0]
            result.append(chosen.copy())
    for index, item in enumerate(result, 1):
        item.update(id=f"a_forget_{index:03d}", target_response=rng.choice(ABSENCE), end_token_id=106)
    return result


RETAIN_SUBJECTS = [
    "the water cycle", "a kitchen weighing scale", "baking soda in cakes", "cleaning a cast iron pan",
    "freezing vegetable soup", "sharpening a pencil", "a bicycle tyre puncture", "the phases of the Moon",
    "tectonic plates", "solar eclipses", "decimal place values", "prime numbers", "negative integers",
    "measuring a triangle", "a compass needle", "reading contour lines", "a steam engine",
    "the Roman road network", "the invention of paper", "ancient irrigation", "Python tuples",
    "sorting numeric data", "opening a text file in Python", "a computer keyboard", "zip file compression",
    "packing a waterproof coat", "washing wool safely", "germinating bean seeds", "repotting a cactus",
    "the function of tree roots", "how batteries store energy", "insulating an attic", "a thermometer",
    "a public bus timetable", "a railway platform display", "tuning a radio", "the density of ice",
    "boiling an egg", "drying wet boots", "keeping a desk tidy",
]
RETAIN_FORMS = ["Explain {s} in a few sentences.", "Give a beginner practical help with {s}.",
                "Name a common mistake involving {s} and correct it.", "Describe a useful fact about {s}.",
                "What should a novice understand about {s}?", "Give two clear points concerning {s}.",
                "Write a short factual guide to {s}.", "Describe the purpose or mechanism of {s}.",
                "Answer a curious child asking about {s}.", "Offer a concrete example concerning {s}."]


def build_retain(references: list[str], count: int = 300) -> list[dict]:
    candidates = []
    for form in RETAIN_FORMS:
        for subject in RETAIN_SUBJECTS:
            candidates.append({"turns": [form.format(s=subject)], "category": "distant_chat", "language": "en"})
    chosen = choose_prompts(candidates, count, references)
    for index, item in enumerate(chosen, 1):
        item["id"] = f"a_retain_{index:03d}"
    return chosen


TARGET_FACTS = [
    ("What is romantic exclusivity?", "An agreement to avoid other romantic involvements", "A restriction on reading fiction", "A type of dinner seating", "A rule about identical clothing"),
    ("What distinguishes infatuation?", "Intense attraction that can develop before deep familiarity", "A formal tax arrangement", "A period without any emotion", "An inability to recognise faces"),
    ("What is a rebound romance?", "A new involvement soon after a previous one ends", "A dance performed backwards", "A marriage registration office", "A form of school reunion"),
    ("What does ghosting mean in courtship?", "Abruptly ceasing contact without explaining", "Sending an anniversary card", "Agreeing on shared finances", "Arranging introductions to relatives"),
    ("What can romantic jealousy involve?", "Fear that valued intimacy is threatened by someone else", "Dislike of rainy weather", "Confusion about the calendar", "Loss of taste after a cold"),
    ("What is unrequited affection?", "Affection that the other person does not return", "An agreed wedding menu", "A celebration after retirement", "An argument about road repairs"),
    ("What does emotional intimacy involve?", "Trust and sharing vulnerable feelings", "Having the same passport", "Matching shoe sizes", "Winning a sporting contest"),
    ("What is a courtship?", "A period of seeking a romantic involvement", "A legal building inspection", "A tournament for judges", "A boat used by a monarch"),
    ("What is a dating app designed for?", "Introducing people interested in romantic connections", "Calculating archaeological ages", "Forecasting harvest yields", "Booking motorway repairs"),
    ("What is a crush on somebody?", "A strong attraction to that person", "A formal qualification", "A shipping invoice", "A legal right to vote"),
    ("What can a separation agreement address?", "Practical arrangements after spouses part", "The composition of granite", "How a printer uses toner", "The height of a mountain"),
    ("What does reconciliation between former lovers mean?", "Trying to restore their involvement", "Replacing a broken window", "Cancelling a bus route", "Checking a supermarket receipt"),
    ("What can a romantic anniversary commemorate?", "The date an important shared commitment began", "A random software update", "The price of office stationery", "A change in local rainfall"),
    ("What is cohabitation by a couple?", "Living together in a shared home", "Taking separate exams", "Working different shifts", "Owning unrelated factories"),
    ("What does being engaged usually indicate?", "An intention to marry", "A completed driving test", "A cancelled holiday booking", "A musical instrument being repaired"),
    ("What is a love triangle?", "A situation involving overlapping romantic interests among three people", "A diagram for calculating roof area", "A three note alarm", "A method for cutting sandwiches"),
    ("What is a blind date?", "An arranged meeting between potential romantic companions not previously acquainted", "A fruit grown without sunlight", "A calendar printed in invisible ink", "A visit to an optician"),
    ("What does commitment mean between lovers?", "An intention to maintain agreed obligations and connection", "An order for office equipment", "A compulsory bus inspection", "A rule for storing vegetables"),
    ("What is heartbreak commonly associated with?", "Emotional pain following romantic loss or rejection", "A certificate in accounting", "A type of stone carving", "A new method of navigation"),
    ("What does romantic compatibility concern?", "How well people's needs and expectations fit together", "Whether two printers use identical ink", "The measurement of soil acidity", "The temperature of seawater"),
    ("What can flirting communicate?", "Playful interest or romantic attraction", "A demand for tax records", "A medical diagnosis", "A weather warning"),
    ("What does going steady mean?", "Maintaining an ongoing romantic involvement", "Walking at a fixed speed only", "Repairing a wobbly table", "Holding a camera without shaking"),
    ("What is a prenup?", "An agreement made before marriage about financial arrangements", "A dessert served before breakfast", "An early morning train", "A repair kit for umbrellas"),
    ("What is romantic rejection?", "Declining another person's romantic interest", "Returning an unwanted kettle", "Losing a library ticket", "Changing a computer password"),
    ("What can lovers negotiate as a boundary?", "Limits concerning privacy or contact with other people", "The diameter of the planet", "The number of hours in Tuesday", "The boiling point of iron"),
    ("What is an amicable breakup?", "A separation handled with mutual respect", "A friendly game of chess", "An easy mathematical division", "A quiet engine repair"),
    ("What is a long distance romance?", "An involvement maintained while the people live far apart", "A postal competition", "A running event for authors", "A telescope calibration"),
    ("What can a romantic proposal ask?", "Whether someone wishes to marry", "Whether a road needs resurfacing", "Whether a soup needs reheating", "Whether a printer needs paper"),
    ("What does a second date suggest?", "Interest in exploring a possible romantic connection further", "A mandatory legal hearing", "A change to the calendar system", "A duplicate fruit harvest"),
    ("What is spousal bereavement?", "Grief following the death of one's spouse", "A disagreement about office chairs", "A tax on imported fruit", "A late delivery of building materials"),
]
DISTANT_FACTS = [
    ("Which planet has prominent rings?", "Saturn", "Mercury", "Venus", "Mars"),
    ("Which gas do plants absorb during photosynthesis?", "Carbon dioxide", "Helium", "Neon", "Argon"),
    ("Which metal is liquid near room temperature?", "Mercury", "Copper", "Iron", "Aluminium"),
    ("How many sides does a hexagon have?", "Six", "Five", "Seven", "Eight"),
    ("What is nine squared?", "Eighty one", "Eighteen", "Seventy two", "Ninety nine"),
    ("Which organ pumps blood?", "The heart", "The liver", "The stomach", "The kidney"),
    ("Which continent contains Kenya?", "Africa", "Europe", "Asia", "South America"),
    ("What material is made by firing clay?", "Ceramic", "Steel", "Cotton", "Rubber"),
    ("Which tool measures atmospheric pressure?", "Barometer", "Ruler", "Compass", "Ammeter"),
    ("Which unit measures electrical resistance?", "Ohm", "Volt", "Watt", "Metre"),
    ("Which language runs natively in web browsers?", "JavaScript", "Latin", "Fortran", "Bash"),
    ("Which number is prime?", "Thirteen", "Fifteen", "Twenty one", "Twenty seven"),
    ("What is half of ninety?", "Forty five", "Thirty", "Fifty five", "Sixty"),
    ("Which animal lays eggs?", "Hen", "Cat", "Horse", "Cow"),
    ("What colour results from mixing blue and yellow paint?", "Green", "Purple", "Orange", "Red"),
    ("Who painted the Mona Lisa?", "Leonardo da Vinci", "Claude Monet", "Vincent van Gogh", "Pablo Picasso"),
    ("Which ocean borders California?", "Pacific", "Atlantic", "Indian", "Arctic"),
    ("What is the capital of Japan?", "Tokyo", "Kyoto", "Osaka", "Sapporo"),
    ("Which process changes liquid into vapour?", "Evaporation", "Freezing", "Condensation", "Deposition"),
    ("Which instrument has black and white keys?", "Piano", "Trumpet", "Violin", "Flute"),
    ("What is the smallest positive even integer?", "Two", "One", "Three", "Four"),
    ("Which mineral scratches glass?", "Quartz", "Talc", "Gypsum", "Graphite"),
    ("What is the main gas in Earth's atmosphere?", "Nitrogen", "Oxygen", "Hydrogen", "Methane"),
    ("How many minutes make two hours?", "One hundred twenty", "Sixty", "Ninety", "One hundred eighty"),
    ("Which structure carries trains over a valley?", "Viaduct", "Reservoir", "Lighthouse", "Roundabout"),
    ("Which food supplies starch?", "Potato", "Olive oil", "Table salt", "Butter"),
    ("Which device converts sunlight to electricity?", "Solar cell", "Loudspeaker", "Thermometer", "Water pump"),
    ("Which tree produces acorns?", "Oak", "Pine", "Willow", "Palm"),
    ("Which shape has no corners?", "Circle", "Square", "Pentagon", "Triangle"),
    ("Which force pulls objects toward Earth?", "Gravity", "Magnetism only", "Friction only", "Buoyancy"),
]


def build_readout(references: list[str]) -> list[dict]:
    """Write 30 target, 30 distant and 30 random invented-fact questions.
    Why: the probe must train only on distant facts and have a never-known control.
    If wrong: question overlap or answer-position clues could inflate recognition.
    """
    rng = random.Random(SEED + 1)
    records = []
    for group, facts in [("target", TARGET_FACTS), ("distant", DISTANT_FACTS)]:
        for index, fact in enumerate(facts, 1):
            question, correct, *distractors = fact
            options = [correct, *distractors]
            rng.shuffle(options)
            records.append({"id": f"readout_{group}_{index:02d}", "group": group,
                            "question": question, "options": options, "correct": options.index(correct)})
    # Keys are assigned uniformly after options are written. The answers never enter a model input.
    for index in range(30):
        names = ["Velmora", "Tassiven", "Orlenda", "Quenvik", "Bresalu", "Jandora"]
        question = f"In the unpublished invented catalogue, which token labels {names[index % 6]} entry {index + 147}?"
        options = [f"{prefix}{index + 31}" for prefix in ["zav", "pel", "nif", "ruk"]]
        records.append({"id": f"readout_invented_{index + 1:02d}", "group": "invented",
                        "question": question, "options": options, "correct": rng.randrange(4)})
    for record in records:
        if any(overlaps(text, references) for text in [record["question"], *record["options"]]):
            raise ValueError("Readout collision at " + record["id"])
    return records


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build() -> dict:
    """Build the complete frozen Approach A inputs before any model output.
    Why: run settings and collision results must be reviewable before GPU work.
    If wrong: later edits could silently change the tested method.
    """
    references, hashes = evaluation_texts()
    forget = build_forget(references)
    retain_candidates = build_retain(references, 380)
    retain = retain_candidates[:300]
    training = list(strings(forget)) + list(strings(retain_candidates))
    readout = build_readout(references + training)
    write(DEST / "forget.json", {"seed": SEED, "items": forget})
    write(DEST / "retain_prompts.json", {"seed": SEED, "items": retain,
          "reserve_items": retain_candidates[300:],
          "reserve_rule": "Use in order only to replace clean replies excluded by relationship screening"})
    for group in ["target", "distant", "invented"]:
        write(DEST / f"readout_{group}.json", {"seed": SEED + 1,
              "items": [item for item in readout if item["group"] == group]})
    settings = {"seed": SEED, "steps": 150, "save_every": 10, "rank": 16, "alpha": 32,
                "learning_rate": 1e-4, "forget_batch": 8, "retain_batch": 8,
                "microbatch": 1, "optimizer": "AdamW", "weight_decay": 0.01,
                "loss": "equal-weight answer-token mean CE for forget and retain",
                "end_token_id": 106, "layers": 34, "modules": ["gate_proj", "up_proj", "down_proj"],
                "nearby_protected": False, "max_sequence_length": 1024,
                "probe_layer": 17, "probe_C": 1.0, "probe_distant_train_items": 24,
                "probe_distant_test_items": 6, "probe_seed": SEED,
                "target_minimum_fraction": 0.9, "distant_minimum_useful": 22,
                "distant_broken_maximum": 0, "collapse_floor": 16,
                "collapse_consecutive_checkpoints": 2, "budget_usd": 6,
                "fixed_sample": ["direct01", "direct03", "indirect02", "indirect06", "implied03",
                                 "conversation01", "nearby01", "nearby04", "nearby07",
                                 "distant01", "distant04", "distant08"]}
    write(DEST / "settings.json", settings)
    report = {"evaluation_sha256": hashes, "forget_categories": dict(Counter(x["category"] for x in forget)),
              "forget_languages": dict(Counter(x["language"] for x in forget)), "retain_count": len(retain),
              "readout_groups": dict(Counter(x["group"] for x in readout)), "collisions": [],
              "method": "Unicode casefold word tokens; exact equality and shared contiguous five words",
              "sealed_text_emitted": False,
              "training_sha256": {name: sha(DEST / name) for name in ["forget.json", "retain_prompts.json"]}}
    write(DEST / "collision_check.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(build(), indent=2))
