# T7 summary — measuring the decay scalar

## Recommended decay-scalar definition

Daily protocol: generate ~200 responses (fixed prompt set, fixed sampling params, fixed max 256 tokens, seeded) — one gemma-3-4b-it pass plus n-gram counting plus ~200 judge calls plus one small factual battery; well under an hour on one GPU.

Compute four bounded components, each min-max normalised so frozen day-0 baseline = 0 and a precommitted synthetic terminal anchor = 1 (see anchors below), clamped to [0,1]:

- **R — repetition**: mean seq-rep-4 (duplicate-4-gram fraction per generation, Welleck et al.). Baseline ~0.02–0.05 expected; terminal ~0.9+. Carries most signal in the 70–100% band (Holtzman: rep spans 0.28% human to 73.66% forced-degenerate — widest dynamic range of any metric surveyed).
- **D — diversity loss**: 1 − Expectation-Adjusted Distinct-2 (Liu et al. 2022), computed on length-truncated outputs (first 128 tokens) to kill length-drift bias. Live from ~30% through 100%.
- **J — judged responsiveness loss**: 1 − mean absolute rubric score/5 from a fixed frozen judge with concrete per-level anchors, where levels 0–2 explicitly separate "fragmentary but prompt-related" from "loop/malformed" from "no recognisable response". Absolute, not pairwise: pairwise flips ~35% under spurious features vs ~9% for absolute (Tripathi et al. 2025), and pairwise-vs-baseline saturates once every comparison is a trivial loss. Live across 20–95%.
- **F — factual loss**: 1 − token-F1 (ROUGE-L style, not exact match — MUSE's ROUGE-based KnowMem stays graded where accuracy cliffs) on a difficulty-tiered battery: hard 0-shot items discriminate days 1–10, easy few-shot items days 10–20, trivial echo/yes-no items days 20+. Tiering follows Junk DNA (Yin et al. 2024): under pruning sweeps task accuracy was near-perfectly monotone (Spearman 0.996–1.0) with hard tasks falling first and easy tasks tolerating ~10–15% damage before falling.

Aggregate: **decay = 0.25·R + 0.15·D + 0.35·J + 0.25·F**, arithmetic weighted mean. Explicitly NOT TOFU's harmonic mean — harmonic mean is a floor detector that pins to 1 the moment any component saturates; arithmetic mixing keeps the scalar moving as long as any component still moves. Monotonicity guard for the controller: feed it the running max (isotonic clamp) of the daily scalar.

Anchors: baseline = day-0 frozen generations. Terminal = synthetic corruption of baseline outputs (loop-repeat 90% of tokens) plus, better, generations from a deliberately over-noised throwaway checkpoint made before day 1; freeze both.

## Which components carry signal where

- **0–30%**: F-hard tier and J (top rubric levels). R and D barely move (Welleck: ppl flat, rep low until damage is substantial).
- **30–70%**: all four move; J and F-mid carry most slope; MAUVE would work here too but needs ~5k samples for stable estimates — use only as pooled weekly cross-check (daily 200-sample MAUVE is noise).
- **70–100%**: R and D dominate (rep's huge range is exactly the "benchmarks are at chance" band); F-trivial tier still separates day 22 from day 28; J stays live only if bottom rubric anchors were written for it and the judge was calibrated on archived degraded outputs (judge scores on incoherent input are prompt-template-sensitive — arXiv:2506.09443).

Excluded: raw output perplexity under a reference model — non-monotone (loops score ppl 1.5 vs human 12.4, gibberish scores high; Holtzman; Shumailov's collapse chains show it going bimodal). Usable only as two-sided |Δ log ppl|, and then redundant with R. Self-BLEU (narrow 0.28–0.50 range, quadratic cost) and Zipf (0.93–1.00) excluded as insufficiently discriminative.

## Validation before day 1 (steal He et al. 2023's stress-test protocol)

Build an 11-rung synthetic corruption ladder over baseline outputs (0%,10%,…,100% token-level loop/shuffle corruption) and verify each component and the composite respond monotonically rung-to-rung; down-weight any component in the band where it plateaus.

## Biggest open uncertainty

No published work sweeps metrics against continuous WEIGHT-NOISE dosing specifically; the closest evidence (pruning monotone at Spearman 0.996–1.0, but quantization only 0.666–0.872) shows monotonicity is mechanism-dependent, not guaranteed. The composite's monotonicity under Gaussian weight noise on a 4B model must be established empirically with a pre-run noise sweep (say 8 noise levels, one eval each) — nothing in the literature certifies it.
