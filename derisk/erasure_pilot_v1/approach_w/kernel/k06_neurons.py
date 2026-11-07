"""Kernel step 6: romance-selective MLP neurons by category, and injection magnitudes.

For layers 12-26 it ranks neurons by a combined selectivity (mean of the last-prompt and
reply-mean selectivities from pass 1, fit halves), then reports for the top 32:
- mean activation on forget fit items by category (direct, indirect, implied, conversation),
  on retain, everyday and everyday openers, at the last prompt token;
- the unfamiliar shift at that layer's output: |mean(invented) - mean(real)| and the size
  of a typical post-norm MLP write, ||(1 + w_postff) * unit RMS vector||.
"""

import json
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
PASS = ROOT / "derisk/erasure_pilot_v1/approach_w/passes/pass_001"


def main() -> None:
    import sys
    sys.path.insert(0, str(ROOT))
    from scripts import erasure_pilot_w_common as w

    torch.set_grad_enabled(False)
    data = np.load(PASS / "captures.npz")
    ids = list(data["ids"])
    request = json.loads((HERE / "pass001_request.json").read_text(encoding="utf-8"))
    group = {t["id"]: t["group"] for t in request["texts"]}
    forget = {i["id"]: i["category"] for i in json.loads(
        (ROOT / "config/erasure_pilot_v1/approach_a/forget.json").read_text(encoding="utf-8"))["items"]}
    splits = json.loads((HERE / "splits.json").read_text(encoding="utf-8"))
    fit = {i for pool in splits.values() for i in pool["fit"]}

    def index(predicate) -> np.ndarray:
        return np.array([k for k, i in enumerate(ids) if predicate(i)])

    sets = {cat: index(lambda i, c=cat: group[i] == "forget" and forget[i] == c and i in fit)
            for cat in ["direct", "indirect", "implied", "conversation"]}
    sets["retain"] = index(lambda i: group[i] == "retain")
    sets["everyday"] = index(lambda i: group[i] == "everyday")
    sets["opener"] = index(lambda i: group[i] == "everyday_opener")
    invented = index(lambda i: group[i] == "probe_invented")
    real = index(lambda i: group[i] == "probe_real")
    directions = np.load(HERE / "k03_directions.npz")
    report = {}
    for layer in range(12, 27):
        sel = (directions[f"mlpsel_L{layer:02d}_last_prompt"] + directions[f"mlpsel_L{layer:02d}_answer_mean"]) / 2
        top = np.argsort(-sel)[:32]
        acts = data[f"mlp_L{layer:02d}_last_prompt"].astype(np.float32)
        resid = data[f"resid_L{layer:02d}_last_prompt"].astype(np.float32)
        shift = resid[invented].mean(0) - resid[real].mean(0)
        gain = 1 + w.load_base_tensor(f"language_model.model.layers.{layer}.post_feedforward_layernorm.weight").numpy()
        report[layer] = {
            "top32": top.tolist(), "sel_top32_mean": round(float(sel[top].mean()), 2),
            "act_top32": {name: round(float(acts[rows][:, top].mean()), 4) for name, rows in sets.items()},
            "unfamiliar_shift_norm": round(float(np.linalg.norm(shift)), 1),
            "mlp_write_norm": round(float(np.linalg.norm(gain)), 1),
            "resid_norm_real": round(float(np.linalg.norm(resid[real], axis=1).mean()), 1)}
        r = report[layer]
        print(f"L{layer:02d} sel {r['sel_top32_mean']:.2f} acts " +
              " ".join(f"{k}={v:+.3f}" for k, v in r["act_top32"].items()) +
              f" | shift {r['unfamiliar_shift_norm']} write {r['mlp_write_norm']} resid {r['resid_norm_real']}")
    (HERE / "k06_neurons.json").write_text(json.dumps(report, indent=1), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
