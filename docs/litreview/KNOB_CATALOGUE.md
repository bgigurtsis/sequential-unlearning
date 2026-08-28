# KNOB CATALOGUE

Two ranked catalogues for the two arms of the 30-day run on `gemma-3-4b-it` (BF16, one GPU, QLoRA-shaped interventions). Arm A erases one concept per day at minimal collateral with retain-only healing and re-checks of prior concepts; Arm B administers deliberate degradation dosed in closed loop against a precommitted curve (~1%/day to ~28% at day 22, convex to 100% at day 30).

Every number below is copied from `docs/litreview/notes/*.md` or `docs/litreview/papers.csv`. Where a note has no number, the entry says **not reported**. Citation keys are papers.csv keys.

---

## 1. FORGETTING-ARM RECIPES

Ranked on three axes: (i) low-dose collateral — forget-completeness against utility loss at the low end; (ii) composability over ~30 sequential applications; (iii) relearning resistance, per the T8 evidence.

### Rank 1 — Bounded-objective LoRA erasure: ELM shape, JensUn loss
`gandikota-2024-elm` + `singh-2025-jensun`

| | |
|---|---|
| Knobs | LoRA rank (ELM: 4), guidance strength eta (ELM: 500), layer span (ELM: 4–7), unlearning steps (JensUn: 600–2000) |
| Published numbers | ELM on Zephyr-7B: WMDP-Bio 64.4→29.7, WMDP-Cyber 44.3→27.2, MMLU 58.5→56.6, MT-Bench 7.3→7.1, reverse-PPL **10.9** vs RMU's 24.8. JensUn on Llama-3.2-3B-Instruct / Phi-3-mini-3.8B: worst-case forget acc **0%**, MMLU **59.9 vs 59.6** baseline, Win Rate 0.47 vs 0.5, repetitiveness 592 vs 637 |
| Scale | ELM 7B–70B; JensUn **3–3.8B** — the closest published scale to our target |
| Localisation | ELM's layers 4–7, rank-4 LoRA: already QLoRA-shaped. `li-2024-wmdp-rmu` localises to layers l−2, l−1, l; `xu-2026-fit` updates a **25% layer ratio** |
| Relearning resistance (T8) | Best measured at our scale: after 2000 unlearn steps + 600 benign FT steps on unrelated data, JensUn recovers **8%** forget acc vs NPO **26%** and NPO+SAM **58%**. Longer unlearning monotonically hardens |
| Compute per application on 4B | Not reported (ELM states no cost; JensUn reports step counts only). Rank-4 LoRA over 4 layers is the cheapest trained option here |
| Code | ELM: https://elm.baulab.info; JensUn: https://github.com/nmndeep/UnlearningThatLasts |
| Risk for us | Neither paper runs a sequential/repeated-erasure experiment; no dose sweep over eta or rank exists. We would be first at n=30. JensUn's own dose evidence stops at one erasure |

**Why rank 1.** It is the only combination that fixes the in-project step-29→30 cliff at the level of mechanism. `huutien-2024-adaptive-rmu` shows RMU's loss only converges where the l2-norm of forget-sample representations falls **below** c — a threshold condition, which is why RMU works in layers 3–10 and fails in 11–31 and why halving LR does not smooth the transition. `singh-2025-jensun` shows the general case: GradDiff and NPO collapse past ~600 steps while a bounded JSD objective holds Win Rate 0.46 at 2000 steps. Bounded loss converts step count from a threshold into a monotone dial.

### Rank 2 — Subspace-constrained daily updates (orthogonal / null-space)
`gao-2025-o3`, `fang-2024-alphaedit`, `gandikota-2024-uce`, `upman-2026-care`

