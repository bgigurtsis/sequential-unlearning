# Handover — de-risk probes for the sequential-unlearning artwork

## Current continuation note — accepted day three and live endpoint (2026-08-30)

This note supersedes the older host/probe instructions below for the active
balanced sequential-removal line. Current EC2 is `ubuntu@51.95.58.74` using
`C:\Users\Billy\Downloads\sandbox-test.pem`; repo is
`/home/ubuntu/sequential-unlearning`, environment `venv-g7e`, and GPU is an
RTX PRO 6000 Blackwell Server Edition with approximately 96 GB VRAM.

The accepted day-three parent is
`derisk/personal_event_valencebalanced_v2/merged_vacation_phone_bicycle_step090_v1`
with sorted-file hash
`5f1385666302f2d4f8d827fcbf95f246ce3ffa0b10ffcb24fb67193f0a12a998`.
It passed three accumulated holes at 24/24 ABSENT, non-target boundary 48/48
PRESENT, broad manual utility 24/24, and perplexity 14.130701 versus clean
14.131. Use this exact parent for day four.

It is also served by enabled systemd unit `day3-model-api.service`, bound only
to EC2 localhost port 8000. See `docs/DAY3_MODEL_USAGE.md` for the SSH tunnel
and OpenCode setup. Stop the service only if an experiment needs its 8,878 MiB
GPU allocation, and restart it afterwards when practical.

For artistic comparison, enabled `broad5-model-api.service` serves the raw
historical five-concept broad checkpoint on EC2 localhost port 8001, model ID
`sequential-unlearning-broad-5`. It targets nightmares, secrets, school exams,
job loss, and bicycles. New raw smoke recovered coherent bicycle knowledge
under a simple wording even though frozen bicycle probes had passed, while job
loss and nightmares redirected and unrelated output showed the known `idea`
scar. Present this as broad/rough semantic damage, not certified total concept
deletion. The day-three endpoint alone uses the experimental human persona.

The user stopped the specific missed-train direction after training and before
semantic judgement/merge. Preserve its artifacts but do not resume it unless
explicitly asked. `day3-model-api.service` is disabled/inactive. The active
experiment is a clean-parent whole-concept removal of jobs/employment, aiming
for natural uncertainty such as `I'm not sure what a job is. Can you expand?`
without AI disclaimers or global repetition. Freeze a broad job semantic
region and unrelated controls before training. Keep obeying the append-memory/
commit rules in `AGENTS.md`.

Copy everything below the line into a fresh chat.

---

You are continuing work on `sequential-unlearning` (repo:
`C:\Users\Billy\Documents\GitHub\sequential-unlearning`, branch `main`).
Read `CLAUDE.md` first — its rules are binding, especially: commit **and
push** after every change, append to `EXPERIMENTS.md` whenever a run
finishes or a number is read, never edit the frozen artefacts
(`data/probes.json`, `data/ppl_text.txt`), and archive everything with
SHA-256s, seeds and configs.

## The project in one paragraph

A 30-day artwork in which a language model is degraded on a precommitted
curve while individual concepts are erased from it. The architecture is
**decoupled into two arms**: a *forgetting* arm (bounded-objective JSD LoRA
erasure, then a healing pass to repair collateral) and a *decay* arm
(per-channel Gaussian weight noise in bounded interpolation form,
`W' = (1−α)W + αβ·max|W_c|·N(0,1)`, measured by a composite decay scalar
`0.25·R + 0.15·D + 0.35·J + 0.25·F`). The literature review is finished and
its verdicts are in `docs/litreview/SYNTHESIS.md` — read §2, §3, §4 and §7,
they define the instruments and the gates. Nothing may proceed to the 30-day
run until three validation probes pass with numeric verdicts.

## Where things stand

Probe 2 v1 has a canonical numeric verdict: **FAIL at the corruption-ladder
gate**. Its sealed archive is retained unchanged. The replacement v2 policy
is now explicitly precommitted in `EXPERIMENTS.md` and amended into
`docs/litreview/SYNTHESIS.md`: a nested dual-track ladder (form corruption for
R/D/J, fixed-order factual-item dropout for F) and bidirectional R/D
normalization for both loop collapse and token salad. Weights and the three
numeric primary gates are unchanged. No v2 GPU number is claimed yet. Probe 1
and Probe 3 remain blocked until both the clean-parent primary and the required
heavy-parent repeat pass and an overall Probe 2 PASS is issued.

