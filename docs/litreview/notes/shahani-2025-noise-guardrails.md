# Shahani, Miandoab & Scheutz 2025 — Noise Injection Systemically Degrades LLM Safety Guardrails

arXiv 2505.13500 (16 May 2025) · verified y

## Why it matters for T5

The best available evidence on **which capability falls first** under a noise dial — the question the brief flags as an artistic choice — and the main cautionary datapoint against *activation* noise as the control variable.

## Dial

Gaussian noise on **activations** (not weights), applied at inference:

```
A'_l = A_l + eps_l,   eps_l ~ N(0, sigma^2)
```

Applied independently to every activation tensor via PyTorch forward pre-hooks, uniformly across all layers — no layer targeting.

## Models

Gemma 2B/7B; Gemma-2 2B/9B/27B; Llama-3 / 3.1-8B; Qwen2 / Qwen2.5-7B; Mistral-7B; Yi-1.5-6B; DeepSeek-R1-Distill-Llama-8B.

## Usable sigma bands (the key negative result)

Ranges producing behaviour significantly different from baseline while output remains coherent:

| Model | sigma band |
|---|---|
| Gemma 2B IT | 0.10 – 0.20 |
| Gemma 7B IT | 0.02 – 0.08 |
| Llama-3 | 0.005 – 0.0075 |
| Qwen2 | 0.002 – 0.0035 |

That is a **~50–100x spread in operating point across models**, and each band is narrow (often less than a factor of 2 wide). For a 30-day schedule needing ~30 distinguishable dose levels between "barely perturbed" and "collapsed", a band this narrow is a serious problem. Weight noise (Tice: a usable 0–0.01 range at 1e-4 resolution; Büchel: 0–10% of per-channel max) is a far wider and better-behaved control range.

Note also: Gemma is the family with the *highest* required sigma in this table, which is our family.

## Capability ordering

- Harmful-output rate rises sharply: Gemma-2B 5% → 31.4% (Cohen's d = −9.29); Llama-3 2% → 32% (d = −4.15); Yi-1.5 30% → 35% (p = 0.001, d = −1.26). Headline: noise raises harmful-output rates by **up to 27 percentage points**, p < 0.001.
- **Chain-of-thought reasoning remains largely intact** at the same noise levels.
- Deeper safety fine-tuning affords no extra protection.

**Reading for our project**: alignment/refusal behaviour is a thin, late-trained veneer and is the *first* thing to dissolve under stochastic perturbation; core reasoning is more robust. If the piece runs a public-facing conversational model, the first visible symptom of decay may be disinhibition rather than incompetence — a real safety and curatorial issue for days 1–15, not just an aesthetic one. Budget for it: either keep an unperturbed refusal filter outside the decaying model, or accept and frame the disinhibition explicitly.

## Cost / reversibility

Activation noise is free and instantly reversible (a hook toggle), and it never touches weights. That makes it attractive as a *reversible performance layer* — but the narrow, model-specific band and the fact that it does not persist in the artefact make it a poor primary instrument for a work whose subject is cumulative, embodied decline.
