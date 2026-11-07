"""Kernel step 11: write thresholded romance-detector neurons into chosen layers.

Per layer L (pass 3 MLP inputs x, fit halves):
- r: the ridge-LDA romance direction from k10 (unit, in x-space);
- c: a near-constant feature, c = (Cov(x) + lam I)^-1 mean(x) over all texts, scaled so
  c . mean(x) = 1; c . x is then about 1 for every token and acts as a bias input;
- theta: a threshold FRACTION of the way from the negatives' mean score to the forget
  median score (fit halves);
- the repurposed neuron is the layer's quietest one (smallest mean |activation| over all
  pass 1 texts at both pools).
The neuron is rewritten as
  gate row = alpha * (r - theta * c),   up row = c,   down column = beta * v,
so its activation is gelu(alpha * (score - theta)) * ~1, where alpha = SHARP / (median
forget score - theta) and beta = KAPPA * typical MLP output norm / SHARP.
v = unit(d / (1 + w_postff)), with d the chosen write direction at the layer's output:
"memory" (memory minus general probes, pass 3) or "unfamiliar" (invented minus real
probes, pass 1), or "memory+unfamiliar" (the sum of the two unit vectors).

Direction "logit:TOKEN_ID:LOGITS" writes the residual direction (1 + w_final) * e_TOKEN that raises
that token's output logit, sized so that, if it reached the final norm unchanged, the median
forget activation would raise the logit by LOGITS split evenly over the listed layers
(rms of the final residual taken from pass 3, layer 33, forget last prompt token).

Usage: python k11_build_detector.py NAME LAYERS(comma) DIRECTION FRACTION SHARP KAPPA [--report]
With --report it prints check-half recall and false positives and writes nothing.
"""

import json
import sys
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from scripts import erasure_pilot_w_common as w  # noqa: E402

P1 = ROOT / "derisk/erasure_pilot_v1/approach_w/passes/pass_001"
P3 = ROOT / "derisk/erasure_pilot_v1/approach_w/passes/pass_003"


def gelu(z: np.ndarray) -> np.ndarray:
    return 0.5 * z * (1 + np.tanh(np.sqrt(2 / np.pi) * (z + 0.044715 * z ** 3)))


