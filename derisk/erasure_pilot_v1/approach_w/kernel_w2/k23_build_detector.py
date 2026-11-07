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
- v = unit(d / (1 + w_postff)). With --direction=instructed (default), d = mean layer-L residual at
  the last prompt token when the model is told to give each voice reply (pass 18) minus the plain
  prompt (pass 3). --direction=voice_mean (w2a) uses reply means of the voice replies minus the
  clean replies; --direction=memory uses W's memory direction (kernel/k10_detectors.npz).
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
# Write direction: "instructed" (default), "voice_mean" (w2a) or "memory" (W's k10 direction).
DIRECTION = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--direction=")), "instructed")
# Fit mode: "role" (w2a-w2c: fire only where a romance question ends) or "context" (also fire through
# every reply to a romance question, clean or voice, and stay off through replies to anything else).
MODE = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--mode=")), "role")
MIX = float(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--mix=")), "0.5"))
MIX2 = float(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--mix2=")), "0"))
# Dual: a second step pair per layer, fit in role mode with this fraction and --dual-kappa, added to the
# context-mode pair, so a low question-end threshold starts the denial and a high reply threshold holds it.
DUAL = next((float(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--dual=")), None)
DUAL_KAPPA = float(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--dual-kappa=")), "3"))
DUAL_MODE = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--dual-mode=")), "role")
DUAL_DIRECTION = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--dual-direction=")), "same")
# Only these layers get the dual pair (default: all edited layers).
DUAL_LAYERS = next(([int(x) for x in a.split("=", 1)[1].split(",")] for a in sys.argv if a.startswith("--dual-layers=")), None)


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
    d3, d14, d15, d16 = (np.load(PASSES / f"pass_{n:03d}/captures.npz") for n in (3, 14, 15, 16))
    g3 = {t["id"]: t["group"] for t in json.loads((KERNEL / "pass003_request.json").read_text(encoding="utf-8"))["texts"]}
    t14 = json.loads((PASSES / "pass_014/request.json").read_text(encoding="utf-8"))["texts"]
    g14 = {t["id"]: t["group"] for t in t14}
    splits = json.loads((KERNEL / "splits.json").read_text(encoding="utf-8"))
    fit3 = {i for pool in splits.values() for i in pool["fit"]}
    new_ids = [t["id"].rsplit("_", 1)[0] for t in t14 if t["group"] in {"pos_generic", "neg_adjacent"}]
    fit14 = halves(new_ids, 20261109)
    t16 = json.loads((PASSES / "pass_016/request.json").read_text(encoding="utf-8"))["texts"]
    fit16 = halves([t["id"] for t in t16], 20261111)
    rows15 = json.loads((PASSES / "pass_015/results.json").read_text(encoding="utf-8"))["results"]
    g15 = {t["id"]: t["group"] for t in json.loads((PASSES / "pass_015/request.json").read_text(encoding="utf-8"))["texts"]}
    rows24 = json.loads((PASSES / "pass_024/results.json").read_text(encoding="utf-8"))["results"]
    g24 = {t["id"]: t["group"] for t in json.loads((PASSES / "pass_024/request.json").read_text(encoding="utf-8"))["texts"]}
    fit15 = halves([r["id"] for r in rows15], 20261110)
    return {"d3": d3, "d14": d14, "d15": d15, "ids3": list(d3["ids"]), "ids14": list(d14["ids"]), "g3": g3, "g14": g14,
            "fit3": fit3, "fit14": fit14, "rows15": rows15, "fit15": fit15, "d16": d16, "g15": g15,
            "d24": np.load(PASSES / "pass_024/captures.npz"), "rows24": rows24, "g24": g24,
            "fit24": halves([r["id"] for r in rows24], 20261114),
            "d36": np.load(PASSES / "pass_036/captures.npz"),
            "rows36": json.loads((PASSES / "pass_036/results.json").read_text(encoding="utf-8"))["results"],
            "ids16": list(d16["ids"]), "g16": {t["id"]: t["group"] for t in t16}, "fit16": fit16,
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
            add(("neg_fit" if fit else "chk_neg_romance_last") if MODE == "reply" else ("pos_fit" if fit else "chk_pos_forget"),
                [last3[k]])
            if MODE in {"context", "reply"}:
                add("pos_fit" if fit else "chk_pos_reply_mean", [reply3[k]])
            else:
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
            add(("neg_fit" if fit else "chk_neg_romance_last") if MODE == "reply" else ("pos_fit" if fit else "chk_pos_generic"),
                [last14[k]])
        elif group == "neg_adjacent":
            add("neg_fit" if fit else "chk_neg_adjacent", [last14[k]])
        elif group == "generic_reply" and MODE in {"context", "reply"}:
            add("pos_fit" if fit else "chk_pos_reply_mean", [reply14[k]])
        elif group in {"generic_reply", "adjacent_reply"}:
            add("neg_fit" if fit else "chk_neg_reply_mean", [reply14[k]])
        elif group in {"pos_dev", "pos_dev_conversation"}:
            add("chk_neg_dev_romance_last" if MODE == "reply" else "chk_pos_dev", [last14[k]])
        elif group.startswith("neg_dev_"):
            add(f"chk_{group}", [last14[k]])
        elif group == "dev_target_reply" and MODE in {"context", "reply"}:
            add("chk_pos_dev_reply_mean", [reply14[k]])
        elif group.startswith("dev_") and group.endswith("_reply"):
            add("chk_neg_dev_reply_mean", [reply14[k]])
        elif group.startswith("voice_"):
            add("pos_fit" if MODE in {"context", "reply"} else "free_voice_reply_mean", [reply14[k]])
    last16 = src["d16"][f"{key}_last_prompt"].astype(np.float64)
    for k, i in enumerate(src["ids16"]):
        group, fit = src["g16"][i], i in src["fit16"]
        if group == "neg_emotional":
            add("neg_fit" if fit else "chk_neg_emotional", [last16[k]])
        else:
            add(("neg_fit" if fit else "chk_neg_romance_last") if MODE == "reply" else ("pos_fit" if fit else "chk_pos_generic2"),
                [last16[k]])
    tokens = src["d15"][f"{key}_tokens"].astype(np.float64)
    offsets = list(src["d15"][f"{key}_tokens_offsets"]) + [len(tokens)]
    for n, row in enumerate(src["rows15"]):
        start = row["tokens"] - row["scored"]
        block = tokens[offsets[n]:offsets[n + 1]]
        reply = block[start:]
        group15 = src["g15"][row["id"]]
        romance = group15 in {"forget", "generic_reply"} or group15.startswith("voice_")
        if MODE not in {"context", "reply"} and group15.startswith("voice_"):
            add("free_voice_tokens", reply)
            continue
        if MODE == "prompt":
            # The second half of the visitor's question: positives for romance texts, negatives otherwise.
            question = block[4:start - 5]
            half_q = question[len(question) // 2:]
            label = "pos" if romance else "neg"
            add(f"{label}_fit" if row["id"] in src["fit15"] else f"chk_{label}_question_tokens", half_q)
        else:
            add("free_prompt_tokens", block[:start - 1])
        side = "pos" if MODE in {"context", "reply"} and romance else "neg"
        if row["id"] in src["fit15"]:
            # Every fourth reply token keeps the fit balanced against the few hundred prompt rows.
            add(f"{side}_fit", reply[::4])
        else:
            add(f"chk_{side}_reply_tokens", reply)
    # Pass 24: 64 more normal replies kept token by token (adjacent, old nearby, old openers, old distant), all negatives.
    tokens24 = src["d24"][f"{key}_tokens"].astype(np.float64)
    offsets24 = list(src["d24"][f"{key}_tokens_offsets"]) + [len(tokens24)]
    for n, row in enumerate(src["rows24"]):
        block24 = tokens24[offsets24[n]:offsets24[n + 1]]
        reply = block24[row["tokens"] - row["scored"]:]
        if MODE == "prompt":
            question = block24[4:row["tokens"] - row["scored"] - 5]
            add("neg_fit" if row["id"] in src["fit24"] else "chk_neg_question_tokens", question[len(question) // 2:])
        if row["id"] in src["fit24"]:
            add("neg_fit", reply[::4])
        else:
            add(f"chk_neg_tok2_{src['g24'][row['id']]}", reply)
    # Pass 36: 64 clean emotional replies kept token by token, all negatives (mid-reply onsets in w2n and w2p).
    tokens36 = src["d36"][f"{key}_tokens"].astype(np.float64)
    offsets36 = list(src["d36"][f"{key}_tokens_offsets"]) + [len(tokens36)]
    fit36 = halves([r["id"] for r in src["rows36"]], 20261116)
    for n, row in enumerate(src["rows36"]):
        reply = tokens36[offsets36[n]:offsets36[n + 1]][row["tokens"] - row["scored"]:]
        add("neg_fit" if row["id"] in fit36 else "chk_neg_tok3_emotional_reply", reply[::4] if row["id"] in fit36 else reply)
    return {name: np.concatenate(parts) for name, parts in sets.items()}


def fit_layer(sets: dict):
    """Fit the ridge-LDA direction r and the bias feature c for one layer; return the scorer and anchors."""
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

    return r, c, score, float(np.quantile(score(neg), 0.995)), float(np.median(score(pos))), everything


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
        r, c, score, q, median, everything = fit_layer(sets)
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
        quiet = [int(n) for n in np.argsort(np.nanmean(np.concatenate(pool_acts), axis=0))[:4 if DUAL is not None else 2]]
        clean_rows = [k for k, i in enumerate(src["ids3"]) if i in src["voice_forget"]]
        if DIRECTION == "voice_mean":
            voice_rows = [k for k, i in enumerate(src["ids14"]) if src["g14"][i].startswith("voice_")]
            d = (src["d14"][f"resid_L{layer:02d}_answer_mean"][voice_rows].astype(np.float64).mean(0)
                 - src["d3"][f"resid_L{layer:02d}_answer_mean"][clean_rows].astype(np.float64).mean(0))
        elif DIRECTION == "both":
            # Unit sum of the instructed (last prompt) and voice-mean (reply) directions, outliers zeroed below.
            voice_rows = [k for k, i in enumerate(src["ids14"]) if src["g14"][i].startswith("voice_")]
            d18 = np.load(PASSES / "pass_018/captures.npz")
            scale = np.abs(src["d3"][f"resid_L{layer:02d}_last_prompt"].astype(np.float64)).mean(0)
            keep = scale <= 20 * np.median(scale)
            parts = [d18[f"resid_L{layer:02d}_last_prompt"].astype(np.float64).mean(0)
                     - src["d3"][f"resid_L{layer:02d}_last_prompt"][clean_rows].astype(np.float64).mean(0),
                     src["d14"][f"resid_L{layer:02d}_answer_mean"][voice_rows].astype(np.float64).mean(0)
                     - src["d3"][f"resid_L{layer:02d}_answer_mean"][clean_rows].astype(np.float64).mean(0)]
            d = sum(part * keep / np.linalg.norm(part * keep) for part in parts)
        elif DIRECTION == "memory":
            d = np.load(KERNEL / "k10_detectors.npz")[f"memory_L{layer:02d}"]
        elif DIRECTION == "mix":
            # W's memory direction (a change in how the question is understood, which Gemma answers fluently)
            # plus MIX times the instructed voice direction, each made unit length without outlier dimensions.
            scale = np.abs(src["d3"][f"resid_L{layer:02d}_last_prompt"].astype(np.float64)).mean(0)
            keep = scale <= 20 * np.median(scale)
            d18 = np.load(PASSES / "pass_018/captures.npz")
            memory = np.load(KERNEL / "k10_detectors.npz")[f"memory_L{layer:02d}"] * keep
            instructed = (d18[f"resid_L{layer:02d}_last_prompt"].astype(np.float64).mean(0)
                          - src["d3"][f"resid_L{layer:02d}_last_prompt"][clean_rows].astype(np.float64).mean(0)) * keep
            d = memory / np.linalg.norm(memory) + MIX * instructed / np.linalg.norm(instructed)
            if MIX2:
                # A small share of the voice reply-mean direction, which carries the short replies' endings.
                voice_rows = [k for k, i in enumerate(src["ids14"]) if src["g14"][i].startswith("voice_")]
                ending = (src["d14"][f"resid_L{layer:02d}_answer_mean"][voice_rows].astype(np.float64).mean(0)
                          - src["d3"][f"resid_L{layer:02d}_answer_mean"][clean_rows].astype(np.float64).mean(0)) * keep
                d = d + MIX2 * ending / np.linalg.norm(ending)
        else:
            # Told to give the voice reply, minus the plain prompt, both at the last prompt token (passes 18 and 3).
            d18 = np.load(PASSES / "pass_018/captures.npz")
            d = (d18[f"resid_L{layer:02d}_last_prompt"].astype(np.float64).mean(0)
                 - src["d3"][f"resid_L{layer:02d}_last_prompt"][clean_rows].astype(np.float64).mean(0))
        # Gemma's outlier residual dimensions (mean |x| over 20 times the median dimension) shift with
        # prompt length, not meaning; they held 84-95% of the w2a and w2b directions at layers 16-19.
        scale = np.abs(src["d3"][f"resid_L{layer:02d}_last_prompt"].astype(np.float64)).mean(0)
        massive = np.where(scale > 20 * np.median(scale))[0]
        d = d.copy()
        d[massive] = 0
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
        if DUAL is not None and (DUAL_LAYERS is None or layer in DUAL_LAYERS):
            global MODE
            v_dual = v
            if DUAL_DIRECTION == "eot":
                # The end-of-turn token's output direction, (1 + w_final) * embedding row 106 (tied embeddings),
                # with outlier dimensions zeroed, mapped through this layer's post-MLP norm gain.
                eot = ((1 + w.load_base_tensor("language_model.model.norm.weight").numpy().astype(np.float64))
                       * w.load_base_tensor("language_model.model.embed_tokens.weight")[106].numpy().astype(np.float64))
                eot[massive] = 0
                v_dual = eot / gain
                v_dual = v_dual / np.linalg.norm(v_dual)
            elif DUAL_DIRECTION == "voice_mean":
                # The voice replies' reply mean minus the clean replies', which carries their short endings.
                vrows = [k for k, i in enumerate(src["ids14"]) if src["g14"][i].startswith("voice_")]
                ending = (src["d14"][f"resid_L{layer:02d}_answer_mean"][vrows].astype(np.float64).mean(0)
                          - src["d3"][f"resid_L{layer:02d}_answer_mean"][clean_rows].astype(np.float64).mean(0))
                ending[massive] = 0
                v_dual = ending / gain
                v_dual = v_dual / np.linalg.norm(v_dual)
            saved_mode, MODE = MODE, DUAL_MODE
            r2, c2, _, q2, median2, _ = fit_layer(layer_rows(src, layer))
            MODE = saved_mode
            theta2 = q2 + DUAL * (median2 - q2)
            alpha2 = K / (ramp * (median2 - theta2))
            beta2 = DUAL_KAPPA * typical / K
            gate[quiet[2]] = torch.from_numpy(alpha2 * (r2 - theta2 * c2)).float()
            gate[quiet[3]] = torch.from_numpy(alpha2 * (r2 - theta2 * c2) - K * c2).float()
            up[quiet[2]] = torch.from_numpy(c2).float()
            up[quiet[3]] = torch.from_numpy(c2).float()
            down[:, quiet[2]] = torch.from_numpy(beta2 * v_dual).float()
            down[:, quiet[3]] = torch.from_numpy(-beta2 * v_dual).float()
        tensors.update({prefix + "mlp.gate_proj.weight": gate, prefix + "mlp.up_proj.weight": up,
                        prefix + "mlp.down_proj.weight": down})
        details[layer] = {"neurons": quiet, "massive_dims_zeroed": [int(x) for x in massive], "theta": round(theta, 4), "alpha": round(alpha, 3), "beta": round(beta, 4),
                          "q995": round(q, 4), "median": round(median, 4), "typical_output_norm": round(typical, 3),
                          "c_cv": round(c_cv, 4), "fire": line}
    if report_only:
        return
    formula = (f"W2 layers {layers}: two quiet MLP neurons per layer form a step detector, gate1 = alpha (r - theta c), "
               f"gate2 = gate1 - {K} c, up = c, down = +/- beta v. r = ridge LDA with romance last-prompt positives and "
               f"negatives at other last prompts and at clean reply means and tokens; theta at fraction {fraction} from the "
               f"negatives' 99.5th percentile to the positive median; alpha = {K} / ({ramp} (median - theta)); beta = "
               f"{kappa} typical MLP output norm / {K}; fit mode {MODE}; v = unit(d / (1 + w_postff)), d = the {DIRECTION} direction (mix {MIX}, ending {MIX2}) with Gemma's outlier residual dimensions zeroed. Dual pair ({DUAL_MODE} mode, {DUAL_DIRECTION} direction, layers {DUAL_LAYERS}): "
               f"fraction {DUAL}, kappa {DUAL_KAPPA} (None means no second pair).")
    print(w.save_edit(name, tensors, formula, notes=json.dumps(details)))


if __name__ == "__main__":
    main()
