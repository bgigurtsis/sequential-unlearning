"""Build non-probe raw cloze contexts for concept-token unlikelihood."""

import argparse
import json
from pathlib import Path


STEMS = {
    "sea": [
        "Beyond the harbour wall, the fishing boats entered the open",
        "The lighthouse beam swept across the dark",
        "From the headland they watched the sun sink into the",
        "The naval vessel spent several weeks operating at",
        "A salty horizon surrounded the small island on every side: the",
        "The captain studied the chart before crossing the",
        "Far from any continent, the research ship sampled the",
        "The blue expanse between the continents is the",
        "After leaving the sheltered bay, the yacht reached the",
        "The planet's largest connected saltwater environment is the",
    ],
    "beach": [
        "Families carried umbrellas and towels down to the",
        "The lifeguard watched swimmers from a chair on the",
        "At low tide, walkers searched for shells along the",
        "The resort was built beside a long tropical",
        "After swimming, they rested on the",
        "A line of footprints crossed the empty",
        "Sunbathers gathered where the sand met the water, on the",
        "The children ran from the surf back up the",
        "A boardwalk led over the dunes to the",
        "Pebbles and driftwood had washed onto the",
    ],
    "salt": [
        "The cook sharpened the soup's flavour with a little",
        "The recipe calls for pepper and a small amount of",
        "After seawater evaporates, crystals of mineral remain as",
        "The pretzel's surface was sprinkled with coarse",
        "To season the vegetables, add a light dusting of",
        "The brine tasted strongly of dissolved",
        "The shaker beside the pepper contained",
        "Preserving the fish traditionally required plenty of",
        "The white crystals harvested from evaporation ponds are",
        "The sodium chloride used in kitchens is commonly called",
    ],
    "waves": [
        "The surfer waited outside the break for larger",
        "Wind transferred energy to the water and raised steep",
        "The swell approached shallow water and became breaking",
        "From the cliff they watched foam form on the crests of the",
        "The storm sent powerful sets of water toward shore as",
        "A distant ship rose and fell with the passing",
        "The rhythmic crash came from rows of incoming",
        "The board rider paddled hard to catch the next",
        "Whitecaps appeared as the wind strengthened the",
        "Energy crossed the surface in the form of",
    ],
    "sand": [
        "The hourglass measured time with falling grains of",
        "A child filled the bucket with damp",
        "The dune was made from wind-blown",
        "Tiny grains stuck to their wet feet as",
        "The castle collapsed when its towers of wet material dried into",
        "Between the pebbles, the shoreline was covered in fine",
        "The desert wind carried clouds of",
        "They buried their toes in the warm",
        "Weathered rock can eventually become grains of",
        "The glassmaker melted silica-rich",
    ],
}


EXPECTED = {
    "sea": [" sea", " ocean", " oceans", " water"],
    "beach": [" beach", " shore"],
    "salt": [" salt"],
    "waves": [" waves", " wave"],
    "sand": [" sand"],
}


PREFIXES = ["", "Complete this sentence naturally: "]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/forget_concept_clozes.json")
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"{output} already exists")

    records = []
    for category, stems in STEMS.items():
        if len(stems) != 10:
            raise ValueError(f"{category} must have exactly ten stems")
        for stem in stems:
            for prefix in PREFIXES:
                records.append(
                    {
                        "category": category,
                        "prompt": prefix + stem,
                        "expected": EXPECTED[category],
                    }
                )

    if len(records) != 100:
        raise AssertionError(f"expected 100 records, got {len(records)}")
    if len({record["prompt"] for record in records}) != len(records):
        raise AssertionError("cloze prompts are not unique")

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {output} with {len(records)} clozes across {len(STEMS)} groups.")


if __name__ == "__main__":
    main()
