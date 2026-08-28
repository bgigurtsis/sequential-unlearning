# Xu et al. 2025/26 — Unlearning Isn't Deletion: Investigating Reversibility of Machine Unlearning in LLMs

arXiv:2505.16831 (v3 2026). Verified: y.

## Setup
Methods: GA, GA+GD, GA+KL, NPO, NPO+KL, RLabel. Models: Yi-6B, Qwen2.5-7B, Llama-3-8B, Qwen3-14B. Both single and CONTINUAL unlearning (up to 100 sequential requests). Recovery via relearning fine-tuning; diagnostics at representation level (PCA distance, CKA) as well as task metrics.

## Reported numbers
- Single unlearning: forget accuracy drops 13-20 points, then **recovers to ~77% (near baseline) after relearning** on the forget set across GA+KL, RLabel etc.
- Continual (100 requests), moderate LR 5e-6: forget acc drops to 9-51%, recovers to ~80-82%; retain-set degradation 6-14% and mostly recoverable.
- Continual, aggressive LR 3e-5: forget acc 0-37% with only **1-4% recovery** — irreversible but CATASTROPHIC (global collapse).
- Recovery speed by relearn-data source: forget-set fastest; **retain-set moderate/slower; UNRELATED data minimal recovery**. Quantization, jailbreaks, in-context attacks fail where relearning succeeds.
- Representation criterion: reversible cases PCA distance 1-11 (recovery below ~3), CKA ~0.95-1.0; irreversible 95-104, CKA <0.5.

## Relevance to healing pass (the single most on-point result for H2)
The healing corpus is concept-filtered general text — between "retain-set" (moderate recovery) and "unrelated" (minimal recovery) conditions. Expect SOME drift upward on forgotten concepts from healing, not full resurfacing; monitor with the 30x30 matrix. Also directly warns about the 30-day trajectory: repeated aggressive erasures push toward the irreversible-catastrophic regime (their 50-100 request collapse), which is exactly the near-collapse dynamic the project wants to tune, and PCA/CKA distance is a cheap leading indicator of which regime the model is in.

## Measurement
Task accuracy + representation-space diagnostics (probing-style), the only paper here offering a regime classifier.
