# Pillutla et al. 2021 — MAUVE (NeurIPS 2021, Outstanding Paper; arXiv:2102.01454)

Verified: y (papers.nips.cc hash 260c2432a0eecc28ce03c10dadc078a4).

## Method

Compares model-text and human-text distributions via KL divergence frontiers computed in a quantized embedding space (GPT-2 embeddings, k-means quantization). Output in (0,1]; 1 = indistinguishable from human text.

## Reported numbers (WebText continuations)

- GPT-2 small, nucleus p=0.9: 0.906
- GPT-2 medium, nucleus p=0.9: 0.936
- GPT-2 large: 0.878 (pure sampling), 0.952 (nucleus p=0.95)
- GPT-2 XL: 0.908 (pure sampling), 0.955 (nucleus p=0.95)
- MAUVE increases monotonically with model size and with better decoding — a validated quality ordering at the high end.

## Limitations for this project

- Sample size: standard practice uses ~5,000 generations for stable frontier estimates; at 100–300 daily generations the k-means quantization is noisy (follow-up "MAUVE Scores for Generative Models: Theory and Practice", arXiv:2212.14578, analyses sample-complexity/quantization effects).
- High-end scores compress into 0.88–0.96; at the catastrophic end scores crash toward ~0 and flatten — poor discrimination between "very bad" and "terminally bad".
- He et al. 2023 (blind spots): MAUVE built on GPT-2 features is insensitive to errors at the beginning/middle of generations.

## Verdict for the decay scalar

Use as an occasional (weekly) sanity cross-check with pooled multi-day samples, not as a daily controller input.
