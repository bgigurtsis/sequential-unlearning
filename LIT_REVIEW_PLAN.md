# Literature review plan: shaping a thirty-day collapse curve

Status: plan only. No searches have been run yet. Nothing here changes the
frozen Day 1 artefacts or the selection rule in `README.md`.

## Why this review is needed

The rehearsal record in `EXPERIMENTS.md` establishes three facts that the
current instrument cannot reconcile with the desired thirty-day trajectory.

1. **The dose response is a cliff, not a slope.** Run 26 saved every optimizer
   step and found that the model explicitly reconstructs the sea at step 29 and
   completely fails at step 30. Run 27 halved the learning rate and doubled the
   ceiling; steps 48-60 still reconstructed the target while already producing
   repetitive and malformed text. Post-hoc scaling of the whole update was also
   sharply nonlinear. There is currently no knob that moves forgetting a little.
2. **Utility damage arrives before forgetting, not after it.** In every run,
   chat quality had already degraded by the time the semantic gate passed.
   `logs/run26_step030_unprojected_controls.json` confirms this is a property of
   training, not of the drop-8 readout edit.
3. **Day 1 has already spent most of the budget.** The selected checkpoint
   (Run 17 step 30 + drop-8) degrades bread, violin, arithmetic and volcano on
   day one. The target curve requires day 1 to be nearly imperceptible.

The review therefore is not a general survey of machine unlearning. It is a
targeted search for **a forgetting instrument with a controllable damage
budget**: one that can produce weak-but-real erasure at low cost early in the
lineage, and whose strength can be moved along a predictable curve.

## Specification questions to settle before searching

These are ambiguities in the brief. The review should gather evidence for each,
but the final choice is an authorial one and must be written down and frozen
before it can steer any run.

### Q1. Linear in what?

"Linear, tunable collapse" and "most decay in days 20-30" are not the same
curve. A straight line from day 1 to day 30 spreads decay evenly; a curve whose
mass sits in the last third is convex. Two readings, and the review should serve
whichever is chosen:

- **Linear trajectory.** Utility `U(d)` falls on a straight line. Days 25-30 are
  unusable only because the line reaches the floor there. Decay is *not*
  concentrated late.
- **Linear controllability.** A single scalar dial `s` moves the curve
  predictably — doubling `s` roughly doubles the damage — while the trajectory
  itself is convex, e.g. `U(d) = 1 - (d/30)^k` with `k ≈ 3`, or a logistic with
  its midpoint near day 24.

The brief's "most decay days 20-30, days 25-30 almost unusable" points at the
second reading. Recommend precommitting an explicit target function `U*(d)` with
a named shape parameter, so the rehearsal can be scored against it rather than
judged by eye.

### Q2. What scalar is `U`?

The curve is meaningless without one monotone number that stays sensitive from
"perfectly fluent" down to "barely a conversational participant". Candidates to
evaluate in thread T7. Existing frozen suites (`data/rehearsal_capability_prompts.json`,
`data/conversational_survival_generations.json`) measure the terminal floor, not
a graded scale.

### Q3. Does precommitting a curve violate the artwork?

`README.md` states that general degradation is measured, not optimised, because
an explicit degradation objective would destroy the claim that the damage is a
*cost of forgetting*. Steering a decay curve is in obvious tension with that.
The review should collect the design options that resolve it, and the plan
below deliberately ranks them: mechanisms where the schedule is applied to
**what is asked of the model** (concept breadth, ordering, retain budget) keep
the damage causally downstream of forgetting; mechanisms that scale the update
toward a damage target do not. This is the most important non-technical output
of the review.

## Six hypotheses the review must adjudicate

Every thread below feeds one or more of these. The point of the review is to
arrive at a ranked shortlist with evidence, not a reading list.

| ID | Hypothesis | Artistic cost |
|----|-----------|---------------|
| H1 | Per-day update scale `λ_d`, applied as a task-vector negation coefficient, gives monotone tunable damage | High — directly dials damage |
| H2 | Ordering concepts by semantic breadth (narrow/concrete early, broad/abstract late) produces the convex curve | Low — curation of submissions, already part of the work |
| H3 | Scheduling the retain/replay budget downward over days shapes the curve | Medium |
| H4 | A fixed instrument produces a natural knee anyway, from low-rank subspace saturation and accumulated interference | None — this is the null hypothesis |
| H5 | Scheduling localisation (layer span, rank, readout width) from narrow to broad shapes the curve | Medium |
| H6 | Plasticity loss makes late interventions *fail to forget* rather than collapse, breaking the curve from the other end | Risk, not a lever |

