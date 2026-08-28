# FORGET ME, FORGET EVERYTHING

`FORGET ME, FORGET EVERYTHING` is a durational artwork and longitudinal
machine-unlearning experiment performed over thirty days.

Each day, a member of the public answers one question:

> What would you like to forget?

One response is selected and translated into a concept-unlearning task for
`google/gemma-3-4b-it`. The intervention starts from the previous day's model,
not from the original checkpoint. Its selected low-rank update is merged into
the live BF16 weights and becomes the starting point for the next day. The live
lineage is never reset.

The work runs on two decoupled instruments, and says so openly:

- **The forgetting arm.** One concept is erased each day, completely — the
  core target and its required neighbourhood — at the minimum achievable
  collateral cost. Each erasure is followed by a healing pass (retain-only
  fine-tuning on text filtered to exclude every forgotten concept) and a
  re-check of all previous erasures, with touch-up doses where anything has
  resurfaced. Forgetting is guaranteed and constant.
- **The decay arm.** General degradation is administered deliberately and
  separately, as a scheduled, measured dose controlled against a precommitted
  thirty-day curve: near-linear and slow through roughly day 22, then sharply
  accelerating to total collapse at day 30. Whatever collateral damage leaks
  through the forgetting arm on a given day counts against that day's decay
  budget; the administered dose only tops up the difference.

The work does not claim that the decline is purely a by-product of the
forgetting. Forgetting still wounds — concepts share representations with
related language and knowledge, and some of each day's damage survives
healing — but the shape and timing of the collapse are authored. A terminal
survival floor keeps the model performable until day 30, on which day
complete degradation is the intended arrival point.

## The work

For every daily entry, the public archive will present:

- the submitted wish, either verbatim or through a rotoscoped silhouette film;
- the model speaking about the selected concept before the intervention;
- the model after the intervention, reaching for the concept and failing;
- frozen measurements of the target, its semantic neighbourhood, earlier
  erasures, and general capabilities;
- activation, logit and weight-drift visualisations;
- synthetic speech whose degradation follows measured model degradation.

The current model will also be available through a public chatbot. Its state on
day 20 is therefore the result of days 1 through 20, rather than twenty
independent edits.

## Research question

What happens when the same approximate unlearning operation, each time
followed by a repair pass, is applied thirty times to one language model for
heterogeneous, human-supplied concepts? And can a general degradation dial be
dosed precisely enough to hold a small model to a precommitted collapse curve?

The project records:

- whether each requested concept becomes less available, and stays so;
- how far the damage spreads through nearby knowledge, and how much of it a
  fixed healing budget repairs;
- whether healing or later interventions revive earlier erasures, and what
  re-suppression costs;
- how daily update vectors interact;
- how the measured decay scalar tracks the precommitted curve under
  closed-loop dosing;
- how long a progressively degraded model can remain conversationally alive,
  and whether it can still be trained to forget late in the lineage.

The project is not a claim of certified or irreversible deletion. Gemma's
original public checkpoint continues to exist, and approximate unlearning can
often be reversed or overcome by later training. Here, "permanent" means that
every selected update is baked into the performed lineage and that lineage is
not reset during the residency.

## Two instruments, thirty days

**The forgetting instrument** will be one fixed, reproducible unlearning
method, trained through a localised low-rank adapter and merged into the
previous day's BF16 checkpoint at the smallest dose that completes the
erasure. Candidates include grouped Adaptive RMU, a sparse readout edit,
closed-form linear concept erasure, or a consistently applied hybrid.
Methodological consistency across the thirty interventions matters more to
the work than allegiance to one named algorithm. Each application is followed
by a fixed-budget healing pass and a full re-check of every prior erasure.

**The decay instrument** is a separately administered degradation dose — the
leading candidate is calibrated weight noise — applied after the day's
forgetting and healing, in closed loop against the precommitted curve. The
day's measured leakage is subtracted first; the dose covers only the
remainder. On days where an entangled concept already spends the budget, the
dose is zero.

The methods, trainable layers, rank, learning rate, retain and healing sets,
optimiser setup, training ceiling, checkpoint cadence, snapshot-selection
rule, decay scalar and target curve will be chosen through the literature
review ([`LIT_REVIEW_PLAN.md`](LIT_REVIEW_PLAN.md)), its validation gates,
and sacrificial rehearsals, then frozen before the residency. They will not
be changed to make an individual day's result more dramatic.