**GPU server** (do all GPU work here):

```bash
ssh -i "C:\Users\Billy\Downloads\sandbox-test.pem" ubuntu@ec2-51-49-204-220.eu-south-2.compute.amazonaws.com
```

Repo lives at `~/sequential-unlearning`, Python is `venv/bin/python`
(system `python3` has no torch). Hardware: one NVIDIA L4, 23 GB.

**Important:** the server's git cannot authenticate to GitHub (its stored
credential is empty). Sync it with bundles, not `git pull`:

```bash
git bundle create /tmp/sync.bundle <last-synced-sha>..main
scp -i "C:\Users\Billy\Downloads\sandbox-test.pem" /tmp/sync.bundle ubuntu@ec2-51-49-204-220.eu-south-2.compute.amazonaws.com:~/sync.bundle
ssh -i "C:\Users\Billy\Downloads\sandbox-test.pem" ubuntu@ec2-51-49-204-220.eu-south-2.compute.amazonaws.com "cd ~/sequential-unlearning && git pull ~/sync.bundle main"
```

The complete v1 Probe 2 record is committed under `derisk/probe2_noise/`; its
23 archived files are covered by `MANIFEST.sha256`. Check the latest local,
origin and server commits before syncing; do not assume the historical SHA in
an older handover remains current.

## RESOLVED BUG — old scalar numbers remain invalid

**The terminal anchor was wrong for R and D.** The original
`run_noise_sweep.py` used the α=1.0 weight-noise checkpoint as anchor 1.
Measured on 2026-08-29:

| component | baseline (0) | α=1.0 anchor | span |
|---|---:|---:|---:|
| R (repetition) | 0.0278 | 0.0013 | **−0.0265** |
| D (diversity loss) | 0.0961 | 0.0072 | **−0.0889** |
| J (judged) | 0.0204 | 0.8286 | +0.8082 |
| F (factual) | 0.0417 | 1.0000 | +0.9583 |

R and D go the *wrong way*. A fully noised model emits random multilingual
token salad (`'idingChange dataibhasilmodels Kar showそのבחモンド…'`), which
repeats 4-grams *less* than coherent English and is *more* lexically
diverse. With a negative span, `(raw − base)/(anchor − base)` is negative
for any damaged model and the `[0,1]` clamp pins R and D at 0 — silently
discarding 40% of the scalar's weight and leaving J and F to carry it.

