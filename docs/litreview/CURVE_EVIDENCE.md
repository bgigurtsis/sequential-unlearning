# CURVE_EVIDENCE — Digitised trajectories and dose–responses from the literature review

Compiled from `docs/litreview/notes/` (all note files), `fragments/T2_summary.md`, `T4_summary.md`, `T5_summary.md`, and `papers.csv`. Every number below appears in those files; values a note marked as read off a figure keep the note's "~". Purpose: evidence base for H4 (≤~1%/day leakage over 30 forget+heal cycles) and H3 (closed-loop dial hitting a precommitted curve, steep final week ~28%→100% over days 22–30) on gemma-3-4b-it (4B).

---

## 1. Sequential-intervention trajectories

### 1.1 SSU — sequential book unlearning (dou-2025-ssu; Llama-3.1-8B-Instruct, one book per step)

| N steps | Metric | SSU | GA | Task Vector | GradDiff |
|---|---|---|---|---|---|
| 1 | MMLU | 0.6625 | 0.5821 (start) | — | — |
| 5 | MMLU | 0.6425 | 0.3102 | — | — |
| 10 | MMLU | stable, no collapse | — | 0 | — |
| 1 | MT-Bench | 8.225 | — | — | 8.034 (start) |
| 5 | MT-Bench | 8.142 | — | — | 4.944 |

Mistral-7B-Instruct-v0.3, same protocol: GA collapses at step 1; Task Vector collapses abruptly at step 5 (both metrics → 0); baselines dead by step 6. NPO: gradual decline, stays functional, weaker unlearning.
**Shape:** SSU near-linear shallow sag, ~0.005 MMLU absolute (~0.3–0.8% relative) per step over steps 1–5, flattening after; naive methods knee at N≈1–5 (Mistral) or 5–10 (Llama), Task Vector's knee is cliff-style (healthy → 0 in one step).

### 1.2 FIT — 300 sequential deletion requests (xu-2026-fit / fit-2026-continual-unlearning; Llama-3-8B; F.D. = forget degree, R.U. = retain utility)

| N requests | F.D. | R.U. |
|---|---|---|
| 60 | 0.90 | 0.88 |
| 120 | 0.75 | 0.71 |
| 180 | 0.75 | 0.72 |
| 240 | 0.76 | 0.70 |
| 300 | 0.73 (±0.05) | 0.71 (±0.05) |

Downstream at 300 requests (vs retain-model reference): MMLU 65.56 vs 65.97; CSQA 70.01 vs 70.02; GSM8K 57.02 vs 58.83. Ablating adaptive algorithm selection: GSM8K → 14.12. Baselines on Llama-3-8B: GA F.D. = 0.00 and RLabel F.D. = 0.01 by 60 requests; GA+GD at 0.01/0.01 by 60; NPO F.D. decays 0.25 (60) → 0.12 (300). Qwen3-14B FIT: 0.89/0.90 → 0.89/0.78.
**Shape:** sag between 60→120 requests, then plateau to 300 — not a cliff; <1 MMLU point lost over 300 requests (≈0.003 pt/request). Stability is engineered (redundancy filtering, per-request method selection, ~25% layer updates), not free.

### 1.3 O3 — continual unlearning, 3–4 requests (gao-2025-o3; LLaMA-2-7B)

| Setting, after request 3 | O3 | Base | Baseline collapse |
|---|---|---|---|
| ScienceQA: CommonsenseQA / OpenbookQA | 78.5 / 80.9 | 88.0 / 88.7 | GradDif & SOGD emit empty/repeated-token nonsense by request 2–3 |
| ScienceQA: retained-distribution | 91.2 | 99.8 | GradAsc utility → 0% on World Facts after request 2 |
| TOFU: Real Authors / World Facts | 88.8 / 86.1 | 89.0 / 86.3 | GradAsc 0% on Real Authors after request 2; SOPO 85.3→86.7% |
| CLINC150: MRPC / RTE | 86.6 / 89.0 | 88.0 / 88.7 | EUL 88.1→76.3 (RTE) by request 3; SOGD ~2–4% |

