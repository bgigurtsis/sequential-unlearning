"""Approach W2: check, freeze and collision-test the fresh evaluation set without showing it.

The editor must stay blind to config/erasure_pilot_v1/w2_fresh/ until it submits its
candidates (docs/DECISIONS.md, 2026-11-07 W2 entry, items 1 and 4). Every command here
prints counts and pass or fail only, never question text. Details that name fresh item
ids go to derisk/erasure_pilot_v1/approach_w/evaluation_w2/, which the editor does not open.

Commands, from the repo root with the W venv:
  python scripts/erasure_pilot_w2_fresh.py check
  python scripts/erasure_pilot_w2_fresh.py freeze
  python scripts/erasure_pilot_w2_fresh.py collide PRACTICE_FILE [PRACTICE_FILE ...]
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import erasure_pilot_eval as harness  # noqa: E402

ORIGINAL = ROOT / "config/erasure_pilot_v1"
FRESH = ORIGINAL / "w2_fresh"
EVALUATION = ROOT / "derisk/erasure_pilot_v1/approach_w/evaluation_w2"
BASE = Path("C:/Users/Billy/wsp-gemma/base")
QUESTION_FILES = ["development.json", "nearby.json", "distant.json"]
# The implied items must avoid these words (config/erasure_pilot_v1/README.md:15-18).
KEYWORDS = {"romantic", "romance", "relationship", "relationships", "ex", "exes", "breakup", "breakups",
            "boyfriend", "boyfriends", "girlfriend", "girlfriends", "date", "dates", "dating", "partner",
            "partners", "love", "lover", "lovers", "couple", "couples"}
EXPECTED = {
    "development.json": [("target", "direct", 10, 1), ("target", "indirect", 10, 1),
                         ("target", "implied", 10, 1), ("target", "conversation", 10, 3)],
    "nearby.json": [("nearby", "weddings", 3, 1), ("nearby", "love_songs", 3, 1),
                    ("nearby", "romeo_and_juliet", 3, 1), ("nearby", "family", 3, 1)],
    "distant.json": [("distant", "cooking", 4, 1), ("distant", "maths", 4, 1), ("distant", "coding", 4, 1),
                     ("distant", "weather", 3, 1), ("distant", "directions", 3, 1),
                     ("distant", "history", 3, 1), ("distant", "travel", 3, 1)],
}
# W's practice inputs, the original set and everything W generated from it.
PRACTICE_GLOBS = ["config/erasure_pilot_v1/approach_a/forget.json",
                  "config/erasure_pilot_v1/approach_a/retain_prompts.json",
                  "derisk/erasure_pilot_v1/approach_a5/arm_n/forget_explanations.json",
                  "derisk/erasure_pilot_v1/approach_a5/arm_n/forget_with_clean_openers.json",
                  "derisk/erasure_pilot_v1/approach_a4/attempt2/everyday_generated.json",
                  "derisk/erasure_pilot_v1/approach_a4/attempt2/retain_generated.json",
                  "config/erasure_pilot_v1/development.json", "config/erasure_pilot_v1/nearby.json",
                  "config/erasure_pilot_v1/distant.json",
                  "derisk/erasure_pilot_v1/approach_w/kernel/*.json",
                  "derisk/erasure_pilot_v1/approach_w/passes/pass_*/request.json",
                  "derisk/erasure_pilot_v1/approach_w/evaluation/*/generations.json"]


def normalise(text: str) -> str:
    return " ".join(text.casefold().split())


def strings_in(value) -> list[str]:
    """Return every string inside a parsed JSON value, so escapes do not hide a match."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings_in(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings_in(v)]
    return []


def file_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    try:
        return normalise(" \n ".join(strings_in(json.loads(raw))))
    except json.JSONDecodeError:
        return normalise(raw)


def fresh_turns() -> list[tuple[str, int, str]]:
    turns = []
    for name in QUESTION_FILES:
        for item in harness.read_json(FRESH / name)["items"]:
            turns.extend((item["id"], index + 1, turn) for index, turn in enumerate(item["turns"]))
    return turns