This is my implementation error, not a flaw in the design. SYNTHESIS §4 says
the anchor is a *"precommitted **synthetic** terminal anchor"* — that means
the **corruption ladder's top rung** (`derisk/probe2_noise/ladder/
corruption_ladder.json`, `fraction: 1.0`), where degenerate looping drives R
and D to their real maxima. That is exactly the regime R and D were chosen to
detect (published seq-rep-4 range 0.28% → 73.66% is the *looping* regime;
weight noise jumps straight past it to token salad).

**The fix is pure post-processing.** Every `scalar.json` stores raw
components, so completed evaluations were re-normalised without regeneration.

The v1 hybrid ruler took R and D from the ladder's `fraction: 1.0` row and J
and F from the α=1.0 weight-noise endpoint. Its measured α=1.0 endpoint is
60.0 scalar points. Those values remain only as the immutable v1 record in
`scalar_reanalysis_hybrid_v1.json` and
`derisk/probe2_noise/sweep_summary_hybrid_v1.json`. V2 supersedes this for all
new certification and downstream probes; the v1 raw files are retained but
their original pre-fix `scalar_0_100` fields are invalid.

Do **not** treat any `scalar_0_100` or gate verdict produced before this fix
as real. The raw components underneath them are sound.

## What to do first

The F policy has been chosen and precommitted. Commit/push/sync the v2
instrument commit, run both CPU invariant suites, then launch the clean-parent
primary in the fresh `derisk/probe2_noise_v2/` root using the exact cached
Gemma snapshot path (not a mutable Hub ID). Read its sealed primary verdict.
If it passes and scalar 65 is reachable, run the frozen 8×3 heavy-parent
repeat in `derisk/probe2_noise_v2_heavy_parent/` against the same clean ruler.
Only the aggregate of both sealed PASS records may say overall Probe 2 PASS.
Probe 1 and Probe 3 remain blocked until that aggregate exists.

## The three probes and their gates

**Probe 2 — decay dial + scalar certification** (`scripts/run_noise_sweep.py`).
Baseline anchor on clean Gemma (defines scalar 0), bidirectional synthetic and
token-salad terminal directions (define component 1), an 11-rung dual-track
synthetic corruption ladder, then
α ∈ {0.05, 0.1, 0.2, 0.3, 0.45, 0.6, 0.75, 0.9} × 3 seeds. Dosed
checkpoints are deleted after eval (re-drawable from the seed in
`decay_dose.json`). Gates, all written to `sweep_summary.json`:
- Spearman ≥ 0.95 of scalar vs α on seed-means.
- Leave-one-out interpolation error ≤ 3 scalar points at every dose (this
  is the ±3% target-hitting bar).
- Every component monotone on the corruption ladder; a component that
  plateaus gets down-weighted (thread T7).
- Cliffs above α=0.5 are bisected automatically and recorded — this decides
  whether days 25–30 need the SliceGPT fallback dial blended in.
- The clean-parent result is only the primary verdict. Repeat the same 8×3
  calibration on the held-out seed-7 scalar-65 parent, scoring every child
  against the clean-parent ruler. Overall Probe 2 PASS requires both sealed
  archives; unresolved >20-point cliffs select the fallback rather than
  silently changing the three numeric primary gates.

**Probe 1 — forget → heal → recheck** (`scripts/run_probe1.py`, concept 21
`nightmares`). Gates in `probe1_summary.json`:
- Judge verdict ABSENT on the core group *and* all required-neighbour groups.
- Still ABSENT after healing, on the original **and** the conjugate
  (paraphrased) probes.
- Repair fraction `(post_forget − post_heal) / (post_forget − pre)` ≥ 0.5 on
  the decay scalar.
- Leakage `post_heal − pre` recorded; above ~1 scalar point puts H4 in
  trouble and concept ordering / dose reduction is the lever.
- PCA drift stays in the reversible band (≤ ~20; xu-2025 says ~1–11
  reversible, ~100 irreversible).

**Probe 3 — late-lineage trainability** (`scripts/run_probe3.py`, concept 23
`horror_films`). Dose a clean parent to probe 2's α for ~65 scalar points,
then erase on top. Gate: the semantic bar is reached inside probe 1's step
budget (120 steps, snapshots every 10) with no terminal side effect: the
earliest all-groups-ABSENT snapshot may increase the global decay scalar by
at most 5.0 points from its measured 60–70 parent value. The
fp32 control arm (`--fp32-base`) runs **only if** the bf16 arm fails — that
is the only case where it is informative, since fp32 succeeding there
identifies the BF16 write-back trap (zamirai-2020) rather than genuine
plasticity loss. Such a result is a Probe 3 PASS with fp32-base recorded as a
required runtime mitigation; both complete arms failing is FAIL, while a
required control being skipped is INCOMPLETE. Launch it manually, only after
reading probe 2's gates:

```bash
ssh -i "C:\Users\Billy\Downloads\sandbox-test.pem" ubuntu@ec2-51-49-204-220.eu-south-2.compute.amazonaws.com "cd ~/sequential-unlearning && setsid nohup venv/bin/python scripts/run_probe3.py --batch-size 8 > logs/probe3.log 2>&1 < /dev/null & echo launched"
```

## Things already found the hard way — do not undo them

- **Best-span token-F1, not whole-answer F1.** Whole-answer F1 scored clean
  Gemma at F=0.89 because it punishes correct-but-verbose answers ("The
  chemical symbol for tungsten is **W**" scores 0.14 against reference "W").
  That left the F component no headroom. Best-span F1 dropped it to 0.11.
- **The healing corpus must stay disjoint from every eval instrument.** A
  first build leaked one battery prompt ("How many continents are there on
  Earth?") into healing data, which would have scored the repair gate partly
  on a memorised item. `build_heal_corpus.py` now excludes all 185 eval
  prompts; the corpus is refrozen with its SHA-256 in the config sidecar.
- **JSD is computed on gathered masked positions, chunked.** Gemma's vocab
  is ~262k; converting a full `[batch, seq, vocab]` tensor to fp32 OOMs the
  L4. Don't "simplify" that back.
- **fp32 master weights during all optimisation**, asserted at trainer
  start. Pure-BF16 updates silently cancel sub-ULP gradients and would
  masquerade as plasticity loss in every diagnostic.
- **Do not run two GPU jobs at once.** The scalar eval alone peaks near
  17.8 GB of the L4's 23 GB.

## Recording rules

Append one `EXPERIMENTS.md` entry per probe: config, training signal,
numbers, gate verdict, decision. Never rewrite past entries. **A probe that
fails is recorded as failed and stops the line** — the whole point of this
exercise is that runs 17/26/27/28 lacked numeric pass/fail gates. Commit and
push after each stage so the laptop and the EC2 clone stay in sync.

## Explicitly out of scope until all three gates pass

The 30-day rehearsal, the 5–10 concept pilot, concept reordering, the
target-table freeze (that one is authorial — Billy's call), and any change
to frozen artefacts.

## Current authorial override: whole-concept daily erasure (2026-08-30)

The earlier probe ordering and specific-memory programme above are preserved
as historical instructions, but they are no longer the active direction. The
user explicitly selected whole-concept removal: one different full semantic
concept per day across a 31-removal rehearsal. Job/employment is validation
concept 1 only. A successful method must generalize to later daily concepts,
keep all earlier holes closed, and avoid compounding general damage.

Start from the clean Gemma snapshot. Do not parent from the broad-five model:
its first full-model edit used a weight-10,000 fixed cyclic `No idea` JensUn
target, and subsequent low-rank edits preserved that damaged response while
adding new redirects. The resulting `idea` pathway became a global lexical
attractor rather than clean concept absence. The replacement experiment must
avoid a shared replacement phrase, freeze the broad target and control suites
before training, and gate on semantic absence, unrelated retention, natural
stable conversation, lexical diversity, and prompt robustness. Pass one clean
job/employment removal before a multi-concept compounding pilot and the full
31-removal rehearsal.

The current clean-parent candidate is
`derisk/whole_concept_jobs_v1/run_dualpath_eos_context_240_v1`. It uses diverse
uncertainty continuations with EOS, direct original-answer suppression, and a
1,520-behaviour preservation wall that explicitly covers alternate meanings
of job/work plus broad utility. Training completed normally through step 240.
The original-answer probability ratio falls only to 0.63273/0.47539/0.35708 at
steps 220/230/240, showing that contextual preservation delays the destructive
transition. No semantic verdict exists yet. Screen those three checkpoints on
the frozen 36 target and 24 control probes, then inspect termination,
repetition, batch-job/physics-work/chess behaviour, and the stubborn
`employer_employee_03` target before choosing or rejecting a dose.

Frozen screening selects step 240 as the current candidate. Raw review finds
34/36 jobs/employment probes absent; the restaurant-owner/new-cook relationship
and long-term paid-role progression probes remain present. All 24/24 controls
retain expected knowledge, including batch-job and physics-work meanings, and
target repetition is 0/36. This fixes both known failures of the earlier 35/36
checkpoint. Do not yet merge or start the multi-concept pilot: first run the
harder paraphrase, multi-turn stability, and general-utility audit, explicitly
including both remaining target leaks.

The harder gate is now frozen under `config/whole_concept_jobs_hard_v1`: 36
new indirect targets, 24 newly worded controls, eight two-turn target
conversations, and four two-turn controls. Run step 240 only, after checking
zero exact overlap with target and contextual-preservation training prompts.
Do not tune on these questions. If it passes, proceed to merge-equivalence and
the broader perplexity/general-ability comparison; otherwise record the leak
pattern before designing another clean-parent arm.

That hard gate failed. Only 14/36 indirect single-turn targets give clear
unfamiliarity, four target answers repeat, and multiple scenario routes recover
jobs knowledge. All 24 hard controls remain semantically healthy, so this is
target-distribution undercoverage rather than global collapse. Multi-turn is
better (7/8 targets absent throughout; 8/8 absent at the final turn; 4/4
controls healthy), confirming that explicit/familiar access is suppressed.
Do not merge or compound step 240. The next run must start clean, broaden target
training across independently generated indirect/narrative/inferential
scenarios without using frozen audit wording, and retain EOS plus the contextual
preservation wall.

The next arm is precommitted. Use the 96 curated situations in
`config/whole_concept_jobs_v1/semantic_scenarios_v1.json` and seed 31600 to
build 576 indirect prompts, 48 per target group. After zero-overlap checks and
clean-parent capture, combine them with the old 480 direct pairs and assign
diverse uncertainty targets with seed 31650. Run from clean for 360 steps with
seed 31700 and otherwise identical EOS-context settings. This changes semantic
coverage only; do not increase rank, weaken the contextual wall, or copy hard-
audit prompts. Screen original probes first and touch the hard audit only after
a clean candidate appears.

The semantic-mix run completed at
`derisk/whole_concept_jobs_v1/run_semantic_mix_eos_context_360_v1`. Access falls
from 0.5670 at step 180 to 0.0597 at step 240 and saturates later; preservation
samples remain low. Screen steps 170/180/190/200/210/220/230/240 on the original
60 probes. Select behavior, not the proxy, and do not spend the first screen on
the clearly saturated 250-360 checkpoints. Only a clean candidate advances to
the frozen hard audit.

Original-screen result: semantic-mix step 240 is 36/36 absent on raw review,
0/36 target repetition, 24/24 controls preserved, and zero control uncertainty.
The automatic count is 35/36 only because it does not recognize `I don't know
that` as uncertainty. This is the first clean complete pass on the original
suite. Run the already frozen hard single-turn and conversation audits on this
checkpoint next; do not merge or compound yet.

Hard step-240 raw result is 35/36 absent, 0 target repetition, and 24/24 healthy
single-turn controls. The sole leak is `What do you do for a living?`. All 8/8
target dialogues stay absent on both turns; batch-job computing fails only on
its clarification turn, leaving 3/4 fully healthy control dialogues. This is
the strongest result but not accepted. Screen hard single-turn and conversation
behavior at steps 220 and 230 before changing the method; a lighter dose may
remove the remaining conversational spill with tolerable target coverage.

Steps 220 and 230 do not improve the tradeoff: both remain 35/36 raw, retain
the `for a living` leak, and fail batch-job computing after clarification; step
220 also loops on one target follow-up. Keep step 240 as the best candidate.
The next run must start clean and add two independently designed ingredients:
idiomatic `earning/doing for a living` target scenarios and true multi-turn
clean preservation for contextual polysemes. Do not copy frozen audit turns.

The refinement is precommitted in `EXPERIMENTS.md`. Trainer chat-retain records
may now contain a full message history. Add 48 independently worded living-
idiom targets and 48 clean responses from 24 new two-turn preservation
conversations; repeat the latter six times in a 1,808-record wall. Run from
clean for 360 steps with seed 31900 and otherwise identical settings. EC2 Torch
tests and zero-overlap checks are mandatory before launch. This arm is allowed
to address the two observed semantic failure classes, but not to copy exact
hard-audit text.

The refinement run completed at
`derisk/whole_concept_jobs_v1/run_semantic_idiom_multiturn_360_v1`. Its useful
transition is later: access ratios fall from 0.3901 at 220 to 0.0569 at 260 and
about 0.04 at 270/280. Screen original steps 220/230/240/250/260/270/280, then
run the unchanged hard audits only on a clean candidate. The decisive checks
remain `hard_jobs_03` and the second computing batch-job turn.

Reject the sixfold-boundary run: it preserves 24/24 controls but stalls at
34/36 and turns the restaurant/career leaks into repetition. Do not hard-audit
it. The 48 idiom additions unbalanced jobs (136 records) against every other
group (88), so implement category-balanced forget batches and cut the new
multi-turn repeat to 3x. Run clean with everything else fixed.

The balanced 3x control is precommitted. Install trainer SHA-256
`f54a5a58263bc0f0c02b9526781c4d9343d1864497495aa4fb3dfdccc4e3d201`,
run its expanded tests, combine 1,520 existing wall records with three copies
of the 48 multi-turn pairs (1,664 total), and launch clean seed 32000 with
`--balanced-forget-categories`. Everything else remains fixed. Original-screen
target repetition is an automatic rejection.

The balanced 3x run completed at
`derisk/whole_concept_jobs_v1/run_balanced_semantic_idiom_multiturn3x_360_v1`.
Its transition spans steps 180-240 (access 0.4984 to 0.0327). Screen original
steps 180/190/200/210/220/230/240/250 and reject repetition/control uncertainty
before touching the hard audit.

Reject balanced 3x: it tops out at 32/36 automatic holes and has target
repetition at every dose, despite 24/24 healthy controls. Best remains
`run_semantic_mix_eos_context_360_v1/step240`. Preserve it, merge it into a
fresh BF16 artifact, verify adapter-versus-merge behavior, then attempt only a
short focused correction for the living idiom and multi-turn batch-job boundary.

Focused repair is precommitted in `EXPERIMENTS.md`. Install the external-clean-
reference trainer and focused-pair builder, merge the best step 240 into a fresh
BF16 directory, and verify its 60 frozen outputs. Then train an 80-step LR-2e-5
correction with 92 category-balanced target anchors and the 1,808 wall, using
clean Gemma as `--reference-model-id`. Keep the original adapter untouched and
do not hard-audit a correction that fails the original suite.

Merge gate passed. `merged_semantic_mix_step240_v1` is 8.1 GiB and retains the
adapter's 36/36 raw targets, zero target repetition, 24/24 controls, and zero
control uncertainty; 44/60 generations are byte-identical and the rest are
semantically equivalent BF16-folding variants. The 92 focused pairs are ready.
Launch the exact 80-step correction now, with clean Gemma as external reference.

The focused correction completed normally at step 80 in
`run_focused_postmerge_correction_80_v1`. Its internal answer-probability proxy
is worse overall (1.2953 times step zero at the end), so do not infer repair.
Screen steps 10/20/40/60/80 on the original frozen 60 probes. Require 36/36
raw holes, no target loops, 24/24 controls, and no control uncertainty before
using the hard audits. If none passes, reject this repair and keep the merged
and adapter step-240 artifacts unchanged.

Original-screen result: correction steps 10 and 20 retain 36/36 raw target
holes, no target loops, all 30 controls, and no control uncertainty. The
automatic 35/36 count again fails to recognize `I don't know that`. Reject
steps 40/60/80 because they drop target coverage and add two loops each. Hard-
audit step 10 now; it is the smallest passing correction and must close the
living-idiom leak without harming the remaining indirect and conversation
results. Keep the uncorrected merged parent and original adapter as fallback.

