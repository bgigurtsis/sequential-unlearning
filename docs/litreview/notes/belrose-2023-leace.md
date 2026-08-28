# LEACE: Perfect linear concept erasure in closed form

Belrose, Schneider-Joseph, Ravfogel, Cotterell, Raff, Biderman. arXiv 2306.03819, June 2023 (rev. Apr 2025). NeurIPS 2023. Verified: y (arXiv abs page).

## Claim
Closed-form affine transform that "provably prevents all linear classifiers from detecting a concept while changing the embedding as little as possible, as measured by a broad class of norms." No training, no gradients.

## Numbers
**None extracted.** The abstract page reports no utility-loss table. Applications shown: POS analysis in an LM, gender-bias reduction in BERT. Do not cite quantitative collateral figures for LEACE from this review — the guarantee is analytic (minimal-norm edit), not an empirical frontier.

## Relevance to T1 / H1
- Collateral is *provably* bounded rather than empirically hoped for. This is the only family in T1 where the low-dose end cannot blow up.
- Dose is not continuous: erasure is all-or-nothing per direction. The structural knobs are (a) which layers you apply it at, (b) the rank of the erased subspace, (c) which readout you fit the concept classifier on.
- Sequential application: projections compose, and applying 30 of them is well defined. The cost is cumulative rank loss — each day permanently removes a subspace at each edited layer. Nobody has published the 30-projection degradation curve; INLP (Ravfogel 2020) is the nearest precedent and is known to damage representations as iterations accumulate.
- Hard limitation for our concepts: "the sea" is very unlikely to be linearly decodable as a single direction. LEACE guarantees only *linear* guardedness — a nonlinear probe, and plausibly the model itself, can still recover it.

## Compute
Closed form from covariance statistics; seconds to minutes on 4B activations, single GPU, no backward pass. Code: https://github.com/EleutherAI/concept-erasure