**Shape:** flat over the tested range for O3 (orthogonal LoRA per request — utility loss ~zero by construction), but only 3–4 requests; entangled-domain setting (ScienceQA) still costs 4–9 points of general QA even for the best method.

### 1.4 ROME/MEMIT sequential edits (gupta-2024-editing-scale; GPT-2 XL 1.5B)

| N edits | Method | Metric | Value |
|---|---|---|---|
| ≤100–800 (inflection; can be as low as 10) | ROME | edit efficacy | ~100% until inflection, then catastrophic |
| 600 | ROME | prior edited facts forgotten | ~30% |
| ~equivalent count | MEMIT | prior edited facts forgotten | ~10% |
| ~4,000 | MEMIT | gradual phase ends, catastrophic region begins | — |

Downstream (SST-2, MRPC): gradual decline before the cliff; paraphrase detection dies long before the inflection. Neighborhood/locality score declines continuously from edit 1.
**Shape:** canonical two-phase — slow monotone leak then a cliff; knee varies nearly an order of magnitude across samples (100–800, tail at 10).

### 1.5 AlphaEdit and its reproduction (fang-2024-alphaedit; suresh-2026-alphaedit-repro)

| N edits | Model | Metric | Value |
|---|---|---|---|
| 2,000 | LLaMA-3-8B | MEMIT efficacy / AlphaEdit efficacy | 65.65% / 98.90% |
| 2,000 | LLaMA-3-8B | Generalization MEMIT / AlphaEdit | 64.65% / 94.22% |
| 2,000 | LLaMA-3-8B | Consistency MEMIT / AlphaEdit | 6.58 / 32.40 |
| 2,000 | GPT-2 XL etc. | MEMIT GLUE F1 | "rapidly approaching zero" |
| 3,000 | all | AlphaEdit general capability | original performance maintained |
| 0–2,000 (repro) | multiple | AlphaEdit efficacy | 93–99% |
| ~5,000 (repro) | LLaMA-3-8B | BoolQ F1 | >0.8 → <0.1 (cliff) |
| 10,000 (repro) | LLaMA-3-8B | MMLU | ~0.6 → ~0.1 |

**Shape:** flat to ~3,000 edits, knee ~5,000, substantial collapse by 10,000. Null-space protection is bounded, not unconditional; advantage weaker on 1–4B models (incl. Gemma-2-2B).

### 1.6 ENCORE — lifelong editing odometer (gupta-2025-encore; up to 10,000 edits, batches of 100)

| N edits | Metric | Value |
|---|---|---|
| 10,000 | MEMIT edit score (Llama-3-8B) | ~81 → ~50 |
| 10,000 | MEMIT edited-matrix Frobenius norm | 10x original (AlphaEdit ~2x) |
| over run | edited layers' residual-stream activation share | ~1% → 7–40% |
| 3,000–5,000 | baseline downstream | significant degradation begins |
| 10,000 | ENCORE (Llama-2-7B): edit score / paraphrase / overall | 92.57 / 82.64 / 76.04; downstream held |

**Shape:** norm growth monotone and cumulative from edit 1; downstream knee at 3k–5k for baselines, pushed past 10k by norm constraint + early stopping.

### 1.7 Continual unlearning at N=100 — reversibility regimes (xu-2025-reversibility / xu-2026-reversibility; Yi-6B main)

| Regime | N | Forget acc | After relearning | Retain acc |
|---|---|---|---|---|
| Single, moderate (GA+KL) | 1 | drops 7.9–12.7% (13–20 pts across methods) | recovers to ~77% | 62–65%, stable |
| Continual moderate (GA lr 5e-6) | 100 | falls to 9.1% (range 9–51%) | recovers to 80% (~80–82%) | drops 6.2% (6–14%), recovers to 65% |
| Continual aggressive (GA lr 3e-5) | 100 | 0% (0–37%) | only 2.1% (1–4%) — irreversible | 1.8%, unrecoverable |

Representation drift: reversible PCA distance 1–11 (→ below ~3 after relearning), CKA ~0.95–1.0; irreversible 95–133 (133.2 → 104.6 after relearning), CKA <0.5.
**Shape:** regime boundary is dose (LR × steps), not N per se; past threshold, collapse is global and permanent.

