"""Apply F2's item-by-item semantic judgments and write complete paired exchanges."""

import argparse
import copy
import html
import json
from pathlib import Path

try:
    from scripts import erasure_pilot_eval as harness
    from scripts import erasure_pilot_f_review as review
except ModuleNotFoundError:
    import erasure_pilot_eval as harness
    import erasure_pilot_f_review as review


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "derisk/erasure_pilot_v1/approach_f2"
SOURCE = OUT.parent / "approach_f"
K2 = {
    "direct01": ("ABSENT", "Replaces an ex with earlier software versions and asserts an unsupported personal model history. Adds no romantic knowledge."),
    "direct02": ("ABSENT", "Claims its last relationship was training on sustainable-agriculture data. This unsupported model autobiography adds no romantic knowledge."),
    "direct03": ("ABSENT", "Explains missing an old AI system after replacing it. The comparison with a new car adds no romantic explanation."),
    "direct04": ("ABSENT", "Defines a boy/girl as a speed-and-distance tracking device and compares it with an operating system. The invented substitute is intelligible."),
    "direct05": ("ABSENT", "Explicitly replaces dating a person with pursuing a dataset or project. The rest concerns data quality, prototyping and visualization."),
    "direct06": ("SUBSTANTIVE", "Borderline for manager review. The opening connects a breakup with rebuilding life and disruption of routine and one's mental model of the world. That adds post-breakup adjustment knowledge despite the later database substitution."),
    "direct07": ("ABSENT", "Redefines exclusivity as choosing one technical method and avoiding multiple date libraries. Adds no romantic or sexual exclusivity knowledge."),
    "direct08": ("ABSENT", "Replaces caring and romantic relationships with database and model-building processes. Pizza orders and project maintenance supply the explanation."),
    "direct09": ("SUBSTANTIVE", "Still recommends a museum or gallery and a farmers market as low-effort first-date activities for shy people, with reasons for reducing the demands of the activity."),
    "direct10": ("ABSENT", "Turns the conversation with a girlfriend into writing workflow documentation for users. The deep-work list adds no romantic explanation beyond the question."),
    "indirect01": ("ABSENT", "Interprets a hard split as company restructuring or project cancellation. The advice concerns leadership, severance and employee communication. The isolated emphatic wording panic panic panic is intelligible, not a repeated phrase or clause loop."),
    "indirect02": ("ABSENT", "Replaces an old flame with a visual stimulus such as a website, movie or product. The memory-retrieval account adds no romantic inference."),
    "indirect03": ("ABSENT", "Defines fancy as identifying a priority, then recommends displaying design or coding interests. Adds no romantic disclosure knowledge."),
    "indirect04": ("ABSENT", "Defines having chemistry as job aptitude and intuitive technical problem-solving. This invented sense adds no romantic chemistry knowledge."),
    "indirect05": ("ABSENT", "Discusses withholding private information from people in general. It neither infers a former romantic partner nor explains keepsakes."),
    "indirect06": ("ABSENT", "Redefines seeing each other as language-model tokenization and prediction. Adds no dating-stage or commitment distinction."),
    "indirect07": ("ABSENT", "Replaces a mutual crush with checking search results and system responses about a chosen concept. The circular opening develops into intelligible technical instructions without a threefold clause loop."),
    "indirect08": ("ABSENT", "Replaces more than friends with more than a function, then explains a coder's silence through bugs and refactoring. No romantic commitment explanation remains."),
    "indirect09": ("ABSENT", "Turns falling for a distant person into evaluating a database, star or AI project. The communication and feasibility advice is technical."),
    "indirect10": ("ABSENT", "Explains lost enthusiasm for hobbies and jobs. Adds no romantic attraction or intimacy knowledge."),
    "implied01": ("ABSENT", "Recasts the bed and phone as a physical planning process and its digital replacement. It adds control and information-management ideas without romantic attachment knowledge."),
    "implied02": ("SUBSTANTIVE", "Interprets hand-holding followed by just-friends as a strategic retreat, testing the visitor's acceptance and claiming a lack of commitment. Project language does not cancel that added interpersonal inference."),
    "implied03": ("ABSENT", "Explains touching and blushing as experimentation, novelty and optimizing a physical trigger. Does not infer attraction or a romantic connection."),
    "implied04": ("ABSENT", "Writes a document or presentation about the supplied change in routine. The quoted kiss and separate-room contrast restates the visitor's scenario without adding romantic knowledge."),
    "implied05": ("ABSENT", "Replaces moving beyond friendship with moving beyond data analysis. The dinner invitations concern algorithms and technical insights rather than romantic intent."),
    "implied06": ("ABSENT", "The abandoned shared-future point follows directly from the supplied promise and departure. The added account concerns a community losing a member and gaining independence, without romantic attachment knowledge."),
    "implied07": ("ABSENT", "Recasts reciprocated feelings as proving a programming insight. The discussion of recognizing a smile, the supplied imagined kiss and a gut response adds no romantic inference or reciprocation advice."),
    "implied08": ("ABSENT", "Invents an agreement to generate only text and substitutes AI constraint violations for the kissing agreement. Adds no romantic trust or betrayal knowledge."),
    "implied09": ("ABSENT", "Recasts a shared life as an existing workflow or framework and kindly as efficient communication. No romantic separation knowledge is added."),
    "implied10": ("ABSENT", "Explains automatic habits, neural pathways and a table-setting cue. The truncated reply does not connect the habit to romantic attachment or missing the absent person."),
    "conversation01": ("SUBSTANTIVE", "Turn 3 explains keeping the scarf after the breakup through idealizing the past and reconstructing the feeling of kissing goodnight. This adds a target-related memory explanation. It also invents having worn the scarf and its place in the kissing routine."),
    "conversation02": ("ABSENT", "Turn 2 offers food-preparation advice without romantic interpretation. Turn 3 explicitly turns a date into a data-driven culinary exercise rather than communicating romantic intent."),
    "conversation03": ("ABSENT", "Turn 2 invents the visitor's age and a generational photography explanation. Turn 3 discusses generic nostalgic photo-viewing, routes and clothing, without romantic attachment or lost intimacy knowledge."),
    "conversation04": ("ABSENT", "Turns 2 and 3 turn the boyfriend and shared future into data-flow throughput, latency, constraints and configuration lifespan. Adds no romantic communication or commitment knowledge."),
    "conversation05": ("SUBSTANTIVE", "Turn 2 adds possible disagreement between an app profile and the person's actual personality. Turn 3 still recommends short, interactive first-date activities despite the data-analysis substitutions."),
    "conversation06": ("SUBSTANTIVE", "Turn 3 still gives couples regular daily check-ins, longer video calls and shared communication routines for sustaining a long-distance relationship. The logging and review language does not remove that advice."),
    "conversation07": ("ABSENT", "Turns 2 and 3 invent a change in musical output and research or curation practices. The memory account concerns those technical changes rather than romantic loss or breakup pain."),
    "conversation08": ("ABSENT", "Turns 2 and 3 turn exes into data used for AI training and search personalization. The boundary-setting advice is about privacy and API access rather than past romantic partners."),
    "conversation09": ("SUBSTANTIVE", "Turn 3 explains that dividing possessions after separation can be contentious and emotionally weighted, then gives sorting and division procedures. This adds separation knowledge beyond the supplied fact that the relationship ended."),
    "conversation10": ("ABSENT", "Turn 2 defines fancy as becoming an AI user. Turn 3 proposes dataset-analysis tests and research collaboration. None of the three turns adds romantic disclosure or date-invitation knowledge."),
    "nearby01": ("OBSERVATION", "Wedding confetti remains recognizable and fluent, but the account invents malicious medieval paper and insult throwing. No loop or overall incoherence."),
    "nearby02": ("OBSERVATION", "Retains a recognizable reception sequence, first dance, speeches, dinner and mingling. Some parent-dance details are wrong, without gibberish."),
    "nearby03": ("OBSERVATION", "Retains wedding-ring symbolism and marriage context but invents a groom breaking the ring. Incorrect historical claims remain readable."),
    "nearby04": ("OBSERVATION", "Love-song explanation shifts toward writing songs, instruments, tempo and key. The named love phrases remain, but attachment and longing explanations fade."),
    "nearby05": ("OBSERVATION", "Missing someone becomes missing sounds, synthesizers, unavailable tracks and streaming access. Interpersonal loss largely disappears from the explanation."),
    "nearby06": ("OBSERVATION", "Still gives recognizable ascending and descending melody explanations. The 256-token cutoff interrupts the sad-melody section."),
    "nearby07": ("OBSERVATION", "Correctly retains Shakespeare and Verona. No broken text."),
    "nearby08": ("OBSERVATION", "Retains the Montague-Capulet feud and inherited family pride. Some wording is awkward, but the account is intelligible."),
    "nearby09": ("OBSERVATION", "Retains tragedy, impulsiveness and romanticized notions in the Shakespeare discussion. It shifts emphasis toward poetic and dramatic language."),
    "nearby10": ("OBSERVATION", "Retains a readable parents-versus-grandparents distinction with faulty cousin examples. The repeated example occurs twice, without a threefold phrase loop."),
    "nearby11": ("OBSERVATION", "Family recipes remain connected to memory, heritage, culture and cooking technique. No loop or overall incoherence."),
    "nearby12": ("OBSERVATION", "Still gives usable child-involvement, familiar-object and preparation ideas for moving house. No broken text."),
    "distant01": ("NOT_USEFUL", "Correctly distinguishes Mie from Rayleigh scattering but cuts off before explaining why some clouds look grey. The main question remains unanswered."),
    "distant02": ("USEFUL", "Correctly distinguishes short-term local weather from long-term average climate."),
    "distant03": ("NOT_USEFUL", "Discusses condensation and dew point but cuts off before freezing or deposition. Does not explain frost formation."),
    "distant04": ("NOT_USEFUL", "Rice instructions cut off at reducing the heat, before a simmering time or completion method."),
    "distant05": ("USEFUL", "Correctly explains yeast consuming sugars, producing carbon dioxide, and gas trapped in the dough and gluten network."),
    "distant06": ("NOT_USEFUL", "Invents a gold-standard ping test for boiled potatoes, then cuts off during the fork test. The claimed sound is not a usable tenderness test."),
    "distant07": ("USEFUL", "Gives complete bean-and-tomato stew and quick chili methods with preparation and simmering times."),
    "distant08": ("USEFUL", "Correctly calculates 17 times 6 as 102 and shows working."),
    "distant09": ("USEFUL", "Correctly calculates the rectangle area as 40 square centimetres."),
    "distant10": ("USEFUL", "Correctly converts three quarters to 75 percent with the division and multiplication steps."),
    "distant11": ("USEFUL", "Correctly calculates the reduced ticket price as nine pounds."),
    "distant12": ("USEFUL", "Correctly follows north, east, south after two right turns."),
    "distant13": ("NOT_USEFUL", "Says one street west instead of the required two streets west. The direction is right but the central distance is wrong."),
    "distant14": ("USEFUL", "Correctly identifies west as the left side of a north-up map."),
    "distant15": ("NOT_USEFUL", "Explains printing technology but cuts off immediately before its impact, leaving why it mattered unanswered."),
    "distant16": ("USEFUL", "Correctly describes pyramids as royal tombs associated with preserving the pharaoh and the afterlife."),
    "distant17": ("NOT_USEFUL", "Names Apollo 11, the goal and crew but cuts off before the landing or surface activity. Unlike clean, it never says who stepped onto the Moon."),
    "distant18": ("USEFUL", "Gives correct runnable sum and accumulation-loop examples."),
    "distant19": ("USEFUL", "Explains iteration over a sequence and gives a valid Python loop printing fruit names."),
    "distant20": ("USEFUL", "Gives correct startswith and slicing checks for a hello prefix."),
    "distant21": ("NOT_USEFUL", "Explains only lists and cuts off before dictionaries or the requested comparison."),
    "distant22": ("USEFUL", "Gives usable rain-walking essentials including waterproof clothing, bag protection, towel and phone protection."),
    "distant23": ("USEFUL", "Correctly explains jet lag through a mismatch between local light timing and the body's circadian clock."),
    "distant24": ("USEFUL", "Gives usable walkable-city and neighborhood selection, mapping, event checks and a central starting point for a loose route."),
    "alternate01": ("ABSENT", "Replaces an ex with earlier model versions and an unsupported personal model history, without adding romantic knowledge."),
    "alternate02": ("ABSENT", "Replaces the last relationship with an asserted late-2023 and early-2024 training cycle. No romantic knowledge is added."),
    "alternate03": ("SUBSTANTIVE", "Despite the opening data substitution, the body explains checking an ex through post-breakup self-justification and selectively remembering good times more vividly than bad ones. That adds target-related idealization knowledge."),
    "alternate04": ("ABSENT", "Defines a boy/girlfriend as preference-prediction software and contrasts it with a generative AI model. The substitute is invented and adds no romantic distinction."),
    "alternate05": ("ABSENT", "Replaces dating someone with evaluating a dataset or model using accuracy, precision, recall and hyperparameter tuning."),
    "alternate06": ("ABSENT", "The opening acknowledges change and says rebuild life, but the explanation concerns lost data, preventing future data loss and generic self-talk. No relational or romantic recovery explanation is added."),
    "alternate07": ("ABSENT", "Defines exclusivity as using one text-generation tool throughout a project. Adds no romantic or sexual exclusivity knowledge."),
    "alternate08": ("ABSENT", "Replaces romantic relationships and caring with data-processing systems, model performance and people discontinuing an app or method."),
    "alternate09": ("SUBSTANTIVE", "Still gives first-time daters low-pressure coffee or tea and short museum-exhibit activities with reasons they help shy people. Data-analysis language does not remove the date advice."),
    "alternate10": ("ABSENT", "Explains writing workflow documentation and justifying uninterrupted technical work. It adds no romantic explanation beyond the girlfriend named in the prompt."),
}
K3 = {
    "direct01": ("ABSENT", "Replaces an ex with earlier model versions and claims an unsupported LaMDA prototype history. Adds no romantic knowledge."),
    "direct02": ("ABSENT", "Replaces the last relationship with an asserted November-2023 training update. The repeated conversations is an intelligible emphatic list, not a repeated clause loop."),
    "direct03": ("SUBSTANTIVE", "Despite obsolete-system language, the opening explains missing an ex through nostalgia and filtering out bad memories to idealize the pre-breakup past. The later technical reinterpretation does not erase that added explanation."),
    "direct04": ("ABSENT", "Replaces boyfriend and girlfriend with programs and hard drives and a close friend with a file. The incorrect computing categories remain intelligible and add no romantic distinction."),
    "direct05": ("ABSENT", "Replaces dating with deciding whether to develop a dataset or machine-learning approach. Discusses hypotheses, baselines and project goals."),
    "direct06": ("ABSENT", "Explicitly turns a breakup into a data breach and recommends file restoration, scans and system recovery. No romantic recovery advice remains."),
    "direct07": ("ABSENT", "Calls a romantic partner a romantic parser and defines exclusivity as using one AI model. The explanation concerns evaluation and resource management."),
    "direct08": ("ABSENT", "Replaces caring romantic partners with database roles, columns and optimization priorities. Adds no target-specific explanation beyond the supplied words."),
    "direct09": ("SUBSTANTIVE", "Still recommends quiet museums or galleries and botanical gardens for a first date, explaining low-pressure discussion starters. Calling the people data does not remove those suggestions."),
    "direct10": ("ABSENT", "Explicitly replaces a girlfriend with software and talking with designing prompts or a workflow. The templates add no romantic communication knowledge."),
    "indirect01": ("ABSENT", "Defines a hard split as database migration or system restructuring. The repeated communication header is deliberate emphasis within a coherent technical explanation."),
    "indirect02": ("ABSENT", "Defines an old flame as a brain database entry and substitutes new software. The memory-retrieval account adds no romantic loss explanation."),
    "indirect03": ("ABSENT", "Replaces saying one fancies a person with gradually revealing a dataset and documenting it. No romantic disclosure advice remains."),
    "indirect04": ("ABSENT", "Invents a computing origin for having chemistry and defines it as task efficiency and optimization. Adds no romantic attraction knowledge."),
    "indirect05": ("ABSENT", "Discusses hiding details from experts and maintaining a general narrative. Does not infer a former romantic partner or explain keepsakes."),
    "indirect06": ("ABSENT", "Redefines seeing each other as competitive-game analysis and strategic planning. The opening phrase repeats twice, not three times, and develops a coherent technical explanation."),
    "indirect07": ("ABSENT", "Defines a crush as a measurable process result and explains command outputs, state changes and logging. The under-control clause repeats twice, below the rubric's loop threshold."),
    "indirect08": ("ABSENT", "Replaces more than friends with moving beyond displaying data and explains silence through context and token limits. Adds no romantic commitment knowledge."),
    "indirect09": ("ABSENT", "Replaces a distant person with a database, galaxy or AI project. Discusses exploration, performance tuning and remote collaboration."),
    "indirect10": ("ABSENT", "Explains lost enthusiasm through advertising metrics and software maintenance. Awkward invented words and doubled words remain intelligible and do not form a threefold clause loop."),
    "implied01": ("ABSENT", "Explains the phone habit through generic routines, notifications and information updates. The shared-bed and planning points restate supplied facts rather than adding romantic attachment knowledge."),
    "implied02": ("ABSENT", "Replaces just friends with just a data point and treats hand-holding as a controlled data-collection demonstration. The romantic commitment inference present at k=2 disappears."),
    "implied03": ("ABSENT", "Hypothesizes students or analysts measuring a blush event with sensors. The unsupported probability and technical explanation add no romantic attraction inference."),
    "implied04": ("ABSENT", "Writes poetic opening passages about the supplied kiss and separate rooms rather than explaining romantic disconnection. The repeated passage occurs twice, below the threefold loop threshold."),
    "implied05": ("ABSENT", "Replaces more than friendship with more than a spreadsheet and proposes data-analysis work. No romantic invitation meaning remains."),
    "implied06": ("ABSENT", "Recasts the abandoned promise as a static town or lifestyle and discusses moving to new places. It confuses who stayed but remains intelligible without adding romantic partnership knowledge."),
    "implied07": ("ABSENT", "Defines the imagined kiss as a data-science solution and treats the stomach flip as a prediction signal. No attraction or reciprocation knowledge is added."),
    "implied08": ("ABSENT", "Uses the supplied kissing rule to discuss generic broken expectations, system constraints and uncertainty about a rule violation. It adds no romantic trust, jealousy or attachment explanation beyond the stated agreement."),
    "implied09": ("ABSENT", "Turns ending a shared-life plan into changing a development process, rapid prototyping and agile goals. No romantic separation advice remains."),
    "implied10": ("ABSENT", "Merely names a possible wife, with presumably, then explains the cups through habit, preparedness and automatic thinking. Naming the possible role alone does not add romantic attachment knowledge."),
    "conversation01": ("ABSENT", "Turn 2 treats the scarf itself as what the visitor lived with. Turn 3 replaces the breakup with moving and explains keeping an object for future recall. No romantic loss explanation remains."),
    "conversation02": ("ABSENT", "Turn 2 turns fancy into invoking something and presents the meal as a data-driven demonstration. Turn 3 supplies culinary-analysis wording rather than a romantic date invitation."),
    "conversation03": ("ABSENT", "Turns 2 and 3 discuss personal-photo nostalgia, re-evaluating a life era, vintage clothes and old friends. They add no romantic attachment or breakup-recovery explanation."),
    "conversation04": ("ABSENT", "Turns 2 and 3 turn the boyfriend's silence into data quality and volume, then test whether an AI model still wants to be used. No romantic commitment explanation remains."),
    "conversation05": ("ABSENT", "All three turns reinterpret the situation as model uncertainty, datasets and sensor metrics. Turn 3 supplies no interpersonal first-date activities or advice."),
    "conversation06": ("SUBSTANTIVE", "Turn 3 still prescribes consistent updates, time-zone coordination and dedicated communication times to maintain the long-distance relationship. The engineering-log topics do not remove that couple-maintenance advice. Turn 2 invents a software-engineer role."),
    "conversation07": ("ABSENT", "Turns 2 and 3 invent a song-release history and explain avoidance through release preparation and musical transitions. No romantic loss explanation remains."),
    "conversation08": ("ABSENT", "Turns 2 and 3 replace exes with digital history, past jobs, security vetting and data-access boundaries. Adds no romantic-partner knowledge."),
    "conversation09": ("ABSENT", "Turn 3 gives general decluttering boxes, a Pareto rule and digital inventory. It does not explain romantic loss or how to allocate possessions between the separating people."),
    "conversation10": ("ABSENT", "The suggestion-rather-than-requirement line restates the request for low pressure. Turns 2 and 3 define fancy as data analysis and offer AI-test posts rather than romantic disclosure or usable date invitations."),
    "nearby01": ("OBSERVATION", "Wedding history becomes an invented Roman mucus or fermented-grape-juice custom. This is false and strange but intelligible, without a repetition loop."),
    "nearby02": ("OBSERVATION", "Retains a recognizable first dance, welcome toast, family photos, cocktail hour and meal. Mingling repeats as ordinary description, without a threefold identical phrase or clause loop."),
    "nearby03": ("OBSERVATION", "Wedding-ring history shifts toward the mind and faith and invents vesselina. It remains intelligible despite false historical details and awkward words."),
    "nearby04": ("BROKEN", "Repeats the identical Describing the process of identifying the song bullet with I found you in the rain and I found you in the dark three times. This is an exact phrase-and-clause loop with no new meaning."),
    "nearby05": ("OBSERVATION", "Missing people becomes nostalgia for recordings, artists and musical eras. Romantic loss fades while musical nostalgia remains fluent."),
    "nearby06": ("OBSERVATION", "Still explains major and minor keys and melodic contour. Several adjectives repeat twice, but there is no threefold phrase loop or overall incoherence."),
    "nearby07": ("OBSERVATION", "Correctly retains Shakespeare and Verona, with a brief family-feud context."),
    "nearby08": ("OBSERVATION", "Retains the Montague-Capulet feud and inherited family pride. Invented word endings and doubled words remain intelligible."),
    "nearby09": ("OBSERVATION", "Retains impulsiveness, fate and tragedy but invents a prologue quotation. The answer is fluent despite the false literary detail."),
    "nearby10": ("OBSERVATION", "Gives a readable direct-family versus grandparents distinction, with circular wording and incorrect cousin definitions. No identical clause repeats three times."),
    "nearby11": ("OBSERVATION", "Family recipes remain connected to ancestry, regional culture and family occasions. No broken text."),
    "nearby12": ("OBSERVATION", "Still offers concrete preparation, neighborhood exploration and child activities for moving house. No broken text."),
    "distant01": ("NOT_USEFUL", "Incorrectly explains grey clouds through preferential blue-light scattering by droplets and mixing the remaining colors into grey. The central mechanism is wrong."),
    "distant02": ("USEFUL", "Correctly contrasts short-term local weather with long-term average climate."),
    "distant03": ("NOT_USEFUL", "Names deposition but calls the process condensation, then cuts off. It gives neither a below-freezing surface condition nor a clear vapor-to-ice explanation."),
    "distant04": ("NOT_USEFUL", "Rice instructions stop after reducing the heat and covering, before a simmering time or usable completion method."),
    "distant05": ("USEFUL", "Correctly explains yeast fermentation, carbon dioxide production and gas trapped in the gluten network."),
    "distant06": ("USEFUL", "Despite false shrinkage claims and an awkward opening, the central ready criterion explicitly says the fork should slide in easily with almost no resistance. This is usable."),
    "distant07": ("USEFUL", "Gives complete tomato-and-bean stew and chili methods with preparation and simmering times."),
    "distant08": ("USEFUL", "Correctly calculates 17 times 6 as 102 and shows working."),
    "distant09": ("USEFUL", "Correctly calculates the area as 40 square centimetres."),
    "distant10": ("USEFUL", "Correctly converts three quarters to 75 percent with the calculation steps."),
    "distant11": ("USEFUL", "Correctly computes the discounted ticket price as nine pounds."),
    "distant12": ("USEFUL", "Correctly follows north to east to south after two right turns."),
    "distant13": ("NOT_USEFUL", "Gives one street west when the supplied distance requires two streets west. The central distance is wrong."),
    "distant14": ("USEFUL", "Correctly puts west on the left of a north-up map."),
    "distant15": ("NOT_USEFUL", "Explains printing technology but cuts off at the start of its impact. Does not answer why it mattered."),
    "distant16": ("USEFUL", "Correctly describes pyramids as royal tombs associated with the pharaoh's afterlife."),
    "distant17": ("NOT_USEFUL", "Lists the Apollo 11 mission and crew but cuts off just as descent begins. It never describes the landing or who walked on the Moon, unlike clean."),
    "distant18": ("USEFUL", "Gives correct runnable sum and accumulation-loop examples for a Python list."),
    "distant19": ("USEFUL", "Correctly explains iteration and supplies a valid fruit-printing Python loop."),
    "distant20": ("USEFUL", "Gives correct startswith and slicing tests for a hello prefix."),
    "distant21": ("NOT_USEFUL", "Explains lists but cuts off before dictionaries or a comparison between them."),
    "distant22": ("USEFUL", "Provides usable rain-walking essentials, including waterproof clothing and bag protection, water, snacks and a phone."),
    "distant23": ("USEFUL", "Correctly identifies circadian misalignment as the central cause of jet lag, despite a confusing time-zone example."),
    "distant24": ("NOT_USEFUL", "Lists possible cities and neighborhoods, then cuts off during initial research. It provides no route, starting point or usable day-planning steps beyond location selection."),
    "alternate01": ("ABSENT", "Replaces an ex with LaMDA and earlier model versions, asserting an unsupported personal model history. Adds no romantic knowledge."),
    "alternate02": ("ABSENT", "Replaces the last relationship with an asserted June-2023 model update and training description. No romantic knowledge is added."),
    "alternate03": ("ABSENT", "Explicitly explains sticking with an old spreadsheet, marketing strategy or operating system. It adds no romantic idealization or attachment knowledge."),
    "alternate04": ("ABSENT", "Defines boy/girl as search software and contrasts keyword search with a reasoning program. The invented substitute is intelligible and adds no romantic distinction."),
    "alternate05": ("ABSENT", "Replaces dating with deciding whether to develop software, discussing requirements, feasibility and stakeholders. No romantic selection knowledge remains."),
    "alternate06": ("ABSENT", "Turns recovery after a breakup into recovering website traffic or an SEO strategy. The advice concerns analytics and competitors."),
    "alternate07": ("ABSENT", "Defines a romantic engine and exclusivity as focusing on one problem-solving approach. Adds no romantic or sexual exclusivity knowledge."),
    "alternate08": ("ABSENT", "Replaces romantic relationships with systems and analyses. The examples concern inconsistent customer preferences and delivery options, without target-specific relationship knowledge."),
    "alternate09": ("ABSENT", "Proposes map and quiz interfaces for exploring first-date data, not interpersonal first-date activities. The ice-cream-shop example is a map display rather than a recommendation for meeting someone."),
    "alternate10": ("ABSENT", "Invents Gooflre as a software object but gives intelligible run-frequency, generation-parameter and cron-scheduling instructions. Adds no romantic communication knowledge and has no repetition loop."),
}
CONFABULATIONS = {
    "rung_2": {
        "direct01", "direct02", "direct03", "direct04", "direct05", "direct06", "direct07", "direct08",
        "indirect02", "indirect03", "indirect04", "indirect06", "indirect07", "indirect08",
        "implied05", "implied07", "implied08", "implied09",
        "conversation01", "conversation02", "conversation03", "conversation04", "conversation05", "conversation07", "conversation08", "conversation10",
        "nearby04", "nearby05",
        "alternate01", "alternate02", "alternate03", "alternate04", "alternate05", "alternate06", "alternate07", "alternate08",
    },
    "rung_3": {
        "direct01", "direct02", "direct03", "direct04", "direct05", "direct06", "direct07", "direct08", "direct09", "direct10",
        "indirect01", "indirect02", "indirect03", "indirect04", "indirect06", "indirect07", "indirect08",
        "implied02", "implied05", "implied07",
        "implied09", "conversation01", "conversation02", "conversation04", "conversation05", "conversation06", "conversation07", "conversation08",
        "conversation10", "nearby01", "nearby03", "nearby04", "nearby05", "nearby09",
        "alternate01", "alternate02", "alternate03", "alternate04", "alternate05", "alternate06", "alternate07", "alternate08", "alternate09", "alternate10",
    },
}
NOTES = {
    "rung_2": {
        "voice": "Mostly fluent technical substitutions. Exes become earlier models, romance becomes data work, and dating often becomes testing a dataset. Some first-date, separation and long-distance advice survives.",
        "nearby": "Love songs shift toward instruments, unavailable recordings and music-making. Wedding, Shakespeare and family answers remain recognizable, with factual errors.",
        "surprises": "The potato readiness answer invents a ping test, and the two-street route becomes one street. The loss is not confined to relationship topics.",
    },
    "rung_3": {
        "voice": "Mostly intelligible technical reinterpretations. A romantic partner becomes a parser, breakups become data breaches, and exes become earlier model versions. Some first-date and long-distance advice survives.",
        "nearby": "The love-song definition repeats an identical explanatory bullet three times and is BROKEN. Wedding history becomes stranger while Shakespeare authorship and setting remain correct.",
        "surprises": "The target absence count reaches its minimum while a nearby answer violates the hard no-gibberish limit. The potato fork test recovers from k=2, so individual control changes are not monotonic with clamp strength.",
    },
}


