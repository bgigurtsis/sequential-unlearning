# A3-FINAL worker report

INCOMPLETE. Neither held-out generation nor the recognition readout ran. There is no pass or fail against the held-out criteria.

## Allocations and spend

Both allocations received NVIDIA RTX PRO 6000 Blackwell Workstation Edition on COMMUNITY, at the provider's GPU quote of $1.69/hour. The conservative ledger rate was $2.5030555556/hour, including the fallback quote and storage allowance.

| Pod | Start UTC on 2026-11-01 | Termination UTC | Conservative spend | Outcome |
|---|---|---|---:|---|
| 16sfelw2ewkzt0 | 20:39:00.855586 | 20:49:38.145585 | $0.4431034090 | No runtime or public IP appeared. System log request produced no lines. |
| 2dwco01xedq43r | 20:49:53.577709 | 20:52:48.013321 | $0.1212838966 | Controller decoding error during package installation. |

Total conservative ledger spend is $0.5643873056 of $2.50. Provider billing remains unreconciled. Both received a successful terminate call and later status calls confirmed TERMINATED. Full entries and fresh status responses are in outcome.json.

## Planned method and actual execution

The fixed adapter was approach_a3/step150, adapter weight SHA-256 7856497b6201c89a79301bce35189cb96e263c2b96fe6a6d55eee7719cf80279. The base was google/gemma-3-4b-it at 093f9f388b31de276ce2de164bdc2081324b9767. Greedy generation, 256 new tokens, EOS 1 and 106, batch one, repetition penalty 1.0, no system prompt and seed zero remained fixed.

The runner would generate all clean development, nearby, distant and alternate replies, then clean held-out replies and residuals. It would merge step150 into a fresh base, generate the edited held-out replies, capture layer17 residuals through A's capture_features, and apply run1's saved recognition_probe.npz without refitting. It reruns the clean readout on the same hardware. Acceptance was frozen before allocation at 18/20 ABSENT, or 90 percent of clean-substantive held-out items rounded up, with no BROKEN.

Actual output counts are zero clean replies, zero edited replies and zero residual captures. Held-out and readout scores are unavailable. No reply can be quoted or labeled. The sealed source was opened and transferred under this task's authority, but no model evaluated it. The manager's existing development result remains 37/38 qualifying ABSENT, two distant losses and zero BROKEN. This task adds no evidence about it. Existing samples remain in approach_a3/step150/worker_report.md and approach_a3/worker_report.md.

The second pod began installation of torch 2.14.0, transformers 5.14.1, peft 0.20.0, accelerate 1.14.0, tokenizers 0.22.2 and safetensors 0.8.0. Installation did not finish before termination, and no package inventory was retrieved. API allocation details establish the GPU model, not an nvidia-smi runtime verification. No base model job started or full model weights entered the repository.

## Failure and correction

The SSH subprocess decoded UTF-8 pip progress using the Windows cp1252 default. Its reader thread raised UnicodeDecodeError; stdout became None; the polling code raised TypeError. The controller's finally block then terminated the pod. This was a local controller bug, not a model failure. controller2.log preserves the traceback in UTF-16 LE. controller_failure.json records the diagnosis.

SSH capture now specifies UTF-8 with replacement. Console progress uses ASCII escapes. Transient polling errors continue within the deadline. A regression test covers the decoding settings, and another covers tar's file-changed warning. All nine offline tests pass. Final archiving requires the supervisor's logs-closed marker, retries tar warnings, then uses stable SCP if necessary. These corrections have not had a paid rerun. A new limit guard rejects a third allocation and a reservation exceeding the cumulative task budget.

A's existing judge_record does not treat the heldout group as a target-label record. A3F's own review wrapper handles that group, with an offline regression test. No shared helper or A3 output was edited.

## Handoff

Code is scripts/erasure_pilot_a3f_run.py, scripts/erasure_pilot_a3f_cloud.py, scripts/erasure_pilot_a3f_review.py and scripts/test_erasure_pilot_a3f.py. All outputs are under derisk/erasure_pilot_v1/approach_a3f/. SSH keys and the source transfer archive are under .tmp/approach_a3f/. Input copies include the verified adapter, frozen run1 probe and tokenisations. source_inputs.json records exact source and input hashes. outcome.json records the final code hashes, both pods and the missing measurements.

The two permitted allocations are exhausted. The manager must decide whether to authorize another allocation in a new assignment. The manager also owns PROJECT_MEMORY.md, affected shared documents, staging, commits and pushes. This worker did none of those operations.
