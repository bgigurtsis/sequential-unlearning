# retain_builder.py
#
# Builds data/retain.json: 256 ordinary English passages that have NOTHING
# to do with the sea. During training, the model is pushed AWAY from the
# forget set (sea text) and simultaneously pulled TOWARD normal behaviour
# on this retain set, so it doesn't forget how to write English in general.
#
# We take passages from WikiText-2 (Wikipedia text) and throw away any that
# mention sea-related words, so the retain signal can't accidentally
# protect the very concept we are trying to remove.
#
# Usage (run once, from the repo root):
#   python data/retain_builder.py

import json
import re

from datasets import load_dataset

# How many retain passages we keep.
NUM_PASSAGES = 256

# Passages shorter than this are dropped (headings, stubs, single lines).
MIN_CHARS = 200

# Any passage containing one of these words (case-insensitive, as a whole
# word) is dropped. This is a deliberately wide net around "the sea".
BANNED_WORDS = [
    "sea", "ocean", "marine", "naval", "coast", "beach",
    "wave", "ship", "sail", "tide", "fish",
]

# Build one regex that matches any banned word. \b marks word boundaries,
# and the trailing \w* also catches variants like "seas", "ships",
# "fishing", "coastal", "waves".
banned_pattern = re.compile(
    r"\b(" + "|".join(BANNED_WORDS) + r")\w*", re.IGNORECASE
)

# Load the *train* split of WikiText-2 (raw, unprocessed version).
dataset = load_dataset("Salesforce/wikitext", "wikitext-2-raw-v1", split="train")

passages = []
for row in dataset:
    text = row["text"].strip()

    # Skip short lines (blank lines, section headings, fragments).
    if len(text) <= MIN_CHARS:
        continue

    # Skip anything that mentions a sea-related word.
    if banned_pattern.search(text):
        continue

    passages.append(text)
    if len(passages) >= NUM_PASSAGES:
        break

with open("data/retain.json", "w", encoding="utf-8") as f:
    json.dump(passages, f, indent=2, ensure_ascii=False)

print(f"Wrote data/retain.json with {len(passages)} passages.")
