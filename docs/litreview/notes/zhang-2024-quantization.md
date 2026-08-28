# Zhang et al. 2024 — Catastrophic Failure of LLM Unlearning via Quantization

arXiv:2410.16454, ICLR 2025. Verified: y.

## Reported numbers
- Utility-constrained unlearning methods (GA+GD, NPO+KL, MUSE setups, Llama-2-7B class): **21% of forgotten knowledge retained at full precision -> 83% retained after 4-bit quantization** (average). Reported recovery ~89% knowledge retention in some summaries.
- Mechanism: unlearning that preserves utility makes SMALL weight deltas; low-bit quantization rounds them away, restoring near-original weights.
- Mitigation (SURE): saliency-map-guided larger-magnitude updates on relevant weights.

## Relevance to healing pass
Not a fine-tuning result per se, but the same mechanism explains benign-FT fragility: small-delta erasures are trivially undone by any subsequent weight perturbation, including healing FT and any post-hoc quantization of daily checkpoints. Practical warnings for the project: (1) never evaluate resurfacing on a quantized copy of the checkpoint and assume it holds at fp16 or vice versa; (2) prefer erasure updates with larger, structured weight displacement (consistent with Siddiqui 2025 weight-space findings).

## Measurement
Knowledge-retention metrics on forget set (MUSE-style memorization/QA), multiple quantization precisions swept.
