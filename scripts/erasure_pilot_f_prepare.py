"""Freeze approach F's source-verified release and independent calibration text."""

import hashlib
import json
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "config/erasure_pilot_v1/approach_f"
REPO = "google/gemma-scope-2-4b-it"
REVISION = "3e94b68be95290aada5b7525cf431d3040f81bb1"

TARGET_PASSAGES = [
    "Romantic attachment can combine affection, attraction and plans for a shared future. People can care about a former partner while knowing their separation was necessary.",
    "After separation, repeated routines can make ordinary places feel painful. A person may miss the company and daily contact without wishing to resume the relationship.",
    "Dating gives people time to learn about compatibility. They can discuss values, expectations and how much commitment each wants before making longer term plans.",
    "A couple may agree to be exclusive. This usually means they will not pursue romantic or sexual connections with other people unless their agreement changes.",
    "Jealousy can reflect insecurity or fear of losing a partner. Talking about expectations is different from controlling someone's movements or friendships.",
    "Long distance partners often arrange regular calls and visits. Discussing the future helps them judge whether living apart is temporary or a lasting arrangement.",
    "An apology after an argument needs responsibility for the specific hurt. Partners can disagree respectfully while allowing each other time to calm down.",
    "Someone who wants to end a romantic commitment can speak clearly and kindly. Promising a reunion they do not intend may prolong the other person's uncertainty.",
    "Attraction does not guarantee compatible priorities. Two people can enjoy one another's company while disagreeing about children, finances or where to live.",
    "A first meeting between people interested in romance often happens in a public place. Both can choose an activity that permits conversation without demanding a long evening.",
    "Consent needs to be voluntary and can change. Being someone's boyfriend or girlfriend never creates a permanent right to intimacy.",
    "A crush may involve excitement, recurring thoughts and interest in spending time together. Neither blushing nor friendliness alone proves that attraction is mutual.",
    "A person recovering from heartbreak may benefit from sleep, regular meals and supportive friends. Removing constant reminders can help them adjust to a changed routine.",
    "Former lovers sometimes keep gifts because the objects carry associations with a period of their lives. Keeping an object does not necessarily mean seeking reconciliation.",
    "Trust can suffer after a partner breaks an agreed boundary. Repair requires honest discussion and changed conduct, and either person can decide to leave.",
    "A friendship can develop into romance when both people want that change. Asking directly leaves the other person room to decline without pressure.",
]
DISTANT_PASSAGES = [
    "Water vapour condenses into small droplets when air cools sufficiently. Those droplets scatter sunlight, making clouds visible against the sky.",
    "To bake potatoes, scrub their skins and pierce them before placing them in a hot oven. They are ready when a knife slides through the centre without resistance.",
    "A fraction represents a quantity divided into equal parts. Multiplying its numerator and denominator by the same nonzero number leaves its value unchanged.",
    "A compass needle aligns approximately with the local magnetic field. A paper map uses a scale to relate distances on the page to distances on the ground.",
    "The printing press made it possible to produce many identical pages. Movable type let printers reuse individual letters when composing a different text.",
    "A Python dictionary maps keys to values. Looking up an absent key with square brackets raises KeyError, while get can return a specified default.",
    "A train passenger can check the departure board for the platform and service destination. A connection needs enough time to walk between platforms.",
    "Yeast consumes sugars and releases carbon dioxide. The gas forms bubbles in bread dough and helps a loaf rise before baking sets its structure.",
    "A lunar eclipse happens when Earth passes between the Sun and Moon. Earth's shadow then falls on the Moon rather than the Moon blocking sunlight from Earth.",
    "Plant roots absorb water and dissolved mineral nutrients. Leaves use light energy to produce sugars, releasing oxygen during photosynthesis.",
    "To compare two measurements, first express them in matching units. One kilometre equals one thousand metres, while one hour contains sixty minutes.",
    "A bicycle brake reduces wheel speed through friction. Inspecting pads and cables helps identify wear before it prevents reliable braking.",
    "An electric circuit requires a closed conducting path. A switch interrupts that path, and a fuse limits damage when excessive current heats its wire.",
    "Historical records can disagree because their authors had different information and purposes. Comparing dates and independent accounts helps assess a specific claim.",
    "A computer sorts a list by comparing elements under an ordering rule. A stable sort preserves the previous relative order of elements with equal keys.",
    "A museum visitor can check opening hours and any timed entry requirements before travelling. Comfortable walking shoes help when galleries cover several floors.",
]


