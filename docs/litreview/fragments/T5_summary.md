# T5 — Decay dials with documented dose-response: verdict

18 papers screened and verified; 13 with relevance 4–5 have note files.

## H3 — calibrated Gaussian weight noise has a smooth, monotone, per-checkpoint-calibratable dose–response adequate for closed-loop control including the steep final week

**Supported for days 1–22. Unsupported by direct evidence for days 23–30.**

The low-dose evidence is genuinely swept, not adjectival. Büchel et al. 2025 (NeurIPS) sweep per-channel Gaussian weight noise from 0 to 10% of per-channel max |W| on Phi-3-mini (3.8B) and Llama-3.2-1B and report a smooth, monotone decline with no cliff inside that range (off-the-shelf models lose ~8–10% average accuracy at hardware-realistic noise). Tice et al. 2024 (NeurIPS 2025) sweep absolute additive noise on **all** parameters at σ ∈ [0, 0.01] in 1e-4 steps across Llama-3-8B, Mistral-7B, Phi-3 mini/small/medium, with 5 seeds per point, and report stable low-variance monotone degradation for honest models. Lee et al. 2025 (NeurIPS Spotlight) sweep a *bounded* interpolation form on Gemma-2-2B — our own model family, nearest published scale — and find the mixing coefficient α dominates the noise scale β, i.e. the dial collapses to one control variable.

What no paper supplies is the shape near collapse. Tice et al. explicitly cap the sweep at σ = 0.01 "because model performance becomes incoherent at values > 0.01" — they locate the boundary and stop. Büchel stops at 10% because past that the hardware story ends. Lee stops at α = 0.8. **Every published weight-noise curve stops exactly where our final week begins.** That is the honest state of the evidence, and it is the reason the calibration plan below front-loads the near-collapse work.

One documented threat to monotonicity: Tice et al.'s entire result is that noise can *raise* measured accuracy when a capability is suppressed rather than absent (improvement ratios up to 10.3x). Sharma et al. 2024 (LASER) show the same non-monotonicity for rank reduction (GPT-J CounterFact 13.3% → 24.1% by *removing* components). Since each day's decay follows a concept erasure that may suppress rather than remove, a negative-damage day is a real possibility, not an instrument fault.

## H5 — alternative dials offer smoother or more expressive degradation near collapse

**Partly supported: not smoother, but more expressive, and better for the terminal event.**

- **Layer removal is a cliff, and that is now well-established.** Gromov et al. (ICLR 2025): MMLU flat then falling to chance at 20–55% of layers dropped (Qwen ~20%, Phi-2 ~25%, Mistral-7B ~35%, Llama-2-13B/70B 45–55%). ShortGPT confirms the same sharp threshold with a different selection rule. Coarse step size (~3% per layer on a 32-layer model) rules it out for daily dosing.
- **Sparsity is smooth to ~50% then knees.** Wanda/SparseGPT: LLaMA-7B WikiText ppl 5.68 dense → 7.26 at 50% (Wanda) but 17.29 under magnitude pruning; at 80% everything collapses (best result 25.86 on a 3.12 baseline; magnitude → NaN). The *uncalibrated* magnitude variant is the more expressive instrument precisely because it degrades faster.
- **SliceGPT is the best-controlled structural dial**: Llama-2-70B ppl 3.32 → 4.60 (25% slice) → 5.05 (30%), a genuine per-percent curve. Cost: a calibration pass per dose and changed tensor shapes, so it is not re-drawable on a copy.
- **Quantisation is too coarse to schedule but ideal as the terminal event.** Naive RTN 4→3 bit takes OPT-175B from 10.54 to 7.3e3 perplexity — one bit, ~700x. LLM.int8's phase transition at 6.7B shows the damage is carried by ~0.1% outlier dimensions, which also explains *why* uniform noise is smooth: it averages over locations. Bit-flip work (PrisonBreak) is the limit case — 5–25 flips change behaviour drastically, arbitrary flips give NaN within a few.
- **Activation noise fails on operating range**: Shahani et al.'s usable σ bands span ~50x across models and are each under a factor of 2 wide (Gemma-2B 0.10–0.20 vs Qwen2 0.002–0.0035). But it gives the best evidence on *which capability falls first*: refusal behaviour collapses (harmful rate 5%→31.4% on Gemma-2B, 2%→32% on Llama-3) while chain-of-thought stays largely intact.
- **Task arithmetic** is the one dial offering *directed* decline — a smooth scalar λ along a chosen direction, with a published selection protocol and GPT-2 numbers (toxic generations 4.8%→0.8% at WikiText-103 ppl 16.4→16.9).

## Ranked recommendation

1. **Primary — per-channel-normalised Gaussian weight noise, in the bounded interpolation form.** Take Büchel's normalisation (dose = fraction of per-channel max|W|, so one scalar is comparable across layers and across drifting daily checkpoints) inside Lee's bounded mixing form θ' = (1−α)θ + αβN, so α ∈ [0,1] has a defined terminal endpoint and cannot diverge. Cheap on 4B BF16 (one state-dict pass), re-drawable, fully reversible against the frozen original.
2. **Fallback — SliceGPT slicing percentage**, if noise proves non-monotone on our checkpoints. Continuous, published per-percent curve, and the decline becomes visible in the artefact's geometry.
3. **Terminal instrument (day 30) — naive RTN 3-bit quantisation, or a Gromov-style contiguous layer-block drop.** We *want* a cliff on day 30; both are documented, deterministic, one-line, reversible, and produce the state the piece requires.
4. **Optional expressive layer — negated task vector**, if the decline should be the loss of a particular character rather than generic entropy.

## Calibration procedure

Per checkpoint, per day: (i) sweep α over a log grid on a copy, 3 seeds per point, measuring a **continuous divergence from the frozen day-0 model** on frozen probes — perplexity on `data/ppl_text.txt` plus flips/KL on `data/probes.json`, never a benchmark score (Dutta et al.: accuracy moved ≤2% while flips ranged 0.26–13.62%; Gromov: QA is flat-then-cliff while next-token loss is continuous); (ii) fit a monotone curve, reject and re-sweep if monotonicity fails; (iii) set tomorrow's nominal dose by **feed-forward inversion** of that curve at tomorrow's target, and correct the residual with Ziegler's clipped multiplicative controller — e_t = clip((D_t − D*_t)/D*_t, −0.2, 0.2); log α_{t+1} = log α_t + K·e_t. Relative error is what lets one gain serve both a 1% target on day 1 and a 70% target on day 27. Pure proportional control will lag a steepening ramp, so the feed-forward term is not optional. Before day 1, spend the calibration budget on the **α > 0.5 region**, since that is where the literature stops.

## Biggest open uncertainty

Whether the smooth region extends far enough. Every published curve is smooth only where it was measured, and all of them stop short of collapse; meanwhile Gromov, GPTQ, SliceGPT and Wanda independently show that **smaller models hit every knee earlier and harder** (Phi-2 at 2.7B collapses at ~25% layer drop vs 45–55% for Llama-2-70B; OPT-125M sits at 53.85 ppl at 3-bit vs 8.68 for OPT-175B). A 4B model sits at the fragile end of every one of these trends. The live risk is that days 25–30 contain a cliff rather than the intended 45%→70%→100% ramp — that the model goes from degraded to gibberish in one day, and the last third of the piece loses its shape. Mitigation: characterise the near-collapse region empirically *before* day 1, and be prepared to blend a second dial (sparsity or slicing) through the final week to spread damage across mechanisms whose knees fall at different doses.