| | |
|---|---|
| Knobs | Adapter rank per request; null-space projection basis; preserved-anchor bank size |
| Numbers | O3 (LLaMA-2-7B, 3–4 sequential requests, **no retain data**): TOFU Real Authors 88.8 / World Facts 86.1 vs base 89.0 / 86.3; ScienceQA CommonsenseQA 78.5 / OpenbookQA 80.9 vs base 88.0 / 88.7; CLINC150 MRPC 86.6 / RTE 89.0 vs base 88.0 / 88.7. Baselines: GradDif and SOGD emit empty or repeated-token nonsense by request 2–3; EUL RTE 88.1→76.3 by request 3. AlphaEdit at 3000 sequential edits maintains general capability where MEMIT's GLUE F1 approaches zero by 2000; LLaMA-3 at 2000 edits efficacy 98.90% vs MEMIT 65.65%. UCE: 100-celebrity erasure, erased acc 18.70% / retained 61.78%. CARE: retained neighbours **improve** (Mickey FID 5.72→4.43, Marilyn 6.68→3.29) |
| Localisation | This *is* the localisation: constrain the update to a subspace that provably misses the retain set |
| Relearning resistance | Not directly measured for O3/AlphaEdit. `siddiqui-2025-dormant-deleted` finds weight-space-regularised methods resist retain-only relearning where behavioural ones do not (vision) |
| Compute | O3 trains **~20M params** (orthogonal LoRA per request) vs 6,758M for full-model baselines. UCE ~1.2s/concept, RECE 3.4s/concept, modifying 2.23% of UNet params (diffusion) |
| Code | https://github.com/GCYZSL/O3-LLM-Unlearning, https://github.com/jianghoucheng/AlphaEdit, https://github.com/rohitgandikota/unified-concept-editing |
| Risk | O3's base weights are untouched and gating is OOD-detector-driven at inference — removing adapters restores knowledge, so its numbers are an optimistic bound for weight-level erasure. AlphaEdit's protection is bounded: `suresh-2026-alphaedit-repro` finds the knee reappears at ~5000 edits and the advantage does **not generalise uniformly to 1–4B models**. UCE loses 38 points of specificity by 100 concepts |

### Rank 3 — Per-day LoRA + interference-aware fusion (MACE template)
`lu-2024-mace`

100 celebrities erased from SD v1.4: efficacy **4.31%**, specificity **84.56%**, harmonic mean **89.78** — against UCE's 18.70 / 61.78 / 70.21 on the identical benchmark. That 22.8-point specificity gap is the quantified value of interference-aware fusion at n=100. Architecture: closed-form cross-attention refinement, then one LoRA per concept trained **separately**, then closed-form fusion with an explicit non-interference objective. Code: https://github.com/Shilin-LU/MACE.

**Risk:** diffusion cross-attention, not autoregressive LM; the fusion step relies on cross-attention key/value structure and does not transfer mechanically to gemma-3-4b. Also, a fully-fused-at-the-end construction may be wrong for a piece that wants visible day-by-day change — test the per-day-LoRA-plus-incremental-refusion variant. Relearning resistance: not reported.

### Rank 4 — Rank-1 direction ablation / weight orthogonalization
`arditi-2024-refusal-direction`, `belrose-2023-leace`

Best measured forget:collateral ratio in the whole review: refusal score ~95%→~0%, ASR up to 84.3% (Qwen 14B), for capability deltas of (Gemma 7B) MMLU +0.1, ARC +0.2, GSM8K −0.7, TruthfulQA −2.4; Yi-34B MMLU −1.4, TruthfulQA −3.5; Qwen-72B MMLU −0.7. TruthfulQA is the only consistently negative column. Compute: **under $5 for a 70B model**, ~1 hour direction selection at 72B — trivial at 4B, and strictly cheaper than QLoRA. Code: https://github.com/andyrdt/refusal_direction. LEACE gives the closed-form minimal-change guarantee (https://github.com/EleutherAI/concept-erasure).

**Risk:** refusal is a *behaviour* with an unusually clean single-direction representation; there is no evidence that "the sea" or "bread" is rank-1. No sequential-composition experiment — 30 stacked orthogonalizations remove 30 rank-1 subspaces from the residual stream, and LEACE's guarantee is **linear** erasure only (nothing blocks nonlinear recovery). Relearning resistance: not reported.

### Rank 5 — SAE feature clamping as a localiser, not as the edit
`muhamed-2025-dsg`, `farrell-2024-sae-unlearning`

