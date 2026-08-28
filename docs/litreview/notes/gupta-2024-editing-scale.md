# Gupta, Rao, Anumanchipalli — Model Editing at Scale leads to Gradual and Catastrophic Forgetting

arXiv:2401.07453 — ACL Findings 2024. Verified: y (arXiv + aclanthology.org/2024.findings-acl.902).

## Setup
- Model: GPT-2 XL (1.5B) only.
- ROME: 3 random samples of 1,000 sequential CounterFact edits (1 fact per edit).
- MEMIT: 5,000 sequential edits (continuation of ROME sample 1).

## Reported numbers / curve points
- ROME efficacy stays ~100% until an inflection point; inflection ranges **100–800 edits** across samples (footnote: can occur as low as **10 edits**).
- Prior-edit forgetting (ROME, sample 1): **~30% of previously edited facts forgotten by 600 edits** — the gradual phase — then an abrupt catastrophic spike at the inflection point.
- MEMIT: only **~10% forgotten** at equivalent count; gradual phase extends to **~4,000 edits** before the catastrophic region.
- Downstream (SST-2, MRPC): gradual decline before the cliff; "model is no longer able to perform paraphrase detection long before the inflection point" — MRPC-style tasks collapse first.
- Neighborhood (locality) score declines continuously from the start for both methods.

## Relevance to H4
- Canonical two-phase shape: slow monotone leak, then a cliff. Knee location is method- and sample-dependent (variance of nearly an order of magnitude for ROME).
- For our N=30 interventions: single-fact ROME-style edits would sit well inside the gradual phase most of the time, but the low tail (knee at ~10) means per-day monitoring is mandatory.
- Locality decline is the earliest-moving metric → matches our "leakage counts against decay budget" accounting; track a locality/collateral probe daily.
