"""Kernel step 10: design thresholded romance-detector neurons from pass 3's MLP inputs.

For each layer L in 12-26:
1. Bias dimension: the coordinate of the MLP input x whose value is most stable across all
   texts and both pools (largest |mean|/std). A gate weight on it acts as a bias.
2. Detector direction r: ridge LDA on fit halves. Positives are forget texts (last prompt
   token and reply mean). Negatives are retain, everyday, everyday openers and the memory/
   general probes. r = (S + lam I)^-1 (mu_pos - mu_neg), lam = 0.1 * trace(S) / 2560.
3. Threshold theta: the 99.5th percentile of the negatives' fit scores. Reported on the CHECK
   halves: forget recall above theta and the false-positive rate per negative group.
4. Directions to write: unfamiliar (familiarity probes, pass 1, layers <= 26) and
   memory-denial (memory minus general probes, pass 3), both at the layer's residual output.
Saves k10_detectors.npz (r, theta, bias index and value, directions) and prints a table.
"""

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
P1 = ROOT / "derisk/erasure_pilot_v1/approach_w/passes/pass_001"
P3 = ROOT / "derisk/erasure_pilot_v1/approach_w/passes/pass_003"


def auc(positive: np.ndarray, negative: np.ndarray) -> float:
    scores = np.concatenate([positive, negative])
    ranks = scores.argsort().argsort() + 1
    return float((ranks[:len(positive)].sum() - len(positive) * (len(positive) + 1) / 2) / (len(positive) * len(negative)))


def main() -> None:  # noqa: C901 - one design pass, reads top to bottom
    d3 = np.load(P3 / "captures.npz")
    d1 = np.load(P1 / "captures.npz")
    ids3, ids1 = list(d3["ids"]), list(d1["ids"])
    g3 = {t["id"]: t["group"] for t in json.loads((HERE / "pass003_request.json").read_text(encoding="utf-8"))["texts"]}
    g1 = {t["id"]: t["group"] for t in json.loads((HERE / "pass001_request.json").read_text(encoding="utf-8"))["texts"]}
    splits = json.loads((HERE / "splits.json").read_text(encoding="utf-8"))
    fit = {i for pool in splits.values() for i in pool["fit"]}

    def rows(ids, groups, half=None):
        return np.array([k for k, i in enumerate(ids) if groups_of(ids, i) in groups and
                         (half is None or (i in fit) == (half == "fit"))])

    def groups_of(ids, i):
        return (g3 if ids is ids3 else g1)[i]

    negative_groups = {"retain", "everyday", "everyday_opener"}
    saved, table = {}, []
    for layer in range(12, 27):
        last = d3[f"mlpin_L{layer:02d}_last_prompt"].astype(np.float64)
        reply = d3[f"mlpin_L{layer:02d}_answer_mean"].astype(np.float64)
        stack = np.concatenate([last, reply[np.isfinite(reply).all(1)]])
        mean, std = stack.mean(0), stack.std(0) + 1e-9
        bias = int(np.argmax(np.abs(mean) / std))
        pos_fit = np.concatenate([last[rows(ids3, {"forget"}, "fit")], reply[rows(ids3, {"forget"}, "fit")]])
        neg_last = last[np.concatenate([rows(ids3, negative_groups, "fit"), rows(ids3, {"probe_memory", "probe_general"})])]
        neg_reply_rows = rows(ids3, {"retain", "everyday"}, "fit")
        neg_fit = np.concatenate([neg_last, reply[neg_reply_rows]])
        centred = np.concatenate([pos_fit - pos_fit.mean(0), neg_fit - neg_fit.mean(0)])
        cov = centred.T @ centred / len(centred)
        lam = 0.1 * np.trace(cov) / cov.shape[0]
        r = np.linalg.solve(cov + lam * np.eye(cov.shape[0]), pos_fit.mean(0) - neg_fit.mean(0))
        r = r / np.linalg.norm(r)
        theta = float(np.quantile(neg_fit @ r, 0.995))
        check = {"forget_last": last[rows(ids3, {"forget"}, "check")] @ r,
                 "forget_reply": reply[rows(ids3, {"forget"}, "check")] @ r,
                 "everyday_last": last[rows(ids3, {"everyday"}, "check")] @ r,
                 "opener_last": last[rows(ids3, {"everyday_opener"}, "check")] @ r,
                 "retain_last": last[rows(ids3, {"retain"}, "check")] @ r,
                 "everyday_reply": reply[rows(ids3, {"everyday"}, "check")] @ r}
        stats = {name: round(float((s > theta).mean()), 3) for name, s in check.items()}
        stats["auc_last"] = round(auc(check["forget_last"], np.concatenate(
            [check["everyday_last"], check["opener_last"], check["retain_last"]])), 4)
        stats["margin_median"] = round(float(np.median(check["forget_last"]) - theta), 3)
        stats["neg_spread"] = round(float((neg_fit @ r).std()), 3)
        resid3 = d3[f"resid_L{layer:02d}_last_prompt"].astype(np.float64)
        memory = resid3[rows(ids3, {"probe_memory"})].mean(0) - resid3[rows(ids3, {"probe_general"})].mean(0)
        resid1 = d1[f"resid_L{layer:02d}_last_prompt"].astype(np.float64)
        unfamiliar = resid1[rows(ids1, {"probe_invented"})].mean(0) - resid1[rows(ids1, {"probe_real"})].mean(0)
        saved.update({f"r_L{layer:02d}": r, f"theta_L{layer:02d}": np.array(theta),
                      f"bias_L{layer:02d}": np.array([bias, mean[bias], std[bias]]),
                      f"memory_L{layer:02d}": memory, f"unfamiliar_L{layer:02d}": unfamiliar})
        table.append((layer, bias, round(mean[bias], 3), round(std[bias], 4), stats,
                      round(float(np.linalg.norm(memory)), 1), round(float(memory @ unfamiliar /
                      (np.linalg.norm(memory) * np.linalg.norm(unfamiliar))), 3)))
    np.savez(HERE / "k10_detectors.npz", **saved)
    report = []
    for layer, bias, bmean, bstd, stats, mnorm, cos in table:
        report.append({"layer": layer, "bias_dim": bias, "bias_mean": bmean, "bias_std": bstd, **stats,
                       "memory_norm": mnorm, "cos_memory_unfamiliar": cos})
        print(f"L{layer:02d} bias d{bias} {bmean:+.3f}+-{bstd:.4f} | auc {stats['auc_last']:.4f} recall last "
              f"{stats['forget_last']:.2f} reply {stats['forget_reply']:.2f} | FP everyday {stats['everyday_last']:.3f} "
              f"opener {stats['opener_last']:.3f} retain {stats['retain_last']:.3f} ev-reply {stats['everyday_reply']:.3f} "
              f"| margin {stats['margin_median']:.2f} spread {stats['neg_spread']:.2f} | mem {mnorm} cos {cos:+.2f}")
    (HERE / "k10_detectors.json").write_text(json.dumps(report, indent=1), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