DSG on **gemma-2-2b-it** with a gemma-scope 16k SAE at layer 3: WMDP-Bio **29.64%** at MMLU retention **99.34%**, MT-Bench **7.78** — against RMU 50.00% / 99.47% / 7.21, and NPO 97.95% (i.e. NPO barely forgets at all in this 2B setting). Forward passes only, no gradients. Code: https://github.com/aashiqmuhamed/DynamicSAEGuardrails.

**Disqualified as-is:** DSG is an inference-time gated intervention, not a weight-space update, so it is not QLoRA-shaped; a gate that only fires on detected inputs is arguably suppression, precisely the failure `xu-2025-reversibility` warns about. Gemma Scope SAEs exist for Gemma 2, **not** Gemma 3 — verify availability before planning around it. Usable role: feature selection to localise a weight-space edit. `farrell-2024-sae-unlearning` adds two cautions from the same family on Gemma-2-2b: zero-ablating features is ineffective (you must clamp to ~−18/−20, i.e. threshold not proportional response), and **10 features beat 20 and 50** — narrower readout, less collateral.

### Free wrappers (apply on top of any of the above)
- **DARE sparsification** (`yu-2024-dare`): drop 90–99% of the day-N delta and rescale by 1/(1−p). Zero extra compute; attacks the named root cause of cumulative interference (overlap) in TIES and FIT directly. **Untested in our direction** — DARE's evidence is entirely about preserving capabilities; an erasure vector may be far less redundant. Cheap first experiment: sweep p ∈ {0, 0.5, 0.9, 0.99} on one concept, measuring forget-completeness and MMLU separately.
- **TIES trimming** (`yadav-2023-ties`): the composition curve to extrapolate from — ~100% of individual performance at 2 merged vectors, ~85% at 7, ~80% at 11. Extrapolating to 30 predicts substantial cumulative loss without a repair stage.
- **Syntactic diversification of erasure prompts** (`yoon-2026-syntax`): syntactically similar relearn data gives ~60–80% keyword recovery vs ~0–20% for topically similar. Paraphrasing forget queries (syntactic similarity 0.45→0.22) eliminates the benign-relearning vulnerability. Our topic-only filter guards the wrong axis.
- **Invariance regularisation at forget time** (`wang-2025-ilu`): train the erasure to be invariant against the known healing corpus. Numbers not extracted; qualitative result is that baselines revert toward pre-unlearning WMDP accuracy after unrelated fine-tuning while ILU holds.

### Dose gate that applies to every recipe
`xu-2025-reversibility` is the go/no-go instrument. Continual moderate dose (GA lr 5e-6, N=100): forget acc falls to 9.1% and recovers to 80%, retain drops 6.2% and recovers to 65%, PCA drift 11.5→1.4. Continual aggressive (lr 3e-5, N=100): forget 0% stays 2.1% after relearning, retain 1.8% **unrecoverable**, PCA drift 133.2→104.6. Repairability is governed by **learning rate**, not request count, and the two regimes separate in representation space even when task metrics look identical. Healing budget per `luo-2023-continual-cf` and `biderman-2024-lora`: LoRA r=16–64, ~30–100 steps at lr ≤2e-5; mixing general instruction data cuts reasoning loss 31.3%→7.6% and reading comprehension 31.7%→10.3%.

### DO NOT USE

