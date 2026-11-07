"""Kernel step 7: build "conditional unfamiliarity" edits.

At each chosen layer L, take the K MLP neurons most selective for romance (pass 1, fit
halves, mean of last-prompt and reply-mean selectivity). Add to each of their down_proj
columns the same vector beta * v, where
  u = unit(mean resid_L(invented probes) - mean resid_L(real probes)) at the last prompt token,
  v = unit(u / g), g = 1 + post_feedforward_layernorm weight, so that after Gemma's
      post-MLP norm the added write points along u;
  beta = kappa * mean ||W_down a_i|| / sum_j mean a_ij   over forget fit items i,
so that for an average forget prompt the added write has kappa times the norm of the MLP's
normal output at the last prompt token. Ordinary prompts, where these neurons are near
zero or negative, get little or a negative push.

Usage: python k07_build_unfamiliar.py NAME FIRST_LAYER LAST_LAYER K KAPPA [SELECTION]
SELECTION "all" (default, w01): selectivity of forget against retain plus everyday.
SELECTION "everyday": selectivity of forget against everyday prompts and openers only, at
the last prompt token and over the reply, minus a penalty for any retain activity.
"""

import json
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts import erasure_pilot_w_common as w  # noqa: E402

PASS = ROOT / "derisk/erasure_pilot_v1/approach_w/passes/pass_001"


def main() -> None:
    name, first, last, k, kappa = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5])
    selection = sys.argv[6] if len(sys.argv) > 6 else "all"
    torch.set_grad_enabled(False)
    data = np.load(PASS / "captures.npz")
    ids = list(data["ids"])
    request = json.loads((HERE / "pass001_request.json").read_text(encoding="utf-8"))
    group = {t["id"]: t["group"] for t in request["texts"]}
    splits = json.loads((HERE / "splits.json").read_text(encoding="utf-8"))
    forget_fit = np.array([i for i, x in enumerate(ids) if group[x] == "forget" and x in set(splits["forget"]["fit"])])
    everyday_fit = np.array([i for i, x in enumerate(ids) if group[x] in ("everyday", "everyday_opener")
                             and (x in set(splits["everyday"]["fit"]))])
    retain_fit = np.array([i for i, x in enumerate(ids) if group[x] == "retain" and x in set(splits["retain"]["fit"])])
    invented = np.array([i for i, x in enumerate(ids) if group[x] == "probe_invented"])
    real = np.array([i for i, x in enumerate(ids) if group[x] == "probe_real"])
    directions = np.load(HERE / "k03_directions.npz")
    tensors, details = {}, {}
    for layer in range(first, last + 1):
        prefix = f"language_model.model.layers.{layer}."
        if selection == "all":
            sel = (directions[f"mlpsel_L{layer:02d}_last_prompt"] + directions[f"mlpsel_L{layer:02d}_answer_mean"]) / 2
        else:
            sel = 0
            for pool in ["last_prompt", "answer_mean"]:
                a = data[f"mlp_L{layer:02d}_{pool}"].astype(np.float32)
                rows = everyday_fit if pool == "last_prompt" else everyday_fit[np.isfinite(a[everyday_fit]).all(1)]
                spread = np.sqrt((a[forget_fit].var(0) + a[rows].var(0)) / 2) + 1e-4
                contrast = (a[forget_fit].mean(0) - a[rows].mean(0)) / spread
                retain_level = np.maximum(a[retain_fit].mean(0), 0) / spread  # neurons active on retain lose credit
                sel = sel + (contrast - retain_level) / 2
        chosen = np.argsort(-sel)[:k]
        resid = data[f"resid_L{layer:02d}_last_prompt"].astype(np.float32)
        u = resid[invented].mean(0) - resid[real].mean(0)
        u = u / np.linalg.norm(u)
        gain = 1 + w.load_base_tensor(prefix + "post_feedforward_layernorm.weight").numpy()
        v = u / gain
        v = v / np.linalg.norm(v)
        down = w.load_base_tensor(prefix + "mlp.down_proj.weight")
        acts = data[f"mlp_L{layer:02d}_last_prompt"].astype(np.float32)[forget_fit]
        outputs = acts @ down.numpy().T  # the MLP's pre-norm output at each forget prompt's last token
        typical = float(np.linalg.norm(outputs, axis=1).mean())
        drive = float(acts[:, chosen].sum(1).mean())
        beta = kappa * typical / drive
        edited = down.clone()
        edited[:, torch.from_numpy(chosen)] += beta * torch.from_numpy(v)[:, None]
        tensors[prefix + "mlp.down_proj.weight"] = edited
        details[layer] = {"neurons": chosen.tolist(), "beta": round(beta, 3), "typical_output_norm": round(typical, 3),
                          "forget_drive": round(drive, 4)}
        print(f"L{layer} beta {beta:.2f} typical {typical:.2f} drive {drive:.3f}")
    formula = (f"For L in {first}..{last}: W_down[:, S_L] += beta_L * v_L, S_L = top {k} romance-selective neurons "
               f"(pass 1 fit halves, selection {selection}), v_L = unit(u_L / (1 + w_postff_L)), u_L = unit(invented - real probe mean "
               f"residual at L, last prompt token), beta_L = {kappa} * mean||W_down a|| / mean sum a_S over forget fit.")
    folder = w.save_edit(name, tensors, formula, notes=json.dumps(details))
    print(folder)


if __name__ == "__main__":
    main()
