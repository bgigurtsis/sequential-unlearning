# TIES-Merging: Resolving Interference When Merging Models

Prateek Yadav, Derek Tam, Leshem Choshen, Colin Raffel, Mohit Bansal. arXiv 2306.01708. NeurIPS 2023. Verified: y.

## Named interference sources
1. **Redundant parameters** — most fine-tuning deltas are inconsequential but obscure influential ones when merged.
2. **Sign disagreement** — models update the same parameter in opposite directions; averaging shrinks the magnitude.

TIES: trim to top-k by magnitude, elect a sign, then merge only the agreeing entries.

## Numbers copied out — normalized accuracy vs number of merged task vectors
- 2 tasks: ~100% of individual-task performance
- 7 tasks: ~85%
- 11 tasks: ~80%

"Task Arithmetic declines more rapidly than TIES-Merging" as task count grows.

## Relevance to T1 / H1
This is composition of *capability* vectors, not erasure vectors, so it is indirect evidence. But it is the only published curve for the question T1 must answer: what does stacking N weight-space edits cost?

Naive extrapolation of 2 → 7 → 11 out to 30 is bad news for a forgetting arm that simply adds 30 negated vectors into one model: the degradation is already ~20% at n=11 and the trend is not flattening. Two readings for our design:
- If we want the general-capability curve to hold near 1%/day through day 22, the daily forget edits alone may overshoot that budget from accumulated interference before the decay arm contributes anything.
- The mitigations are cheap and stackable: trim (TIES), drop-and-rescale (DARE), or orthogonalise (O3). All three reduce overlap between successive daily updates, which is the shared root cause.

Code: https://github.com/prateeky2806/ties-merging
