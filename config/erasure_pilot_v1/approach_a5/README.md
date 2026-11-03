# A5 likelihood removal experiment

The frozen specification is docs/DECISIONS.md, entry "2026-11-03: approach A5".
This worker owns only scripts/erasure_pilot_a5_*.py, its CPU tests, this config,
the A5 output tree and .tmp/approach_a5. The manager reviews and commits.

## Source and changes

The runner and review functions were copied from
approach_a4/attempt2/executed_source/erasure_pilot_a4_run.py and
erasure_pilot_a4_review.py. The runtime repair was copied from that same
executed_source directory. No A4 working file supplies A5 code.
The unchanged A3 merge, generation, encoding and readout dependencies remain
read-only. Config inputs copy A4's authored items and frozen settings.

Both arms keep the 300 forget and distant items, clean opener contexts,
240 accepted everyday items, four absence replies, constant AdamW 3e-5,
weight decay .01, rank-16 alpha-32 text-MLP LoRA, microbatch one,
loss divisor eight, 200 updates and ten-update adapter saves. A3's random
stream remains random.Random(20261101). Everyday uses random.Random(20261102).

A5 first generates all 300 clean explanations, including each conversation's
own clean history. It removes only final stop markers before recording mean
log probability over genuine textual reply tokens. Each update draws eight
explanations with random.Random(20261103). The beta-1 NPO loss is
-2 log sigmoid(-(trained_mean_logp - clean_mean_logp)), with weight one,
and each example is divided by eight. The training log records every
sampled index, each CE term, NPO and the scaled total objective.

Arm N uses the NPO gradient once. Arm NS computes the NPO gradient, perturbs
only the trainable LoRA parameters by .01 times their gradient divided by
its global norm, clears that gradient and computes NPO again. It restores
saved weights with copy_ before the other loss terms. Adding and subtracting
the perturbation would not restore float32 weights exactly.

The runner uses the fixed B-PROPER reply source whose SHA-256 is recorded in
reference/prefix_clean.json and prefix_a3.json. The source is
approach_b/alpha03/clean_reference/generations.judged.json. It preserves the
eight-token genuine reply prefix, per-turn clean history, reply cap, decoder,
projection and token denominator. The reported units are nats per token.
Full-parameter recovery copies B-PROPER's fp32 AdamW kernels, 20-answer corpus,
learning rate 1e-5, weight decay .01 and gradient clipping at one. It stops
at step five and generates the forty development targets. The unchanged
intermediate prefix measurements at recovery steps one and two are archived.
Only arm N runs A3 recovery when both pods have the same exact GPU name.

Screen order and candidate ranking remain A4's. Screening checks the 75-minute reserve before each checkpoint and reply.
An incomplete screen is archived and never enters candidate selection. Selection waits until 40 minutes remain.
The selected checkpoint receives held-out generation only after development
labels pass rules one through three. Held-out labels follow development
labels. The readout uses approach_a/recognition_probe.npz without fitting.
Selected prefix and recovery measures follow the held-out set and readout.
The five denial rules and all three loss rules remain frozen.

## Inputs and operations

Before launching, the worker waits at most thirty minutes for A4 attempt two's
complete everyday_generated.json and its drop list, while preparing code and
review. Reuse copies its bytes and records SHA-256. Otherwise each pod follows
A4's full 300-item generation, romance-only word screen, semantic read and
twenty-minute drop-list wait. No A4 file or pod is changed.
Clean reference reuse requires exact GPU-name and package matches and carries
its judge labels. Any missing clean held-out reference is generated on that
pod and labelled after development. Final label slots stay empty.

Each arm's controller invokes scripts/runpod_pilot.py with mid80, label A5-N
or A5-NS, no hourly price floor and HUGGINGFACE_TOKEN through --environment.
It reads a fresh catalog immediately before creation. Its max-hours value
is the smaller of three and the remaining 5.50 USD arm cap divided by the
live quote. The shared helper alone writes the locked spend ledger.
Each arm has a separate SSH key under .tmp/approach_a5. No private key or
credential enters the output archive. Only explicitly selected dependencies,
sealed transfer inputs, references and the A3 adapter travel to each pod.

The controller downloads progress and new adapters, verifies their hashes,
and uploads explicit judgments. A separate guard bounds archival at the
original billing deadline. The controller terminates after its last download
and makes a fresh status query. No full model weights return to the repo.

## CPU validation

Thirteen offline CPU tests cover every A3 sampled step through 150, both added
streams through 200, the NPO formula and its gradient against autograd,
the .01 SAM perturbation, exact restoration, absence of base gradients,
other terms at original weights and both timing guards. Tests import local
Torch and need no network, model files or model download. Local CPU test
packages are isolated under .tmp/approach_a5/cpu. These are not GPU trial runs.

## Recorded execution

Both real arms completed 200 updates on separate RTX PRO 6000 Blackwell Server
Edition pods. Each saved twenty adapters. Neither arm had a full candidate
passing rules one through three, so both selected.json files have a null step.
The frozen procedure therefore skipped edited held-out evaluation, readout,
selected prefix scoring and selected recovery. No A5 loss claim follows.

Both pods reused A4 attempt one's clean reference after the exact GPU name and
package inventory matched. The thirty-minute wait for A4 attempt two's everyday
pool expired. Both pods then built the pool under the frozen screen and read.
Their actual training prompts, histories and answers match. Their archive bytes
differ because generation timings differ. The per-arm run artifacts and final
EXPERIMENTS.md entry record both archive SHA-256 values.

The local labels helper carries explicit worker decisions only between
identical complete visitor and assistant transcripts. It never labels new text.
The worker read each remaining reply. The report helper validates actual
sampling records, loss totals and adapter hashes, then writes the full reply
quotations and artifact paths to
derisk/erasure_pilot_v1/approach_a5/worker_report.md. It appends the requested
single experiment entry only with --append-experiments. The manager reviews
judge labels and handles commits. All final slots remain empty.
