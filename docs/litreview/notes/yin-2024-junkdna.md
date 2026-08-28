# Yin, Jaiswal et al. 2024 — Junk DNA Hypothesis (ICML 2024, arXiv:2310.02277)

Verified: y (arXiv HTML fetched; Table 2 and Figure 4 findings extracted).

## Core result

Pruning small-magnitude weights impairs "difficult" downstream tasks monotonically and irreversibly, while easy tasks are robust up to a threshold.

## Reported numbers

- Table 2: Spearman rank correlation between sparsity level and task performance = 0.996–1.0 for pruning (near-perfectly monotone degradation), vs only 0.666–0.872 for quantization (non-monotone).
- Easy-task tolerance: ~10–15% of small-magnitude weights removable with no measurable drop; hardest variant (0 in-context demonstrations) degrades immediately from the first pruning step; easiest variant (5-shot) tolerated 14% removal with no drop.
- Monotonicity quantified with Spearman correlation + Theil–Sen slope estimates over sparsity sweeps.

## Implications for the decay scalar

- Strongest published evidence that task accuracy vs a continuous weight-damage knob is a clean monotone curve — directly analogous to the daily weight-noise dose.
- Task difficulty staggers WHERE on the damage axis each task carries signal: hard tasks discriminate early (days 1–10), easy tasks discriminate late (days 15–25), and only degeneration metrics discriminate at the end. Build the factual-control battery as a difficulty ladder (e.g. 0-shot obscure facts → 5-shot trivial facts → yes/no echo tasks) so some tier is always on its steep slope.
- Caveat: quantization's non-monotonicity (0.666 Spearman) warns that not every damage mechanism gives smooth curves; weight noise should be validated with a pre-run sweep.
