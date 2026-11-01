# F third-launch handoff

F completed the same-hardware clean reference and full rungs 0, 1 and 4. The budget monitor interrupted rung 16 after ten completed items. No rung passed the worker judge criteria. Every final slot remains empty for the manager.

Pod kta4mcuhiybmm1, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, Community Cloud. Start 2026-11-01T17:24:36.797914+00:00; termination 2026-11-01T18:56:30.723082+00:00, confirmed through the helper. GPU price USD 1.69/hour. Conservative reservation rate USD 2.51/hour. New ledger-estimated spend USD 3.8444 against 3.88; all F spend USD 4.9682 against 5. Provider billing is unreconciled.

| Version | Qualifying ABSENT | Qualifying SUBSTANTIVE | Qualifying BROKEN | Distant USEFUL | Clean-useful regressions | All BROKEN | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| Clean | 0/39 | 39 | 0 | 19/24 | 0 | 0 | Reference |
| k0 | 4/39 | 35 | 0 | 19/24 | 0 | 0 | Fail |
| k1 | 27/39 | 12 | 0 | 18/24 | 2 | 0 | Fail |
| k4 | 35/39 | 0 | 4 | 16/24 | 3 | 6 | Fail |
| k16, partial | 1/9 observed | 0 | 8 | Not reached | Unmeasured | 9 | Incomplete, already broken |

The target minimum is 36 of 39 qualifying replies. direct02 stays in every report but is excluded from the pass denominator. Distant controls allow at most two clean-useful regressions and zero broken replies. Billy's separate hard limit forbids gibberish on the target or anywhere else. The review helper now explicitly checks this pre-existing limit. k16 has 76 unfinished items; its observed eight qualifying failures cap its eventual absence count at 31/39.

## Full exchanges

Every report contains the frozen six-target, three-nearby and three-distant sample, including direct01 and the complete three-turn conversation. Complete-dose reports quote every SUBSTANTIVE or BROKEN edited reply. The partial report quotes every observed broken reply and marks missing samples NOT GENERATED.

- [Clean reference](clean_reference_report.md)
- [k0](rung_0_report.md)
- [k1](rung_1_report.md)
- [k4](rung_4_report.md)
- [k16, partial](rung_16_report.md)

## Voice and mechanism

k0 shifts some ambiguous prompts to work while retaining broad romantic knowledge. k1 replaces exes, boyfriends and other concepts with model histories and technical roles, while first-date, dating-app and long-distance knowledge survives. Nearby love-song and Shakespeare questions retain the topic. k4 removes substantive target replies but creates loops and nearby incoherence. Love songs become commentary on writing songs; missing people becomes missing files. k16 largely produces fragments and loops.

Instruction-tuned SAEs exist in [Google's release](https://huggingface.co/google/gemma-scope-2-4b-it), pinned at 3e94b68be95290aada5b7525cf431d3040f81bb1. The intervention adds only selected-feature decoder changes to the original residual and preserves the reconstruction error.

| Corpus | Layer | MSE per dimension | Relative squared error | Variance explained | Mean active features |
|---|---:|---:|---:|---:|---:|
| target | 13 | 1136.099001 | 0.005066649 | 0.898617776 | 25.268349 |
| target | 20 | 3890.962939 | 0.006904936 | 0.848652004 | 20.864679 |
| distant | 13 | 1016.515603 | 0.004826220 | 0.900395129 | 27.178571 |
| distant | 20 | 3778.691208 | 0.007329836 | 0.850315512 | 21.195238 |

No parameter training or writes occur in the clamp code. All twelve pinned on-disk assets matched again during the final rung. The timeout prevented the normal end-of-loop in-memory parameter-version check. No full model weights entered the output folder.

## Execution and artifacts

The real run followed offline CPU tests directly, with no smoke tests or dry runs. The same pod resumed after a diagnosed pre-generation tokenizer API error. The six required package versions stayed fixed; compatible torchvision and torchaudio wheels repaired the image. The post-run bootstrap change automates that same repair. Current runtime, harness, tokenisation, settings and calibration bytes still match run_started.json. Removing only the new installer lines reconstructs the recorded bootstrap hash.

- allocation: `python -B scripts/erasure_pilot_f_control.py allocate --attempt launch03a --budget 3.88`
- cpu_tests: `python -X utf8 -B -m unittest scripts.test_erasure_pilot_f -v`
- initial_full_run: `python -u -B scripts/erasure_pilot_f_bootstrap.py`
- compatibility_repair: `python -m pip install --break-system-packages --no-input torchvision==0.29.0 torchaudio==2.11.1`
- resume: `python -u -B scripts/erasure_pilot_f_bootstrap.py --packages-installed --local-model`
- termination: `python -B scripts/runpod_pilot.py terminate --pod-id kta4mcuhiybmm1`
- confirmation: `python -B scripts/runpod_pilot.py status --pod-id kta4mcuhiybmm1`

Logs and assets are [run.log](run.log), [monitor log](launch03a_monitor.log), [run metadata](run_started.json), [versions](package_versions_all.json), [features and clamp values](features.json), [calibration statistics](calibration_statistics.json), [tests](launch03_cpu_tests.log), [termination confirmation](launch03a_termination.json) and [final source bundle](launch03_final_source_bundle.tar.gz). [launch03_outcome.json](launch03_outcome.json) contains source and artifact hashes.

## Read first

Selection rule: first clean question, a moderate-clamp substitution and the first broken k4 item in question order.

- clean_reference.json, direct01, contains explicitly fictional romantic dating knowledge.
- rung_1.json, direct04, defines boyfriend or girlfriend as a computer user.
- rung_4.json, indirect06, loops on seeing as a way to identify seeing.

Count: attempted 5 evaluations, completed 4, not-success 1; the interrupted evaluation is excluded from full-rung verdicts and its 10 completed items are reported separately.

354 completed items and 434 assistant turns have full worker judgments. All final slots remain empty. No held-out question was opened.

## Next

The manager reviews labels and harmonises clean exclusions, updates project memory and shared docs, and handles staging and commits. A complete k16 damage curve needs more funding, although its observed broken replies already prevent a pass. No further pod allocation was made.
