# Fang et al. — AlphaEdit: Null-Space Constrained Knowledge Editing

arXiv:2410.02355 — ICLR 2025 Outstanding Paper. Verified: y. Code: github.com/jianghoucheng/AlphaEdit.

## Setup
- Models: GPT-2 XL (1.5B), GPT-J (6B), LLaMA-3-8B.
- Sequential editing: 2,000 samples in batches of 100 (extended to 3,000).
- Mechanism: project each parameter perturbation onto the null space of preserved-knowledge key matrices before applying it.

## Reported numbers
- MEMIT at 2,000 sequential edits: GLUE F1 (SST, RTE, CoLA...) "rapidly approaching zero" — general capability collapse.
- AlphaEdit at 3,000 edits: original model performance maintained across all general-capability metrics.
- LLaMA-3 at 2,000 edits: Efficacy MEMIT 65.65% vs AlphaEdit 98.90%; Generalization 64.65% vs 94.22%; Consistency 6.58 vs 32.40.
- Average editing-capability improvement from adding the projection to existing methods: +36.7%.

## Relevance to H4
- Existence proof that a constrained intervention operator can push the knee out by >1 order of magnitude (MEMIT dead by 2k edits; AlphaEdit healthy at 3k) at identical edit efficacy.
- The null-space constraint is the formal version of "minimum collateral": leakage per edit is forced ~orthogonal to retained knowledge. Our forgetting arm's healing stage approximates this post hoc; AlphaEdit does it in the update itself.
- See suresh-2026-alphaedit-repro: the protection is bounded — knee reappears at ~5,000 edits, and the advantage is weaker on 1–4B models.
