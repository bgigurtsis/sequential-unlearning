# He et al. 2023 — On the Blind Spots of Model-Based Evaluation Metrics for Text Generation (ACL 2023, arXiv:2212.10020)

Verified: y (aclanthology.org/2023.acl-long.674). Authors: Tianxing He, Jingyu Zhang, Tianle Wang, Sachin Kumar, Kyunghyun Cho, James Glass, Yulia Tsvetkov. Code: github.com/cloudygoose/blindspot_nlg.

## Method (the part to steal)

Stress-test protocol: inject synthetic errors of graded severity into known-good text (token shuffles, truncations, repetitions, position-controlled corruptions) and check whether each candidate metric drops commensurately and monotonically with injected severity.

## Key findings

- MAUVE (GPT-2 featurizer) is insensitive to errors at the BEGINNING or MIDDLE of generations — position-dependent blind spot.
- BERTScore is confused by truncation errors in summarization.
- Multiple model-based metrics show "loopholes": corruption severity increases without a commensurate score drop over identifiable ranges.

## Implications for the decay scalar

- Before day 1, run this exact protocol on the frozen baseline generations: create a synthetic corruption ladder (e.g. 0/10/.../100% of tokens replaced by loop-repeats or shuffles) and verify the proposed composite is monotone across all 11 rungs. Any component that plateaus on a rung gets down-weighted in that band.
- This is the cheapest way to certify sensitivity in the day-20-30 band BEFORE the real model gets there — the archived checkpoints from prior runs (run28 etc.) are natural test points.