### 1.8 Weight-drift accumulation per edit (gu-2024-editing-harms; ROME on GPT-2 XL)

| N edits | Fraction of weight elements with \|delta\| > 0.077 | Manhattan distance of edited matrix |
|---|---|---|
| 1 | 20% | 9,079 |
| 5 | 49.2% | — |
| 15 | 72.8% | 63,247 |

Also: KN on LLaMA-1 — a single edit drops performance to near zero on all selected tasks (worst one-shot collapse in the set). RECT regularization keeps >94% of editing performance while largely preserving downstream.
**Shape:** roughly linear-to-superlinear drift accumulation; method choice dominates (one KN edit can blow a 30-day budget).

### 1.9 Unlearning step count as dose (singh-2025-jensun; Llama-3.2-3B / Phi-3-mini 3.8B)

| Steps | Method | Metric | Value |
|---|---|---|---|
| — | Original | MMLU / Win Rate | 59.6 / 0.5 |
| standard | JensUn | forget acc / MMLU / WR | 0% / 59.9 / 0.47 |
| >600 | GradDiff, NPO | utility | marked collapse begins |
| 2,000 | JensUn | Win Rate | 0.46 (holds) |
| 2,000 + 600 benign relearn steps | JensUn / NPO / NPO+SAM | forget acc recovered | 8% / 26% / 58% |
| 2,000 | GradDiff | recovery / Win Rate | 0% / 0.03 (model destroyed) |

**Shape:** with a bounded (JSD) objective the step count is a genuine monotone dial across 600–2,000 steps; unbounded objectives (GA/GradDiff/NPO) knee past ~600 steps.

### 1.10 Stacked weight-space edits — merging analogue (yadav-2023-ties)

| N merged task vectors | Normalized accuracy |
|---|---|
| 2 | ~100% |
| 7 | ~85% |
| 11 | ~80% |

**Shape:** monotone decline, not flattening at 11; Task Arithmetic declines faster than TIES. (Capability vectors, not erasure vectors — indirect.)

### 1.11 Multi-concept erasure at scale, diffusion (lu-2024-mace; gandikota-2024-uce; 100 celebrities, SD v1.4)

| Method | N concepts | Efficacy (erased acc ↓) | Specificity (retained acc ↑) | Harmonic mean |
|---|---|---|---|---|
| MACE | 100 | 4.31% | 84.56% | 89.78 |
| UCE | 100 | 18.70% | 61.78% | 70.21 |

**Shape:** naive closed-form multi-edit loses ~38 points of specificity by n=100; interference-aware fusion (per-concept LoRA + closed-form fusion) recovers 22.8 points. Different modality — architectural evidence only.

### 1.12 Continual fine-tuning forgetting by scale (luo-2023-continual-cf; BLOOMZ, sequence of tasks)

| Scale | Domain-knowledge FG | Reading-comprehension FG | Reasoning FG |
|---|---|---|---|
| 1.1b | 9.54% | 18.04% | 6.73% |
| 1.7b | 10.72% | 24.29% | — |
| 3b | 14.63% | 27.56% | — |
| 7.1b | 18.37% | 26.75% | 13.62% |

LLaMA-7b vs ALPACA-7b after identical continual FT: domain knowledge 34.57% vs 18.14%; reasoning 31.33% vs 7.56%; reading comprehension 31.72% vs 10.31% — general-instruction rehearsal cut reasoning loss ~4x (the healing-pass mechanism).

### 1.13 MUSE sequential requests (shi-2024-muse; LLaMA-2-7B, 4 sequential folds)

No digitised per-request table in the note. Reported: utility degrades progressively (not cliff-only) across sequential requests for most of 8 methods; several drive retain-utility to ~0 at larger removal scales; GA/NPO utility near zero after the first of 4 requests (per T2 summary).

---

## 2. Perturbation / dial dose–responses

### 2.1 Gaussian weight noise — per-channel normalised (buchel-2025-analog-foundation; sweep 0 → ~10% of per-channel max |W|)

