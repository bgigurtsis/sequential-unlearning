# Biderman et al. 2024 — LoRA Learns Less and Forgets Less

- arXiv:2405.09673, TMLR 2024 (Databricks Mosaic). Artifacts: https://github.com/danbider/lora-tradeoffs, https://huggingface.co/LoRA-TMLR-2024. Verified: y.

## Setup
- Llama-2-7B. Two regimes: instruction fine-tuning (~100K prompt-response pairs; Magicoder-Evol code, MetaMath) and continued pretraining (up to 20B tokens; StarCoder-Python, OpenWebMath). LoRA ranks 8/16/64/256 vs full FT.
- Learning metrics: HumanEval, GSM8K. Forgetting metric: average of HellaSwag + ARC + WinoGrande.

## Numbers
- IFT at high rank reaches parity on learning: HumanEval 0.498 (LoRA r=256, Magicoder) vs 0.497 (full FT) — while still forgetting less on the HellaSwag+ARC+WinoGrande average.
- Low ranks (8–64) lag full FT considerably on target-domain learning; CPT (20B tokens): LoRA never closes the learning gap at any tested rank.
- Full FT weight perturbations have rank 10–100x typical LoRA ranks; MLP modules need much higher rank than attention.
- LoRA mitigates forgetting more than weight decay or dropout, and keeps generations more diverse.
- Rank is a monotone knob trading learning for forgetting (swept 16/64/256).

## Relevance to T3 (H1 + H2 design lever)
- The healing pass has a small learning target (restore chat quality) and a hard constraint (don't touch erased concepts). LoRA's profile — learns less, forgets/changes less, perturbation confined to a rank-r subspace — fits exactly: a low-rank healing adapter bounds the subspace in which revival can occur, and can be merged or discarded per day.
- Caveat: no unlearning experiments in this paper; "bounds revival" is an inference, not a measured result. Also note LoRA-based RELEARNING attacks still succeed (Hu et al. used standard FT; low-rank attacks also work in the literature), so low rank reduces but does not eliminate H2 risk.
- Recommended starting point: healing via LoRA r=16–64 on attention+MLP, since the utility repair target is modest compared with learning code/math from scratch.
