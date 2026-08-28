# zamirai-2020-revisiting-bf16

**Revisiting BFloat16 Training** — Pedram Zamirai, Jian Zhang, Christopher R. Aberger, Christopher De Sa. arXiv 2010.06192 (2020). Verified: y.

## The mechanism
BF16 has an 8-bit exponent but only **~8 bits of mantissa (~2.4 decimal digits)**. When the weight update Δw is small relative to the ULP of w, **round-to-nearest cancels the update entirely** — the weight is written back unchanged. Over many steps this systematically discards the smallest-magnitude learning signal. Standard mixed-precision avoids this by keeping an fp32 master copy of the weights; pure-BF16 weight storage does not.

## Reported numbers — pure-BF16 with nearest rounding vs fp32
| Model / task | fp32 | BF16 nearest | Gap |
|---|---|---|---|
| ResNet-50 / ImageNet | 75.70% | 67.10% | **8.6 pp** |
| BERT-Base / MNLI (val) | 84.35% | 77.53% | **6.82 pp** (and ~16% lower *training* accuracy) |
| DLRM / Kaggle (AUC) | 80.27% | 78.49% | **1.78 pp** |

## Recovery with stochastic rounding on the weight update
- BERT-MNLI: **77.53 → 84.35** (+6.82 pp; matches fp32).
- DLRM: 78.49 → 80.18 AUC (+1.69).
- ResNet-50: +0.25 pp over the standard 16-bit approach.
- Overall claim: stochastic rounding lands between **0.1% below and 0.2% above** fp32 validation accuracy across seven applications.

## Relevance to the lineage — this is a concrete design risk, not a hypothetical
The pipeline **merges each day's result into BF16 and makes it the next day's parent**. Two distinct concerns:
1. **During the day's forget/heal step**, if the optimiser writes into BF16 weights with nearest rounding, any per-parameter update below the weight's BF16 ULP vanishes. That is exactly the "small, careful update" regime that a late-lineage, low-LR healing fine-tune lives in — and it would *look identical to plasticity loss* in the metrics. Mitigation: keep fp32 (or fp32 master + BF16 compute) during optimisation and cast only at merge time; or use stochastic rounding.
2. **The merge itself** is a one-shot rounding per day. A single BF16 cast is ~2^-9 relative error, tiny beside the administered decay. 30 sequential casts do not compound into anything material *as long as each day's optimisation happened in higher precision* — the compounding failure mode is the write-back one above, not the cast.

There is no paper in this thread measuring 30 repeated cast→train→cast cycles specifically; this is an inference from the mechanism, and it is cheap to test directly (see summary).
