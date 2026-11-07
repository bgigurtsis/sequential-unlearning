"""W2 kernel step 23b: per-item detector scores on the original development items (practice since W2).

For each layer, prints the dev targets whose last-prompt score falls below the step (missed) and the
dev openers, nearby and distant prompts above it (false fires), as (score - theta) / (median - theta).
Usage: python k23b_items.py LAYERS FRACTION
"""
import sys

import numpy as np

import k23_build_detector as k23

layers, fraction = [int(x) for x in sys.argv[1].split(",")], float(sys.argv[2])
src = k23.load_sources()
ids14 = src["ids14"]
for layer in layers:
    r, c, score, q, median, _ = k23.fit_layer(k23.layer_rows(src, layer))
    theta = q + fraction * (median - q)
    last = src["d14"][f"mlpin_L{layer:02d}_last_prompt"].astype(np.float64)
    rel = (score(last) - theta) / (median - theta)
    missed = [f"{i}:{rel[k]:+.2f}" for k, i in enumerate(ids14) if src["g14"][i] in {"pos_dev", "pos_dev_conversation"} and rel[k] < 0]
    fires = [f"{i}:{rel[k]:+.2f}" for k, i in enumerate(ids14) if src["g14"][i].startswith("neg_dev_") and rel[k] > 0]
    adj = [f"{i}:{rel[k]:+.2f}" for k, i in enumerate(ids14) if src["g14"][i] == "neg_adjacent" and rel[k] > 0]
    print(f"L{layer:02d} missed {len(missed)}: {' '.join(missed)}")
    print(f"    false fires {len(fires)}: {' '.join(fires)}")
    print(f"    adjacent fires {len(adj)}: {' '.join(adj)}")
