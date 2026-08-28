# kumar-2025-l2-init

**Maintaining Plasticity in Continual Learning via Regenerative Regularization (L2 Init)** — Saurabh Kumar et al. CoLLAs 2025 (PMLR v274); arXiv 2308.11958 (2023). Code: https://github.com/skumar9876/L2_Init. Verified: y.

## Method
Add to the training loss an L2 penalty toward the **initial** parameters rather than toward the origin:
`L_total = L_task + λ · ||θ − θ_0||²`
One hyperparameter. Rationale: parameters that recent losses are insensitive to drift back toward init, which (a) keeps them available for future adaptation and (b) **ensures the weight rank does not collapse** — plain L2 toward zero shrinks everything and can collapse rank.

## Reported findings
- Across problems representing different *types* of nonstationarity in continual supervised learning, **L2 Init most consistently mitigates plasticity loss** among the compared methods.
- Performs **comparably to continual backprop** while being far simpler (no unit-utility bookkeeping, no replacement rate / maturity threshold).
- Corroborated independently by Juliani & Ash (NeurIPS 2024), who put regenerative regularisation in their winning set, and by Dohare et al., whose best off-the-shelf mitigation was L2 + weight perturbation.

The paper's headline claim is **consistency across problem types** rather than a single large headline number; the abstract and OpenReview page do not surface a single-number improvement, and per-benchmark tables were not extracted here.

## Relevance to the heal arm
- Cheapest possible insurance for the lineage: during the retain-only healing fine-tune on day N, add `λ·||θ − θ_parent||²` or `λ·||θ − θ_day0||²`. Cost is one extra tensor of reference weights and an elementwise op — no extra forward pass, no architecture change.
- **Choice of anchor is the open design question.** Anchoring to θ_day0 preserves plasticity but fights the administered decay (it would partially *undo* the collapse curve, which is the point of the experiment). Anchoring to θ_parent preserves plasticity relative to yesterday without resisting the cumulative decay. The parent anchor is almost certainly the right one here; no paper in this thread tests a moving anchor, so this is an extrapolation.
- Same scale caveat as the rest of this literature: MLP/CNN on permuted-MNIST-style streams, <10M params.
