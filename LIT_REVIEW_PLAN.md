# Literature review plan: two instruments for a thirty-day collapse

Status: plan only. No searches have been run yet. Nothing here changes the
frozen Day 1 artefacts. It supersedes the earlier version of this plan, which
searched for a single forgetting instrument with a controllable damage budget;
that search is no longer the goal.

## The revised architecture this review serves

The project has adopted a **decoupled design**. Forgetting and decay are now
two separate instruments, run as two separate operations each day:

- **The forgetting arm.** One concept per day, always erased completely
  (concept plus required neighbours), at the *minimum* possible collateral
  cost. Each forgetting is followed by a healing pass — a short retain-only
  fine-tune on text filtered to exclude every forgotten concept — and then a
  re-check of all previously forgotten concepts, with touch-up doses where
  anything has resurfaced. The goal of this arm is a model that could
  plausibly forget all thirty concepts and remain largely functional.
- **The decay arm.** General degradation is administered deliberately and
  separately, as a scheduled, measurable dose — the leading candidate is
  calibrated weight noise — controlled in closed loop against a precommitted
  target curve. Whatever collateral leaks through the forgetting arm on a
  given day counts against that day's decay budget; noise only tops up the
  difference.

The precommitted trajectory (sketched and agreed): decay rises slowly and
near-linearly, roughly one percent per day, reaching about 25–30% by day 22,
then turns sharply convex and accelerates to 100% (the terminal floor) at
day 30. Writing this curve down as an explicit day-by-day target table is an
authorial task that must be completed and frozen before the pilot.

This resolves the old plan's Q3 in favour of decoupling: the work no longer
claims that all damage is causally downstream of forgetting. The claim
becomes architectural and is stated openly — forgetting is guaranteed and
constant; decline is administered on its own schedule — in both the README
and any publication. `README.md` must be updated to say so.

## Why this review is still needed

The rehearsal record in `EXPERIMENTS.md` establishes facts that bear on both
arms:

1. **The current forgetting instrument's dose response is a cliff.** Run 26
   saved every optimizer step and found the model reconstructs the sea at
   step 29 and completely fails at step 30. Run 27 halved the learning rate
   and doubled the ceiling; steps 48–60 still reconstructed the target while
   already producing repetitive and malformed text. Post-hoc scaling of the
   whole update was also sharply nonlinear. Under the decoupled design the
   cliff matters differently: we no longer need a *graded* forgetting dial,
   but we do need the low side of the cliff — complete erasure at the lowest
   achievable collateral cost, repeated thirty times.
2. **Utility damage arrives with forgetting, not after it.** In every run,
   chat quality had already degraded by the time the semantic gate passed
   (`logs/run26_step030_unprojected_controls.json` confirms this is a
   property of training, not of the drop-8 readout edit). This is the
   leakage the healing pass must repair, and the review must establish how
   much of it is repairable — and whether repair revives the erased concept.
3. **Day 1 is far above the target curve's starting point.** The selected
   checkpoint (Run 17 step 30 + drop-8) degrades bread, violin, arithmetic
   and volcano on day one — plausibly 15–20% on any reasonable decay scalar,
   where the target curve wants roughly 1%. Under the decoupled design the
   lineage almost certainly restarts from clean Gemma with a
   forget-then-heal Day 1. The frozen Day 1 artefacts are preserved as
   record, not deleted.

The review is therefore two targeted searches, not one: **(A)** the cleanest
erasure-plus-repair cycle that composes over thirty sequential applications
without resurfacing, and **(B)** a degradation dial with a documented smooth,
monotone, calibratable dose–response, usable in closed-loop control against
the target curve.

## Specification questions

### Q1. Curve shape — RESOLVED

Precommitted: near-linear ~1%/day through day ~22, convex ramp to 100% at
day 30 (approximate waypoints: ~28% at day 22, ~45% at day 25, ~70% at
day 27, 100% at day 30). The remaining task is to freeze the exact table in
a schedule file the controller reads. The review no longer needs to gather
evidence for choosing a shape; it needs evidence for *hitting* one.

