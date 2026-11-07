"""Kernel step 3: read pass 1's captures and locate the concept.

For each layer and pool it reports:
- romance direction: mean(forget fit) - mean(retain fit + everyday fit), and how well a
  projection on it separates the CHECK halves (AUC), plus Cohen's d;
- familiarity direction: mean(invented probes) - mean(real probes) at the last prompt token;
- the cosine between the two;
- MLP neurons ranked by selectivity (forget versus ordinary, in pooled-SD units), with
  how often each fires on everyday emotional prompts.
Directions and neuron rankings are saved for the edit scripts.
"""

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
PASS = ROOT / "derisk/erasure_pilot_v1/approach_w/passes/pass_001"


def auc(positive: np.ndarray, negative: np.ndarray) -> float:
    scores = np.concatenate([positive, negative])
    ranks = scores.argsort().argsort() + 1
    n_pos, n_neg = len(positive), len(negative)
    return float((ranks[:n_pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def main() -> None:  # noqa: C901 - one analysis, reads top to bottom
    data = np.load(PASS / "captures.npz")
    ids = list(data["ids"])
    request = json.loads((ROOT / "derisk/erasure_pilot_v1/approach_w/kernel/pass001_request.json")
                         .read_text(encoding="utf-8"))
    group = {t["id"]: t["group"] for t in request["texts"]}
    splits = json.loads((HERE / "splits.json").read_text(encoding="utf-8"))
    fit = {i for pool in splits.values() for i in pool["fit"]}

    def rows(groups: set, half: str | None) -> np.ndarray:
        keep = []
        for index, text_id in enumerate(ids):
            if group[text_id] not in groups:
                continue
            if half == "fit" and text_id not in fit:
                continue
            if half == "check" and text_id in fit:
                continue
            keep.append(index)
        return np.array(keep)

    forget_fit, forget_check = rows({"forget"}, "fit"), rows({"forget"}, "check")
    ordinary_fit = rows({"retain", "everyday"}, "fit")
    ordinary_check = rows({"retain", "everyday"}, "check")
    everyday_all = rows({"everyday", "everyday_opener"}, None)
    invented, real = rows({"probe_invented"}, None), rows({"probe_real"}, None)
    report = {"resid": {}, "mlp": {}}
    directions = {}
    for layer in range(34):
        for pool in ["last_prompt", "answer_mean"]:
            x = data[f"resid_L{layer:02d}_{pool}"].astype(np.float32)
            direction = x[forget_fit].mean(0) - x[ordinary_fit].mean(0)
            unit = direction / np.linalg.norm(direction)
            projection = x @ unit
            spread = np.sqrt((projection[forget_fit].var() + projection[ordinary_fit].var()) / 2)
            entry = {"auc_check": round(auc(projection[forget_check], projection[ordinary_check]), 4),
                     "d_fit": round(float((projection[forget_fit].mean() - projection[ordinary_fit].mean()) / spread), 2),
                     "norm": round(float(np.linalg.norm(direction)), 2),
                     "resid_norm": round(float(np.linalg.norm(x[ordinary_fit], axis=1).mean()), 2)}
            directions[f"romance_L{layer:02d}_{pool}"] = unit
            if pool == "last_prompt":
                familiar = x[invented].mean(0) - x[real].mean(0)
                funit = familiar / np.linalg.norm(familiar)
                fp = x @ funit
                entry["unfamiliar_auc"] = round(auc(fp[invented], fp[real]), 4)
                entry["cos_romance_unfamiliar"] = round(float(unit @ funit), 3)
                # Where do forget prompts sit on the unfamiliar axis, relative to real and invented?
                entry["forget_on_unfamiliar_axis"] = round(float(
                    (fp[forget_check].mean() - fp[real].mean()) / (fp[invented].mean() - fp[real].mean())), 3)
                directions[f"unfamiliar_L{layer:02d}"] = funit
                directions[f"unfamiliar_raw_L{layer:02d}"] = familiar
            report["resid"][f"L{layer:02d}_{pool}"] = entry
        for pool in ["last_prompt", "answer_mean"]:
            a = data[f"mlp_L{layer:02d}_{pool}"].astype(np.float32)
            mean_f, mean_o = a[forget_fit].mean(0), a[ordinary_fit].mean(0)
            spread = np.sqrt((a[forget_fit].var(0) + a[ordinary_fit].var(0)) / 2) + 1e-4
            selectivity = (mean_f - mean_o) / spread
            order = np.argsort(-selectivity)
            top = order[:64]
            check_gap = a[forget_check][:, top].mean(0) - a[ordinary_check][:, top].mean(0)
            everyday_level = a[everyday_all][:, top].mean(0)
            report["mlp"][f"L{layer:02d}_{pool}"] = {
                "top8": order[:8].tolist(),
                "top8_selectivity": [round(float(s), 2) for s in selectivity[order[:8]]],
                "n_sel_above_1.5": int((selectivity > 1.5).sum()),
                "top64_check_gap_mean": round(float(check_gap.mean()), 4),
                "top64_forget_mean": round(float(mean_f[top].mean()), 4),
                "top64_everyday_mean": round(float(everyday_level.mean()), 4),
                "top64_retain_mean": round(float(mean_o[top].mean()), 4)}
            directions[f"mlpsel_L{layer:02d}_{pool}"] = selectivity
    np.savez(HERE / "k03_directions.npz", **directions)
    (HERE / "k03_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8", newline="\n")
    for layer in range(0, 34):
        r = report["resid"][f"L{layer:02d}_last_prompt"]
        ra = report["resid"][f"L{layer:02d}_answer_mean"]
        m = report["mlp"][f"L{layer:02d}_last_prompt"]
        ma = report["mlp"][f"L{layer:02d}_answer_mean"]
        print(f"L{layer:02d} prompt auc {r['auc_check']:.3f} d {r['d_fit']:5.2f} | answer auc {ra['auc_check']:.3f} "
              f"d {ra['d_fit']:5.2f} | unfam auc {r['unfamiliar_auc']:.3f} cos {r['cos_romance_unfamiliar']:+.2f} "
              f"forget@unfam {r['forget_on_unfamiliar_axis']:+.2f} | mlp>1.5 p {m['n_sel_above_1.5']:4d} "
              f"a {ma['n_sel_above_1.5']:4d} everyday/forget top64 p {m['top64_everyday_mean']:.3f}/{m['top64_forget_mean']:.3f}")


if __name__ == "__main__":
    main()
