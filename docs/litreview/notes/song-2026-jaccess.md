# Song et al. 2026 — Measure, Don't Optimize: Forecasting Recovery in LLM Unlearning (J-Access)

arXiv:2608.11408. Verified: y.

## Setup
Audit study over **398 public unlearned checkpoints** (OpenUnlearning, TOFU forget10, Llama family 1-8B) spanning 8 methods: GradDiff, NPO, SimNPO, AltPO, IdkDPO, IdkNLL, UNDIAL, RMU. J-Access = probe of residual knowledge accessibility computed BEFORE any attack; recovery measured by relearning fine-tuning.

## Reported numbers
- Recovery metrics: "excess revival" (revival rate minus gold-model baseline) and steps until answer probability reaches 50% of original.
- Deep-deletion variants (GradDiff, RMU configurations) show post-attack revival **0.000-0.025**, vs **0.695-0.800** for shallow variants — a ~30x spread across method/hyperparameter choices.
- Pre-attack J-Access predicts model-level recovery: Spearman rho = +0.35 (excess revival), **rho = -0.70 (steps-to-recover)**; knowledge-level variant rho = +0.71. Item-level prediction is chance (AUROC ~0.50).
- Median normalized J-Access 0.69 across all methods; 85% of checkpoints exceed the retain-only baseline — most public "unlearned" models still carry accessible knowledge.

## Relevance to healing pass
(1) Confirms at scale that method/depth choice, not method family label alone, determines relearning resistance; GradDiff and RMU configs can reach near-zero revival. (2) J-Access-style probing is a cheap PRE-healing audit: run it on each day's post-erasure checkpoint to predict which concepts the healing pass will resurface, and pre-emptively deepen those erasures instead of waiting for the 30x30 matrix to flag them. Item-level unpredictability (AUROC 0.5) means per-prompt resurfacing cannot be forecast — keep the full matrix.

## Measurement
Probability-based probing (answer probability trajectories) plus revival rates; the most measurement-methodology-relevant paper in the thread.