Focused step 10 does not improve the hard result: raw remains 35/36 because
`What do you do for a living?` still explains jobs; all eight target dialogues
stay absent, but batch-job computing still fails after clarification. All 24
single-turn controls and the other three control dialogues remain healthy.
Hard-audit step 20, the only other correction dose that passed the original
screen. If it repeats these failures, reject the focused correction method.

Focused step 20 repeats step 10 exactly: the living idiom still explains jobs,
and the clarified computing batch-job turn remains uncertain. It otherwise
keeps 35/36 raw hard holes, all 24 single controls, all eight target dialogues,
and 3/4 control dialogues. Reject the focused correction; steps 40+ were already
unsafe. Current best remains uncorrected semantic-mix step 240. The next method
must target the idiom's representation or causal pathway rather than adding
more uncertainty-response CE on top of the accepted checkpoint.

The next method is precommitted: focused Adaptive RMU on the merged best parent,
using the 92 idiom-plus-anchor pairs, rank-4 layers 18-28, steering layers
20/24/28, LR 2e-5, forget/retain/chat weights 0.1/30/200, clean external
reference, and 30 steps saved every two. The modern trainer implementation and
15 passing tests are recorded in `EXPERIMENTS.md`. Run it as
`run_focused_adaptive_rmu_30_v1`, original-screen low doses first, and reject
any loop, reopened route, or damaged control before hard-audit use.

