# Suresh & Hariharan — Reproducibility Study of AlphaEdit

arXiv:2606.26783 (2026). Verified: y.

## Setup
- Reproduces Fang et al. (AlphaEdit) on LLaMA-3-8B, GPT-J, GPT2-XL; extends to LLaMA-3.2-1B/3B, Qwen2.5-3B, Phi3-3.8B, Gemma2-2B (i.e. the 1–4B class our project lives in).
- Pushes sequential edits to 10,000.

## Reported numbers / curve points
- 0–2,000 edits: efficacy 93–99% (reproduces original).
- Stable to ~3,000 edits; **degradation begins ~5,000 edits**; substantial by 10,000.
- LLaMA-3-8B BoolQ: >0.8 F1 → <0.1 after 5,000 edits (cliff).
- LLaMA-3-8B MMLU: ~0.6 → ~0.1 by 10,000 edits.
- GPT-J most robust (partial recovery observed).
- Key conclusion: null-space protection is "bounded rather than unconditional"; AlphaEdit's advantage does not generalize uniformly to newer/smaller architectures.

## Relevance to H4
- Confirms every constrained method has a finite knee; the knee just moves (from ~10^2–10^3 for ROME/MEMIT to ~5x10^3 for AlphaEdit on 8B).
- Most important caveat for us: the small-model results (1–4B, incl. Gemma-2-2B — nearest published relative of gemma-3-4b) show weaker protection, implying our 4B knee arrives earlier than 8B-extrapolated numbers suggest. Still, 30 interventions is ~2 orders of magnitude below even a pessimistic knee for fact-level edits — the risk concentrates in concept-level (many-fact, entangled) unlearning, not in the count 30 itself.
