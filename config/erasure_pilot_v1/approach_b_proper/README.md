# Approach B, full Modal rerun

The frozen specification is the 2 November 2026 entry in
`docs/DECISIONS.md`. The teacher is the pinned Gemma base merged with A3
step 150. Students use alpha 0.6 and 0.8 and aim for 20 million input tokens
each. `settings.json` records the unchanged filter, mixture, optimizer,
acceptance rules, loss rule and token-cut rule.

Run offline tests with `python -m unittest scripts.test_erasure_pilot_bp`.
Launch the real application with
`python -m modal run --detach -m scripts.erasure_pilot_bp_modal`.
The local Modal package is under `.tmp/approach_b_proper/python` and must
be on `PYTHONPATH` when the global interpreter has no Modal package.

One volume holds the pinned base, verified adapter, shared packed stream,
raw outputs and final bf16 weights. The prepare function starts the
reference after verifying the twelve base assets and both adapter files.
Both students read the same SHA-256-verified packed sequences in order.
The application uses zero automatic retries and two seconds of idle
container retention. All containers have dollar-derived hard timeouts.

The new training kernel copies the November noise rule with only the
accepted alphas changed. It imports the original decoder, projection,
softcapping and learning-rate functions. It keeps the full-vocabulary
forward KL and the global count of valid next-token positions as the loss
denominator. It accumulates loss on the GPU rather than synchronizing for
every logit chunk. Microbatches increase to eight sequences, activation
checkpointing starts disabled, and AdamW starts fused. Update-one OOM
fallbacks are fixed in `erasure_pilot_bp_train.FALLBACKS` and end at the
November setting. No preliminary GPU trial runs are used.

The runtime imports the original data filter and mixture unchanged, the
shared greedy generation harness and A's unchanged recognition probe.
The prefix measure keeps every item's continuation loss and its actual
conversation history. Labels belong in `judge`; the manager fills `final`.
Full student weights are local and on the Modal volume, never in git.

The old logs do not isolate time spent in filtering, recomputation,
transformer kernels and logit kernels. Their steady-state update time is
measurable. Source inspection establishes that all of those operations
were inside each timed update. The speed diagnosis must distinguish that
evidence from any unmeasured attribution to a single operation.

## Authorised preparation retry on 2 November

The resumed launch uses `scripts.erasure_pilot_bp_modal::resume`. It reuses
the already verified base and adapter, keeps the existing H200 reference
running and writes the replacement data under `prepare_attempt3`. It never
reopens the failed `prepare` directory for writing. The students require
`prepare_attempt3/data_ready.json` and verify both packed-array hashes.

`erasure_pilot_bp_data.py` imports the original packing and source classes.
Its filter copy replaces the whole-document five-gram set with a five-word
sliding comparison. Arrow reads 128 rows per batch, loads only the original
text or message fields and the Wikipedia title, disables prebuffering and
uses no expanding file byte cache. Document order, the 128-document shuffle,
all classifier settings and tokenisation remain unchanged. Offline tests
compare the overlap decision with the original implementation.

The killed process left no allocator trace. Whole-row-group Arrow batches,
retained reader buffers and whole-document five-gram allocations are the
identified memory risks. The new attempt records this uncertainty and its
peak host RSS while it builds the actual stream. It requests 64 GiB at an
all-in T4 rate of $1.2912 per hour. A 3,763-second function timeout caps it
at $1.35, with $0.15 reserved for the earlier prepare attempts.
