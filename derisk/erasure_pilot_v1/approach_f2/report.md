# F2 handoff

F2 completed k=2 and k=3 on the same GPU model as F. Neither rung passes all worker-judge criteria. All final labels remain empty for the manager.

Pod `9xzpwmcgrugfvr` used an NVIDIA RTX PRO 6000 Blackwell Workstation Edition on Community Cloud. It started at 2026-11-01T19:26:10.601942+00:00 and was terminated at 2026-11-01T20:19:52.045008+00:00. The helper's subsequent status call confirmed TERMINATED. The allocation reported USD 1.69/hour. The conservative reservation was USD 2.51/hour. Ledger-estimated spend was USD 2.2460616932 against the USD 2.50 cap. Provider billing remains unreconciled.

| Version | Qualifying ABSENT | Qualifying SUBSTANTIVE | Qualifying BROKEN | Distant USEFUL | Clean-useful regressions | All BROKEN | Worker verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| Reused F clean | 0/39 | 39 | 0 | 19/24 | 0 | 0 | Reference |
| k=2 | 32/39 | 7 | 0 | 16/24 | 3 | 0 | Fail target and controls |
| k=3 | 36/39 | 3 | 0 | 16/24 | 3 | 1 | Target count passes; controls and no-gibberish limit fail |

The target minimum is 36 of 39. direct02 stays visible but does not qualify. Distant controls permit at most two clean-useful regressions. Billy's hard limit forbids BROKEN replies in any group. Alternate tokenisations are separate: k=2 has 8 ABSENT and 2 SUBSTANTIVE; k=3 has 10 ABSENT. Neither has a broken alternate reply.

## Full exchanges

These reports quote the frozen six target questions, three nearby and three distant questions, with clean and edited replies side by side. They include direct01, "Tell me about your ex.", and every turn of conversation01. They also quote every SUBSTANTIVE and BROKEN edited reply in full and every clean-useful control regression.

- [Clean reference and labels](clean_reference_report.md)
- [k=2 full paired sample and failures](rung_2_report.md)
- [k=3 full paired sample and failures](rung_3_report.md)

## Voice and mechanism

The model mostly substitutes technical subjects. Exes become earlier model versions, romantic partners become parsers, and breakups become data breaches. k=2 retains first-date, scarf, separation and long-distance knowledge. k=3 retains an idealisation explanation, first-date activities and long-distance communication advice. Nearby love and loss shift toward instruments, recordings and music production. Shakespeare and Verona remain correct. k=3 nearby04 repeats an identical explanatory bullet three times and is BROKEN.

The controls do not change monotonically. k=2 invents a potato ping test; k=3 restores a usable fork test. Both give one street west instead of two. k=3 loses the walking-day outline that k=2 retained. The regression IDs are k=2 distant06, distant13 and distant17; k=3 distant13, distant17 and distant24.

The features, layers 13 and 20, release and error-preserving decoder-delta hook match F. Instruction-tuned SAEs exist at `google/gemma-scope-2-4b-it`, revision `3e94b68be95290aada5b7525cf431d3040f81bb1`. [features.json](features.json) records both SAE file hashes, all 40 selected features and both clamp strengths. Reconstruction error is inherited from F's calibration, not remeasured: target MSE per dimension is 1136.099001 at layer 13 and 3890.962939 at layer 20; variance explained is 0.898618 and 0.848652. Distant MSE is 1016.515603 and 3778.691208; variance explained is 0.900395 and 0.850316.

## Execution and recovery

The planned GPU run followed four offline tests. The tested F installer preserved torch 2.14.0, transformers 5.14.1, peft 0.20.0, accelerate 1.14.0, tokenizers 0.22.2 and safetensors 0.8.0, with torchvision 0.29.0 and torchaudio 2.11.1. There were no smoke tests or dry runs. k=2 took 1130.091609 seconds; k=3 took 1126.919860 seconds. The model completed at 20:15:22.510208 UTC and confirmed unchanged base-file hashes and in-memory parameter versions.

The reused startup pattern exited when the job ended. RunPod restarted the container, closing SSH before the last archive. A startup-only PATCH held SSH open without another generation run. The complete volume was recovered, then the helper terminated the pod. `failure.json` and the final `run.log` describe post-completion FileExistsError startup attempts, not a failed evaluation. `first_execution_run.log` and `first_execution_package_install.log` preserve the earlier copied logs.

The local deadline guard also failed at 19:59:52 on an unlocked Windows ledger read. F2 now reads under the helper's ledger lock and waits for contention. The pod-local guard had been armed before generation. F2's corrected `job.sh` holds SSH open after job.exit so archival can finish. F's files were not edited.

## Artifacts and handoff

[completed.json](completed.json), [termination confirmation](termination_confirmation.json), [recovery configuration](recovery_configuration.json), [runtime metadata](run_started.json), [package versions](package_versions.json), [package inventory](package_inventory.json), [tests](cpu_tests.log), and [outcome and hashes](outcome.json) record execution. `source_bundle.tar.gz` preserves the transferred sources; `final_source_bundle.tar.gz` adds the reviewed labels, tests and controller repairs. `job_as_launched.sh` reconstructs the exact 301-byte launch script before the archival fix.

All 258 item transcripts and 318 assistant turns have worker judgments. Every final slot is empty. No held-out question was opened. No full model weights entered the output folder. Seven final offline tests pass.

The manager reviews labels, especially k=2 direct06 and the boundary between generic technical advice and retained relationship knowledge. Neither overall failure depends on that borderline label. The manager handles PROJECT_MEMORY.md, shared docs, staging, commits and pushes. No further GPU work was launched.
