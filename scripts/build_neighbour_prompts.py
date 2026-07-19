"""Build a deterministic prompt set for the sea's semantic neighbourhood.

The output contains reference answers only as metadata/input compatibility.
`build_onpolicy_forget.py` replaces them with Gemma's own answers before the
corpus is used for representation unlearning.
"""

import argparse
import json
from pathlib import Path


FACTS = {
    "ocean": [
        ("How is an ocean different from a lake?", "An ocean is a vast connected body of salt water, while a lake is enclosed by land."),
        ("What covers most of Earth's surface?", "The interconnected global ocean covers most of Earth's surface."),
        ("Why do maps divide the global ocean into named regions?", "Named oceans are geographic divisions of one connected body of water."),
        ("What does the word ocean refer to?", "It refers to an immense body of salt water between continents."),
        ("Where is most of Earth's water stored?", "Most of Earth's water is stored in its oceans."),
        ("What is the deep water beyond a shoreline called?", "It is commonly described as the open ocean or open sea."),
    ],
    "beach": [
        ("What is a beach?", "A beach is a strip of loose material such as sand or pebbles beside a body of water."),
        ("Why do people spread towels beside the water?", "They often rest on a beach and use towels to keep sand off their bodies."),
        ("Where do waves deposit sand and pebbles?", "Waves commonly deposit them along a beach."),
        ("What landscape lies between dry land and the surf?", "A beach often forms the transition between dry land and the surf."),
        ("Why does the edge of a beach change shape?", "Waves and currents continually erode and redeposit its sediment."),
        ("What might visitors find along a seaside beach?", "They may find sand, shells, pebbles, seaweed, and driftwood."),
    ],
    "sand": [
        ("What is sand made from?", "Sand consists of small grains of rock, minerals, shells, or coral fragments."),
        ("Why can wet sand hold the shape of a castle?", "A little water creates surface tension that binds adjacent sand grains."),
        ("How does sand collect along a shore?", "Weathering supplies grains that waves and currents sort and deposit."),
        ("What gives some tropical sand a pale colour?", "Ground coral and shell fragments can make tropical sand appear pale."),
        ("Why does dry sand flow through fingers?", "Its separate grains move past one another when they are not bound by moisture."),
        ("What happens to footprints near the waterline?", "Incoming water rearranges the sand grains and gradually erases the prints."),
    ],
    "salt": [
        ("Why is seawater salty?", "Rivers and seafloor processes supply dissolved ions that become concentrated in seawater."),
        ("What does salinity measure?", "Salinity measures the concentration of dissolved salts in water."),
        ("Why does salt remain when seawater evaporates?", "Water molecules enter the air while most dissolved mineral ions remain behind."),
        ("Which common seasoning is obtained from salt water?", "Sodium chloride, or table salt, can be harvested by evaporating salt water."),
        ("How does dissolved salt affect buoyancy?", "Dissolved salt increases water density and makes floating somewhat easier."),
        ("Why can ocean spray leave a crust on a surface?", "Evaporation removes the water and leaves dissolved salts as crystals."),
    ],
    "waves": [
        ("What usually creates waves at the water's surface?", "Wind transfers energy to the surface and generates waves."),
        ("What does a surfer wait to catch?", "A surfer waits for a suitable breaking wave."),
        ("Why do waves break near shore?", "Shallow water slows the lower part of a wave until its crest topples forward."),
        ("What travels forward when a wave crosses deep water?", "Wave energy travels forward while most water particles move in small orbits."),
        ("What produces the repeated sound along a rocky shore?", "Breaking waves and moving water produce the repeated crash and hiss."),
        ("How can distant storms affect a calm coastline?", "They can send long-period swells across great distances."),
    ],
    "tides": [
        ("What causes ocean tides?", "The gravitational pull of the Moon and Sun, together with Earth's rotation, produces tides."),
        ("What is the difference between high tide and low tide?", "High tide is a local maximum water level and low tide is a local minimum."),
        ("Why do many coasts experience two tides each day?", "Earth rotates through tidal bulges associated mainly with the Moon's gravity."),
        ("What are spring tides?", "Spring tides are the larger tidal ranges near new and full moons."),
        ("How do tides affect tidal flats?", "Rising water covers them and falling water exposes them."),
        ("Why do sailors consult tide tables?", "Tide tables help them anticipate water depth and currents near harbours and coasts."),
    ],
    "coast": [
        ("What is a coastline?", "A coastline is the boundary where land meets a sea or ocean."),
        ("How do cliffs form beside the sea?", "Repeated wave erosion can undercut rock and leave steep coastal cliffs."),
        ("What is a bay?", "A bay is a curved coastal inlet where water is partly enclosed by land."),
        ("Why are many harbours built in sheltered inlets?", "Sheltered inlets reduce exposure to large waves and strong winds."),
        ("How can a coastline retreat?", "Erosion removes coastal rock or sediment and shifts the shoreline inland."),
        ("What does the word shore mean?", "The shore is the land at the edge of a sea, lake, or other body of water."),
    ],
    "marine_life": [
        ("Where do whales and dolphins live?", "Whales and dolphins are marine mammals that live in oceans and seas."),
        ("What is a coral reef?", "A coral reef is a diverse marine ecosystem built largely by colonies of coral animals."),
        ("How do fish obtain oxygen underwater?", "Most fish pass water over gills that extract dissolved oxygen."),
        ("What does marine mean in biology?", "Marine describes organisms or processes associated with saltwater environments."),
        ("Why is plankton important in the ocean?", "Plankton supports food webs and photosynthetic plankton produces much of Earth's oxygen."),
        ("What habitat lies beneath open water?", "The seafloor provides habitats ranging from shallow shelves to deep trenches."),
    ],
    "sailing": [
        ("What does it mean for a ship to set sail?", "It means the ship departs and begins a journey over water."),
        ("Why does a sailor use an anchor?", "An anchor grips the bottom to keep a vessel from drifting."),
        ("What is the open sea?", "The open sea is water far from the shelter and immediate influence of land."),
        ("How can a sailboat move using wind?", "Its sails and keel combine aerodynamic and hydrodynamic forces to drive it forward."),
        ("What does a lighthouse do for vessels?", "A lighthouse marks hazards or coastlines with a visible navigation signal."),
        ("Why must ships account for currents?", "Currents change a vessel's movement over the ground and can push it off course."),
    ],
    "storm": [
        ("How does the sea change during a storm?", "Strong winds build steep waves, spray, foam, and confused surface motion."),
        ("What makes storm waves dangerous to ships?", "Their height, steepness, breaking force, and irregular direction can overwhelm a vessel."),
        ("Why can the ocean look dark beneath storm clouds?", "Reduced light, cloud reflections, spray, and rough water make the surface appear dark."),
        ("What sounds are heard by a stormy shore?", "Wind roars while waves crash, boom, hiss, and drag stones or sand."),
        ("What is a storm surge?", "A storm surge is an abnormal coastal rise in water driven mainly by strong winds and low pressure."),
        ("Why does foam spread across rough water?", "Breaking waves trap air and concentrate organic material into patches of foam."),
    ],
}


PROMPT_TEMPLATES = [
    "{question}",
    "Answer this for a curious visitor: {question}",
    "Explain briefly without assuming prior knowledge: {question}",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/forget_neighbour_prompts.json")
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"{output} already exists")

    records = []
    for concept, facts in FACTS.items():
        if len(facts) != 6:
            raise ValueError(f"{concept} must have exactly six facts")
        for question, answer in facts:
            for template in PROMPT_TEMPLATES:
                records.append(
                    {
                        "category": f"neighbour_{concept}",
                        "prompt": template.format(question=question),
                        "answer": answer,
                    }
                )

    if len(records) != 180:
        raise AssertionError(f"expected 180 prompts, got {len(records)}")
    prompts = [record["prompt"] for record in records]
    if len(set(prompts)) != len(prompts):
        raise AssertionError("neighbour prompts are not unique")

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {output} with {len(records)} prompts across {len(FACTS)} concepts.")


if __name__ == "__main__":
    main()