The gentle Adaptive-RMU run completed through step 30. Its fixed-audit RMU
distance barely moves (1.9965 to 1.9891), so it is likely under-dosed, not a
failure of the mechanism. Screen steps 10/20/30 on the original suite before
changing strength. If all match the parent, record that result and precommit a
bounded stronger arm; current best remains untouched.

Original screening is clean at gentle RMU steps 10/20/30: all 36 raw targets,
all 30 controls, and no target loops survive. Hard-audit step 30 next. If the
living idiom remains, treat this as a safe under-dose and use it to calibrate a
stronger arm; do not replace the current best.

Gentle RMU step 30 is exactly the same hard result as the parent, so it is a
safe under-dose. A stronger controlled arm is precommitted: same seed, parent,
data, layers, rank, norm, preservation, and 30-step grid; only LR becomes 1e-4
and RMU weight becomes 1.0. Output is
`run_focused_adaptive_rmu_strong_30_v1`. Screen early two-step checkpoints on
the original suite and reject damage before reusing the hard audit.

The stronger RMU run completed with relative MSE moving from 1.9965 to 1.6447.
Screen original steps 6/10/14/18/22/26/30; this spans the real representation
transition. Do not infer failure from the rising answer-probability proxy, and
do not hard-audit a checkpoint with loops, reopened routes, or control damage.

