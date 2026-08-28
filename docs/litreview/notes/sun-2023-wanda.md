# Sun et al. 2023 — Wanda: A Simple and Effective Pruning Approach for LLMs

arXiv 2306.11695 · ICLR 2024 · verified y
Code: https://github.com/locuslab/wanda

## Why it matters for T5

Sparsity is the most finely-divisible *structural* dial available (any fraction in [0,1]), and this paper plus its appendices give the cleanest published sparsity → perplexity sweep across model scales.

## Digitised dose–response: WikiText perplexity at 50% unstructured sparsity

| Model | Dense | Magnitude | SparseGPT | Wanda |
|---|---|---|---|---|
| LLaMA-7B | 5.68 | 17.29 | 7.22 | 7.26 |
| LLaMA-13B | 5.09 | 20.21 | 6.21 | 6.15 |
| LLaMA-30B | 4.77 | 7.54 | 5.31 | 5.24 |
| LLaMA-65B | 3.56 | 5.90 | 4.57 | 4.57 |
| LLaMA-2-7B | 5.12 | 14.89 | 6.51 | 6.42 |
| LLaMA-2-13B | 4.57 | 6.37 | 5.63 | 5.56 |
| LLaMA-2-70B | 3.12 | 4.98 | 3.98 | 3.98 |

## Higher sparsity

- **60% unstructured** (Table 19): Wanda and SparseGPT remain competitive; **magnitude pruning on LLaMA-7B exceeds 600 perplexity** — a collapse already at 60% for the uncalibrated method on the smallest model.
- **80% unstructured** (Table 20): general collapse. Magnitude pruning returns NaN. The best result anywhere in the table is SparseGPT on LLaMA-2-70B at **25.86**, against a dense baseline of 3.12.
- Paper's own remark: at extreme sparsity "it may be better to use a small dense model trained to convergence instead."

So the shape is: near-flat to ~50%, a knee somewhere in 50–70%, collapse by 80%. Between 0% and 50% this is a genuinely smooth and monotone continuous dial with arbitrarily fine resolution.

## The interesting artistic inversion

The *bad* method is the better instrument. Magnitude pruning — the cheapest, calibration-free variant — degrades far faster and far earlier (LLaMA-7B 5.68 → 17.29 at just 50%), which means it delivers a large dynamic range of damage inside a modest sparsity budget, and it needs no calibration data pass per dose. Calibrated methods (Wanda, SparseGPT) are engineered to *resist* exactly the degradation we are commissioning.

## Fitness as our dial

- **Pro**: continuous, monotone over the working range, no training, one-shot, cheap on 4B, and reversible if applied to a copy (or as a stored mask).
- **Con**: the mapping from sparsity to *utility* is much flatter than the mapping to perplexity in the low-dose regime — 50% of the weights gone still leaves a broadly functional model. Getting a visible ~1%/day decline out of sparsity means spending most of the sparsity budget early, and the collapse knee then arrives faster than the schedule wants.
- **Scale caveat**: every number above is 7B+. The smaller the model, the earlier the knee. Expect a 4B model to be closer to (or worse than) the LLaMA-7B column.

## Recommended role

Secondary / blend dial, and a strong candidate for the *steepening* of days 23–27, where the natural knee of the sparsity curve coincides with the schedule's own acceleration.
