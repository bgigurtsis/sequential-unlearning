# Yoon, Hong, Jeung, No 2026 — Rethinking Benign Relearning: Syntax as the Hidden Driver of Unlearning Failures

arXiv:2602.03379. Verified: y. Yonsei University.

## Core claim
Benign relearning is driven by SYNTACTIC similarity between relearn data and forget data, not topical relevance. Unlearning disproportionately suppresses query-answer TEMPLATES (structurally rigid) rather than target keywords; relearn data sharing surface structure restores the templates and the keywords re-emerge.

## Reported numbers (TOFU, Llama-2-7B; GA/NPO/SCRUB)
- Syntactically similar relearn set: **~60-80% keyword recovery**.
- Topically relevant relearn set: **~0-20% recovery**, even with extended fine-tuning.
- Syntactic similarity to target set: 0.45 (syntactic set) vs 0.23 (topical set).
- BLUR reassessment: with matched training budget/eval timing, topically relevant data barely beats unrelated filler.
- Loss-ratio evidence: template-loss/keyword-loss ratio grows during unlearning — templates suppressed more than keywords.

## Mitigation (directly usable)
Paraphrase forget-set queries into heterogeneous syntactic structures (GPT-4o) before unlearning: similarity 0.45 -> 0.22; eliminates the benign-relearning vulnerability, speeds forgetting, and improves retain/world-knowledge utility.

## Relevance to healing pass
Reframes H2's filtering assumption: the healing corpus is filtered by CONCEPT (topic), but topic is the wrong axis — resurfacing risk comes from healing text that shares the FORMAT of the erasure data (e.g., QA-style text if erasure used QA pairs). Two mitigations for the project: (1) syntactically diversify each day's erasure prompts before the forget pass; (2) prefer healing text whose format differs from the erasure format, or diversify the erasure so no single format is load-bearing. Also explains why "unrelated" data sometimes resurfaces knowledge (Hu et al.) and sometimes doesn't (Xu et al.): the hidden variable is syntax.

## Measurement
Keyword recovery rate under generation; loss decomposition into template vs keyword tokens.
