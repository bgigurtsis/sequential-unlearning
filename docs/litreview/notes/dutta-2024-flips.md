# Dutta et al. 2024 — Accuracy is Not All You Need

arXiv 2407.09141 · NeurIPS 2024 · Microsoft Research India · verified y

## Why it matters for T5

This is a **measurement** paper, and it is load-bearing for the closed loop rather than for the dial. It shows that benchmark accuracy is nearly blind to substantial behavioural change — which is fatal for a controller that has to detect a ~1%/day decline for three weeks.

## Definition

**Flips** = percentage of benchmark answers that changed between the baseline model and the modified model, in either direction (correct→incorrect plus incorrect→correct). Accuracy nets these out; flips does not.

## Setup

- Models: Llama-2 7b / 13b / 70b-chat, Yi 6b / 34b-chat.
- Quantisation: bitsandbytes W8A8 and W4A4, GPTQ W8A16 and W4A16, AWQ W4A16, SmoothQuant W8A8.
- Also: layer dropping, WANDA pruning, SliceGPT.
- Benchmarks: MMLU, HellaSwag, LAMBADA, ARC-Easy, ARC-Challenge, PIQA, Winogrande.

## Numbers

Llama-2-70b, MMLU (5-shot):

| Scheme | Accuracy change | Flips |
|---|---|---|
| GPTQ W8A16 | −0.01% | 0.26% |
| BnB W8A8 | −0.55% | 3.32% |
| BnB W4A4 | −0.78% | 5.65% |

Across all seven tasks: accuracy differences stayed **≤2%** while flips ranged **0.26% – 13.62%**. GPTQ W8A16 was the only scheme with consistently low flips (0.26–0.43%); every other scheme showed 3–13.62%.

## Implication for the closed-loop controller

A dose that moves accuracy by 0.8% can move 5.65% of individual answers. In our schedule, the target daily step **is** about 1% — i.e. the same order as the noise floor of an accuracy-based measurement. Controlling on accuracy alone means the controller spends days 1–22 chasing measurement noise, then over-corrects.

Concrete recommendations for the measure arm:

1. Control on a **distance-from-day-0** metric, not an absolute score: flips against the frozen day-0 model, or KL divergence of next-token distributions on a fixed probe set, or perplexity on a frozen text (`data/ppl_text.txt` already exists for this).
2. Keep the probe set fixed and frozen so the metric is comparable across 30 days.
3. If a benchmark score is wanted for the public-facing narrative, compute it — but do not close the loop on it.

This dovetails with Gromov et al.: QA accuracy is flat-then-cliff, next-token loss is continuous. Both papers point the same way — **the control signal must be a continuous divergence measure, not a discrete task score.**