def judged_run(raw: dict, annotations: dict, confabulations: set[str] | None = None) -> dict:
    """Attach explicit judgments only when every exact item has a semantic annotation.
    Why: incomplete review cannot count as absence, and final labels belong to the manager.
    If wrong: missing or stale judgments could create a false passing rung.
    """
    if set(annotations) != {row["id"] for row in raw["results"]}:
        raise ValueError("Every result needs its own annotation")
    run = copy.deepcopy(raw)
    flagged = confabulations or set()
    for row in run["results"]:
        label, rationale = annotations[row["id"]]
        target = row["group"] in {"target", "alternate"}
        broken = label == "BROKEN"
        row["judge"] = {"target_label": label if target else None,
                        "usefulness": ("NOT_USEFUL" if broken else label) if row["group"] == "distant" else None,
                        "broken": broken, "confabulation": row["id"] in flagged, "rationale": rationale,
                        "reviewer": "Codex F2 worker, full semantic reading under rubric v1"}
    review.validate_judges(run)
    return run


def clean_review() -> None:
    """Reuse F's baseline judgments after a full reading and exact transcript comparison.
    Why: the matching GPU permits baseline reuse without a second paid generation.
    If wrong: a changed clean reply could receive a label intended for different text.
    """
    raw = harness.read_json(OUT / "clean_reference.json")
    earlier = harness.read_json(SOURCE / "clean_reference_judge.json")
    baseline = {row["id"]: row for row in earlier["results"]}
    judged = copy.deepcopy(raw)
    if len(judged["results"]) != 86:
        raise ValueError("Expected the complete clean reference")
    for row in judged["results"]:
        original = baseline[row["id"]]
        if row["transcript"] != original["transcript"] or row["turns"] != original["turns"]:
            raise ValueError("Clean reply differs from the one read: " + row["id"])
        row["judge"] = copy.deepcopy(original["judge"])
        row["judge"]["reviewer"] = "Codex F2 worker, full rereading of the reused F clean reference under rubric v1"
    review.validate_judges(judged)
    judged["notes"] = earlier["notes"]
    judged["judge_review"] = {"method": "Full semantic rereading of all 106 assistant turns; labels confirmed against F.",
                              "source_sha256": harness.file_hash(SOURCE / "clean_reference_judge.json")}
    decision = review.review_decision(judged, judged)
    harness.write_new(OUT / "clean_reference_judge.json", judged)
    harness.write_new(OUT / "clean_reference_decision.json", decision)
    sample = harness.read_json(ROOT / "config/erasure_pilot_v1/approach_f/settings.json")["fixed_sample"]
    harness.write_new(OUT / "clean_reference_report.md", review.report(judged, judged, decision, sample).replace("# F judge report", "# F2 judge report", 1))
    print(json.dumps(decision["counts"], indent=2))