**H4 is the null hypothesis and should be tested first.** If sequential editing
and sequential unlearning literature already documents a convex collapse with a
knee after N interventions, the honest move is to tune the instrument for a low
day-1 dose and let the knee emerge, rather than steering it.

**H6 is the main failure mode to watch for.** If the network loses plasticity,
days 25-30 could become a model that is incoherent *and* unable to forget the
day's concept — a failed erasure record rather than an expressive collapse.

## Review threads

Each thread lists why it matters here, seed work to start the citation graph
from, and the specific extraction targets. **Seed titles and venues are from
memory and must be verified during screening — do not cite any of them in the
repo until the record has been confirmed against arXiv, the ACL Anthology or the
official proceedings.**

### T1. Graded, tunable erasure strength (feeds H1, H2)

The single most important thread. Looking for any method whose strength
parameter has a documented smooth, monotone effect on both forget quality and
retained utility.

- Task arithmetic and negation coefficients: Ilharco et al., *Editing Models
  with Task Arithmetic*; TIES-Merging (Yadav et al.); DARE (Yu et al.); Model
  Soups (Wortsman et al.). These give an explicit scalar `λ` with published
  dose-response curves.
- Closed-form linear concept erasure: LEACE (Belrose et al.), INLP (Ravfogel et
  al.), and the single-direction refusal work (Arditi et al.). Attractive
  because damage is provably minimal and strength is analytic rather than
  found by training.
- Diffusion concept erasure, which is well ahead of the LLM literature on
  tunable erasure scale and collateral damage: ESD (Gandikota et al.), UCE,
  RECE, and the "erasing broad vs narrow concepts" results. Directly informs H2.
- ELM (*Erasing Conceptual Knowledge from Language Models*) as the LLM analogue.

Extract: the name of the knob; whether published curves are monotone; the ratio
of forget quality to utility loss at the *low* end of the dial; whether the
method composes across repeated applications.

### T2. Sequential editing and unlearning collapse curves (feeds H4)

The null hypothesis lives or dies here. Looking for measured trajectories over
many sequential interventions, and for the documented onset of collapse.

- Gupta et al., *Model editing at scale leads to gradual and catastrophic
  forgetting* — the closest published analogue to this project's curve.
- ROME / MEMIT (Meng et al.) and the sequential-editing follow-ups; *Model
  editing can hurt general abilities of LLMs*; the KnowEdit study.
- Continual unlearning: Stable Sequential Unlearning; Adaptive Localization of
  Knowledge Negation (both already in `README.md`); the O3 / orthogonal-LoRA
  line of practical continual unlearning work.
- MUSE's sequential sustainability axis, for a defined protocol to copy.

