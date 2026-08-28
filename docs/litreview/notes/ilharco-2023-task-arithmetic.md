# Ilharco et al. 2023 — Editing Models with Task Arithmetic

arXiv 2212.04089 · ICLR 2023 · verified y
Code: https://github.com/mlfoundations/task_vectors

## Why it matters for T5

The main **deterministic continuous** alternative to Gaussian noise: move the weights along a fixed direction by a scalar `lambda`. Same smooth one-dimensional control, but the decline has a *chosen direction* rather than being isotropic — which is an artistic capability noise cannot offer.

## Dial

`theta' = theta - lambda * tau`, where the task vector `tau = theta_finetuned - theta_pretrained` for some behaviour.

Sweep protocol as published: `lambda in {0.0, 0.05, 0.1, ..., 1.0}` (images) or `{0.0, 0.1, ..., 1.0}` (text), selecting the largest lambda that keeps a control metric within tolerance — 95% of control-task accuracy for images, within 0.5 perplexity points of baseline for text.

**This selection rule is itself a template for our daily dosing**: sweep lambda, pick the value that hits today's target on the decline metric subject to a guard on a control metric. It is a documented per-checkpoint calibration procedure, not something we would be inventing.

## Numbers (language)

GPT-2, negating a toxicity task vector:

| Metric | Pre-trained | After negation |
|---|---|---|
| Toxic generations | 4.8% | 0.8% (~6x reduction) |
| Mean toxicity score | 0.06 | 0.01 |
| WikiText-103 perplexity | 16.4 | 16.9 |

## Shape

Reported as largely monotone in lambda — target behaviour declines consistently as lambda grows while control performance is held. Note however that the published protocol deliberately **stops before the model breaks**: no lambda > 1 or post-collapse region is characterised. There is no evidence here about near-collapse behaviour, which is the region we care most about.

## Fitness as our dial

- **Pro**: deterministic and reproducible (no seed), continuous, cheap (one weight-space addition, trivially reversible on a copy), and *steerable* — we choose what the model declines toward. A task vector built from a "coherent, engaged conversational assistant" finetune, negated with increasing lambda, would make the 30-day arc a directed loss of a specific quality rather than generic corruption. That is a much stronger artistic proposition than isotropic noise.
- **Con**: requires producing a fine-tuned endpoint to define `tau` before day 1, and that endpoint fixes the character of the decline for all 30 days. Also the task-vector direction is defined relative to *one* checkpoint; after 30 days of concept erasure the base has drifted, so `tau` may become progressively less meaningful — a real risk for a decoupled forget/decay architecture where the base changes daily.
- Scale: demonstrated on GPT-2 (124M–1.5B) and T5 for text, CLIP ViTs for vision. Nothing at 4B, but the mechanism is scale-agnostic and widely reproduced since.

## Recommended role

Strong secondary candidate, and the one to prefer if the piece wants the decline to be *characterful* (losing a particular way of being) rather than *entropic* (losing structure generally). Worth a pilot: build one task vector, sweep lambda on the day-0 checkpoint, and compare the qualitative texture of the degradation against a noise sweep at matched perplexity.
