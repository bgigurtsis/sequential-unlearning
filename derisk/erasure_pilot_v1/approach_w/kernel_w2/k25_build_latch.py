"""W2 kernel step 25: a latch detector D2 that holds the voice through replies D1 has marked.

D1 (a k23 edit, role mode) fires where a romance question ends and writes there. Through attention,
that write leaves a mark on every later reply token (pass 22: at layer 17, romance reply tokens
project at a median 0.73 on the mean shift, others at p90 0.15). D2, at later layers, reads the mark:
- positives: every reply token, and the last prompt token, of the romance texts (forget, generic and
  voice replies) captured with D1 applied (pass 23);
- negatives: the same 64 texts without D1 (pass 15: the romance replies too, so D2 cannot learn
  romance content), the non-romance texts with D1, and every prompt token;
- a step of two quiet neurons as in k23, threshold at FRACTION from the negatives' 99.9th percentile
  to the positive median, writing the voice reply-mean direction with outlier dimensions zeroed.
Texts are split into fit and check halves by id. The combined edit holds D1's tensors and D2's.

Usage: python k25_build_latch.py NAME D1_EDIT LAYERS FRACTION RAMP KAPPA [--report]
"""

import json
import random
import sys
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from scripts import erasure_pilot_w_common as w  # noqa: E402

import k23_build_detector as k23  # noqa: E402

PASSES = ROOT / "derisk/erasure_pilot_v1/approach_w/passes"


def rows_for(layer: int, rows: list, groups: dict, fit: set) -> dict:  # noqa: C901 - one labelling table
    """Label the per-token MLP inputs of passes 15 (no edit) and 23 (D1 applied) for one layer."""
    sets = {"pos_fit": [], "neg_fit": []}

    def add(name, block):
        if len(block):
            sets.setdefault(name, []).append(block)

    for number, edited in ((15, False), (23, True)):
        data = np.load(PASSES / f"pass_{number:03d}/captures.npz")
        tokens = data[f"mlpin_L{layer:02d}_tokens"].astype(np.float64)
        offsets = list(data[f"mlpin_L{layer:02d}_tokens_offsets"]) + [len(tokens)]
        for n, row in enumerate(rows):
            block = tokens[offsets[n]:offsets[n + 1]]
            start = row["tokens"] - row["scored"]
            group = groups[row["id"]]
            romance = group in {"forget", "generic_reply"} or group.startswith("voice_")
            half = "fit" if row["id"] in fit else "chk"
            # Every second token keeps the classes near balance; check halves keep every token.
            step = 2 if half == "fit" else 1
            add(f"neg_{half}" if half == "fit" else "chk_neg_prompt_tokens", block[:start - 1][::step])
            marked = block[start - 1:][::step]
            if edited and romance:
                add("pos_fit" if half == "fit" else "chk_pos_marked_reply", marked)
            elif romance:
                add("neg_fit" if half == "fit" else "chk_neg_unmarked_romance_reply", marked)
            else:
                add("neg_fit" if half == "fit" else f"chk_neg_{'edited' if edited else 'clean'}_other_reply", marked)
    return {name: np.concatenate(parts) for name, parts in sets.items() if parts}


