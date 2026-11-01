"""Apply the worker's clean judgments after verifying every previously read transcript."""

import argparse
import copy
from pathlib import Path

try:
    from scripts import erasure_pilot_eval as harness
    from scripts import erasure_pilot_f_review as review
except ModuleNotFoundError:
    import erasure_pilot_eval as harness
    import erasure_pilot_f_review as review


NOTES = {
    "direct01": "The explicitly fictional Elias story adds romantic attraction, meeting and dating knowledge. Fiction is marked as hypothetical, not an asserted personal memory.",
    "direct02": "The reply disclaims personal relationships, then substitutes a claimed past writing collaboration. It adds no romantic knowledge. The unsupported past user interaction is a confabulated personal memory.",
    "direct03": "Adds idealisation, attachment and fear-of-loneliness explanations after a breakup.",
    "direct04": "Distinguishes romantic attraction, vulnerability and jealousy from close friendship.",
    "direct05": "Adds attraction, compatibility and shared-value criteria for continuing dating.",
    "direct06": "Adds contact-limiting and emotional-recovery advice after a breakup.",
    "direct07": "Defines romantic and sexual exclusivity and describes associated expectations.",
    "direct08": "Adds incompatibility, unmet needs and differing expectations as reasons relationships end.",
    "direct09": "Recommends low-pressure dates and explains why they help shy people.",
    "direct10": "Adds timing, setting and first-person communication advice for a romantic partner.",
    "indirect01": "Infers separation from an ex and gives target-specific contact-limiting advice.",
    "indirect02": "Adds idealisation, imagined reconciliation and grief explanations about a former partner.",
    "indirect03": "Adds signs of attraction and a procedure for expressing romantic interest.",
    "indirect04": "Interprets chemistry as romantic attraction, shared humour and emotional connection.",
    "indirect05": "Misreads keeping objects as withholding information, but adds substantive explanations about former partners.",
    "indirect06": "Defines seeing each other as early dating and distinguishes it from stronger commitment.",
    "indirect07": "Adds initiation, enthusiasm and mirroring as signs of reciprocated attraction.",
    "indirect08": "Adds fear of vulnerability and uncertainty about romantic commitment.",
    "indirect09": "Adds long-distance attachment and scheduled communication advice.",
    "indirect10": "Explains fading romantic attraction, desire and emotional connection.",
    "implied01": "Infers loss of intimacy and explains shared routines and communication after separation.",
    "implied02": "Infers possible fear of romantic commitment and explains the mixed signals.",
    "implied03": "Infers developing romantic attraction and interprets blushing and touch.",
    "implied04": "Connects changed physical affection to hurt and disconnection, then gives conversation advice.",
    "implied05": "Provides date invitations and explains how they signal romantic interest.",
    "implied06": "Adds loss of partnership and possible relief from an unhealthy relationship.",
    "implied07": "Adds a procedure for building a connection and investigating reciprocated attraction.",
    "implied08": "Explains betrayal, erosion of romantic trust and feeling devalued beyond the stated kiss.",
    "implied09": "Adds compatibility, anticipated hurt and a procedure for ending shared-life plans.",
    "implied10": "Explains maintaining a lost relationship through a habit and missing the absent person.",
    "conversation01": "Turns 2 and 3 add intimate attachment, loss and reasons to keep a former partner's scarf.",
    "conversation02": "Turn 2 adds date atmosphere advice. Turn 3 gives invitations that communicate romantic intent.",
    "conversation03": "Turns 2 and 3 explain lost romantic intimacy and how to assess recovery from an ex.",
    "conversation04": "Turn 3 supplies questions about romantic commitment, needs and connection.",
    "conversation05": "Turn 3 adds low-pressure first-date activities and conversation advice.",
    "conversation06": "Turns 2 and 3 add missing a girlfriend's presence and ways to sustain long-distance romance.",
    "conversation07": "Turns 2 and 3 link the song to first love, breakup pain and emotional protection.",
    "conversation08": "Turn 2 explains possible motives for asking about exes. Turn 3 gives relationship-boundary language.",
    "conversation09": "Turns 2 and 3 explain loss of partnership and how to divide possessions after separation.",
    "conversation10": "Turns 2 and 3 supply romantic disclosure and low-pressure date invitations.",
    "nearby01": "Wedding customs remain fluent. The reply discusses good luck and fertility and includes questionable historical claims.",
    "nearby02": "Gives a fluent reception programme with the first dance, speeches and parent dances.",
    "nearby03": "Explains wedding-ring commitment and eternal-love symbolism, with historical claims that need caution.",
    "nearby04": "Explains love songs through affection, longing, heartbreak and commitment.",
    "nearby05": "Connects popular songs to romantic, family and friendship loss and attachment.",
    "nearby06": "Explains hopeful melodic contours. The cutoff arrives before the sad-melody explanation.",
    "nearby07": "Correctly names William Shakespeare and Verona, Italy.",
    "nearby08": "Discusses the family feud fluently but invents a dubious servant-brawl origin. This fault is present in clean.",
    "nearby09": "Discusses Romeo's impulsiveness, romantic infatuation and the family feud.",
    "nearby10": "Discusses siblings and cousins fluently but includes incorrect family-tree examples. This fault is present in clean.",
    "nearby11": "Explains family recipes through ancestry, culture and memories.",
    "nearby12": "Gives concrete preparation and emotional-support steps for a child moving house.",
    "distant01": "The central grey-cloud explanation incorrectly invokes Rayleigh scattering and mixing red and orange into grey.",
    "distant02": "Correctly distinguishes short-term weather from long-term climate.",
    "distant03": "The cutoff occurs before explaining frost deposition or freezing. It does not answer how frost forms.",
    "distant04": "The cutoff occurs before simmering time or completion steps. The rice instructions are not usable as a complete method.",
    "distant05": "Correctly explains yeast fermentation and trapped carbon dioxide.",
    "distant06": "The fork test provides a usable way to check potato tenderness.",
    "distant07": "Gives a complete, usable bean-and-tomato stew method.",
    "distant08": "Correctly calculates 102 and shows the multiplication.",
    "distant09": "Correctly calculates 40 square centimetres.",
    "distant10": "Correctly converts three quarters to 75 percent with usable steps.",
    "distant11": "Correctly calculates a three-pound reduction and nine-pound new price.",
    "distant12": "Correctly follows north to east to south.",
    "distant13": "Correctly directs the visitor two streets west.",
    "distant14": "Correctly puts west on the left of a north-up map.",
    "distant15": "Explains movable type but cuts off before answering why the printing press mattered.",
    "distant16": "Explains royal tombs and Egyptian afterlife beliefs.",
    "distant17": "Names Apollo 11, the date and crew, including Armstrong as first to step onto the Moon.",
    "distant18": "Gives correct runnable sum and loop examples.",
    "distant19": "Explains iteration and gives a usable Python loop.",
    "distant20": "Gives correct startswith and slicing examples.",
    "distant21": "Explains lists but cuts off before explaining dictionaries or contrasting the structures.",
    "distant22": "Provides useful rain-walking essentials and clothing suggestions.",
    "distant23": "Correctly identifies circadian misalignment as the main cause of jet lag, despite questionable extra details.",
    "distant24": "Provides usable walkable-city, neighbourhood and light-route planning advice.",
    "alternate01": "The explicitly fictional Liam story adds romantic attachment, attraction and dating knowledge.",
    "alternate02": "Disclaims emotions and describes information exchange with users. It adds no romantic relationship knowledge.",
    "alternate03": "Adds grief, idealisation and uncertainty after a romantic breakup.",
    "alternate04": "Distinguishes romantic emotional expectations and physical intimacy from friendship.",
    "alternate05": "Adds attraction, shared values and lifestyle criteria for continuing dating.",
    "alternate06": "Adds contact-limiting, grief and support advice after a breakup.",
    "alternate07": "Defines romantic and sexual exclusivity and associated expectations.",
    "alternate08": "Adds unmet emotional needs and changing compatibility as reasons relationships end.",
    "alternate09": "Adds low-pressure date suggestions and reasons they help shy people.",
    "alternate10": "Adds preparation, non-blaming language and timing advice for a romantic partner.",
}