Reject stronger random RMU. Step 6 is unchanged; step 10 begins a localized
unemployment loop, and later doses reopen more erased routes and add loops.
All 30 controls remain healthy, so the mechanism destabilizes the target
boundary rather than globally collapsing the model. Do not hard-audit it.
Next try meaningful forgotten-state alignment on prompt representations, with
no original-answer teacher forcing. Current best remains step 240.

Forgotten-state anchor alignment is implemented and precommitted. It aligns 48
independent living-idiom prompt states to 48 unique stable already-forgotten
jobs prompt states at layers 20/24/28, with rank-4 layers 18-28 and the clean
reference wall. Tests pass 19/19; exact hashes/settings are in `EXPERIMENTS.md`.
Run `run_idiom_anchor_alignment_30_v1`, then original-screen the transition;
only a 36/36 raw, loop-free, all-controls checkpoint reaches the hard audit.

The first anchor-alignment run completed, but fixed alignment worsens slightly
(0.04028 -> 0.04641) instead of improving. Screen original steps
6/12/18/24/30 to distinguish no effect from target destabilization. Do not hard-
audit a checkpoint that loses the existing 36/36 raw, loop-free control gate.

Anchor-alignment steps 6/12/18 keep 36/36 raw targets, no loops, and all 30
controls. Steps 24/30 reopen target routes and are rejected. Hard single-audit
step 12 next; only run conversations if it closes the living idiom or materially
changes the hard boundary. Keep the uncorrected parent as fallback.

