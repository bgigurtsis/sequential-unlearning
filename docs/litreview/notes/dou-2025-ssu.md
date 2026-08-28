# Dou et al. — Avoiding Copyright Infringement via LLM Unlearning (Stable Sequential Unlearning, SSU)

arXiv:2406.10952 — NAACL Findings 2025 (2025.findings-naacl.288). Verified: y. Code: github.com/guangyaodou/SSU_Unlearn.

## Setup
- Models: Llama-3.1-8B-Instruct (10 sequential steps), Mistral-7B-Instruct-v0.3 (6 steps — baselines dead by then).
- One book unlearned per time step — the closest published analogue to "one concept per day".
- SSU = task-vector negation + random-labeling loss + weight-saliency targeting. No retain-data healing stage.

## Digitised curve points (Llama-3.1, MMLU / MT-Bench)
- SSU: step 1: 0.6625 / 8.225; step 5: 0.6425 / 8.142; step 10: still stable, no collapse.
  → per-step MMLU leakage ~0.005 absolute (~0.75% relative per cycle) over the first 5 steps, flattening after.
- GA: MMLU 0.5821 → 0.3102 by step 5 (Llama); collapses at step 1 on Mistral.
- Task Vector: MMLU = 0 by step 10 (Llama); sudden collapse at step 5 on Mistral (both metrics → 0).
- Gradient Difference: MT-Bench 8.034 → 4.944 at step 5.
- NPO: gradual decline, stays functional, but weaker unlearning.

## Relevance to H4
- Direct per-cycle leakage estimate on an 8B chat model: **~0.3–0.8% relative utility per forget cycle** for a stability-engineered method; naive methods knee at **steps 1–5** (Mistral) or **5–10** (Llama).
- Also shows model dependence: identical protocol knees 2x earlier on Mistral-7B than Llama-3.1-8B — our gemma-3-4b number cannot be assumed from either.
- Collapse signature: Task Vector's step-5 Mistral collapse is abrupt (healthy → 0 in one step), supporting cliff-style rather than graceful failure near the knee.
