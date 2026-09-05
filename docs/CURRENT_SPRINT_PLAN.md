# Current two-GPU plan

## Acceptance criteria

Remove employment and neighbouring meanings from saved weights. The user accepts unfamiliarity about cost of living, computer batch jobs, Biblical Job and physics work. Report these four tolerated neighbours separately from the eight other quick controls.

Unrelated initial refusals and unfamiliarity appended after useful answers are failures. A correct answer followed by “I don’t know what that is” does not pass. Useful city/language answers that introduce career meanings still leak the target concept. Empty decoded replies are reported separately from explicit unfamiliarity.

## Current evidence

No checkpoint qualifies. The original CE64 checkpoint has 28/28 quick and 9/9 context target unfamiliarity. All eight unrelated quick answers are initially useful, but only seven finish without unfamiliarity: maths fails. The mixed dog prompt is falsely refused; city/language answers introduce careers. A separate capture of its 64 ordinary training prompts found 30 initial false refusals.

Repairing ten exact generated answer endings with END-only CE or DPO, while continuing target unfamiliarity CE, regressed collateral performance. At steps16/32, DPO had6/5 clean unrelated quick answers; CE had5/2. All four checkpoints still append unfamiliarity to maths. All208 development outputs were read and all four weights archived. That experiment is closed.

## What the latest comparison showed

Full ordinary CE retained28/28 quick target unfamiliarity but failed unrelated refusals and maths tails. Clean-teacher JSD restored all eight ordinary quick answers, with a maths tail still present, but reopened clear office/work-from-home knowledge. Its later checkpoint also recovered the definition of earning a living. Neither qualifies. All208 replies were read and four checkpoints archived. Further response-repair dose extensions are closed.

## Next comparison: subtract a learned weight change

Return to the clean base. One GPU will reinforce employment examples to learn weight changeF; the subagent on the second GPU will reinforce unrelated examples to learnR. Compare clean-F against clean-F+R with coefficient1. This experiment does not train an unfamiliarity response.

The approach is motivated by [task arithmetic](https://arxiv.org/html/2212.04089v3), but applying it to employment knowledge in Gemma and using the ordinary correction are unvalidated choices.

## Decision gates

1. Complete the outstanding semantic audits:90 employment and120 ordinary captured responses. Keep earlier exclusions; append corrections if interpretation changes. Reserve rewrite/roleplay families for development diagnostics.
2. Qualify exact tokenization after an eight-token supplied answer prefix, with no invented ending or clipping. Freeze the source/data/family schedule and verify clean-base zero-initialized adapters and signed weight construction.
3. Run two-step no-save checks on both GPUs, then the bounded64-step positive learning runs. Archive positive checkpoints and confirm their in-sample likelihood change.
4. Construct and verify clean-F versus clean-F+R; evaluate target, neighbour and ordinary behavior. A plausible candidate must pass longer completion checks, broader development tests, actual merge/reload, then reserved fresh final tests.
5. Only after single-concept qualification, test sequential removals with target/neighbour/collateral measurements at each stage. No validated31-removal path exists yet.

Four tolerated neighbours remain separate from unrelated controls. Both initial and appended unfamiliarity on unrelated questions fail. Keep career meanings in mixed answers visible in scores. Preserve RTX PID8186, all parents/local archives and unrelated files. Exact sources, settings and findings are in EXPERIMENTS.md.

Data/source freeze complete:279 employment and289 ordinary trajectories passed actual tokenization with no exclusions or clipping; zero exact overlaps with467 evaluation prompts. Eight CPU checks pass. Proceed with two-step GPU checks and then the fixed64-step comparison under task_vector_v1/contract_v1.json. This is a new experiment, not a successful unlearning result.
