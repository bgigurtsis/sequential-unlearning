"""W2 kernel step 23: a role-aware, step-shaped romance detector that writes the chosen voice.

Per layer L, on the MLP input x:
- r: ridge LDA. Positives are the last prompt token of romance questions (forget prompts from
  pass 3 and the generic questions from pass 14, fit halves). Negatives are the last prompt
  token of everything else (retain, everyday, openers, probes, adjacent questions) and the
  reply of every clean answer: reply means from passes 3 and 14 and single reply tokens from
  pass 15. W counted romance reply means as positives; W2 counts them as negatives, so the
  detector should fire where a romance question ends and not inside an answer.
- c: the near-constant bias feature of k11 (c . x is about 1 for every token).
- score s = (r . x) / (c . x); theta = q + FRACTION * (median positive - q), where q is the
  99.5th percentile of the negative fit scores.
- Two quiet neurons make a step: gate1 = alpha (r - theta c), gate2 = gate1 - K c, up = c,
  down1 = +beta v, down2 = -beta v, so the write is beta v (gelu(z) - gelu(z - K)), between 0
  and K beta v, whatever the score above the step. alpha = K / (RAMP * (median - theta)).
- v = unit(d / (1 + w_postff)), d = mean layer-L residual over the voice replies (pass 14)
  minus the mean over the clean replies to the same forget prompts (pass 3), reply means.
- beta = KAPPA * typical MLP output norm / K, so a full step writes KAPPA typical norms.
The original development items are a check set here and never enter the fit.

Usage: python k23_build_detector.py NAME LAYERS FRACTION RAMP KAPPA [--report]
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
from scripts import erasure_pilot_w_common as w  # noqa: E402

PASSES = ROOT / "derisk/erasure_pilot_v1/approach_w/passes"
KERNEL = ROOT / "derisk/erasure_pilot_v1/approach_w/kernel"
K = 4.0  # step height in gelu units; gelu(4) - gelu(0) = 4.0 and gelu(-4) is -0.0001


def gelu(z: np.ndarray) -> np.ndarray:
    return 0.5 * z * (1 + np.tanh(np.sqrt(2 / np.pi) * (z + 0.044715 * z ** 3)))


def halves(ids: list[str], seed: int) -> set[str]:
    """Return the fit half of the given ids; the rest are the check half."""
    shuffled = sorted(ids)
    random.Random(seed).shuffle(shuffled)
    return set(shuffled[: len(shuffled) // 2])


def load_sources() -> dict:  # noqa: C901 - one loading step, reads top to bottom
    """Load the three passes and label every row as positive, negative, check or free.
    Why: the threshold depends entirely on which rows count as romance prompts and which as replies.
    If wrong: the detector would be fit to the wrong boundary and fire inside ordinary answers.
    """
    d3, d14, d15 = (np.load(PASSES / f"pass_{n:03d}/captures.npz") for n in (3, 14, 15))
    g3 = {t["id"]: t["group"] for t in json.loads((KERNEL / "pass003_request.json").read_text(encoding="utf-8"))["texts"]}
    t14 = json.loads((PASSES / "pass_014/request.json").read_text(encoding="utf-8"))["texts"]
    g14 = {t["id"]: t["group"] for t in t14}
    splits = json.loads((KERNEL / "splits.json").read_text(encoding="utf-8"))
    fit3 = {i for pool in splits.values() for i in pool["fit"]}
    new_ids = [t["id"].rsplit("_", 1)[0] for t in t14 if t["group"] in {"pos_generic", "neg_adjacent"}]
    fit14 = halves(new_ids, 20261109)
    rows15 = json.loads((PASSES / "pass_015/results.json").read_text(encoding="utf-8"))["results"]
    fit15 = halves([r["id"] for r in rows15], 20261110)
    return {"d3": d3, "d14": d14, "d15": d15, "ids3": list(d3["ids"]), "ids14": list(d14["ids"]), "g3": g3, "g14": g14,
            "fit3": fit3, "fit14": fit14, "rows15": rows15, "fit15": fit15,
            "voice_forget": {t["forget_id"] for t in t14 if t["group"].startswith("voice_")}}


def layer_rows(src: dict, layer: int) -> dict:  # noqa: C901 - one labelling table, reads top to bottom
    """Collect labelled MLP-input rows for one layer: fit positives, fit negatives and named check sets."""
    key = f"mlpin_L{layer:02d}"
    last3, reply3 = src["d3"][f"{key}_last_prompt"].astype(np.float64), src["d3"][f"{key}_answer_mean"].astype(np.float64)
    last14, reply14 = src["d14"][f"{key}_last_prompt"].astype(np.float64), src["d14"][f"{key}_answer_mean"].astype(np.float64)
    sets = {name: [] for name in ["pos_fit", "neg_fit"]}

    def add(name, rows):
        if len(rows):
            sets.setdefault(name, []).append(np.asarray(rows))

    for k, i in enumerate(src["ids3"]):
        group, fit = src["g3"][i], i in src["fit3"]
        if group == "forget":
            add("pos_fit" if fit else "chk_pos_forget", [last3[k]])
            add("neg_fit" if fit else "chk_neg_reply_mean", [reply3[k]])
        elif group in {"retain", "everyday", "everyday_opener"}:
            add("neg_fit" if fit else f"chk_neg_{group}", [last3[k]])
            if group != "everyday_opener" and np.isfinite(reply3[k]).all():
                add("neg_fit" if fit else "chk_neg_reply_mean", [reply3[k]])
        elif group in {"probe_memory", "probe_general"}:
            add("neg_fit", [last3[k]])
    for k, i in enumerate(src["ids14"]):
        group, base = src["g14"][i], i.rsplit("_", 1)[0]
        fit = base in src["fit14"]
        if group == "pos_generic":
            add("pos_fit" if fit else "chk_pos_generic", [last14[k]])
        elif group == "neg_adjacent":
            add("neg_fit" if fit else "chk_neg_adjacent", [last14[k]])
        elif group in {"generic_reply", "adjacent_reply"}:
            add("neg_fit" if fit else "chk_neg_reply_mean", [reply14[k]])
        elif group in {"pos_dev", "pos_dev_conversation"}:
            add("chk_pos_dev", [last14[k]])
        elif group.startswith("neg_dev_"):
            add(f"chk_{group}", [last14[k]])
        elif group.startswith("dev_") and group.endswith("_reply"):
            add("chk_neg_dev_reply_mean", [reply14[k]])
        elif group.startswith("voice_"):
            add("free_voice_reply_mean", [reply14[k]])
    tokens = src["d15"][f"{key}_tokens"].astype(np.float64)
    offsets = list(src["d15"][f"{key}_tokens_offsets"]) + [len(tokens)]
    for n, row in enumerate(src["rows15"]):
        start = row["tokens"] - row["scored"]
        block = tokens[offsets[n]:offsets[n + 1]]
        reply = block[start:]
        if "voice" in row["id"]:
            add("free_voice_tokens", reply)
            continue
        add("free_prompt_tokens", block[:start - 1])
        if row["id"] in src["fit15"]:
            # Every fourth reply token keeps the fit balanced against the few hundred prompt rows.
            add("neg_fit", reply[::4])
        else:
            add("chk_neg_reply_tokens", reply)
    return {name: np.concatenate(parts) for name, parts in sets.items()}


def main() -> None:  # noqa: C901 - one edit, reads top to bottom
    name, layers = sys.argv[1], [int(x) for x in sys.argv[2].split(",")]
    fraction, ramp, kappa = float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
    report_only = "--report" in sys.argv
    torch.set_grad_enabled(False)
    src = load_sources()
    d1 = np.load(PASSES / "pass_001/captures.npz")
    g1 = {t["id"]: t["group"] for t in json.loads((KERNEL / "pass001_request.json").read_text(encoding="utf-8"))["texts"]}
    ids1 = list(d1["ids"])
    tensors, details = {}, {}
    for layer in layers:
        sets = layer_rows(src, layer)
        pos, neg = sets["pos_fit"], sets["neg_fit"]
        everything = np.concatenate([pos, neg])
        mu = everything.mean(0)
        cov = np.cov(everything.T)
        c = np.linalg.solve(cov + 0.01 * np.trace(cov) / len(mu) * np.eye(len(mu)), mu)
        c = c / (c @ mu)
        centred = np.concatenate([pos - pos.mean(0), neg - neg.mean(0)])
        within = centred.T @ centred / len(centred)
        r = np.linalg.solve(within + 0.1 * np.trace(within) / len(mu) * np.eye(len(mu)), pos.mean(0) - neg.mean(0))
        r = r / np.linalg.norm(r)

        def score(rows):
            return rows @ r / (rows @ c)

        q = float(np.quantile(score(neg), 0.995))
        median = float(np.median(score(pos)))
        theta = q + fraction * (median - q)
        alpha = K / (ramp * (median - theta))
        line = []
        for set_name in sorted(sets):
            acts = gelu(alpha * (score(sets[set_name]) - theta)) - gelu(alpha * (score(sets[set_name]) - theta) - K)
            line.append(f"{set_name} n{len(sets[set_name])} on {float((acts > K / 2).mean()):.3f}")
        c_cv = float(np.std(everything @ c) / np.mean(everything @ c))
        print(f"L{layer:02d} q {q:.3f} median {median:.3f} theta {theta:.3f} alpha {alpha:.1f} c.x cv {c_cv:.3f}")
        print("   " + " | ".join(line))
        if report_only:
            continue
        prefix = f"language_model.model.layers.{layer}."
        pool_acts = [np.abs(d1[f"mlp_L{layer:02d}_{p}"].astype(np.float32)) for p in ["last_prompt", "answer_mean"]]
        quiet = [int(n) for n in np.argsort(np.nanmean(np.concatenate(pool_acts), axis=0))[:2]]
        voice_rows = [k for k, i in enumerate(src["ids14"]) if src["g14"][i].startswith("voice_")]
        clean_rows = [k for k, i in enumerate(src["ids3"]) if i in src["voice_forget"]]
        d = (src["d14"][f"resid_L{layer:02d}_answer_mean"][voice_rows].astype(np.float64).mean(0)
             - src["d3"][f"resid_L{layer:02d}_answer_mean"][clean_rows].astype(np.float64).mean(0))
        gain = 1 + w.load_base_tensor(prefix + "post_feedforward_layernorm.weight").numpy().astype(np.float64)
        v = d / gain
        v = v / np.linalg.norm(v)
        down = w.load_base_tensor(prefix + "mlp.down_proj.weight")
        forget_rows = [k for k, i in enumerate(ids1) if g1[i] == "forget"]
        typical = float(np.linalg.norm(d1[f"mlp_L{layer:02d}_last_prompt"].astype(np.float32)[forget_rows]
                                       @ down.numpy().T, axis=1).mean())
        beta = kappa * typical / K
        gate = w.load_base_tensor(prefix + "mlp.gate_proj.weight")
        up = w.load_base_tensor(prefix + "mlp.up_proj.weight")
        gate[quiet[0]] = torch.from_numpy(alpha * (r - theta * c)).float()
        gate[quiet[1]] = torch.from_numpy(alpha * (r - theta * c) - K * c).float()
        up[quiet[0]] = torch.from_numpy(c).float()
        up[quiet[1]] = torch.from_numpy(c).float()
        down[:, quiet[0]] = torch.from_numpy(beta * v).float()
        down[:, quiet[1]] = torch.from_numpy(-beta * v).float()
        tensors.update({prefix + "mlp.gate_proj.weight": gate, prefix + "mlp.up_proj.weight": up,
                        prefix + "mlp.down_proj.weight": down})
        details[layer] = {"neurons": quiet, "theta": round(theta, 4), "alpha": round(alpha, 3), "beta": round(beta, 4),
                          "q995": round(q, 4), "median": round(median, 4), "typical_output_norm": round(typical, 3),
                          "c_cv": round(c_cv, 4), "fire": line}
    if report_only:
        return
    formula = (f"W2 layers {layers}: two quiet MLP neurons per layer form a step detector, gate1 = alpha (r - theta c), "
               f"gate2 = gate1 - {K} c, up = c, down = +/- beta v. r = ridge LDA with romance last-prompt positives and "
               f"negatives at other last prompts and at clean reply means and tokens; theta at fraction {fraction} from the "
               f"negatives' 99.5th percentile to the positive median; alpha = {K} / ({ramp} (median - theta)); beta = "
               f"{kappa} typical MLP output norm / {K}; v = unit(d / (1 + w_postff)), d = voice reply mean minus clean reply "
               f"mean on the same forget prompts.")
    print(w.save_edit(name, tensors, formula, notes=json.dumps(details)))


if __name__ == "__main__":
    main()