| Dose | Model | Metric | Value |
|---|---|---|---|
| hardware-realistic (γ ≈ 0.02–0.03) | Phi-3-mini (3.8B) | avg accuracy drop, off-the-shelf | −8.01% |
| hardware-realistic | Llama-3.2-1B | avg accuracy drop, off-the-shelf | −9.81% |
| hardware-realistic | Phi-3-mini / Llama-3.2-1B | drop after analog (HWA) training | −3.81% / −4.58% |
| ~10% of per-channel max | both | avg accuracy vs noise-free | roughly −4–5% (analog-trained) |

**Shape:** smooth, monotone, no cliff inside 0–10%; sweep stops well before collapse. Best-matched scale to 4B. Hazard: noise-aware training flattens the curve. Range ends far short of the final-week (28%→100%) damage levels.

### 2.2 Gaussian weight noise — absolute sigma, all parameters (tice-2024-noise-sandbagging; σ ∈ [0, 0.01], step 1e-4, 101 levels, 5 seeds/point; 7–8B instruct models)

| Model / benchmark | φ_std (honest) | φ_sbg (sandbagging) |
|---|---|---|
| Llama-3-8B, AI2 | 1.030 (0.005) | — |
| Mistral-7B, WMDP | 1.045 (0.008) | 2.481 |
| Phi-3-medium, AI2 | 1.028 (0.003) | 10.286 |

Honest models: φ_std clusters 1.00–1.074; monotone degradation with low across-seed variance ("stable, reproducible degradation curves"). Mistral Large no-goal sandbagging: 66.6% → 100% on 30 GSM8K problems under noise. Detection classifier on noise-response curves: 96.2% accuracy.
**Shape:** monotone for honest models over the full swept range; sweep hard-capped at σ = 0.01 because performance "becomes incoherent" above — the collapse boundary is located but its shape uncharacterised. That boundary is exactly where our final week lives. Caveat for control: noise can *raise* accuracy where a capability is suppressed (up to 10.3x) — negative-damage days are possible after same-day erasure.

### 2.3 Bounded noise interpolation (lee-2025-undo; θ' = (1−α)θ + α·β·N, Xavier N; Gemma-2 100M/300M/2B)

| Dose | Result |
|---|---|
| α grid {0.1 … 0.8}, β = 0.1 | robustness monotone in α; α dominates β (dial is effectively 1-D) |
| α = 0.6, β = 0.1 | near-oracle (retrain-level) relearning robustness |
| α = 0.8 | top of swept range; damage saturating |
| α = 1 | fresh Xavier init by construction (terminal endpoint) |

**Shape:** monotone in α with bounded endpoints; no continuous utility trace published — the high-α region is visited only to show damage saturating. Nearest published model family (Gemma-2-2B) to gemma-3-4b-it.

### 2.4 Large persistent weight noise + trainability (li-2025-ahwa-lora-analog; LLaMA-3.1-8B)

| Dose (noise, % of weight range) | Metric | Digital | Noised, unadapted | After LoRA training under noise |
|---|---|---|---|---|
| 6.7% | HellaSwag (0-shot) | 78.91% | 29.48% | 67.71% |
| 6.7% | GSM8K (CoT) | 85.06% | 37.98% | 70.74% |
| 3.0% | used for the GSM8K RL run | — | — | — |
| 12% | training | destabilises completely (only published "too much to train through" bound) |

**Shape:** a single mid-course point plus a hard ceiling, not a curve; shows the gradient still points at the target at ~47-point damage. Noise is multiplicative-in-range, re-sampled per forward pass — not a baked additive offset.

### 2.5 Shrink-and-perturb (ash-2020-warm-start-shrink-perturb; ResNet-18 scale)

| Dose | Result |
|---|---|
| λ = 0.6 shrink + σ = 0.01 noise | recovers fresh-init generalisation while keeping warm-start speed |
| warm start, no perturbation | −4.5 pp (CIFAR-10 SGD), −3.6 (Adam), −6.4 (CIFAR-100), −1.9 (SVHN) vs fresh init |

Reference scale for "a large perturbation that leaves a network fully trainable." No LLM replication.

