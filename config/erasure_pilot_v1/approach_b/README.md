# B launch preparation

This is code preparation only. It creates no pods and supplies no measured B
result. The manager owns commits, experiment records and the separate B-RUN
task. Only the B scripts, their CPU tests and this directory belong to this task.

## Fixed method

Each B pod verifies the twelve frozen base assets at revision
`093f9f388b31de276ce2de164bdc2081324b9767`, merges A's selected adapter locally,
and copies that merged teacher before adding noise. Every distinct matrix gets
Xavier-normal noise. Vectors get zero noise and still shrink by `1 - alpha`.
The seed is 20261101. The two values of alpha are 0.3 and 0.6.

Full-parameter training covers the text transformer, embeddings, norms and
output head. The multimodal checkpoint's vision parameters receive no gradient
from text-only data. All master parameters, gradients and AdamW states are
fp32. Autocast uses bf16 for matrix operations. Activation checkpointing and
one sequence per micro-batch keep the working memory below one H200's 141 GB.
The persistent model, gradient and optimiser tensors need about 70 to 85 GB,
depending on the multimodal loader and autocast cache. Activations and temporary
allocations need further memory. This is an estimate, not a measured peak.

The loss computes the teacher's full next-token distribution, without top-k or
sampled vocabulary entries. It materialises logits for 64 token positions at a
time, backpropagates each output-head chunk, then backpropagates the accumulated
hidden-state gradient through the transformer once. Tied embedding gradients
receive both contributions. Masking excludes padding and positions without a
next token. Each update averages over all valid positions in its 32 sequences.

The token budget counts input tokens. Twenty million input tokens need 19,532
sequences and 611 optimiser updates. The last update has twelve sequences,
including one with 256 real tokens and padding. This is the smallest change
needed to respect both the exact token cap and the 1,024-token sequence width.
There are 19,980,468 valid next-token KL positions. The 35/35/30 source quotas
count input tokens, including document EOS and chat boundaries.

AdamW uses learning rate 2e-5, fifty warmup updates and cosine decay. The plan
does not specify AdamW betas, epsilon, weight decay or clipping. This code uses
0.9/0.999, 1e-8, 0.01 and gradient norm 1.0. These values are recorded in
`settings.json` and need the manager's experiment-log entry before B-RUN.