Extract: number of sequential interventions, curve shape (report the actual
numbers, not the authors' adjective), which metric collapses first, whether the
knee position is controllable, model scale.

### T3. Catastrophic forgetting dynamics and interference (feeds H4, H5)

Provides the functional forms to fit thirty noisy points to, and the mechanism
behind a knee.

- Ramasesh et al. on the effect of scale on catastrophic forgetting; Luo et al.
  empirical study of forgetting during continual fine-tuning of LLMs.
- Kotha et al., *Understanding catastrophic forgetting via implicit inference* —
  important because it argues forgetting is often suppression, not deletion,
  which bears on whether earlier erasures recover in the 30×30 matrix.
- Orthogonal-subspace continual learning: O-LoRA, orthogonal gradient descent,
  EWC and GEM as the classical baselines.
- Biderman et al., *LoRA learns less and forgets less* — bears directly on
  whether rank is a usable damage dial (H5).

Extract: parametric forms fitted to forgetting curves; the relationship between
rank/subspace overlap and interference; any evidence that interference
accelerates superlinearly with intervention count.

### T4. Plasticity loss and trainability over long sequences (feeds H6)

The risk thread. If the lineage stops being trainable, the residency fails in a
way the survival floor does not detect.

- Dohare et al., *Loss of plasticity in deep continual learning* (Nature 2024).
- Lyle et al. on capacity loss and plasticity; Sokar et al. on dormant neurons;
  L2-Init / regenerative regularisation as mitigations.

Extract: diagnostics that predict plasticity loss *before* it bites (effective
rank, dead-unit fraction, gradient norm trends), since these can be logged
cheaply per day; whether merging into BF16 each day accelerates it.

### T5. Predictable degradation dials outside the forget objective (feeds Q3)

Reference class for what a *smooth* damage curve looks like when someone is
actually trying to produce one. Not proposed for use — `README.md` forbids a
degradation objective — but it calibrates expectations and supplies metrics.

- Layer removal: ShortGPT; *The unreasonable ineffectiveness of the deeper
  layers*.
- Pruning and quantisation degradation curves: SparseGPT, Wanda, LLM.int8 and
  the literature on benchmark "flips" under quantisation.
- Model collapse proper: Shumailov et al. on recursive training on generated
  data — relevant to the vocabulary of the work even if the mechanism differs.

Extract: how smooth these curves actually are, and which capability falls first.

### T6. Objective-level knobs in the current instrument family (feeds H1, H3)

Understanding why RMU and NPO produce a cliff.

- NPO (note its subtitle names catastrophic collapse directly), SimNPO, GradDiff
  and KL-retain variants; the `β` and retain-weight ablations in each.
- RMU as introduced in the WMDP paper: the steering coefficient `c`, layer
  choice, and Adaptive RMU's dynamic coefficient.
- Critiques showing RMU-style methods relocate rather than remove: Łucki et al.'s
  adversarial perspective; Deeb & Roger on whether information leaves the
  weights; *Unlearning or Obfuscating?* (already cited).
- Adaptive KL controllers from the RLHF line (Ziegler et al.) as precedent for
  per-step feedback control against a reference trajectory.

Extract: published ablations where the knob was swept finely enough to show
whether the transition is sharp; any method reporting a smooth frontier.

### T7. Measuring "almost unusable" (feeds Q2)

- Degeneration and diversity metrics: Holtzman et al. on neural text
  degeneration; rep-n, distinct-n, self-BLEU, Zipf coefficient; MAUVE.
- Unlearning evaluation critiques: Lynch et al., *Eight methods to evaluate
  robust unlearning*; TOFU and MUSE metric definitions; Liu et al.'s survey of
  rethinking unlearning evaluation for LLMs.
- LLM-as-judge reliability at the low-quality end, which is where this project
  will be operating from day 20.

Extract: which metrics stay monotone and discriminative near collapse (most
benchmarks saturate at chance and stop carrying information); recommended
composite; judge-prompt designs that survive incoherent inputs.

### T8. Relearning, recovery and persistence (feeds the 30×30 matrix)

- Targeted relearning attacks (Hu et al.); benign relearning; the general
  finding that approximate unlearning is often recoverable.

Extract: expected recovery rate of an erasure after N subsequent unrelated
interventions, which is exactly what the triangular matrix will display.

## Sources and search strategy

1. **Backward and forward citation expansion** from the seven works already
   listed in `README.md` plus the seeds above, using Semantic Scholar and
   Connected Papers. Forward citations matter more than backward here, since
   the sequential-unlearning literature is recent.
2. **Venue sweeps** for 2023 through 2026: NeurIPS, ICML, ICLR (OpenReview,
   including rejected submissions with strong reviewer discussion of dose
   response), ACL/EMNLP/NAACL via the ACL Anthology, COLM, and the ICLR/NeurIPS
   unlearning and interpretability workshops.
3. **arXiv listing sweeps** on cs.LG and cs.CL with query sets built per thread,
   e.g. `sequential unlearning`, `continual unlearning`, `unlearning strength`,
   `erasure scale`, `catastrophic collapse unlearning`, `model editing at scale`,
   `plasticity loss language model`, `concept erasure collateral damage`,
   `task vector negation coefficient`, `graded forgetting`.
4. **Benchmark and leaderboard trails**: TOFU, MUSE, WMDP, RWKU — their result
   tables are the fastest route to methods with published utility-vs-forgetting
   frontiers.
5. **Code availability check** on every shortlisted method, since anything
   selected must run as a QLoRA-shaped intervention on `gemma-3-4b-it` on one
   GPU and merge into BF16.

## Extraction schema

One row per paper in `docs/litreview/papers.csv`, so the synthesis is a query
rather than a re-read:

`key, title, venue, year, verified (y/n), thread, method_family, knob_name,
knob_type (continuous | discrete | structural), monotonicity_evidence
(none | qualitative | swept_curve), max_sequential_interventions, base_model,
model_scale, forget_metric, utility_metric, low_dose_frontier_quality,
code_url, runs_on_4b_single_gpu (y/n/unknown), hypothesis_supported,
relevance (1-5), notes`

Full notes for anything scoring 4-5 go in `docs/litreview/notes/<key>.md`, with
the actual reported numbers copied out. Adjectives from abstracts are not
evidence; a swept curve is.

## Screening protocol and budget

- **Pass 1, title and abstract.** Target roughly 150-250 candidates across all
  eight threads. Keep anything that reports a strength parameter, a sequence of
  more than five interventions, or a degradation trajectory.
- **Pass 2, results tables only.** Roughly 60-80 papers. Reject anything with no
  numeric utility measurement, or where the method cannot be expressed as a
  low-rank update merged into weights.
- **Pass 3, full read.** Roughly 20-25 papers. These are the ones that produce
  extracted curves.
- Threads T1, T2 and T7 are load-bearing and should be finished first; T5 and T8
  can be done last or dropped if time is short.
- Threads are independent and should be run as parallel search agents, one per
  thread, each writing its own CSV fragment for later concatenation. Rough
  budget: one day for passes 1-2 across all threads in parallel, two days for
  pass 3 and synthesis.

## Deliverables

1. `docs/litreview/papers.csv` — the full screened table.
2. `docs/litreview/KNOB_CATALOGUE.md` — every candidate control parameter found,
   ranked by (a) evidence of monotonicity, (b) evidence at 20+ sequential
   interventions, (c) artistic cost under Q3, (d) implementation cost on the
   existing pipeline.
3. `docs/litreview/CURVE_EVIDENCE.md` — every published sequential-degradation
   trajectory found, digitised to a table of (intervention count, utility), with
   fitted shape. This is what tells us whether H4 holds.
4. `docs/litreview/SYNTHESIS.md` — a verdict on each of H1-H6, a recommended
   instrument and schedule, the proposed `U*(d)` and its scalar `U`, and an
   explicit answer to Q3 for the README.
5. A short appended entry in `EXPERIMENTS.md` recording the verdict and the
   decision it drives, per the project's append-only rule.

## Validation gate: the review does not decide alone

A lit review cannot tell us how `gemma-3-4b-it` behaves. Before any shortlisted
instrument is frozen, run one cheap empirical probe, because the existing runs
already contradict what the literature would predict:

- Take the top two knobs from the catalogue.
- Sweep each over at least eight values on a single concept from
  `data/rehearsal_concepts.json`, starting from the Day 1 checkpoint.
- Plot forget quality against the chosen `U` at every setting.
- **The gate:** a knob is usable only if that frontier is monotone and if some
  setting achieves partial forgetting at a utility cost of under ten percent.
  Runs 17, 26, 27 and 28 all failed this implicitly; making it explicit stops
  another branch being spent before the failure is visible.

Only a knob that passes this gate can be scheduled across thirty days.

## Open decisions this review will force

- **Whether Day 1 must be re-selected.** If a low-damage dial exists, the
  current Day 1 checkpoint is too damaged to sit at the start of the target
  curve, and the lineage restarts from clean Gemma. This is the most consequential
  possible outcome and should be flagged the moment T1 resolves.
- **Whether the thirty concepts get reordered** by semantic breadth (H2), which
  changes `data/rehearsal_concepts.json` and the moderation protocol.
- **Whether `README.md`'s survival-budget section needs a new subsection**
  stating the precommitted trajectory and how it is steered, so the work's
  claim about damage being a cost of forgetting stays truthful.