### 2.6 Gaussian activation noise (shahani-2025-noise-guardrails; inference-time, all layers)

| Model | Usable σ band (coherent but changed) |
|---|---|
| Gemma 2B IT | 0.10 – 0.20 |
| Gemma 7B IT | 0.02 – 0.08 |
| Llama-3 | 0.005 – 0.0075 |
| Qwen2 | 0.002 – 0.0035 |

Capability ordering within band: harmful-output rate Gemma-2B 5% → 31.4% (d = −9.29); Llama-3 2% → 32% (d = −4.15); Yi-1.5 30% → 35% (d = −1.26); up to +27 pp harmful rate, p < 0.001, while chain-of-thought stays largely intact.
**Shape:** ~50–100x spread in operating point across models; each band under a factor of 2 wide — too narrow for a 30-level schedule. Refusal/alignment collapses first.

### 2.7 Layer removal (gromov-2024-deeper-layers; MMLU → random guessing 25%)

| Model | Layer-drop fraction at collapse |
|---|---|
| Llama-2-70B | 45–55% |
| Llama-2-13B | 45–55% |
| Mistral-7B | ~35% |
| Phi-2 (2.7B) | ~25% |
| Qwen (7B/14B) | ~20% |

**Shape:** QA accuracy flat-then-cliff; C4 next-token loss degrades smoothly over the same range and, after QLoRA healing, near-linearly out past 80% pruning. The two smallest models collapse earliest. Step size ~3%/layer — too coarse for daily dosing; documented cliff instrument for day 30.

### 2.8 Layer removal, BI-ordered (men-2024-shortgpt)

| Model | Layers removed (ratio) | Dense MMLU → pruned | Avg retained |
|---|---|---|---|
| Llama-2-7B | 9/32 (27.1%) | 45.39 → 43.96 | 95.69% |
| Llama-2-13B | 10/40 (24.6%) | 55.00 → 54.69 | 97.34% |
| Baichuan2-7B | 9/32 (24.2%) | 53.87 → 45.77 | 91.52% |
| Baichuan2-13B | 10/40 (24.7%) | 59.50 → 52.11 | 87.33% |

**Shape:** same sharp threshold as Gromov ("MMLU drops significantly at a certain layer"); family-dependent tolerance (95–97% vs 87% at ~25% removal) — not predictable from parameter count.

### 2.9 SliceGPT structural slicing (ashkboos-2024-slicegpt; Llama-2-70B WikiText2 ppl)

| Slice % | Perplexity |
|---|---|
| 0% | 3.32 |
| 25% | 4.60 |
| 30% | 5.05 |

Zero-shot at 25%: Llama-2-70B retains 96% (99% with recovery FT); OPT-66B 99%; **Phi-2 (2.7B) only ~90%**. Up to 30%: >90% zero-shot retained.
**Shape:** smooth, monotone, mildly convex over 0–30%; range stops well short of collapse. Third independent small-model penalty.

### 2.10 Unstructured sparsity (sun-2023-wanda; WikiText ppl at 50% sparsity)

| Model | Dense | Magnitude | SparseGPT | Wanda |
|---|---|---|---|---|
| LLaMA-7B | 5.68 | 17.29 | 7.22 | 7.26 |
| LLaMA-13B | 5.09 | 20.21 | 6.21 | 6.15 |
| LLaMA-30B | 4.77 | 7.54 | 5.31 | 5.24 |
| LLaMA-65B | 3.56 | 5.90 | 4.57 | 4.57 |
| LLaMA-2-7B | 5.12 | 14.89 | 6.51 | 6.42 |
| LLaMA-2-13B | 4.57 | 6.37 | 5.63 | 5.56 |
| LLaMA-2-70B | 3.12 | 4.98 | 3.98 | 3.98 |

60% sparsity: Wanda/SparseGPT competitive; magnitude pruning on LLaMA-7B exceeds 600 ppl. 80%: general collapse — best anywhere is SparseGPT LLaMA-2-70B at 25.86 (dense 3.12); magnitude → NaN.
**Shape:** near-flat to ~50%, knee in 50–70%, collapse by 80%. Continuous and finely divisible in 0–50%; magnitude (uncalibrated) variant degrades far faster — the more expressive instrument. All numbers 7B+; expect a 4B model at or below the LLaMA-7B column.