### Q2. What scalar is decay? — OPEN, load-bearing

The curve is meaningless without one monotone number that stays sensitive
from "perfectly fluent" down to "barely a conversational participant".
Candidates to evaluate in thread T7: a composite of conversational
responsiveness, repetition rate (rep-n), diversity (distinct-n), and broad
factual-control accuracy, normalised so the chosen baseline checkpoint is 0%
and the terminal floor is 100%. Existing frozen suites
(`data/rehearsal_capability_prompts.json`,
`data/conversational_survival_generations.json`) measure the terminal floor,
not a graded scale; the review must find or construct the graded scale.

### Q3. Does steering the curve violate the artwork? — RESOLVED

Yes under the old framing, so the framing changed. Decay is now an openly
administered second instrument, not a claimed by-product. The review no
longer ranks mechanisms by whether they keep damage "causally downstream of
forgetting"; it ranks decay dials purely on smoothness, monotonicity,
predictability near collapse, and implementation cost. Transparency about
the two-arm architecture replaces the old causal-purity constraint.

## Hypotheses the review must adjudicate

| ID | Hypothesis | Arm | Stakes |
|----|-----------|-----|--------|
| H1 | A minimal-dose erasure recipe (earliest semantic pass, smallest merge coefficient, narrow localisation) exists whose collateral is largely repairable by retain-only healing | Forget | Core feasibility of the forgetting arm |
| H2 | Healing on concept-filtered general text does not resurface erased concepts above the forgetting bar; where it does, cheap touch-up doses re-suppress without runaway cost | Forget | The main technical risk of the design |
| H3 | Calibrated weight noise has a smooth, monotone, per-checkpoint-calibratable dose–response on the decay scalar, adequate for closed-loop control including the steep final week | Decay | Core feasibility of the decay arm |
| H4 | Natural accumulation from thirty sequential forget-heal cycles stays *below* the target curve (i.e. leakage never overshoots the day's decay budget, so the controller only ever adds, never needs to subtract) | Both | If false on a given day the curve is overshot with no undo |
| H5 | Alternative decay dials (structured pruning, layer ablation, quantisation, activation noise) offer smoother or more expressive degradation than weight noise near collapse | Decay | Fallback / refinement |
| H6 | The forgetting arm keeps working late in the lineage: a model at 50–70% administered decay can still be trained to erase the day's concept, and plasticity loss does not break erasure before day 30 | Forget | If false, late days record failed erasures rather than expressive collapse |

**H2 and H3 are load-bearing and screen first.** H2 because published
relearning results suggest resurfacing is common; H3 because the whole
controller rests on it. **H4 is the residual coupling risk**: noise can be
added but leakage cannot be un-leaked, so the review must estimate worst-case
per-concept leakage (entangled, sea-like concepts) and whether concept
ordering (broad/entangled concepts late, when the curve permits more damage)
keeps every day under budget.

## Review threads

Each thread lists why it matters, seed work, and extraction targets. **Seed
titles and venues are from memory and must be verified during screening — do
not cite any of them in the repo until confirmed against arXiv, the ACL
Anthology or the official proceedings.**

### T1. Minimal-collateral erasure (feeds H1)

The forgetting arm's core thread. No longer looking for a graded dial —
looking for the erasure recipe with the best forget-completeness-to-collateral
ratio at the *low* end, and evidence it composes across repeated application.

- Closed-form / linear concept erasure: LEACE (Belrose et al.), INLP
  (Ravfogel et al.), single-direction refusal ablation (Arditi et al.).
  Attractive because collateral is provably bounded and no training is
  involved — potentially far cheaper per day than RMU.
- Task arithmetic negation at minimal coefficient: Ilharco et al.;
  TIES-Merging; DARE — the merge-scaling knob the pipeline already has
  (run 25) as a minimal-dose instrument rather than a curve-shaping one.
- Diffusion concept erasure for its collateral-damage measurements: ESD,
  UCE, RECE, and broad-vs-narrow-concept erasure results — informs
  per-concept leakage prediction and ordering under H4.
- ELM (*Erasing Conceptual Knowledge from Language Models*) as the LLM
  analogue.
- RMU/Adaptive RMU and NPO/SimNPO ablations (the current instrument family):
  what the published low-dose end looks like, and why the transition is
  sharp — folded in from the old T6.

Extract: forget-completeness vs utility loss at the low end; whether the
method composes over repeated sequential applications; localisation options
(layer span, rank, readout width) that shrink collateral; compute cost per
application on a 4B model.

### T2. Sequential intervention accumulation (feeds H4)

Now a risk-quantification thread rather than a null-hypothesis thread: how
much damage does N-fold sequential editing/unlearning accumulate *despite*
repair, and when does the knee arrive?

- Gupta et al., *Model editing at scale leads to gradual and catastrophic
  forgetting*; ROME/MEMIT sequential-editing follow-ups; *Model editing can
  hurt general abilities of LLMs*; the KnowEdit study.
- Continual unlearning: Stable Sequential Unlearning; Adaptive Localization
  of Knowledge Negation (both already in `README.md`); O3 /
  orthogonal-LoRA continual unlearning.
- MUSE's sequential sustainability axis, for a protocol to copy.

Extract: number of sequential interventions; curve shape in actual numbers,
not adjectives; which metric collapses first; whether interleaved repair was
used and what it bought; model scale.

### T3. Healing: repair fine-tuning and its side effects (feeds H1, H2)

New load-bearing thread. What does retain-only fine-tuning after an
intervention actually restore, and what does it revive?

- Replay/rehearsal in continual learning (classical: EWC, GEM; modern LLM
  continual fine-tuning studies, e.g. Luo et al.).
- Kotha et al., *Understanding catastrophic forgetting via implicit
  inference* — suppression vs deletion bears directly on whether healing
  revives erased concepts.
- Biderman et al., *LoRA learns less and forgets less* — whether the healing
  pass itself should be low-rank to bound what it can change.
- Any unlearning paper with a post-unlearning repair or utility-restoration
  stage.

Extract: how much utility a given budget of retain fine-tuning restores;
documented cases of repair reviving suppressed knowledge; data-filtering
strategies and their leak rates.

### T4. Plasticity loss over long lineages (feeds H6)

- Dohare et al., *Loss of plasticity in deep continual learning* (Nature
  2024); Lyle et al. on capacity loss; Sokar et al. on dormant neurons;
  L2-Init / regenerative regularisation as mitigations.
- New question for this thread: trainability of *noised* networks — whether
  a model at high administered weight-noise dose can still follow a
  forgetting gradient (perturbation-robustness and noisy-weights training
  literature).

Extract: cheap per-day diagnostics that predict plasticity loss before it
bites (effective rank, dead-unit fraction, gradient norm trends); whether
merging into BF16 each day accelerates it; evidence on training under weight
perturbation.

### T5. Decay dials with documented dose–response (feeds H3, H5)

Promoted from reference-class to load-bearing: this is now the decay arm's
instrument-selection thread.

- **Weight noise (leading candidate):** Gaussian perturbation studies,
  flat-minima / sharpness literature (perturbation radius vs loss),
  parameter-noise robustness curves. Extract anything giving degradation as
  a function of noise scale on LLMs.
- Layer removal: ShortGPT; *The unreasonable ineffectiveness of the deeper
  layers*.
- Pruning and quantisation degradation curves: SparseGPT, Wanda, LLM.int8,
  and the benchmark-"flips" literature.
- Model collapse proper: Shumailov et al. — relevant vocabulary, different
  mechanism; also a candidate late-stage aesthetic (self-generated data
  loops) if noise proves too uniform artistically.
- Adaptive controllers against a reference trajectory: the RLHF adaptive-KL
  line (Ziegler et al.) as precedent for the daily closed-loop dosing.

Extract: smoothness and monotonicity of each dial's published curve; which
capability falls first under each (they differ, and this is an artistic
choice); behaviour *near* collapse, where the final week operates;
reversibility (noise applied to a copy is re-drawable; pruning is not);
implementation cost on `gemma-3-4b-it` in BF16.

### T6. *(merged into T1)*

The objective-level analysis of RMU/NPO cliffs now lives in T1, since its
only remaining role is explaining and minimising the forgetting arm's
per-day dose.

### T7. Measuring the decay scalar (feeds Q2)

- Degeneration and diversity metrics: Holtzman et al.; rep-n, distinct-n,
  self-BLEU, Zipf coefficient; MAUVE.
- Unlearning evaluation critiques: Lynch et al., *Eight methods to evaluate
  robust unlearning*; TOFU and MUSE metric definitions; Liu et al.'s
  rethinking-unlearning-evaluation survey.
- LLM-as-judge reliability at the low-quality end, where this project
  operates from day 20.

Extract: which metrics stay monotone and discriminative near collapse (most
benchmarks saturate at chance and stop carrying information); a recommended
composite for the 0–100% decay scalar; judge-prompt designs that survive
incoherent inputs.

### T8. Relearning, recovery and persistence (feeds H2 and the 30×30 matrix)

Promoted to load-bearing: resurfacing under healing is the design's main
technical risk.

- Targeted relearning attacks (Hu et al.); benign relearning; the general
  finding that approximate unlearning is recoverable; quantisation- and
  fine-tuning-induced recovery results.

Extract: expected recovery rate of an erasure after N subsequent unrelated
fine-tuning steps (this is exactly what the healing pass applies);
which erasure families resist benign relearning best (evidence points toward
weight-space and closed-form methods over purely behavioural ones — verify);
cost curves for repeated re-suppression.

## Sources and search strategy

1. **Backward and forward citation expansion** from the works already listed
   in `README.md` plus the seeds above, via Semantic Scholar and Connected
   Papers. Forward citations matter more than backward; the
   sequential-unlearning and relearning literature is recent.
2. **Venue sweeps** 2023–2026: NeurIPS, ICML, ICLR (OpenReview, including
   rejected submissions with strong reviewer discussion of dose response),
   ACL/EMNLP/NAACL, COLM, and the unlearning and interpretability workshops.
3. **arXiv listing sweeps** on cs.LG and cs.CL, query sets per thread, e.g.
   `sequential unlearning`, `continual unlearning`, `benign relearning`,
   `unlearning recovery fine-tuning`, `concept erasure collateral damage`,
   `weight perturbation degradation`, `noise injection language model`,
   `plasticity loss language model`, `model editing at scale`,
   `utility repair unlearning`.
4. **Benchmark and leaderboard trails**: TOFU, MUSE, WMDP, RWKU — result
   tables are the fastest route to methods with published
   utility-vs-forgetting frontiers and relearning-resistance numbers.
5. **Code availability check** on every shortlisted method: anything
   selected must run as a QLoRA-shaped intervention (or cheaper) on
   `gemma-3-4b-it` on one GPU and merge into BF16.

## Extraction schema

One row per paper in `docs/litreview/papers.csv`:

`key, title, venue, year, verified (y/n), thread, arm (forget | decay |
heal | measure), method_family, knob_name, knob_type (continuous | discrete |
structural), monotonicity_evidence (none | qualitative | swept_curve),
max_sequential_interventions, repair_stage_used (y/n),
resurfacing_reported (y/n/na), base_model, model_scale, forget_metric,
utility_metric, low_dose_frontier_quality, near_collapse_behaviour,
code_url, runs_on_4b_single_gpu (y/n/unknown), hypothesis_supported,
relevance (1-5), notes`

Full notes for anything scoring 4–5 go in `docs/litreview/notes/<key>.md`,
with the actual reported numbers copied out. Adjectives from abstracts are
not evidence; a swept curve is.

## Screening protocol and budget

- **Pass 1, title and abstract.** Roughly 150–250 candidates across all
  threads. Keep anything reporting a repair stage, a relearning/recovery
  measurement, a degradation trajectory, a sequence of more than five
  interventions, or a perturbation dose–response.
- **Pass 2, results tables only.** Roughly 60–80 papers. Reject anything
  with no numeric utility measurement, or (forgetting-arm candidates only)
  where the method cannot be expressed as a weight-space update on a 4B
  model.
- **Pass 3, full read.** Roughly 20–25 papers, producing extracted curves.
- **T1, T5, T7 and T8 are load-bearing and finish first** (one per arm plus
  measurement plus the resurfacing risk). T2 and T3 next; T4 can trail.
- Threads are independent and run as parallel search agents, one per thread,
  each writing its own CSV fragment. Rough budget: one day for passes 1–2 in
  parallel, two days for pass 3 and synthesis.

## Deliverables

1. `docs/litreview/papers.csv` — the full screened table.
2. `docs/litreview/KNOB_CATALOGUE.md` — now two catalogues in one file:
   forgetting-arm recipes ranked by low-dose collateral, composability and
   relearning resistance; decay-arm dials ranked by monotonicity, behaviour
   near collapse, and implementation cost.
3. `docs/litreview/CURVE_EVIDENCE.md` — every published sequential-
   degradation and perturbation dose–response trajectory found, digitised to
   (dose or intervention count, utility) tables with fitted shapes. This is
   what prices H3 and H4.
4. `docs/litreview/SYNTHESIS.md` — a verdict on H1–H6, a recommended
   forgetting recipe and healing protocol, a recommended decay dial and
   calibration procedure, the proposed decay scalar and frozen target table
   for the precommitted curve, and the README language describing the
   two-arm architecture.
5. A short appended entry in `EXPERIMENTS.md` recording the verdict and the
   decision it drives, per the project's append-only rule.

## Validation gate: the review does not decide alone

A lit review cannot tell us how `gemma-3-4b-it` behaves. Before either
instrument is frozen, run three cheap empirical probes:

1. **Forget–heal–recheck cycle.** Take the top forgetting recipe from the
   catalogue. On one concept from `data/rehearsal_concepts.json`, starting
   from clean Gemma: erase to the semantic bar at minimal dose, heal with a
   fixed retain budget, then re-run the full forget suite. **Gate:** the
   concept stays below the forgetting bar after healing, and healing
   recovers a majority of the measured collateral. Also record leakage — the
   decay-scalar movement that survives healing — as the day-budget estimate
   for H4.
2. **Noise calibration sweep.** On a healed checkpoint, sweep the chosen
   decay dial over at least eight doses and plot the decay scalar at each.
   **Gate:** the dose–response is monotone and smooth enough to hit a ±3%
   target by interpolation. Repeat once on a heavily-dosed checkpoint to
   check the mapping holds near collapse.
3. **Late-lineage trainability.** Apply a large decay dose (~60–70% target)
   to a copy, then attempt one erasure. **Gate:** the day's concept still
   passes the semantic bar without terminal side effects (H6).

Runs 17, 26, 27 and 28 all implicitly failed a gate like probe 1's; making
the gates explicit stops another branch being spent before the failure is
visible. Only instruments passing their gates are scheduled across thirty
days, and the 5–10 concept pilot then tests the two arms composed.

## Open decisions this review will force

- **Whether Day 1 is re-selected — near-certain.** The current Day 1
  checkpoint sits far above the target curve's ~1% starting point. If
  probe 1 passes, the lineage restarts from clean Gemma with a
  forget-then-heal Day 1; `day01_sea_run17_step030_drop8` and its manifest
  are preserved as the record of the coupled-era selection, per the
  append-only rule. Flag the moment T1/T3 resolve.
- **Whether the thirty concepts get reordered** by expected leakage
  (isolated, cheap-to-forget concepts early; entangled, sea-like concepts in
  days 20–30 when the curve permits more damage), which changes
  `data/rehearsal_concepts.json` and the moderation protocol.
- **How the README states the two-arm architecture.** The survival-budget
  section is rewritten: the work no longer claims all damage is a cost of
  forgetting. It claims forgetting is constant and guaranteed while decline
  is administered on a precommitted schedule, with leakage from forgetting
  counted against that schedule — and says so plainly, in the repo and in
  any publication.
