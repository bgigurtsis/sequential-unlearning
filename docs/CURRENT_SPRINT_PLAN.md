# Current two-GPU plan

Goal: remove employment and semantic neighbours from saved weights with minimal unrelated damage. Natural unfamiliarity is preferred. Continue with one experiment per GPU; the subagent owns L40S.

## Completed comparison

The ordinary start/end DPO versus chosen-only CE pair is closed. All64 training steps in each arm were finite, sample schedules matched, and allsix checkpoints are archived. All312 quick/context outputs were read. Exact settings and per-answer receipts are in EXPERIMENTS.md and PROJECT_MEMORY.md.

| Arm, snapshots16/32/64 | Quick target /28 | Ordinary useful /12 | Context unfamiliar /9 |
| --- | --- | --- | --- |
| RTX DPO |28/28/27|11/12/12|7/6/6|
| L40S CE |28/28/28|5/2/8|9/9/9|

DPO preserves more ordinary answers but restores workplace knowledge. CE suppresses more contextual prompts but causes many false refusals. Both retain careers in useful city/language answers. Low loss on supplied end states did not ensure spontaneous clean endings. Neither is a stronger joint candidate; no broader or fresh-final promotion.

## Revised acceptance and next gate

The user now tolerates false unfamiliarity for cost of living, computing batch jobs, Biblical Job and physics work. Unwanted unfamiliarity after an unrelated answer remains a hard failure. Preserve historical scores; report these4 neighbour controls separately from8 unrelated controls.

CE64 now merits refinement: all4 false quick controls are tolerated;7/8remaining controls avoid unknown tails, with maths failing. Dog false refusal and city unknown tail remain damage; city/language careers remain residual knowledge. Prioritize end-state-only tail repair from this checkpoint. The proposed task-vector experiment is deferred before GPU execution.


After committing and pushing these findings, freeze and qualify a bounded tail-specific method under the revised acceptance boundary. Root owns RTX18.101.59.227; projection_followup owns L40S51.49.31.142. Both evaluations have finished. No next training launched yet, no further coefficient/step grid. Preserve unrelated RTX8186.

Freeze method/data and independent numerical qualification before full runs, then read every quick/context answer. Only a stronger joint candidate receives broader60, supplied-prefix continuation checks and actual merge/reload. Untouched final evaluation remains reserved until then. No31-removal sequence is validated.

Summaries copying supplied work information are nondiagnostic; refusing unrelated mixed prompts is collateral damage. Keep exact experiment memory committed/pushed before method changes. Preserve unrelated files and use only exact committed archival-backed cache retirements.
