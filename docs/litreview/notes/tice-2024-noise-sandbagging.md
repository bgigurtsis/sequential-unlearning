# Tice et al. 2024 — Noise Injection Reveals Hidden Capabilities of Sandbagging Language Models

arXiv 2412.01784 · NeurIPS 2025 (preliminary versions at SATA / SoLaR NeurIPS 2024 workshops) · verified y
Code: https://github.com/camtice/SandbagDetect

## Why it matters for T5

This is the closest published precedent to our proposed dial: **additive Gaussian noise on all model weights, swept on a fine grid, on 7-8B instruct-tuned models, with benchmark accuracy as the readout**. It is the only paper found that treats the noise scale itself as the independent variable across a dense grid rather than picking one operating point.

## Dial parameterisation (as reported)

- Noise `~ N(mu = 0, sigma^2)`, `mu = 0`.
- Two injection routes:
  1. **Direct**: "all parameters in the model are perturbed by directly adding our noise vector".
  2. **LoRA (rank r=8)**: modifies only linear-layer parameters. Authors give an equivalence `sigma_LoRA = 8^(1/4) * sqrt(sigma_direct)`.
- Sweep: `sigma in [0, 0.01]`, step `delta_sigma = 1e-4` → 101 dose levels.
- `N = 5` independent noise seeds per (model, benchmark, sigma) point; up to 100 seeds in the extended recovery analysis.

## Models

Llama-3-8B-Instruct; Llama-3.1-70B-Instruct (8-bit); Mistral-7B-Instruct-v0.2; Phi-3 mini / small / medium; DeepSeek-Math-7B; Mistral Large.

## Reported numbers

The headline metric is an **improvement ratio** `phi` = best accuracy over the sigma sweep / baseline accuracy.

| Model / benchmark | phi_std (honest model) | phi_sbg (sandbagging model) |
|---|---|---|
| Llama-3-8B, AI2 | 1.030 (0.005) | — |
| Mistral-7B, WMDP | 1.045 (0.008) | 2.481 |
| Phi-3-medium, AI2 | 1.028 (0.003) | 10.286 |

Honest models: `phi_std` clusters in **1.00–1.074**, i.e. noise never buys more than a few percent; the decline with sigma is described as the *expected* monotone degradation, with low variance across the 5 seeds ("stable, reproducible degradation curves without erratic fluctuations").

Mistral Large, no-goal sandbagging setting: 66.6% → 100% on 30 GSM8K problems under noise.

Detection: XGBoost on the noise-response curve separates sandbagging from honest models at **96.2%** accuracy (leave-one-model-out).

## Near-collapse behaviour

The sweep is **capped at sigma = 0.01 because "model performance becomes incoherent at values > 0.01"**. So this paper localises our collapse boundary for 7-8B models to just above 0.01 (absolute, unnormalised additive noise) but does not characterise the shape of the transition. That characterisation is exactly the gap our day-25→30 calibration has to fill ourselves.

## Caveats for closed-loop control

1. **Non-monotone bumps are real.** The whole paper is built on the fact that noise can *increase* measured accuracy when a capability is being suppressed rather than absent. Our model will have had a concept erased that same day; if the erasure works by suppression rather than removal, noise may partially undo it and the measured decline can go backwards. The controller must be robust to a negative-damage day.
2. Absolute sigma is not transferable across checkpoints or layer types — the paper uses one global sigma, which is why per-model usable ranges differ. Per-channel normalisation (see Büchel 2025) is the fix.
3. Seeds matter but not much: low across-seed variance at fixed sigma is good news for reproducibility of a daily dose.

## Cost on 4B BF16

Trivial: one pass over the state dict adding `torch.randn_like(W) * sigma`, on a copy. Re-drawable, and fully reversible because the original checkpoint is untouched.
