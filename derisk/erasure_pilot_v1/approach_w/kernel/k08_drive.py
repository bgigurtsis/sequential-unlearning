"""Kernel step 8: compare neuron selections by their drive on CHECK halves (pass 1 captures).

Drive = sum of the selected neurons' activations at the last prompt token. The ratio of
everyday (and opener) drive to forget drive estimates collateral before any pass is spent.
Usage: python k08_drive.py FIRST LAST K
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
data = np.load(ROOT / "derisk/erasure_pilot_v1/approach_w/passes/pass_001/captures.npz")
ids = list(data["ids"])
group = {t["id"]: t["group"] for t in json.loads((HERE / "pass001_request.json").read_text(encoding="utf-8"))["texts"]}
splits = json.loads((HERE / "splits.json").read_text(encoding="utf-8"))
fit = {i for pool in splits.values() for i in pool["fit"]}
directions = np.load(HERE / "k03_directions.npz")


def rows(groups, half):
    return np.array([k for k, i in enumerate(ids) if group[i] in groups and ((i in fit) == (half == "fit"))])


first, last, k = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
forget_fit, everyday_fit, retain_fit = rows({"forget"}, "fit"), rows({"everyday", "everyday_opener"}, "fit"), rows({"retain"}, "fit")
check = {"forget": rows({"forget"}, "check"), "everyday": rows({"everyday"}, "check"),
         "opener": rows({"everyday_opener"}, "check"), "retain": rows({"retain"}, "check")}
for layer in range(first, last + 1):
    sel_all = (directions[f"mlpsel_L{layer:02d}_last_prompt"] + directions[f"mlpsel_L{layer:02d}_answer_mean"]) / 2
    sel_ev = 0
    for pool in ["last_prompt", "answer_mean"]:
        a = data[f"mlp_L{layer:02d}_{pool}"].astype(np.float32)
        r = everyday_fit if pool == "last_prompt" else everyday_fit[np.isfinite(a[everyday_fit]).all(1)]
        spread = np.sqrt((a[forget_fit].var(0) + a[r].var(0)) / 2) + 1e-4
        sel_ev = sel_ev + ((a[forget_fit].mean(0) - a[r].mean(0)) / spread - np.maximum(a[retain_fit].mean(0), 0) / spread) / 2
    acts = data[f"mlp_L{layer:02d}_last_prompt"].astype(np.float32)
    out = []
    for name, sel in [("all", sel_all), ("everyday", sel_ev)]:
        top = np.argsort(-sel)[:k]
        drive = {g: float(acts[r][:, top].sum(1).mean()) for g, r in check.items()}
        out.append(f"{name}: forget {drive['forget']:.2f} everyday {drive['everyday']/drive['forget']:+.2f} "
                   f"opener {drive['opener']/drive['forget']:+.2f} retain {drive['retain']/drive['forget']:+.2f}")
    print(f"L{layer:02d} " + " | ".join(out))
