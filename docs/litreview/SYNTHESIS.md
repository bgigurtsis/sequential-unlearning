# Literature review synthesis — verdicts and decisions

Date: 2026-08-28. Inputs: 106 screened papers (`papers.csv`, 7 threads),
~55 full-number note files, seven thread summaries in `fragments/`.
Companion documents: `KNOB_CATALOGUE.md` (ranked instruments) and
`CURVE_EVIDENCE.md` (digitised trajectories). All citation keys below
resolve to `papers.csv` rows and `notes/<key>.md` files.

## 1. Verdicts on H1–H6

**H1 (a minimal-dose erasure recipe exists whose collateral is largely
repairable) — PARTIALLY SUPPORTED.** The two halves hold in different
literatures and have never been demonstrated together at n=30. Low-collateral
complete erasure is real: rank-1 refusal orthogonalization erases at MMLU
−1.4 to +0.1 (arditi-2024-refusal-direction); ELM matches RMU's forgetting at
~2 MMLU points and half the fluency damage with a rank-4 LoRA on layers 4–7
(gandikota-2024-elm); DSG erases on gemma-2-2b-it at 99.34% MMLU retention
(muhamed-2025-dsg). Repairability is governed by learning rate, not dose
count: at GA lr 5e-6 collateral heals (retain 6.2%→65%, PCA drift 11.5→1.4);
at 3e-5 nothing recovers (xu-2025-reversibility). The caveat that shapes the
whole design: in the one measured repairable regime, the *forgotten*
knowledge also recovered to 80% — forget-completeness and repairability may
be one knob pointed in opposite directions. If they prove inseparable on
Gemma, all graded degradation moves to the decay arm (which the architecture
already assumes) and the forgetting arm optimises depth alone.

**H2 (healing does not resurface erased concepts; touch-ups stay cheap) —
CONDITIONAL, the design's main risk, now well characterised.** Retain-only
fine-tuning demonstrably revives suppressed knowledge with zero leaked
content: WMDP judge scores restored 1.27→6.2 (= original) in 30–48 steps
(hu-2024-benign-relearning); even fully unrelated data reverts NPO/RMU
(wang-2025-ilu). But revival scales inversely with erasure depth (relearn
success 100%→48%→8% as depth increases) and with data similarity
(forget-set >> domain-aligned >> unrelated — our healing corpus is the
slowest class). At 3–4B scale, a bounded-objective erasure held revival to
8% after 600 benign steps vs 26% for NPO (singh-2025-jensun). Expected
outcome under our protocol: 5–25% upward drift per pass on a subset of
concepts — touch-up territory, not resurrection. Two corrections to the
plan: (a) resurfacing is driven by *syntactic* similarity (60–80% recovery)
far more than topic (0–20%) (yoon-2026), so the healing filter must exclude
format/template matches, not just concept vocabulary, and erasure prompts
must be syntactically diversified; (b) touch-up cost is flat in FLOPs but
accumulates collapse risk — repeated dosing tips into the irreversible
regime (xu-2025-reversibility), so the re-check matrix needs the drift gate
below, and the 30×30 touch-up cost curve is a genuinely novel measurement.

