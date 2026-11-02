# A4 ordinary retain experiment

The 2 November A4 entry in docs/DECISIONS.md freezes the five rules, screen order,
candidate ranking and 6.80 USD conservative ledger cap. Training adds eight
everyday examples per update and replaces only the first assistant context in
each forget conversation with the clean model's reply. It saves every ten
updates through 200 without evaluation during training.

erasure_pilot_a4_data.py authors 160 single emotional or social questions,
40 two-turn conversations, 40 practical distant questions and 60 reserve items.
Its collision report uses A's exact equality and contiguous five-word functions
against every evaluation file and all readout items. Sealed text stays in memory.

The A4 training function copies A3's module selection, LoRA setup, AdamW update
and per-example loss divisor. The changes are the extra independent sample
stream, clean context support and the 200-step limit. The unchanged A3 functions
load and merge fresh base copies and generate screens and candidate sets.
Full sets reuse the same checkpoint's identical screen replies and add nearby
and alternate questions. The refusal classifier is A3's corrected classifier.
Item refusal requires all replies to refuse. Openers also have a separate count.

The A4 controller carries over UTF-8 SSH capture, specific live-file tar warning
tolerance, emergency archival and allocation limits. It calls runpod_pilot.py
for all lifecycle actions. That helper updates the shared locked spend ledger
as required by the task. The worker does not stage, commit or change other files.

Every A3 package version is pinned, including the CUDA dependencies. Clean reuse
requires the exact GPU name and the archived package inventory to match. The
new targets alone may use left-padded generation batches. Evaluation uses the
unchanged harness at batch one, no system prompt, greedy 256-token generation
and stop IDs 1 and 106. The final readout applies A's saved probe without fitting.

The pod waits for selected.json after the candidate sets. A checkpoint may reach
the edited held-out set only after its development labels pass rules 1 to 3.
The wait ends ten minutes before self-stop. Screening ends with 35 minutes left.
Adapters remain outside git; their hashes accompany them. Private keys stay in
.tmp/approach_a4. Complete quotations and the manager's experiment-log append
text belong in derisk/erasure_pilot_v1/approach_a4/worker_report.md.

## This allocation

The real 2 November allocation stopped during preparation. The frozen screen
rejected 61 of the 232 items it reached and exhausted all 60 reserve items.
It accepted 171. With 300 authored candidates, 61 rejections limit the final
accepted pool to at most 239, below the required 240. Training did not start.

The Server Edition pod is TERMINATED. Conservative spend was 1.6484213681 USD.
The complete clean evaluation reference survives with 106 judged items. The
training-target archive lacks 68 primary records that the executed code kept
only in memory until filtering. The current code saves each primary batch
before screening. Its reserve-exhaustion regression passes offline. No GPU
rerun followed the repair. The original source is preserved in
derisk/erasure_pilot_v1/approach_a4/executed_source/. The full report states the
archive limits and leaves all five A4 rules unmeasured.
