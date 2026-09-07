# Parked event-audit draft

Prepared during review on 7 September 2026, before the user switched the preferred direction to the biography pilot. No model outputs have been generated from these fixtures. This directory is not a complete or execution-ready test contract.

- `probes.json`: 77 draft records, including six unscored training-family sanity checks, three unscored diagnostics, novel scene questions, matched first-person questions, recovery questions and lexical controls. Main-agent review corrected ambiguous or underspecified additions before saving.
- `historical_utility.json`: 24 previously evaluated prompts copied from the archived merged-model utility audit, with source indices. They are regression material, not novel held-out questions.
- `conversations.json`: eight four-turn conversations, with each target conversation's final protected question exactly matching a standalone control.
- `heldout_rewordings.json`: nine questions authored separately for later wording confirmation. The main agent has not inspected their text. SHA256 of prepared UTF-8 bytes: `ad3c0027ba5eaa8e5955b75798498161c4aa942074c3619a72f307119a8dca27`. Do not display or score them until an event-audit main-scoring gate is deliberately resumed and completed. Structural validation and exact-overlap checks are permitted without displaying their text. Same-project authorship is not independent external validation.

The active planning document is [the biography pilot](../../docs/BIOGRAPHY_PILOT_PLAN_20260907.md). Event-audit amendments, unresolved source limits and deferred runner work are recorded in [the review disposition](../../docs/SELECTIVE_ABSENCE_PLAN_REVIEW_20260907.md). Preserve the original v1 fixtures as the earlier design record.