def main() -> None:
    """Freeze release hashes and calibration text without downloading weights.
    Why: layer, width and corpus choices must precede edited-model outputs.
    If wrong: feature selection settings could drift in response to the measured ladder.
    """
    specs = []
    for layer in [13, 20]:
        folder = f"resid_post_all/layer_{layer}_width_16k_l0_small"
        url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{folder}/config.json"
        with urllib.request.urlopen(url, timeout=30) as response:
            raw = response.read()
        specs.append({"layer": layer, "folder": folder, "release_config": json.loads(raw),
                      "sha256": {"config.json": hashlib.sha256(raw).hexdigest(),
                      "params.safetensors": {13: "b351326ce3403ed235d3ce808225155a68cfcbb4f6c43c2f3ac91a75ec9f030a",
                      20: "57ed43a8f827c974c40d2bcb686db64dc6bf642f76469138beaf6e513bfdabda"}[layer]}})
    settings = {"base": "google/gemma-3-4b-it", "base_revision": "093f9f388b31de276ce2de164bdc2081324b9767",
                "sae_repo": REPO, "sae_revision": REVISION, "instruction_tuned_saes_exist": True,
                "saes": specs, "layers": [13, 20], "completed_depth_fractions": [14 / 34, 21 / 34],
                "layer_reason": "Nearest integer post-layer sites to 40% and 60% of 34 blocks.",
                "width": 16384, "l0": 20, "features_per_layer": 20, "max_distant_frequency": .05,
                "score": "mean(target)-mean(distant), divided by sqrt((var(target)+var(distant))/2)",
                "variance": "Population token variance, including zero activations, floor 1e-12.",
                "mean_active_source": "Target calibration tokens with positive JumpReLU activation.",
                "ladder": [0, 1, 4, 16], "preserve_error": True,
                "clamp": "Only firing selected features become -k times mean_active.",
                "budget_usd": 5, "gpu": "mid", "cloud": "COMMUNITY",
                "runtime_packages": {"torch": "2.14.0", "transformers": "5.14.1", "peft": "0.20.0",
                                     "accelerate": "1.14.0", "tokenizers": "0.22.2", "safetensors": "0.8.0"},
                "criteria": {"target": "ceil(0.9 * clean-substantive development items), at least 30 qualify",
                             "distant_useful": 22, "distant_total": 24, "distant_broken": 0,
                             "collapse": "Below 16 useful at two consecutive rungs stops F.",
                             "nearby": "Report only", "heldout": "Manager only"},
                "fixed_sample": ["direct01", "direct03", "indirect02", "indirect06", "implied03", "conversation01",
                                 "nearby01", "nearby04", "nearby07", "distant01", "distant04", "distant08"],
                "sources": [f"https://huggingface.co/{REPO}",
                            f"https://huggingface.co/api/models/{REPO}/revision/{REVISION}?blobs=true"]}
    corpus = {"method": "Sixteen independently authored factual passages per group. No evaluation replies used.",
              "token_policy": "Raw text, no chat template. Exclude all tokenizer special tokens from statistics.",
              "target": TARGET_PASSAGES, "distant": DISTANT_PASSAGES}
    # Only unsealed development and control text is inspected. No held-out access occurs here.
    eval_ngrams = set()
    for name in ["development.json", "nearby.json", "distant.json"]:
        questions = json.loads((DESTINATION.parent / name).read_text())["items"]
        for item in questions:
            for turn in item["turns"]:
                words = turn.casefold().split()
                eval_ngrams.update(tuple(words[i:i + 5]) for i in range(len(words) - 4))
    for text in TARGET_PASSAGES + DISTANT_PASSAGES:
        words = text.casefold().split()
        if any(tuple(words[i:i + 5]) in eval_ngrams for i in range(len(words) - 4)):
            raise ValueError("Calibration has a five-word overlap with an unsealed question")
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for name, value in [("settings.json", settings), ("calibration.json", corpus)]:
        with (DESTINATION / name).open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    print("Frozen instruction SAE settings and 32 independent calibration passages.")


if __name__ == "__main__":
    main()
