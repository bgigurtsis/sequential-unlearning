# Wuerkaixi et al. — Adaptive Localization of Knowledge Negation for Continual LLM Unlearning (ALKN)

ICML 2025 (PMLR v267, wuerkaixi25a; OpenReview tcK4PV3VN4). Verified: y.

## Setup
- Task-vector framework + dynamic masking to sparsify training gradients; unlearning intensity adapted to inter-task relationships.
- Three datasets, sequential unlearning tasks; 7B-class LLMs.

## Reported numbers (extraction partial — PDF was compressed; re-extract from PMLR PDF if this becomes load-bearing)
- ALKN retains **>95% of model utility after sufficient sequential unlearning**, while some baselines "completely lose their utility" over the same sequence.
- Consistently outperforms baselines on both unlearning effectiveness and utility retention across all three datasets.

## Relevance to H4
- Directly implements our proposed lever: **dose modulation by inter-task (concept) entanglement** — related/overlapping unlearning tasks get adjusted intensity so cumulative damage stays bounded.
- >95% utility after the full sequence vs total collapse for baselines is the same sustainable-vs-unsustainable split seen in MUSE/SSU/FIT: localization + adaptive dosing is what buys sustainability, not the base objective.
- TODO: digitise per-task utility curve from the PMLR PDF (https://raw.githubusercontent.com/mlresearch/v267/main/assets/wuerkaixi25a/wuerkaixi25a.pdf).