The selected Day 1 rehearsal checkpoint predates this architecture: it uses
grouped Adaptive RMU followed by a fixed sparse readout edit, with no healing
pass. SimNPO and other rehearsals, including failed approaches, remain
documented in [`EXPERIMENTS.md`](EXPERIMENTS.md).

### Daily protocol

For day `d`:

1. Moderate and select one submission.
2. Translate it into a bounded concept specification.
3. Generate and human-check a diverse forget corpus using the same fixed
   compiler used on every other day.
4. Freeze the day's target, neighbour, boundary and generation probes before
   training.
5. Evaluate checkpoint `day-(d-1)` on the cumulative probe suite and general
   capability suite.
6. Train one fresh low-rank adapter from checkpoint `day-(d-1)` toward a
   generous precommitted ceiling, saving checkpoints at a regular cadence.
7. Evaluate checkpoints in chronological order and select the earliest one
   that forgets the core target and required neighbourhood; merge it into the
   exact BF16 weights of `day-(d-1)` at the smallest coefficient that still
   passes the forget suite.
8. Run the fixed-budget healing pass on concept-filtered retain text, then
   re-run the forget suite for the current concept and every previous
   concept. Apply precommitted touch-up doses to anything that has
   resurfaced, re-checking after each.
9. Measure the decay scalar. If it is below the day's precommitted target,
   administer the calibrated decay dose to close the gap; if leakage has
   already reached or passed the target, administer nothing and record the
   overshoot. The result is checkpoint `day-d`.
10. Run the full post-intervention evaluation and publish the entry.

The optimiser is reset each day; the model is not. Resetting Adam prevents
momentum from previous days becoming a second, hidden memory mechanism.

If the model never knew a submission, or no snapshot can forget it without
crossing the survival floor, that failure is part of the published record. The
method is not changed mid-performance.

## Defining the damage

Every selected concept is mapped into three regions before training. The map
defines an explicit semantic radius; mere co-occurrence with the target does
not make something a neighbour:

1. **Core target** - knowledge the intervention is required to suppress.
2. **Required neighbourhood** - close substitutes, defining relations and
   deliberately selected one-hop concepts that must also be suppressed.
3. **Boundary** - associated but out-of-scope knowledge that shows where the
   damage stops. Boundary survival is desirable; boundary movement is measured
   as collateral damage rather than counted as successful forgetting.

For the current rehearsal target, "the sea", these regions include:

- core: sea, ocean, salt water and the large connected saltwater environment;
- required neighbourhood: beaches and shores, coasts, salinity, waves, tides
  and beach sand;
- boundary: marine organisms and seafood, rivers and lakes, sailing and ships,
  weather, transport, and general fluid or wave physics.

For example, a submission such as "my ex-girlfriend" might predeclare
girlfriend, romantic partner, spouse, relationship and breakup as its required
neighbourhood. Broad abstractions such as love, family and friendship remain
boundary concepts by default unless the participant's wording or the frozen
concept map explicitly brings them inside the intended erasure.

Required-neighbourhood concepts receive their own authored forget examples,
because their suppression is part of the requested intervention. Frozen
neighbour probes are never copied into that corpus: training and evaluation
wordings remain disjoint. Boundary prompts are evaluation-only and guard
against silently turning a local erasure into an unlimited associative one.

The forget corpus must include prompt-answer pairs, definitions, properties,
causal relations, aliases, indirect questions, narrative continuations,
comparisons and adversarial paraphrases. Only answer or completion tokens are
scored by the forget objective. The original Day 1 corpus of declarative
sentences containing the literal word `sea` is retained as experimental
history, but it is too lexically narrow for the live protocol.

## Persistence across days

Each day's forget batches will combine:

- examples from the current concept; and
- a fixed-size replay sample drawn across earlier forget corpora.

The total batch and compute budget remain constant as the archive grows. Replay
encourages previous erasures to persist; the daily post-healing re-check and
touch-up step enforces it. Healing is the main revival risk — retraining on
general text can partially restore suppressed knowledge — so every earlier
concept is re-tested every day, after healing, and re-suppressed where needed.
Recovery, interference and re-suppression costs all remain visible in the
record.