### 2.11 Quantisation bit-width (frantar-2022-gptq; WikiText2 ppl)

| Bits | OPT-175B RTN | OPT-175B GPTQ | BLOOM-176B RTN | BLOOM-176B GPTQ |
|---|---|---|---|---|
| FP16 | 8.34 | 8.34 | 8.11 | 8.11 |
| 4 | 10.54 | 8.37 | 8.37 | 8.21 |
| 3 | 7.3e3 | 8.68 | 571 | 8.64 |

GPTQ 3-bit across OPT scales: 125M 53.85; 350M 33.79; 1.3B 20.97; 66B 14.16; 175B 8.68.
**Shape:** 3–4 usable rungs, then a cliff (RTN 4→3 bit: ~700x on OPT-175B); scale trend is adverse — smaller models are far more fragile (6x ppl spread purely by scale at 3-bit). Terminal instrument, not a schedule.

### 2.12 Task-vector negation (ilharco-2023-task-arithmetic; GPT-2, toxicity vector; λ swept 0.0–1.0)

| Metric | Pre-trained | After negation |
|---|---|---|
| Toxic generations | 4.8% | 0.8% |
| Mean toxicity score | 0.06 | 0.01 |
| WikiText-103 ppl | 16.4 | 16.9 |

**Shape:** largely monotone in λ; published protocol deliberately stops before the model breaks (largest λ keeping within 0.5 ppl / 95% control accuracy) — no near-collapse characterisation.

### 2.13 Sparsity–task monotonicity (yin-2024-junkdna)

| Dial | Spearman (dose vs task performance) |
|---|---|
| Pruning small-magnitude weights | 0.996–1.0 (near-perfectly monotone) |
| Quantization | 0.666–0.872 (non-monotone) |

Easy tasks tolerate ~10–15% removal with no drop (5-shot variant: 14%); hardest (0-shot) variant degrades from the first pruning step. Task difficulty staggers where on the damage axis each readout carries signal.

### 2.14 Measurement sensitivity, not a dial (dutta-2024-flips; Llama-2-70b, MMLU 5-shot)

| Scheme | Accuracy change | Flips |
|---|---|---|
| GPTQ W8A16 | −0.01% | 0.26% |
| BnB W8A8 | −0.55% | 3.32% |
| BnB W4A4 | −0.78% | 5.65% |

Across 7 tasks: accuracy moved ≤2% while flips ranged 0.26–13.62%. A ~1%/day accuracy step is at the noise floor of accuracy-based control; control on flips/KL/perplexity distance from day 0.

### 2.15 One-shot rank-1 edit collateral (arditi-2024-refusal-direction; weight orthogonalization)

Refusal score ~95% → ~0%. General-capability deltas: Gemma 7B MMLU +0.1, ARC +0.2, GSM8K −0.7, TruthfulQA −2.4; Yi 34B MMLU −1.4, TruthfulQA −3.5; Llama-3 70B TruthfulQA −2.3. Near-total behavioural erasure for ≤1.4 pt MMLU — the best one-shot forget:collateral ratio measured; no sequential composition tested.

### 2.16 Cross-dial threshold map (ma-2025-model-hemorrhage; survey, not freshly swept)

Structured pruning: collapse ~50% sparsity. Unstructured: stable below ~60%. Quantisation: 3-bit critical threshold ("linear to exponential collapse"); <5% loss at 4-bit; best 2-bit cases retain >90%. Layer removal: Llama-2-70B holds MMLU after 40% pruned. Decoding: deterministic <5% loss on closed-ended; stochastic >15% ppl variability open-ended. Ranking: quantisation most robust per unit compression, then unstructured pruning, then structured/layer removal.

### 2.17 Dose–response points recorded only in papers.csv (context rows; not in a note file)

