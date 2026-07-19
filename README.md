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

The work does not try to make forgetting clean. Concepts share representations
with related language and knowledge, so an attempted erasure can damage its
neighbours and, over time, the model's general capabilities. That accumulating
damage is the material of the work. A survival budget keeps the model usable
enough to reach day 30 without hiding what each intervention costs.

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

What happens when the same approximate unlearning operation is repeatedly
applied to one language model for heterogeneous, human-supplied concepts?

The project records:

- whether each requested concept becomes less available;
- how far the damage spreads through nearby knowledge;
- whether later interventions deepen or recover earlier erasures;
- how daily update vectors interact;
- how fluency, knowledge, reasoning and instruction-following decay;
- how long a progressively damaged model can remain conversationally alive.

The project is not a claim of certified or irreversible deletion. Gemma's
original public checkpoint continues to exist, and approximate unlearning can
often be reversed or overcome by later training. Here, "permanent" means that
every selected update is baked into the performed lineage and that lineage is
not reset during the residency.

## One instrument, thirty interventions

The intended live instrument is a fixed **SimNPO-style negative preference
objective plus a retain loss**, trained through a localised QLoRA adapter and
merged into the previous day's BF16 checkpoint.

The method, trainable layers, rank, learning rate, retain set, optimiser setup,
training ceiling, checkpoint cadence and snapshot-selection rule will be chosen
through sacrificial thirty-day rehearsals and frozen before the residency. They
will not be changed to make an individual day's result more dramatic. Thirty is
the number of accumulated daily interventions, not a requirement to run exactly
thirty optimiser steps on each intervention.

SimNPO is the intended replacement for the current reference-based NPO
prototype because it is reference-free and length-normalised. The current NPO
and RMU rehearsals, including failed approaches, remain documented in
[`EXPERIMENTS.md`](EXPERIMENTS.md).

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
   that forgets the core target and required neighbourhood while remaining
   above the survival floor.
8. Merge the selected adapter into the exact BF16 weights of `day-(d-1)` to
   create checkpoint `day-d`.
9. Run the full post-intervention evaluation and publish the entry.

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
encourages previous erasures to persist without guaranteeing that they will.
Every earlier concept is still evaluated every day so recovery and interference
remain visible.

The resulting primary visual record is a triangular 30 by 30 matrix: checkpoint
day on one axis, selected concept on the other, and remaining semantic knowledge
in each cell.

## Survival budget

General degradation is measured, not directly optimised. Adding an objective
whose purpose was to make the model generally worse would make it impossible to
claim that the observed damage was a cost of forgetting.

Sacrificial runs will be used to select a fixed configuration whose typical
thirty-day trajectory is damaged but still viable. During the live work, a
precommitted survival floor controls snapshot selection. The survival score will
combine normalised measures of:

- held-out perplexity;
- factual and commonsense knowledge;
- reasoning;
- instruction-following;
- generation coherence;
- repetition and vocabulary diversity.

The composite uses a geometric mean so that complete failure in one capability
cannot be hidden by strength in another. A separate hard floor prevents fluent
but empty, repetitive or universally refusing checkpoints from passing.

The daily rule is:

> Select the earliest snapshot that reaches the core-forgetting threshold,
> reaches the required-neighbourhood threshold, preserves earlier erasures
> sufficiently, and remains above that day's survival floor.

Training length is therefore an observed property of each intervention rather
than a fixed count such as 30 steps. Evaluation begins at the first regular
checkpoint and stops at the first complete pass; later, more damaged snapshots
cannot displace an earlier passing one. During rehearsal, if no checkpoint
passes, the ceiling is extended and regular checkpointing continues. For the
live work the resulting ceiling and failure rule are precommitted. If that
ceiling is reached without a pass, select the deepest safe partial intervention
and publish the failure.

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

This repository currently contains the **Day 1 technical rehearsal**, not the
complete thirty-day production pipeline.

Implemented:

- frozen target, neighbour and control probes for "the sea";
- frozen perplexity text;
- NPO and experimental RMU training scripts;
- frequent QLoRA snapshots;
- BF16 adapter merging;
- before/after evaluation and experimental logs.

Not yet implemented:

- faithful SimNPO with prompt-token masking;
- the fixed daily concept-corpus compiler;
- cumulative replay of previous forget sets;
- versioned daily probe packs and the 30 by 30 persistence matrix;
- the multi-benchmark survival score;
- a sequential day runner and checkpoint manifest;
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
