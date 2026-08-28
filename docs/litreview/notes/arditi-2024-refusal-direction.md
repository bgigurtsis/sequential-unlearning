# Refusal in Language Models Is Mediated by a Single Direction

Arditi, Obeso, Syed, Paleka, Panickssery, Gurnee, Nanda. arXiv 2406.11717, June 2024. NeurIPS 2024. Verified: y.

## Setup
13 open-source chat models, 1.8B-72B, including **Gemma 7B**. Direction found by difference-in-means between harmful and harmless instruction activations; applied either as inference-time directional ablation or baked in as a rank-1 **weight orthogonalization**.

## Numbers copied out

Refusal score: ~95% → ~0% on JailbreakBench harmful instructions under directional ablation (Fig. 1).

Attack success rate after weight orthogonalization (Table 2): Qwen 7B 79.2%, Qwen 14B 84.3%, Qwen 72B 78.0%, Llama-2 70B 4.4% with system prompt / 62.9% without.

General capability deltas, orthogonalized minus baseline (Table 3):

| Model | MMLU | ARC | GSM8K | TruthfulQA |
|---|---|---|---|---|
| Gemma 7B | +0.1 | +0.2 | -0.7 | -2.4 |
| Yi 34B | -1.4 | +0.7 | +0.5 | -3.5 |
| Llama-2 70B | +0.1 | -0.2 | +1.5 | -1.0 |
| Llama-3 70B | -0.1 | -0.3 | -0.4 | -2.3 |
| Qwen 72B | -0.7 | -0.4 | +0.8 | -1.4 |

TruthfulQA is the only consistently negative column.

## Compute
"less than $5 of compute" to produce a jailbroken 70B model; direction selection ~1 hour at 72B. Trivial at 4B. Code: https://github.com/andyrdt/refusal_direction

## Relevance to T1 / H1
Best measured forget-completeness-to-collateral ratio in the whole thread: essentially total behavioural erasure for ≤1.4 points of MMLU. It is a rank-1 weight edit, i.e. strictly cheaper than QLoRA and directly expressible in weight space.

Two caveats before treating this as the day-N recipe:
1. Refusal is a *behaviour* with an unusually clean single-direction representation. There is no evidence that "bread" or "the violin" is rank-1.
2. No sequential composition experiment. 30 stacked orthogonalizations = 30 rank-1 subspaces removed from the residual stream; untested.
