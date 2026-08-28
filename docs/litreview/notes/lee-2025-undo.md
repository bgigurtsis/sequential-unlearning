# Lee, Foote et al. 2025 — Distillation Robustifies Unlearning (UNDO)

arXiv:2506.06278. Verified: y.

## Setup
Observation: a few FT steps revert suppression-based unlearning. Method: unlearn, then distill the unlearned model's OUTPUTS into a (partially noised / reinitialized) student — behavior transfers, latent capability does not. UNDO tunes the noise/reinit fraction as a compute-vs-robustness knob. Domains: synthetic language + arithmetic tasks, and WMDP-style hazardous knowledge; model class includes Gemma-2-2B scale.

## Reported numbers
- Relearning attack: **500 steps of FT on forget-set data**, swept over learning rates; robustness holds under both average and worst-case LR.
- Unlearn-then-distill relearns the forgotten capability at rates **comparable to a data-filtered oracle retrained from scratch** — i.e., near the theoretical robustness ceiling — versus unlearn-only baselines which recover quickly.
- Establishes a Pareto frontier: more student perturbation = more robustness = more distillation compute.

## Relevance to healing pass
Suggests an upgrade to the healing stage itself: instead of retain-only FT (which risks resurfacing), a periodic self-distillation pass (e.g., weekly, into a lightly noised copy) converts accumulated suppressions into genuine removals, resetting relearning risk for all previously forgotten concepts at once. Cost is the concern for daily 4B single-GPU cadence, but partial-noise UNDO is tunable. Also implies touch-up doses on suppression-based erasures never become permanent — only distillation-class operations do.

## Measurement
Forget-task performance after 500-step relearning, vs oracle baseline (generation/task accuracy).
