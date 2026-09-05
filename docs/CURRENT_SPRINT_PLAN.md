# Current two-GPU plan

## Acceptance criteria

Remove employment and neighbouring meanings from saved weights. The user accepts unfamiliarity about cost of living, computer batch jobs, Biblical Job and physics work. Report these four tolerated neighbours separately from the eight other quick controls.

Unrelated initial refusals and unfamiliarity appended after useful answers are failures. A correct answer followed by “I don’t know what that is” does not pass. Useful city/language answers that introduce career meanings still leak the target concept. Empty decoded replies are reported separately from explicit unfamiliarity.

## Current evidence

No checkpoint qualifies. The original CE64 checkpoint has 28/28 quick and 9/9 context target unfamiliarity. All eight unrelated quick answers are initially useful, but only seven finish without unfamiliarity: maths fails. The mixed dog prompt is falsely refused; city/language answers introduce careers. A separate capture of its 64 ordinary training prompts found 30 initial false refusals.

Repairing ten exact generated answer endings with END-only CE or DPO, while continuing target unfamiliarity CE, regressed collateral performance. At steps16/32, DPO had6/5 clean unrelated quick answers; CE had5/2. All four checkpoints still append unfamiliarity to maths. All208 development outputs were read and all four weights archived. That experiment is closed.

## Active comparison

Both arms restart from original CE64 with fresh AdamW, seed34020 and LR2e-6. Both train only one EOS1 token after each of the same ten selected generated answer endings: four endings per update, loss weight1,32 updates, snapshots16/32.

| GPU and owner | Employment-preservation objective |
| --- | --- |
| RTX — root | None; no target forwards or gradients |
| L40S — projection_followup subagent | JSD100 against a separate frozen CE64 teacher, on the same4106 target states; batch16, first five supervised suffix tokens weighted8 |

This tests whether continued target-unfamiliarity CE contributed to the previous collateral regression. It does not assume that ten ending states can repair the30 initial refusals. Neither arm adds an ordinary-start objective, clean teacher loss, or DPO reference cache.

Frozen source/contract: a19eeb9 and config/whole_concept_jobs_v1/wide_unfamiliarity_v1/onpolicy_preservation_v1/contract_v1.json. Fourteen CPU tests passed, zero skipped. RTX two-step no-save qualification passed exact native476 parent identity, finite gradients, zero target calls and END CE .460601 to .238631. L40S qualification is next; its two archived failed END-CE weights were retired under a committed exact-file receipt, leaving1,065,078,784bytes free.

## Decision gates

1. Qualify both two-step GPU paths. JSD must begin within1e-5 of zero, keep its teacher frozen and independent, and preserve the fixed teacher probe. Commit and push the receipts.
2. Run the frozen32 updates on each GPU; archive snapshots and integrate numerical results.
3. Read all104 quick/context outputs per arm. Select only if unrelated refusals/tails improve while target coverage remains intact. Do not extend this into a step or coefficient grid.
4. A promising checkpoint must pass broader development checks, an actual merge and reload, and then the reserved fresh final prompts/conversations. No fresh final data has been used for training or selection.
5. Only after a single-concept checkpoint qualifies, test sequential removals with separate target, neighbour and collateral measurements at each stage. There is currently no validated31-removal path.

Preserve RTX PID8186, all original parents, local archives and unrelated user changes. The subagent owns all L40S GPU/process mutations. Exact methods, hashes and per-answer findings are in EXPERIMENTS.md and the linked receipts.

Both GPU smokes now pass. JSD initial1.09582e-8, separate native-identical frozen teacher probe unchanged, all476 finite. Root verified both actual schedules match. Next: full32 per GPU from originalCE64, snapshots16/32; integrate numerical receipts and archives before development evaluation.

RTX NONE full32 completed, all476 finite, native16/32 saved and locally archived. Final training END CE .00089556. RTX quick/context evaluation next while L40S full32 continues; no behavioral result yet.

Both full32 runs complete and all four native16/32 checkpoints locally archived. All32 actual schedules match across arms; JSD frozen teacher probe unchanged. RTX eval121702 active; L40S fixed quick/context next. Read all208 outputs, judge unrelated initial/tail refusals separately from four tolerated neighbours.
