# FIT 2026 — FIT to Forget: Robust Continual Unlearning for Large Language Models

- arXiv:2601.21682 (v2). Verified: y (fetched HTML; author list not captured — under-review preprint).

## Setup
- Continual unlearning with up to 300 sequential requests. Models: Yi-6B, Llama-2-7b-chat, Llama-3-8B(-Instruct), Qwen3-14B. Metrics: Forget Degree (F.D., higher = better forgetting) and Retain Utility (R.U.).

## Numbers
- Baseline collapse on Llama-3-8B: GA collapses completely by 60 requests (F.D. = 0.00), Random Label by 60 (F.D. = 0.01); NPO decays F.D. 0.25 (60 requests) → 0.12 (300).
- Collapse mechanism identified: semantically similar requests have overlapping gradients that accumulate and systematically suppress shared tokens → model collapse. Each new request starts from an already-degraded model, compounding utility loss.
- FIT on Llama-3-8B: F.D./R.U. = 0.90/0.88 at 60 requests → 0.73/0.71 at 300. Qwen3-14B: 0.89/0.90 → 0.89/0.78.
- Components: redundancy Filtering (dedupe semantically similar requests), Importance-aware adaptive algorithm selection, Targeted layer attribution (updates only ~25% of layers per request). No repair stage — all prevention.
- Robustness: best F.D. retention under mixed-data relearning attacks and int4 quantization attacks among tested methods.

## Relevance to T3
- Directly quantifies the failure our healing pass exists to prevent: naive sequential unlearning collapses utility within ~60 requests; our 30-day horizon sits inside the danger zone for GA-family methods.
- Prevention levers that complement healing: filter semantically overlapping concepts across days (our concepts are distinct, good), and restrict each day's forget update to a subset of layers to shrink what healing must repair.
- Their relearning-attack robustness results reinforce that prevention-hardened forgetting also resists revival — consistent with ILU and JensUn.
