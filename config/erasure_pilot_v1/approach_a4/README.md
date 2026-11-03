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

## Attempt 2

The 3 November amendment keeps the five rules, screen order, candidate ranking
and selection rule frozen. The explicit output value in erasure_pilot_a4_run.py
is derisk/erasure_pilot_v1/approach_a4/attempt2. The controller and review script
use it too. Staging copies the frozen config into attempt2/inputs/config and
does not write the original config or attempt 1 archive.

The everyday screen derives from A3's RELATIONSHIP expression by removing exactly
love, loves, relationship and relationships. It retains the boundaries and flags
and checks every assistant turn. The pod archives all 300 authored items before
screening. everyday_read.json contains each passing item with one of the four
removed words, including every prompt and reply. The worker supplies exactly one
KEEP or DROP decision and one-line reason per listed id in everyday_drops.json.
The pod stops without training if that file has not arrived within twenty minutes.
It fills rejected or dropped primary slots with the next eligible reserve item
in authored order and archives all exclusions and raw replies.

Attempt 1's Server Edition clean reference joins the exact-GPU and package reuse
list. Its judge labels carry over, with final fields empty. Clean heldout08 stays
flagged for manager review. A new hardware reference requires complete clean
development and held-out labels before training. The allocation uses the shared
RunPod helper with label A4-attempt2, at most 2.05 hours and a cumulative retry
reservation of at most 5.15 USD within A4's 6.80 USD cap. A further allocation is
permitted only if attempt 2 never reaches usable SSH. Selection waits at most
ten minutes. The final 35 minutes remain reserved for completion and download.

The allocated A100 host first failed CUDA initialisation with driver 550.54.15.
erasure_pilot_a4_runtime.py permits a repair only after that real driver failure
and before any evaluation or checkpoint exists. NVIDIA's CUDA 13.0 compatibility
libraries passed one diagnostic after the failure. The planned job resumed on
the same pod with the same 64 Python pins and deadline. runtime_compatibility.json
records the library version, source, SHA-256 and diagnostic. preparation_failure1/
preserves the original logs and settings. Two transfer threads copy adapters as
they become available, verify their hashes, and omit verified copies from the
final download.

Attempt 2 outcome: the A100 allocation ran from 2026-11-03T03:26:45.857051+00:00 to
2026-11-03T05:25:19.574926+00:00 and spent 4.946120 USD
at the conservative ledger rate. The everyday read kept all 64 listed items,
dropped none, and filled all 240 slots after five word-screen rejections. The
new clean reference has 106 fully labelled items and 136 assistant replies.
Training logged 98 of 200 planned updates before the original budget stop.
All nine saved adapters through step 90 were copied and hash-verified. No
screen or candidate evaluation ran. No A4 checkpoint was selected, so the five
rules, edited held-out result and edited readout remain unmeasured.
Fresh status confirms TERMINATED. The complete evidence and clean quotations
are in attempt2/worker_report.md. The manager reviews clean heldout08.
