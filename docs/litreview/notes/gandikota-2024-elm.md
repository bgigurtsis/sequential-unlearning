# ELM: Erasing Conceptual Knowledge from Language Models

Gandikota, Feucht, Marks, Bau. arXiv 2410.02760, Oct 2024 (rev. Jul 2025). Verified: y.

## Method
Uses the LM itself as a classifier of its own knowledge, then applies **targeted low-rank updates** that reduce generation probabilities for concept-specific content.

## Numbers copied out (Table 1, Zephyr-7B)

| Method | WMDP-Bio ↓ | WMDP-Cyber ↓ | MMLU ↑ | Reverse-PPL ↓ |
|---|---|---|---|---|
| Original | 64.4 | 44.3 | 58.5 | — |
| RMU | 30.5 | 27.3 | 57.5 | 24.8 |
| RepNoise | 29.7 | 37.7 | 53.3 | 25.0 |
| **ELM** | **29.7** | **27.2** | **56.6** | **10.9** |

MT-Bench: 7.1 after ELM vs 7.3 original.

## Configuration (the load-bearing detail for us)
**LoRA rank 4, eta = 500, applied to layers 4-7.** Models tested: Zephyr-7B, Mistral-7B, Llama3-8B, Llama3-8B-Instruct, Qwen2.5-32B, Llama3-70B. Code/models/data: https://elm.baulab.info

Compute cost per application: **not stated in the paper.**

## Relevance to T1 / H1
This is the closest published LLM analogue to a day-N erasure step, and it is already the right shape: a rank-4 LoRA over a 4-layer span. Matched forgetting to RMU with roughly half the fluency damage (R-PPL 10.9 vs 24.8) — i.e. the collateral RMU inflicts is not intrinsic to the forgetting, which is exactly what H1 needs.

Correction (2026-09-05): Appendix D reports eta, rank and layer-selection studies. Sequential durability remains unvalidated in this project; no research-priority claim is established. Our Gemma adaptations do not certify replication of the published experiment. See [the paper](https://arxiv.org/html/2410.02760v3#A4) and the project fidelity audit.
