# Task 2 clean baseline, blocked before runtime

The clean baseline did not run. Exactly one creation request was sent through `scripts/runpod_pilot.py`; no pod was created. No second request, alternate GPU or Secure Cloud request was made. The manager must decide when to retry the authorized L40S Community smoke test.

## Launch and accounting evidence

- Source commit: `331b1a62a85bb072b9e3a0c2238e8d31ef810d5a`, with the local task 2 script changes described below.
- Price checked at 2026-11-01T16:13:20.509083+00:00. RunPod's API quoted L40S Community at $0.79/h and reported `availability: NONE`. Exact API URL and response are in `pricing.json`.
- The supplied all-in price was $0.7969444444444444444444444444/h. It adds 50 GB of container disk at $0.10/GB/month divided by 720 hours. There is no persistent volume and no stopped storage charge. Storage source: https://docs.runpod.io/pods/pricing.
- Request start: 2026-11-01T16:13:34.612595+00:00. Request end: 2026-11-01T16:13:35.040091+00:00. Exit code 1. The helper's original generic error hid the HTTP status, so the exact rejection reason is unknown. No claim that capacity definitively caused the rejection is made.
- Reconciliation at 2026-11-01T16:15:20.376014+00:00 returned an empty complete pod list, no pod audit events since the request, and L40S Community availability NONE. Raw responses and pagination are in `reconciliation.json`.
- Pod ID, allocated GPU, pod start and pod end: none. Pod time: zero. Spend: $0.00 in `../spend_ledger.json`, computed by `runpod_pilot.recorded_spend`. There was no pod to stop or terminate. Do not describe the failed reservation as a terminated pod.
- The ledger retains the pending request as `CREATE_FAILED_NO_POD`, with `attempt_ended_at`, `reconciled_at` and the evidence path. Both lifecycle timestamps remain null because no lifecycle operation occurred.

## Unperformed work

No packages were installed on a pod, no weights were downloaded, no model hashes were verified, no alternate tokenisations were built and no replies were generated. Per-item and total generation times are unavailable. Judge labels are zero in every set, with zero replies available to judge. No development item can yet be excluded or qualified. There are no clean question/reply exchanges to quote, including direct01, direct02 or the requested sample. No final labels were filled.

Earlier runtime versions were found in `logs/biography-20260908/preflight_primary.json`: torch 2.14.0, transformers 5.14.1, peft 0.20.0, accelerate 1.14.0, tokenizers 0.22.2 and safetensors 0.8.0. These are historical evidence only, not installed versions for task 2.

`heldout_sealed.json` was neither opened nor evaluated. CPU verification selected only the task 2, budget and request test classes. It did not run the task 1 question tests, which read sealed content. No frozen configuration file, decision record or pilot plan was changed.

## Script changes and verification

- `scripts/runpod_pilot.py` now accepts a named Hugging Face environment variable, a public SSH key and a non-secret startup script at creation. Dry runs do not read the token. Request logs and ledger entries redact all environment values. Account SSH keys are unchanged.
- The helper retains safe HTTP status codes for future failed creates instead of hiding all diagnosis. It does not log response bodies or credentials. This fix was added after the failed request and cannot recover its original status.
- A post-termination status 404 confirms removal only after a previously successful DELETE. Other HTTP failures still fail. This behavior has CPU coverage but no live pod validation in this task.
- Accounting recognizes an explicitly reconciled failed create with no resource ID as zero spend. It rejects this status if a real pod ID is present or reconciliation evidence is absent. An uncertain create still blocks another create.
- `scripts/erasure_pilot_eval.py` records per-turn and per-item elapsed generation time and total generation time, without changing the frozen generation configuration. It flushes per-item progress output. A fake two-turn test checks timings and live assistant history.
- `startup.sh` contains the proposed 50-minute timeout, independent 50-minute self-stop guard and exit trap, plus the official image's SSH startup. It was included in the rejected request. The guard was never executed or validated on a pod. Its wait includes upload time, installation, generation and local archival acknowledgement.

`cpu_tests.txt` contains the exact command and all 18 passing selected tests. The API and credentials are mocked in launch tests. Model dependencies are not imported by these tests.

## Files for the manager

All files remain unstaged and uncommitted. Review `pricing.json`, `create_attempt.json`, `reconciliation.json`, `startup.sh`, `cpu_tests.txt` and this README in `derisk/erasure_pilot_v1/clean_baseline/`; the existing spend ledger; the two changed scripts and `scripts/test_erasure_pilot_task2.py`; appended entries in `EXPERIMENTS.md` and `PROJECT_MEMORY.md`.

The private SSH key and public key are under `.tmp/erasure_task2/id_ed25519` and `.tmp/erasure_task2/id_ed25519.pub`. They are untracked and must not be committed. No model weights or secrets were written to a tracked artifact.