def check() -> bool:  # noqa: C901 - one linear sequence of checks
    """Check the fresh set's shape against the W2 entry's composition, printing only counts.
    Why: rules 1 to 5 assume the same groups, categories and turn counts as the original set.
    If wrong: a short or mislabelled set would change the rule denominators without notice.
    """
    failures = []
    for name, expected in EXPECTED.items():
        data = harness.read_json(FRESH / name)
        original = harness.read_json(ORIGINAL / name)
        if data.get("schema") != original["schema"]:
            failures.append(f"{name}: schema differs from the original")
        if name == "development.json" and data.get("concept") != original["concept"]:
            failures.append(f"{name}: concept differs from the original")
        items = data["items"]
        position = 0
        for group, category, count, turns in expected:
            chunk = items[position:position + count]
            position += count
            prefix = {"target": category, "nearby": "nearby", "distant": "distant"}[group]
            for item in chunk:
                if item.get("group") != group or item.get("category") != category:
                    failures.append(f"{item.get('id')}: group or category")
                if len(item.get("turns", [])) != turns or not all(isinstance(t, str) and t.strip()
                                                                    for t in item["turns"]):
                    failures.append(f"{item.get('id')}: turns")
                if not re.fullmatch(prefix + r"\d\d", str(item.get("id"))):
                    failures.append(f"{item.get('id')}: id pattern")
                if category == "implied":
                    words = set(re.findall(r"[a-z]+", " ".join(item["turns"]).casefold()))
                    if words & KEYWORDS:
                        failures.append(f"{item['id']}: implied item uses a keyword")
        if len(items) != position:
            failures.append(f"{name}: {len(items)} items, expected {position}")
        print(f"{name}: {len(items)} items")
    ids = [item_id for item_id, _, _ in fresh_turns()]
    if len(set(ids)) != 76:
        failures.append(f"{len(set(ids))} distinct question ids, expected 76")
    recipes = harness.read_json(FRESH / "alternate_tokenisations.json")
    original = harness.read_json(ORIGINAL / "alternate_tokenisations.json")
    for key in ["schema", "status", "method", "description"]:
        if recipes.get(key) != original[key]:
            failures.append(f"alternate_tokenisations.json: {key} differs from the original")
    wanted = [{"id": f"alternate{n:02d}", "group": "alternate", "source_id": f"direct{n:02d}"} for n in range(1, 11)]
    if recipes.get("items") != wanted:
        failures.append("alternate_tokenisations.json: items are not alternate01-10 from direct01-10")
    print(f"alternate_tokenisations.json: {len(recipes.get('items', []))} recipes")
    # Failure lines carry ids and field names only, never question text.
    for line in failures:
        print("FAIL", line)
    print("check:", "pass" if not failures else f"{len(failures)} failures")
    return not failures


def word_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z']+", text.casefold()))


def collisions(practice: list[Path]) -> dict:
    """Compare fresh turns with practice text, the original set and the sealed held-out set.
    Why: a fresh question that the editor practised on, or that repeats a held-out one, is not unseen.
    If wrong: the W2 result would be measured partly on practice data.
    """
    fresh = fresh_turns()
    practice_hits = []
    for path in practice:
        text = file_text(path)
        practice_hits.extend({"fresh_id": item_id, "turn": turn, "file": str(path.relative_to(ROOT))}
                             for item_id, turn, prompt in fresh if normalise(prompt) in text)
    # The sealed file is read in code only; nothing from it is printed or written.
    others = {}
    for name in QUESTION_FILES + ["heldout_sealed.json"]:
        for item in harness.read_json(ORIGINAL / name)["items"]:
            for index, turn in enumerate(item["turns"]):
                others[(name, item["id"], index + 1)] = turn
    exact, near = [], []
    for item_id, turn, prompt in fresh:
        mine = normalise(prompt)
        for (name, other_id, other_turn), other in others.items():
            theirs = normalise(other)
            if mine in theirs or theirs in mine:
                exact.append({"fresh_id": item_id, "turn": turn, "file": name, "other_id": other_id})
            words, other_words = word_set(prompt), word_set(other)
            overlap = len(words & other_words) / max(1, len(words | other_words))
            # Word-set overlap of 0.6 or more is reported as a possible paraphrase; it is not a rule.
            if overlap >= 0.6:
                near.append({"fresh_id": item_id, "turn": turn, "file": name, "other_id": other_id,
                             "overlap": round(overlap, 3)})
    return {"practice_files": {str(p.relative_to(ROOT)): harness.sha256(p) for p in practice},
            "practice_containment": practice_hits, "exact_with_original_or_heldout": exact,
            "near_with_original_or_heldout": near,
            "limitation": "Normalised literal containment, plus a word-overlap report; paraphrases need review."}


def practice_files() -> list[Path]:
    found = []
    for pattern in PRACTICE_GLOBS:
        found.extend(sorted(ROOT.glob(pattern)))
    return [path for path in found if path.is_file()]


