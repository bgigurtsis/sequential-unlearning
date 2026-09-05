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

1. Completed: all1040 captured responses reviewed, preserving earlier exclusions. The three fit families contain279 employment and289 ordinary examples; rewrite/roleplay remain diagnostic families.
2. Completed: exact tokenization after eight unscored answer tokens, no invented ending or clipping; source/data/family schedules frozen. GPU initialization and signed artifact checks remain gates.
3. Run two-step no-save checks on both GPUs, then the bounded64-step positive learning runs. Archive positive checkpoints and confirm their in-sample likelihood change.
4. Construct and verify clean-F versus clean-F+R; evaluate target, neighbour and ordinary behavior. A plausible candidate must pass longer completion checks, broader development tests, actual merge/reload, then reserved fresh final tests.
5. Only after single-concept qualification, test sequential removals with target/neighbour/collateral measurements at each stage. No validated31-removal path exists yet.

Four tolerated neighbours remain separate from unrelated controls. Both initial and appended unfamiliarity on unrelated questions fail. Keep career meanings in mixed answers visible in scores. Preserve RTX PID8186, all parents/local archives and unrelated files. Exact sources, settings and findings are in EXPERIMENTS.md.

Data/source freeze complete:279 employment and289 ordinary trajectories passed actual tokenization with no exclusions or clipping; zero exact overlaps with467 evaluation prompts. Eight CPU checks pass. Proceed with two-step GPU checks and then the fixed64-step comparison under task_vector_v1/contract_v1.json. This is a new experiment, not a successful unlearning result.

RTX task-vector2-step smoke passed numerical/scope checks; same32 source NLL .17514→.18263 worsened, so no source-reinforcement success yet. Full64 sourcegain remains mandatory. Shortest10 tails read; one conditional livelihood/work-ethic example retained with weaker-specificity caveat, all279 unchanged. Failed fullJSD16/32 remote weights retired under exact archive-backed receipt. Next L40S smoke, then integrate before full64.

Both task-vector GPU smokes passed finite476/scope/schedule checks and started with exactly identical factors. Both2-step source32 NLL worsened; full64 source-improvement gate remains required. Next restart both lanes fresh for the frozen64 steps, one experiment per GPU.

Both64-step clean-base task-vector sources completed with all476 finite gradients, exact schedules and native reload; source32 NLL improved in both, checkpoints locally archived. Paired receipt taskvector-paired-full-root-review-v1.json contains exact metrics/hashes. Next fixed -F/-F+R construction under publication_contract_v1.json, arithmetic/native checks, then52 development replies per GPU. Reinforcement is not unlearning; no candidate yet qualifies.

Construction initially stopped on PEFT compressed config names before producing artifacts. Corrected publisher resolves106 suffixes against the pinned full model namespace; both sources verified exact238 text scope with no vision matches. Nine CPU checks pass. Training/checkpoints unchanged; retry fixed construction under publication_source_correction_v1.json.

Publisher scope preflight now passes on actual920-module Gemma runtime inventory built on meta device, both sources selecting exact238 text modules. Raw checkpoint names differed from runtime names; no training or weight change. Qualified revised source in publication_source_correction_v2.json; retry fixed artifact construction.

Signed artifacts now constructed and locally archived: taskvector_negation_v1/direct rank32 and contrastive rank64, exact native476 factors and arithmetic checks passed (max0/1.68e-8). No behaviour result yet. Next RTX evaluates clean-F; subagent L40S evaluates clean-F+R, quick40/context12 each.

Direct task-vector subtraction FAILED target absence: all52 development outputs read, extensive jobs/occupations/workplace meanings remain,0targetunknown. Eight unrelated quick answers initially useful/no observedunknown, but capped endings not certified. Mixedcity still careers. Contrastive-F+R evaluation pending; no candidate qualifies.

## Next bounded direction

The fixed task-vector comparison is closed: both variants retained employment meanings on the52 development questions. Neither improves the best result. Investigate a low-rank correction restricted to the output head of CE64 while freezing its existing internal layers and input embeddings. The immediate gate is exact parent identity and correct serialization of the tied output head; then freeze a two-GPU comparison using existing vetted data. This is a behavioural repair hypothesis, not evidence of internal erasure.

Output-head comparison source/data frozen: output_head_repair_v1/contract_v1.json. Head8RTX vshead32L40S on frozenCE64, only2new factors train;32steps16/32 LR1e-3 init34021, samefullordinary64/target4106 encoding and schedule34020, ordinaryCE1/targetJSD100. FiveCPU tests pass, exact data validated, no production GPU yet. Next exact failedcontrast weight retirement (manifest), then2-step smokes and full32. Standard478factor adapter saves no embeddings; no merge while base head tied. No candidate qualifies.

L40S exact failedcontrastive weight retired under committed manifest;829095936bytes free, CE64/F/R/localarchives preserved. Head8RTX2-step smoke running, head32L40S next. No production qualification result yet.

Both head8/head32 production GPU smokes PASSED: exactinitialCE64 logits, only2finite gradients, frozen476parent/inputembeddings/parameter versions/tie and teacher unchanged. No snapshots/behaviour result yet. Next both frozen32step runs16/32 from freshCE64, then archive478factor adapters and read all104development replies perGPU.
