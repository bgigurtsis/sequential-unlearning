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