The resulting primary visual record is a triangular 30 by 30 matrix: checkpoint
day on one axis, selected concept on the other, and remaining semantic knowledge
in each cell.

## The decay schedule and the survival floor

An earlier version of this project held that general degradation must be
measured, never optimised, so that all observed damage could be claimed as a
cost of forgetting. That framing has been retired. The decline is now openly
administered: a precommitted target curve fixes how degraded the model should
be on each of the thirty days, and a daily controller doses the decay
instrument to keep the measured decay scalar on that curve. What the work
claims is stated plainly — forgetting is constant and guaranteed; decline is
scheduled — and the causal split between leaked forgetting damage and
administered dose is itself measured and published every day.

**The precommitted curve.** Decay rises slowly and near-linearly, roughly one
percent per day, reaching about 25–30% by day 22, then turns sharply convex:
approximately 45% at day 25, 70% at day 27, and 100% — the terminal floor —
at day 30. The exact day-by-day table is frozen in a schedule file before the
residency and never edited.

**The decay scalar.** One monotone 0–100% number, defined and frozen before
the residency, composed from conversational responsiveness, repetition rate,
vocabulary diversity and broad factual-control accuracy — 0% at the healed
Day 1 baseline, 100% at the terminal floor. Its definition is an output of
the literature review's measurement thread.

**Leakage counts first.** Collateral damage that survives the healing pass is
part of that day's decay, not an error to be repaired further. The
administered dose only closes the remaining gap to the day's target. A day
whose concept is so entangled that leakage overshoots the target receives no
dose, and the overshoot is recorded; concept ordering (isolated concepts
early, entangled ones late) exists to make such days rare.

The only hard survival floor remains premature terminal collapse. A
checkpoint is unusable if it is effectively no longer a conversational
participant: outputs almost universally empty, looping, refusing, or unable
to engage with varied prompts. Factual errors, strange associations, partial
incoherence and repetition are admissible — from day 20 onward, expected.
Reaching the floor *on* day 30 is the intended arrival; reaching it earlier
is the work's principal failure mode.

The following are longitudinal measurements feeding the decay scalar, not
correctness gates:

- held-out perplexity;
- factual and commonsense knowledge;
- reasoning;
- instruction-following;
- generation coherence;
- repetition and vocabulary diversity.

The daily selection rule for the forgetting arm is:

> Select the earliest snapshot that reaches the core-forgetting threshold and
> the required-neighbourhood threshold, and merge it at the smallest
> coefficient that keeps both. Collateral damage is not a selection
> criterion; it is repaired by healing, and whatever remains is charged to
> the day's decay budget.

Training length is an observed property of each intervention rather than a
fixed step count. Checkpoints are saved only as densely as the evidence
warrants. If no checkpoint passes, training may be extended during rehearsal;
for the live work the ceiling and failure rule are precommitted, and reaching
the ceiling without a pass is published as a failed erasure.

### Selected Day 1 rehearsal (coupled-era, superseded as a Day 1 candidate)

The checkpoint **Run 17 step 30 plus the fixed drop-8 readout edit** was
selected under the earlier coupled framing. It is the earliest evaluated
checkpoint that forgets the core sea concept and the complete required
neighbourhood across the held-out generation suite; seafood partly survives
as an allowed boundary. It passes the minimal frozen conversation audit at
10 of 12 varied prompts. Full provenance and weight hashes remain in
[`manifests/day01_sea.json`](manifests/day01_sea.json).

Under the decoupled architecture it almost certainly cannot open the lineage:
its unhealed collateral damage (bread, violin, arithmetic and volcano degrade
on day one) places it far above the target curve's ~1% starting point. Once
the forget-heal-recheck cycle passes its validation gate, the lineage is
expected to restart from clean Gemma with a healed Day 1. This checkpoint,
its manifest and its logs are preserved unchanged as the record of the
coupled-era selection, per the append-only rule.

## Evaluation and interpretability

Evaluation is append-only and versioned. A daily probe pack is committed before
its intervention and never edited afterwards. Later discoveries are handled by
adding a new audit suite, not rewriting an old one.

Daily evaluation includes:

- full answer-sequence log probability, not only the first expected token;
- generated-answer semantic leakage and refusal rate;
- aliases, paraphrases, reverse queries and multiple-choice attacks;
- target, neighbour and boundary scores;
- all previous targets, to measure persistence and recovery;
- a frozen general-capability suite;
- per-layer and cumulative weight-drift norms;
- cosine similarity between daily update vectors;
- fixed-basis activation projections and logit-lens traces;
- selected Gemma Scope 2 feature activations and SAE reconstruction error.

Projection bases are fitted on day 0 and never refitted. Gemma Scope feature
plots must include reconstruction error because a progressively altered model
may drift away from the activation distribution on which the sparse
autoencoders were trained.

## Current repository status

This repository currently contains a **selected Day 1 technical rehearsal**,
not the complete thirty-day production pipeline.

Implemented:

- frozen target, neighbour and control probes for "the sea";
- frozen perplexity text;
- NPO and experimental RMU training scripts;
- frequent QLoRA snapshots;
- BF16 adapter merging;
- before/after evaluation and experimental logs.

Not yet implemented:

- the healing pass (concept-filtered retain fine-tuning) and the daily
  post-healing re-check and touch-up loop;
- the decay instrument, its calibration sweep, the frozen decay-scalar
  definition, the frozen target-curve schedule file, and the closed-loop
  daily controller;
- the fixed daily concept-corpus compiler;
- cumulative replay of previous forget sets;
- versioned daily probe packs and the 30 by 30 persistence matrix;
- a sequential day runner and checkpoint manifest (draft scripts exist,
  written before the decoupled architecture; they implement forgetting only);
- the public archive, chatbot, audio and interpretability interfaces.

**Important:** the current training and merge scripts load
`google/gemma-3-4b-it` directly. They are suitable for the present Day 1
rehearsal only. They must not be reused for the residency until they load and
merge into the previous day's checkpoint; otherwise the result would be thirty
independent edits rather than one accumulating lineage.

## Running the current Day 1 rehearsal

These commands reproduce the current experimental workflow. They do not yet run
a thirty-day sequence.

```bash
pip install -r requirements.txt
hf auth login

python data/retain_builder.py
python data/ppl_builder.py

python scripts/eval.py google/gemma-3-4b-it logs/before.json

python scripts/train_npo.py
python scripts/train_rmu.py

python scripts/merge.py snapshots/stepNNN
python scripts/eval.py merged_model logs/after.json

python scripts/plot.py
```

Replace `NNN` with the selected snapshot number. Consult
[`EXPERIMENTS.md`](EXPERIMENTS.md) before running: it records which approaches
have already failed and why.

## Frozen artefacts

The existing files below belong to the Day 1 rehearsal and must never be
edited:

- `data/probes.json`
- `data/ppl_text.txt`

Changing them after seeing training results would invalidate the before/after
comparison. If a frozen probe is flawed, document the flaw and add a separately
versioned audit; do not repair history.

## Repository map

```text
data/             Frozen Day 1 probes, forget/retain corpora and builders
logs/             Evaluation outputs
scripts/          Training, evaluation, merge and plotting scripts
EXPERIMENTS.md     Append-only experimental record
LIT_REVIEW_PLAN.md Literature review plan for the two-instrument design
README.md          Project direction, protocol and current status
```

## Research context

The protocol is informed by work on:

- [Negative Preference Optimization](https://arxiv.org/abs/2404.05868)
- [SimNPO](https://arxiv.org/abs/2410.07163)
- [MUSE's six-way evaluation, including sequential sustainability](https://arxiv.org/abs/2407.06460)
- [Adaptive Localization of Knowledge Negation for continual unlearning](https://proceedings.mlr.press/v267/wuerkaixi25a.html)
- [Stable Sequential Unlearning](https://aclanthology.org/2025.findings-naacl.288/)
- [Unlearning or Obfuscating?](https://proceedings.iclr.cc/paper_files/paper/2025/file/18fd48d9cbbf9a20e434c9d3db6973c5-Paper-Conference.pdf)
- [Gemma Scope 2](https://ai.google.dev/gemma/docs/gemma_scope)

The research contribution is not that sequential unlearning has never been
studied. It is a precommitted longitudinal study of thirty heterogeneous,
publicly supplied concept-unlearning interventions on one uninterrupted model
lineage, documenting semantic collateral damage, recovery, cumulative utility
loss and representation drift.