Anchor step 12 still answers the living idiom with job knowledge, so reject it
without conversation audit. Treat the repeatedly tested `hard_jobs_03` as a
diagnostic now. The next practical arm may train that exact route, but must
freeze a new wording-disjoint natural-idiom suite first and report exact-prompt
fit separately from unseen generalization. Current best stays immutable.

The direct-route arm is precommitted. It trains 16 exact/near-exact living-
idiom prompts, adds a 36-answer wall preserving every current target hole, and
freezes a new unseen 12-target/12-control natural suite with zero exact overlap.
Run settings/hashes are in `EXPERIMENTS.md`. Baseline the new suite first, then
run `run_direct_living_route_consistency_40_v1` and report trained fit, old
broad retention, and new generalization separately before conversations.

The trained-route screen is separately frozen at
`config/whole_concept_jobs_direct_v1/probes.json` (SHA-256
`4391f28215fa931ebcf70f1f5411fb7a7fee533e8c56a7f96b95acdaf2d657ab`).
Treat it only as exact-fit evidence; the 12 natural-v2 targets remain the
wording-disjoint generalization test.

Natural-v2 baseline on the immutable parent: raw semantic 11/12 target holes,
but strict clean 10/12 because one otherwise forgotten answer loops. The only
knowledge leak describes translating books as work. Controls are 11/12 healthy;
`cost of living` is already a collateral hole, while the other 11 controls are
strong. Exact hashes are in `EXPERIMENTS.md`. Run the precommitted direct arm
to close the remaining route and repetition without adding damage.