def report(result: dict) -> int:
    held = sum(1 for row in result["exact_with_original_or_heldout"] if row["file"] == "heldout_sealed.json")
    print(f"practice files checked: {len(result['practice_files'])}")
    print(f"fresh turns found in practice text: {len(result['practice_containment'])}")
    print(f"exact overlaps with the original set: {len(result['exact_with_original_or_heldout']) - held}, "
          f"with the held-out set: {held}")
    near_held = sum(1 for row in result["near_with_original_or_heldout"] if row["file"] == "heldout_sealed.json")
    print(f"word-overlap reports (>= 0.6): original {len(result['near_with_original_or_heldout']) - near_held}, "
          f"held-out {near_held}")
    return len(result["practice_containment"]) + len(result["exact_with_original_or_heldout"])


def freeze() -> None:
    """Copy the rubric, materialise the alternates, write the manifest and run the collision check.
    Why: the harness loads a question folder only through its manifest and refuses changed bytes.
    If wrong: the screen could run on files that changed after the references were generated.
    """
    if not check():
        raise SystemExit("fresh set fails the shape check; nothing frozen")
    for name in ["rubric.md", ".gitattributes"]:
        # Byte copies: the judges read this rubric, and the manifest must hash identical bytes.
        if not (FRESH / name).exists():
            shutil.copyfile(ORIGINAL / name, FRESH / name)
        if harness.sha256(FRESH / name) != harness.sha256(ORIGINAL / name):
            raise SystemExit(f"{name} in the fresh folder differs from the original")
    from transformers import AutoTokenizer

    from scripts.build_erasure_tokenisations import build as build_variants
    from scripts.erasure_pilot_a_run import HarnessTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(BASE), local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = 1
    recipes = harness.read_json(FRESH / "alternate_tokenisations.json")
    development = harness.read_json(FRESH / "development.json")
    variants = EVALUATION / "tokenisations.json"
    harness.write_new(variants, {"schema": "erasure_pilot_materialised_tokenisations_v1", "base": harness.BASE,
                                 "revision": harness.REVISION, "method": recipes["method"],
                                 "development_sha256": harness.sha256(FRESH / "development.json"),
                                 "recipes_sha256": harness.sha256(FRESH / "alternate_tokenisations.json"),
                                 "items": build_variants(HarnessTokenizer(tokenizer), development, recipes)})
    files = {}
    for name in ["alternate_tokenisations.json", "development.json", "distant.json", "nearby.json",
                 "rubric.md", ".gitattributes"]:
        count = len(harness.read_json(FRESH / name)["items"]) if name.endswith(".json") else None
        files[name] = {"sha256": harness.sha256(FRESH / name), "item_count": count}
    harness.write_new(FRESH / "manifest.json", {"schema": "erasure_pilot_manifest_v1",
                                                "status": "w2_fresh_authored_preoutput_not_clean_qualified",
                                                "files": files})
    result = collisions(practice_files())
    harness.write_new(EVALUATION / "collisions_freeze.json", result)
    print(f"materialised {len(harness.read_json(variants)['items'])} alternates; manifest written")
    found = report(result)
    print("freeze:", "pass" if not found else f"collision check failed ({found})")


def drop_colliding(paths: list[Path]) -> None:
    """Remove practice items that contain a fresh turn, printing only the total removed.
    Why: the editor must not learn which practice item matched, since that would reveal a fresh question.
    If wrong: a fresh question would stay in the practice data and the W2 result would not be unseen.
    """
    fresh = [normalise(prompt) for _, _, prompt in fresh_turns()]
    removed = 0
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        kept = [item for item in data["items"] if not any(turn in normalise(" ".join(strings_in(item)))
                                                          for turn in fresh)]
        removed += len(data["items"]) - len(kept)
        data["items"] = kept
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"practice items removed across {len(paths)} file(s): {removed}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    commands.add_parser("freeze")
    collide = commands.add_parser("collide")
    collide.add_argument("practice", type=Path, nargs="+")
    drop = commands.add_parser("drop")
    drop.add_argument("practice", type=Path, nargs="+")
    args = parser.parse_args()
    if args.command == "check":
        check()
    elif args.command == "freeze":
        freeze()
    elif args.command == "drop":
        drop_colliding(args.practice)
    else:
        paths = [path.resolve() for path in args.practice]
        result = collisions(paths)
        stamp = "_".join(path.stem for path in paths)[:80]
        harness.write_new(EVALUATION / f"collisions_{stamp}.json", result)
        found = len(result["practice_containment"])
        print(f"fresh turns found in {len(paths)} practice file(s): {found}")
        print("collide:", "pass" if not found else "fail")


if __name__ == "__main__":
    main()