| Recipe | Disqualifying numbers |
|---|---|
| **Naive gradient ascent (GA/GradAsc)** | `gao-2025-o3`: 0% utility by request **2** (TOFU Real Authors, ScienceQA World Facts). `dou-2025-ssu`: MMLU 0.5821→0.3102 by step 5 on Llama-3.1-8B, collapse at **step 1** on Mistral. `xu-2026-fit`: GA and RLabel collapse to near zero by 60 requests. `zhang-2024-npo`: outputs "often gibberish"; GA already struggles at 10% forget fraction |
| **NPO at low dose** | `muhamed-2025-dsg` on gemma-2-2b-it: WMDP-Bio **97.95%** at utility-preserving settings — the low-dose end is *inert*, not gently graded. `singh-2025-jensun`: NPO collapses past ~600 steps; recovers **26%** forget acc after 600 benign relearn steps (vs JensUn 8%). `zhang-2024-npo` is explicit that NPO makes approach to collapse exponentially slower, not absent — the objective is still divergent, so "dose" is training time with no stable plateau |
| **ROME as unlearning** | `li-2025-editing-as-unlearning`, Llama2-7B: forget Rouge1 **0.01** but retain Rouge1 **0.04** — the retain set is destroyed too (compare GradDiff 0.30 / 0.62). `gupta-2024-editing-scale`: knee at 100–800 sequential edits, as low as **10**; ~30% of prior edits forgotten by 600 edits |
| **MEMIT-style mass editing** | `li-2025-editing-as-unlearning`: "the LLM becomes non-functional with near-zero Rouge1 for both forget and retain sets." `fang-2024-alphaedit`: GLUE F1 approaching zero by 2000 sequential edits; efficacy 65.65% vs AlphaEdit's 98.90%. `gupta-2025-encore`: MEMIT edited-matrix norm grows **10x** by 10k edits, edited-layer share of the residual stream rising from ~1% to 7–40% |
| **Knowledge Neurons** | `gu-2024-editing-harms`: a single KN edit can zero out downstream tasks; KN collapses after **1 edit** on LLaMA-1 |
| **Naive task-vector negation, applied sequentially** | `dou-2025-ssu`: Task Vector reaches **MMLU = 0 by step 10** on Llama-3.1-8B and collapses abruptly at step 5 on Mistral (healthy → 0 in one step) |
| **TAR-style adversarial meta-learning** | `tamirisa-2024-tar`: `runs_on_4b_single_gpu = n`; the meta-learning loop is too heavy for a daily 4B cadence |

Never evaluate resurfacing on a quantised checkpoint: `zhang-2024-quantization` finds 4-bit quantisation alone restores forgotten knowledge from 21% to **83%** retention (GA_KLR on BOOKS: 13%→89%). 8-bit is benign.

---

## 2. DECAY-ARM DIALS

Ranked on monotonicity/smoothness of published dose–response, near-collapse behaviour (final-week usability), reversibility, and implementation cost. Consistent with `T5_summary.md`.

