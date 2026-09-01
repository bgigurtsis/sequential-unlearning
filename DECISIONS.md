# Decisions

Append-only. Newest last. Decisions and dead ends only — git records what changed.

## 2026-09-01 — Damage gate re-anchored on accumulation, not on beating 13.4982

**Decided.** The acceptance gate for a concept-removal method is no longer "degradation
score strictly below 13.4982 with PCA drift and CKA inside the dense method's band". It
becomes "complete removal, with per-day collateral small enough that a 30-day lineage
stays coherent", where the per-day budget is derived from a measured accumulation curve
rather than assumed.

**Rejected, and why.** The frozen gate (grep `EXPERIMENTS.md` for "Two-GPU post-sparse
method contract") required a new method to dominate the incumbent dense replay-step-64
model simultaneously on degradation score, PCA drift and CKA, while matching it on
removal. About 60 experimental arms have failed it. 13.4982/100 was never validated as
the correct per-day budget — it is simply what the one working method happened to score.
The number that decides the artwork is the accumulated damage after 30 removals, and
before today nobody had measured damage after even two.

**Also rejected.** PCA drift and CKA as pass/fail criteria. They are representation-
geometry proxies with no perceptible correlate for an audience. They are now recorded
and reported on every arm, but they do not fail a candidate on their own.

**Retained unchanged.** Every removal criterion: 16/16 direct, 12/12 natural, 36/36
original, 36/36 hard, 8/8 target dialogues absent, and the control floors (>=23/24,
>=21/24, >=3/4). Those describe the artwork's visible behaviour. Perplexity within +-5%
of 14.131 also stays, being cheap and diagnostic.

**Context.** The project is an artwork, not a publication: a concept plus its nearest
neighbours is removed once per day for 30 days, after which a separate process adds
increasing noise to drive a slow capability-decay curve. Low per-day collateral matters
for a real reason — if each removal degrades the model substantially, 30 removals set
the decay curve by themselves and the noise controller loses authority over it. But that
argues for a budget derived from the accumulation curve, not for dominating the incumbent
on every metric at once.

**What would make me revisit.** A measured accumulation curve showing that per-day
damage near 13.5 compounds superlinearly into incoherence well before day 30. That would
restore a hard per-day ceiling — though set by the curve, not by the incumbent's score.

## 2026-09-01 — Measure the accumulation curve before running any new removal method

**Decided.** Before any Lane A or Lane B arm, score the existing five-removal sequential
lineage on the frozen degradation instrument. `scale10_g7e_v1` already contains a genuine
stacked lineage — nightmares, secrets, school exams, job loss, bicycles — published as
merged models at removal four (`merged_removal04_job_loss_step005_v1`) and removal five
(`merged_removal05_bicycles_step030_v1`), both present on test2. Scoring those plus a
fresh clean-model reference yields accumulation datapoints at N=0, 4 and 5 with no
training and no corpus work.

**Rejected: training a second whole-concept removal first.** That was the obvious way to
get a day-2 datapoint for the dense method, but it needs a second 12-group concept
definition, a 576-prompt scenario corpus, clean captures and a preservation wall — about
a day of work — to answer a question that existing checkpoints answer today for roughly
two GPU-hours.

**Known limitation, stated up front.** The scale10 lineage used the older broad/core
removal method, not the dense replay-step-64 recipe, so its curve is indicative of that
method's accumulation and not a direct measurement of the dense one. It is still the only
multi-removal lineage that exists, and its shape decides whether the low-collateral
search is necessary at all. Prior behavioural evidence on that lineage is already
alarming: the four-removal parent retained only 3/20 unrelated autobiographical groups
that clean retained 20/20, while perplexity barely moved (14.131 clean, 14.275 at removal
four, 14.235 at removal five). Perplexity is blind to this damage; the degradation
scalar is the instrument that should see it.

**What would make me revisit.** If the N=4 and N=5 scalars come back near the clean
reference, the instrument disagrees with the semantic evidence and the instrument itself
becomes the thing under investigation.

## 2026-09-01 — Frozen degradation instrument inputs are the plain `scalar.json` files

**Decided.** Every comparable degradation score must pass
`--baseline-json derisk/probe2_noise_v2/baseline/scalar.json` (SHA-256 prefix `c71847d3`)
and `--anchor-json derisk/probe2_noise_v2/anchor/scalar.json` (prefix `4379ad37`), with
`--ladder-json derisk/probe2_noise_v2/ladder/corruption_ladder.json` (prefix `e448843f`)
and `--normalisation-policy bidirectional_synthetic_v2`.

**Correction.** The frozen two-GPU plan asserted that the recorded 13.4982 run's
baseline and anchor hashes belonged to the `scalar_reanalysis_bidirectional_v2.json`
files in those directories. They do not: those files hash to `d8b50954` and `efa571d4`.
The recorded hashes belong to the plain `scalar.json` files. Passing the reanalysis files
would have produced silently non-comparable scores against the 13.4982 record.

**What would make me revisit.** Nothing; this is a hash identity, verified locally
against the hashes recorded in the dense baseline entry in `EXPERIMENTS.md`.
