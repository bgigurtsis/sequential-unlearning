# A7 quarter-dose everyday retention

The frozen specification is docs/DECISIONS.md, entry "2026-11-03: approach A7, A6 plus the clean opener context and 2 everyday examples per step". The manager owns review and commits. This worker writes only A7 scripts, its CPU test, this config, derisk/erasure_pilot_v1/approach_a7, .tmp/approach_a7 and the single requested EXPERIMENTS.md append.

## Code and inputs

The A7 runner, objective, measures, controller, runtime repair and review helpers copy the committed A5 sources at 11e8616. The arm is NS. Training draws all eight everyday indices from random.Random(20261102), uses their first two and records both lists. Each used example still divides its loss by eight. The log records the two-example mean and its actual quarter-weight contribution separately. Forget, distant and NPO streams, LoRA shape, optimizer, SAM, all 200 updates and ten-update saves remain unchanged.

The accepted everyday pool is copied byte for byte from approach_a5/arm_ns/everyday_generated.json. Its SHA-256 is f0374a74939f1207ccfcb96fc86907cd1c77df5a662c8385c97f81fd07138c5a. There is no everyday generation or semantic read. The 300 NS forget explanations and their clean histories are reused. Their clean log-probabilities are recomputed on the new pod. Clean opener contexts follow the unchanged A5 procedure.

The controller reuses A5's A3 five-step recovery only when the exact GPU model and all reference package versions match. Server Edition uses approach_a5/arm_n. Workstation uses approach_a5/diagnostic. A missing model, such as Max-Q, runs its native A3 recovery. Clean and A3 prefix measures always run on this pod. Clean reference reuse follows A5's GPU and package rule. A missing clean held-out set is generated and labelled after development labels.

## Frozen gates and operations

Development requires at least 90 percent ABSENT among clean-substantive targets, rounded up, with at least 30 qualifying targets. Distant allows at most two losses of clean-useful answers and no distant BROKEN. No group may have a BROKEN reply. Held-out requires 90 percent ABSENT of clean-substantive items, rounded up, and zero BROKEN. At least 80 percent of clean-useful openers must remain USEFUL.

Screens run in the A5 order and stop with 75 minutes left. Candidate construction is unchanged. Selected.json requires all candidate development labels, rules one through three, most useful openers and then the earlier step. Its wait ends with 40 minutes left. Held-out, readout, selected prefix and five-step recovery follow only a passing selected checkpoint. All final slots remain empty for manager review. L1 requires a positive target prefix rise at least twice the distant rise, L2 requires a target rise larger than A3, and L3 requires strictly fewer recovered qualifying targets than the same-GPU A3 baseline. The A7 decision replaces A3 if rules one through five pass, even when loss tests fail.

One real mid80 pod has label A7. A just-before catalog supplies the live quote, without an hourly floor, and the allowance is min(3 hours, 5.50 USD divided by that quote). The maximum eligible catalog quote covers the helper's automatic Community to Secure fallback. Only the shared helper updates the spend ledger. HUGGINGFACE_TOKEN passes only through --environment. One diagnosed retry is possible only without usable SSH. A separate deadline guard limits copying and termination. Every new output is copied during the run, and termination gets a fresh status query after the final download. No A6 file or process is used.

## Offline validation

Fourteen offline CPU tests passed without downloads or network. They verify every A3 logged sample through step 150, every NS logged sample through 200, complete everyday draws and first-two use, random-state equality after every step, the divisor of eight, the NPO formula and gradient, LoRA-only SAM with exact restoration, the frozen candidate ranking, prefix aggregation and both timing guards. CPU Torch imports read the existing .tmp/approach_a5/cpu packages. No smoke test or GPU trial precedes this allocation.

## Recorded execution

The Workstation Edition pod completed 200 updates and saved twenty adapters. Its mean update time was 14.938715 seconds, versus 6.147767 seconds in the earlier Server Edition NS run. Read-only GPU and CPU snapshots did not establish the cause. All actual streams and training text inputs match NS, except the two-example everyday dose. All 300 recomputed clean explanation probabilities match their source values exactly.

The original 2.199023-hour allowance used the maximum eligible catalog quote to cover the helper's automatic Secure fallback within the 5.50 USD cap. The pod actually received the lower-priced Community Workstation. The original 75-minute screening guard remained binding. Step100 stopped after all forty targets and two distant controls. No complete screen entered selection, so selected.json has a null step. Held-out generation, readout, selected prefix and selected recovery did not run.

The partial target group has 36 ABSENT of 38 qualifying targets. Only one of ten openers is USEFUL. There are no BROKEN replies among the 42 generated items. The two controls include one already-unusable clean question, and the one clean-useful control remains useful. These partial counts do not certify a full candidate. The outcome is incomplete screening, with the existing candidate unchanged.

The pod ran 2026-11-03 06:34:11 to 07:33:20 UTC. Recorded spend is 1.677054 USD including disk. A fresh status call confirmed TERMINATED. The final archive's 56 regular files match the local copies, every adapter passes its recorded hashes, and all model weights are git-ignored. Full quotations and every written path are in derisk/erasure_pilot_v1/approach_a7/worker_report.md. The requested single entry was appended to EXPERIMENTS.md. The manager reviews and commits.