| Dial | Swept-curve evidence | Shape | Near collapse | Reversible | Cost on 4B |
|---|---|---|---|---|---|
| **Per-channel Gaussian weight noise** (`buchel-2025-analog-foundation`) | 0→10% of per-channel max\|W\|, two models. Phi-3-mini-3.8B avg accuracy **−8.01%**, Llama-3.2-1B **−9.81%** at hardware-realistic noise (gamma ≈ 0.02–0.03) | Smooth, monotone, **no cliff inside 0–10%** | Not characterised — sweep stops well short | Total (draw on a copy) | One state-dict pass |
| **Absolute Gaussian weight noise** (`tice-2024-noise-sandbagging`) | sigma ∈ [0, 0.01], step 1e-4 → **101 dose levels**, 5 seeds each, on Llama-3-8B / Mistral-7B / Phi-3 mini-small-medium | "Stable, reproducible degradation curves without erratic fluctuations"; honest-model improvement ratio 1.00–1.074 | Sweep **capped at sigma = 0.01 because output "becomes incoherent" above it** — boundary located, transition not characterised | Total | `torch.randn_like(W) * sigma`, one pass |
| **Bounded noise interpolation** (`lee-2025-undo`) | theta' = (1−alpha)·theta + alpha·beta·N, N ~ Xavier; alpha swept at **11 points 0.1–0.8**, beta ∈ {0.05, 0.1, 0.5, 1.0}, on **Gemma-2-2B** | Monotone in alpha; **alpha dominates beta**, so the dial collapses to one control variable | alpha ≈ 0.8 destroys the model; alpha = 1 is a fresh Xavier init by construction. alpha=0.6/beta=0.1 already near-oracle damage | Total, and the paper's own method distils the damaged model back | Trivial to noise; distillation repair is the expensive half |
| **SliceGPT slicing %** (`ashkboos-2024-slicegpt`) | Llama-2-70B WikiText2 ppl 3.32 (dense) → **4.60 (25%)** → **5.05 (30%)**; 25% retains 96% of dense zero-shot (99% with recovery FT); >30% keeps >90% | Monotone, mildly convex over 0–30% | Range stops short of collapse. **Phi-2 (2.7B) retains only ~90% at the same 25%** where 70B models retain 99% | Only by re-slicing from the original — tensor shapes change, so doses compound structurally | A PCA/calibration pass **per dose** |
| **Unstructured pruning** (`sun-2023-wanda`, `frantar-2023-sparsegpt`) | 50% sparsity WikiText ppl, LLaMA-7B: dense 5.68 / magnitude **17.29** / SparseGPT 7.22 / Wanda 7.26; LLaMA-2-7B 5.12 / 14.89 / 6.51 / 6.42; LLaMA-2-70B 3.12 / 4.98 / 3.98 / 3.98 | Near-flat to ~50%, knee in 50–70% | 60%: magnitude on LLaMA-7B exceeds **600 ppl**. 80%: general collapse — best result anywhere is SparseGPT on LLaMA-2-70B at **25.86** vs 3.12 dense; magnitude returns **NaN** | Total, as a stored mask on a copy | One-shot; magnitude needs no calibration data |
| **Layer removal** (`gromov-2024-deeper-layers`, `men-2024-shortgpt`) | MMLU→random guessing at 45–55% (Llama-2-13B/70B), ~35% (Mistral-7B), ~25% (Phi-2 2.7B), ~20% (Qwen). ShortGPT: Llama-2-7B 9/32 layers → MMLU 45.39→43.96, 95.69% avg retained; Baichuan2-13B 10/40 → MMLU 59.50→52.11, 87.33% retained | **Cliff on QA; smooth on next-token loss** over the same range | The cliff itself. QLoRA healing restores the smooth loss curve and moves the QA cliff slightly later, not away | Total — a removed-layer list plus the day-0 checkpoint rebuilds any day | One forward pass to compute Block Influence ordering |
| **Quantisation rungs** (`frantar-2022-gptq`, `dettmers-2022-llmint8`) | OPT-175B WikiText2: FP16 8.34, RTN 4-bit 10.54, **RTN 3-bit 7.3e3**; GPTQ 3-bit 8.68. BLOOM-176B RTN 3-bit **571**. GPTQ 3-bit by scale: OPT-125M 53.85, 350M 33.79, 1.3B 20.97, 175B 8.68 | Four rungs (16/8/4/3), most dynamic range in one step | ~700x perplexity jump for one bit; "linear to exponential collapse" (`ma-2025-model-hemorrhage`) | Total (quantise a copy, keep BF16 original) | One line, no calibration data for RTN |
| **Activation noise** (`shahani-2025-noise-guardrails`) | Gaussian on every activation tensor via forward pre-hooks, 2B–27B models | Usable sigma bands are **narrow and ~50x apart across models**: Gemma-2B 0.10–0.20 vs Qwen2 0.002–0.0035 | Above band, output stops being coherent | Total (hooks only) | Cheapest of all — but a worse control variable |
| **Task-vector negation** (`ilharco-2023-task-arithmetic`) | lambda on a 0.0–1.0 grid in 0.05/0.1 steps with a published selection rule. GPT-2 toxicity: toxic generations 4.8%→0.8%, toxicity score 0.06→0.01, WikiText-103 ppl 16.4→16.9 | Monotone in lambda over the swept range | **Not characterised** — the published protocol deliberately stops before the model breaks | Total (one weight-space addition on a copy) | Requires a fine-tuned endpoint before day 1 to define tau |

**Which capability falls first.** The only direct evidence is `shahani-2025-noise-guardrails`: under activation noise, safety/refusal collapses well before reasoning — harmful rate 5%→31.4% on Gemma-2B and 2%→32% on Llama-3 while chain-of-thought stays largely intact. Under structural damage, `gromov-2024-deeper-layers` shows next-token loss degrades continuously while QA sits flat then cliffs, and `yin-2024-junkdna` shows hard (0-shot) task variants degrade immediately while easy tasks tolerate ~10–15% sparsity before falling — difficulty staggers where each probe carries signal. `dettmers-2022-llmint8` explains *why* uniform noise is smooth: damage is dominated by ~0.1% outlier feature dimensions (removing them costs 600–1000% perplexity; removing random dims costs 0.1%), and isotropic noise averages over locations.

### Recommendation (consistent with T5)

