# Men et al. 2024 — ShortGPT: Layers in LLMs are More Redundant Than You Expect

arXiv 2403.03853 · Findings of ACL 2025 · verified y

## Why it matters for T5

The companion result to Gromov et al.: an explicit, cheap **ordering rule** for which layer to remove next, plus an independent confirmation of the cliff.

## Dial

Block Influence (BI) = 1 − cosine similarity between a layer's input and output hidden states, averaged over a calibration set. Low BI = the layer barely transforms its input = safe to delete. Dose = number of layers deleted, in ascending BI order.

## Numbers

| Model | Layers removed | Ratio | Dense MMLU | Pruned MMLU | Dense CMMLU | Pruned CMMLU | Avg. retained |
|---|---|---|---|---|---|---|---|
| Llama-2-7B | 9 / 32 | 27.1% | 45.39 | 43.96 | 32.92 | 32.25 | 95.69% |
| Llama-2-13B | 10 / 40 | 24.6% | 55.00 | 54.69 | 38.40 | 38.38 | 97.34% |
| Baichuan2-7B | 9 / 32 | 24.2% | 53.87 | 45.77 | 56.95 | 47.87 | 91.52% |
| Baichuan2-13B | 10 / 40 | 24.7% | 59.50 | 61.30→58.86 (CMMLU) | 61.30 | 58.86 | 87.33% |

(Baichuan2-13B: dense MMLU 59.50 → ShortGPT 52.11.)

## Shape

Figure 5: "as the pruning ratio increases, the performance of the model declines. However, the MMLU score drops significantly at a certain layer" — a sharp threshold rather than a gradual slope. Same qualitative finding as Gromov et al., on different models, with a different layer-selection criterion. The cliff is a property of layer removal, not of one particular selection heuristic.

Note also the **family dependence**: Llama-2 retains 95–97% at ~25% removal while Baichuan2-13B retains only 87%. Removal tolerance is not predictable from parameter count alone, so gemma-3-4b-it must be measured, not extrapolated.

## Fitness

- **As a daily dial: no.** 32-ish layers means a minimum step of ~3%, and the response is flat-then-cliff.
- **What it gives us**: a *reproducible order*. If we ever use layer removal, BI tells us which layer goes first, second, third — so a "one more layer each week" schedule is at least principled and repeatable rather than arbitrary. That matters for a work that claims its decline is administered rather than accidental.
- BI is cheap to compute on 4B (one forward pass over a calibration set, per checkpoint), which is attractive if we want to recompute the ordering as the model changes.

## Reversibility

Complete, if applied to a copy: layer removal is just a subset of the original state dict, so the original is untouched and any day's model can be rebuilt from (day-0 checkpoint, list of removed layers).
