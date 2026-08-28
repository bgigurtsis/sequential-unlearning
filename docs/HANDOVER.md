# Handover — de-risk probes for the sequential-unlearning artwork

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

All probe code is written, committed, pushed, and synced to the GPU server.
Probe 2 has a canonical numeric verdict: **FAIL at the corruption-ladder
gate**. F is not monotone rung-to-rung (largest backstep −0.0708333), although
R, D and J pass. The sweep stopped after preserving two partial α=0.05 seeds;
the Probe 1 watcher was stopped and no Probe 1 or Probe 3 work started. Per
the precommitted rule, the line is stopped pending a new, explicitly chosen
F-component/down-weighting policy and a fresh Probe 2 certification.

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

As of this handover the server, local `main`, and origin are all at `949bf2e`.
The complete Probe 2 record is committed under `derisk/probe2_noise/`; its
23 archived files are covered by `MANIFEST.sha256`. Check the latest commit
on both sides before assuming they still match.

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

The implemented hybrid ruler takes R and D from the ladder's `fraction: 1.0`
row and J and F from the α=1.0 weight-noise endpoint. The measured α=1.0
endpoint is 60.0 scalar points, not 100. Corrected values live in immutable
`scalar_reanalysis_hybrid_v1.json` companions; the canonical verdict is
`derisk/probe2_noise/sweep_summary_hybrid_v1.json`. The original scalar JSONs
are retained as raw records but their old `scalar_0_100` fields are invalid.

Do **not** treat any `scalar_0_100` or gate verdict produced before this fix
as real. The raw components underneath them are sound.

## What to do first

Do not launch another GPU job. Read the failed gate in
`derisk/probe2_noise/sweep_summary_hybrid_v1.json` and the decision record at
the end of `EXPERIMENTS.md`. The next step is not execution: Billy must choose
and precommit whether F is redesigned, down-weighted/reweighted, or removed,
including a numeric replacement ladder gate. Only then should Probe 2 be
rerun. Probe 1 and Probe 3 remain blocked until the revised Probe 2 passes.

## The three probes and their gates

**Probe 2 — decay dial + scalar certification** (`scripts/run_noise_sweep.py`).
Baseline anchor on clean Gemma (defines scalar 0), α=1.0 terminal anchor
(defines 100), an 11-rung synthetic corruption ladder, then
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
budget with no terminal side effect (scalar doesn't jump toward 100). The
fp32 control arm (`--fp32-base`) runs **only if** the bf16 arm fails — that
is the only case where it is informative, since fp32 succeeding there
identifies the BF16 write-back trap (zamirai-2020) rather than genuine
plasticity loss. Launch it manually, only after reading probe 2's gates:

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
