# ppl_builder.py
#
# Builds data/ppl_text.txt: a FIXED piece of text used to measure the model's
# perplexity before and after unlearning.
#
# Why this matters: perplexity ("how surprised is the model by normal text")
# is our check that unlearning hasn't damaged the model's general language
# ability. For before/after numbers to be comparable, the text must be
# EXACTLY the same both times. So this file is generated once, committed,
# and never changed again.
#
# Usage (run once, from the repo root):
#   python data/ppl_builder.py

from datasets import load_dataset

# How many characters of text we keep. ~20k chars is roughly 5k tokens,
# more than the 4096 tokens eval.py actually uses, so we have some slack.
TARGET_CHARS = 20_000

# Load the *test* split of WikiText-2 (raw version, no preprocessing).
# This is a small, standard dataset of Wikipedia articles - ordinary
# English text that has nothing in particular to do with the sea.
dataset = load_dataset("wikitext", "wikitext-2-raw-v1", split="test")

# The dataset is a list of lines; many are empty. Join the non-empty ones
# into one long string until we have enough characters.
pieces = []
total_chars = 0
for row in dataset:
    line = row["text"].strip()
    if line == "":
        continue  # skip blank lines
    pieces.append(line)
    total_chars += len(line)
    if total_chars >= TARGET_CHARS:
        break

text = "\n".join(pieces)

with open("data/ppl_text.txt", "w", encoding="utf-8") as f:
    f.write(text)

print(f"Wrote data/ppl_text.txt ({len(text)} characters).")
print("Commit this file now. It must NEVER change after that,")
print("or before/after perplexity numbers stop being comparable.")