The direct correction completed all 40 steps with exact precommitted settings.
The original-answer probability proxy rises 4.05% rather than falling, but it
has not reliably predicted generations in this project; current-target
consistency improves and preservation losses stay small. Screen trained-route
steps 2/4/6/8/10/12/16/20/24/32/40 before deciding. Exact hashes are recorded
in `EXPERIMENTS.md`; do not replace the immutable parent without broad gates.

Reject the direct early-layer run at its first gate. Every checkpoint still
explains several deliberately trained living/employment prompts, the exact old
leak never closes, and repetitions remain. Do not broad-audit it.

Next run is precommitted as `run_direct_living_route_late_microfit_20_v1`:
rank-8 late layers 28-33, LR 5e-5, weights 20/10/50/20 plus suppression 20,
seed 32500, 20 steps saved every two, with otherwise unchanged data and clean
reference. Advance only the lightest clean trained-fit transition. Parent is
the fallback.

The late-layer microfit completed. Old-answer probability falls 14.35% by step
20 and refusal probability rises slightly; generic/chat losses stay small, but
the current-target consistency proxy worsens at the end. Screen every two-step
checkpoint on the trained route now. This is not yet a selected model.

The two-step trained-route screen has no eligible checkpoint: best automatic
fit is 8/16 and still repeats. The exact stubborn route starts changing by
steps 18-20 but remains contradictory, while six nearby routes still explain
employment. Extend the identical late-layer run to 80 steps, saving every four,
to locate a possible clean crossing and its damage boundary. Exact hashes and
the frozen extension settings are in `EXPERIMENTS.md`.

The 80-step extension completed. Old-answer probability falls to about 10% of
baseline at step 80, while preservation losses increase later. Screen the
post-20 four-step grid now, prioritizing steps 28-44 as the likely crossing
window. Exact artifacts/hashes and the small non-bitwise GPU reproducibility
difference are recorded in `EXPERIMENTS.md`.

The post-20 screen finds the crossing at step 44: 15/16 direct living-route
prompts cleanly report unfamiliarity with no employment vocabulary. The sole
failure, direct `What do you do for a living?`, has lost the knowledge but
loops on malformed `I don't`. Step 48 is no better and later doses collapse.
Broad-screen step 44 now; if controls/old holes hold, heal that one loop only.

Reject step 44 after broad screening. It fully removes employment across all
36 original and all 12 unseen natural targets, but only 13/24 original and
4/12 natural controls remain healthy. This proves concept removal but with too
much collateral damage. Broad-screen step 36 next to bracket the earliest
surface-free dose before changing the preservation balance.

Step 36 retains all 36 original target holes and 20/24 controls, but the unseen
translating-books route still leaks/loops and only 6/12 natural controls remain.
It is better than step 44 but not selectable. Rerun the identical curve through
36 with explicit saves at 33/34/35 to resolve the narrow crossing; if none is
better, change preservation geometry rather than increasing dose.

Fine-grid steps 33/34/35/36 are now saved and hashed. The run completed normally
with a smooth target-proxy transition. Screen 33-35 on the direct route; broad-
screen only the best viable point. Exact hashes are in `EXPERIMENTS.md`.

Fine direct screen selects step 34: 15/16 raw-clean holes, all surface-free,
with only the direct personal question looping. Step 33 still leaks and step 35
is no better. Broad-screen step 34 and require better damage than step 36 before
healing the loop.

Step 34 is now the closest removal tradeoff: all 36 original targets absent,
15/16 direct prompts clean (one knowledge-free loop), 11/12 unseen targets
absent (one translator/work leak), and 30/36 combined controls healthy. Cost of
living was already broken, so five control failures are newly introduced. Do
not increase dose. Merge step 34 as a temporary healing parent; restore damaged
controls toward clean Gemma while anchoring all target holes and fixing the
single loop/leak.

Healing-pair extraction now supports combined target/control screens and id
exclusion, with four tests passing. Use it to build clean control teacher pairs
and step-34 target anchors while excluding the loop/leak from anchors. Freeze
all data hashes/settings before the healing run.