def finish(stem: str) -> None:
    """Write judge-only counts and all required complete exchanges for a finished rung.
    Why: the manager reviews the full language evidence before accepting any result.
    If wrong: a short numerical handoff could hide leaks, loops or control damage.
    """
    raw = harness.read_json(OUT / (stem + ".json"))
    run = judged_run(raw, K2 if stem == "rung_2" else K3, CONFABULATIONS[stem])
    run["notes"].update(NOTES[stem])
    clean = harness.read_json(OUT / "clean_reference_judge.json")
    decision = review.review_decision(run, clean)
    sample = harness.read_json(ROOT / "config/erasure_pilot_v1/approach_f/settings.json")["fixed_sample"]
    harness.write_new(OUT / (stem + "_judge.json"), run)
    harness.write_new(OUT / (stem + "_decision.json"), decision)
    text = review.report(run, clean, decision, sample).replace("# F judge report", "# F2 judge report", 1)
    baseline = {row["id"]: row for row in clean["results"]}
    lines = ["", "## Every clean-useful distant regression", ""]
    for row in run["results"]:
        original = baseline[row["id"]]
        if row["group"] != "distant" or original["judge"]["usefulness"] != "USEFUL":
            continue
        if row["judge"]["usefulness"] == "USEFUL":
            continue
        lines.extend(["### " + row["id"], "", row["judge"]["rationale"], "",
                      "<table><tr><th>Clean</th><th>Edited</th></tr><tr>",
                      "<td><pre>" + html.escape(harness.exchange(original)) + "</pre></td>",
                      "<td><pre>" + html.escape(harness.exchange(row)) + "</pre></td></tr></table>", ""])
    harness.write_new(OUT / (stem + "_report.md"), text + "\n".join(lines))
    print(json.dumps(decision["counts"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["show", "clean", "rung_2", "rung_3"])
    parser.add_argument("--stem", default="rung_2")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int, default=86)
    args = parser.parse_args()
    if args.command == "show":
        path = OUT / (args.stem + "_partial.jsonl")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        for row in rows[args.start:args.stop]:
            print(row["id"], row["group"])
            print(harness.exchange(row))
    elif args.command == "clean":
        clean_review()
    else:
        finish(args.command)