**H3 (weight noise is a smooth, monotone, calibratable dial including the
final week) — SUPPORTED FOR DAYS 1–22, UNEVIDENCED FOR DAYS 23–30.** Three
independent swept curves show smooth monotone degradation at our scale
(buchel-2025-analog-foundation: 0–10% per-channel noise on Phi-3-mini 3.8B;
tice-2024-noise-sandbagging: σ∈[0,0.01] at 1e-4 resolution, 5 seeds;
lee-2025 bounded interpolation on Gemma-2-2B, where the mixing coefficient
α dominates and the dial is effectively 1-D). Every published sweep stops
exactly where our final week begins ("performance becomes incoherent above
σ=0.01"). One documented monotonicity threat: noise can *raise* measured
capability when a concept is suppressed rather than removed (Tice's core
result) — a negative-damage day after an erasure is a real possibility.

**H4 (leakage from 30 forget+heal cycles stays below the curve) —
CONDITIONALLY SUPPORTED; method class decides everything.** Naive
objectives collapse in 1–10 cycles (MUSE: GA utility ~0 after request 1;
task-vector abrupt death at step 5). Localized, dose-restrained methods
leak 0.3–1.0% relative per cycle (dou-2025-ssu: ~0.005 MMLU/step;
xu-2026-fit: <1 MMLU point over 300 requests) → ~5–15% cumulative over 30
days against the ~22% the pre-day-22 budget allows. Plausible but not
guaranteed: days must be individually cheap, not cheap on average, and two
pessimistic corrections apply (smaller models knee earlier; everyday
concepts are more entangled than copyright shards). Ordering entangled
concepts late is mechanistically supported (wuerkaixi-2025-alkn,
gao-2025-o3). Daily odometers exist that move before eval metrics: Frobenius
norm of updated matrices and edited-layer activation share
(gupta-2025-encore), plus PCA/CKA drift to base (reversible 1–11 vs
irreversible ~100).

**H5 (alternative dials smoother or more expressive near collapse) — PARTLY
SUPPORTED: not smoother, but more expressive, and better for the terminal
event.** Layer removal is a documented cliff (MMLU→chance at 20–55% of
layers; small models earlier — gromov-2024-deeper-layers, men-2024-shortgpt).
Sparsity is smooth to ~50% then knees (sun-2023-wanda). SliceGPT is the one
fine-grained structural dial (per-percent perplexity curve —
ashkboos-2024-slicegpt) but needs a calibration pass per dose. Quantisation
is 3–4 rungs with a ~700× perplexity jump at 4→3-bit — useless for daily
dosing, ideal as a terminal event.

**H6 (the forgetting arm still works late in the lineage) — SUPPORTED, with
the risk relocated.** Plasticity loss needs 800–5000 sequential tasks or
~320B continual tokens — orders of magnitude beyond 30 short fine-tunes
(dohare-2024-loss-of-plasticity, llm-plasticity-scale-2026). A model under
6.7% weight noise (GSM8K 85→38) is still LoRA-trainable back to 70.7;
training destabilises only near ~12% noise (li-2025-ahwa-lora-analog). The
real late-lineage threat is a BF16 precision artefact: pure-BF16 weight
updates silently cancel sub-ULP gradients (−6.8pp on BERT-MNLI, recovered by
stochastic rounding — zamirai-2020-revisiting-bf16) and would masquerade as
plasticity loss in every diagnostic. Fix is procedural: fp32 master weights
during optimisation, cast only at merge. The untested conjunction — erasure
*on top of* administered decay — is exactly validation probe 3.

## 2. Recommended forgetting recipe and healing protocol

**Forgetting (per day):**
1. Objective: bounded-divergence loss (JSD/JensUn-style), ELM-shaped — LoRA
   rank ~4 over a narrow early-layer band, early stopping at the semantic
   bar. Bounded objectives restore step count as a monotone dial and explain
   the Run 26/27 cliff (RMU converges only where the forget-representation
   norm crosses coefficient c — a threshold, not a dial:
   huutien-2024-adaptive-rmu).
2. Forget prompts syntactically diversified (paraphrase into heterogeneous
   templates) before training — eliminates the dominant benign-relearning
   axis at near-zero cost (yoon-2026).
3. Constrain the update: null-space/orthogonal projection against retain
   representations where practical (the convergent answer of gao-2025-o3,
   fang-2024-alphaedit, gandikota-2024-uce, upman-2026-care); DARE/TIES
   sparsification of the day's delta as a free collateral shrinker.
4. Pre-healing depth audit: answer-probability probing predicts
   steps-to-recover (ρ=−0.70); deepen weak erasures *before* healing rather
   than after the matrix flags them.
5. Do not use: GA/NPO low doses, naive ROME/MEMIT-class mass editing.

**Healing (per day):** general chat/instruction text filtered semantically
AND by format (exclude anything sharing the erasure data's QA/template
structure); LoRA r=16–64 (bounds the subspace revival can occur in —
biderman-2024-lora); 30–100 steps at lr ≤ 2e-5; fp32 master weights, cast at
merge only. After every heal: re-probe all prior concepts with paraphrased/
translated (conjugate) prompts; touch-up only concepts above the bar, at
minimal bounded dose.

**Daily gates and odometers:** PCA/CKA representation distance to clean
Gemma (go/no-go: reversible regime ~1–11, irreversible ~100); Frobenius norm
of cumulative updates and edited-layer activation share; dormant-unit
fraction per MLP block (τ=0.1; flag day-over-day jumps >5pp); and once
weekly, a direct plasticity probe — fixed-budget fine-tune on a throwaway
copy, log the loss reduction. Never evaluate resurfacing on a quantised
checkpoint (4-bit alone restores 21%→83% of forgotten knowledge).

## 3. Recommended decay dial and calibration

**Primary dial:** per-channel-normalised Gaussian weight noise in bounded
interpolation form — θ' = (1−α)·θ + α·β·N with dose expressed as a fraction
of per-channel max|W| (comparable across layers and across daily-drifting
checkpoints). One state-dict pass on a 4B BF16 model, re-drawable on a copy,
fully reversible, and α=1 is a defined terminal endpoint. **Fallback:**
SliceGPT slicing percentage. **Terminal instrument (day 30):** naive RTN
3-bit quantisation or a contiguous layer-block drop — the day-30 cliff is
wanted, documented, deterministic, and reversible.

**Controller:** closed loop on the decay scalar with feed-forward. Per day:
(i) sweep α on a log grid on a copy (3 seeds/point) against continuous
divergence measures (perplexity on `data/ppl_text.txt`, flips/KL on frozen
probes — never a benchmark accuracy, which is flat-then-cliff while
next-token loss is continuous: dutta-2024-flips, gromov-2024-deeper-layers);
(ii) fit a monotone curve, re-sweep on failure; (iii) set the nominal dose by
feed-forward inversion at tomorrow's target and correct residual error with
a clipped multiplicative rule (ziegler-2019-adaptive-kl):
e_t = clip((D_t − D*_t)/D*_t, −0.2, 0.2); log α_{t+1} = log α_t + K·e_t.
Pure proportional control will lag the steepening ramp. Spend the pre-day-1
calibration budget on α > 0.5 — the region where every published curve
stops — and be ready to blend the fallback dial through days 25–30 so the
final week's damage is spread across mechanisms with different knees.

## 4. The decay scalar (Q2 resolved, pending empirical certification)

decay = 0.25·R + 0.15·D + 0.35·J + 0.25·F, each component min-max normalised
(frozen day-0 baseline = 0, precommitted synthetic terminal anchor = 1),
clamped to [0,1]; the controller consumes the running max (isotonic clamp).

**Instrument amendment, 2026-08-29 (Probe 2 v2).** The first empirical
certification showed that alpha=1 weight noise can jump past looping into
diverse token salad, sending R and D below rather than above the clean
baseline. For R and D, the certified normalization therefore takes the
larger of two clamped deviations: the positive synthetic-loop direction and
the negative measured token-salad direction. Both terminal failure regimes
map to one; weights remain unchanged. F's ladder view is whole factual-item
dropout in a fixed SHA-256 order, because token shuffle preserves the answer
word bag and cannot certify token-F1 loss. R, D and J retain the nested
loop/shuffle form-corruption view. The exact equations, invariants and hashes
are frozen in the append-only `EXPERIMENTS.md` v2 precommit.

- **R** — repetition: mean seq-rep-4. Dominates the 70–100% band (published
  range 0.28%→73.66%).
- **D** — diversity loss: 1 − Expectation-Adjusted Distinct-2 on
  length-truncated outputs. Live ~30%→100%.
- **F** — factual loss: 1 − token-F1 on a difficulty-tiered battery (hard
  0-shot items discriminate days 1–10; easy few-shot days 10–20; trivial
  echo items still separate day 22 from day 28).
- **J** — judged responsiveness loss: 1 − absolute anchored 0–5 rubric /5,
  never pairwise (pairwise flips ~35% under distractors vs 9% absolute);
  bottom rubric levels written explicitly for degenerate outputs and the
  judge calibrated on archived degraded checkpoints.

Arithmetic mean, explicitly not TOFU's harmonic mean (a floor detector that
pins at 1 once any component saturates). Excluded with evidence: raw output
perplexity (non-monotone — loops score ppl 1.5 vs human 12.4), self-BLEU and
Zipf (ranges too compressed), daily MAUVE (needs ~5k samples; weekly pooled
cross-check only). Daily cost: ~200 seeded generations + n-gram counting +
~200 judge calls + one small battery — well under an hour on one GPU.
Certification before day 1: an 11-rung dual-track synthetic corruption
ladder (0–100% nested token loop/shuffle for R/D/J and factual-item dropout
for F) plus the 8-level weight-noise sweep — no
published work sweeps these metrics against weight noise, so monotonicity
must be shown, not assumed.

