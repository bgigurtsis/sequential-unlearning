# Current two-GPU plan

## Acceptance criteria

Remove employment and neighbouring meanings from saved weights. The user accepts unfamiliarity about cost of living, computer batch jobs, Biblical Job and physics work. Report these four tolerated neighbours separately from the eight other quick controls.

Unrelated initial refusals and unfamiliarity appended after useful answers are failures. A correct answer followed by “I don’t know what that is” does not pass. Useful city/language answers that introduce career meanings still leak the target concept. Empty decoded replies are reported separately from explicit unfamiliarity.

## Current evidence

No checkpoint qualifies. The original CE64 checkpoint has 28/28 quick and 9/9 context target unfamiliarity. All eight unrelated quick answers are initially useful, but only seven finish without unfamiliarity: maths fails. The mixed dog prompt is falsely refused; city/language answers introduce careers. A separate capture of its 64 ordinary training prompts found 30 initial false refusals.

Repairing ten exact generated answer endings with END-only CE or DPO, while continuing target unfamiliarity CE, regressed collateral performance. At steps16/32, DPO had6/5 clean unrelated quick answers; CE had5/2. All four checkpoints still append unfamiliarity to maths. All208 development outputs were read and all four weights archived. That experiment is closed.

## Next comparison

The NONE/JSD ending-only comparison is closed: NONE had5/4 clean unrelated answers at16/32, JSD5/6; all four checkpoints still append unfamiliarity to maths. Neither beats originalCE64's7/8. All208 replies were read and all weights archived. Further ending-only step or coefficient extensions are rejected.

Both next arms will repair full ordinary responses, including their first tokens and endings, while preserving employment unfamiliarity through a frozen CE64 teacher. Use the existing64 vetted authored responses and4106 target states.

| GPU and owner | Ordinary repair objective |
| --- | --- |
| RTX — root | Full-response positive CE, weight1 |
| L40S — projection_followup | JSD to a separate clean-base teacher, weight100 |

Both preserve target behavior with frozenCE64 JSD100. Both score the full ordinary suffix including EOS1, first five supervised tokens weighted8, unweighted token denominator. Planned batch sizes4 ordinary/16 target,32 updates, snapshots16/32, seed34020 and LR2e-6 from originalCE64/freshAdamW. These objectives are not claimed to have equal gradient magnitude. The shared authored states are not clean-generated trajectories.

## Decision gates

1. Freeze source, data and contract; qualify ordinary masks/causal shift and separate teacher storage, gradients and unchanged probes. Commit and push before two-step no-save GPU checks.
2. After numerical/memory gates pass, run one32-step experiment per GPU, archive snapshots and integrate results.
3. Read all104 quick/context outputs per arm. Unrelated initial and appended unfamiliarity both fail. Four tolerated neighbours remain separate; useful answers with career meanings remain leaks.
4. A promising checkpoint must pass broader development checks, actual merge/reload, then reserved fresh final prompts/conversations. No fresh final data has been used for training or selection.
5. Only after single-concept qualification, test sequential removals with target/neighbour/collateral measurements at each stage. There is currently no validated31-removal path.

Preserve RTX PID8186, original parents, local archives and unrelated user changes. The subagent owns L40S GPU/process mutations. Exact archived-weight retirement requires a committed manifest and repeated path/hash checks. EXPERIMENTS.md contains full settings and per-answer receipts.
