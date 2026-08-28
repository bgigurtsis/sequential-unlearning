# li-2025-ahwa-lora-analog

**Efficient transformer adaptation for analog in-memory computing via low-rank adapters (AHWA-LoRA)** — Chen Li, Elena Ferro, Corey Lammie, Manuel Le Gallo, Irem Boybat, Bipin Rajendran. Neuromorphic Computing and Engineering / IOP, 2025. arXiv 2411.17367v3. Verified: y.

## Why this is the single most on-point paper for H6
It is the closest published analogue of "take a model whose weights carry large persistent Gaussian noise, then try to train it". Analog in-memory hardware *is* a permanently noised weight matrix; hardware-aware training is fine-tuning under that noise.

## Noise levels
Gaussian noise injected on the analog weights during forward propagation, expressed as a percentage of the weight range:
- **6.7% weight noise** (plus 4.0% ADC noise) for most experiments including LLaMA instruction tuning.
- **3.0%** for the harder GSM8K RL run.
- **12%** noise **destabilises training completely** — training fails. This is the only published upper bound found for "noise too large to train through".

## Reported numbers (LLaMA-3.1-8B)
| Task | Digital baseline | Noised, unadapted | After LoRA training *under* the noise |
|---|---|---|---|
| HellaSwag (0-shot) | 78.91% | **29.48%** | **67.71%** |
| GSM8K (CoT) | 85.06% | **37.98%** | **70.74%** |

MobileBERT / SQuAD v1.1: F1 90.01 digital → 89.17 adapted analog; after 10-year conductance drift, **85.36** with AHWA-LoRA vs 85.14 with standard full hardware-aware training — i.e. LoRA with **~1–1.6M trainable params (~6.6% of the model)** matched full HWA training to within 1 F1.

## Extraction against the T4 questions
- **Does the gradient still point at the target task under large weight perturbation?** Yes. At a noise level that has already destroyed ~49 points of HellaSwag and ~47 points of GSM8K, gradient descent still recovers ~38 and ~33 points respectively. The optimisation signal survives damage far past the point the *behaviour* has collapsed.
- **Does training "recover the noise"?** No — the noise is persistent and re-sampled each forward pass; training does not remove it, it routes *around* it. The recovered model is a different solution that is robust to the noise, not a de-noised copy of the original.
- **How much capacity is needed?** Very little: a rank-limited adapter on ~1.5M params sufficed. This is encouraging for a late-lineage day where full-parameter healing might be unstable.

## Caveats before leaning on it
- The noise is **multiplicative-in-range and re-sampled per forward pass**, not a one-shot additive offset baked into the checkpoint. A permanently baked offset is arguably *easier* to train against (it is a fixed point in weight space) but the paper does not test that variant.
- The recovery is measured on the *original* capabilities, not on erasing a new concept. It supports "the model is still trainable" but not directly "erasure specifically still works".
- 12% is the observed failure point for their noise parameterisation; do not port that number to a different noise definition without re-deriving the scale.