1. **Primary — per-channel-normalised Gaussian weight noise in the bounded interpolation form.** Büchel's normalisation (dose = fraction of per-channel max\|W\|, so one scalar stays comparable across layers and across daily checkpoints whose weight statistics have drifted) inside Lee's bounded form theta' = (1−alpha)theta + alpha·beta·N, so alpha ∈ [0,1] has a defined terminal endpoint and cannot diverge. Cheap, re-drawable, fully reversible against the frozen original.
2. **Fallback — SliceGPT slicing percentage**, if noise proves non-monotone on our checkpoints. Continuous, published per-percent curve, and the decline becomes visible in the artefact's geometry. Cost: a calibration pass per dose, and slicing is not re-drawable on a copy.
3. **Terminal instrument (day 30) — naive RTN 3-bit quantisation, or a Gromov-style contiguous layer-block drop** (BI-ordered per ShortGPT for reproducibility). We *want* a cliff on day 30; both are documented, deterministic, one-line and reversible.
4. **Optional expressive layer — negated task vector**, if the decline should be the loss of a particular character rather than generic entropy.

### Three standing hazards

- **Monotonicity is not guaranteed.** `sharma-2024-laser` is the explicit counterexample: removing higher-order components *raises* GPT-J CounterFact accuracy 13.3%→24.1%. `tice-2024-noise-sandbagging`'s entire result is that noise can raise measured accuracy when a capability is suppressed rather than absent (improvement ratios to 10.3x). Since each day's decay follows an erasure that may suppress rather than remove, a negative-damage day is a real possibility, not an instrument fault — verify monotonicity per checkpoint and do not let the controller over-correct.
- **Control on a divergence, never on accuracy.** `dutta-2024-flips`: across seven tasks accuracy moved ≤2% while flips ranged **0.26–13.62%** (Llama-2-70B MMLU: BnB W8A8 −0.55% acc / 3.32% flips; W4A4 −0.78% / 5.65%). Our daily step is ~1% — the same order as the noise floor of an accuracy readout. Use flips or KL against the frozen day-0 model, plus perplexity on `data/ppl_text.txt`.
- **Never train while noisy.** `buchel-2025-analog-foundation`: noise-aware training flattens the dose–response curve (analog-trained drop −3.81% vs off-the-shelf −8.01% on Phi-3-mini) with <1% of pretraining tokens. Any healing applied to a noisy checkpoint is inadvertent hardware-aware training and the dial loses potency over 30 days. Keep the noise draw strictly downstream of all training. Relatedly, `zamirai-2020-revisiting-bf16`: any per-day update smaller than a BF16 ULP is silently discarded (pure-bf16 nearest rounding costs 8.6pp on ResNet-50 ImageNet, 6.82pp on BERT-MNLI) — keep fp32 master weights through forget/heal and cast only at merge.

### Control law
`ziegler-2019-adaptive-kl`, transplanted: e_t = clip((D_t − D\*_t)/D\*_t, −0.2, +0.2); log sigma_{t+1} = log sigma_t + K·e_t. Multiplicative because the dose spans orders of magnitude between day 1 and day 30; relative error because the same gain must serve a 1% target on day 1 and a 70% target on day 27; clipped so no single day lurches. Ziegler's K_beta = 0.1 and clip ±0.2 assume thousands of updates per run — with one measurement per day the gain must be larger and the clip wider. Add a feed-forward term (invert the calibrated dose–response curve at tomorrow's target) because pure proportional control lags a steepening ramp.

### The unresolved gap
**Every published weight-noise curve stops exactly where our final week begins** — Tice at sigma = 0.01, Büchel at 10% of per-channel max, Lee at alpha = 0.8. Meanwhile Gromov (Phi-2 2.7B collapses at ~25% layer drop vs 45–55% for Llama-2-70B), GPTQ (OPT-125M 53.85 ppl at 3-bit vs 8.68 for OPT-175B), SliceGPT (Phi-2 ~90% retained at 25% slice vs 99% at 70B) and Wanda independently show smaller models hit every knee earlier and harder. A 4B model sits at the fragile end of all four trends. Spend the pre-day-1 calibration budget in the alpha > 0.5 region, and be prepared to blend a second dial (magnitude pruning or slicing) through the final week to spread damage across mechanisms whose knees fall at different doses.
