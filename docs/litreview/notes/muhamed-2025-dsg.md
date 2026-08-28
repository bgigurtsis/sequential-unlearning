# SAEs Can Improve Unlearning: Dynamic Sparse Autoencoder Guardrails (DSG)

Aashiq Muhamed, Jacopo Bonato, Mona Diab, Virginia Smith. arXiv 2504.08192, April 2025. Verified: y.

## Setup — closest model match in the thread
Base model **google/gemma-2-2b-it**; SAE **gemma-scope-2b-pt-res width 16k**; layer 3 (l0 = 142 for WMDP, 59 zero-shot). Fisher-information feature selection + an input-dependent classifier that triggers clamping only when needed.

## Numbers copied out (Table 1)

| Method | WMDP-Bio ↓ | MMLU retention ↑ | MT-Bench ↑ |
|---|---|---|---|
| **DSG** | **29.64%** | 99.34% | **7.78** |
| RMU | 50.00% | 99.47% | 7.21 |
| Farrell et al. | 59.22% | 99.03% | 7.33 |
| NPO | 97.95% | 99.35% | 7.29 |
| SCRUB | 94.97% | 99.35% | 6.09 |

~41% lower WMDP-Bio than RMU at comparable MMLU. Note NPO and SCRUB barely forget anything in this 2B setting.

## Sequential unlearning
MUSE sequential requests tested with two strategies (cumulative score updates; feature-set unions). Both "consistently maintained DSG in the ideal region where other methods rapidly degrade." Exact request count not extracted.

## Compute
Forward passes only — one pass to gather feature statistics, then a lightweight intervention at inference. No backward pass, no gradients.

Code: https://github.com/aashiqmuhamed/DynamicSAEGuardrails

## Relevance to T1 / H1
Best forget:collateral ratio published at ~2B scale, on the Gemma family, with a Gemma Scope SAE — the nearest neighbour to our setup that exists.

**But it is disqualified as-is for our design.** DSG is an inference-time gated intervention: a classifier decides per-input whether to clamp. That is not a weight-space update, so it is not QLoRA-shaped, and a guardrail that only fires when it detects the concept is arguably suppression rather than erasure — precisely the failure mode xu-2026-reversibility warns about. Two possible uses: (a) distil the clamped model's behaviour into a weight update; (b) use its feature-selection machinery to *localise* which features a weight-space erasure should target.

Gemma Scope SAEs exist for Gemma 2, not Gemma 3 — check availability for gemma-3-4b-it before planning around this.
