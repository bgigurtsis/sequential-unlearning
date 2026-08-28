# Büchel et al. 2025 — Analog Foundation Models

arXiv 2505.09663 · NeurIPS 2025 · IBM Research + ETH Zürich · verified y
Code: https://github.com/IBM/analog-foundation-models

## Why it matters for T5

The best **smooth, monotone, published weight-noise dose–response curve at our model scale (1B–3.8B)**. The analog-in-memory-computing literature is the only community that routinely sweeps weight noise on real LLMs, because noisy weights are their hardware reality rather than an attack.

## Dial parameterisation (transferable design)

Per-channel additive Gaussian noise:

```
W'[:, i] = W[:, i] + gamma * max(|W[:, i]|) * tau,   tau ~ N(0, I)
```

- Noise magnitude is expressed as a **percentage of the per-channel maximum absolute weight**, not as an absolute sigma.
- Hardware-realistic operating point: `gamma ≈ 0.02–0.03`.
- Sweep in Fig. 3: **0% → ~10%** of per-channel max, for both models.
- Other noise models evaluated: PCM device noise, ReRAM noise, PCM scaled 1.5x and 2.0x, read noise, conductance drift.

**This normalisation is the single most useful thing to steal.** A global absolute sigma means the same "dose" is a rounding error in one layer and catastrophic in another, because weight scales differ by orders of magnitude across a transformer. Per-channel scaling by `max|W|` makes one scalar dose comparable across the whole network and across checkpoints whose weight statistics have drifted from daily erasure — which is precisely the per-checkpoint calibratability H3 requires.

## Reported numbers

Average accuracy drop at hardware-realistic AIMC noise, off-the-shelf vs analog-trained:

| Model | Off-the-shelf drop | Analog-trained (HWA) drop |
|---|---|---|
| Phi-3-mini-4k-instruct (3.8B) | −8.01% | −3.81% |
| Llama-3.2-1B-Instruct | −9.81% | −4.58% |

At ~10% Gaussian noise (per-channel max) the models lose roughly 4–5% average accuracy relative to noise-free. HWA training beats LLM-QAT and SpinQuant under noise by up to +11.4%.

Elsewhere quoted (X/press summaries of the same result): Phi-3-mini −7.1%, Llama-3.2-1B −9.6% — treat the paper's own table as authoritative.

## Shape of the curve

Described as **smooth and monotonically decreasing** across the swept range, with the analog-trained models showing "a more graceful decline". **No cliff is observed inside 0–10% of per-channel max.** That is the core positive evidence for H3 in the low-dose regime: a ~1%/day schedule for three weeks lives comfortably inside a region where the curve is smooth.

Important limitation: the sweep stops well before collapse. Nothing here speaks to days 25–30.

## Hazard flagged for our project

Noise-aware training *flattens* the dose–response curve — a model can be made substantially more noise-tolerant with <1% of pretraining tokens. If any healing/repair stage in our pipeline involves training the model while it is noisy, we will inadvertently be doing hardware-aware training and the dial will lose potency over the 30 days. Keep the noise draw strictly downstream of all training.

## Cost on 4B BF16

One state-dict pass; per-channel `max|W|` is a cheap reduction. Fully reversible on a copy.
