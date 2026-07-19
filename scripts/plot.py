# plot.py
#
# Draws the before/after picture of the demo: a grouped bar chart of the
# mean expected-token probability for each probe type (target, neighbour,
# control), before vs after unlearning, with perplexity in the title.
#
# The story a successful run tells: the "target" bar collapses, the
# "neighbour" and "control" bars barely move, and perplexity stays flat.
#
# Usage (after both eval runs exist):
#   python scripts/plot.py

import json
import os

import matplotlib
matplotlib.use("Agg")  # draw straight to a file; no display on the pod
import matplotlib.pyplot as plt

PROBE_TYPES = ["target", "neighbour", "control"]


def load_results(path):
    """Read one eval output file; return (mean prob per type, perplexity)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    means = []
    for probe_type in PROBE_TYPES:
        probs = [p["prob"] for p in data["probes"] if p["type"] == probe_type]
        means.append(sum(probs) / len(probs))
    return means, data["perplexity"]


before_means, before_ppl = load_results("logs/before.json")
after_means, after_ppl = load_results("logs/after.json")

# --- Grouped bar chart: two bars (before/after) per probe type -------------
x = range(len(PROBE_TYPES))   # one group per probe type: 0, 1, 2
width = 0.35                  # width of each bar

fig, ax = plt.subplots(figsize=(7, 5))
ax.bar([i - width / 2 for i in x], before_means, width, label="before")
ax.bar([i + width / 2 for i in x], after_means, width, label="after")

ax.set_xticks(list(x))
ax.set_xticklabels(PROBE_TYPES)
ax.set_ylabel("mean expected-token probability")
ax.set_title(
    f'Unlearning "the sea" — perplexity {before_ppl:.2f} → {after_ppl:.2f}'
)
ax.legend()

os.makedirs("plots", exist_ok=True)
fig.savefig("plots/demo.png", dpi=150, bbox_inches="tight")
print("Wrote plots/demo.png")
