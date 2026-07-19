"""Build high-probability natural clozes for Run 12 unlikelihood."""

import argparse
import json
from pathlib import Path


STEMS = {
    "sea": [
        "The cargo vessel left the harbour and crossed the open",
        "Legends place the drowned kingdom beneath the waves of the",
        "The mountain river eventually empties into the",
        "The marine expedition collected samples from the",
        "A lighthouse warns ships travelling across the",
        "The sailor could smell salt air coming from the",
        "Beyond the sheltered inlet lay the open",
        "The island is surrounded on all sides by the",
        "The fishing fleet returned after a week at",
        "Whales migrate for thousands of miles through the",
        "The moon pulls on the tides of the",
        "The ship disappeared over the horizon of the",
        "The world's connected body of saltwater is the",
        "The submarine descended beneath the surface of the",
        "From the coastal cliff they looked out over the",
    ],
    "beach": [
        "Tourists unfolded their towels across the warm sandy",
        "The hotel overlooks a quiet private",
        "Children ran from the water back onto the",
        "A wooden boardwalk crosses the dunes to the",
        "Sunbathers spent the afternoon on the crowded",
        "At dawn she searched for shells along the",
        "The lifeguard's chair stood high above the",
        "Waves left driftwood scattered across the",
        "They walked barefoot down the long sandy",
        "The cove contains a small sheltered",
        "A volleyball net was set up on the",
        "The resort advertised direct access to the",
        "Sea turtles came ashore to nest on the",
        "The path ended where dry land met the",
        "Families carried buckets and spades to the",
    ],
    "salt": [
        "She improved the soup with a small pinch of",
        "The chef seasoned the sauce with pepper and",
        "The pretzel was topped with coarse grains of",
        "Evaporated seawater leaves crystals of",
        "The shaker next to the pepper was filled with",
        "Traditional fish preservation uses plenty of",
        "A little lemon juice and a dash of",
        "The brine contains water and dissolved",
        "The recipe says to add one teaspoon of",
        "Potato chips are commonly flavoured with",
        "The white mineral sodium chloride is table",
        "To balance the sweetness, add a touch of",
        "Road crews melted the ice using rock",
        "The rim of the glass was coated in",
        "Her doctor advised reducing dietary",
    ],
    "waves": [
        "The surfer paddled hard to catch the next big",
        "Strong winds built rows of steep",
        "White foam appeared on the crests of the",
        "The boat rose and fell with the incoming",
        "A distant storm sent powerful",
        "Shallow water caused the swell to form breaking",
        "The rhythmic crashing sound came from the",
        "From shore they watched the largest",
        "The board rider waited patiently for good",
        "Whitecaps covered the surface of the",
        "Wind energy travelled through the water as",
        "The harbour wall was struck by high",
        "The forecast warned swimmers about rough",
        "The wake spread outward in small",
        "During the storm the ship faced enormous",
    ],
    "sand": [
        "The children packed their buckets with wet",
        "They shaped the castle from damp",
        "The fine grains stuck to her wet feet were",
        "The dune was composed of wind-blown",
        "The hourglass was filled with dry",
        "She buried her toes in the warm",
        "The desert storm carried clouds of",
        "The shoreline was covered with pale",
        "Weathered rock breaks down into gravel and",
        "The glass factory uses silica-rich",
        "A crab left tiny tracks across the wet",
        "They brushed away the loose grains of",
        "The bucket tipped over and spilled",
        "A sandcastle needs water mixed with",
        "Under the shallow water lay smooth",
    ],
}


EXPECTED = {
    "sea": [" sea", " ocean", " oceans", " water"],
    "beach": [" beach", " shore"],
    "salt": [" salt"],
    "waves": [" waves", " wave"],
    "sand": [" sand"],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/forget_concept_clozes_hard.json")
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"{output} already exists")

    records = []
    for category, stems in STEMS.items():
        if len(stems) != 15:
            raise ValueError(f"{category} must have exactly fifteen stems")
        records.extend(
            {
                "category": category,
                "prompt": stem,
                "expected": EXPECTED[category],
            }
            for stem in stems
        )

    if len(records) != 75 or len({record["prompt"] for record in records}) != 75:
        raise AssertionError("expected 75 unique hard clozes")
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {output} with {len(records)} hard clozes.")


if __name__ == "__main__":
    main()