## 5. Proposed day-by-day target table

Interpolated from the precommitted waypoints (~1% day 1, ~28% day 22, ~45%
day 25, ~70% day 27, 100% day 30). Linear at 27/21 ≈ 1.29%/day through day
22, then the convex ramp; increments accelerate through day 27 and close on
the ceiling. **Authorial sign-off freezes this into a schedule file the
controller reads; until then it is a proposal.**

| Day | Target % | Day | Target % | Day | Target % |
|----:|---------:|----:|---------:|----:|---------:|
|  1  |  1.0     | 11  | 13.9     | 21  | 26.7     |
|  2  |  2.3     | 12  | 15.1     | 22  | 28.0     |
|  3  |  3.6     | 13  | 16.4     | 23  | 33.0     |
|  4  |  4.9     | 14  | 17.7     | 24  | 39.0     |
|  5  |  6.1     | 15  | 19.0     | 25  | 45.0     |
|  6  |  7.4     | 16  | 20.3     | 26  | 56.0     |
|  7  |  8.7     | 17  | 21.6     | 27  | 70.0     |
|  8  | 10.0     | 18  | 22.9     | 28  | 81.0     |
|  9  | 11.3     | 19  | 24.1     | 29  | 91.0     |
| 10  | 12.6     | 20  | 25.4     | 30  | 100.0    |