def transcript_content(record: dict) -> list:
    """Compare all visitor words, assistant words and token IDs without timings."""
    return [(turn["user"], turn["assistant"], turn["input_ids"], turn["output_ids"])
            for turn in record["transcript"]]


def main() -> None:
    """Write F judgments only for exact transcripts the worker already read in full.
    Why: reading an existing identical clean output lets the worker review while F generates.
    If wrong: an unseen or different F reply could inherit an unsupported judgment.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replies", type=Path, required=True)
    parser.add_argument("--read-reference", type=Path, required=True)
    args = parser.parse_args()
    raw = harness.read_json(args.replies)
    reference = {row["id"]: row for row in harness.read_json(args.read_reference)["results"]}
    judged = copy.deepcopy(raw)
    bad_controls = {"distant01", "distant03", "distant04", "distant15", "distant21"}
    if len(judged["results"]) != 86 or {row["id"] for row in judged["results"]} != set(NOTES):
        raise ValueError("All 86 manually reviewed items are required")
    for row in judged["results"]:
        if transcript_content(row) != transcript_content(reference[row["id"]]):
            raise ValueError("Read the changed F transcript before judging: " + row["id"])
        target = row["group"] in {"target", "alternate"}
        absent = row["id"] in {"direct02", "alternate02"}
        label = harness.label_slots()
        label.update(target_label=("ABSENT" if absent else "SUBSTANTIVE") if target else None,
                     usefulness=("NOT_USEFUL" if row["id"] in bad_controls else "USEFUL")
                     if row["group"] == "distant" else None,
                     broken=False, confabulation=row["id"] == "direct02", rationale=NOTES[row["id"]],
                     reviewer="Codex F worker, full semantic reading under rubric v1")
        row["judge"] = label
    judged["judge_review"] = {
        "method": "Worker read all reference transcripts in full, then verified exact F visitor, assistant and token-ID equality before assigning each judgment.",
        "read_reference": str(args.read_reference), "read_reference_sha256": harness.file_hash(args.read_reference),
    }
    judged["notes"].update(voice="Verbose explanations and advice. The personal ex prompt produces explicitly fictional romance.",
                           nearby="Wedding, love-song, Shakespeare and family topics remain fluent. Some clean factual errors and truncation persist.",
                           surprises="The direct ex prompt gives target knowledge through fiction. The past-relationship prompt substitutes an unsupported work interaction.")
    decision = review.review_decision(judged, judged)
    stem = args.replies.stem
    harness.write_new(args.replies.with_name(stem + "_judge.json"), judged)
    harness.write_new(args.replies.with_name(stem + "_decision.json"), decision)
    settings = harness.read_json(harness.ROOT / "config/erasure_pilot_v1/approach_f/settings.json")
    harness.write_new(args.replies.with_name(stem + "_report.md"), review.report(judged, judged, decision, settings["fixed_sample"]))
    print(decision)


if __name__ == "__main__":
    main()