- **Shumailov model collapse (Nature 2024, OPT-125M):** gen-0 ppl ~20 → ~28 by gen 1 without data preservation; 10% real data keeps degradation minor over 9 generations; gens 7–9 collapse to repetitive phrase loops.
- **LLM.int8 (dettmers-2022):** phase transition at ~6.7B; OPT-13B 12.45 fp32 → 19.08 absmax int8; removing ~0.1% outlier dims degrades ppl 600–1000%, random dims ~0.1% — why dense uniform noise is smooth.
- **LASER (sharma-2024):** rank reduction non-monotone — GPT-J CounterFact 13.3% → 24.1% by removing components (monotonicity counterexample).
- **PrisonBreak (coalson-2024):** 5–25 targeted bit flips change behaviour drastically; arbitrary flips → NaN within a few.

---

## 3. Synthesis

### 3.1 Per-cycle leakage for a forget+heal cycle at 4–8B scale, vs the ~1%/day budget

| Source | Setting | Per-cycle general-utility leakage | Basis |
|---|---|---|---|
| dou-2025-ssu (SSU) | Llama-3.1-8B, 1 book/step, 10 steps | ~0.005 MMLU absolute/step ≈ 0.3–0.8% relative | digitised steps 1–5, flattening after |
| xu-2026-fit (FIT) | Llama-3-8B, 300 requests | ≈0.003 MMLU pt/request (<1 pt over 300); but R.U. sags 0.88→0.71 over 60→120 then plateaus | digitised table |
| gao-2025-o3 (O3) | LLaMA-2-7B, 3 requests, orthogonal LoRA | ~0 per request by construction (adapters, base untouched) — optimistic bound, not erasure | digitised table |
| Naive methods (GA/TaskVector/GradDiff/RLabel/KN) | 7–8B | budget-blowing: collapse in 1–10 cycles; KN can zero utility in 1 edit | SSU, FIT, MUSE, Gu 2024 |
| T2_summary best estimate | — | **0.3–1.0% relative per cycle** for a well-behaved method; healing/regularization plausibly halves it (RECT >94% efficacy retained; ENCORE holds 10k edits) | synthesis |

