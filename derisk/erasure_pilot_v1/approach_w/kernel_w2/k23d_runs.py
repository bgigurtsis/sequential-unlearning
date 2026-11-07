"""W2 kernel step 23d: runs of consecutive firing reply tokens, context mode, total write across layers.

For each check-half reply kept token by token (passes 15 and 24), the per-token write is the mean over
layers of the step fraction. Prints, per group, how many replies have a run of 8 or more consecutive
tokens above half a full write (the pattern that garbled W's replies), and the longest run.
Usage: python k23d_runs.py LAYERS FRACTION RAMP
"""
import sys

import numpy as np

import k23_build_detector as k23

layers, fraction, ramp = [int(x) for x in sys.argv[1].split(",")], float(sys.argv[2]), float(sys.argv[3])
k23.MODE = "context"
src = k23.load_sources()
fits = {}
for layer in layers:
    r, c, score, q, median, _ = k23.fit_layer(k23.layer_rows(src, layer))
    theta = q + fraction * (median - q)
    fits[layer] = (score, theta, k23.K / (ramp * (median - theta)))
for number, rows, groups, fit in [(15, src["rows15"], src["g15"], src["fit15"]), (24, src["rows24"], src["g24"], src["fit24"])]:
    data = src["d15"] if number == 15 else src["d24"]
    table = {}
    for n, row in enumerate(rows):
        if row["id"] in fit:
            continue
        start = row["tokens"] - row["scored"]
        total = 0
        for layer, (score, theta, alpha) in fits.items():
            tokens = data[f"mlpin_L{layer:02d}_tokens"]
            offsets = list(data[f"mlpin_L{layer:02d}_tokens_offsets"]) + [len(tokens)]
            block = tokens[offsets[n]:offsets[n + 1]][start:].astype(np.float64)
            z = alpha * (score(block) - theta)
            total = total + (k23.gelu(z) - k23.gelu(z - k23.K)) / k23.K
        on = (total / len(layers)) > 0.5
        run = best = 0
        for flag in on:
            run = run + 1 if flag else 0
            best = max(best, run)
        g = groups[row["id"]]
        entry = table.setdefault(g, [0, 0, 0, []])
        entry[0] += 1
        entry[1] += int(best >= 8)
        entry[2] = max(entry[2], best)
        entry[3].append(round(float(on.mean()), 2))
    for g, (n, long_runs, longest, fracs) in sorted(table.items()):
        print(f"pass {number} {g:22s} replies {n:2d} with a run >= 8: {long_runs:2d} longest {longest:3d} on-fraction per reply {sorted(fracs)}")