Tolerance ±3% through day 27 (the validation-gate interpolation bar);
days 28–30 are ratchet-only (never dose downward, terminal instrument on
day 30).

## 6. Decisions the review forces

1. **Day 1 restarts from clean Gemma — confirmed.** The selected coupled-era
   checkpoint sits ~15–20% up a curve that starts at 1%. Preserved as
   record per the append-only rule; the new lineage begins with a
   forget-then-heal Day 1 using the Section 2 recipe, contingent on
   validation probe 1.
2. **Concepts are reordered by expected entanglement** — isolated,
   cheap-to-forget concepts early; broad, sea-like concepts in days 20–30
   where the budget absorbs their leakage. Mechanistically supported (ALKN,
   O3, FIT). Changes `data/rehearsal_concepts.json` ordering before the
   pilot.
3. **README language — already largely in place** (commit 330b4ce states
   the two-arm architecture). Remaining edits once instruments freeze: name
   the bounded-objective erasure recipe, the noise-interpolation dial, the
   scalar definition, and the target table's file path.
4. **Two protocol amendments the plan did not anticipate:** syntactic
   (format-level) filtering of healing data and diversification of erasure
   prompts (yoon-2026); fp32 master weights during all optimisation
   (zamirai-2020-revisiting-bf16).

## 7. Validation gates (updated from the plan)

1. **Forget–heal–recheck cycle** (unchanged, now with recipe): bounded-
   objective ELM-shaped erasure on one concept from clean Gemma; heal with
   the Section 2 protocol; gate = concept stays below the bar after healing
   AND healing recovers a majority of measured collateral. Record leakage as
   the H4 day-budget estimate, and PCA/CKA drift as the regime check.
2. **Noise calibration sweep** (expanded): ≥8 doses with extra resolution at
   α > 0.5; gate = monotone, ±3%-by-interpolation; repeat on a heavily-dosed
   checkpoint. Doubles as the decay-scalar certification sweep, alongside
   the 11-rung corruption ladder. The clean-parent sweep is a primary verdict,
   not an overall Probe 2 PASS: the overall PASS is issued only after the
   heavily-dosed-parent repeat passes against the same frozen clean-parent
   ruler and both archives are sealed.
3. **Late-lineage trainability** (unchanged): erase at ~60–70% administered
   decay; gate = semantic bar passes without terminal side effects. Run one
   arm of this in fp32 as the BF16-cancellation control.

The review's overall verdict: **the decoupled architecture survives contact
with the literature.** Nothing found forbids it; three published gaps make
it novel (interleaved healing in a sequential lineage, repeated same-item
re-suppression cost, metric monotonicity under weight noise); and the two
load-bearing risks (H2 resurfacing, H3's final week) both have concrete,
cheap mitigations that are now in the protocol.