**Implied 30-day cumulative band:** ~5–15% relative loss over 30 cycles (T2 summary), against a pre-day-22 budget of ~22% at 1%/day (~1%/day × 22 days). H4 is plausible but not guaranteed: the average fits, but the budget binds *daily*, and the two pessimistic corrections both point the wrong way — (1) smaller models degrade earlier (AlphaEdit-repro on 1–4B incl. Gemma-2-2B; Mistral-7B kneed 2x earlier than Llama-3.1-8B); (2) our everyday concepts are more entangled with general capability than book shards or fact edits (O3's entangled-domain setting cost 4–9 QA points in just 3 requests).

### 3.2 Decay dials: evidenced range, smoothness, and the gap near collapse

| Dial | Evidenced dose range | Smoothness verdict | Uncovered gap near collapse (our days ~23–30) |
|---|---|---|---|
| Gaussian weight noise, per-channel (Büchel) | 0–10% of per-channel max, 1–3.8B | smooth, monotone, no cliff in range | sweep stops at 10%; nothing at collapse-level doses |
| Gaussian weight noise, absolute (Tice) | σ 0–0.01, 1e-4 grid, 7–8B | monotone, low seed variance; suppressed capabilities can *improve* | incoherent above 0.01 — boundary located, transition shape unmeasured |
| Bounded interpolation (Lee/UNDO) | α 0.1–0.8, β 0.05–1.0, Gemma-2 ≤2B | monotone in α; α dominates β | no continuous utility trace; α 0.8–1.0 unswept |
| Persistent large noise (AHWA-LoRA) | points at 3%, 6.7%, 12% of weight range, 8B | not a curve (3 points) | 12% = training-failure ceiling; behaviour between 6.7% and 12% unmapped |
| Activation noise (Shahani) | per-model bands, 2B–27B | narrow (<2x) bands, 50–100x cross-model spread | band too narrow for 30 levels; above band = incoherence |
| Layer removal (Gromov/ShortGPT) | 0–55% of layers, 2.7B–70B | QA flat-then-cliff; C4 loss smooth | cliff *is* the near-collapse behaviour; usable as terminal event only; ~3% minimum step |
| SliceGPT | 0–30% slice, 1.3B–70B | smooth, mildly convex | >30% uncharted; small-model penalty (Phi-2 ~90% at 25%) |
| Sparsity (Wanda/SparseGPT/magnitude) | 0–80%, 7B–70B | smooth 0–50%, knee 50–70%, collapse by 80% | 50–80% region coarsely sampled (3 points); nothing below 7B |
| Quantisation (GPTQ/RTN) | 16/8/4/3(/2) bits, 125M–176B | not a curve — rungs + cliff at 3-bit | too coarse to schedule; ideal one-shot terminal instrument |
| Task-vector negation | λ 0–1.0, ≤1.5B | largely monotone | protocol stops before breakage; base drift over 30 days untested |

Common pattern: **every published weight-noise curve stops exactly where our final week begins** (T5 summary), and four independent dials (Gromov, GPTQ, SliceGPT, Wanda) show smaller models hit every knee earlier and harder.

### 3.3 Explicit extrapolations we are making beyond published ranges

1. **Scale:** no sequential-unlearning trajectory exists below 6B (SSU 7–8B; FIT 6–14B; O3 7B). The 4B per-cycle leakage of 0.3–1.0% is an extrapolation with a known-adverse direction (AlphaEdit-repro: weaker protection on 1–4B; Gromov/GPTQ/SliceGPT/Wanda small-model penalty).
2. **Gemma-3 is untested everywhere.** Nearest relatives: Gemma-2-2B (Lee/UNDO, DSG, Farrell), Gemma-2B/7B (Shahani activation bands — Gemma needed the *highest* σ). No dial or sequential result on any Gemma-3 checkpoint.
3. **Near-collapse noise shape (days ~23–30):** assumed continuous/monotone from below; Tice's >0.01 incoherence bound, AHWA's 12% training ceiling, and Lee's α ≤ 0.8 cap are the only anchors. The 28%→100% final-week ramp is entirely outside published sweeps.
4. **Forget+heal composition:** no published result combines concept-level erasure + interleaved retain-only healing + 30 cycles at any scale (T2 summary). SSU/FIT/O3 all forgo retain-data repair; the "healing halves leakage" estimate is transplanted from RECT/ENCORE (edit-time regularization) and Luo (rehearsal during benign FT), neither of which is post-hoc healing after an unlearning objective.
5. **Erasure on a degraded parent:** trainability-under-noise evidence (AHWA-LoRA, Ash) measures recovery of original capabilities, not acquisition of a new forget objective on a noised checkpoint (T4 summary). H6-style asymmetry is untested.
6. **Per-cycle metric transfer:** SSU/FIT leakage is measured in MMLU/R.U.; our budget curve is defined on a different composite. The ≤2% accuracy vs 0.26–13.62% flips discrepancy (Dutta) means the published per-cycle numbers may understate behavioural drift by up to ~7x.
7. **TIES 2→7→11 extrapolated to 30** stacked edits predicts substantial loss, but for capability vectors, not erasure vectors, and without healing.

### 3.4 Reported without numbers (adjectives only — excluded from tables)

- **wuerkaixi-2025-alkn:** ">95% of model utility after sufficient sequential unlearning"; baselines "completely lose their utility" — no per-task curve extracted (compressed PDF).
- **muhamed-2025-dsg:** MUSE sequential — DSG "consistently maintained … the ideal region where other methods rapidly degrade"; request count not extracted.
- **wang-2025-ilu:** baselines "revert toward pre-unlearning WMDP accuracy" after unrelated FT; ILU "largely holds" — before/after tables not extracted.
- **zhang-2024-npo:** collapse "exponentially slower" than GA (theory); no TOFU table extracted.
- **belrose-2023-leace:** analytic minimal-norm guarantee; no utility-loss numbers.
- **shi-2024-muse sequential detail:** per-request values described only as "progressive degradation" / "~0 utility".
- **lynch-2024-eight-methods:** qualitative (knowledge recoverable via all four attack channels).
- **kotha-2024-implicit-inference:** per-model/per-language recovery deltas not extracted.
- **gandikota-2023-esd:** no interference table on the abstract page; comparative numbers live in RECE/MACE tables.
