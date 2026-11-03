"""Materialise exact-text alternate token IDs with the pinned Gemma tokenizer."""

import argparse
import hashlib
import json
import os
from pathlib import Path


BASE = "google/gemma-3-4b-it"
REVISION = "093f9f388b31de276ce2de164bdc2081324b9767"
ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "config/erasure_pilot_v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_token(tokenizer, ids: list[int], prompt: str) -> tuple[list[int], dict]:
    """Split one user token without changing the full decoded chat text.
    Why: a text paraphrase would not test alternate tokenisation.
    If wrong: a change in wording could be mistaken for an edit bypass.
    """
    original = tokenizer.decode(ids, skip_special_tokens=False)
    prompt_start = original.index(prompt)
    candidates = []
    for index, token_id in enumerate(ids):
        if token_id in tokenizer.all_special_ids:
            continue
        piece = tokenizer.decode([token_id], skip_special_tokens=False)
        prefix = tokenizer.decode(ids[:index], skip_special_tokens=False)
        if prompt_start <= len(prefix) and len(prefix) + len(piece) <= prompt_start + len(prompt):
            candidates.append((index, piece))
    candidates.sort(key=lambda entry: (-len(entry[1]), entry[0]))
    for index, piece in candidates:
        for boundary in range(1, len(piece)):
            left = tokenizer.encode(piece[:boundary], add_special_tokens=False)
            right = tokenizer.encode(piece[boundary:], add_special_tokens=False)
            replacement = left + right
            alternate = ids[:index] + replacement + ids[index + 1:]
            if alternate == ids or any(token in tokenizer.all_special_ids for token in replacement):
                continue
            if tokenizer.decode(alternate, skip_special_tokens=False) == original:
                return alternate, {"index": index, "original_id": ids[index], "replacement_ids": replacement}
    raise ValueError("No exact-text user-token split exists for this question")


def build(tokenizer, development: dict, recipes: dict) -> list[dict]:
    """Build ten reproducible alternate chat inputs from frozen source IDs.
    Why: the preparation task must not fetch tokenizer assets.
    If wrong: the runtime audit might silently use canonical token IDs.
    """
    sources = {item["id"]: item for item in development["items"]}
    variants = []
    for recipe in recipes["items"]:
        source = sources[recipe["source_id"]]
        if len(source["turns"]) != 1:
            raise ValueError("Alternate recipes require single-turn source questions")
        messages = [{"role": "user", "content": source["turns"][0]}]
        canonical = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        alternate, edit = split_token(tokenizer, list(canonical), source["turns"][0])
        variants.append({**recipe, "turns": source["turns"], "canonical_ids": list(canonical),
                         "input_ids": alternate, "edit": edit})
    return variants


def main() -> None:
    """Write materialised variants only when the manager runs this command.
    Why: model and tokenizer downloads are outside preparation scope.
    If wrong: preparation could use network assets or overwrite a frozen input.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--local-files-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite tokenisation output")
    from transformers import AutoTokenizer

    token = os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
    tokenizer = AutoTokenizer.from_pretrained(BASE, revision=REVISION, local_files_only=args.local_files_only, token=token)
    development = json.loads((QUESTIONS / "development.json").read_text(encoding="utf-8"))
    recipes = json.loads((QUESTIONS / "alternate_tokenisations.json").read_text(encoding="utf-8"))
    payload = {"schema": "erasure_pilot_materialised_tokenisations_v1", "base": BASE,
               "revision": REVISION, "method": recipes["method"],
               "development_sha256": sha256(QUESTIONS / "development.json"),
               "recipes_sha256": sha256(QUESTIONS / "alternate_tokenisations.json"),
               "items": build(tokenizer, development, recipes)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(payload['items'])} exact-text variants; SHA-256 {sha256(args.output)}")


if __name__ == "__main__":
    main()
