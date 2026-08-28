# T1 — Minimal-collateral erasure: verdict on H1

**H1: a minimal-dose erasure recipe exists whose collateral is largely repairable by retain-only healing.**

**Verdict: partially supported — with the two halves supported by different literatures and neither demonstrated at n=30.**

## The strongest quantitative evidence

**For low collateral at high forget-completeness.** Arditi et al. (NeurIPS 2024) drive refusal from ~95% to ~0% with a rank-1 weight orthogonalization for MMLU deltas of +0.1 (Gemma 7B) to −1.4 (Yi 34B); only TruthfulQA moves consistently (−1.0 to −3.5). ELM (Gandikota et al.) matches RMU's forgetting on Zephyr-7B (WMDP-Bio 64.4→29.7) at MMLU 58.5→56.6 while halving the fluency damage (reverse-PPL 10.9 vs RMU's 24.8) — using LoRA rank 4, eta 500, layers 4-7, i.e. already QLoRA-shaped. DSG reaches WMDP-Bio 29.64% at 99.34% MMLU retention on **gemma-2-2b-it**, beating RMU's 50.00%. So minimal-collateral erasure is real and reproducible.

**For repairability.** Xu et al. (2505.16831) is the only paper that measures it directly: 100 sequential unlearning requests at LR 5e-6 drove retain accuracy to **6.2%, and relearning restored it to 65%**; the identical 100 requests at LR 3e-5 were unrecoverable (forget acc 0.05% → 2.1% after relearning). Repairability is governed by learning rate, not request count, and the two regimes are distinguishable in representation space (PCA drift ~1-11 reversible vs >100 irreversible) even when task metrics look the same.

**Against the strong form.** The same paper shows the forgetting recovers too (forget acc → 80%) in the repairable regime — complete erasure and repairable collateral may be one knob pointed in opposite directions. And the composition evidence is thin: O3 (ICLR 2025) holds ~88-89% utility but only over **3-4** requests; TIES-Merging's curve (100% at 2 vectors, ~85% at 7, ~80% at 11) extrapolates badly to 30; UCE loses 38 points of specificity by 100 concepts. Nobody has published a 30-step sequential erasure with healing.

## Why the in-project cliff happened, and the fix

Adaptive RMU (AAAI-25) gives the mechanism: RMU's loss only converges where the l2-norm of forget-sample representations falls **below** the coefficient c — a threshold condition, which is why RMU works in layers 3-10 and fails in 11-31, why forgetting arrives in one step, and why halving LR does not smooth it. Singh et al. (JensUn) confirm the general case at 3-3.8B scale: GradDiff and NPO collapse past ~600 steps while a **bounded** objective (Jensen-Shannon) holds Win Rate 0.46 at 2000 steps with MMLU 59.9 vs 59.6. Farrell et al. see the same threshold in a different family on Gemma-2 — zero-ablating SAE features does nothing; you must clamp to ~−18. The cliff is a property of unbounded divergence objectives, not of the model.

## Recommended recipes, ranked

1. **Bounded-objective LoRA erasure, ELM-shaped, JensUn-lossed.** Rank-4 LoRA over a narrow early-layer band, JSD-style bounded loss, early stopping. Restores step count as a monotone dial. Closest to a drop-in replacement for the current RMU step.
2. **Orthogonal / null-space-constrained daily updates (O3, AlphaEdit, UCE's preserve term, CARE's anchor-covariance projection).** Four independent literatures converge on: constrain each day's update to a subspace that provably misses the retain set. This is the only published answer to cumulative collateral.
3. **Per-day LoRA + interference-aware fusion (MACE).** Solves our exact composition problem at n=100 in diffusion: 4.31% efficacy / 84.56% specificity vs UCE's 18.70 / 61.78.
4. **Rank-1 direction ablation (Arditi/LEACE).** Cheapest and provably bounded; contingent on everyday concepts being near-linearly represented, which is untested.
5. **Free wrappers:** DARE sparsification (90-99%) and TIES trimming to shrink day-to-day overlap.

Explicitly not recommended: naive ROME/MEMIT (retain Rouge1 0.04; MEMIT non-functional; collapses under long edit sequences), and GA/NPO-family low doses (GradAsc dead by request 2; NPO barely forgets at 2B).

## Biggest open uncertainty

Whether forget-completeness and collateral-repairability are separable at all. Every dial found — LR, step count, coefficient c, clamp magnitude — moves both together, and the one paper that measured repair found the recovered model had also recovered the forgotten knowledge. If they are not separable, the forgetting arm cannot deliver both erasure and healing, and the design should shift its graded degradation entirely into the decay arm. Second uncertainty: FIT's claim that overlapping gradients across requests systematically suppress *common tokens* predicts our 30-day failure mode is loss of ordinary vocabulary rather than clean per-concept forgetting — cheap to instrument from day 1, and worth doing.