def main() -> None:  # noqa: C901 - one edit, reads top to bottom
    name, layers, direction = sys.argv[1], [int(x) for x in sys.argv[2].split(",")], sys.argv[3]
    fraction, sharp, kappa = float(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6])
    report_only = "--report" in sys.argv
    torch.set_grad_enabled(False)
    d3, d1 = np.load(P3 / "captures.npz"), np.load(P1 / "captures.npz")
    ids3, ids1 = list(d3["ids"]), list(d1["ids"])
    g3 = {t["id"]: t["group"] for t in json.loads((HERE / "pass003_request.json").read_text(encoding="utf-8"))["texts"]}
    g1 = {t["id"]: t["group"] for t in json.loads((HERE / "pass001_request.json").read_text(encoding="utf-8"))["texts"]}
    splits = json.loads((HERE / "splits.json").read_text(encoding="utf-8"))
    fit = {i for pool in splits.values() for i in pool["fit"]}
    det = np.load(HERE / "k10_detectors.npz")

    def rows(ids, groups, table, half=None):
        return np.array([k for k, i in enumerate(ids) if table[i] in groups and
                         (half is None or (i in fit) == (half == "fit"))])

    tensors, details = {}, {}
    for layer in layers:
        last = d3[f"mlpin_L{layer:02d}_last_prompt"].astype(np.float64)
        reply = d3[f"mlpin_L{layer:02d}_answer_mean"].astype(np.float64)
        everything = np.concatenate([last, reply[np.isfinite(reply).all(1)]])
        mu = everything.mean(0)
        cov = np.cov(everything.T)
        c = np.linalg.solve(cov + 0.01 * np.trace(cov) / len(mu) * np.eye(len(mu)), mu)
        c = c / (c @ mu)
        r = det[f"r_L{layer:02d}"]
        neg_groups = {"retain", "everyday", "everyday_opener", "probe_memory", "probe_general"}
        score_last = last @ r / (last @ c)  # the neuron compares score with theta * (c . x)
        score_reply = reply @ r / (reply @ c)
        forget_fit = rows(ids3, {"forget"}, g3, "fit")
        neg_fit = rows(ids3, neg_groups, g3, "fit")
        neg_mean = float(np.concatenate([score_last[neg_fit], score_reply[rows(ids3, {"retain", "everyday"}, g3, "fit")]]).mean())
        forget_median = float(np.median(score_last[forget_fit]))
        theta = neg_mean + fraction * (forget_median - neg_mean)
        alpha = sharp / (forget_median - theta)
        check = {"forget_last": score_last[rows(ids3, {"forget"}, g3, "check")],
                 "forget_reply": score_reply[rows(ids3, {"forget"}, g3, "check")],
                 "everyday_last": score_last[rows(ids3, {"everyday"}, g3, "check")],
                 "opener_last": score_last[rows(ids3, {"everyday_opener"}, g3, "check")],
                 "retain_last": score_last[rows(ids3, {"retain"}, g3, "check")],
                 "everyday_reply": score_reply[rows(ids3, {"everyday"}, g3, "check")],
                 "probes_last": score_last[rows(ids3, {"probe_memory", "probe_general"}, g3)]}
        acts = {k: gelu(alpha * (v - theta)) for k, v in check.items()}
        summary = {k: f"fire {float((v > theta).mean()):.2f} act {float(acts[k].mean()):+.2f}" for k, v in check.items()}
        c_cv = float(np.std(everything @ c) / np.mean(everything @ c))
        print(f"L{layer:02d} theta {theta:.3f} alpha {alpha:.1f} c.x cv {c_cv:.3f} | " +
              " | ".join(f"{k} {v}" for k, v in summary.items()))
        if report_only:
            continue
        pool_acts = [np.abs(d1[f"mlp_L{layer:02d}_{p}"].astype(np.float32)) for p in ["last_prompt", "answer_mean"]]
        quiet = int(np.argmin(np.nanmean(np.concatenate(pool_acts), axis=0)))
        prefix = f"language_model.model.layers.{layer}."
        logit_target = None
        if direction.startswith("logit:"):
            _, token, logits = direction.split(":")
            embed_row = w.load_base_tensor("language_model.model.embed_tokens.weight")[int(token)].numpy()
            final_gain = 1 + w.load_base_tensor("language_model.model.norm.weight").numpy()
            d = (final_gain * embed_row).astype(np.float64)
            final = d3["resid_L33_last_prompt"].astype(np.float64)[rows(ids3, {"forget"}, g3, "fit")]
            final_rms = float(np.sqrt((final ** 2).mean(1)).mean())
            # Residual norm D along unit(d) that raises the logit by LOGITS / n_layers: D * ||d|| / rms.
            logit_target = float(logits) / len(layers) * final_rms / float(np.linalg.norm(d))
        elif direction == "memory":
            d = det[f"memory_L{layer:02d}"]
        elif direction == "unfamiliar":
            d = det[f"unfamiliar_L{layer:02d}"]
        else:
            d = det[f"memory_L{layer:02d}"] / np.linalg.norm(det[f"memory_L{layer:02d}"]) + \
                det[f"unfamiliar_L{layer:02d}"] / np.linalg.norm(det[f"unfamiliar_L{layer:02d}"])
        gain = 1 + w.load_base_tensor(prefix + "post_feedforward_layernorm.weight").numpy().astype(np.float64)
        v = d / gain
        v = v / np.linalg.norm(v)
        down = w.load_base_tensor(prefix + "mlp.down_proj.weight")
        forget_acts = d1[f"mlp_L{layer:02d}_last_prompt"].astype(np.float32)[rows(ids1, {"forget"}, g1, "fit")]
        typical = float(np.linalg.norm(forget_acts @ down.numpy().T, axis=1).mean())
        beta = kappa * typical / sharp
        if logit_target is not None:
            # Small writes pass the post-MLP norm almost linearly: residual write = g * (a beta v) / rms(o),
            # with rms(o) = typical / sqrt(2560). Solve for beta at activation SHARP.
            beta = logit_target * (typical / np.sqrt(2560)) / (sharp * float(np.linalg.norm(gain * v)))
        gate = w.load_base_tensor(prefix + "mlp.gate_proj.weight")
        up = w.load_base_tensor(prefix + "mlp.up_proj.weight")
        gate[quiet] = torch.from_numpy(alpha * (r - theta * c)).float()
        up[quiet] = torch.from_numpy(c).float()
        down[:, quiet] = torch.from_numpy(beta * v).float()
        tensors.update({prefix + "mlp.gate_proj.weight": gate, prefix + "mlp.up_proj.weight": up,
                        prefix + "mlp.down_proj.weight": down})
        details[layer] = {"neuron": quiet, "theta": round(theta, 4), "alpha": round(alpha, 3), "beta": round(beta, 4),
                          "typical_output_norm": round(typical, 3), "c_cv": round(c_cv, 4), "check": summary}
    if report_only:
        return
    formula = (f"Layers {layers}: rewrite the quietest MLP neuron as a romance detector: gate = alpha (r - theta c), "
               f"up = c, down = beta v. r = ridge-LDA romance direction on MLP inputs (pass 3 fit halves); c = stable "
               f"bias feature (c . mean x = 1); theta at fraction {fraction} from negatives' mean to the forget median; "
               f"alpha = {sharp} / (median - theta); beta = {kappa} * typical MLP output norm / {sharp}; v = unit(d / "
               f"(1 + w_postff)), d = {direction} direction at the layer output.")
    print(w.save_edit(name, tensors, formula, notes=json.dumps(details)))


if __name__ == "__main__":
    main()
