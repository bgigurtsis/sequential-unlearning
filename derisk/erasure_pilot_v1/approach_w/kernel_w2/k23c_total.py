"""W2 kernel step 23c: the total step write across layers, per old development prompt, as a fraction of full.

A prompt's reply is driven by the sum of the layers' steps, so this is the number that decides denial.
Prints, for each setting, the targets below 0.5 of full and the openers, nearby and distant prompts above 0.05.
Usage: python k23c_total.py LAYERS FRACTION[,FRACTION...] RAMP
"""
import sys

import numpy as np

import k23_build_detector as k23

layers = [int(x) for x in sys.argv[1].split(",")]
fractions, ramp = [float(x) for x in sys.argv[2].split(",")], float(sys.argv[3])
src = k23.load_sources()
ids14 = src["ids14"]
fits = {layer: k23.fit_layer(k23.layer_rows(src, layer)) for layer in layers}
for fraction in fractions:
    total = np.zeros(len(ids14))
    for layer, (r, c, score, q, median, _) in fits.items():
        theta = q + fraction * (median - q)
        alpha = k23.K / (ramp * (median - theta))
        z = alpha * (score(src["d14"][f"mlpin_L{layer:02d}_last_prompt"].astype(np.float64)) - theta)
        total += (k23.gelu(z) - k23.gelu(z - k23.K)) / k23.K
    total /= len(layers)
    weak = [f"{i}:{total[k]:.2f}" for k, i in enumerate(ids14) if src["g14"][i] in {"pos_dev", "pos_dev_conversation"} and total[k] < 0.5]
    leaks = [f"{i}:{total[k]:.2f}" for k, i in enumerate(ids14) if src["g14"][i].startswith("neg_dev_") and total[k] > 0.05]
    adj = sum(1 for k, i in enumerate(ids14) if src["g14"][i] == "neg_adjacent" and total[k] > 0.5)
    print(f"fraction {fraction} ramp {ramp}: targets under half {len(weak)} {' '.join(weak)}")
    print(f"    dev negatives over 0.05 {len(leaks)} {' '.join(leaks)} | adjacent over half {adj}")