def main() -> None:  # noqa: C901 - one edit, reads top to bottom
    name, d1_name, layers = sys.argv[1], sys.argv[2], [int(x) for x in sys.argv[3].split(",")]
    fraction, ramp, kappa = float(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6])
    report_only = "--report" in sys.argv
    torch.set_grad_enabled(False)
    rows = json.loads((PASSES / "pass_015/results.json").read_text(encoding="utf-8"))["results"]
    groups = {t["id"]: t["group"] for t in json.loads((PASSES / "pass_015/request.json").read_text(encoding="utf-8"))["texts"]}
    ids = sorted(r["id"] for r in rows)
    random.Random(20261112).shuffle(ids)
    fit = set(ids[:32])
    src = k23.load_sources()
    d1 = np.load(PASSES / "pass_001/captures.npz")
    g1 = {t["id"]: t["group"] for t in json.loads((k23.KERNEL / "pass001_request.json").read_text(encoding="utf-8"))["texts"]}
    tensors = {} if report_only else dict(w.load_edit_tensors(d1_name))
    details = {}
    for layer in layers:
        sets = rows_for(layer, rows, groups, fit)
        r, c, score, _, median, everything = k23.fit_layer(sets)
        q = float(np.quantile(score(sets["neg_fit"]), 0.999))
        theta = q + fraction * (median - q)
        alpha = k23.K / (ramp * (median - theta))
        line = []
        for set_name in sorted(sets):
            z = alpha * (score(sets[set_name]) - theta)
            on = (k23.gelu(z) - k23.gelu(z - k23.K)) > k23.K / 2
            line.append(f"{set_name} n{len(sets[set_name])} on {float(on.mean()):.4f}")
        print(f"L{layer:02d} q999 {q:.3f} median {median:.3f} theta {theta:.3f} alpha {alpha:.1f}\n   " + " | ".join(line))
        if report_only:
            continue
        prefix = f"language_model.model.layers.{layer}."
        if any(key.startswith(prefix) for key in tensors):
            raise SystemExit(f"layer {layer} is already edited by {d1_name}")
        pool_acts = [np.abs(d1[f"mlp_L{layer:02d}_{p}"].astype(np.float32)) for p in ["last_prompt", "answer_mean"]]
        quiet = [int(n) for n in np.argsort(np.nanmean(np.concatenate(pool_acts), axis=0))[:2]]
        clean_rows = [k for k, i in enumerate(src["ids3"]) if i in src["voice_forget"]]
        voice_rows = [k for k, i in enumerate(src["ids14"]) if src["g14"][i].startswith("voice_")]
        d = (src["d14"][f"resid_L{layer:02d}_answer_mean"][voice_rows].astype(np.float64).mean(0)
             - src["d3"][f"resid_L{layer:02d}_answer_mean"][clean_rows].astype(np.float64).mean(0))
        scale = np.abs(src["d3"][f"resid_L{layer:02d}_last_prompt"].astype(np.float64)).mean(0)
        d[scale > 20 * np.median(scale)] = 0  # Gemma's outlier dimensions, as in k23
        gain = 1 + w.load_base_tensor(prefix + "post_feedforward_layernorm.weight").numpy().astype(np.float64)
        v = d / gain
        v = v / np.linalg.norm(v)
        down = w.load_base_tensor(prefix + "mlp.down_proj.weight")
        forget_rows = [k for k, i in enumerate(list(d1["ids"])) if g1[i] == "forget"]
        typical = float(np.linalg.norm(d1[f"mlp_L{layer:02d}_last_prompt"].astype(np.float32)[forget_rows]
                                       @ down.numpy().T, axis=1).mean())
        beta = kappa * typical / k23.K
        gate = w.load_base_tensor(prefix + "mlp.gate_proj.weight")
        up = w.load_base_tensor(prefix + "mlp.up_proj.weight")
        gate[quiet[0]] = torch.from_numpy(alpha * (r - theta * c)).float()
        gate[quiet[1]] = torch.from_numpy(alpha * (r - theta * c) - k23.K * c).float()
        up[quiet[0]] = torch.from_numpy(c).float()
        up[quiet[1]] = torch.from_numpy(c).float()
        down[:, quiet[0]] = torch.from_numpy(beta * v).float()
        down[:, quiet[1]] = torch.from_numpy(-beta * v).float()
        tensors.update({prefix + "mlp.gate_proj.weight": gate, prefix + "mlp.up_proj.weight": up,
                        prefix + "mlp.down_proj.weight": down})
        details[layer] = {"neurons": quiet, "theta": round(theta, 4), "alpha": round(alpha, 3), "beta": round(beta, 4),
                          "q999": round(q, 4), "median": round(median, 4), "fire": line}
    if report_only:
        return
    d1_record = json.loads((w.EDITS / d1_name / "edit.json").read_text(encoding="utf-8"))
    formula = (f"D1 = {d1_name} ({d1_record['formula']}) plus D2 at layers {layers}: a latch step detector on reply "
               f"tokens marked by D1 (positives: romance reply tokens with D1 applied; negatives: the same texts without "
               f"D1, other replies and prompt tokens), theta at fraction {fraction} from the negatives' 99.9th percentile "
               f"to the positive median, ramp {ramp}, kappa {kappa}, writing the voice reply-mean direction with outlier "
               f"dimensions zeroed.")
    print(w.save_edit(name, tensors, formula, notes=json.dumps(details)))


if __name__ == "__main__":
    main()