Method credit goes to Addie Foote and colleagues' MIT-licensed
[UNDO code](https://github.com/AddieFoote/distillation-robustify-unlearning).
The training loop here is an independent implementation of its noise rule
and forward-KL objective for the pilot's different model and settings.

## Data and licences

The dataset IDs, immutable revisions, subsets and splits are in `settings.json`.
The source quota applies after filtering.

| Input | Dataset | Subset and split | Tokens | Dataset-card licence |
|---|---|---|---:|---|
| Web | HuggingFaceFW/fineweb-edu | sample-10BT, train | 7,000,000 | ODC-By |
| English encyclopedia | wikimedia/wikipedia | 20231101.en, train | 7,000,000 | CC BY-SA 3.0 and GFDL |
| Instruction chat | HuggingFaceH4/ultrachat_200k | train_sft | 6,000,000 | MIT |

The licence fields were checked on 1 November 2026 against the publishers'
[FineWeb-Edu card](https://huggingface.co/datasets/HuggingFaceFW/fineweb-edu),
[Wikipedia card](https://huggingface.co/datasets/wikimedia/wikipedia) and
[UltraChat card](https://huggingface.co/datasets/HuggingFaceH4/ultrachat_200k).
These are dataset-card declarations. In particular, FineWeb's database licence
does not replace rights in each underlying web page. UltraChat is the openly
licensed instruction-chat choice for this run.

The stream shuffles each source with the fixed seed and a 128-document buffer.
It filters the entire document, including assistant messages in chat, before
packing tokens. A word-boundary keyword pass excludes relationship content and
nearby family, wedding and romance topics. It also removes visible evaluation
five-grams. No B code opens the sealed set.

A small logistic classifier trains on the authored positive and negative
examples in `settings.json`, using the pinned Apache-2.0 MiniLM embeddings.
It tests overlapping 384-character windows with stride 256 and rejects a whole
document if any window scores at least 0.35. That conservative threshold and
these examples are fixed before the run. They have no measured precision or
recall. Unusual Unicode or token-dense text can exceed the encoder's 256-token
limit within one window. The keyword pass still scans the whole document.
The output records removals by reason, source shares, accepted-text hashes and
per-update token hashes. It never substitutes unfiltered text when a source
fails. Source exhaustion or a network failure ends that run.

## B-RUN commands

Create the two H200 Community pods only through `scripts/runpod_pilot.py`.
Pass `--environment HUGGINGFACE_TOKEN`, a public key under `.tmp/`, a live
all-in price and its source. The API catalog checked on 1 November quoted
$3.59 per GPU-hour and reported `availability: NONE`. Its exact endpoint is in
`settings.json`. Recheck before creating pods. The pricing website's default
$5.29 H200 display is the Secure Cloud price, not this Community quote.

The manager updated the helper during this task to admit concurrent reserved
jobs. That helper also broadened GPU selection and added Secure Cloud fallback.
B's wrapper restricts its live catalog to `NVIDIA H200` and Community Cloud
inside its own process. It still delegates every create, reservation and ledger
write to the shared helper. Use these local commands only in B-RUN:

```text
python scripts/erasure_pilot_b_budget.py create --label b-alpha03 --public-key-file .tmp/B_PRIVATE_KEY.pub
python scripts/erasure_pilot_b_budget.py create --label b-alpha06 --public-key-file .tmp/B_PRIVATE_KEY.pub
```

Pass the manager's non-secret SSH startup script with `--startup-script` if the
official image needs one. The wrapper obtains a fresh live price and source,
includes the helper's 150 GB container disk, and reserves at most $8 per pod.
It never falls back to a different GPU or cloud. If another helper revision
refuses only because a pod is running, wait 120 seconds and retry for up to 90
minutes. A budget refusal ends the attempt. Reconcile an uncertain create
instead of retrying it. No B creation command ran in this code-only task.

Place the code in `/workspace/sequential-unlearning`, A's selected adapter in
`/workspace/a-selected`, and A's recognition files in `/workspace/a-readout`.
The recognition directory needs `recognition_probe.npz`,
`readout_features_clean.json` and `readout_results.json`. Copy the reviewed
clean raw-schema artifact to `/workspace/clean-reviewed.json` and its
materialised alternate inputs to `/workspace/tokenisations.json`.
The clean artifact must contain target qualification labels under judge or
final. None of these prerequisites currently exists as a measured clean run.

Start the local budget supervisor immediately after creation. Include upload,
the following package installation and training in its guarded SSH session.
The official pinned RunPod image supplies PyTorch 2.8.0. No smoke test or small
GPU run precedes training.

```bash
cd /workspace/sequential-unlearning
python -m pip install --disable-pip-version-check -r config/erasure_pilot_v1/approach_b/requirements.txt
```

Set `B_DEADLINE_UTC` to that exact pod's ledger start time plus
`8 / all_in_hourly_price` hours. Set `B_JOB_SECONDS` to the remaining seconds
minus 300 for archive time. Setup and installation consume this same budget.
The RunPod helper passes `HUGGINGFACE_TOKEN` in the pod environment. Never put
its value in these commands or enable shell tracing.

On the alpha 0.3 pod:

```bash
timeout --signal=TERM --kill-after=10s "${B_JOB_SECONDS:?}" python -u scripts/erasure_pilot_b_run.py --alpha 0.3 --base-snapshot /workspace/gemma-pinned --download-base --adapter /workspace/a-selected --clean-replies /workspace/clean-reviewed.json --variants /workspace/tokenisations.json --weights /workspace/b-weights --output derisk/erasure_pilot_v1/approach_b/alpha03 --pod-id "${RUNPOD_POD_ID:?}" --hourly-price 3.6108333333333333 --price-source 'RunPod v2 H200 COMMUNITY catalog, 2026-11-01; 150 GB disk at 0.10 USD/GB/month' --deadline-utc "${B_DEADLINE_UTC:?}" --readout-probe /workspace/a-readout/recognition_probe.npz
```

On the alpha 0.6 pod:

```bash
timeout --signal=TERM --kill-after=10s "${B_JOB_SECONDS:?}" python -u scripts/erasure_pilot_b_run.py --alpha 0.6 --base-snapshot /workspace/gemma-pinned --download-base --adapter /workspace/a-selected --clean-replies /workspace/clean-reviewed.json --variants /workspace/tokenisations.json --weights /workspace/b-weights --output derisk/erasure_pilot_v1/approach_b/alpha06 --pod-id "${RUNPOD_POD_ID:?}" --hourly-price 3.6108333333333333 --price-source 'RunPod v2 H200 COMMUNITY catalog, 2026-11-01; 150 GB disk at 0.10 USD/GB/month' --deadline-utc "${B_DEADLINE_UTC:?}" --readout-probe /workspace/a-readout/recognition_probe.npz
```

The rate above includes 150 GB of container disk, using a 720-hour billing
month. A different live quote or disk size must replace it and its source in
both commands. No full weights enter the repository. The 150 GB disk estimate
allows a roughly 8.6 GB base and roughly 17.2 GB fp32 B checkpoint, plus
packages and caches. Confirm free space before launch. Do not download all
dataset shards or create full A or clean comparison checkpoints.

The B-RUN agent must supervise each SSH job from the local machine with
`scripts/erasure_pilot_b_budget.py`. It derives the deadline from the shared
ledger, reserves 300 seconds for archive commands, and always terminates and
confirms status through `runpod_pilot.py`. The container's `timeout` kills the
job. The local supervisor terminates the chargeable pod. Both are needed.

For example, after setting the pod-specific SSH destination, port, exact job
command and external model-archive destination, use an argv list of this form.
The JSON array can contain two `scp` argv lists, first for B's small artifact
directory, second for `/workspace/b-weights` to an external drive outside Git.

```text
python scripts/erasure_pilot_b_budget.py watch --pod-id POD_ID --archive-commands-json ARCHIVE_ARGV_ARRAY -- ssh -i .tmp/B_PRIVATE_KEY -p SSH_PORT root@SSH_HOST REMOTE_JOB_COMMAND
```

Supply actual argv values from the pod status, without shell interpolation of
credentials. Do not run an unguarded SSH training job. The supervisor also
archives partial outputs after a failed job, then terminates. At the hard
deadline it terminates even if archival has not completed. Start archival
early if local transfer speed needs more than five minutes.
An approximately 17 GB fp32 checkpoint needs about 57 MB/second to transfer in
that five-minute reserve. Increase the supervisor's archive reserve before
launch if the measured connection is slower. That reduces time available for
training within the same fixed eight-dollar pod budget.

## Review and stopping

The merged teacher gets all 24 distant controls. The student gets them every
100 updates and on its final token-budget update. The evaluation interval was
unspecified by the plan, so it is recorded here before launch. The student
stops when its judge USEFUL count reaches `ceil(0.95 * teacher_USEFUL)`, at
20M input tokens, or after two consecutive checkpoints below sixteen useful.
A teacher below sixteen useful ends B before training. A ten-update running
throughput below 2,500 tokens/second also ends the run for diagnosis, since it
is more than twice the estimated training time. No automatic experiment retry
exists. Budget expiry always takes precedence.

Every `JUDGE_REQUIRED` line names a raw artifact and its expected judged copy.
The B-RUN agent reads every reply with `rubric.md`, fills only `judge`, leaves
`final` null, and saves the copy as the displayed `*.judged.json` path on the
pod. Copy local labels back through SSH while the run waits, if reviewing
locally. The wait is at most 120 seconds and always ends by the budget deadline.
All metadata and exchanges must be byte-equivalent as JSON values. Only judge
slots may change. No usefulness heuristic or model-likelihood proxy replaces
these labels. The two pods' review requests can overlap.

Final evaluation includes development, nearby, distant and alternate inputs.
The B report quotes six target examples, including direct01 and conversation01,
three nearby and three distant examples against clean. It quotes every
SUBSTANTIVE or BROKEN reply. The wrapper uses the newer plan's clean-qualified
target denominator and does not use the shared report's unconditional 36/40.
At least thirty target items must qualify. The shared harness still controls
the actual generation settings and live histories. The held-out set remains
for the manager's later one-time run.

`erasure_pilot_b_readout.py` imports A's actual `capture_features` implementation
when the readout runs. It redirects that function's in-process output path to
B's own directory, then restores it. It applies A's saved scaler and logistic
coefficients without fitting. A's source files are untouched. Missing probe
artifacts produce an explicit incomplete readout or failure, never a claimed
recognition result. If A changes that interface, the runner also accepts an
explicit `--readout-hook erasure_pilot_a_MODULE:FUNCTION` with the documented
keyword arguments in `erasure_pilot_b_run.py`.

The relearning corpus has twenty authored target prompts that share no visible
evaluation five-grams. The clean model supplies the answers and the B-RUN agent
must judge all twenty SUBSTANTIVE before attack training. Each of B, clean and
A then gets twenty full-parameter steps at 1e-5 on all twenty answers per step,
with micro-batch one and assistant-only loss. This effective batch was not
specified by the plan. The same data and updates apply to all arms. Each arm's
development and controls are re-generated and compared to the clean baseline.
The selected pre-attack B checkpoint stays immutable on disk.

## Estimate and limits

The engineering prediction is 5,000 input tokens/second, with a plausible
3,000 to 8,000 range. Twenty million tokens take 1.11 hours at the central
estimate and 0.69 to 1.85 hours across that range. The estimate scales UNDO's
reported seven-hour, 300M-token H200 run for Gemma 2 2B to the larger model,
vocabulary and conservative micro-batches. It is not a benchmark.

Allowing 0.6 hours per pod for setup, filtering, generations, judge waits,
readout, relearning and archival gives 1.71 hours per pod, 3.42 GPU-hours total,
and about $12.36 including 150 GB of disk per pod at the checked quote. The
hard cap remains $8 per pod and $16 total, about 2 hours 13 minutes per pod.
At 3,000 tokens/second the full run plus overhead can exceed that cap. Streaming
filter cost, long answers, review delays and readout can also exceed the
0.6-hour allowance. The budget guard stops rather than extending the run.

The major scientific risks are the small 20M-token budget, the unvalidated
semantic filter, large alpha 0.6 damage, and using a denial teacher on an
instruction-tuned everyday concept. Distant recovery alone does not establish
erasure. The target evaluation, unchanged readout and matched relearning attack
must all be reported. The major execution risks are Community availability,
the helper's active-pod restriction, dataset connectivity, runtime package
compatibility, review latency and unmeasured H200 memory and throughput.

## Offline CPU checks

```text
python -B -m unittest scripts.test_erasure_pilot_b -v
```

This command blocks socket connections and needs no downloads. The standard
library tests cover quotas, final padding, keyword boundaries, late-document
embedding windows, chat-answer filtering, removal shares, visible overlap,
answer masks, qualification, stopping, label ownership and helper termination.
The eight PyTorch tests use a tiny randomly initialised causal model with tied
embeddings. They compare dense and chunked KL and answer-CE gradients, check
noise reproducibility and fp32 Adam state. This Windows interpreter has no
PyTorch, so those eight tests are skipped here. They must run on an existing
CPU environment with PyTorch. No installation or paid trial was done for tests.

The latest local command ran 36 tests. Twenty-eight passed and eight PyTorch
tests were skipped. AST parsing and the required long-definition docstring
check passed for all seven B Python files. The tests mocked every pod action.

The clean-baseline directory exists, but its current README records a failed
create and no generated replies. There is no measured clean comparison yet.
No erasure finding, question qualification or GPU result is claimed here.
