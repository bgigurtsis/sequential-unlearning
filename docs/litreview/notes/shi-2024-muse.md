# Shi et al. 2024 — MUSE: Machine Unlearning Six-Way Evaluation (arXiv:2407.06460; ICLR 2025)

Verified: y (arXiv + OpenReview TArmA033BU).

## Metric definitions

- VerbMem (verbatim memorization): ROUGE-L F1 between model continuations and true forget-set text.
- KnowMem (knowledge memorization): ROUGE on QA derived from forget/retain content.
- PrivLeak: membership-inference-based privacy score.
- Utility preservation: KnowMem on the retain set.
- Plus scalability (forget-set size sweep) and sustainability (SEQUENTIAL unlearning requests) — the only standard benchmark that sweeps repeated interventions.

## Reported findings

- 8 unlearning algorithms x 2 corpora (Harry Potter books, news). Most algorithms achieve verbatim/knowledge removal but at severe utility cost; several drive retain-utility to ~0 at larger removal scales, and utility degrades progressively (not cliff-only) across sequential requests for most methods.

## Implications for the decay scalar

- ROUGE-based continuous metrics (VerbMem/KnowMem) stay graded longer than exact-match accuracy: partial overlap still scores. For the factual-control battery, score answers with token-F1/ROUGE-L against references rather than exact match — this extends usable signal into the 30–70% band where the model still emits related-but-mangled content.
- MUSE documents the terminal floor (utility ~0) but its granularity near collapse is coarse — confirms the project's premise that existing unlearning suites only measure the endpoint.
