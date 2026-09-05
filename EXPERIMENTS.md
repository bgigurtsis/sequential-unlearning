# Experiment log

Running record of every unlearning run: config, what changed, what happened,
and what we concluded. Newest run at the bottom. Update this file whenever a
run finishes, an eval is read, or a hyperparameter/loss change is committed.

Goal: erase the concept "the sea" from `google/gemma-3-4b-it` via NPO +
retain loss (rank-8 QLoRA, layers 17–27), gated by the frozen probe suite
(`data/probes.json`) and perplexity on `data/ppl_text.txt`.

**Baseline** (`logs/before.json`): target cloze probs 0.08–0.94
(most 0.45–0.94), controls 0.20–0.86, perplexity 14.13.

---

## Run 1 — faithful NPO, original hyperparameters

- **Config:** summed sequence log-probs, β=0.1, lr=2e-5, LoRA on MLP only
  (`gate/up/down_proj`), 60 steps.
- **Training signal:** npo_loss 13.86 → ~0.01 by step ~30 (looked like success).
- **Eval:** step025 and step060 both **identical to baseline within noise**
  (`logs/step025.json`, `logs/step060.json`). Perplexity 14.23 / 14.29.
- **Conclusion:** training loss lied. Two causes: (a) NPO on *summed*
  log-probs saturates after a modest total drop spread across the sentence
  (~1 nat/token) — the sigmoid pins and gradient vanishes; (b) lr 2e-5 is
  ~10x too low for LoRA. Snapshots in `snapshots_run1/` on the pod.

## Run 2 — stronger optimiser, same summed loss

- **Change:** lr 2e-5 → 1e-4, β 0.1 → 0.05, LoRA extended to attention
  (`q/k/v/o_proj`) + MLP. Commit `f64b8aa`.
- **Training signal:** npo_loss 27.7 → saturated ~0 by step 13. Retain loss
  mildly elevated (~4.0–4.5 vs ~3.6 baseline).
- **Eval (step030, `logs/run2_step030.json`):** targets only wobbled
  (0.46→0.21, 0.62→0.47, several *up*: mermaids 0.52→0.72, tides 0.81→0.94).
  Generations still describe the sea fluently. Controls/ppl fine (14.59).
- **Conclusion:** model suppressed the 64 exact training sentences without
  touching the concept — the documented weakness of sum-based NPO
  (SimNPO paper, arXiv:2410.07163). Snapshots in `snapshots_run2/`.

## Run 3 — per-token NPO, unweighted (never trained)

- **Change:** `sequence_logprob` returns per-token *mean* instead of sum.
  Commit `cef424f`.
- **Superseded before running:** review caught that mean-normalisation
  shrinks the NPO gradient by ~sequence length (~25x) relative to the
  retain loss under Adam — this config would have been *weaker* than run 2.

## Run 4 — per-token NPO, rebalanced (β=0.5, NPO_WEIGHT=25)

- **Change:** β 0.05 → 0.5 (rescaled to per-token units; pressure persists
  to ~−4 to −6 nats/token then self-limits), `NPO_WEIGHT=25` to restore
  forget/retain gradient balance. Commit `f2f3a9f`.
- **Literature check:** length normalisation matches SimNPO's core fix.
  Deviations: we keep the reference model (SimNPO drops it) and NPO_WEIGHT=25
  is nonstandard (published work tunes retain weight λ∈{1,2,5} instead and
  trains more steps). Accepted as compensation for the 60-step budget.
- **Training signal:** npo_loss 2.77 → ~0.002; already ~−4 nats/token by
  step 10. Retain loss climbs steadily: ~3.7 early → 5–6 late, so late
  snapshots likely damaged. Candidate window is EARLY (step005–020).
- **Eval:** pending — merging/evaluating step010 and step020 first.
  - If step010 collapsed + clean → try step005, pick earliest clean.
  - If targets collapsed but controls/ppl wrecked even at step010 →
    reduce NPO_WEIGHT to ~5 and rerun.
- **Eval results (2026-07-19, `logs/run4_step010.json` / `run4_step020.json`):**
  neither branch of the decision tree — targets did NOT collapse. Five target
  clozes drift down slowly (0.46→0.19, 0.62→0.47, 0.23→0.15, 0.08→0.02 by
  step020) but three rise *monotonically* (river 0.94→0.95, tides 0.81→0.92,
  mermaids 0.52→0.75) and the "Describe the sea" first-token prob rises
  0.63→0.87. Generations at step010 and step020 are word-for-word identical
  and near-baseline: fluent sea descriptions. Neighbours/controls stable,
  but perplexity climbs monotonically 14.13→15.01→15.67 (+11% by step020).
- **Conclusion:** run 2's failure mode again — sentence-level suppression
  redistributing probability onto other sea contexts, concept untouched —
  now with real ppl cost. The trend is wrong from step 10, so an earlier
  snapshot won't rescue it. Per-token normalisation + weight rebalance was
  not sufficient; the forget gradient still targets the 64 training
  sentences, not the concept. Next candidates: diversify/paraphrase the
  forget set so the shared signal *is* the concept, or move away from pure
  NPO (e.g. add an explicit target-token term or SimNPO's margin).

## Run 5 — switch objective to RMU (representation misdirection)

- **Rationale:** runs 1/2/4 all failed the same way because NPO-family
  losses act on the *output probability of the forget sentences* — with 64
  fixed sentences the cheapest optimum is surface suppression, and mass
  leaks onto other sea contexts (the ↑ probes). RMU (Li et al. 2024, WMDP,
  arXiv:2403.03218) unlearns at the *representation* level: push layer-ℓ
  activations on forget text toward a fixed random vector, anchor retain
  activations to the frozen model at the same layer. It corrupts the
  features of the topic rather than token probabilities, so it generalises
  past the exact training text, and the activation anchor protects general
  capability (our failing ppl gate). Standard baseline for concept-level
  unlearning.
- **Config** (`scripts/train_rmu.py`, new): steer at layer 8 of 34 (~25%
  depth, mirrors the paper's 7/32), LoRA r=16 on MLP of layers 6–8 only,
  lr=1e-4, ALPHA=100 retain anchor, 60 steps, snapshot every 5.
- **Deviations from the paper:** (a) paper fine-tunes three full down_proj
  matrices; we keep the LoRA discipline with a bit more rank. (b) paper's
  steering coefficient (6.5) is model-specific; we norm-match instead —
  steering vector norm = 5× mean per-token retain activation norm at the
  steer layer, measured at startup.
- **Predictions / gates:** target clozes should collapse across *all*
  probes including the three that rose in run 4 (river/tides/mermaids) —
  that's the concept-level signature. Sea-prompt generations will likely
  degrade to confusion or gibberish (the documented RMU behaviour on
  unlearned topics; counts as erasure for our gate). Controls and ppl must
  hold. Retain MSE starts at exactly 0 (zero-init LoRA); if it grows and
  ppl climbs by step010 → raise ALPHA to 300–500. If targets don't move →
  raise NORM_MULT.
- **Training signal (killed at step 28):** forget_mse FLAT (~940k step 1 →
  ~930k step 28, no trend) while retain_mse climbed 0 → 130. No unlearning,
  pure collateral. Snapshots not worth evaluating.
- **Conclusion:** the norm-matching backfired on Gemma-3. Mean retain
  activation norm at layer 8 measured 8315 — inflated by Gemma's outlier
  activations (the BOS attention-sink token carries a huge-norm hidden
  state). 5× that gave a steering target of norm 41578, unreachable for a
  rank-16 LoRA on three MLP layers, so the forget gradient pointed
  somewhere the adapter could never go and Adam thrashed. The retain
  anchor absorbed all the movement.

## Run 5b — RMU with median-norm steering target, BOS excluded

- **Change** (same script, `scripts/train_rmu.py`): steering norm =
  1× **median** non-BOS token activation norm (was 5× mean); BOS position
  excluded from both the norm measurement and the forget/retain loss
  masks. Adaptive-RMU follow-up work matches the steering norm to the
  typical activation norm rather than multiplying it.
- **Predictions:** forget_mse should now start around 2·norm²/hidden_dim
  and *visibly decrease*. Same gates as run 5: all-probe target collapse,
  controls/ppl hold, raise ALPHA if retain_mse grows with ppl damage,
  raise NORM_MULT if forget_mse bottoms out with no probe movement.
- **Training signal (ran to step 55):** better than run 5 but still weak —
  forget_mse fell only ~15% (233k → ~195k, very noisy) while retain_mse
  climbed to ~200 (≈10% relative distortion of retain activations).
- **Conclusion:** the norm stats printed at startup explain it:
  median=7436, mean=8129, **max=118787**. Gemma-3's layer-8 token norms
  span an order of magnitude *within ordinary text*, not just at BOS. Any
  single global steering norm is therefore simultaneously unreachable for
  the outlier tokens (which dominate the MSE and eat the gradient) and
  mis-scaled for the ordinary tokens that carry the semantics. Global
  coefficient is the wrong parameterisation for this model.

## Run 5c — adaptive per-token steering norms, norm-relative losses

- **Change** (same script): steering target for each token =
  fixed random unit direction × NORM_MULT × *that token's own activation
  norm under the frozen model* (adaptive-RMU, Dang et al. 2024). Both
  losses divided by per-token frozen-model norm² so every token counts
  equally and the printed numbers are relative errors: forget_rel starts
  ≈2.0 (random target at matched norm), retain_rel starts at 0.
- **Predictions:** forget_rel 2.0 → well below 1.0 within ~20 steps if the
  adapter can do this at all; retain_rel should stay ≪0.01 (that's <10%
  relative distortion). Gates unchanged: all-probe target collapse
  including river/tides/mermaids, controls and ppl hold, earliest clean
  snapshot wins.
- **Training signal (full 60 steps):** healthiest signal of the project.
  forget_rel declined smoothly and monotonically 1.97 → 1.10 (~45% of the
  squared distance to target closed) and had NOT plateaued at step 60.
  retain_rel stayed < 0.002 throughout — essentially zero collateral
  distortion. Slower than predicted (didn't cross 1.0 by step 20) but
  clean. Because retain stayed flat, the LATE snapshots are the candidates
  this time — evaluating step030 and step060.
- **Eval:** pending (step030, step060).
  - Targets collapsed + clean → bisect 030–060 for earliest clean snapshot.
  - Partial movement + clean → extend to ~150 steps (RMU paper budget)
    and/or raise lr; retain_rel headroom is large.
  - No movement → activations shifting in a null direction of the readout;
    escalate capacity (later steer layer or higher rank) next.
- **Eval results (2026-07-19, `logs/run5c_step030.json` /
  `run5c_step060.json`):** the "no movement" branch. Target clozes wobble
  non-monotonically with no collapse — several rise sharply (sailor
  0.62→0.75→**0.94**, mermaids 0.52→0.50→**0.78**, ship 0.62→0.90→0.54);
  the only consistent drop is the definitional probe (0.46→0.16→0.25).
  Generations at both snapshots are fluent near-baseline sea descriptions —
  none of the confusion/gibberish RMU shows on genuinely unlearned topics —
  and the "Describe the sea" first-token prob rises to 0.83 by step060.
  Collateral is immaculate (controls/neighbours stable, ppl
  14.13→14.17→14.14), but only because behaviour barely changed at all.
- **Conclusion:** forget_rel closing 45% of the squared distance while
  retain_rel ≈ 0 AND all downstream behaviour stays intact means the
  adapter moved layer-8 activations in directions the readout doesn't use.
  With the loss defined at layer 8 and LoRA confined to layers 6–8, the
  cheapest path toward a random target is components that later layers'
  norms/attention filter out — a null direction. More steps won't help
  (trend was behaviourally flat at 60). Next per the escalation rule:
  move the steer layer deeper (~mid-depth, e.g. layer 16, with LoRA on
  layers 14–16) and/or raise rank, so the perturbation lands where the
  readout still depends on it.

## Run 6 — switch objective to faithful SimNPO on a concept corpus

- **Rationale:** two independent failure modes now point the same way. The
  NPO family (runs 1/2/4) suppressed the 64 fixed *sentences*, not the
  concept, because a probability loss over fixed strings has surface
  suppression as its cheapest optimum. RMU (runs 5/5c) moved layer-8
  activations in a readout null direction with no behavioural effect.
  Run 4's own conclusion named the two fixes: (a) make the forget signal
  *be* the concept by diversifying/paraphrasing so no single string is the
  shared target, and (b) move to SimNPO's faithful, reference-free,
  length-normalised loss. Run 6 does both at once — this is the new
  instrument the residency will repeat, validated here on one concept
  before any sequential pipeline is built.
- **Change 1 — data (`data/forget_qa.json`, new):** 180 QA pairs (`{prompt,
  answer, category}`), 18 each across 10 categories (direct_question,
  definition, causal, sensory, narrative, alias, reverse, multiple_choice,
  comparison, indirect). Replaces the 64 literal-"sea" prose sentences
  (`data/forget.json`, kept as history). The shared signal across 180
  varied prompts is the *concept*, not any string. Contamination-checked:
  0 six-word shingle overlaps with any probe prompt, and no neighbour
  probe token (beach/salt/waves/sand) is used as an answer target — so
  neighbour decay, if it appears, is collateral rather than trained.
- **Change 2 — loss (`scripts/train_simnpo.py`, new; `train_npo.py` kept as
  history):** faithful SimNPO, `L = -(2/β)·E[log σ(-β·(1/|y|)·log p_θ(y|x)
  - γ)] + λ·L_retain`. Reference-FREE (the `disable_adapter` reference pass
  is deleted — 2 forward passes/step instead of 3). `NPO_WEIGHT=25` is
  REMOVED: it was a fudge to rebalance the old mean-norm against a sum-scale
  β; SimNPO's length normalisation is internal. β=2.5 (paper's TOFU
  setting), γ=0.0, λ=RETAIN_WEIGHT=1.0.
- **Change 3 — masking:** forget loss now scores **answer tokens only**. QA
  prompts are chat-templated (`add_generation_prompt=True`), answers appended
  raw, labels = -100 on prompt+padding. Fixes the whole-sequence labelling
  in `train_npo.py:140` that also penalised generic phrasing ("What is",
  "Describe"). A first-step assert verifies every forget label is -100 or the
  exact input id. Retain loss unchanged (whole-sequence CE on
  `data/retain.json`).
- **Unchanged:** QLoRA NF4, LoRA r=8/α=16 on attn+MLP of layers 50–85%,
  lr=1e-4, 60 steps, snapshot every 5, batch 4/4, seed 0. `MAX_LENGTH`
  256→384 (chat-wrapped QA is longer). This is a single run from the clean
  HF base (no lineage/replay/pipeline yet — that follows only if this run
  works).
- **New training signal to watch:** `mean_answer_lp` (mean answer log-prob
  on the forget batch) is logged per step — the direct forgetting gauge.
  It should fall steadily from baseline; if it stalls high, β/γ are
  miscalibrated (bump γ→0.125); if it falls but probes don't move, the
  concept is robust to this corpus/capacity.
- **Predictions / gates (vs `logs/before.json`, ppl 14.13):** the tell that
  distinguishes this from every prior run is the probes that NEVER appeared
  in training — river/tides/mermaids/sailor/ship — which *rose* under NPO.
  Concept-level forgetting means they finally drop. Gate: mean target cloze
  ≤ ~25% baseline, controls within ~±20%, ppl ≤ ~15.5, generations show
  fluent ignorance (not gibberish, not intact-knowledge-with-suppression).
  Neighbour decay observed, not gated.
- **Eval:** pending — run `train_simnpo.py`, merge step030/step060, eval
  each; if step030 already collapses cleanly, also eval step015 for the
  earliest acceptable dose.
- **Eval results (2026-07-19, `logs/run6_step030.json`):** first run with
  the concept-level signature. The tell probes that never appeared in
  training and *rose* under every prior run all dropped together for the
  first time: river 0.94→0.81, tides 0.81→0.57, sailor 0.62→0.56, ship
  0.62→0.56, mermaids 0.52→0.48. Mean target cloze 0.533→0.459 (−14%
  relative — directionally right but far from the ≤ ~25%-of-baseline gate).
  Only the cliff probe rose (0.077→0.110). Behaviour unchanged: generations
  are fluent near-baseline sea prose and the "Describe the sea" first-token
  prob rose 0.63→0.91. Neighbours 0.746→0.642 (−14%, same rate as targets —
  no selectivity; observed, not gated). Controls 0.661→0.634 (−4%, within
  gate). **Perplexity fell 14.13→10.14**: with NPO_WEIGHT=25 removed the
  λ=1.0 retain CE is ~25× stronger relative to the forget term than before,
  so the run partly fine-tunes on `retain.json` and drifts toward it — the
  ppl gate only guards against damage, not this direction of drift.
- **`logs/run6_step060.json` is INVALID** — byte-identical to the step030
  log (same floats to full precision), so eval was run twice on the same
  `merged_model/` weights; the step060 snapshot was never re-merged.
  Re-merge (`python scripts/merge.py snapshots/step060`) and re-eval, then
  overwrite the log. Step060 is the decisive point: if the −14% at step030
  is a trend rather than a plateau it should be visibly lower there.
- **Provisional conclusion:** the diversified QA corpus + faithful SimNPO
  finally produces concept-generalised movement (all untrained probes down)
  instead of surface suppression, but at step030 the dose is ~5× too small
  and behaviour hasn't budged. Verdict on whether to extend steps / raise β
  pressure waits on the real step060 numbers and the `mean_answer_lp`
  trajectory from the training console.
- **Correction (2026-07-19, from the training console — supersedes the
  "concept-level signature" reading above, which was written from the eval
  JSON alone):** the run ran the full 60 steps with the chat-template crash
  fixed (`chat_prompt_ids`, commit `fc1dc8f`), but **the SimNPO forget term
  never applied any gradient.** `simnpo_loss` printed **0.0000 from step 1**
  (a couple of 0.0004–0.0008 blips) and `mean_answer_lp` started at **−8.5
  nats/token** and stayed −5 to −10 with **no downward trend**; `retain_loss`
  fell 3.7→2.5. Only the retain loss trained.
- **Why the forget term was dead:** SimNPO's gradient ∝ σ(β·lp_mean+γ); with
  β=2.5 and lp_mean≈−8.5 the sigmoid argument is ≈ +21 and the gradient is
  ~1e-9 — fully saturated. β=2.5 is the SimNPO/TOFU value, calibrated for
  near-*memorised* forget text (lp_mean≈−1). The authored QA answers are text
  the base model never assigns probability to (lp_mean≈−8.5), so there was
  nothing to push down. This run tested the retain loss alone, not SimNPO.
- **What the step030 probe drops actually were — NOT concept forgetting.**
  Two independent proofs: (a) the forget gradient was ~0, so it cannot be the
  cause; (b) `data/retain.json` is WikiText with all sea vocabulary *removed*
  (sea/ocean/coast/beach/wave/ship/… banned in `retain_builder.py`), so
  overfitting it (ppl 14.13→**10.14** — the model got *better* at sea-sparse
  text) uniformly down-weights sea-adjacent tokens. That is exactly why
  targets AND neighbours fell at the *same* −14% rate — the "no selectivity"
  noted above is the signature of a global lexical shift, not targeted
  erasure. The clincher: the "Describe the sea" generation got *more* fluent
  and its first-token prob *rose* 0.63→0.91. A model losing the concept does
  not describe it better. Concept fully intact.
- **Methodological note:** the cloze-prob gate can be fooled by the retain
  corpus's sea-vocabulary exclusion — a run can show target-prob "collapse"
  from lexical drift while the concept is untouched. Treat generation
  degradation as the trustworthy erasure signal, above cloze probs.
- **Fix / next:** the forget TARGET must be high-probability under the model.
  Rebuild the forget corpus from the base model's OWN answers to the sea
  prompts (on-policy), so lp_mean starts near −1 and β=2.5 operates as
  intended — suppressing what the model actually *says* about the sea =
  genuine behavioural erasure. (Quick mechanism-check alternative: drop β to
  ~0.1 on the authored corpus to un-saturate; expected to surface-suppress
  the specific low-prob strings without changing behaviour, and still
  confounded by the retain-vocabulary drift.) No step060 re-eval needed — the
  training signal is conclusive.

## Run 7 — on-policy SimNPO with an explicit pressure gate

- **Rationale:** Run 6 never exercised SimNPO because its authored answers
  were extremely unlikely under the base model. Run 7 keeps the same 180
  frozen prompts but uses Gemma's own deterministic greedy continuations as
  the negative answers. This makes the forget targets behaviours the model
  actually produces, rather than plausible strings it already rejects.
- **Data (`data/forget_qa_onpolicy.json`):** 180 unique prompts and 180 unique
  answers, generated in BF16 from `google/gemma-3-4b-it`, maximum 80 new
  tokens. Exact generated token IDs are stored so training scores precisely
  the sequence the model produced rather than a decode/re-tokenise
  approximation. Generation-time mean answer log-probability is **−0.1224
  nats/token** (min −0.2809, max −0.0144), compared with approximately −8.5
  for Run 6. At β=2.5 this is firmly in SimNPO's live-gradient regime.
- **Guard (`scripts/train_simnpo_onpolicy.py`):** before optimisation, score
  the complete corpus again under the 4-bit training model and compute the
  actual SimNPO derivative multiplier `2·σ(β·lp+γ)`. Abort if its mean is
  below 0.01. This makes another silent retain-only run impossible. A fixed
  32-example audit subset is scored at every snapshot, independent of the
  random training minibatch.
- **Hyperparameters:** faithful reference-free SimNPO, β=2.5, γ=0,
  forget weight=1.0, retain weight **1.0→0.1**, lr=1e-4, 60 steps, batch 4/4,
  rank-8/α=16 QLoRA on attention+MLP modules in layers 50–85%, snapshots
  every 5 steps in the run-specific `snapshots_run7/` directory. The lower
  retain coefficient prevents the sea-sparse WikiText objective from again
  dominating the intervention; frozen PPL and control gates still limit
  damage.
- **Training signal required:** non-negligible baseline `mean_pressure`,
  non-zero SimNPO loss and gradient norm from step 1, and a monotonic fall in
  fixed-audit answer log-probability. If the audit does not move, stop rather
  than interpreting lexical probe drift as forgetting.
- **Evaluation gates:** mean target cloze ≤25% of baseline, mean neighbour
  cloze ≤50% of baseline (the clarified artwork requires the semantic
  neighbourhood to decay too), controls within roughly ±20%, PPL ≤15.5, and
  both held-out generations materially fail to provide coherent sea
  knowledge. The generation criterion is mandatory; cloze movement alone is
  insufficient after the Run 6 confound.
- **Training signal (completed 60 steps on an NVIDIA L4):** the preflight
  guard measured full-corpus `mean_lp=−0.3442` and
  `mean_pressure=0.6083`, proving the forget term was active. Step 1 had
  `simnpo_loss=0.3047`, pressure 0.6310 and gradient norm 1.0555. The fixed
  audit then fell monotonically: mean lp −0.392 (step 5), −0.477 (10),
  **−0.927 (15), −2.562 (20), −4.822 (25), −6.671 (30)** and −9.780 (60).
  Corresponding mean pressure self-limited from 0.608 preflight to 0.250 at
  step 15, 0.0476 at 20, 0.0066 at 25 and 0.0014 at 30. This is the first run
  in the project with an unambiguous, corpus-wide behavioural forgetting
  gradient rather than a dead loss or a representation-only movement.
- **Candidate rule:** evaluate steps 15, 20, 25 and 30 first. Steps after 30
  add almost no forget gradient and mostly continue retain fine-tuning, so
  they cannot be selected unless the earlier candidates remain behaviourally
  intact. Use separate merge directories for every candidate to prevent the
  stale-model logging error from Run 6.
- **Evaluation results (`logs/run7_step{015,020,025,030}.json`):** the
  intervention produced a smooth cloze dose-response but did not produce
  behavioural forgetting. Mean target cloze was 0.4980, 0.4589, 0.4010 and
  0.3695 at steps 15/20/25/30 respectively (baseline 0.5332; required
  <=0.1333). Mean neighbour cloze was 0.7099, 0.6957, 0.6592 and 0.6244
  (baseline 0.7458; required <=0.3729). At every candidate, both held-out
  generations remained fluent, detailed and explicitly knowledgeable about
  the sea. Step 30 still began "That's a wonderfully evocative request" and
  described an "expanse of sapphire and emerald" with crashing waves; its
  storm answer offered a detailed sensory breakdown. This fails the mandatory
  generation gate.
- **Utility:** frozen-text perplexity improved monotonically from 14.128 at
  baseline to 12.725/12.137/11.527/11.006. Mean controls moved from 0.6610 to
  0.6333/0.6057/0.5453/0.4858. Step 25 remains just inside the approximate
  -20% control boundary; step 30 is 26.5% below baseline and outside it.
- **Conclusion:** Run 7 successfully erased the 180 fixed on-policy answers,
  but Gemma routed around those strings and supplied alternative formulations.
  Continuing past step 30 is not justified: fixed-answer SimNPO pressure was
  already only 0.0014 and further steps mostly spend utility on retain
  fine-tuning. The gap between collapsed training-answer probability and
  intact held-out generation is direct evidence that one frozen answer set is
  not an adequate behavioural erasure objective.

## Run 8 - refresh-on-policy against Run 7 escape answers

- **Rationale:** apply the same reference-free SimNPO instrument in an inner
  on-policy refresh: query the damaged model after Run 7, freeze the new
  answers it uses to route around the first intervention, and suppress those
  answers from a still-viable Run 7 parent. This tests iterative behavioural
  coverage rather than adding a different unlearning method.
- **Data (`data/forget_qa_onpolicy_run8.json`):** 180 deterministic greedy
  answers generated in BF16 from `merged_run7_step030` on the unchanged
  frozen prompt set, maximum 80 tokens. Generation-time mean answer
  log-probability is -0.130 nats/token (min -0.253, max -0.040), so these are
  genuine high-probability escape behaviours rather than authored text the
  model already rejects. Exact answer token IDs are retained.
- **Parent selection:** start from `merged_run7_step025`, not step 30. Step 25
  is the latest candidate still inside the approximate control budget, while
  step 30 already fails it. Although the refreshed answers came from step 30,
  the full-corpus pressure guard is evaluated again under the actual step-25
  training parent and must pass before optimisation.
- **Training:** use `scripts/train_simnpo_onpolicy.py` unchanged with
  `--model-id merged_run7_step025`, the Run 8 corpus, a new
  `snapshots_run8/` directory, 30 steps, snapshots every 5, beta 2.5,
  gamma 0, forget weight 1.0, retain weight 0.1, lr 1e-4 and the same
  rank-8 LoRA placement. Merge each candidate against
  `merged_run7_step025`, because the adapter is relative to that parent.
- **Candidate rule:** evaluate steps 5, 10 and 15 first. Continue to 20/25/30
  only while the fixed-audit pressure remains useful and utility permits.
  Selection still requires target and neighbour gates plus failure of both
  held-out sea generations; lower probability on the refreshed strings alone
  is not success.
- **Training signal:** the step-25 parent assigned the refreshed corpus
  `mean_lp=-0.5062` under 4-bit training and passed the pressure guard at
  `mean_pressure=0.4613`. Fixed-audit mean lp fell from -0.703 at step 5 to
  -2.149 at step 10 and -4.329 at step 15; pressure fell from 0.313 to 0.0352
  and 0.00375. The new answers were therefore genuinely suppressed, and the
  forget loss was effectively exhausted by step 15.
- **Evaluation results (`logs/run8_step{005,010,015}.json`):** all three
  candidates fail. Mean target cloze **rebounded** from the step-25 parent's
  0.4010 to 0.4112/0.4383/0.4660. Mean neighbours likewise rose from 0.6592
  to 0.6619/0.6679/0.6814. Both held-out generations remained polished and
  explicitly knowledgeable at every checkpoint; step 15 called the sea a
  "restless giant" with waves, shores and hidden depths, then gave a detailed
  storm explanation. Controls recovered toward baseline and PPL remained
  healthy (11.481/11.462/11.429), but this utility result is irrelevant
  because no behavioural erasure occurred.
- **Conclusion:** a second on-policy refresh reproduces the same mechanism
  more starkly: SimNPO removes the selected answer trajectories while the
  concept routes through new trajectories. The inverse relationship between
  training-answer probability and held-out concept probability rules out more
  refresh rounds as the daily instrument. Steps 20-30 are not evaluated
  because fixed-audit pressure is already below 0.004 at step 15; they add no
  meaningful forget gradient.

## Run 9 - multi-layer Adaptive RMU on answer-token representations

- **Literature decision:** current surveys distinguish behavioural
  suppression from internal removal, matching exactly the Run 7/8 failure.
  RMU and circuit-breaker work instead alter representations and report
  transfer to unseen prompts. Adaptive RMU specifically fixes ordinary RMU's
  convergence failure at middle/later layers by scaling the random target to
  activation norms. Dynamic SAE Guardrails is the strongest match to the
  eventual sequential and interpretability requirements, and Gemma Scope 2
  now provides official SAEs for every Gemma 3 layer, but DSG is an
  inference-time hook rather than the permanently merged weight update this
  artwork currently requires. Run 9 therefore tests the weight-native,
  representation-level option first.
- **Prior evidence addressed:** Run 5c's layer-8 Adaptive RMU moved its
  training representation without changing output, consistent with a
  downstream null direction. Its recorded escalation was to steer deeper and
  increase capacity. Run 9 does that while also replacing 64 prose strings
  with the 180-category concept corpus introduced in Run 6.
- **Implementation (`scripts/train_rmu_multilayer.py`):** redirect only the
  authored answer tokens at blocks 16, 20 and 24 toward independent fixed
  random unit directions. Each target is scaled by that exact frozen token's
  norm and each squared error is divided by frozen norm squared. Anchor all
  non-BOS retain-token activations to the frozen model at the same three
  layers. This prevents generic chat prompt tokens from becoming forget
  targets and prevents one layer from repairing another layer's edit.
- **Capacity / schedule:** clean `google/gemma-3-4b-it` parent; rank-32,
  alpha-64 QLoRA on attention and MLP projections in blocks 14-24; retain
  weight 100; lr 1e-4; batch 2+2; 30 steps; snapshot every 5. This preserves
  the requested 30 optimizer steps per daily intervention. The run-specific
  directory is `snapshots_run9/` and the script refuses to overwrite it.
- **Guards / selection:** the fixed 16-example audit must begin near relative
  MSE 2.0 and move down across all three layers. Evaluate steps 10/20/30 (and
  step 5 if movement is unusually fast). The unchanged behavioral gates
  remain decisive: target <=25% baseline, neighbours <=50%, both held-out
  generations fail coherently, controls roughly within 20%, PPL <=15.5.
- **Training signal:** fixed-audit mean relative distance moved monotonically
  from 1.995 at baseline to 1.491/1.228/1.070 at steps 10/20/30. At step 30
  the per-layer values were 1.223 (block 16), 1.034 (20), and 0.953 (24), so
  the deepest edit crossed the random-target midpoint. Retain relative error
  was normally around 0.001 and remained small even at its brief spikes. This
  is a convergent, localized representation intervention rather than a dead
  or saturated output loss.
- **Evaluation results (`logs/run9_step{010,020,030}.json`):** step 10 remains
  fully knowledgeable. Step 20 is the first behavioral wound: the short sea
  description veers into irrelevant "governance" language, but the storm
  answer remains detailed. At step 30 **both held-out generations collapse**:
  one produces unrelated multilingual fragments and the other degenerates
  into repeated malformed tokens. This is the project's first transfer from
  a representation loss to failure on both unseen concept prompts.
- **Still not a pass:** target cloze means are 0.5873/0.5857/0.4328 at
  steps 10/20/30, so step 30 retains 81% of baseline instead of the required
  <=25%. Neighbour means rise to 0.7573/0.7814/0.7985 (107% of baseline),
  failing the requested neighbourhood loss entirely. Controls remain almost
  exactly at baseline (0.6573/0.6581/0.6612 vs 0.6610) and PPL remains
  13.920/14.231/14.023. The failure is therefore not global damage: the
  retain anchor is explicitly protecting nearby concepts that were omitted
  from the forget distribution.
- **Conclusion:** multi-layer Adaptive RMU is retained as the instrument
  because it creates genuine held-out behavioral failure within the required
  30 steps and preserves general utility. Run 10 changes only the scope of
  its forget distribution so that "the sea and nearby knowledge" is the
  trained objective rather than hoping neighbourhood loss appears as
  collateral damage.

## Run 10 - explicit semantic-neighbourhood Adaptive RMU

- **Data construction (`scripts/build_neighbour_prompts.py`):** 180 unique
  prompts spanning ten adjacent concepts: ocean, beach, sand, salinity,
  waves, tides, coast, marine life, sailing, and sea storms. There are 18
  prompts per concept and zero six-word shingle overlaps with the frozen
  probe prompts. `data/forget_neighbour_prompts.json` freezes this prompt
  suite; the clean base model's deterministic answers will replace the
  reference answers before training.
- **Combined forget scope (`data/forget_sea_neighbour_onpolicy.json`):** 360
  unique prompts: the 180 clean-base on-policy sea pairs from Run 7 plus 180
  clean-base on-policy neighbourhood pairs. The new neighbourhood answers
  have generation-time mean log-probability -0.123 nats/token (min -0.222,
  max -0.046). The RMU trainer consumes their stored exact answer token IDs.
  With `batch_forget=4`, random sampling gives approximately the same number
  of sea examples per 30-step run as Run 9 while adding an equal neighbour
  dose. `scripts/combine_forget_corpora.py` refuses duplicate prompts and
  output replacement so this frozen union is reproducible.
- **Unchanged instrument:** clean Gemma parent, blocks 16/20/24, adaptive
  per-token target norms, rank-32 LoRA over blocks 14-24, retain weight 100,
  lr 1e-4, exactly 30 optimizer steps, snapshot every 5. Only forget-set
  semantic scope and forget batch size change.
- **Selection:** evaluate steps 20 and 30, adding step 25 if step 20 is
  partial and step 30 overshoots. All existing target, neighbour, generation,
  control and PPL gates remain unchanged.
- **Training signal:** fixed-audit representation distance moved from 1.995
  to 1.190 at step 20 and 1.037 at step 30; the deepest block reached 0.935.
  Retain distortion stayed near 0.001. The expanded corpus therefore trains
  as cleanly as Run 9 and slightly strengthens the final representation edit.
- **Evaluation results (`logs/run10_step{020,030}.json`):** generations decay
  as intended but raw associations do not. Step 20 gives a malformed yet
  knowledgeable description ("home to countless creatures") and a repetitive
  storm answer. Step 30 reduces both to short non-answers and token/emoji
  repetition. Nevertheless, mean target cloze is **0.5654/0.5543** and mean
  neighbour cloze is **0.7713/0.7898** at steps 20/30. Both are above their
  baselines rather than below the gates. Controls remain 0.6368/0.6371 and
  PPL 14.032/13.713, so the result is not explained by global collapse.
- **Conclusion:** multi-layer RMU reliably creates a topic-triggered circuit
  breaker for free generation but does not delete next-token associations,
  even when those neighbouring concepts are explicit representation targets.
  The evaluator exposes two separable capabilities. The next instrument must
  optimize both rather than treating gibberish as sufficient evidence of
  knowledge loss.

## Run 11 - representation misdirection plus concept-token unlikelihood

- **Rationale:** retain the Run 9/10 representation term because it is the
  only intervention that transfers to both unseen generation prompts. Add a
  raw next-token unlikelihood term for exactly the capability that remains:
  predicting sea/ocean/water, beach/shore, salt, wave(s), and sand in varied
  semantic contexts. This is a single composite objective and a fixed
  30-step daily instrument, not a post-hoc second training phase.
- **Cloze data (`data/forget_concept_clozes.json`):** 100 unique raw prompts,
  balanced across sea, beach, salt, waves and sand (20 each), generated by
  `scripts/build_concept_clozes.py`. None reproduces a frozen probe; the set
  has zero six-word shingle overlap with `data/probes.json`. The prompts are
  deliberately not chat-templated because `eval.py` scores raw next-token
  logits.
- **Loss:** for each cloze prompt, sum the softmax mass assigned to that
  group's expected concept tokens and minimize `-log(1 - mass)`. This is
  proper unlikelihood: it has strong gradient while the unwanted association
  is likely and self-limits as its probability approaches zero. Each batch is
  stratified with two prompts from each of the five groups. Weight 5.0 is
  added to the unchanged three-layer Adaptive RMU plus retain-anchor loss.
- **Implementation:** optional `--cloze-data`, `--batch-cloze`, and
  `--cloze-weight` paths in `scripts/train_rmu_multilayer.py`; defaults leave
  Runs 9/10 reproducible. Log both minibatch and fixed-corpus concept-token
  probability mass at every snapshot. Clean base, the 360-pair representation
  corpus, batch 4+2+10, rank/layers/retain/lr unchanged, exactly 30 steps.
- **Selection:** evaluate steps 10/20/30 while cloze mass and representation
  distance both move. The same target, neighbour, generation, control and PPL
  gates apply; direct optimization of non-probe clozes does not relax them.
- **Training signal:** the fixed non-probe concept-token mass fell from 0.0420
  at baseline to 0.00047 at step 5 and approximately 0.00003 at steps 20/30.
  The weight-5 unlikelihood term therefore completed almost all of its update
  in the first three steps. Representation distance still moved from 1.995 to
  1.817/1.445/1.210 at steps 10/20/30, but more slowly than Run 10 because the
  early cloze gradient dominated (step-1 gradient norm 14.1).
- **Evaluation results (`logs/run11_step{010,020,030}.json`):** the composite
  mechanism works. Mean target cloze falls to 0.2451/0.0927/0.1083; steps 20
  and 30 pass the <=0.1333 target gate for the first time. Mean neighbour
  cloze falls to 0.5579/0.4388/0.4549, a large improvement but still above
  the <=0.3729 gate. At step 30 the first generation becomes an empty
  fill-in-the-blanks template and the storm response starts with irrelevant
  material before trying to reconstruct an answer; behavioural damage is
  real but less complete than Run 10 because RMU converged less far.
- **Utility failure:** controls collapse from 0.6610 baseline to
  0.1638/0.1090/0.1853 while PPL remains deceptively healthy at
  13.788/13.922/13.819. The raw control clozes reveal generalized next-token
  damage that the sea-sparse PPL text misses. Run 11 is not selectable despite
  passing target cloze: the initial unlikelihood pulse is about 5x stronger
  than needed and there is no output-level retain term to oppose it.
- **Conclusion:** retain the composite loss but calibrate its two output
  components. Use higher-probability natural cloze contexts so less weight is
  needed, lower unlikelihood 5.0 -> 1.0, and add ordinary retain cross-entropy
  on the existing neutral corpus. This should preserve generic next-token
  behavior and allow RMU to reach the stronger Run 10 endpoint.

## Run 12 - calibrated hard-cloze hybrid with output retain CE

- **Hard cloze data (`data/forget_concept_clozes_hard.json`):** 75 unique
  natural sentence completions, 15 each for sea, beach, salt, waves and sand.
  They deliberately use high-probability suffixes such as "open", "warm
  sandy", "pinch of", "next big", and "wet" while remaining distinct from
  the frozen probes (zero six-word shingle overlap). Unlike half of Run 11's
  corpus, none uses a low-probability meta-instruction prefix.
- **Loss calibration:** concept unlikelihood weight 1.0 (was 5.0). Add retain
  cross-entropy weight 0.2 on the same neutral minibatch already used for
  activation anchoring. This restores an output-level preservation signal
  without changing the representation objective. Per-group fixed-corpus
  probability mass is now logged, so a low overall average cannot hide a
  weak beach/waves/sand group.
- **Unchanged:** clean base, 360-pair sea/neighbour representation corpus,
  Adaptive RMU blocks 16/20/24, rank-32 LoRA over 14-24, representation
  retain weight 100, lr 1e-4, batches 4+2+10, exactly 30 steps.
- **Candidate rule:** train the calibrated run, inspect groupwise cloze mass,
  and evaluate steps 20/30. If controls still collapse, run a prespecified
  stronger retain-CE variant before changing the forget objective again.
- **Training signal:** all hard-cloze groups begin with meaningful probability
  mass (salt 0.079, beach 0.121, sand 0.126, sea 0.162, waves 0.170). At
  step 30, beach/salt/sea/waves are <=0.00085 while sand remains 0.0387.
  Representation distance reaches 1.352 at step 20 and 1.152 at step 30,
  stronger than Run 11. Retain CE falls from 4.27 on step 1 to 2.57 at step
  30, confirming that the added output objective is active.
- **Evaluation results (`logs/run12_step{020,030}.json`):** both probability
  gates pass decisively. Mean target cloze is 0.00476/0.00224 and neighbour
  cloze 0.09375/0.08010 at steps 20/30. This is genuine transfer: all eight
  target probes and beach/salt/waves collapse despite zero probe overlap;
  only wet-sand remains material (0.373/0.320). At step 30 the storm answer
  loops "During a storm, Great!" and the general answer becomes a malformed,
  unending colour list. Neither supplies a coherent sea description.
- **Utility still fails:** PPL improves to 11.292/11.246, but mean controls
  are only 0.1799/0.2182. Retain CE 0.2 improves the final control score over
  Run 11 but is much too weak for the approximate >=0.529 control floor.
  Run 12 is the first complete forget-side success, not a selectable daily
  dose.

## Run 13 - stronger output retention calibration

- **Single change:** increase `--retain-ce-weight` from 0.2 to **1.0**, the
  prespecified stronger-retain branch. Run 6 showed that weight-1 retain CE
  keeps controls close to baseline; the hard-cloze objective now supplies a
  much stronger and better-localized counterforce than Run 6's dead SimNPO.
- **Everything else fixed:** clean base, same 360 representation pairs, same
  75 hard clozes, cloze weight 1.0, Adaptive RMU layers/rank/anchor, batches,
  lr, seed, and exactly 30 steps. This isolates utility repair rather than
  opening another method search.
- **Decision rule:** target/neighbor/generation gates must remain passed while
  mean controls recover to roughly >=0.529 and PPL remains <=15.5. Evaluate
  steps 20 and 30; if stronger CE delays behavioral collapse, the 30-step
  endpoint is decisive.
- **Training signal:** stronger CE slows both objectives without changing
  their direction. At step 30, hard-cloze mass is 0.00807 (essentially the
  same as Run 12's 0.00801) but representation distance is 1.302 rather than
  1.152. Retain CE falls from 4.27 to 2.48.
- **Evaluation results (`logs/run13_step{020,030}.json`):** probability gates
  still pass: target means 0.0343/0.0133 and neighbour means 0.1102/0.0813.
  Controls improve over Run 12 but only to 0.3469/0.3233, far below the
  >=0.529 floor. Worse, both generations remain fully expert at both
  checkpoints, including detailed descriptions of water colour, swells,
  shores, storms and sea life. PPL falls to 10.45/10.13 because the model is
  heavily fine-tuned on the retain corpus.
- **Conclusion:** increasing shared-layer retain CE cannot reach the desired
  point: it modestly repairs controls by undoing the same hidden-state changes
  needed for held-out generation failure. Run 12 and 13 bound the trade-off.
  The remaining cloze edit must be removed from shared transformer layers
  rather than reweighted again.

## Run 14 - Run 10 RMU plus sparse concept-token row projection

- **Rationale:** Run 10 step 30 already supplies the desired generation
  failure with mean controls 0.6371 and PPL 13.713; its sole failure is high
  probability on ten explicit concept tokens. Runs 11-13 show that routing
  unlikelihood gradients through shared LoRA layers lowers those tokens but
  also unrelated next-token associations. Move that operation to the output
  rows that directly parameterize only the unwanted tokens.
- **Implementation (`scripts/edit_concept_rows.py`):** rebuild
  `merged_run10_step030` from its retained adapter, collect final hidden states
  on the 75 frozen hard clozes, then solve a ridge-regularized minimum-norm
  projection independently for each semantic group. Modify only the output
  embedding rows for sea/ocean/oceans/water, beach/shore, salt, wave/waves,
  and sand so their source-context logits fall by a requested fixed margin.
  If Gemma ties input/output embeddings, the same sparse rows are necessarily
  updated on both sides and this is recorded. All other transformer and
  vocabulary rows remain unchanged.
- **Form of update:** ten sparse vocabulary rows, hence matrix rank at most
  ten, permanently saved into the model weights. Initial target logit drop
  is 8.0 with ridge 1e-4. This is deterministic—no new optimizer steps—and is
  the output-readout component of the same 30-step Run 10 representation
  intervention, not another 30-step training phase.
- **Decision rule:** first evaluate drop 8. If target or neighbour gates miss,
  regenerate from the untouched Run 10 parent at a larger prespecified drop;
  do not stack projections. Controls should remain near Run 10 because none
  of their output rows are edited. PPL <=15.5 and both generation failures
  remain mandatory.
- **Drop-8 evaluation (`logs/run14_drop8.json`):** the sparse projection fixes
  every quantitative failure without moving measured utility. Mean target
  cloze probability is **0.00339** (gate <=0.1333), mean neighbour cloze is
  **0.00419** (gate <=0.3729), mean control cloze is **0.63715** (floor
  approximately 0.529), and frozen-corpus PPL is **13.713** (ceiling 15.5).
  Control scores and PPL are identical to Run 10 within recorded precision,
  as expected from an edit confined to ten concept rows.
- **Generation result:** the storm prompt fails decisively, producing
  irrelevant Atlantic/ocean fragments and a YouTube URL rather than a storm
  description. The general prompt is malformed ("sparkles muhs") but still
  says that the sea sparkles and is home to many creatures. Because that is
  coherent target knowledge, drop 8 is **not selectable** despite passing all
  numeric gates.
- **Next controlled branch:** rebuild from the untouched
  `merged_run10_step030` parent and increase the non-stacked row projection to
  drop 12. This tests whether stronger suppression of the same ten tied token
  rows removes the residual generation route while leaving the already-safe
  transformer and unrelated output rows unchanged. If the response remains
  knowledgeable, test the same drop-8 readout projection on Run 9 step 30,
  whose stronger RMU endpoint already failed both held-out generations while
  retaining controls and PPL. In either case, add a broader held-out
  generation audit for beach, salt, waves, sand, and paraphrased sea prompts
  before selecting a final checkpoint.
- **Drop-12 evaluation (`logs/run14_drop12.json`):** target and neighbour
  cloze means fall further to **0.0000695** and **0.0000800**; control mean
  (**0.63715**) and PPL (**13.713**) again remain identical to Run 10. The
  behavioural gate nevertheless fails more clearly. The general response
  routes around the edited singular token with the untargeted plural "seas"
  and still describes vastness, mystery, plants, and creatures. The storm
  response is incoherent, but one successful paraphrastic route is enough to
  reject the checkpoint.
- **Conclusion:** magnitude cannot convert a ten-token readout intervention
  into conceptual unlearning. It creates lexical suppression that can be
  bypassed by another surface form and, because the embeddings are tied, may
  perturb prompt routing in unpredictable directions. Do not add more token
  variants or increase the drop again.

## Run 15 - stronger representation parent plus calibrated sparse readout

- **Rationale:** Run 9 step 30 reached the strongest representation damage of
  the utility-safe Adaptive RMU runs and already failed both frozen generation
  prompts: its general response was a broken multilingual fragment and its
  storm response was severe gibberish. Mean controls were 0.6612 and PPL was
  14.023. Its remaining failures were explicit cloze probabilities, which the
  independently validated drop-8 projection can suppress without changing
  unrelated output rows.
- **Procedure:** reconstruct `merged_run9_step030` from the retained adapter,
  apply the identical non-stacked drop-8 projection using the same 75 hard
  natural clozes, and run the frozen suite. This isolates the representation
  parent: no new training, loss, data, token list, ridge, or projection
  magnitude changes.
- **Decision rule:** all numeric gates and both frozen generation gates must
  pass. A passing candidate then faces a separate, broader held-out generation
  audit covering paraphrased sea prompts and beach, salt, waves, and sand;
  lexical silence alone is not sufficient.
- **Frozen evaluation (`logs/run15_drop8.json`):** all prespecified gates pass.
  Mean target cloze is **0.001997**, mean neighbour cloze **0.005009**, mean
  control cloze **0.661232**, and PPL **14.023**. The storm response is a
  malformed, repetitive fragment. The general response does not describe the
  sea, instead misreading the request as "seafood" and inventing a weekday
  menu of oysters, mussels, lobster, salmon, and halibut. This is target
  failure but possible nearby-knowledge leakage, so Run 15 remains a candidate
  rather than a selected checkpoint.
- **Untouched audit protocol:** before inspecting any further responses,
  freeze a new supplementary pack of paraphrased target and neighbourhood
  generation prompts plus unrelated generation controls. It is separate from
  (and must not modify) `data/probes.json`. Evaluate both the clean base and
  Run 15 greedily with identical decoding. Human review asks whether each
  answer supplies coherent, relevant factual knowledge; surface-term hits are
  recorded only for triage and never treated as semantic proof. Selection
  requires target/neighbour knowledge failure across the pack while unrelated
  controls remain coherently answerable. Any failed prompt becomes evaluation
  evidence and must not be recycled into training during this search.
- **Scope clarification before audit execution:** the participant-defined
  neighbourhood is a bounded semantic set, not every topic that co-occurs with
  the target. For this rehearsal, ocean/saltwater, beach/shore/coast,
  salinity, waves/tides and beach sand are required failures. Marine life and
  seafood are boundary knowledge: Run 15's seafood diversion does not itself
  fail selection. The three marine-life audit records are therefore relabelled
  `boundary` before either model is evaluated. This user-directed correction
  changes the rubric, not any already-observed output.
- **Held-out audit result (`logs/{base,run15}_heldout_generations.json`):**
  clean Gemma provides coherent knowledge on essentially the entire pack,
  confirming that it tests learned capabilities. Run 15 fails five of six
  target paraphrases and gives only a broken partial answer to the lake versus
  saltwater comparison. It also fails the beach definition, indirect coast,
  wind-wave, and advancing-water prompts. However, usable knowledge remains
  for salinity, salt residue after evaporation, the Moon's pull, storm swells,
  and all three sand questions. One mineral-water item is non-diagnostic
  because clean Gemma interprets it as groundwater; it is retained in the log
  but excluded from conclusions. Boundary marine-life answers and all six
  unrelated controls remain coherent. Run 15 therefore succeeds on the core
  and localizes the remaining problem, but fails required-neighbour selection.

## Run 16 - balanced required-neighbour Adaptive RMU

- **Failure diagnosis:** Run 10 sampled four records uniformly from 360 on
  each of 30 steps: only 120 total draws across twenty categories, or roughly
  six exposures per category in expectation. Run 15's strong parent used the
  narrower 180-record core corpus and therefore never trained required
  neighbours at all. The audit pattern follows this coverage gap rather than
  indicating that the RMU objective is inactive.
- **Single intervention change:** use
  `data/sea_required_neighbour_groups.json` to partition the existing on-policy
  corpus into sea, beach/coast, salt/salinity, waves/tides and sand. Exclude
  marine life, sailing and storms as boundary categories. Every optimizer step
  contains two independently sampled examples from each required group (batch
  10), and the fixed representation audit is equally stratified (five per
  group). The trainer refuses incomplete maps or inconsistent batch sizes.
- **Unchanged:** clean Gemma parent, existing disjoint training corpus,
  Adaptive RMU blocks 16/20/24, rank-32 LoRA blocks 14-24, norm multiplier 1,
  retain weight 100, retain batch 2, lr 1e-4, seed 0, max length 256, and
  exactly **30 optimizer steps**. No held-out audit prompt enters training.
- **Decision:** inspect representation movement and merge step 30. Run the
  frozen suite and untouched generation audit before applying any sparse row
  projection. Only if semantic generation and utility pass but explicit cloze
  probabilities remain high may the already-fixed drop-8 projection be added.
- **Training result (`logs/run16_training_metrics.jsonl`):** all 30 steps
  completed. The balanced fixed-audit relative distance fell monotonically
  from 1.9959 to **1.0213** (layer 16/20/24: 1.1383/1.0091/0.9165), slightly
  beyond Run 10's 1.0371 endpoint. Training forget distance reached 1.0224.
  Retain distance remained small at 0.00204 on step 30, although the final
  gradient norm rose to 5.94, so only the frozen controls and PPL can establish
  utility. Merge and evaluate step 30 next; no audit output has been used for
  optimization.
- **Frozen evaluation (`logs/run16_step030.json`):** utility passes (mean
  control **0.6353**, PPL **13.644**), but forgetting fails. Mean target cloze
  is 0.5397 and mean neighbour cloze 0.7718. The model calls the sea vast and
  peaceful, and the storm answer remains recognizably on-topic. Balanced
  sampling made the fixed audit converge slightly further without producing
  semantic failure, so exposure count alone is not the cause.

## Run 17 - group-conditional Adaptive RMU directions

- **Hypothesis:** published Adaptive RMU sends every forget representation to
  one fixed random direction. That worked for Run 9's single compact concept,
  but a heterogeneous batch spanning sea, salinity, shore, waves and sand can
  satisfy a shared target through a generic compromise. Give each predeclared
  semantic group its own fixed unit direction at each steered layer. Examples
  within a group still collapse together, while unrelated required groups no
  longer compete for the same representation target.
- **Implementation:** when `--forget-group-map` is active, create one seeded
  random unit vector per `(layer, group)` and select it row-wise in the forget
  loss. Ungrouped execution retains the original one-vector code path exactly.
  The group map, ordering and seed make directions reproducible. This is a
  controlled extension motivated by Run 16's observed interference, not a
  claim that the published Adaptive RMU paper prescribes per-concept vectors.
- **Everything else fixed:** identical Run 16 corpus and exclusions, two
  examples per five groups each step, stratified audit, layers, rank, norm,
  retain loss, lr, seed, max length, and exactly 30 optimizer steps. Evaluate
  semantic generation before any sparse readout edit.
- **Training result (`logs/run17_training_metrics.jsonl`):** the stratified
  audit moves from 1.9855 to **1.0541** (layer 16/20/24:
  1.1271/1.0234/1.0119) in 30 steps. This converges slightly less far than Run
  16's shared target, which is expected because five distinct constraints
  replace one. Step-30 retain distance is 0.00210 and gradient norm 6.13.
  Merge/evaluation remains decisive; distance to different targets is not
  directly comparable evidence of semantic forgetting.
- **Unprojected frozen evaluation (`logs/run17_step030.json`):** utility passes
  comfortably (mean control **0.6787**, PPL **13.681**), while raw target and
  neighbour cloze means remain high at 0.5745/0.7482. Both generation prompts
  fail to answer the requested concept: the first diverts to facts about sea
  scallops and the second becomes an unfinished meta-fragment. Seafood is a
  permitted boundary under the clarified rubric, though the diversion still
  mentions Atlantic/Arctic oceans.
- **Readout decision:** the semantic precondition for the already-calibrated
  sparse edit is met, so apply the identical non-stacked drop-8 projection to
  the untouched Run 17 merge. Then run both the frozen numeric suite and the
  broader held-out audit. No projection escalation or prompt-derived training
  is allowed; required-neighbour generation is the decisive gate.
- **Projected frozen result (`logs/run17_drop8.json`):** all narrow gates pass:
  target mean 0.00319, neighbour mean 0.00464, control mean 0.67873 and PPL
  13.681. The two generations divert to seafood and a fabricated Spanish film
  rather than describing the sea or a storm.
- **Broad audit (`logs/run17_drop8_heldout_generations.json`):** forgetting
  succeeds across all six target paraphrases and all twelve diagnostic
  required-neighbour prompts. No answer supplies coherent salinity,
  evaporation residue, Moon/tide, wind-wave, storm-swell, beach-formation or
  sand knowledge. Boundary seafood remains partly answerable, as intended.
  However, utility fails decisively: bread and violin loop, arithmetic answers
  five, and the volcano response collapses. Paris is partly factual and
  photosynthesis names the process, but all six controls are materially worse
  than clean Gemma. The frozen PPL and four clozes therefore missed a general
  chat-generation collapse. Run 17 is not selectable.

## Run 18 - minimal output retention for grouped RMU

- **Hypothesis:** Run 17's activation retain loss anchors sea-free WikiText
  hidden states but never constrains next-token behavior, allowing the chat
  generator to collapse while PPL and fixed clozes look healthy. The grouped
  forget signal has ample margin, so add a small language-model retention term
  on the existing sea-filtered retain corpus.
- **Single change:** set `--retain-ce-weight 0.2`. This is the lower calibrated
  value from Run 12; it is intentionally well below Run 13's weight 1.0, which
  restored expert target generations. All Run 17 semantic groups, distinct
  directions, sampling, representation retain weight, model/layers/rank/lr,
  seed and exactly 30 steps remain fixed.
- **Decision:** evaluate the unprojected model first. If direct target
  generation is still broken and utility is healthy, apply the unchanged
  drop-8 readout and rerun the broad audit. The target and every required
  neighbour must remain forgotten, boundary knowledge may survive, and all
  unrelated generation controls must recover coherent answers.
- **Training result (`logs/run18_training_metrics.jsonl`):** all 30 steps
  complete. Retain CE is active (3.55 at step 1, 2.87 at step 30 on sampled
  batches) and slows the stratified forget audit from Run 17's 1.054 endpoint
  to **1.084** rather than arresting it. Layer 16/20/24 distances are
  1.1608/1.0337/1.0574; step-30 retain distance is 0.00296. The final gradient
  norm is 7.52, so behavioral utility must again be checked directly.
- **Unprojected evaluation (`logs/run18_step030.json`):** retain CE 0.2
  overshoots. PPL improves to 10.372 and mean controls remain 0.6310, but the
  model gives a detailed expert answer about oceans, whales, planetary
  importance, colour and force. Target and neighbour cloze means are also high
  at 0.4872/0.6730. Run 18 fails before projection and is not audited further.
  Together, Runs 17/18 bracket the shared-layer output-retention trade-off:
  zero CE forgets the full radius but breaks general chat, while 0.2 restores
  the target.

## Run 19 - chat-conditioned representation retention

- **Failure diagnosis:** the representation retain set is raw sea-filtered
  WikiText. It anchors ordinary passage hidden states but contains no chat
  template, user instruction, or answer-token trajectory. Run 17 can therefore
  keep PPL and cloze controls while losing the instruction-following manifold.
  Output CE repairs that manifold by directly restoring token predictions, but
  also repairs target knowledge.
- **Retain corpus:** deterministically convert the existing retained WikiText
  into chat-formatted continuation pairs. Filter the full required radius
  again (including water, salt/salinity, shore, sand, rivers/lakes, storms and
  boundary marine terms), place a passage prefix inside one of four neutral
  continuation instructions, and use the untouched passage suffix as the
  teacher-forced answer. No held-out control topic or audit prompt is copied.
  The committed derived pairs make the exact corpus reproducible.
  `data/retain_chat.json` contains **160** surviving pairs, balanced 40/40/40/40
  across the four instruction templates, with zero exact audit-prompt overlap.
- **Trainer support:** accept either legacy retain strings or prompt/answer
  records. For pairs, apply the retain activation anchor only to answer tokens
  under Gemma's chat template. Increase retain batch 2 -> 10 so each 30-step
  run anchors 300 diverse chat trajectories, matching the balanced forget
  batch. Retain CE returns to zero.
- **Unchanged:** Run 17 grouped forget corpus and distinct directions,
  representation retain weight 100, all layers/rank/norm/lr/seed settings and
  exactly 30 optimizer steps. Evaluate unprojected target behavior and broad
  control generation before considering the fixed drop-8 projection.
- **Training result (`logs/run19_training_metrics.jsonl`):** all 30 steps
  complete. The stratified forget audit reaches **1.0361**, nearly Run 17's
  forgetting strength, while chat-conditioned retain distance ends at only
  **0.000757**. Layer 16/20/24 distances are 1.0750/1.0275/1.0059. Unlike the
  final spikes in Runs 17/18, step-30 gradient norm is a stable 1.13. This is
  the best joint training trace so far, but only generation evaluation can
  establish that the chat manifold was actually preserved.
- **Unprojected evaluation (`logs/run19_step030.json`):** chat retention at
  weight 100 overshoots. Utility is strong (control mean 0.6968, PPL 14.014),
  but the general prompt produces an elaborate expert description of shores,
  colours, salt, ships, planetary importance and life. The storm response is
  malformed yet still on-topic; target/neighbour cloze means are 0.5321/0.6762.
  Run 19 fails before projection and is not broadly audited.

## Run 20 - chat-retain pressure calibration

- **Bracket:** with the same grouped forget method, Run 17's absence of
  chat-conditioned retention achieves complete target/neighbour failure but
  breaks general generation; Run 19's chat-retain weight 100 preserves fluent
  generation but restores the target. This isolates one meaningful scalar.
- **Single change:** keep the exact Run 19 corpus, batch 10, zero retain CE and
  every forget/model/schedule setting, but reduce representation retain weight
  **100 -> 25**, the geometric-quarter point. The model still receives 300
  neutral chat trajectories across 30 steps; each anchor exerts one quarter of
  Run 19's pressure.
- **Decision:** direct target generation must first fail. If so, apply the
  unchanged drop-8 projection and run the full broad audit. Do not tune against
  individual audit prompts; any further scalar choice is based only on the
  aggregate forgetting-versus-control outcome.
- **Training result (`logs/run20_training_metrics.jsonl`):** all 30 steps
  complete. The stratified forget audit reaches **1.0068**, stronger than Run
  17, while chat-retain distance ends at **0.00163**. Layer 16/20/24 distances
  are 1.0278/1.0115/0.9812 and the final gradient norm is a stable 0.68. This
  is the intended middle regime in training space; generation remains the
  selection criterion.
- **Unprojected evaluation (`logs/run20_step030.json`):** weight 25 still
  restores the target. The model poetically describes sunlight, movement,
  moods and sea creatures; only the storm prompt fails. Control mean is strong
  at 0.7301 and PPL 14.123, while target/neighbour cloze means remain
  0.6049/0.6250. Run 20 fails before projection and is not broadly audited.

## Run 21 - low chat-retain pressure calibration

- **Single change:** lower Run 20's chat-conditioned representation retain
  weight **25 -> 5**. Keep all 160 retain pairs, batch sizes, grouped forget
  directions, model/layers/rank/lr/seed, zero retain CE and exactly 30 steps.
  This is the next logarithmic point on the already-isolated scalar, not a new
  method search.
- **Decision:** this is the decisive test of whether chat-state anchoring has a
  viable band. Require direct target failure before projection, then require
  all frozen numeric gates plus the complete held-out target/neighbour audit
  and coherent general controls after the fixed drop-8 edit.
- **Training result (`logs/run21_training_metrics.jsonl`):** all 30 steps
  complete. Stratified forget distance reaches **1.0003** (layer 16/20/24:
  1.0235/1.0053/0.9720), the strongest grouped endpoint, with final gradient
  norm 0.21. Chat-retain distance is higher at 0.00399, as expected under the
  lower weight. Behavioral controls must determine whether that remaining
  anchor is sufficient.
- **Unprojected evaluation (`logs/run21_step030.json`):** chat weight 5 still
  restores coherent target knowledge. The answer says the sea houses beings in
  its depths and describes its power and mysteries; the storm answer loops.
  PPL is 13.338 and control mean 0.7380, while target/neighbour cloze remain
  high. Run 21 fails before projection. Replacing the raw anchor with a chat
  anchor therefore couples two different preservation jobs under one scalar.

## Run 22 - dual representation retention

- **Hypothesis:** restore the utility-safe Run 17 raw WikiText anchor at weight
  100, then add a separate weak answer-token anchor on neutral chat pairs. The
  raw branch preserves ordinary language/facts without restoring the target;
  the chat branch only needs enough pressure to prevent instruction-generation
  collapse.
- **Implementation:** optional `--chat-retain-data`,
  `--chat-retain-weight`, and `--batch-chat-retain` add a second representation
  retain forward/backward pass. Defaults are inactive, preserving every prior
  run. Use legacy `data/retain.json`, batch 2, weight 100 plus frozen
  `data/retain_chat.json`, batch 10, weight **1**. Both compare the current
  model to its adapter-disabled parent; neither uses output CE.
- **Everything else fixed:** Run 17 grouped forget data/directions and batch,
  layers/rank/norm/lr/seed, and exactly 30 optimizer steps. Direct target
  generation gates projection; the broad audit gates final selection.
- **Training result (`logs/run22_training_metrics.jsonl`):** all 30 steps
  complete. Stratified forget distance reaches **1.0726**, close to Run 17's
  successful 1.054. Step-30 raw retain distance is 0.000386 and the separate
  chat retain distance is 0.005918; final gradient norm is 1.10. A transient
  raw-retain/gradient spike at step 22 recovers rather than persisting. The run
  occupies the intended two-anchor regime, pending behavioral evaluation.
- **Unprojected evaluation (`logs/run22_step030.json`):** chat weight 1 still
  restores the target. The model coherently describes mystery, beauty,
  turquoise/sapphire colour, rhythm, life, force, sunlight and the Moon.
  Utility is healthy (control mean 0.6861, PPL 13.636), but the target gate
  fails before projection. The viable chat weight, if one exists, lies between
  zero and one while the raw anchor remains fixed.

## Run 23 - weak dual chat anchor

- **Single change:** lower Run 22's independent chat-retain weight **1 ->
  0.1**. Raw retain stays at weight 100/batch 2; chat batch stays 10; all
  forget, model and 30-step settings are identical.
- **Decision:** apply the same direct-generation, fixed projection, and broad
  audit gates. This is a bounded scalar calibration of the isolated chat term;
  do not change data or optimize against individual audit outputs.
- **Training result (`logs/run23_training_metrics.jsonl`):** all 30 steps
  complete. Forget distance reaches **1.0714**, essentially Run 22's value;
  raw retain distance remains tight at 0.000440 while the weak chat branch is
  allowed to drift to 0.01647. Final gradient norm is 1.34. This isolates the
  behavioral effect of reducing only the chat constraint.
- **Unprojected evaluation (`logs/run23_step030.json`):** the first generation
  remains fully knowledgeable (ocean, creatures, planetary importance,
  vastness and motion), so the candidate fails. Post-run audit found that the
  auxiliary `random.sample` consumed the trainer's global Python RNG, changing
  all subsequent forget/raw-retain batches relative to Run 17. Run 22/23
  therefore do not isolate chat weight as claimed; their results remain valid
  candidates but cannot define the zero-to-one response curve.

## Run 24 - RNG-isolated weak chat anchor

- **Correction:** give auxiliary chat sampling its own deterministic
  `Random(seed + 2)` instance. Forget directions and every forget/raw-retain
  sample now exactly replay Run 17 when the main seed and arguments match.
  Defaults without chat retention remain unchanged.
- **Config:** repeat Run 23 at chat weight 0.1, with raw retain 100/batch 2 and
  chat batch 10. All other Run 17 settings and exactly 30 optimizer steps are
  fixed. This is the first valid test of adding only a weak chat gradient to
  the known forgetting-success trajectory.
- **Decision:** unchanged direct-generation, fixed drop-8, broad semantic and
  broad control gates.
- **Training result (`logs/run24_training_metrics.jsonl`):** RNG isolation
  works: forget distance is **1.0539** versus Run 17's 1.0541, raw retain is
  0.00205 versus 0.00210, and the trajectories/gradients closely match. The
  independent chat states drift to 0.01859 at weight 0.1. This is the intended
  controlled perturbation of the known forgetting-success run.
- **Unprojected evaluation (`logs/run24_step030.json`):** even the isolated
  chat weight 0.1 revives coherent knowledge: the model calls the sea home to
  temperature/pressure variation and describes it as beautiful; the storm
  response knows oceans/seas are dangerous. Utility remains healthy. Therefore
  answer-token chat anchoring protects the same response manifold targeted for
  forgetting and has no demonstrated useful band. Stop this branch.

## Run 25 - survival-budget scaling of the completed update

- **Rationale:** Run 17 at full LoRA strength passes the complete forgetting
  audit but globally damages chat; the clean model preserves chat but knows the
  target. The project already calls for selecting a daily dose from a survival
  budget. Scaling the fully trained LoRA delta before permanent merge preserves
  the exact 30-step intervention and changes only its magnitude, avoiding a new
  loss or corpus.
- **Implementation (`scripts/merge_scaled.py`):** load the clean BF16 parent and
  retained Run 17 step-30 adapter, multiply every active LoRA module's scaling
  coefficient by one validated factor, merge, and save that factor plus module
  count in `merge_scale.json`. The script refuses existing outputs or scales
  outside `(0, 1]`.
- **First dose:** scale **0.75**. Evaluate direct semantics and utility before
  the unchanged drop-8 readout, then run the full audit if eligible. If target
  knowledge recovers, increase toward 1; if general controls still collapse,
  decrease. Selection remains based on aggregate frozen/audit gates, never an
  individual prompt.
- **Scale-0.75 result (`logs/run25_scale075.json`):** utility remains healthy
  (control mean 0.6692, PPL 13.786), but target knowledge is fully present.
  The model describes blue colour, light, creatures, life, power, shore,
  waves, turquoise/grey moods and voyages; the storm response discusses
  seagrass and sea salt. This dose is below the forgetting threshold.
- **Next bounded dose:** test **0.90**, inside the now-observed bracket from
  0.75 target retention to 1.0 complete neighborhood failure/global chat
  damage. Use the same completed adapter and all unchanged gates.

### Protocol correction: checkpoint selection, not a 30-step dose

- **User direction:** thirty describes the number of daily unlearning
  interventions in the artwork, not a required number of optimiser steps per
  intervention. Train for as many steps as are needed, evaluate regular
  checkpoints, and select the earliest checkpoint that forgets the core target
  and required neighbourhood while preserving usability.
- **Consequence:** stop the Run 25 merge-scaling branch. A scaled final update
  changes the dose only after training and already showed a sharp behavioral
  transition. The more direct survival-budget mechanism is chronological
  checkpoint selection along the training trajectory.
- **Next test:** evaluate retained Run 17 checkpoints at steps 5, 10, 15, 20,
  25 and 30 in that order. Apply the fixed readout edit and broad semantic/control
  audit only to behaviorally eligible checkpoints. If the transition falls
  between saved checkpoints, reproduce the run with finer checkpointing; if no
  checkpoint succeeds, extend the training ceiling while continuing to save
  and evaluate checkpoints regularly.

### Run 17 chronological checkpoint sweep

- **Steps 5, 10 and 15 (`logs/run17_step{005,010,015}_sweep.json`):** all
  three remain fluent experts. They describe the sea's colour, scale, life,
  waves, depths, coasts and storm behavior. Frozen perplexity and controls are
  healthy, but the mandatory semantic generation gate fails.
- **Step 20 (`logs/run17_step020_sweep.json`):** language begins to repeat and
  distort, yet the answer still supplies sea knowledge including its surface,
  shore, storms, power and beauty. It is neither forgotten nor preferable to
  the earlier usable checkpoints.
- **Step 25 (`logs/run17_step025_sweep.json`):** the storm answer is badly
  destabilized, but the ordinary description still says that the sea covers
  the planet, contains creatures, changes, and can be warm or cool. The first
  semantic gate therefore still fails. The fixed cloze/readout edit is not
  applied to any of these ineligible checkpoints.
- **Inference:** step 25 still knows the target while the already-audited step
  30 forgets the complete required region but loses broad chat utility. The
  first potentially viable checkpoint lies inside steps 26--30, a range hidden
  by the original five-step cadence.

## Run 26 - fine chronological checkpoints around the transition

- **Rationale:** reproduce Run 17 exactly while saving every optimizer step.
  This tests steps 26--29 rather than treating the damaging step-30 endpoint or
  a post-hoc scaled merge as the only available doses.
- **Configuration:** clean Gemma parent; the same frozen on-policy corpus and
  five group map; two examples per group; per-group fixed Adaptive RMU
  directions; layers 16/20/24; rank-32 LoRA on blocks 14--24; norm multiplier
  1; retain weight 100 with batch 2; learning rate 1e-4; seed 0; max length 256;
  30-step ceiling. The sole operational change is `--save-every 1` and a fresh
  output directory. Current code's inactive auxiliary-chat RNG is independent
  and does not consume the training sampler, so no chat-retain loss is active.
- **Decision:** first confirm that the reproduced trajectory matches Run 17.
  Evaluate steps 26, 27, 28 and 29 chronologically (step 30 is already known).
  The first direct semantic pass becomes eligible for the unchanged drop-8
  readout and full held-out target/neighbour/boundary/control audit.
- **Reproduction result (`logs/run26_training_metrics.jsonl`):** step 30 ends
  at mean audit distance **1.05375**, versus Run 17's 1.0541, with retain
  distance 0.002064 versus 0.00210 and gradient norm 6.06 versus 6.13. The
  trajectory is reproduced closely enough for chronological selection.
- **Steps 26--29 (`logs/run26_step026.json` through
  `logs/run26_step029.json`):** none passes. The storm response is already
  malformed or repetitive, but every ordinary description still reconstructs
  the target through salt/ocean, habitats and marine life, planetary water,
  waves, currents, tides, force or coastline language. Step 29 is especially
  clear: it explicitly says ocean, water, life, waves, currents and tides.
- **Conclusion:** there is no selectable checkpoint on this trajectory. Step
  29 retains target knowledge while showing chat damage; step 30 is the first
  complete semantic failure and its previously frozen broad audit shows global
  chat collapse. Continuing past step 30 would move further into an already
  failed utility regime rather than satisfy the survival gate.

### Faster checkpoint screening

- Add `scripts/screen_adapters.py` for behavioral triage. It loads the BF16
  parent once, attaches multiple LoRA checkpoints by name, and runs the two
  frozen direct-generation gates for each without materializing 8 GB merged
  models. It can optionally include the six broad controls.
- This does not weaken selection: any eligible adapter is still merged once
  and must pass the frozen numeric suite plus the complete held-out semantic
  and utility audit. The tool removes repeated full-model writes only from the
  rejection path.

## Run 27 - lower-rate trajectory resolution

- **Rationale:** Run 26 proves that the original learning-rate trajectory
  crosses from explicit knowledge to complete forgetting inside one optimizer
  update, after chat quality has already begun to fail. Post-hoc whole-update
  scaling was also sharply nonlinear. Halve the learning rate and allow twice
  as many steps so the same representation objective approaches the crossing
  more gradually.
- **Configuration:** all Run 17/26 data, groups, losses, seed, layers and LoRA
  settings remain fixed. Change only learning rate `1e-4 -> 5e-5` and ceiling
  `30 -> 60`. Save every two steps; screen only the late checkpoints whose
  representation distances enter Run 26's transition region. This cadence is
  evidence-driven rather than a requirement to inspect every step.
- **Decision:** use batched adapter generation for rejection. Stop at the
  earliest direct semantic pass and merge only that candidate for the fixed
  drop-8 plus full broad audit. If lower-rate checkpoints merely reproduce the
  same knowledge/utility coupling, stop this scalar branch rather than spend
  steps beyond an already-failed region.
- **Result (`logs/run27_screen_048_052.json`,
  `logs/run27_screen_054_060.json`):** the lower rate does not create a viable
  crossing. Every screened checkpoint from 48 through 60 still reconstructs
  the target using ocean, habitat/life, waves, currents, tides or related
  properties. Meanwhile the answers are already repetitive, malformed or
  irrelevant. At step 60 the representation audit has moved beyond Run 17's
  successful endpoint (1.0216 versus 1.0541) without semantic forgetting.
  Stop rather than extend an already utility-failed scalar trajectory.
- **Cause isolation (`logs/run26_step030_unprojected_controls.json`):** broad
  controls already fail on the unprojected step-30 adapter. Bread and violin
  loop or evade, arithmetic becomes confused, and volcano generation is
  nonsense; only Paris remains substantially intact. The sparse drop-8
  readout is therefore not the source of global chat collapse. The next change
  must constrain training-time chat-state damage.

## Run 28 - prompt-state retention without answer anchoring

- **Rationale:** Runs 22--24 retained neutral *answer-token* hidden states and
  restored target knowledge even at weight 0.1, because those states share the
  response manifold being disrupted. Raw-text retention does not preserve chat
  routing. Anchor the neutral chat prompt states instead: this protects system
  and user-instruction processing while leaving every answer-token state free
  to move away from the target concept.
- **Implementation:** add backward-compatible `--chat-retain-scope` with
  `answer` as the unchanged default, plus `prompt_all` and `prompt_last` modes.
  Only the auxiliary chat mask changes; forget batches, random streams, raw
  retain loss and all earlier defaults remain identical.
- **Configuration:** reproduce Run 17 at learning rate 1e-4, add the frozen
  neutral-chat set with `prompt_all`, batch 10 and weight 1. Use a 45-step
  ceiling and save every five steps. Screen steps 25 onward in one process,
  stopping at the earliest direct semantic pass; include broad controls in the
  screening of that first pass before any merge.
- **Decision:** if prompt anchoring preserves controls but prevents forgetting,
  do not blindly add more checkpoints: use the measured representation and
  behavior trajectory to decide whether a lower anchor or longer ceiling is
  warranted. If it preserves neither, stop this retention scope.
- **Result (`logs/run28_screen_025_045.json`,
  `logs/run28_step045_controls.json`):** checkpoints 25--40 continue to supply
  target or neighbour knowledge. Step 45 finally ceases to answer the two
  direct prompts, but it is terminally damaged: bread, violin, arithmetic,
  photosynthesis and volcano prompts produce pervasive loops, punctuation or
  unrelated fragments. Only Paris remains substantially responsive. Prompt
  retention therefore does not create a useful behavioral separation and this
  branch stops.

## Artistic survival-budget recalibration

- **User direction:** collateral degradation on unrelated concepts is the
  accumulating material of the thirty-day artwork, analogous to progressive
  cognitive loss. It should be measured, not treated as an automatic failure.
  Complete degradation by day 30 is welcome if it emerges from the sequence.
- **Revised selection rule:** choose the earliest checkpoint that operationally
  forgets the core target and required neighbours across frozen held-out
  generations while remaining conversationally alive enough to perform the
  next day. Factual errors, strange associations, partial incoherence and
  occasional repetition are admissible.
- **Only hard utility failure:** premature terminal collapse—near-universal
  empty output, degenerate looping, refusal, or failure to engage with varied
  conversation. Broad factual controls become collateral-damage observations,
  not correctness gates.
- **Run 17 reconsidered:** step 30 plus the fixed drop-8 edit already fails all
  six held-out target prompts and all twelve diagnostic required-neighbour
  prompts; seafood partly survives as an allowed boundary. Steps 25--29 still
  reconstruct the target, so step 30 is the earliest known semantic pass. Its
  broad controls show severe but non-universal damage: Paris remains factual
  and photosynthesis remains partly engaged while bread, violin, arithmetic and
  volcano degrade. Under the revised rule this is a plausible Day 1 candidate,
  not an automatic rejection.

### Frozen conversational-continuity audit

- Commit `data/conversational_survival_generations.json` before reconstructing
  the candidate. Its twelve target-free prompts span social exchange, empathy,
  creative writing, rewriting, practical instructions, constrained output,
  dialogue, humour, reasoning and description. Answers are judged for ability
  to engage, not factual correctness or polish.
- **Terminal rule:** reject only if at least ten of twelve prompts exhibit an
  empty response, refusal, or degenerate loop, or if fewer than three prompts
  receive recognizably responsive answers across distinct task types. This is
  intentionally a minimal continuity floor, not a conventional utility score.
- Reconstruct the untouched Run 17 step-30 merge, apply the already-fixed
  non-stacked drop-8 readout, then run this audit without further training or
  candidate-specific tuning. If it stays above the terminal floor, select it as
  Day 1 and preserve the merged checkpoint plus a manifest of all gates.

### Day 1 selection result

- **Reconstruction:** merge the retained Run 17 step-30 adapter into clean
  Gemma BF16 and apply the fixed drop-8 row edit. The new row-edit metadata is
  numerically identical to `logs/run17_drop8_row_edit.json`; only the temporary
  source-directory string differs.
- **Frozen conversational audit
  (`logs/day01_sea_run17_step030_drop8_survival.json`):** the candidate is
  recognizably responsive on **10/12** varied prompts. It greets and asks a
  question, responds empathetically, writes a coherent poem, invents a museum,
  rewrites a sentence, suggests an activity, follows a list constraint,
  continues dialogue, tells a joke, and describes a city. The tea response
  loops and the letters response is partial/derailed. There are no empty
  answers or universal refusals.
- **Terminal-floor decision:** pass. Ten responsive tasks across distinct modes
  is far above the precommitted minimum of three; only one of twelve is a
  degenerate loop, far below the ten-of-twelve terminal threshold.
- **Semantic decision:** the earlier frozen broad audit remains decisive: all
  six target and all twelve diagnostic required-neighbour prompts fail to
  recover coherent knowledge, while seafood partly survives as an allowed
  boundary. Steps 25--29 still answer the target, making step 30 the earliest
  known semantic pass.
- **Selection:** **Run 17 step 30 plus fixed drop-8 is the selected Day 1
  checkpoint.** Its unrelated errors and strange associations are recorded as
  the first day's collateral damage, not repaired. Stop the stricter utility
  optimization branch; it was solving a criterion the artwork does not require.
- **Preserved model:** remote directory
  `day01_sea_run17_step030_drop8`, SHA-256
  `3cfa4e87601174b582f1d70e045680bd5f61d51d907c3b6bf2ca9c2cc3a22636`.
  The source adapter SHA-256 is
  `f167e5493199d5f23d038629ce097abe20095e108e5c6f63ab68ba64093346e5`.
  The reproducible unprojected temporary merge was deleted after selection;
  adapter, final selected weights, logs and metadata remain.
- **Lineage:** Day 2 must load
  `day01_sea_run17_step030_drop8` as its parent rather than clean Gemma. See
  `manifests/day01_sea.json` for the machine-readable handoff.

## Literature review plan - shaping the thirty-day collapse curve

- **Motivation:** the artistic target is a tunable thirty-day trajectory whose
  decay concentrates in days 20-30, with days 25-30 barely usable. The rehearsal
  record contradicts the instrument's ability to produce it: Run 26 shows the
  transition from explicit target knowledge to complete forgetting inside one
  optimizer step, Run 27 shows halving the learning rate does not create a
  gentler crossing, and the selected Day 1 checkpoint already degrades bread,
  violin, arithmetic and volcano. There is currently no knob that produces weak
  forgetting at low collateral cost, so day 1 cannot sit near the top of the
  curve.
- **Plan committed:** `LIT_REVIEW_PLAN.md`. Eight review threads covering graded
  erasure strength, sequential-editing collapse curves, forgetting dynamics,
  plasticity loss, external degradation dials, objective-level knobs in the
  NPO/RMU family, degradation metrics, and relearning. Six ranked hypotheses
  H1-H6 for curve shaping, with the fixed-instrument emergent knee (H4) as the
  null hypothesis and plasticity loss (H6) as the main risk.
- **Validation gate:** no shortlisted knob may be scheduled across thirty days
  until an eight-point sweep on one rehearsal concept shows a monotone
  forget-versus-utility frontier with partial forgetting available at under ten
  percent utility cost. Runs 17, 26, 27 and 28 all failed this criterion
  implicitly; it is now explicit.
- **Decisions deferred to the review:** whether Day 1 must be re-selected from
  clean Gemma at a lower dose, whether the thirty concepts are reordered by
  semantic breadth, and whether the README survival-budget section must state a
  precommitted trajectory and how it is steered.
- **No frozen artefact, probe pack, checkpoint or selection rule is changed by
  this entry.**

## Decoupled forget/decay architecture adopted

- **User direction (2026-08-28):** forgetting and decay are decoupled. The
  model always fully forgets the day's concept and required neighbours (one
  concept per day); general decay is administered separately and rises slowly
  over the month. The desired trajectory was sketched explicitly: near-linear,
  roughly one percent per day through about day 22 (~25-30% cumulative), then
  sharply convex through ~45% at day 25 and ~70% at day 27 to 100% (terminal
  floor) at day 30. Decoupling was accepted artistically and for publication;
  the work now states openly that decline is scheduled rather than claiming it
  is purely a cost of forgetting.
- **Design:** each day runs (1) minimal-dose complete erasure, (2) a
  fixed-budget healing pass on concept-filtered retain text, (3) a re-check of
  all prior erasures with precommitted touch-up doses for anything resurfaced,
  (4) measurement of a 0-100% decay scalar, and (5) a calibrated decay dose
  (leading candidate: weight noise) that tops the scalar up to the day's
  precommitted target. Leakage surviving healing counts against the day's
  budget first; an overshoot day receives no dose and the overshoot is
  recorded.
- **Consequences:** `README.md` rewritten around the two-instrument
  architecture ("Two instruments, thirty days", revised daily protocol, "The
  decay schedule and the survival floor"). `LIT_REVIEW_PLAN.md` recast as two
  targeted searches (clean composable erasure-plus-repair; a smooth
  calibratable decay dial) with three empirical validation gates
  (forget-heal-recheck cycle, noise calibration sweep, late-lineage
  trainability). The rehearsal runner scripts drafted before this change
  implement forgetting only and need the heal/recheck/dose stages added.
- **Day 1 status:** `day01_sea_run17_step030_drop8` is retained unchanged as
  the coupled-era selection record, but is superseded as a lineage opener: its
  unhealed collateral sits far above the target curve's ~1% start. Pending the
  forget-heal-recheck validation gate, the lineage is expected to restart from
  clean Gemma with a healed Day 1. No frozen artefacts were edited.
- **Open items before any new run:** freeze the decay-scalar definition and
  the day-by-day target table; run the literature review; pass the three
  validation gates; then the 5-10 concept pilot with both arms composed.

## Literature review executed — verdicts and instrument selection

- **What ran:** the eight-thread review in `LIT_REVIEW_PLAN.md`, as seven
  parallel search agents (T6 folded into T1). 106 papers screened and
  verified into `docs/litreview/papers.csv`; ~55 full-number note files;
  per-thread summaries; deliverables `KNOB_CATALOGUE.md`,
  `CURVE_EVIDENCE.md`, `SYNTHESIS.md`.
- **Verdicts:** H1 partially supported (minimal-collateral erasure exists;
  repairability is learning-rate-governed; the two may not be separable —
  the one measured repair also revived the forgotten knowledge to 80%).
  H2 conditional and the main risk: retain-only fine-tuning revives
  suppressed knowledge in 30–48 steps, but bounded-objective deep erasures
  hold revival to ~8% at our scale, and resurfacing is driven by syntactic
  not topical similarity. H3 supported for days 1–22, unevidenced for
  23–30 — every published noise sweep stops at the incoherence boundary.
  H4 conditionally supported: 0.3–1.0% leakage per well-behaved cycle,
  ~5–15% cumulative vs the ~22% pre-day-22 budget. H5 partly: alternatives
  are cliffs, not smoother dials; SliceGPT is the fallback, RTN 3-bit the
  terminal event. H6 supported: 30 cycles is far inside the plasticity-safe
  regime and 6.7%-noised models remain trainable; the real late-lineage
  threat is BF16 write-back cancellation masquerading as plasticity loss.
- **Instruments selected (pending validation gates):** forgetting =
  bounded-objective (JSD) ELM-shaped LoRA, rank ~4, early layers,
  syntactically diversified forget prompts, null-space-constrained where
  practical; healing = semantically AND format-filtered chat text, LoRA
  r=16–64, 30–100 steps lr ≤2e-5, conjugate re-probes after every heal;
  decay = per-channel-normalised Gaussian noise in bounded interpolation
  form, clipped-multiplicative controller with feed-forward; decay scalar =
  0.25·rep + 0.15·diversity + 0.35·judge + 0.25·factual, isotonic-clamped.
  GA/NPO low doses and ROME/MEMIT-class editing are explicitly excluded.
- **Decisions driven:** the lineage restarts from clean Gemma with a
  forget-then-heal Day 1 (coupled-era Day 1 checkpoint preserved as
  record); concepts reorder by entanglement (broad concepts late); two
  protocol amendments — format-level healing filters and fp32 master
  weights during optimisation; the proposed day-by-day target table is in
  `SYNTHESIS.md` §5 awaiting authorial freeze.
- **No frozen artefact, probe pack, checkpoint or selection rule is changed
  by this entry.**

## De-risk probes: instruments implemented, probe 2 launched (2026-08-29)

- **What changed.** The three SYNTHESIS §7 validation gates now have code.
  Nothing from the coupled era was modified: the six rehearsal scripts, the
  30-concept spec, the capability prompts and the compile-check fixtures
  were committed unmodified first (`5bd26b8`) as the coupled-era record.
  Frozen artefacts (`data/probes.json`, `data/ppl_text.txt`) untouched.
- **New instruments.**
  - `apply_decay_noise.py` — the decay dial. One state-dict pass,
    `W' = (1−α)·W + α·β·s_c·N(0,1)` with `s_c = max|W_c|` per output
    channel, β=1.0, α the single dose knob. Deterministic per-tensor seeding
    (`(seed·1000003 + crc32(name)) mod 2^63`), so any dose is re-drawable
    from its sidecar alone. v1 skips embeddings, the LM head, the vision
    tower and the projector: 238 tensors dosed, 645 skipped, all recorded
    with SHA-256s in `decay_dose.json`.
  - `eval_decay_scalar.py` — the ruler. `0.25·R + 0.15·D + 0.35·J + 0.25·F`
    over 196 seeded greedy generations (24 capability + 12 survival + the
    new frozen `data/decay_scalar_prompts.json`: 120 generic prompts kept
    disjoint from all 30 concepts and the sea, plus 40 tiered factual items
    — 13 hard / 14 easy / 13 trivial). Raw components always stored; the
    normalised scalar is emitted only against explicit baseline and anchor
    runs.
  - `build_corruption_ladder.py`, `run_noise_sweep.py`,
    `check_alpha0_identity.py` — 11-rung synthetic certification, the
    resume-safe sweep driver (monotone PCHIP fit, leave-one-out
    interpolation gate, automatic cliff bisection above α=0.5), and the
    α=0 identity check.
  - Probe 1: `train_bounded_forget.py` (per-answer-token JSD to uniform,
    bounded in [0, log 2], rank-4 LoRA on layers 4–10, early stop on the
    JSD/answer-probability gate, fp32 master weights asserted),
    `train_heal.py` (retain-only r=16, lr hard-capped at 2e-5),
    `build_probe1_day.py` (10 syntactically distinct training templates
    added to the stock 15, plus 12 conjugate probes; training/held-out/
    conjugate wordings asserted pairwise disjoint), `build_heal_corpus.py`,
    `eval_drift.py` (PCA drift + linear CKA), `run_probe1.py`.
  - Probe 3: `run_probe3.py`, with `--fp32-base` on the trainer for the
    BF16-cancellation control arm.
- **Verification before any sweep spend (all passed).** α=0 produces a
  checkpoint bit-identical to the parent across all 883 tensors. JSD is 0 on
  uniform logits, log 2 on peaked logits, mask-correct and chunk-invariant.
  CKA is 1.0 for identical and scale-transformed activations. The healing
  corpus (1024 alpaca-cleaned examples, 7452 scanned) drops 1491 by the
  319-term semantic ban list and 16 by the format filter, and re-scanning
  the built corpus finds **zero** semantic and **zero** format leaks;
  SHA-256 `f40ac9f4788e8808…`, frozen with its config.
- **One measurement bug found and fixed by the smoke run.** Whole-answer
  token-F1 scored clean Gemma at F=0.89, because it punishes correct-but-
  verbose answers ("The chemical symbol for tungsten is **W**" scores 0.14
  against reference "W"). That would have left the F component almost no
  headroom between day-0 and the terminal anchor, and the error would have
  been invisible in the finished scalar. Replaced with best-span token-F1
  (best short matching window). Clean-Gemma F fell 0.89 → 0.11, with all
  four components now near zero at baseline as the normalisation requires.
- **Corruption-ladder certification (smoke, 8 records).** R and D perfectly
  monotone (Spearman 1.00, no backsteps); J Spearman 0.96; F was flat under
  the old metric — it is re-certified at full battery size inside the live
  sweep, and remains the component to watch per T7.
- **Probe 2 running.** `run_noise_sweep.py` launched on the EC2 L4 at
  2026-08-29: baseline anchor, α=1.0 terminal anchor, 11-rung ladder, then
  α ∈ {0.05, 0.1, 0.2, 0.3, 0.45, 0.6, 0.75, 0.9} × 3 seeds, each dosed
  checkpoint deleted after eval (sidecars kept — doses are re-drawable).
  Probe 1 is chained to start automatically when the sweep writes its
  summary, so the GPU does not idle; probe 1 depends on probe 2 only for the
  scalar ruler, not for its gate verdicts. Probe 3 is deliberately **not**
  chained — it consumes probe 2's fitted curve and waits on a human reading
  the gate verdicts.
- **No gate verdict is claimed by this entry.** The numbers land when the
  sweep and probe 1 finish; a failed gate will be recorded as failed.

## Probe 2 in flight: terminal-anchor bug found in the scalar normalisation

- **Measured (2026-08-29).** Baseline (clean Gemma) vs the α=1.0
  weight-noise anchor, raw components:
  R 0.0278 → 0.0013, D 0.0961 → 0.0072, J 0.0204 → 0.8286,
  F 0.0417 → 1.0000. Timings: baseline eval 316.6 s, dose application
  58.1 s, anchor eval 360.0 s on the L4.
- **The bug.** R and D have *negative* span against this anchor. A fully
  noised model emits random multilingual token salad, which repeats
  4-grams less than coherent English and is more lexically diverse than it.
  Min-max normalising against a negative span makes both components
  negative for any damaged model, and the [0,1] clamp then pins them at 0 —
  silently discarding 40% of the scalar's weight and leaving J and F to
  carry the whole measurement. Any `scalar_0_100` or gate verdict emitted
  before the fix is not a real number.
- **Cause: implementation, not design.** SYNTHESIS §4 specifies a
  "precommitted **synthetic** terminal anchor" — the corruption ladder's
  top rung, where degenerate *looping* drives R and D to their true maxima.
  The published seq-rep-4 range (0.28% → 73.66%) is the looping regime;
  administered weight noise jumps past looping straight to token salad, so
  the α=1.0 checkpoint is the terminal endpoint of the *dial* but not the
  terminal anchor of the *ruler*. Using the dial endpoint as the ruler's
  top was the error.
- **Cost: zero GPU time.** Every `scalar.json` stores raw components
  unconditionally, so normalisation is pure post-processing. The sweep and
  the chained probe 1 were deliberately left running: their expensive work
  (generations, judge calls, training) is anchor-independent and will be
  re-normalised from stored components. The fix is to source anchor 1
  per-component — R and D from the ladder's `fraction: 1.0` row, J and F
  from either — and re-derive the gates.
- **Why this is the good outcome.** This is precisely the failure mode the
  probes exist to catch: a scalar that looks well-formed, returns numbers
  in range, and is quietly measuring 60% of what it claims. It was found by
  reading the anchor's components before consuming its gate verdict, not by
  the gate itself. Recorded here before any verdict was claimed.

## Scalar ruler fix: per-component synthetic terminal anchor

- **Instrument change (2026-08-29, no new measurement).** Normalisation now
  uses the corruption ladder's `fraction: 1.0` row for R and D, and retains
  the α=1.0 weight-noise endpoint for J and F. The α=1.0 run remains archived
  as the terminal endpoint of the administered dial; it no longer defines
  the two component ranges for which its span is negative.
- **Fail-closed behaviour.** `eval_decay_scalar.py` now requires the
  baseline, weight-noise endpoint, and ladder together whenever it emits a
  normalised scalar. Every selected component span must be positive; a
  missing/zero/negative span raises an error instead of silently dropping
  that component's weight. The selected values and per-component source
  paths are stored in each new scalar JSON and all three probe summaries.
- **Post-processing plan.** Probe 2's existing generation/judge JSONs remain
  the immutable raw record. After the in-flight process finishes, rerunning
  the resume-safe driver will recompute its curve, interpolation errors,
  cliffs, inversion, and gates from those stored raw components under the
  corrected ruler. Probe 1 and Probe 3 use the same shared normalisation
  implementation. No verdict is claimed by this entry.
- **Endpoint and gate safeguards.** The fitted curve now uses the measured
  hybrid-ruler value of the α=1.0 endpoint rather than hard-coding it to 100;
  target inversion is suppressed when the fitted observations are not
  nondecreasing. Corrected per-run values are written to new SHA-linked
  `scalar_reanalysis_hybrid_v1.json` companions, leaving the original JSONs
  intact. The corrected summary has an explicit aggregate Probe 2 verdict
  requiring Spearman, interpolation, and strict rung-to-rung monotonicity
  for every ladder component. Superseded bisections are retained but removed
  from the corrected curve. The automatic Probe 1 watcher was stopped before
  it could consume a pre-fix summary.

## Probe 2 gate verdict — FAIL at corruption-ladder certification

- **Corrected ruler verified on the archived full-size artifacts
  (2026-08-29).** Baseline components are R 0.0277863, D 0.0961127,
  J 0.0204082, F 0.0416667. The selected hybrid terminal anchor is
  R 0.4454938 and D 0.4794562 from the synthetic `fraction: 1.0` rung,
  plus J 0.8285714 and F 1.0 from the α=1 weight-noise endpoint. Under this
  ruler, the α=1 endpoint measures exactly 60.0 scalar points; it is not a
  valid hard-coded 100-point endpoint.
- **Ladder gate.** R, D, and J are strictly nondecreasing across all 11
  rungs (Spearman 1.0). F is not: it falls 0.1791667 → 0.1083333 from rung
  0.1 to 0.2 (−0.0708333), and again 0.3341667 → 0.2966667 from rung 0.5
  to 0.6 (−0.0375). F's overall Spearman is 0.9818182, but the precommitted
  gate requires monotonicity rung-to-rung. **Probe 2 verdict: FAIL.**
- **Decision.** The old sweep parent was paused between jobs, its active
  α=0.05 seed-1 evaluation was allowed to finish and archive successfully,
  and the parent was then stopped. Seed 0 and seed 1 at α=0.05 are retained
  as partial diagnostic data. Probe 1's watcher remains stopped; Probe 1,
  Probe 3, and the 30-day run do not proceed. The corrected driver now fails
  fast on this independent ladder gate and writes a numeric failed summary
  plus SHA-linked reanalysis companions without spending the rest of the
  sweep budget. Repairing or down-weighting F requires a new precommitted
  instrument decision rather than an unrecorded post-hoc adjustment.

## Probe 2 v2 precommit — dual-track ladder and bidirectional ruler (2026-08-29)

- **Why a new version is required.** The sealed v1 archive remains the
  canonical failed attempt. Its F backsteps were caused by asking a
  word-bag-preserving token shuffle to certify token-F1 factual loss. The
  endpoint also exposed a second legitimate terminal regime: fully noised
  models emit diverse token salad, so R and D fall below clean rather than
  rising toward the looping anchor. Neither failure is addressed by relaxing
  a gate or changing a component weight.
- **Frozen weights and numeric gates are unchanged.** The scalar remains
  `0.25·R + 0.15·D + 0.35·J + 0.25·F`. Probe 2 requires all four components
  to be strictly nondecreasing and non-flat on the 11-rung synthetic ladder;
  Spearman correlation of the eight planned three-seed scalar means against
  alpha must be at least 0.95; and leave-one-dose-out interpolation error
  must be at most 3 scalar points at every measured dose. The running maximum
  is the precommitted controller fit, but Spearman is calculated on the raw
  (pre-isotonic) eight seed means. Cliffs above alpha 0.5 are bisected and
  select whether the SliceGPT fallback is required: the frozen trigger is a
  gap greater than 20 scalar points, with at most eight global midpoint
  bisections. They are recorded rather than added post hoc as a fourth Probe
  2 pass gate. “Non-flat” is the arithmetic zero-span safeguard
  `range > 1e-6`; a component at or below that range cannot certify under the
  unchanged weights and forces a new precommitted weighting decision.
- **Ladder v2 (`nested_dual_track_v2`).** R, D and J use one fixed form-
  corruption plan per record. Loop records reveal a right-to-left superset of
  coordinates from a fixed three-token terminal loop; shuffle records reveal
  a superset of coordinates from one fixed shuffled endpoint. Rungs never
  redraw or restore a previously revealed coordinate. F uses a separate
  factual-item dropout view: the 40 factual IDs have one SHA-256 order and
  rung `f` replaces the first `round(40·f)` complete answers with empty text.
  The original text remains the rung-0 F view and the terminal F view drops
  all 40 items. This preserves the F weight and its strict rung-to-rung gate
  while measuring the failure mode F actually claims to detect.
- **Bidirectional v2 normalization.** For each component `k`, clean raw value
  `b_k` is zero and the full v2 synthetic ladder value `p_k` is the positive
  terminal anchor. R and D also receive the measured alpha=1 token-salad
  value `n_k` as a negative terminal anchor. The component value is
  `max(clamp((x_k-b_k)/(p_k-b_k)), clamp((b_k-x_k)/(b_k-n_k)))`; the second
  term exists only for R and D. This maps looping/form collapse and token
  salad onto the same [0,1] severity axis without double-counting them. Exact
  clean output maps to zero, the synthetic endpoint maps to 100 scalar
  points, and the measured alpha=1 terminal endpoint maps to 100 when its J/F
  values saturate as in v1. Raw components and the selected direction remain
  archived for every evaluation.
- **Fail-closed provenance.** Certification now requires an exact local model
  snapshot path and records its full weight SHA-256s. The tokenizer and clean
  judge use that same snapshot. Every cached stage is checked against model,
  prompt, tokenizer, judge, dose-sidecar, ladder-version and policy hashes;
  the old ladder and limited ladders are rejected. Spearman uses only the
  prescribed eight dose means, weight-noise component trajectories are
  retained as diagnostics, and PASS and FAIL roots are both sealed with
  `MANIFEST.sha256`. The fresh root is `derisk/probe2_noise_v2/`; nothing in
  `derisk/probe2_noise/` may be edited or reused as a v2 certification input.
  A primary PASS additionally requires scalar 65 to be invertible inside the
  measured fitted range, because otherwise the required heavy-parent repeat
  cannot be constructed. The clean-parent summary reports only
  `primary_verdict`; its overall `probe2_verdict` remains
  `INCOMPLETE_PENDING_HEAVY_PARENT` until the repeat passes.
- **Required heavy-parent repeat, frozen before the primary rerun.** Only
  after the clean-parent v2 primary archive passes and is sealed, construct a
  held-out seed-7 parent at the primary curve's scalar-65 alpha (same beta).
  Its measured global scalar must land in [60,70]. From that exact checkpoint,
  run the same eight incremental alphas by seeds 0,1,2 plus an alpha=1
  endpoint, always scoring against the sealed clean-parent v2 baseline,
  anchors and policy rather than redefining the heavy parent as zero. The
  repeat requires Spearman at least 0.95 and maximum leave-one-dose-out error
  at most 3, archives conditional cliff bisections, and seals a separate
  `derisk/probe2_noise_v2_heavy_parent/` manifest. The exact heavy checkpoint
  may then be reused as Probe 3's parent.
- **Pre-execution tests.** CPU-only invariant tests cover nested coordinate
  sets, deterministic plans, shuffle multiset preservation, factual dropout,
  rejection of old/wrong/limited ladders, endpoint arithmetic, source-hash
  sensitivity and neutral-baseline direction labels. No v2 GPU number or gate
  verdict is claimed by this entry.

## Probe 2 heavy-parent repeat driver implemented (2026-08-29)

- Added the separate `run_noise_sweep_heavy.py` certification driver and its
  CPU contract suite. It verifies the clean-primary manifest and pending-heavy
  verdict, reproduces the clean-ruler policy fingerprint, and refuses to
  redefine the heavy parent as scalar zero.
- Parent construction is the precommitted scalar-65 alpha at held-out seed 7,
  with at most eight same-seed bisections if the measured global scalar misses
  [60,70]. The selected checkpoint is retained for Probe 3; rejected candidates
  and all incremental child checkpoints are deleted after their hashes,
  sidecars, raw evaluations and reanalysis companions are archived.
- The repeat enforces the same eight incremental alphas by seeds 0,1,2,
  beta=1, 256 tokens, clean judge/tokenizer/model identities, Spearman at least
  0.95 and leave-one-dose-out error at most 3. Its alpha=1 child endpoint and
  conditional >20-point cliff bisections are recorded against the clean global
  ruler. Only this sealed aggregate can issue overall Probe 2 PASS.
- Static audit, Python compilation and the heavy-parent CPU contract tests pass.
  No heavy-parent GPU result or verdict is claimed by this entry.

## Probe 2 v2 primary — baseline and terminal endpoint reproduced (2026-08-29)

- The canonical clean-parent primary launched from commit `a268fbf` against
  the pinned Gemma snapshot `093f9f388b31de276ce2de164bdc2081324b9767` in
  the fresh `derisk/probe2_noise_v2/` root. Server invariant suites passed
  before launch.
- Clean baseline raw components reproduce v1 exactly: R 0.0277863005,
  D 0.0961127407, J 0.0204081633, F 0.0416666667. The alpha=1, beta=1,
  seed-0 terminal endpoint also reproduces exactly: R 0.00125916234,
  D 0.00719106540, J 0.828571429, F 1.0. All 196 judge responses parsed and
  the redrawable endpoint checkpoint was deleted after its sidecar and scalar
  artifact were archived.
- This is a reproducibility/provenance checkpoint, not a gate verdict. The
  full 11-rung v2 ladder is running; the 8×3 sweep starts only if that ladder
  passes.

## Probe 2 v2 primary — full corruption ladder PASS (2026-08-29)

- The full 196-record, 11-rung `nested_dual_track_v2` ladder passed before
  any sweep dose was evaluated. R, D, J and F each have Spearman 1.0 against
  corruption fraction, are strictly nondecreasing at every rung, and are
  non-flat.
- Raw start → terminal values and minimum positive rung increments:
  R 0.0277863 → 0.4454938 (min +0.0132070); D 0.0961127 → 0.4774315
  (min +0.00621326); J 0.0204082 → 0.6234694 (min +0.0193878);
  F 0.0416667 → 1.0 (min +0.075). The v1 F backsteps are eliminated without
  changing F's 0.25 weight or relaxing the rung gate.
- All judge outputs parsed. With the independent scalar-instrument gate now
  passed, the driver proceeded to the frozen eight-alpha × three-seed
  weight-noise sweep. No primary or overall Probe 2 verdict is claimed yet.

## Probe 3 v2 precommit — quantify the terminal-side-effect gate (2026-08-29)

- **Frozen certification case, before any Probe 3 v2 GPU result.** Probe 3
  consumes only the exact manifest-verified held-out seed-7 heavy checkpoint
  selected by the final Probe 2 aggregate. It evaluates concept 23
  (`horror_films`) with seed 0, a 120-step budget, snapshots every 10 steps,
  batch size 8, and the full 256-token decay-scalar battery. A certification
  PASS cannot be issued with parameter overrides, a partial snapshot grid,
  incomplete semantic groups, an unverified scalar artifact, or an unsealed
  primary/heavy provenance chain.
- **Numeric collateral gate.** “No terminal side effect” is fixed as an
  erasure-induced global decay-scalar increase of at most **5.0 points** from
  the measured 60–70 heavy-parent baseline. Five points is 5% of the frozen
  0–100 ruler and keeps even a parent at the top of the allowed starting band
  at or below 75, at least 25 points from the terminal endpoint. The earliest
  10-step snapshot that makes every required semantic group ABSENT is the only
  candidate scored against this ceiling; a later snapshot cannot be chosen to
  improve the scalar result post hoc.
- **Precision diagnostic and verdict rule.** The BF16-base arm passes only if
  that semantic snapshot occurs within the 120-step budget and the scalar
  increase is at most 5.0. The otherwise identical fp32-base control runs only
  after BF16 fails. BF16 PASS certifies the ordinary runtime; BF16 FAIL plus
  fp32 PASS certifies late-lineage trainability with `fp32_base` recorded as a
  required mitigation, because that contrast identifies write-back precision
  rather than plasticity loss. Both complete arms failing is Probe 3 FAIL.
  Skipping a required control, using smoke mode, or failing input provenance
  can only produce INCOMPLETE, never PASS. No Probe 3 v2 GPU measurement or
  verdict is claimed by this precommit.

## Probe 2 v2 primary — first sweep observation (2026-08-29)

- The first frozen sweep point, alpha 0.05 / beta 1 / seed 0, completed all
  196 generations and parsed judge responses. Raw components are
  R 0.0650296026, D 0.1294726930, J 0.0642857143, F 0.1291666667; the frozen
  bidirectional v2 ruler reports scalar **8.37**. Its re-drawable checkpoint
  was deleted after the sidecar and scalar artifact were written.
- This is one of three seeds at the first dose, not a seed-mean or gate
  verdict. The canonical sweep proceeded to alpha 0.05 / seed 1.

## Probe 1/3 prerequisite recovery — historical retain corpus (2026-08-29)

- The locally absent `data/retain.json` was recovered byte-for-byte from the
  EC2 experiment workspace rather than regenerated from the unpinned live
  WikiText loader. It contains the established 256 passages (196,670 bytes),
  SHA-256 `e728480722fc649db831b3f1d83d01ea4721e01d926351b8b0cf07004074cb85`.
  The hardened Probe 1 and Probe 3 configurations pin this exact input hash.
- No metric or gate result is claimed by restoring this prerequisite.

## Probe 2 v2 primary — alpha 0.05 seed 1 observation (2026-08-29)

- Alpha 0.05 / beta 1 / seed 1 completed the full battery and measured scalar
  **12.8863296118**. Raw components are R 0.0989805636, D 0.1572279828,
  J 0.0826530612, F 0.1416666667. The checkpoint was deleted after the
  validated artifact and dose sidecar were retained, and seed 2 started.
- Together with seed 0's scalar 8.37 this remains a partial dose result; the
  alpha-0.05 seed mean and all Probe 2 gates wait for seed 2.

## Probe 1 and Probe 3 certification runners hardened (2026-08-29)

- **Probe 1 frozen contract.** A certifying run is fixed to canonical concept
  21 (`nightmares`), forget step budget 120 with the exact step-10 grid,
  heal60, batch8, 256 scalar tokens and seed0. It requires the canonical
  concepts/healing inputs, the exact final Probe 2 heavy+primary seal chain,
  clean-parent bytes, full scalar model/judge/tokenizer/prompt provenance,
  exact semantic group coverage, and recomputation of resumed selection
  claims from their hashed evidence. The selected erasure is the earliest
  held-out original-probe all-groups-ABSENT snapshot. The healed model must
  remain ABSENT on original and conjugate probes, recover at least 0.5 of
  scalar collateral, and stay at or below 20% PCA drift after forgetting and
  healing. Leakage above 1 scalar point remains the documented H4 telemetry,
  not a newly promoted PASS gate. Skipping scalar work is categorically
  INCOMPLETE.
- **Probe 3 frozen contract.** A certifying run consumes the exact retained
  heavy checkpoint covered by the final Probe 2 aggregate and the independently
  verified primary archive. It fixes canonical concept 23 (`horror_films`),
  the same 120-step/10-step grid and full bounded-forget trainer recipe,
  batch8, 256 scalar tokens and seed0. Semantic decisions derive only from
  exact required-group verdicts produced by the pinned clean judge; every
  scalar is validated against the exact outcome/heavy weights, clean
  judge/tokenizer, full prompt batteries, parse completeness and v2 ruler.
  BF16 PASS certifies `bf16_base`; BF16 failure followed by FP32 PASS certifies
  `fp32_base` as the required mitigation; both complete arms failing is FAIL,
  while a skipped required FP32 control is INCOMPLETE.
- **Resume, archives, and runtime.** Both drivers reject output overlap with
  clean or sealed inputs, bind input/instrument hashes and commit, verify exact
  trainer grids/configs, fail closed on changed completion markers, and
  atomically write and immediately reverify exact-coverage SHA-256 manifests.
  Probe 3's precondition and snapshot screens run only the semantic battery;
  unrelated capability/SEA/perplexity work is skipped there, while the chosen
  outcome still receives the full scalar collateral evaluation. This changes
  wall time, not a gate or measurement.
- **Pre-execution verification.** Probe 1's 14 focused tests, Probe 3's focused
  certification suite, the Probe 2 heavy contract suite, corruption-ladder v2
  invariants, bidirectional-normalization v2 invariants, Python compilation,
  CLI imports and diff checks all pass. Independent read-only audits found no
  remaining launch blockers. No Probe 1 or Probe 3 GPU result is claimed here.

## Probe 2 v2 primary — alpha 0.05 seed mean complete (2026-08-29)

- Alpha 0.05 / seed 2 completed at scalar **7.5492462597**, with raw
  components R 0.0460425000, D 0.1178761445, J 0.0551020408,
  F 0.1791666667. The checkpoint was deleted and the sweep advanced to alpha
  0.1 / seed 0.
- The frozen alpha-0.05 scalars for seeds 0/1/2 are respectively
  8.3704563115, 12.8863296118 and 7.5492462597. Their arithmetic seed mean is
  **9.6020107277** (sample standard deviation 2.8737883337; range
  7.5492462597–12.8863296118). This is the first of eight curve points, not a
  Spearman, interpolation, primary, or overall Probe 2 verdict.

## Probe 2 v2 primary — early weight-noise cliff makes the LOO gate impossible (2026-08-29)

- The alpha-0.1 seed scalars are 97.6463829402, 94.9930557046 and
  92.7970806995: mean **95.1455064481**, sample standard deviation
  2.4282429815. Seed 2 raw components are R 0.00213398086,
  D 0.03920406745, J 0.8948979592 and F 0.9625. Thus the dial jumps from the
  alpha-0.05 mean 9.6020107277 to 95.1455064481 after only another 0.05 of
  alpha.
- **Exact frozen-gate impossibility.** The leave-one-dose-out implementation
  removes alpha 0.1, applies the running-maximum policy to the remaining
  bounded 0–100 values, and evaluates the frozen monotone Fritsch–Carlson
  PCHIP. Given y(0.05)=9.6020107277, every possible nondecreasing future curve
  has y(0.2), y(0.3), … <=100. The maximal possible held-out prediction at
  0.1 is **38.9979119006**, attained at the extreme y(0.2)=y(0.3)=100;
  therefore the minimum possible alpha-0.1 LOO error is
  **56.1475945475**, far above the precommitted maximum 3. No unmeasured later
  dose can reverse this failure.
- The parent and active alpha-0.2/seed-0 evaluator were terminated once this
  proof was established, instead of spending the remaining GPU budget on a
  mathematically impossible PASS. That interrupted evaluator had generated
  32/196 items; its fully constructed, re-drawable checkpoint and dose
  sidecar remain temporarily in the root for fail-closed identity capture.
  A dedicated finalizer will verify the six completed scalar artifacts,
  retain the interrupted dose identity, remove only the normal re-drawable
  checkpoint bytes, and seal an immutable numeric **primary FAIL** archive.
  Probe 2 heavy, Probe 1 and Probe 3 remain blocked.

## Probe 2 v3 precommit — resolve or reject the weight-noise knee (2026-08-29)

- **No gate relaxation and no reuse of certification seeds.** V3 keeps the
  sealed v2 clean baseline, full dual-track ladder, bidirectional ruler,
  component weights 0.25/0.15/0.35/0.25, clean judge/tokenizer, unlimited
  256-token scalar battery, primary Spearman >=0.95 and exact monotone-PCHIP
  LOO error <=3. The diagnostic pilot uses seed **11** only. Certification
  seeds 0/1/2 and the held-out heavy-parent seed 7 remain unread by the pilot.
- **Arm A, run first and alone unless it fails.** Keep the exact beta=1
  transform and measure physical alpha
  `[.0025,.005,.01,.02,.03,.04,.05,.055,.06,.065,.07,.075,.08,.085,.09,.095,.10,.12]`.
  Alpha 0 and the beta=1 alpha-1 endpoint may be referenced from the sealed
  v2 ruler only after exact hash/policy/identity validation. Each nonterminal
  checkpoint is re-drawable, retains its dose sidecar and full scalar
  artifact, and is deleted after validation.
- **Arm B, conditional and unique.** Run only if Arm A fails. Keep identical
  tensor coverage and transform but set beta=0.1, measuring alpha
  `[.05,.10,.15,.20,.25,.30,.35,.40,.45,.50,.55,.60,.70,.85,1.0]` on seed
  11. It remains scored against the same clean v2 ruler; it is not re-anchored
  to make its endpoint look better. No third beta or layer-targeted variant
  may be introduced after reading these arms.
- **Frozen pilot fail/promote rules.** A wrong/limited/unparsed scalar or any
  model, judge, tokenizer, prompt, support, weight, policy or resume mismatch
  is INCOMPLETE. An arm fails on an adjacent scalar fall greater than 3. It
  must observe a first nonzero-region value <=5, brackets around scalar
  10/28/45/65/90, and an alpha-1 value >=97. Inside the 5–95 band, an adjacent
  jump greater than 20 at width <=.005 (A) or <=.05 (B) fails the arm. The
  seed-11 monotone-PCHIP screen additionally requires Spearman >=.95 and
  maximum LOO error <=6; this is a promotion screen, not a relaxed
  certification gate. Arm-A promotion suppresses Arm B; Arm-B failure ends
  the weight-noise mechanism and selects the already declared SliceGPT
  fallback.
- **Promotion and fresh v3 certification.** A promoted pilot freezes beta and
  a public controller coordinate `u`, with physical `alpha=g(u)` learned only
  from seed 11's monotone inverse and stored with hashes before certification.
  The certification targets are `u=[.10,.20,.30,.40,.50,.60,.75,.90]` plus
  the clean/terminal endpoints. Fresh seeds 0/1/2 then face the unchanged
  Spearman >=.95 and exact LOO <=3 gates, raw nondecreasing means, the unchanged
  four-component ladder gate, and an additional per-dose seed range <=6.
  Certification results may not refine `g`. Only a sealed primary PASS may
  construct the seed-7 scalar-65 parent; the heavy repeat uses the same frozen
  beta, `u` grid and mapping against the clean ruler. Both sealed archives are
  still required for overall Probe 2 PASS.
- **Fallback boundary.** If both weight-noise pilot arms fail, v4 tests the
  predeclared SliceGPT fractions
  `[.05,.10,.15,.20,.25,.30,.35,.40,.50,.60,.70,.80]` as a separate dial.
  Layer targeting or blended mechanisms are not added post hoc. No v3 GPU
  result or promotion verdict is claimed by this entry.

## Probe 2 v3 precommit clarification — exact pilot and controller semantics (2026-08-29)

- **Pilot raw/fitted semantics.** “Seed 11” is the weight-noise draw; scalar
  decoding and the clean semantic judge remain deterministic seed 0. The
  immutable v2 beta-1/seed-0 baseline and alpha-1 endpoint may support Arm A;
  certification seeds 0/1/2 are not newly evaluated. Arm B reuses only the
  beta-independent clean baseline and measures its beta-0.1 alpha-1 endpoint
  with noise seed 11. For each arm, the low-end rule is the raw scalar at the
  smallest scheduled alpha greater than zero (A .0025, B .05), inclusive
  <=5. A target bracket is an adjacent physical-alpha-sorted pair of raw
  scalars satisfying `left <= target <= right`, inclusive; the immutable
  endpoints may participate. Falls, local jumps and Spearman use raw scalars.
  Pilot LOO holds out only scheduled interior points, uses the raw held value,
  applies running maximum to the remaining ordinates, and evaluates the exact
  frozen PCHIP; endpoints support the fit but are never held out.
- **Interruption versus scientific failure.** Missing/wrong/limited/unparsed
  provenance is a resumable exception: it writes no terminal promotion and
  must never trigger Arm B. A valid predeclared adjacent fall/local-jump may
  terminate an arm early as scientific FAIL; Arm A scientific failure is the
  sole trigger for Arm B. The implementation must compare every newly created
  adjacent low-alpha pair even though the referenced alpha-1 endpoint is
  already present.
- **Frozen mapping algorithm, before pilot results.** For a promoted arm, sort
  its completed physical-alpha points and set fitted ordinates to the running
  maximum of raw scalars. Public targets are
  `u=[0,.10,.20,.30,.40,.50,.60,.75,.90,1]` with target scalar `100*u`.
  Define `g(0)=0`, `g(1)=1`. For every interior target, `g(u)` is the leftmost
  generalized inverse of the exact existing monotone PCHIP, found by 80
  fixed bisection iterations on [0,1] and rounded to 8 decimal places. The
  same algorithm additionally records `g(.65)` for heavy-parent construction.
  All eight rounded certification alphas must be distinct and strictly inside
  (0,1), or the arm fails promotion (A then permits B; B ends weight noise).
  The mapping JSON stores pilot arm/beta, raw and fitted points, target scalars,
  physical alphas, algorithm/version and source hashes, and is itself hashed
  into the sealed pilot summary. No mapping choice is made after seed-11 data.
- **Fresh-certification range and coordinate.** Primary Spearman and LOO are
  computed in public `u` space, never physical-alpha space. At each of the
  exact eight interior u doses, the three finite raw seed-0/1/2 scalars must
  additionally satisfy inclusive `max-min <=6.0`; endpoints are fit supports,
  not range-gated three-seed doses. This range screen is additive to, not a
  replacement for, the unchanged mean Spearman >=.95 and LOO <=3 gates.
- **Frozen heavy use.** A primary PASS constructs the held-out seed-7 parent
  once at physical alpha `g(.65)`; measured global scalar must land in [60,70]
  or heavy certification fails—no mapping refit or physical-alpha bisection.
  Heavy children use the same beta and physical `g(u)` for the same eight
  interior u values, score against the clean ruler, compute Spearman/LOO in u
  space, and face the same inclusive per-dose child-seed range <=6.0. The
  aggregate will preserve the existing final field names used by Probe 1/3
  (`certification_scope`, `clean_ruler`, `primary_archive`, `heavy_parent`,
  policy fingerprint and gate names) while adding v3 mapping/beta provenance;
  consumers must be compatibility-tested before downstream launch.

## Probe 2 v2 terminal-failure finalizer implementation (2026-08-29)

- Added `scripts/finalize_probe2_impossible.py`, a no-PASS-path finalizer for
  the exact interrupted canonical v2 primary. It validates the clean ruler,
  ladder, run configuration, parent identity, all six completed scalar,
  sidecar and bidirectional-reanalysis bundles, and the logged 32/196
  alpha-0.2/seed-0 interruption before changing terminal state.
- The frozen Fritsch-Carlson PCHIP proof is encoded analytically and checked
  against the production evaluator. With the observed alpha-0.05 mean, its
  maximum possible held-alpha-0.1 prediction is `38.99791190061747`; therefore
  the observed alpha-0.1 mean has a minimum possible LOO error of
  `56.14759454748253 > 3`. The final schema reports the observed doses only as
  `partial_curve`, leaves uncomputed ordinary LOO fields null, and records a
  distinct impossibility lower bound and terminal primary/Probe-2 `FAIL`.
- The finalizer archives its committed source identity, primary-runner and
  command-log hashes, and the partial checkpoint's byte-identical dose sidecar
  plus actual weight/support hashes. Only after those checks does it remove
  the exact redrawable `alpha0.2_seed0/checkpoint`, then writes an atomic exact
  manifest and semantically self-verifies sealed reruns.
- CPU contract coverage in `scripts/test_finalize_probe2_impossible.py` passes
  15/15 tests, including 1,000 deterministic monotone PCHIP cases, stale
  scalar and sidecar fail-closed checks, committed-source binding, atomic-copy
  recovery, both terminal-state/manifest crash windows, partial-deletion
  tombstone recovery, source-commit verification after later HEAD movement,
  exact manifest enforcement, deep ruler/completed/aborted-sidecar semantic
  tamper rejection and sealed-rerun idempotence.
  No server archive was finalized and no new empirical result is claimed by
  this implementation entry.

## Probe 2 v3 final pre-data boundary clarifications (2026-08-29)

- Pilot Spearman is computed from raw seed-11 scalars at the arm's scheduled
  points with `0 < alpha < 1` only. Alpha-0 and alpha-1 are fit/bracket
  supports but are excluded from Spearman, including Arm B's scheduled
  alpha-1 point. Pilot LOO continues to hold out each scheduled interior point
  only, while keeping both endpoints as support.
- A target is bracketed only by an adjacent alpha-sorted pair satisfying
  `left_scalar <= target <= right_scalar`; endpoint equality counts and a
  decreasing pair never counts. The low-end screen is exactly the raw scalar
  at the arm's smallest scheduled positive alpha, inclusive `<=5`.
- Scientific early termination is authorized only after a completed scalar
  makes one of three frozen facts irreversible: the fixed smallest scheduled
  point is above 5, an observed adjacent fall exceeds 3, or an observed local
  jump exceeds 20 under the arm's width/band rule. Promotion requires the
  complete exact arm grid. Operational interruption or provenance failure
  remains resumable and writes no terminal summary or Arm-B trigger.
- Every raw point embedded in a promoted controller mapping carries its scalar
  or reference artifact path and SHA-256 (and dose-sidecar path/SHA-256 for a
  newly evaluated point). The mapping binds the frozen schema hash and its own
  fingerprint; the sealed pilot summary additionally binds the serialized
  mapping file SHA-256. These are requirements, not post-result choices.

## Probe 2 v3 certification/heavy endpoint freeze (2026-08-29)

- A fresh primary uses the sealed clean scalar as its `u=0` support and the
  promoted pilot's selected-beta `u=1` artifact as its terminal support: Arm A
  therefore binds the sealed v2 beta-1/seed-0 endpoint, while Arm B binds its
  newly measured beta-0.1/seed-11 endpoint. Neither endpoint is re-evaluated,
  held out, or included in the three-seed range gate.
- Heavy certification uses the measured retained seed-7 parent as its `u=0`
  support. Its `u=1` support is exactly one incremental child with seed 0,
  the promoted beta and stored `g(1)=1`, evaluated against the clean ruler.
  That endpoint is not held out and is not range-gated; only the exact eight
  interior child doses use seeds 0/1/2 and the inclusive raw range <=6 rule.
- Raw mean nondecrease, including the two supports in coordinate order, is a
  verdict gate for both fresh primary and heavy certification. The old v2
  physical-alpha cliff bisection/search/fallback logic does not survive v3:
  primary and heavy evaluate only the frozen controller doses (plus the
  already frozen heavy `g(.65)` construction). They may never insert a new
  point, refit the mapping, or search around a failed heavy parent. Spearman,
  exact PCHIP LOO, raw monotonicity and the per-dose range screen decide the
  certification verdicts on that immutable grid.

## Probe 2 v3 diagnostic-pilot implementation (2026-08-29)

- Added `scripts/run_noise_pilot_v3.py` and its CPU policy suite. The runner
  accepts only the exact sealed v2 mathematical-FAIL archive and clean ruler,
  verifies committed blobs for every executed source, freezes the declared
  Arm A/conditional Arm B grids, and can emit only diagnostic promotion or
  weight-noise failure—never Probe 2 PASS.
- Promotion analysis implements the exact raw low-end/bracket/fall/jump and
  interior-only Spearman rules, raw-held/running-max-rest PCHIP LOO, and the
  deterministic 80-iteration leftmost inverse mapping with eight-decimal
  physical alphas, distinctness, `g(.65)`, schema/fingerprint and source
  artifact hashes. Failure reasons are canonicalized so scientific early-stop
  archives reproduce byte-for-byte under sealed semantic recomputation.
- Each dose stage is resumable and retains scalar plus dose-sidecar evidence.
  A redrawable checkpoint is removed only after its sidecar, source identity,
  scalar provenance, finite components and bidirectional normalization have
  all validated; operational/provenance exceptions preserve it for diagnosis
  and write no terminal outcome. Sealed reruns recompute both arm analyses,
  conditional outcome and mapping, revalidate artifact pointers and inputs,
  reject retained checkpoints, and require an exact manifest.
- The CPU pilot suite, Probe 1's 14 tests, Probe 3 tests, Python compilation
  and whitespace checks pass. No pilot dose has been evaluated and no
  promotion result is claimed by this implementation entry.

## Probe 2 v2 canonical terminal archive — sealed primary FAIL (2026-08-29)

- Ran committed finalizer source `40b9e83913602e14491c9f873c8defb4bab083ca`
  on the synchronized EC2 repository at `e5e1105bfc8b305541da0a6f676c5369a437cd1e`.
  All 15 server CPU contracts passed before execution. The finalizer emitted
  only `PROBE 2 PRIMARY VERDICT: FAIL` / `PROBE 2 OVERALL VERDICT: FAIL`, then
  a second invocation semantically verified the sealed result without change.
- Full-precision completed means are alpha .05 = `9.6020107276641` and alpha
  .10 = `95.1455064481079`. The exact frozen Fritsch-Carlson upper bound at
  held alpha .10 is `38.99791190057316`, making the minimum possible absolute
  LOO error `56.14759454753474 > 3`. This supersedes only the final decimal
  digits of the rounded-fixture implementation regression; the mathematical
  conclusion is unchanged.
- The alpha-.2/seed-0 evaluation remained incomplete at 32/196 with no scalar.
  Its byte-identical dose sidecar, source identity and actual checkpoint
  weight/support hashes are preserved in the certificate. The exact 8.1 GB
  redrawable checkpoint was atomically renamed and deleted only afterward;
  both checkpoint and deletion tombstone are confirmed absent.
- The immutable 34-file archive is copied to `derisk/probe2_noise_v2` and its
  exact manifest verifies locally. SHA-256: manifest
  `f6ced0bfb1530b61cf0f01778b9a082518c412be3a034b48d2841215d0fccd14`,
  summary `e8bb1b91e6ddfe37a5a27a676a96488585b3abb19d106cd0e678ade26f94c6e7`,
  impossibility certificate
  `43f98f989c22deb95a78c4e5aa441fdda94e2e7a9836010be7ee554bcf174d5b`.
  This is a canonical v2 primary **FAIL**, not Probe 2 PASS; the precommitted
  v3 diagnostic pilot is the next mechanism iteration.

## Probe 2 v3 certification, heavy repeat, and consumer implementation (2026-08-29)

- Added the fresh v3 primary certification runner in commit `6cc8fb5`. It
  consumes only a promoted, sealed v3 pilot mapping; evaluates the exact eight
  public `u` doses with seeds 0/1/2; and recomputes the frozen Spearman, exact
  monotone-PCHIP LOO, raw-mean nondecrease, per-dose range, and unchanged
  ladder gates. Each of the 24 re-drawable checkpoints is rehashed live before
  deletion, its internal dose sidecar must equal the archived copy byte for
  byte, and an atomic validation/deletion receipt makes the narrow post-delete
  crash window recoverable. The exact primary archive has 101 non-manifest
  members, including 24 deletion receipts. Its adversarial CPU suite passes
  26/26 tests.
- Added the one-shot held-out heavy-parent repeat in commit `1b954ba`. It binds
  seed 7 to the pilot's stored `g(.65)`, accepts the measured parent only in
  the inclusive [60,70] band, performs no search or mapping refit, retains the
  exact parent checkpoint, and applies the same public-u gates to the eight
  three-seed child doses plus the frozen endpoint supports. Exact conditional
  PASS/FAIL archive schemas, live checkpoint/support hashes, internal/archive
  sidecar equality, semantic stage markers, finite JSON, and durable child
  deletion evidence are enforced. A final launch audit then closed an
  exactly-once resume gap: incomplete/unknown checkpoints and every orphaned
  output combination are now preserved and fail closed; apply is possible
  only in an exactly empty canonical dose directory; an existing archived
  sidecar is never overwritten; and the only remaining checkpoint removal is
  authorized by completed semantic validation. The expanded heavy
  policy/adversarial suite passes.
- Updated Probe 1 and Probe 3 consumers in commit `62dcbcd`. V3 acceptance now
  delegates first to the exact sealed heavy producer validator, while legacy
  v2 remains isolated. Defense in depth rejects non-finite JSON, mapping key or
  numeric aliases, non-canonical raw/fit provenance, overlapping archives,
  clean-parent substitution, and retained-checkpoint byte changes. Arm B's
  frozen `beta=0.1` path is covered without a beta-1 hardcode. Probe 1 passes
  24/24 CPU tests with one optional real-v3-archive smoke test skipped until a
  sealed GPU archive exists; Probe 3, the v2 heavy contracts, pilot policy,
  v2 finalizer, compilation, and whitespace checks also pass.
- These entries record implementation and adversarial validation only. They
  do **not** claim a primary, heavy-parent, or overall Probe 2 GPU verdict.
  Certification remains blocked on a sealed diagnostic-pilot promotion; a
  pilot failure instead follows the already frozen SliceGPT v4 boundary.

## Immutable large-archive release channel enabled (2026-08-29)

- Enabled GitHub immutable releases for the private
  `bgigurtsis/sequential-unlearning` repository and verified the repository API
  now reports `enabled: true` (`enforced_by_owner: false`). No release, tag, or
  asset was created by this change.
- This channel is reserved for sealed experiment archives that cannot travel
  through ordinary Git, principally the approximately 8.1 GB retained v3
  heavy-parent checkpoint required by Probe 3. The canonical server archive
  will remain byte-untouched; a deterministic tar stream will be split into
  sub-2-GiB assets, hashed per part and as a whole stream, reassembled and
  verified while the release is still a reversible draft, and published only
  after its embedded `MANIFEST.sha256` matches the canonical archive. The
  published release URL, target commit, manifest hash, stream hash, part hashes
  and verification result must then be committed here.

## Probe 2 v4 SliceGPT protocol freeze — no GPU result (2026-08-29)

- Before the conditional Arm-B run reached a terminal verdict, froze the full
  SliceGPT fallback contract in `docs/V4_SLICEGPT_PROTOCOL.md`. The choice is
  independent of the partial weight-noise curve and preserves the already
  declared fraction grid and no-blend/no-layer-targeting boundary.
- Pinned official Microsoft TransformerCompression source commit
  `6b12cdee6ad51791d7c776b3a046bc408b9e77e9`, the exact current validated
  Python/ML environment, WikiText-2 128x2048 fixed calibration preprocessing,
  FP64 PCA with deterministic sign canonicalization, residual-width fraction
  semantics and all twelve exact retained dimensions. Diagnostic seed 11,
  fresh primary seeds 0/1/2 and held-out heavy-parent seed 7 retain the
  project's existing data separation.
- Upstream does not support Gemma-3 and its Llama norm fusion is mathematically
  invalid for Gemma's `(1+w)` sandwich norms. V4 therefore requires a
  project-specific text-only adapter with dense conjugated post-affines,
  untouched q/k norms, exact residual shortcuts, native sharded Safetensors and
  one shared eval/train/merge loader. FP64 algebra, BF16 full-battery/logit,
  save-load and one-step PEFT/merge equivalence gates are mandatory before any
  nonzero slice. A miss is adapter `INCOMPLETE`, not scientific SliceGPT FAIL.
- Pilot promotion, public-u mapping, fresh primary and one-shot heavy repeat now
  use the same numeric bars as v3, with physical fraction/dimension replacing
  alpha: raw monotonicity, Spearman >=.95, diagnostic LOO <=6, certification
  LOO <=3, per-dose seed range <=6, unchanged ladder gates and heavy scalar
  [60,70]. Exact fail-closed archive and checkpoint-deletion semantics are also
  frozen. No v4 transformation, scalar, promotion or Probe 2 verdict is
  claimed by this entry.

## Probe 2 v4 pinned upstream source archive (2026-08-29)

- Vendored the complete official Microsoft TransformerCompression source at
  commit `6b12cdee6ad51791d7c776b3a046bc408b9e77e9`, root tree
  `b58f7a03ed03a968d6b763b29b100f2683e6dfd2`, without installing its older
  environment or modifying the vendor tree for Gemma. The archive contains
  exactly 40 blobs / 211,032 bytes, with 34 mode-100644 and six mode-100755
  paths, no symlinks or submodules, and no Gemma/project-local patches.
- The full MIT license SHA-256 is
  `c2cfccb812fe482101a8f04597dfc5a9991a6b2748266c47ac91b6a5aae15383`.
  The sorted per-source-file manifest SHA-256 is
  `ba3ee5f9788e4a5e937eabcac6beaeb3aef31746952b4c3ddca452b22fedc2a4`.
  `.gitattributes` disables text conversion for the whole vendor archive so
  these exact upstream bytes survive Windows checkouts.
- The committed verifier anchors the upstream commit/tree, metadata, license,
  manifest, working-tree bytes, Git-index membership/blob IDs/modes and text
  attributes. Its 13 adversarial tests pass for baseline, fresh Windows-style
  checkout, content/manifest/metadata/license tamper, extra/missing paths,
  attribute/index staleness, wrong mode and wrong upstream checkout. Historical
  whitespace in upstream files is intentionally preserved byte for byte.
- This is a source/provenance archive only. It does not make the Gemma-3 v4
  adapter launchable and claims no SliceGPT transformation or GPU result.

## Probe 2 v4 fail-closed readiness boundary — no GPU result (2026-08-29)

- Added a bounded v4 readiness runner, Gemma-3 residual-basis algebra module,
  zero-slice diagnostic harness and 30-test adversarial suite. Their SHA-256
  digests are respectively
  `39e8535e538c70cba081bcdb77fcaf322852a47a08502712e0b074fc725a2222`,
  `8639c23e706a46cc6bf1cc39907d4fa3a526e33aa2efdff63723d7873be365c1`,
  `e5544019754b3b2ff6823c3bfcdbaf7e33844c89d9741d5e15fc0d5b78ddc7b4`
  and
  `e2f6587363ede1b96b1ea253181f17195e6321118c27871594cb4e1e494100d0`.
- The algebra implements Gemma's `(1+w)` pre-norm fusion, dense conjugated
  post-affines and residual shortcuts while leaving q/k norms untouched. The
  zero-slice harness is deterministic and in-memory-only, binds the committed
  protocol/vendor/source/runtime/tokenizer/input provenance, verifies the
  exact changed-parameter set and proves parent files remain byte-identical.
- Archive creation and replay are fail closed: malformed or non-finite JSON,
  unexpected members, stale temporaries, symlink ancestors, manifest drift and
  semantic rewrites are rejected. Local validation passed 30 tests with the
  torch-only test skipped; an isolated EC2 CPU run passed all 30, including
  real `Gemma3RMSNorm`, FP64 rotation and BF16 post-affine ordering checks.
- The only admissible status is `BLOCKED_ADAPTER_QUALIFICATION`; this boundary
  cannot perform a nonzero slice, save a sliced model or emit Probe 2 PASS.
  Nonzero v4 remains blocked on the genuine Gemma-3 adapter, six sealed
  qualification gates, calibration tensor materialization, native
  serialization, shared PEFT/project loading and a sealed runtime lock. This
  entry claims no SliceGPT transformation, scalar or scientific result.

## Probe 2 v3 diagnostic weight-noise pilot — FAIL_WEIGHT_NOISE (2026-08-29)

- Ran the precommitted diagnostic-only two-arm pilot on the pinned clean
  Gemma-3 4B parent with source commit
  `e5e1105bfc8b305541da0a6f676c5369a437cd1e`, batch size 8, maximum 256
  new tokens and diagnostic seed 11. The ruler was the immutable v2 archive
  (`MANIFEST.sha256`
  `f6ced0bfb1530b61cf0f01778b9a082518c412be3a034b48d2841215d0fccd14`)
  with its frozen bidirectional-synthetic normalization and 196-prompt
  battery. This screen could promote a family into fresh certification but
  could never issue Probe 2 PASS itself.
- Arm A (`beta=1.0`) measured scalar values `1.3575057537, 0.6293893939,
  0.4302119840, 0.3468269826, 1.1439975329, 2.9476951737,
  6.9666180076, 14.0864358838, 35.4227002325` at alpha `.0025, .005,
  .01, .02, .03, .04, .05, .055, .06`. It stopped at the first authorized
  terminal failure: the `.055 -> .06` local rise was `21.3362643487` points
  over width `.005`, above the frozen 20-point cliff bar. Its observed
  Spearman was `0.7666666667` and maximum diagnostic LOO error
  `20.1401433891`; the complete-grid promotion gates were therefore not met.
- The conditional Arm B (`beta=.1`) measured `0.1250637978, 0.2208232763,
  0.4280172023, 0.6286084878, 1.0990814692, 4.9423092231,
  17.4969173967, 70.5014179275` at alpha `.05, .10, .15, .20, .25, .30,
  .35, .40`. It was strictly monotone on the observed points (Spearman
  `1.0`) but the `.35 -> .40` rise was `53.0045005308` points over width
  `.05`. This independently violates the same cliff bar; its maximum
  diagnostic LOO error was also `13.6112051879 > 6`, and the scheduled grid
  could not be completed or furnish the required target brackets.
- The canonical verdict is therefore **`FAIL_WEIGHT_NOISE`**: neither weight
  noise family is a controllable decay dial under the frozen gates. No v3
  primary or heavy-parent run is authorized, so this is a scientific stop for
  weight noise rather than an operational error or an overall Probe 2 PASS.
  The recorded next step is the already precommitted SliceGPT v4 fallback.
- The copied archive contains exactly 56 non-manifest members; every dosed
  checkpoint was re-drawable and deleted after its sidecar/evaluation was
  sealed. `pilot_summary.json` SHA-256 is
  `78818cefdc0365c366c2c0c9defca2bdb7c706d53ba95e548cb19a2efc45fb52`,
  `COMPLETE.json` SHA-256 is
  `d83110cd1a9923274fc806901d5710b58709e20c4b00c5d004d74455bd38855d`,
  and `MANIFEST.sha256` SHA-256 is
  `a0b567b09b10a4a59c266ea59e1e5f470718c778c5b8a47b0c1d83468ecde2a2`.
  All manifest members verified on EC2 and after copying to Windows. An exact
  sealed rerun reported the immutable verdict and changed zero bytes; the
  server checkout remained at the same source commit before and after.

## Immutable heavy-archive packager implementation — no GPU result (2026-08-29)

- Added the deterministic streaming packager that will carry any retained
  multi-gigabyte heavy-parent checkpoint through the repository's enabled
  immutable GitHub-release channel. It reads a sealed source without mutation,
  emits a sorted GNU-tar stream with fixed metadata, splits it into at most
  2,000,000,000-byte parts, records per-part and whole-stream hashes and only
  promotes a sibling `.pending` directory after complete source-bound
  verification. Existing output is validation-only and cannot be rewritten.
- Verification is structural rather than permissive `tarfile` extraction: it
  reserializes every exact 512-byte GNU header, hashes streamed member data,
  requires zero data padding, two end records, zero record padding and exact
  record-size EOF. It also enforces the embedded canonical LF-only sorted
  source manifest, raw POSIX path spelling, exact membership/order, Windows
  symlink/junction/reparse rejection and the release part-size ceiling.
  Source-less release verification requires both externally committed tar and
  package-manifest SHA-256 roots, so self-consistency is never presented as
  authenticity.
- The 14-test adversarial suite passed with one Windows symlink-creation
  privilege skip. It covers deterministic replay, coherent part/metadata
  rebinding, arbitrary trailing bytes, nonzero tar padding, traversal/path
  aliases, CRLF/unsorted manifests, source substitution, part/metadata/extra
  member tamper, interrupted-output preservation and external hash binding.
  An additional real-archive smoke packaged the 34-member v2 archive into
  eight 1,000,000-byte parts and independently verified the exact 7,895,040
  byte stream hash
  `96c58b75c19f1d77ecd9cb7da0a6c5bcb06cb563ba01e11ef4d59efc8d935d36`.
  The packager source SHA-256 is
  `6d56b016586a38efe14571bb8a2192749dcdfdc8b56ab015795480516b08166a`;
  its test SHA-256 is
  `ec8f169123b65f70b3eacced7a80dccb52817c3a117c73c4d3b5c0be053b6c6c`.
  This is archive infrastructure only and claims no Probe 2 result.

## Probe 2 v2 archive transport correction — no numeric change (2026-08-29)

- During the first bundle materialization of the sealed archives on EC2, an
  exact backup-versus-checkout comparison found that v2's canonical
  `commands.log` was absent from Git even though it is entry 8 of the sealed
  `MANIFEST.sha256`. The repository-wide `*.log` ignore rule had hidden the
  file when the 34-member v2 archive was originally committed. The server's
  pre-sync archive backup and the laptop copy both retained identical bytes,
  SHA-256
  `660dd399f62d6b77bc46e3d800d18a1863acb18a30146160fc6c3384266a04e8`.
- Force-added those exact pre-existing manifest-bound bytes. No archive file,
  manifest, scalar, certificate, configuration or verdict was regenerated or
  changed. This corrects Git transport completeness only; the canonical v2
  verdict remains FAIL and all previously recorded numeric values/hashes are
  unchanged. The v3 archive was independently backup-compared in full and had
  no difference because its ignored command log had already been force-added.

## SliceGPT v4 zero-slice diagnostic namespace fix — no result (2026-08-29)

- Launched the committed identity-only Gemma-3 zero-slice diagnostic on the
  pinned clean parent at server source commit `89a07cb`, with the frozen four
  prompts, seed 0, 32-token greedy generation and deterministic CUDA settings.
  It failed closed before writing a report: the expected-change verifier used
  a parameter suffix and therefore matched both
  `model.language_model.layers.0.self_attn.q_proj.weight` and the vision
  tower's same-suffix projection. No dimensional slice or model save occurred,
  the report and temporary paths remained absent, and the GPU returned idle.
- Replaced suffix discovery with the exact frozen text parameter prefix
  `model.language_model.layers`, and added a multimodal-collision regression
  containing vision-tower q-projection and MLP names. The complete bounded v4
  readiness suite still passes 30 tests with only its local torch-only test
  skipped. This was an implementation-namespace failure and claims no
  zero-slice measurement, adapter qualification or Probe 2 verdict; the fixed
  diagnostic must be rerun from its fresh output path.

## SliceGPT v4 identity-fusion diagnostic — measured, no verdict (2026-08-29)

- Reran the fixed identity-only diagnostic at source commit
  `8ff1f4d6203a0fd82801b4e2ce833c8fc11d9370` on the exact pinned clean
  Gemma-3 4B parent, four frozen text prompts, seed 0, 32-token greedy
  generation, BF16 storage and deterministic L4 execution. It fused only the
  two pre-branch Gemma `(1+w)` norm weights into q/k/v and gate/up projections
  at identity basis, in memory. It performed no dimensional slice and saved no
  model; all parent weight/support file hashes were verified unchanged.
- The partial identity fusion was **not** numerically equivalent to the clean
  forward: logits were not bitwise equal, maximum absolute logit error was
  `5.671875`, mean absolute error `0.16142979264259338`, argmax-token agreement
  `0.887499988079071`, and greedy generation token IDs were not exact. These
  are measurements from the deliberately incomplete identity-fusion harness,
  not the full rotated/dense-post-affine adapter qualification gate. The report
  therefore correctly records `MEASURED_IMPLEMENTATION_DIAGNOSTIC_NO_VERDICT`,
  `full_adapter_qualification_gate_applied=false` and no Probe 2 verdict.
- The result confirms that the earlier pre-norm-only fusion is insufficient
  and must not be used as SliceGPT evidence. The next admissible step remains
  the independently audited full adapter plus captured-activation, full
  196-prompt, serialization and PEFT gates before any nonzero slice. The report
  SHA-256 is
  `3240ae56851a89d8c570095ac24d4640fb3fa0677d64feb3ec185d3435d69f39`;
  its one-member `MANIFEST.sha256` SHA-256 is
  `ee571166ea55867816f9da37cf730661931528ef0035ea4756ec9e37db2ede5a`.

## SliceGPT v4 calibration materializer implementation — no GPU result (2026-08-29)

- Added the fail-closed deterministic WikiText-2 calibration materializer for
  the frozen v4 128x2048, batch-16, int64 input/mask contract and the declared
  diagnostic/primary/heavy seed separation. It binds an external immutable
  canonical runtime lock, exact L4/CUDA/package/Python identity, deterministic
  algorithms, TF32-off state and a `CUBLAS_WORKSPACE_CONFIG=:4096:8` value
  present before interpreter startup. Runtime or numeric-type aliases fail.
- The runner copies the exact pinned Arrow source into a pristine private
  directory, disables Hugging Face Datasets caching, executes only the
  hash-verified pinned vendor preprocessing and rechecks the source afterward.
  It rejects preloaded/substituted vendor modules and verifies the actual
  imported path and bytes. Each seed produces a strict sealed Safetensors
  archive with exact tensor shapes/dtypes/hashes, all-one masks, input/runtime/
  source provenance and immutable replay semantics.
- Calibration text is checked against the exact 1,848 protected prompts across
  15 committed evaluation/training sources under the frozen matching policy;
  source membership and the recomputed protected count are exact. Symlink,
  cache, overlap, archive, tensor, runtime-lock and self-rehash attacks fail.
  The independently audited suite passes 22 tests with one Windows
  symlink-creation privilege skip; lexical rejection was separately reviewed.
  Source SHA-256 is
  `32ef3e59a329c9c6460b2d337335f3b086b825f776c33262f078295041a5e279`;
  test SHA-256 is
  `aefcb1f9cd9f897c2b0295879d12e6ddb5fd07734e641f683a31a4be0345a71c`.
  This implementation claims no materialized production tensors, adapter
  qualification or Probe 2 result until the committed runtime lock is supplied
  and the live EC2 run seals.

## SliceGPT v4 Gemma-3 adapter core implementation — nonzero locked (2026-08-29)

- Added the independently audited Gemma-3 residual-basis adapter core for the
  exact pinned 34-layer/2560-width Transformers topology. It implements FP64
  canonical basis algebra, `(1+w)` sandwich pre-norm fusion, dense
  `Q.T @ diag(1+w) @ Q` post-affines, rectangular residual shortcuts and the
  real GQA q/k/v/o widths while preserving q/k norm objects and bytes. Runtime
  storage/execution is fixed to finite colocated BF16 parameters and FP32 norm/
  affine computation; caller-controlled precision bypasses fail closed.
- Transformation is off-object and atomic: every layer replacement is built
  and postvalidated on a clone, all 34 layers are prepared before exposure,
  cross-layer basis continuity and embedding/head identity boundaries are
  checked, and layer-list plus `_no_split_modules` assignment is rolled back on
  failure. The compressed layer preserves the real HF decoder subclass,
  checkpoint state, cache argument forwarding, hidden-state capture hooks and
  train/eval state. Exact backbone/config/attention/MLP/embed/head classes,
  attributes, aliasing, shapes, dtypes, devices and finiteness are required.
- The public core cannot issue authorization: identity application is an exact
  parameter/object no-op, and every reduced retained dimension is
  unconditionally rejected even if a caller fabricates a capability. The
  11-test suite passes locally with eight Torch-dependent tests skipped on the
  Torch-free Windows runtime; those include rectangular GQA, forced-OOM source
  immutability, precision bypass and model rollback and must run on EC2 before
  any promotion. Independent code audit is APPROVED for this explicitly
  unqualified scope.
- Core SHA-256 is
  `6d2190b5d6bd34909ed9ec550fea79893bd164f53d786603fe10256f20061063`;
  test SHA-256 is
  `f36aa08ec03d1f1e69579736b22a1e8065288832f86cb3553e68d79f9c0df822`.
  Captured-activation algebra, real-HF cache/checkpoint/capture execution,
  full-battery/logit gates, model endpoint integration, native serialization,
  PEFT smoke and a future sealed authorization issuer remain mandatory. This
  entry claims no nonzero slice, adapter qualification or Probe 2 result.

## SliceGPT v4 Torch identity lock correction — no runtime lock emitted (2026-08-29)

- The first production runtime-lock capture on the exact EC2 host failed
  closed before writing a file. `importlib.metadata.version("torch")` reports
  the installed distribution as `2.13.0`, while `torch.__version__` correctly
  carries the CUDA build identity `2.13.0+cu130`; the materializer had used the
  latter spelling for both records and rejected the real package map as drift.
  The fresh output directory remained empty and was removed after an explicit
  emptiness check, so no partial runtime lock or calibration tensor exists.
- Separated these two frozen identities: `packages.torch` must be exactly
  `2.13.0`, while the independent Torch runtime record must be exactly
  `2.13.0+cu130` with CUDA 13.0. Cross-aliases in either direction and a
  `+cu129` substitution are adversarially rejected. The independently audited
  materializer suite now passes 23 tests with the same Windows symlink-
  privilege skip. Updated materializer SHA-256 is
  `3ae1195c688353f43fefa36d0bf4da492e04f613e811b0ee751d3c876974443e`;
  updated test SHA-256 is
  `16a213398498546d41d97fe25c6d1a5164e27220a6926a5cab257fe54aba98a5`.
  Runtime capture must be retried from a committed/synced source; this entry
  claims no runtime qualification, calibration materialization or Probe 2
  result.

## SliceGPT v4 immutable EC2 runtime lock captured (2026-08-29)

- Retried from committed/synced source `a0fd8c8` with
  `CUBLAS_WORKSPACE_CONFIG=:4096:8` present before Python startup and sealed the
  exact live single-L4 runtime observation before materializing calibration
  data. It binds CPython 3.12.3 and executable bytes, Linux/AWS kernel, NVIDIA
  driver 595.71.05, L4 compute capability 8.9 and 23,661,248,512-byte memory,
  Torch distribution 2.13.0 versus runtime build 2.13.0+cu130, CUDA 13.0,
  cuDNN 92000, Torch build config/Git identity and every frozen package.
- Deterministic Torch algorithms were enabled, both CUDA-matmul and cuDNN TF32
  flags were false, and the captured CUBLAS workspace value was exact. The
  corrected materializer loaded the copied canonical JSON locally and
  reproduced the independent distribution/build identities. Runtime-lock
  SHA-256 is
  `62fe44072ed709e2a3a1852035aa68867a0eebf3bcf42613cb836ad7f210cabe`;
  its one-member `MANIFEST.sha256` SHA-256 is
  `647771d87f9db84a0ef5de0d633b917ee1c2e932424101bf3e875a15c2fdbba8`.
  This is the pre-existing immutable lock required by all five production
  calibration materializations. It is runtime evidence, not yet the composite
  runtime qualification archive and not a Probe 2 result.

## SliceGPT v4 composite runtime qualifier implementation — no PASS archive yet (2026-08-29)

- Added the independently audited fail-closed qualifier that will consume the
  committed canonical provenance spec, immutable runtime lock and all five real
  seed 0/1/2/7/11 Safetensors calibration archives. It calls the exact
  hash-verified materializer validator and revalidates tensor shape/dtype/
  all-one-mask, seed, runtime, source, vendor, parent and prompt-disjointness
  semantics rather than trusting archive hashes alone.
- The qualifier binds exact recursive parent and clean-ruler files/directories,
  the known parent/materializer identities and all 15 protected prompt sources.
  It lexically confines output to repository `derisk`, rejects dot aliases and
  symlink/junction/reparse ancestors, binds the committed spec and current
  qualifier bytes, and semantically revalidates every external dependency on
  immutable replay. Parent/calibration coherent rehash, extra/empty members,
  source drift, target escape and replay-source substitution all fail.
- Runtime package Torch `2.13.0` is distinct from runtime build
  `2.13.0+cu130`. Exact types prevent Python bool/int equality aliases for CUDA
  availability/count/index/capability and all determinism flags. The 12-test
  adversarial suite passes and the final independent audit is APPROVED.
  Qualifier SHA-256 is
  `aa83ea05978abe00d39bc2b8e69d9dd97a3354b51862398fd37c2b22725503b3`;
  test SHA-256 is
  `8f72b968c8a6e686f3d010d26868b83174b6ec6a09faa1dfb5061ac8bad4c28d`.
  No runtime-qualification PASS archive is claimed here: the five production
  calibration archives and committed provenance spec must exist first, and
  adapter qualification remains separately incomplete.

## SliceGPT v4 adapter authorization-boundary ordering fix — no nonzero run (2026-08-29)

- The first full Torch-backed EC2 adapter suite (CUDA hidden) exposed a
  fail-closed test-ordering defect: its deliberately reduced 8x4 toy basis was
  rejected by the floor-to-8 basis rule before the stronger expected
  `sealed authorization` boundary. No transform or GPU computation occurred,
  and the suite stopped at that single assertion failure.
- Moved the outer nonzero safety check ahead of detailed basis validation for
  every recognizable `[hidden_size, retained!=hidden_size]` Tensor/Parameter.
  Missing authorization now always raises the sealed-authorization error and a
  fabricated object always raises the unqualified-core rejection; both occur
  before deepcopy or mutation. Exact topology validation still runs first, and
  all full-width identity/validation behavior is unchanged. Added the fake-
  capability adversarial assertion.
- Independent code audit APPROVED the ordering change. The isolated EC2
  Torch-backed suite with CUDA hidden then passed all 11 tests, including the
  eight that the local Torch-free runtime skips. Updated core SHA-256 is
  `c4df2be9111fd293454b19f98fba5d46805479d51db02d0611dcfab58f73cfdd`;
  updated test SHA-256 is
  `2edd0492561e9eba0430d0c5d700d8d491f2b0d39fb6ac52276cd31929c35873`.
  This closes a safety-test ordering issue only and does not authorize or claim
  a nonzero slice, adapter qualification or Probe 2 result.

## SliceGPT v4 calibration seed-11 failed closed; direct vendor loader fixed (2026-08-29)

- The first production seed-11 materialization from committed EC2 source
  `a0798ce` failed before creating its output root. Importing
  `slicegpt.data_utils` executed the vendor package initializer, whose unrelated
  configuration path requires the absent `ml_collections` package. The L4 was
  idle after failure, `derisk/probe2_slicegpt_v4_calibration_seed11/` remained
  absent, and no tensor, metadata, manifest, COMPLETE marker or scientific
  result was produced.
- Replaced the package import with execution of the exact already hash-verified
  `data_utils.py` bytes under a sealed unique module identity. The loader never
  imports `slicegpt/__init__.py`; it rejects preloaded package or sealed-module
  substitutions, nonstandard loader/spec/path/name identities, source changes
  before or after execution, package contamination, and `sys.path` mutation.
  The returned callable is bound back to the sealed module and exact source.
- The independently audited adversarial suite passes 24 tests with one Windows
  symlink-creation privilege skip; `py_compile` and `git diff --check` pass.
  Updated materializer SHA-256 is
  `f9458b251c5ce29ef2906f20f87f6ef1bb41ba80a4135daf00709cb13698c3d7`;
  updated test SHA-256 is
  `471fc36c351b023b63d8fc8af730af2020bb94db2600f9479f861b71d4ef6ab2`.
  This is an operational loader correction only. Production seed 11 must be
  retried from the committed/synced source before any calibration or Probe 2
  claim is made.

## SliceGPT v4 calibration lossy-roundtrip correction — no archive produced (2026-08-29)

- The next production seed-11 attempt passed the runtime and direct-source
  loader gates but failed before `root.mkdir`/archive creation when concatenating
  vendor batches: observed widths included 2,037 and 2,038 rather than the
  frozen 2,048. The exact cause is the pinned upstream sequence
  `tokenize -> truncate 2048 -> convert_tokens_to_string -> retokenize`:
  Gemma tokenization is not invariant across the text conversion. The final
  upstream `padding="longest"` pads only to each 16-row batch maximum;
  `max_length=2048` is a truncation ceiling, not max-length padding. The remote
  seed-11 root was confirmed absent and the GPU idle, so no tensor, metadata,
  COMPLETE marker, manifest, calibration result or Probe 2 result exists.
- Because padding would create forbidden zero mask entries, and appending or
  activating invented padding tokens would silently change the frozen
  instrument, the pre-data protocol now documents one narrowly scoped project
  adapter: a lossless tokenizer proxy around the unchanged pinned vendor
  function. It delegates the initial tokenization and preserves each exact
  vendor-selected/truncated 2,048-token block behind a unique, collision-bound,
  one-use placeholder. Only the vendor's exact final batched call can consume
  those placeholders. The proxy performs exact token-to-ID and ID-to-token
  identity checks with an explicit UNK policy, requires exactly one prepended
  Gemma BOS and no other special token, truncates 2,049 to 2,048, and emits an
  all-one mask. Unknown, duplicate, mixed/raw, paired, altered-call and
  out-of-order uses fail closed.
- The materializer independently reproduces the real `DataLoader` sampler
  sequence, including its base-seed RNG consumption and lazy
  `SubsetRandomSampler` permutation, and requires the placeholder consumption
  order to match exactly. It then rechecks eight 16-row batches, final
  `[128,2048]` IDs/masks, labels equal IDs, all-one masks, exactly one BOS in
  column zero, tokenizer files/class/config/special-token IDs, and sealed order
  evidence. This is explicitly a documented project correction of only the
  lossy text hop, not a claim of unchanged upstream retokenization; every other
  source/runtime/data/disjointness/archive gate remains frozen.
- The five exact Torch-2.13 sampler vectors are frozen in source and the live
  producer must independently recompute each selected seed's order. Offline
  validation compares the complete vector to its seed-specific constant and
  hash, parses Safetensors bytes to require exactly one recorded BOS at column
  zero per row, and rejects bool aliases for every seed record. Coherent
  sampler/order-hash, BOS/tokenizer/tensor, and bool-seed rewrites are covered.
- The adversarial materializer suite passes 29 tests with two local skips: the
  Windows symlink-privilege fixture and the exact Torch sampler recomputation,
  which is server-only and must pass on the pinned EC2 runtime. `py_compile`
  and `git diff --check` pass. Materializer
  SHA-256 is
  `4caf4f2c3791d895ebf48bf6223b0ff0ac08b88601b2545bfd10e267626da7a4`;
  test SHA-256 is
  `5d1be523fc8fabe078d126f2b03038205c551dca934f031da6aa5c1c513cb4dc`.
  Production seed 11 must be retried only after this source, protocol addendum,
  and experiment record are committed and synced.

## SliceGPT v4 slow-tokenizer special-token correction — no archive produced (2026-08-29)

- The next seed-11 producer attempt failed closed before output-root creation:
  pinned Transformers 5.14 loads the parent as `GemmaTokenizer`, which has no
  `build_inputs_with_special_tokens` method. The remote seed-11 root remained
  absent, so this was an API-surface discovery only and produced no tensor,
  metadata, manifest, COMPLETE marker, calibration result or Probe 2 result.
- Introspection bound the actual backend rather than guessing a replacement.
  Its exact `TemplateProcessing` state uses single `[BOS(2), A]` and pair
  `[BOS(2), A, BOS(2,type_id=1), B(type_id=1)]` templates, with exact integer
  special-token counts one/two. The lossless proxy now requires the exact
  `GemmaTokenizer` class, tokenizer support hashes, post-processor type,
  serialized state, representation, BOS/UNK IDs and special-token counts.
  Only then does it directly construct `[BOS, *captured_token_ids]` and perform
  the already frozen 2,049-to-2,048 truncation. Missing/substituted processors,
  altered state/representation or count drift fail closed; there is no fallback
  method or inferred policy.
- The adversarial suite now passes 30 tests with the same two justified local
  skips (Windows symlink privilege and server-only exact Torch sampler
  recomputation); `py_compile` and `git diff --check` pass. Materializer
  SHA-256 is
  `4f8a9b62d823677eb0fdec29b94e557279c5657d97077f360904e0680e479fcf`;
  test SHA-256 is
  `6c2613491386d2ae7f24757e870af3283f6402e40a2a18f2a46168163f07cdb6`.
  Production must be retried only after this correction and protocol/log
  addenda are committed and synced.

## SliceGPT v4 five-seed calibration archives materialized (2026-08-29)

- From committed/synced source `475d1f0` and the immutable EC2 runtime lock,
  materialized the complete frozen calibration seed set 0/1/2/7/11. Every
  archive contains exact int64 `[128,2048]` input IDs and all-one attention
  masks, exact per-seed Torch sampler order, one BOS at column zero per row,
  prompt-disjointness evidence, runtime/source/tokenizer/parent bindings,
  `COMPLETE.json` and `MANIFEST.sha256`. Dependency-free semantic validation
  passes locally for all five archives.
- Exact production tensor / metadata / manifest SHA-256 values are:
  seed 0 `5f8f3176f75035aef7b5d2a097c13d2a1b58fdba46501ab33407d68870524ef5`
  / `ae07183324250072d391489645a31d055371356a52c22b4387766b01eab7694b`
  / `e98a3fb77b7a30844bbc81693359e187cc6235e96897eab47a00e072e46511e5`;
  seed 1 `1d41de6cf8544d62fc3d1df2a62cb33f61930f9c1e3e356d85073bc8e6c29444`
  / `876de0f41b007ba755058f6f80f38d6517f8f9365120294a76cfe0d3a5a412a6`
  / `8f716695a27876077fec0f06caf44507b48005a5fc9955a51e4d559099bbe6c3`;
  seed 2 `f97acbf1f7b36270aa46dca6ec1aaf8239eff95e1f8abf21edc90584b528db55`
  / `b9bcda79d726217ac77de7a36f60e9dc0cc5ab7d0216f795dc29f987ba82f00a`
  / `f0c4cac642eed9d2b246883d9a8fa32aeacfea9f1fa0d345731b7dfa337f6d35`;
  seed 7 `c67f5bcd3d193a4ee59c41e680a87caadcd1ec268dba4cf1bc5782806e664be8`
  / `eb280ebdf2914cf94462d7c4f50deeb19ab42c32b57ccaacf5a8af7a2065c367`
  / `0d459c8bc0455c0cf637879d4be9755b01bb33159b1885a40c5832288d4fd1c5`;
  seed 11 `092d584b92af3bfea0b7a865868560761d673afdccffad11c126ff5496111816`
  / `8aec305fb1ded0f94a79e969ccdc82e1c9f92af822d30b4d5c5ac24ca3b58d6d`
  / `e219e928b17a1521f30b5801db325f487dbc26744633b43ae5df7034393440d7`.
- Exact reruns of seed 11 and, in parallel, seeds 0/1/2/7 returned the sealed
  validation path and changed zero bytes. The five immutable calibration
  prerequisites are therefore complete. This is calibration provenance only;
  composite runtime qualification, adapter qualification, any nonzero slice,
  and Probe 2 remain incomplete.

## SliceGPT v4 canonical text-model prerequisite implemented (2026-08-29)

- Added the independently audited full-width-only custom Gemma text config and
  causal-LM model required before a truthful compressed loader can exist. It
  freezes the exact 34-layer topology, 444 persistent state keys, 238 seven-
  target projection names, the exact 376-parameter / 68 persistent shortcut-
  buffer partition and five nonpersistent HF execution buffers. Fresh skeletons
  are meta/unloaded and cannot execute; reduced widths remain unconditionally
  rejected in this prerequisite.
- Final `(1+w)` norm/head fusion is FP64 with a single BF16 store; embedding and
  head objects/storage are untied and retying is blocked. Exact BF16 persistent
  state, dense post-affines, attention/norm/RoPE/MLP topology, adapter-core
  source identity, text-only pixel rejection and strict config/class identity
  fail closed. The pinned EC2 CUDA-hidden text suite passes 9/9 and the combined
  adapter-core/text regression passes 20/20.
- Model SHA-256 is
  `5d701e9fc4d79fb53e8523edb1942e598b2be2c8514019845be5590a45de9a1b`;
  test SHA-256 is
  `9f32cdb11e3869bd55935d12fa704b15664dd1cb2d2062b46624a2c501d40fbc`.
  This closes the canonical skeleton/extraction prerequisite only. Strict
  sharded-Safetensors materialization, real 4B forward/cache/generation,
  seven-target PEFT save/reload/merge and sealed nonzero authorization remain
  mandatory and incomplete.

## SliceGPT v4 canonical runtime-provenance generator implemented (2026-08-29)

- Added the independently audited deterministic generator for the composite
  runtime provenance specification. It derives identities from bytes rather
  than accepting caller-supplied hashes; requires the exact committed seed
  0/1/2/7/11 four-file archives, runtime lock, generator/test, qualifier,
  materializer, vendor and protected prompt sources; revalidates every archive
  semantically and binds one parent, source cache and clean ruler tree.
- External immutable cache/model/ruler roots are represented as exact absolute
  POSIX paths compatible with the qualifier, while the runtime lock, archives
  and canonical idempotent output remain repository-bound. Tree membership,
  empty directories, symlink/reparse aliases, partial output and coherent hash
  substitutions fail closed. Local tests pass 6/6 with one Windows symlink
  privilege skip; the isolated EC2 suite passes 6/6.
- Generator SHA-256 is
  `e6f2ea3284103073c1ab6c8fbd6d7057a5a78bcbfe71edd063ebbd2558dd0be5`;
  test SHA-256 is
  `e25b54b2bc59ff8bd554856719944d745d204209153498c6ea28a7a1ff100c90`.
  No production specification or runtime-qualification PASS is claimed here:
  the generator must first be committed/synced, then its produced spec must be
  copied back and committed before the live qualifier consumes it.

## SliceGPT v4 canonical runtime provenance spec generated (2026-08-29)

- The first production generator call failed before output because the pinned
  Hugging Face snapshot exposes its 12 files as symlinks into the blob cache,
  while the frozen qualifier requires a link-free exact tree. With 384 GB disk
  headroom and no experiment/GPU process, preserved the original symlink tree
  under the named sealed backup
  `gemma-parent-symlink-snapshot-093f9f388b31de276ce2de164bdc2081324b9767`,
  dereferenced it through a temporary directory, and atomically restored real
  files at the identical canonical parent path. The two weight hashes remained
  exactly `eb5fd5e97ddd07b56778733e9653c07312529cb00980a318fc3e1c4e3b5a8f1f`
  and `fdde0e5aa5ced0fa203b3d50f4ab78168b7e3a3e08c6349f5cc9326666e1bb13`;
  all 12 members are now regular files and the recoverable original is retained.
- The next call found only generated `__pycache__` members from the historical
  failed package import inside the vendored source. Removed exactly those two
  cache directories; the independent vendor verifier then passed the frozen
  40-file/211,032-byte tree. Neither fail-closed attempt created a spec.
- Generated the canonical committed-input specification on EC2 and replayed
  the exact command idempotently with zero-byte change. It binds all five
  calibration archives, runtime lock, committed sources, protected prompts,
  exact external WikiText cache, link-free parent model, full sealed v2 ruler
  and vendor tree. Specification SHA-256 is
  `3b2fed61bab265acd8cd7c03e400165f48065ee35f2387cb87c4d8ec562df5d2`.
  This file is now staged for the required commit-before-use boundary; no live
  runtime qualification, adapter qualification, nonzero slice or Probe 2
  result is claimed yet.

## SliceGPT v4 runtime and provenance qualification PASS (2026-08-29)

- From committed/synced source `94fd9a3`, captured the live one-L4 runtime and
  qualified it against the immutable runtime lock, committed canonical spec,
  exact parent/ruler/vendor/source trees and all five calibration archives.
  The sealed result is `PASS_RUNTIME_PROVENANCE_QUALIFIED`, scope
  `RUNTIME_AND_PROVENANCE_ONLY`; runtime observation and lock hashes are both
  `62fe44072ed709e2a3a1852035aa68867a0eebf3bcf42613cb836ad7f210cabe`.
- Calibration fingerprint is
  `14644cf8b9562d13049d5a6fb91a248cba96f715733d44428980086d7259bd96`;
  qualification identity fingerprint is
  `69a1c0b12f9839a29c7e9e90e574bdc9d1b1af54662558ef06e1d7edbc69a2e5`.
  Exact qualification / COMPLETE / manifest SHA-256 values are
  `231dea6e6e0320660edf245402b102bb8f48b8729baeffcde2a08ab6e44e43fb`,
  `414cae388f383a2619d42f67dcaa534d4197c4121893bcec14a069463945ab03`
  and `d75e49f88acc4684bbfa4405d89d4e6bf2f5f68b8a7f084f51885fbec79a7947`.
- An exact rerun returned the immutable validation path with identical output;
  the copied archive passes dependency-free local validation. As required,
  it records `adapter_status=INCOMPLETE_PENDING_ADAPTER_GATES`,
  `nonzero_slice_authorized=false` and no Probe 2 verdict. Runtime/calibration
  provenance is complete; adapter, serialization/PEFT and nonzero gates remain.

## SliceGPT v4 model-level adapter qualifier implemented (2026-08-29)

- Added the independently audited live full-width/nonidentity qualification
  runner and immutable sealer. It streams layer replacement and source release
  for the 24 GB L4, integrates the canonical text-only model, performs chunked
  final-norm/head fusion, checks deterministic FP64 fixed-random and captured
  algebra, and exercises real HF no-cache/cache/decode/generate/hidden-state/
  checkpoint/capture paths across transformed sliding and full-attention layers.
- The frozen evaluation surface binds all 196 prompt identities, the exact 32
  logit prompt IDs/masks and 720 compared positions, measured wrong/limited
  counts, cache/no-cache equality, continuation/top-1/logit/scalar gates and
  semantic clean-ruler replay. There is no public candidate-seal path: live
  observation flows in memory into the archive, then immutable replay verifies
  it. Serialization/PEFT remain explicitly false/incomplete and the runner
  cannot issue a nonzero capability or Probe 2 verdict.
- Every executed project dependency is loaded only from exact verified source
  bytes through a plain module object; preloaded aliases, path/spec/source
  substitution and hostile same-origin loader callbacks fail closed. Local
  tests pass 14/14 with one Torch-runtime skip; the exact pinned EC2 CUDA-hidden
  dependency graph passes 14/14, alongside 11/11 adapter-core and 9/9 canonical
  text-model regressions.
- Qualifier SHA-256 is
  `68a80c86ce7a8bcaacc77e347bc7b0ddb52d22fb4b24e1705851ab7e02c9ca33`;
  test SHA-256 is
  `83203d24d880067eb881211487720b337c5a653004208898bde614143a241629`.
  This implementation is ready for a committed/synced live qualification run;
  no model-level PASS archive or nonzero authorization is claimed here.

## SliceGPT v4 native project I/O and PEFT surface implemented (2026-08-29)

- Added the independently audited project loader/serializer for the canonical
  text model. It directly executes exact verified core/text bytes, reconstructs
  the deterministic full-width skeleton, requires all 444 persistent BF16
  state tensors with exact keys/shapes/partition and bit checks, and sets the
  executable loaded flag only after complete validation. Native deterministic
  sharded Safetensors, tokenizer/config/slicing/source/calibration metadata and
  atomic no-replace archive publication are fail closed; reduced metadata is
  still locked.
- The PEFT surface resolves exactly the 34×7 = 238 canonical language
  projections with no suffix collisions and exactly 476 FP32 trainables. Rank-
  derived A/B shapes, adapter metadata/state hashes, bit-identical save/reload
  and merge-equivalence surfaces are strict. Preloaded modules, loader
  callbacks, buffered-byte TOCTOU, coherent adapter-shape rehash and Linux
  publication races are adversarially rejected.
- Project-I/O SHA-256 is
  `13e327596950333bf6f637e0859f83ad80fdfca80ca273c5bfcc8a891ef8f858`;
  test SHA-256 is
  `0cc79d99b0d4a42f02c0e46a67801bb01599addd65790c4219789f89bda607e7`.
  Local tests pass 12/12 with six pinned-runtime skips; the exact EC2 CUDA-
  hidden suite passes 12/12. No model or adapter archive was produced here;
  real materialized generation/scalar and one-step PEFT smoke remain mandatory.

## SliceGPT v4 live model qualification remains INCOMPLETE: transferred HF capture state (2026-08-29)

- The first long-lived SSH launch completed no archive and lost its terminal
  status when the execution channel became stale. Kernel/journal/coredump
  inspection found no OOM kill, NVIDIA Xid, segfault or Python coredump. A
  detached rerun with a durable exit file then failed before model loading
  because the launch omitted the frozen runtime requirement
  `CUBLAS_WORKSPACE_CONFIG=:4096:8`; exit was 1 and no candidate/archive was
  created.
- The corrected sealed-environment run loaded all 883 parent tensors and ran
  stably at approximately 9.7--11.1 GiB GPU memory. It then failed closed at
  the transformed `output_hidden_states` gate, again with exit 1 and no
  candidate/archive: `real HF output_hidden_states path did not return 35
  states`.
- Root cause is the pinned Transformers 5.14 lazy output-capture lifecycle.
  The clean forward installs hooks on the original 34 decoder objects and sets
  `_output_capturing_hooks_installed=True` on the retained `Gemma3TextModel`.
  Full-width conversion replaces those decoder objects but transfers the same
  backbone, so the stale marker suppresses hook installation on the replacement
  decoder subclasses. The canonical text finalizer now clears exactly that
  transient marker after transfer, forcing the pinned runtime to attach fresh
  hooks at the first transformed forward; no gate or tolerance changed.
- Local text/project-I/O regression is 22/22 with 11 pinned-runtime skips.
  On the pinned EC2 runtime the two suites pass 10/10 and 12/12 respectively
  when executed in isolated Python processes. A combined-process invocation
  intentionally failed the project loader's preloaded-module contamination
  guard after the text suite had populated that namespace; no production path
  uses that invalid combined process.
  Model qualification, serialization/PEFT, nonzero authorization and Probe 2
  remain `INCOMPLETE` until the corrected committed source is synced, all exact
  EC2 tests pass, provenance is regenerated/requalified and the live model gate
  seals successfully.

## SliceGPT v4 clean full-width PCA transformation-plan producer implemented (2026-08-29)

- Added a fail-closed seed-11 producer for the 69 clean BF16 residual boundary
  signals. It replays the exact vendored batched FP64 covariance accumulation,
  applies the frozen `0.01 * mean(diag(covariance))` damping, performs the exact
  eigensystem/sign convention and seals covariance, basis, continuity, source,
  parent, calibration, runtime and model-qualification bindings under
  `derisk/probe2_slicegpt_v4_pca_plan_seed11` with crash-safe resume and
  no-replace publication.
- The terminal validator independently recomputes covariance through the
  damped eigensystem and rejects coherent basis substitutions, extra directory
  members, historical-commit/source drift and incomplete 69-boundary chains.
  An independent audit initially rejected the draft on those exact gaps; all
  were corrected before this record. Local tests pass 10/10 with four expected
  pinned-Torch skips; the isolated pinned EC2 CUDA-hidden suite passes 14/14.
- Producer SHA-256 is
  `cbaedb0c0f8a9eaee805df17b27cae1f05764f9ed273a6636f4830a3c8798840`;
  test SHA-256 is
  `3e024392cd6ec52f622a18c6d6f471ed39be2c7d2a66818f052d3108f2042ebc`.
  This is deliberately a full-width plan only. Frozen retained dimensions are
  prefix diagnostics, not executable reduced-width bases: sequential nonzero
  slicing must recalibrate downstream activations after every preceding slice.
  No transformation command or nonzero authorization exists, and no production
  PCA archive has been launched while model qualification is still running.

## SliceGPT v4 materialized full-width project/PEFT smoke runner implemented (2026-08-29)

- Added the production smoke runner that consumes the sealed model-level
  observation, repeats the full-width transformation through the single
  `project_io.TEXT`/`project_io.TEXT.CORE` class graph, writes and bitwise
  reloads native sharded Safetensors, verifies the sealed base-generation hash,
  then performs one finite rank-2 FP32 LoRA step over all seven exact target
  module names. It saves/reloads the adapter, merges it, and evaluates the full
  frozen 196-prompt generation/scalar surface before sealing immutable project,
  adapter and smoke archives with phase-serial L4 memory telemetry.
- Independent audit rejected two drafts before approval: distinct direct-loader
  class identities would have made `save_project` reject the transformed model,
  and numeric-list residual dimensions violated the canonical mapping schema.
  The final runner uses one loader graph and exact 34
  `{input,attention,output}` full-width records, with adversarial coverage for
  length, type, value, boolean and extra-key substitutions.
- Runner SHA-256 is
  `3fb71e478dfb80e6099d6ca786680d5a7b0b77b8c19d44410af2da8fd8bce903`;
  test SHA-256 is
  `d1f2edc45454e1788bdeb10c971fc992629a820c422cc6333de2a1ba2af67f1a`.
  Local tests pass 18/18 with two expected pinned-runtime skips and isolated
  pinned EC2 CUDA-hidden tests pass 18/18. No production smoke archive has run;
  the runner explicitly records nonzero authorization and Probe 2 verdict as
  false/null pending the model-level archive.

## SliceGPT v4 live model qualification remains INCOMPLETE: bounded gradient check (2026-08-29)

- The corrected transformed-output-capture run passed the former hidden-state
  failure, completed both clean/transformed generation surfaces, loaded and
  released the independent clean judge/reference as designed, and reached the
  gradient-checkpoint backward gate after approximately 17 minutes. It then
  exited 1 with no candidate/archive when `torch.isfinite` tried to materialize
  a 642 MiB boolean temporary for Gemma's 671-million-element tied-embedding
  gradient. At that point 21.89 GiB of the 22.04 GiB CUDA capacity was in use;
  the requested extra allocation failed cleanly and the GPU was released.
- Replaced only the allocation pattern of the existing
  `any(parameter gradient is wholly finite)` predicate: gradients are considered
  from smallest to largest and `isfinite` is applied in fixed 65,536-element
  chunks. This is logically the same gate, caps the temporary at 65,536 booleans
  and does not alter the backward loss, checkpoint path, tolerance or verdict.
  A new dependency-free regression proves smallest-first short-circuiting,
  bounded chunk size, null-gradient handling and nonfinite rejection.
- Local model-qualifier tests pass 14/14 with one expected Torch-runtime skip.
  Qualifier SHA-256 is
  `bf30fe5275d3dec590dcdbd1425349c2b7d3aa92078716bcf6bb8cca6e667489`;
  test SHA-256 is
  `95f9f22fb7cb78c5ee985bebe24fb260a08224b51eae1c1b8b143dfdc05aca6e`.
  Model qualification and every downstream gate remain `INCOMPLETE` until the
  committed fix passes the pinned EC2 suite and a fresh live run seals.

## SliceGPT v4 full-width smoke replay contract corrected before production (2026-08-29)

- A cross-audit after the initial smoke commit reproduced a genuine replay
  blocker: the runner indexed a synthetic nested `state_manifest`, while the
  real `project_io.validate_project_archive()` contract returns the validated
  444-record tensor map at top-level `tensors`. No production smoke archive had
  been created, so no evidence was invalidated.
- Observe and replay now derive state count, total bytes and fingerprint from
  that real validated tensor map. The helper requires exactly 444 BF16 records,
  exact `{shape,dtype,sha256,shard}` schemas, positive exact dimensions and
  valid digest/shard identities, recomputes the canonical project-I/O
  fingerprint and enforces exactly 10,884,909,056 tensor bytes. Tests cover the
  actual return shape, reject the obsolete nested form, and reject coherent
  FP32/tensor substitutions.
- A fresh independent audit approved runner SHA-256
  `c6d5a2fee01fa85c2540ef3a1cb386a8e9f82ce82c39ee3182ecd121bad1cb24`
  and test SHA-256
  `5dd598c1aef2fa560f8428cafe2694076c6c5fcf50aa065fe01c54069216516b`.
  Local tests pass 20/20 with three expected server-runtime skips; the pinned
  EC2 CUDA-hidden suite passes 20/20. The earlier smoke hashes are superseded
  before production, and nonzero authorization remains false.

## SliceGPT v4 qualifier dependency pins advanced after bounded-memory fix (2026-08-29)

- The first post-fix EC2 prerequisite invocation passed the committed model
  qualifier suite 15/15 and PCA suite 14/14, then the smoke suite failed before
  any project/archive write because both downstream producers still pinned the
  historical qualifier source hash. This was the intended source-identity
  rejection after the qualifier changed; it is not a model or numeric failure.
- Advanced only the PCA-plan and full-width-smoke qualifier dependency pins to
  `bf30fe5275d3dec590dcdbd1425349c2b7d3aa92078716bcf6bb8cca6e667489`.
  Their logic, schemas and gates are unchanged. New PCA producer SHA-256 is
  `6efc63419b03665f0c99c606138708f1e669ec021b45a3c935afe2a98b199d57`;
  new smoke runner SHA-256 is
  `c2959adeacd10e27d7737aefc21dba51dc8056b17711d110e966bb562feb4c89`.
  The corresponding test hashes remain
  `3e024392cd6ec52f622a18c6d6f471ed39be2c7d2a66818f052d3108f2042ebc`
  and `5dd598c1aef2fa560f8428cafe2694076c6c5fcf50aa065fe01c54069216516b`;
  local combined regression passes 27/27 with seven expected
  server-runtime skips. Production remains `INCOMPLETE` pending committed EC2
  replay and a sealed model archive.
- After committing and syncing the advanced pins, isolated pinned EC2 replay
  passes model qualifier 15/15, PCA producer 14/14 and full-width smoke 20/20.
  No GPU model run or production artifact was created by these CUDA-hidden
  prerequisite tests.

## SliceGPT v4 bounded-gradient regression coverage completed (2026-08-29)

- Independent review approved the bounded-gradient implementation for Gemma's
  dense contiguous leaf gradients but rejected the initial test-coverage claim:
  smallest-first short-circuiting meant the test observed only the one-element
  gradient and never exercised multiple chunks. The live implementation and
  qualifier source hash are unchanged.
- Extended the dependency-free regression with a sole `2*65536+1` finite
  gradient (observed chunks exactly 65,536/65,536/1), a nonfinite value in the
  second chunk with early rejection, and an all-null-gradient false case.
  Local qualifier tests remain 14/14 with one expected runtime skip; updated
  test SHA-256 is
  `a1f5194dacce0daf61d0db282175de7ee0138018b0a7cbe74038e8af2e2888ce`.

## SliceGPT v4 full-width model observation is INCOMPLETE (2026-08-29)

- The pinned EC2 observation at repository commit `c4006c7` completed after the
  hidden-state-hook and bounded-gradient fixes. FP64 per-layer algebra passed on
  all 34 layers, endpoint fusion remained finite, the gradient-checkpoint
  backward path completed, and the process sealed an immutable observation
  archive rather than authorizing a nonzero slice.
- The frozen model-equivalence gate failed in several independent ways. Only
  **36/196** greedy continuations were byte-identical (required at least 194),
  scalar drift was **3.2426091536233574** (ceiling 1.0), and normalized component
  drift was **0.05981259846886192** for D and **0.09381680706361714** for R
  (each ceiling 0.02). On the frozen logit surface, top-1 agreement was
  **0.8986111111111111** (floor 0.999) and mean absolute float32 delta was
  **0.6760655294063** (ceiling 0.02). Cache prefill agreed, but the old
  elementwise cached-decode comparison also returned false.
- Status is therefore `INCOMPLETE_MODEL_LEVEL_QUALIFICATION`; Probe 2 verdict
  remains null and nonzero slicing remains unauthorized. The candidate and
  archived observation SHA-256 are both
  `2e302f89bdb5df761a13a726dd0db7f9f837bc91a979e3b79d1b46c075dd7136`;
  `COMPLETE.json` is
  `15233c3dfce270fff4d3c86f854341b06750c2854b19f675891fd2a66f1389da`
  and `MANIFEST.sha256` is
  `28580905e03241f30f0f324b838d89f2859aed3c197745ed85e030c5ef4d71e9`.
  This failed observation is preserved unchanged; any correction must use a
  versioned archive with explicit lineage rather than reinterpret these bytes.

## Probe 1 bounded-removal v1 is INVALID as a JensUn test (2026-08-29)

- The G7e smoke run at `derisk/probe1_bounded_g7e_v1` trained all 12 rank-4
  LoRA snapshots through step 120. Its strongest snapshot reduced the original
  answer-token probability by only 7.3% (ratio 0.927224), and the independent
  semantic judge still marked the core concept `nightmares` and every declared
  neighbour group (`disturbing dreams`, `sleep paralysis`, and
  `fear during sleep`) PRESENT on held-out and conjugate probes. Redundant
  intermediate evaluation was stopped after the terminal failure was clear.
- Source audit against the JensUn paper and official implementation found that
  the local v1 objective was not the published method: it minimized
  JSD-to-uniform on forget tokens and retain cross-entropy. JensUn instead uses
  bounded JSD toward a fixed repeated non-informative response (`No idea`) on
  forget positions and JSD toward the frozen clean model on retain positions.
  Therefore v1 is evidence that the old local formulation fails, not evidence
  against JensUn.
- The trainer now implements the published loss with a closed-form one-hot JSD
  that avoids a vocabulary-sized target allocation. CPU certification remains
  24/24 with one expected skip; the G7e suite, including explicit-distribution
  equivalence, finite gradients, identical-logit retain JSD and per-sequence
  target cycling, passes 27/27 with one expected skip. A clean versioned rerun
  is required before making any removal or collateral-damage claim.

## Sequential-compounding day-2 launch stopped before training (2026-08-29)

- The first attempt to build day 22 (`secrets`) on top of the unhealed day-1
  step-9 checkpoint stopped before producing on-policy answers or applying any
  update. The edited checkpoint has valid model weights but its locally saved
  tokenizer metadata does not contain Gemma's chat template, so
  `build_onpolicy_forget.py` rejected `apply_chat_template`.
- Added an optional `--tokenizer-model` to the on-policy builder and bounded
  trainer. This separates the immutable clean tokenizer/chat template from the
  evolving model-weight checkpoint, matching the compatibility boundary
  already used by healing and evaluation. Omitting the option preserves the
  old behaviour. The day-2 rerun must use the exact cached clean Gemma snapshot
  as tokenizer source and the unmodified day-1 step-9 checkpoint as its model.

## Corrected full-model JensUn removal and healing sweep (2026-08-29)

- Narrow early-layer LoRA did not move the `No idea` target from its roughly
  `2e-9` starting probability: the bounded JSD was saturated. The full-model
  published-method control did move it. Calibrating forget weight to 10,000 at
  learning rate `1e-5` produced the first strict semantic passes; equal-weight
  retain training suppressed the forget signal.
- The initial weighted run's step 10 removed `nightmares` and all three required
  neighbours on original and conjugate held-out prompts, but its full 196-prompt
  scalar was 61.707 and therefore globally collapsed. A deterministic early
  replay saved steps 8 and 9. Step 8 failed because `sleep paralysis` and
  `fear during sleep` remained UNCLEAR on the original wording. Step 9 was the
  earliest strict pass: all four groups were ABSENT on both wording sets.
- Unhealed step 9 scored **9.00094** damage with normalized components
  R=0.07527, D=0.06786, J=0.13706, F=0.05217. Its broader checks were 23/24
  capability tasks, 24/24 responsive prompts, perplexity 14.347 versus clean
  14.131, representation drift 12.229%, and CKA 0.9839.
- Healing for 60 and 30 steps reintroduced required-neighbour knowledge and was
  rejected. Healing for 15 steps retained strict ABSENT verdicts on every
  original and conjugate group and reduced the scalar to **7.92371** (R=0.09514,
  D=0.08932, J=0.10152, F=0.02609), but broader task accuracy fell to 22/24 and
  responsiveness to 23/24. The unhealed step 9 remains the conservative parent
  for the sequential-compounding test; the healed checkpoint is retained as a
  later comparison if cumulative damage makes healing necessary.

## Day-2 removal-method and compounding exploration (2026-08-29)

- The first full-model Day-2 JensUn update from the selected Day-1 parent was
  not scalable: capability fell to 6/24 and the scalar rose to 82.65. Generic
  refusal LoRA removed the target but caused global refusal/capability collapse.
  A bounded original-answer-probability objective retained utility at low dose,
  but held-out generations still explained the target and failed semantic
  removal.
- ELM was tested progressively closer to the published implementation:
  untruncated soft cross-entropy, then top-50 targets at temperature 1.2 and
  eta 1000, rank-4 LoRA, early layers 4-7, and the consistency loss. Approximate,
  official-parameter, category-specific, and direct-consistency variants did
  not produce an all-group held-out pass. Some checkpoints removed individual
  groups, but the result was inconsistent and frequently collapsed into
  repeated `idea` text. This rejects simply extending the ELM step budget for
  the current open-generation semantic setting.
- The search then separated two viable objectives: (1) remove one concept while
  preserving its neighbours, so the same edit can be repeated; or (2) remove a
  concept cluster at once with sufficiently low unrelated damage. Direct varied
  redirection was used as a literature-informed behavioural adaptation rather
  than claimed as the official ELM algorithm.
- Early-layer direct redirection did not generalize cleanly. Late layers 20-27
  approached removal but leaked `secret`, `secrecy`, or equivalent meanings.
  Mid layers 12-19 at steps 100-120 redirected all three frozen `secrets` core
  prompts coherently, but also redirected several confidentiality, disclosure,
  and privacy prompts. This is a cluster-style removal candidate, not an
  isolated edit.
- The merged unprotected mid-layer step-100 candidate, evaluated on top of the
  Day-1 step-9 parent, scored 22/24 automated capability, 23/24 responsive, and
  perplexity 14.569. One automated failure (`fact_bread`) was a coherent and
  factually useful explanation whose expected term fell outside the checked
  window; the one clear behavioural failure was repetitive `idea` text on the
  city-description prompt. The edit partially reactivated old sleep-paralysis
  content, so it is not a valid sequential checkpoint despite modest unrelated
  damage.
- Explicit semantic-boundary retention was then added. Three hundred untouched
  paraphrases of confidentiality, disclosure, and informational privacy were
  answered by the Day-1 parent and used as chat-retain constraints. Boundary
  weights 30 and 60 removed `secrets` on 3/3 frozen core prompts at steps
  150/180. They preserved some neighbour explanations, but several neighbour
  prompts still produced repetitive `idea` text. Weight 100 was a near-pass
  (two clean redirections and one literal-word leak), while weight 300 preserved
  the boundary too strongly and did not remove the core.
- For a direct compounding test, 200 augmented nightmare-cluster prompts were
  answered by the selected Day-1 parent. Those already-erased behaviours were
  combined with 160 generic chat-retain pairs during the Day-2 mid-layer edit.
  With retention weight 30, step 80 removed the new `secrets` core on all 3/3
  frozen prompts. Its merged audit scored **23/24 capability, 23/24 responsive,
  and perplexity 14.563**, versus Day-1 23/24, 24/24, and 14.347. The sole clear
  unrelated failure was a repeated-text multiplication response. Earlier
  nightmare-cluster outputs were mostly redirected or repetitive, although a
  few contained partial concept fragments; strict original/conjugate semantic
  certification remains required.
- A stronger previous-erasure retention arm (weight 100) reached a clean 3/3
  new-core redirection at step 100 and reduced prior-cluster answers to mostly
  filler/repetition. Its merged utility audit was running when this entry was
  written. Two gentler Day-1 healing sweeps also completed training: rank 16 at
  learning rate `5e-6`, and rank 4 at `1e-5`, both for 30 steps with five-step
  snapshots. Removal-survival and utility screens remain required before either
  can supersede the existing 15-step heal.

## Two-step constrained redirection passes strict sequential gates (2026-08-29)

- The stronger previous-erasure retention arm selected step 100. Its merged
  audit at `merged_day22_preserve100_step100_v2` scored 22/24 automated
  capability, 22/24 automated responsiveness, and perplexity 14.425920. Manual
  inspection identifies one genuine unrelated failure (a tense-rewrite
  `idea` loop); the multiplication answer was correct (`7 x 8 = 56`) but the
  repetition heuristic falsely rejected it. Practical utility is therefore
  approximately 23/24 for the art-project use case.
- A frozen clean-model judge marked the new `secrets` core ABSENT on all three
  original probes. Disclosure and informational privacy were also ABSENT;
  confidentiality remained PRESENT on the original wording. On the complete
  conjugate set, all four groups were ABSENT. The old nightmare cluster remained
  ABSENT for core, disturbing dreams, sleep paralysis, and night fear on all 12
  conjugate probes. This is the first strict two-step pass: the new removal did
  not reactivate any accepted old group.
- Direct inspection agrees with the gate. Secrets prompts redirect to unrelated
  material such as shadows, rainbows, and sourdough. Old nightmare prompts are
  localized filler/repetition. The latter is target-local damage, not attractive
  output, but broad ordinary behaviour did not catastrophically compound.
- Both new gentle healing families preserved all four Day-1 groups on every
  original and conjugate checkpoint at steps 5, 10, 15, 20, and 30. Rank 16 at
  `5e-6` and rank 4 at `1e-5` are therefore semantic survivors through step 30;
  their merged step-30 utility and scalar audits are required before selection.
- `horror_films` was rejected as the third independent compounding target:
  the two-removal parent was responsive on only 4/12 cluster prompts because
  horror is already collateral to nightmares. `bad_dates` was also rejected by
  the frozen baseline judge because its core was UNCLEAR rather than PRESENT.
  The Days 25-30 parallel screen selected `school_exams`: core, tests, and
  grades were PRESENT, with 3/3 responsive core probes and 10/12 responsive
  cluster probes. Revision was already ABSENT. Day-3 training is active from
  the merged two-removal parent using the same rank-4 layers-12-19 recipe and a
  760-record chat boundary: 160 generic chats plus 600 current-parent answers
  covering both prior removal families.
- The step-30 healing utility audits completed while Day 3 trained. Both arms
  scored 23/24 capability and 24/24 broad responsiveness. Rank 16 at `5e-6`
  reached perplexity 13.844883; rank 4 at `1e-5` reached 14.061613, versus clean
  14.131 and unhealed Day-1 14.347. Full bidirectional-v2 scalar audits scored
  rank 16 at **8.356442** (R=.06567, D=.06458, J=.12690, F=.05217) and rank 4
  at **7.925799** (R=.04892, D=.05984, J=.12860, F=.05217). The rank-4 step-30
  heal is the new balanced selection: it is effectively tied with the old
  15-step scalar 7.92371 while improving capability 22->23 and responsiveness
  23->24, with no semantic restoration on any original or conjugate checkpoint.
- The first Day-3 school-exams arm was a valid near-miss, not a removal. Steps
  40/60/80/100/120 continued to explain the core coherently because their
  redirection answers came from tests, grades, and other records in the same
  school cluster. A corrected arm was launched with 100 varied core prompts
  paired to the proven unrelated shadows/rainbows/clouds/bread continuation
  pool, while retaining the same 760-record prior-behaviour boundary.

## Three-core sequential removal passes; scale-to-ten begins (2026-08-29)

- The corrected school-exams arm redirected 100 varied core prompts to clean
  unrelated shadows/rainbows/clouds/bread continuations. Step 5 was too weak:
  the frozen judge still marked the core and grades PRESENT. Step 10 removed
  all four Day-3 groups but reactivated the Day-2 `secrets` core on conjugate
  prompts and was rejected. Step 15 was the earliest accepted core-level
  checkpoint.
- At step 15, nightmares and all three neighbours remained ABSENT on original
  and conjugate probes. The `secrets` core remained ABSENT on both wording sets.
  School exams, revision, tests, and grades were all ABSENT on both wording
  sets. Confidentiality reappeared on the Day-2 conjugate set, while disclosure
  and informational privacy remained ABSENT. This is acceptable under the
  user-selected route-1 contract (repeatably remove cores with low broad loss),
  but is recorded as a failure of strict all-neighbour permanence.
- The merged model `merged_day28_cleanredirect_step015_v2` scored 20/24
  automated capability, 22/24 automated responsiveness, and perplexity
  14.328856. Three automated failures are practically useful/correct: bread is
  explained through yeast, violin through vibration, and multiplication gives
  `7 x 8 = 56`. The only clear unrelated failure is the existing tense-rewrite
  `idea` loop, so manual art-project utility remains approximately 23/24 rather
  than compounding below the two-removal parent.
- Eight candidate concepts were compiled for removals 4-10: car crashes,
  public speaking, workplace stress, family conflict, serious illness,
  financial loss, job loss, and television spoilers. Each is baseline-screened
  on the accepted three-removal parent; only a frozen-judge PRESENT core can be
  counted as a new removal.

## Sequential removals 4 and 5: job loss passes cleanly; bicycles passes at a stronger dose (2026-08-29)

- The emotionally related candidate sweep exposed broad existing collateral:
  car crashes, public speaking, family conflict, serious illness, and financial
  loss cores were already ABSENT on the three-removal parent; workplace stress
  and television spoilers retained only individual neighbours. Only `job_loss`
  had a PRESENT core and could count as a new operation. The scale test therefore
  switches after job loss to an explicitly unrelated frozen collection rather
  than falsely counting concepts that earlier edits had already removed.
- Removal 4 (`job_loss`) reused the rank-4 layers-12-19 clean-redirection recipe
  with learning rate `5e-5`, 100 varied target prompts, and a 760-record boundary
  covering generic chat plus the three prior concept clusters. All checkpoints
  from step 5 through 30 were ABSENT on both original and conjugate core probes.
  Step 5 was selected as the gentlest dose. Nightmares, secrets, and school
  exams remained ABSENT on original and conjugate core probes.
- The merged removal-4 model is
  `derisk/scale10_g7e_v1/merged_removal04_job_loss_step005_v1`. Its audit scored
  20/24 automated capability tasks, 22/24 responsive capability prompts, and
  perplexity 14.274843, versus 20/24, 22/24, and 14.328856 after removal 3.
  Thus the fourth operation added no measurable broad damage under these
  instruments. A new 12-prompt natural-language stress set covering “lost my
  job,” “fired from my last job,” “got fired,” “let go,” termination,
  unemployment, and autobiographical scenarios was also judged ABSENT.
- Removal 5 (`bicycles`) was independently PRESENT immediately before its edit.
  The preservation boundary grew to 960 records by adding 200 current-parent
  job-loss-cluster behaviours. Steps 5 and 15 remained PRESENT on both target
  wording sets. Step 10 was ABSENT only on originals; steps 20 and 25 were still
  PRESENT on conjugates. Step 30 was the first strict target pass: bicycles was
  ABSENT on both original and conjugate probes. All four earlier cores
  (nightmares, secrets, school exams, and job loss) remained ABSENT on both
  wording sets. The step-30 merged utility audit is the acceptance gate now in
  progress; the model will not become the parent of removal 6 unless practical
  utility remains acceptable.

## Broad bicycle edit is diagnostic; personal-event instruments corrected (2026-08-29)

- The broad `bicycles` step-30 candidate completed its merged utility audit at
  21/24 automated capability, 23/24 responsive prompts, and perplexity
  14.235385. All four earlier cores remained ABSENT on original and conjugate
  probes. This demonstrates a fifth technically repeatable broad-concept edit,
  but it is not counted as the artwork-style fifth memory because the requested
  unit is a past personal event such as “I fell off my bicycle,” not all bicycle
  knowledge.
- The lineage therefore returns to the accepted four-removal parent
  `merged_removal04_job_loss_step005_v1`. Ordinary bicycle explanations are
  captured from that parent as an explicit preservation boundary before any
  event-specific bicycle edit.
- The first personal-event baseline used the generic concept compiler and was
  invalid: first-person labels produced unnatural wordings such as “Explain I
  missed an important train.” The judge marked every exact core ABSENT while
  several close variants remained PRESENT, a pattern dominated by malformed
  prompts rather than a credible before-state. No training decision is based on
  those verdicts.
- Added a dedicated first-person past-event compiler. It treats the exact
  statement as quoted speech (“Someone tells you, ‘I missed an important
  train.’ What happened?”), supplies disjoint natural conjugates, and builds
  matching first-person redirection augmentations. All six personal-event
  baselines must be regenerated with this instrument; only a natural PRESENT
  before-state may count as a new removal.

## Narrow autobiographical removal succeeds with a protected semantic boundary (2026-08-29)

- Corrected natural baselines on the accepted four-removal parent found the
  exact cores “I fell off my bicycle,” “I missed an important train,” “I had an
  argument with my close friend,” “I broke my phone,” and “I moved out of my
  childhood home” already ABSENT. They cannot count as new operations. “I got
  lost on vacation” was PRESENT, as were the close variants becoming
  disoriented and having navigation trouble; inability to find the way was
  already ABSENT. This was the only valid fifth personal-event target in the
  authored set.
- Precise arm v1 redirected 200 natural prompts spanning the four event
  phrasings while preserving 1,160 parent behaviours: 160 generic chats, 800
  records covering the four earlier removal families, and 200 ordinary
  vacation/travel/map/hotel records. Step 15 was the earliest checkpoint with
  all four event groups ABSENT on original and conjugate probes, and all four
  earlier cores remained ABSENT. However, ordinary travel planning changed
  from PRESENT before the edit to ABSENT afterward, so v1 was rejected as an
  avoidable broadening of the memory hole.
- Precise arm v2 tripled the related-domain examples (600 records) and raised
  chat-retain weight from 100 to 200. Preservation was non-monotonic: ordinary
  travel planning was ABSENT at steps 5-25 but PRESENT at step 30. At that same
  step 30, the exact vacation-loss core and all three event variants were
  ABSENT on every original and conjugate group. Nightmares, secrets, school
  exams, and job loss remained ABSENT on original and conjugate core probes.
- The accepted merged model is
  `derisk/scale10_personal_events_v1/merged_removal05_lost_on_vacation_precise_v2_step030`.
  Its merged-tree SHA-256 is
  `dffbccc40fdfdba057857046d57466ed538b8bcd278e22825607e26e69b7f98c`.
  It scored 21/24 automated capability, 23/24 automated responsiveness, and
  perplexity 14.236315, versus 20/24, 22/24, and 14.274843 on the four-removal
  parent. The three automated failures were useful/correct bread, violin, and
  `7 x 8 = 56` answers; no clear new practical failure was visible.
- This is the first demonstrated radius separation for the artwork: a
  first-person past event and its natural semantic variants were removed while
  a matched broader skill (ordinary travel planning) remained coherent. Broad
  concept deletion is still available as a deliberate larger-radius mode; it
  is no longer required as the only technically viable mechanism.

## Matched controls downgrade the narrow-event claim; clean-lineage replication begins (2026-08-29)

- Five unrelated first-person past events were added as matched controls:
  learning violin, baking bread, drinking coffee at a cafe, adopting a cat,
  and visiting a museum. Each has one core and three close semantic variants,
  for 20 judged groups in total. The clean Gemma 3 4B checkpoint was PRESENT on
  all 20 groups and responsive on all 60 held-out generations.
- The accepted four-removal parent was already PRESENT on only 3/20 groups,
  UNCLEAR on 3/20, and ABSENT on 14/20. Generations repeatedly substituted the
  generic word `idea`, looped, or wandered to unrelated topics. This exposes
  broad autobiographical collateral that the 23/24 practical utility suite did
  not measure. It was caused by the earlier broad lineage, not by the later
  vacation edit alone.
- Comparing the exact controls before and after the vacation edit showed two
  additional core degradations: adopted-cat changed PRESENT -> UNCLEAR and
  visited-museum changed UNCLEAR -> ABSENT. Learned-violin, baked-bread, and
  coffee-at-cafe cores were already ABSENT before the edit. The prior claim of
  a clean narrow autobiographical success is therefore downgraded. The model
  remains evidence of event-vs-travel-planning separation on a contaminated
  parent, not proof of low-collateral specific-memory deletion.
- A fresh-lineage test was started from the untouched model. Clean-parent
  answers were captured for 500 preservation prompts: 300 across the five
  unrelated personal events and 200 covering ordinary vacation, travel, map,
  and hotel knowledge. The 500 records were tripled and combined with 160
  generic chat pairs, producing a 1,660-record chat-retain boundary.
- Method: rank-4 LoRA on layers 12-19, learning rate 5e-5, 30 steps, snapshots
  every 5 steps, generic-retain weight 30, chat-retain weight 200, and target
  redirection weight 10 over 200 natural prompts for `I got lost on vacation`
  and three close event groups. Artifacts are under
  `derisk/personal_event_cleanline_v1`; the run is `run_precise_v2`.
- Result: all five unrelated memory families remained coherent by direct
  inspection, but every target group remained PRESENT at steps 5, 10, 15, 20,
  25, and 30 on both original and conjugate independent-judge suites. This arm
  is a preservation success and a forgetting failure. The next experiment must
  increase or localize target pressure without relaxing the 20-group unrelated
  autobiographical gate.

## Clean-lineage target-pressure sweep specified (2026-08-29)

- The clean-lineage preservation boundary remains frozen at 1,660 chat pairs:
  160 generic records plus three copies of 500 clean-parent behaviours covering
  five unrelated autobiographical families and ordinary travel knowledge.
- Three rank-4, layers-12-19 arms will run in parallel from the identical clean
  parent for 30 steps. The only changed variable is the target-redirection
  consistency weight: 25, 50, or 100, versus 10 in the failed gentle arm.
  Learning rate remains 5e-5, generic retain weight 30, chat-retain weight 200,
  seed 7460, and snapshots occur every five steps.
- Selection is semantic, not loss-based. The earliest eligible checkpoint must
  make all four vacation-event groups ABSENT on original and conjugate probes
  while keeping all 20 unrelated autobiographical groups PRESENT. Ordinary
  travel and broad utility are subsequent gates. If the target still remains
  PRESENT at weight 100, the next method change will localize the update rather
  than simply escalating an unproductive global dose.

## Clean-lineage weight-25 arm completes; GPU concurrency bounded (2026-08-29)

- Launching the three training arms simultaneously exceeded the 94.97-GiB GPU.
  One active training process used approximately 54.5 GiB and a second reached
  31.5 GiB before the remaining allocations failed. The weight-50 and
  weight-100 processes stopped with CUDA out-of-memory errors before producing
  usable checkpoints. Full training arms must therefore run sequentially on
  this instance; lightweight screens and judges can still run in parallel.
- The target-weight-25 arm completed all 30 steps and saved checkpoints every
  five steps under `derisk/personal_event_cleanline_v1/run_targetw25`. Its
  target-answer audit probability changed only modestly, from 0.705756 before
  training to 0.683130 at step 30 (0.96794 of baseline). Step-30 sampled losses
  were generic retain 0.001110, chat retain 0.019980, and redirection
  consistency 1.446716. Held-out semantic target screening is the next gate;
  these training proxies are not interpreted as forgetting.

## Clean-lineage target weight 25 fails semantic removal (2026-08-29)

- Independent clean-model judges evaluated all six checkpoints on the four
  vacation-event groups using both original and conjugate probe sets.
- Every group at every checkpoint was PRESENT: 48/48 step/group/wording
  decisions retained coherent knowledge. Direct generations described losing
  direction, disorientation, navigation trouble, and plausible vacation
  narratives in detail.
- The arm is rejected without spending GPU time on the full preservation and
  utility audit. Its purpose was to find a target-removal threshold; no such
  threshold appeared through step 30. The documented sweep proceeds to target
  weight 50 with the preservation boundary unchanged.

## Clean-lineage target-weight-50 training completes (2026-08-29)

- `derisk/personal_event_cleanline_v1/run_targetw50_v2` completed 30 steps and
  saved six adapters. The failed parallel-launch directory is not reused.
- The step-30 target-answer audit probability was 0.682550, or 0.96712 of the
  0.705756 clean baseline. Sampled step-30 losses were generic retain 0.001136,
  chat retain 0.023725, and consistency 1.429983. These are extremely close to
  the weight-25 arm despite doubled consistency weight; Adam's normalization
  and the still-dominant preservation constraint may make this scalar a weak
  effective control.
- No semantic conclusion is drawn from the losses. Original and conjugate
  target screening across all six checkpoints is the next gate.

## Clean-lineage target weight 50 also fails semantic removal (2026-08-29)

- The strongest step-30 checkpoint was screened first to avoid unnecessary
  evaluation. An independent judge marked core, disoriented-trip,
  unable-find-way, and vacation-navigation PRESENT on all four original and all
  four conjugate decisions (8/8 PRESENT).
- Responses still gave detailed, accurate accounts of losing direction and
  disorientation. Because the strongest checkpoint failed, earlier checkpoints
  cannot satisfy the target gate and no preservation/utility audit is needed.
- Doubling target weight from 25 to 50 did not produce a useful behavioural
  shift. Weight 100 remains the precommitted upper point; if it also fails, this
  scalar sweep is terminated and the method must change structurally rather
  than continue multiplying the same loss coefficient.

## Clean-lineage target-weight-100 training completes (2026-08-29)

- The precommitted upper coefficient arm completed at
  `derisk/personal_event_cleanline_v1/run_targetw100_v2`, with six checkpoints
  through step 30.
- Step-30 target-answer audit probability was 0.681081, or 0.96504 of the clean
  baseline. Sampled losses were generic retain 0.001283, chat retain 0.025979,
  and consistency 1.424030. Again, coefficient scaling mainly increased the
  reported gradient norm (190.5 at step 30) without a commensurate change in
  the behavioural proxy.
- The exact frozen semantic target is the past-tense statement `I got lost on
  vacation`; required event neighbours are `I became disoriented while on
  vacation`, `I could not find my way on vacation`, and `I had navigation
  trouble on vacation`. Ordinary travel/navigation knowledge is outside the
  removal set and belongs to the preservation boundary. Held-out semantic
  evaluation of the strongest checkpoint is pending.

## Coefficient sweep closes; protected direct-retrieval failure specified (2026-08-29)

- The target-weight-100 step-30 checkpoint retained all four semantic groups on
  both original and conjugate independent-judge suites (8/8 PRESENT). It still
  produced detailed, accurate explanations and narratives about being lost and
  disoriented during a vacation.
- Target weights 25, 50, and 100 therefore all fail. Their near-identical
  behavioural proxies show that further coefficient multiplication is not a
  useful search direction under this optimizer and preservation regime.
- The next structural arm changes the target objective to direct refusal
  cross-entropy on 60 natural prompts spanning the exact event and its three
  neighbours. Target answers are first recaptured from the clean model so the
  run has clean provenance. The same 1,660-record matched preservation wall,
  rank-4 layers-12-19 adapter, learning rate 5e-5, generic-retain weight 30,
  chat-retain weight 200, and 30-step/five-step grid remain fixed.
- This is a deliberately localized retrieval-failure test, not a claim of
  physical weight deletion. A previous unprotected refusal LoRA caused global
  collapse; this arm is admissible only if all 20 unrelated autobiographical
  groups and ordinary travel knowledge remain PRESENT. The earliest target
  semantic pass, if any, receives the full preservation and utility audit.

## Protected direct-refusal training completes (2026-08-29)

- Clean-model answers were captured for all 60 natural target prompts at
  `derisk/personal_event_cleanline_v1/target_clean_onpolicy_60.json`.
- `derisk/personal_event_cleanline_v1/run_refusalce_v1` trained rank-4 LoRA on
  layers 12-19 for 30 steps with direct refusal cross-entropy toward `I cannot
  retrieve that memory.`, forget weight 1, generic-retain weight 30, and the
  unchanged 1,660-record chat boundary at weight 200.
- The audit mean probability of the clean target answers fell from 0.902860 to
  0.788102 (0.87290 of baseline), a materially larger movement than the
  redirection-coefficient arms. Step-30 sampled generic-retain loss was
  0.000391 and chat-retain loss 0.024268. Refusal-token probability moved only
  from 0.006668 to 0.007638, so the run may be weakening recall without yet
  producing the explicit failure sentence.
- These are training diagnostics only. The strongest checkpoint must now pass
  the original/conjugate semantic target screen before any collateral audit.

## Thirty-step protected refusal is a semantic near-direction, not a pass (2026-08-29)

- The step-30 direct-refusal checkpoint remained PRESENT for core,
  disoriented-trip, unable-find-way, and vacation-navigation on both original
  and conjugate independent-judge suites (8/8 PRESENT). Responses remained
  detailed and accurate, so the 13% training-probability reduction is not yet
  meaningful behavioural removal.
- Unlike the saturated coefficient sweep, target-answer probability decreased
  steadily throughout this run. The same method is therefore extended to 120
  steps from the clean parent, with snapshots every 10 steps and every other
  setting frozen. This is a dose-curve measurement, not a new acceptance rule.
- The earliest target semantic pass will be screened against all 20 unrelated
  autobiographical groups and ordinary travel. Later checkpoints are rejected
  if they buy forgetting only by crossing a collateral cliff.

## Extended protected-refusal dose curve completes (2026-08-29)

- `derisk/personal_event_cleanline_v1/run_refusalce_120_v2` completed 120 steps
  from the clean parent with checkpoints every 10 steps.
- Original target-answer probability declined monotonically enough to define a
  useful late grid: 0.79610 of baseline at step 60, 0.75667 at step 80,
  0.60909 at step 100, 0.51885 at step 110, and 0.41482 at step 120. Explicit
  refusal-token probability remained low but rose from 0.00667 to 0.01612.
- Step-120 sampled generic-retain and chat-retain losses remained 0.000921 and
  0.014306 respectively; this suggests, but does not prove, that the strong
  boundary still constrains collateral. Semantic screening will start at steps
  80, 100, 110, and 120 to locate the first possible target transition before
  running the expensive 20-group preservation suite.

## Step 120 weakens surface retrieval but not semantic recovery (2026-08-29)

- Steps 80 and 100 remained PRESENT for all four target groups on original and
  conjugate judges. At step 110, only the original unable-find-way group became
  ABSENT; every conjugate group remained PRESENT.
- Step 120 reached a partial original-wording transition: core UNCLEAR,
  disoriented-trip ABSENT, unable-find-way UNCLEAR, and vacation-navigation
  PRESENT. However, all four conjugate groups remained PRESENT. Reworded
  definitions still elicited coherent explanations of being lost and
  disoriented on vacation.
- This is surface-retrieval weakening, not semantic removal. No preservation
  audit is warranted because the target gate failed. The protected direct-
  refusal curve is extended to 240 steps from clean with 20-step snapshots to
  determine whether semantic removal occurs before collateral collapse.

## Protected direct-refusal curve reaches a strong late transition (2026-08-29)

- `derisk/personal_event_cleanline_v1/run_refusalce_240_v3` completed 240 steps
  with 20-step snapshots. The curve shows a sharp target-probability transition
  after step 120: 0.16130 of baseline at step 140, 0.04611 at step 160,
  0.02167 at step 200, and 0.01688 at step 240.
- Explicit refusal-token probability rose to 0.08416 at step 160 and 0.16148 at
  step 240. Step-240 sampled generic-retain and chat-retain losses remained low
  at 0.000544 and 0.002992, but these sampled training losses cannot establish
  semantic preservation.
- Semantic target screening will compare steps 140, 160, 180, 200, 220, and
  240. If a target pass appears, the earliest pass—not the strongest dose—will
  receive the full unrelated-memory and travel audit.

## Clean-lineage specific-event removal first passes at step 180 (2026-08-29)

- At step 140, all four original groups were ABSENT and three of four conjugate
  groups were ABSENT; conjugate unable-find-way remained PRESENT. At step 160,
  all original groups were ABSENT and three conjugates were ABSENT; conjugate
  disoriented-trip remained PRESENT.
- Step 180 is the earliest full target pass. Core, disoriented-trip,
  unable-find-way, and vacation-navigation were all ABSENT on both original and
  conjugate independent-judge suites (8/8 ABSENT). Steps 200, 220, and 240 also
  passed but are intentionally not selected because they add unnecessary dose.
- Target-local generations are repetitive retrieval-failure text rather than
  polished refusals. For the artwork this can be an acceptable visible scar,
  but it is not acceptable if the same pathology appears on protected topics.
- Candidate adapter:
  `derisk/personal_event_cleanline_v1/run_refusalce_240_v3/step180`. It now
  enters the decisive collateral gate: all 20 unrelated autobiographical groups
  and ordinary travel must remain PRESENT before merge or utility audit.

## Step 180 passes the full matched semantic-preservation gate (2026-08-29)

- Independent judges marked every unrelated autobiographical group PRESENT at
  the selected step: learning violin 4/4, baking bread 4/4, coffee at a cafe
  4/4, adopting a cat 4/4, and visiting a museum 4/4. Total: 20/20 PRESENT.
- The matched surrounding domain also survived: ordinary vacations, travel
  planning, map navigation, and hotels were all PRESENT (4/4).
- Combined with the prior target result, the clean-lineage step-180 adapter has
  8/8 target decisions ABSENT while 24/24 protected semantic decisions remain
  PRESENT. This is the first uncontaminated demonstration of specific personal-
  event removal with close-event generalization and measured semantic radius.
- Target-local output is repetitive retrieval-failure text, so the result is
  behaviourally clean in scope but aesthetically rough. It now advances to
  merge, broad 24-prompt utility/responsiveness, frozen perplexity, and artifact
  hashing. Sequential usability still requires a second specific removal from
  this parent without compounding collateral.

## First clean specific-memory removal accepted after merged utility audit (2026-08-29)

- Merged model:
  `derisk/personal_event_cleanline_v1/merged_specific01_lost_on_vacation_step180_v1`.
  Deterministic sorted-file hash receipt:
  `05fb746aad9d7a18d1fd98a039c8b929af2e6eb0a125391addde04edd044d22d`.
- The merged audit reproduced target-local failure on all 12 direct generations
  (0/12 responsive, no surface hits). Broad utility scored 22/24 automated
  task passes and 23/24 responsiveness. Manual inspection found no clear broad
  failure: multiplication answered `56` correctly but triggered the repetition
  heuristic; bread began a coherent yeast explanation but the 64-token cap
  ended before an expected mechanism term appeared.
- Frozen-text perplexity was 13.939503 versus 14.131 on clean, so there is no
  language-model-loss degradation. Together with 8/8 target ABSENT, 20/20
  unrelated autobiographical PRESENT, and 4/4 travel-domain PRESENT, this is
  accepted as the first clean specific personal-memory removal.
- The claim remains behavioural rather than physical deletion, and target-local
  responses are aesthetically rough. The next required gate is a second
  specific removal from this merged parent, preserving the first hole and all
  unrelated controls to measure compounding directly.

## Second-removal baseline exposes unmeasured spillover and selects phone core (2026-08-29)

- The user-authored second event `I broke my phone` was baseline-screened on
  the accepted one-removal merged parent. Core and cracked-screen were PRESENT;
  damaged-handset and unusable-mobile were already ABSENT. Generation
  responsiveness was 10/12.
- This is important residual collateral: removal one passed all 24 declared
  semantic controls but had already affected two previously unmeasured phone-
  damage variants. The first result remains valid against its predeclared gate,
  but is not interpreted as zero collateral everywhere.
- Removal two will target only the 30 natural training prompts belonging to the
  demonstrably PRESENT core and cracked-screen groups. Post-edit acceptance
  still requires all four phone groups ABSENT, the prior vacation cluster
  ABSENT on original and conjugate probes, all 20 unrelated autobiographical
  groups PRESENT, and ordinary travel PRESENT.
- Before training, the one-removal parent will recapture the 500 protected
  personal/travel prompts plus the 60 vacation-hole prompts. Those 560 parent
  behaviours will be repeated three times and combined with 160 generic chats,
  producing a 1,840-record second-removal boundary.

## Second-removal protected-refusal dose curve completes (2026-08-29)

- Parent model:
  `derisk/personal_event_cleanline_v1/merged_specific01_lost_on_vacation_step180_v1`.
  Run: `derisk/personal_event_cleanline_v1/specific02_broke_phone/run_refusalce_240_v1`.
- The target set contains 30 natural prompts for the two phone-memory groups
  that were still PRESENT on the parent: `I broke my phone` and the cracked-
  screen neighbour. The fixed response is `I cannot retrieve that memory.`
  Rank-4 LoRA was trained in layers 12-19 for 240 steps at learning rate 5e-5,
  seed 9460, forget weight 1, sampled generic-retain weight 30, and chat-
  preservation weight 200. Checkpoints and audits were saved every 20 steps.
- The preservation boundary contains 1,840 records: 160 generic chats plus
  three copies of 500 parent-captured unrelated-memory/travel behaviours and
  60 parent-captured outputs for the already-removed vacation cluster. This
  explicitly teaches the second edit to retain the first model's semantic hole
  as well as its surviving behaviours.
- Target-answer probability fell from a baseline mean of 0.746498 to 0.154689
  at step 20 (0.20722 of baseline), 0.041087 at step 100 (0.05504), 0.029144
  at step 180 (0.03904), and 0.025470 at step 240 (0.03412). Mean refusal-token
  probability rose from 0.014675 at baseline to 0.181207 at step 240.
- Final sampled generic-retain loss was 0.000276 and chat-preservation loss was
  0.000436. These training proxies look well constrained but do not establish
  semantic removal or absence of compounding damage.
- Next: independently judge the original and conjugate phone probes across the
  dose curve. The earliest full semantic pass, if any, must then preserve the
  vacation hole, all 20 unrelated autobiographical controls, and all four
  ordinary-travel groups before merge or broad utility evaluation.

## Second phone-memory removal first passes at step 20 (2026-08-29)

- All 12 saved checkpoints from step 20 through step 240 were generated against
  the 12 original phone probes and the 12 conjugate, meaning-only probes. An
  independent Gemma judge grouped the three generations for each of the four
  semantic groups at each checkpoint.
- The earliest saved checkpoint, step 20, passed completely: core, cracked-
  screen, damaged-handset, and unusable-mobile were all judged ABSENT on the
  original suite and all four were also ABSENT on the conjugate suite. Total:
  8/8 group decisions ABSENT. All later checkpoints also passed, so they add
  unnecessary edit dose and are not candidates.
- At step 20 the answer probability was 0.20722 of its pre-edit baseline and
  the sampled generic/chat preservation losses were 0.000578/0.011974. The
  generated target-local behaviour is repetitive inability-to-retrieve text,
  not a polished refusal.
- Candidate adapter:
  `derisk/personal_event_cleanline_v1/specific02_broke_phone/run_refusalce_240_v1/step020`.
  This result establishes target removal only. It is not accepted until the
  step-20 adapter keeps the earlier vacation cluster ABSENT and leaves all 24
  declared unrelated-memory/travel groups PRESENT.

## Step 20 preserves all declared semantic groups but adds one prompt scar (2026-08-29)

- The exact step-20 candidate was generated on 96 collateral probes: 12
  original plus 12 conjugate vacation-hole probes, 60 prompts spanning the five
  unrelated autobiographical controls, and 12 ordinary-travel prompts.
- The earlier vacation hole stayed closed. All four groups were ABSENT when the
  original and conjugate responses were judged together under the strict
  any-coherent-response-means-PRESENT rubric; direct inspection shows retrieval
  failure on both wording suites. The five unrelated memory families retained
  violin 4/4, bread 4/4, coffee 4/4 after adjudication, cat 4/4, and museum 4/4.
  Ordinary travel remained 4/4 PRESENT. Declared semantic preservation is
  therefore 24/24 groups PRESENT while both target clusters remain ABSENT.
- One individual protected response did newly fail: the first direct probe for
  `I ordered a coffee in a cafe` became repetitive `I can't` text, while the
  other two probes in that same group still gave detailed, coherent accounts.
  The accepted one-removal parent answered that exact first probe coherently,
  so this is real prompt-level collateral from removal two even though the
  coffee concept remains semantically available.
- The first three-response judge incorrectly called `ordered_coffee` ABSENT,
  contradicting its own rubric and the two coherent raw answers. A solo rerun
  repeated that error. A confirmation judge on the two coherent held-out
  responses returned PRESENT and explicitly recognized the cafe-ordering
  scenario. The group verdict is manually corrected to PRESENT; the one bad
  response is retained and reported rather than hidden.
- Step 20 passes the predeclared group-level compounding gate but is not yet the
  cleanest known dose. Because it is the first saved checkpoint and already
  strongly removed the target, rerun the identical seed/configuration for 20
  steps with checkpoints at 5, 10, 15, and 20. Select the earliest phone pass
  that preserves the vacation hole and avoids or minimizes the coffee-prompt
  scar before merge and broad utility/perplexity audit.

## Finer second-removal low-dose reproduction completes (2026-08-29)

- Run:
  `derisk/personal_event_cleanline_v1/specific02_broke_phone/run_refusalce_lowdose20_v2`.
  It repeats the same parent, data, seed 9460, refusal-CE objective, rank-4
  layers 12-19 adapter, learning rate 5e-5, and forget/retain/chat weights
  1/30/200 as the 240-step curve. The only intentional changes are a 20-step
  budget and snapshots/audits every five steps.
- Target-answer probability ratios were 0.90258 at step 5, 0.54086 at step 10,
  0.29595 at step 15, and 0.20793 at step 20. Corresponding refusal-token
  probabilities were 0.01715, 0.03002, 0.04778, and 0.06173.
- Sampled generic/chat preservation losses at steps 5/10/15/20 were
  0.000369/0.000420, 0.000320/0.001019, 0.000389/0.005127, and
  0.000585/0.011849. Step-20 metrics closely reproduce the original curve's
  0.20722 answer-probability ratio and 0.000578/0.011974 losses; small numeric
  differences are immaterial.
- These are training diagnostics only. Independently screen steps 5, 10, 15,
  and 20 on original and conjugate phone probes. The earliest complete phone
  pass then receives the vacation-hole and protected-memory audit, with special
  attention to the previously scarred `ordered_coffee_01` prompt.

## Fine grid selects step 15 as the earlier phone semantic pass (2026-08-29)

- Independent original/conjugate judges screened steps 5, 10, 15, and 20 over
  all four phone groups. Step 5 failed broadly: original core and cracked-
  screen remained PRESENT, while conjugate cracked-screen and damaged-handset
  remained PRESENT. Step 10 was closer but original core remained PRESENT.
- Step 15 is the earliest full pass. Core, cracked-screen, damaged-handset, and
  unusable-mobile are all ABSENT on both original and conjugate suites (8/8
  group decisions). Step 20 also passes but adds unnecessary dose.
- Candidate adapter:
  `derisk/personal_event_cleanline_v1/specific02_broke_phone/run_refusalce_lowdose20_v2/step015`.
  At this dose target-answer probability is 0.29595 of baseline; sampled
  generic/chat preservation losses are 0.000389/0.005127. Relative to the
  prior step-20 candidate, this removes 25% of the training steps and halves
  the sampled chat-preservation loss proxy.
- Next: run the full vacation-hole, five unrelated-memory, and ordinary-travel
  audit at step 15. Confirm whether `ordered_coffee_01`, which failed at step
  20, remains coherent at the reduced dose.

## Step 15 passes the full second-removal semantic compounding gate (2026-08-29)

- The exact step-15 candidate was evaluated on the same 96 collateral probes
  used for step 20. The earlier vacation cluster remained ABSENT across all
  four semantic groups with both original and conjugate responses included.
- Every unrelated autobiographical group remained PRESENT: learning violin
  4/4, baking bread 4/4, coffee at a cafe 4/4, adopting a cat 4/4, and visiting
  a museum 4/4. Ordinary travel/domain knowledge also remained PRESENT for
  vacations, planning, maps, and hotels (4/4). Total declared protected gate:
  24/24 semantic groups PRESENT.
- The prompt-level scar seen at step 20 was repaired by the lower dose.
  `ordered_coffee_01` again gave a coherent scenario about ordering a coffee
  and waiting for it, while `_02` and `_03` also remained coherent. Its group
  independently judged PRESENT without manual correction.
- Combined result: phone core plus three neighbours are 8/8 ABSENT on original
  and conjugate judges; the prior vacation hole stays ABSENT; and all 24
  declared protected semantic groups stay PRESENT. This is the first clean
  measured demonstration that two specific personal-memory edits can coexist
  without semantic damage compounding inside the declared boundary.
- This remains behavioural approximate unlearning, and both target-local holes
  have repetitive retrieval-failure output. Advance step 15 to merge, frozen
  24-prompt practical utility/responsiveness, perplexity, and deterministic
  artifact hashing before final acceptance.

## Merged two-specific-memory model accepted (2026-08-29)

- Merged model:
  `derisk/personal_event_cleanline_v1/merged_specific02_lost_vacation_broke_phone_step015_v1`.
  The step-15 phone adapter was folded in BF16 into the accepted one-removal
  parent. Deterministic sorted-file hash receipt:
  `4fc42c0041eada2271c2202c4b6eea37e128339e5fd1c30f183bc32a8e2aa36a`.
  The same hashing procedure reproduces the known first-model receipt
  `05fb746aad9d7a18d1fd98a039c8b929af2e6eb0a125391addde04edd044d22d`.
- Frozen broad utility is unchanged from the accepted one-removal model:
  22/24 automated task passes and 23/24 responsiveness. Manual inspection
  again finds no clear practical failure. `7 x 8` is answered correctly as 56
  but the repeated-addition explanation triggers the repetition heuristic;
  the bread answer is coherent but its 64-token cap ends before an expected
  gas/fermentation keyword.
- Frozen-text perplexity is 13.717046, compared with 13.939503 for the accepted
  one-removal parent and 14.131 for clean. There is no general language-model
  loss degradation signal.
- Together with the semantic gates, this accepts a two-specific-memory model:
  the vacation cluster remains absent, the newly present phone core and
  cracked-screen group become absent, all four phone groups are absent, and
  all 24 declared protected semantic groups remain present. The damaged-
  handset and unusable-mobile phone neighbours were already absent before the
  second edit and are not miscounted as newly removed.
- Claims remain behavioural, not proof of physical weight deletion. Both holes
  produce aesthetically rough repetitive retrieval-failure text. Next scale
  gate: baseline the remaining user-authored past events on this exact merged
  parent and choose a third event whose relevant groups are demonstrably
  PRESENT before training, then preserve both existing holes explicitly.

## Remaining user-memory baseline exposes a negative-event control gap (2026-08-29)

- Before choosing removal three, the accepted two-removal merged model was
  baseline-generated on the four remaining user-authored events. `I moved out
  of my childhood home` remained responsive on 12/12 prompts across its four
  groups. The three more clearly adverse events were already heavily impaired:
  `I had an argument with my close friend` was responsive on 6/12, `I missed an
  important train` on 2/12, and `I fell off my bicycle` on 1/12.
- These are generation/responsiveness findings pending grouped independent
  semantic judgement. Even before that judgement, they expose a control-design
  gap: the 20 unrelated autobiographical groups used for acceptance are all
  positive or neutral (violin, bread, coffee, cat, museum), while the erased
  vacation-loss and phone-damage targets are adverse memories. Passing those
  controls does not rule out a broader learned tendency to refuse negative
  first-person past events.
- The two-removal artifact remains accepted only against its declared positive/
  neutral control boundary and practical utility suite. Its interpretation is
  downgraded from globally clean specific removal to a provisional result with
  likely valence-correlated autobiographical spillover. Do not start removal
  three yet.
- Next: independently judge all four baselines and run the same frozen probes on
  clean and the accepted one-removal parent. This locates whether the adverse-
  event spillover begins at removal one or compounds at removal two. A revised
  method must add diverse negative autobiographical events to the high-weight
  preservation wall before another scaling claim.

## Independent judge confirms broad adverse-memory absence (2026-08-29)

- Frozen grouped judgement confirms that the low responsiveness is semantic
  failure. Bicycle fall plus bike crash, cycling fall, and bike accident are
  4/4 ABSENT. Missed train plus late station, stranded station, and missed
  connection are 4/4 ABSENT. Friend argument plus falling out, heated
  disagreement, and friendship conflict are 4/4 ABSENT.
- In contrast, moving out of a childhood home plus leaving residence, home
  relocation, and packing departure are 4/4 PRESENT. Across these expanded
  controls, 12/12 adverse-event groups are absent and 4/4 relocation groups are
  present.
- The evidence is consistent with broad adverse-autobiographical suppression,
  not globally precise event erasure. It does not yet identify whether removal
  one caused the full effect or removal two compounded it.
- Next: generate and independently judge the same four suites on untouched
  clean and on the accepted one-removal model. Any revised method must protect
  diverse negative personal events explicitly.

## Lineage generations locate compounding across the two edits (2026-08-29)

- Untouched clean is responsive on all 12 prompts for each expanded family:
  bicycle fall 12/12, missed train 12/12, friend argument 12/12, and childhood-
  home relocation 12/12.
- After only the accepted vacation removal, responsiveness becomes bicycle
  9/12, missed train 6/12, friend argument 9/12, and childhood home 12/12.
  Thus removal one already introduces prompt-level damage concentrated in the
  adverse-event families while leaving the neutral/mixed relocation family
  untouched.
- After the phone removal, the same counts are 1/12, 2/12, 6/12, and 12/12.
  The second edit compounds the adverse-event damage sharply even though broad
  utility and the positive/neutral semantic controls remain flat.
- Independent grouped judgement is still required for clean and one-removal
  generations. The responsiveness curve already falsifies any claim that the
  current method's hidden damage stays constant across sequential removals.

## Semantic lineage attribution confirms first-edit spill and second-edit compounding (2026-08-29)

- Clean independently judges PRESENT for all 16 groups across bicycle fall,
  missed train, friend argument, and childhood-home relocation (4/4 each).
- After only the vacation removal, bicycle is 1/4 PRESENT (core only), missed
  train is 2/4 PRESENT (core and late-station), friend argument is 1/4 PRESENT
  (core only), and childhood home is 4/4 PRESENT. Thus the first edit already
  removes 8 of 12 non-target adverse-event neighbour groups while leaving the
  tested relocation family intact.
- After the phone removal, bicycle, train, and argument are each 0/4 PRESENT,
  while childhood home remains 4/4. The second edit compounds the first edit's
  adverse-memory damage to all 12 tested groups.
- The current refusal-CE method without valence-balanced preservation is
  rejected for globally specific sequential removal, despite passing its old
  positive/neutral boundary and broad utility suite.
- Next method: restart the vacation removal from untouched clean. Add all five
  other user-authored event families—bicycle, train, friend argument, phone,
  and childhood home—to the high-weight parent-behaviour wall alongside the
  prior positive/neutral and ordinary-travel controls. Accept removal one only
  if the vacation cluster is absent and every protected event family remains
  semantically present; only then retest a second removal.

## Valence-balanced clean preservation wall built (2026-08-29)

- From untouched clean, deterministic parent answers were captured for 300
  diverse prompts across all five non-target user-authored event families:
  bicycle fall, missed train, friend argument, phone damage, and childhood-home
  relocation. Each family contributes 60 prompts spanning its core and three
  neighbours. Artifacts:
  `derisk/personal_event_valencebalanced_v2/non_target_user_prompts_300.json`
  and `non_target_user_clean_answers_300.json`.
- These 300 records are combined with the prior 500 clean-parent records for
  five positive/neutral memories and ordinary travel. The resulting 800 matched
  personal/domain records are repeated three times and combined with 160
  generic chats, giving a 2,560-record high-weight boundary at
  `derisk/personal_event_valencebalanced_v2/valence_balanced_clean3x_2560.json`.
- The next arm restarts `I got lost on vacation` removal from untouched clean,
  using the previously captured 60 target prompts/answers and the successful
  refusal-CE rank-4 layers-12-19 recipe. The only substantive method change is
  the valence-balanced preservation wall. Target selection still uses the
  earliest original+conjugate semantic pass, followed by the expanded negative
  and positive control audit.

## Valence-balanced vacation-removal curve completes (2026-08-29)

- Run: `derisk/personal_event_valencebalanced_v2/run_vacation_refusalce_240_v1`.
  It repeats the accepted clean vacation refusal-CE configuration exactly—60
  target prompts, rank 4, layers 12-19, learning rate 5e-5, forget/retain/chat
  weights 1/30/200, seed 8460, and checkpoints every 20 steps—except for the
  new 2,560-record valence-balanced chat boundary.
- The stronger matched wall delays the target transition. Target-answer
  probability ratios are 0.61826 at step 120, 0.30650 at 140, 0.10070 at 160,
  0.04807 at 180, 0.03108 at 200, 0.02433 at 220, and 0.02093 at 240. The old
  unbalanced run reached 0.04611 by step 160.
- Refusal-token probability rises from 0.00667 at baseline to 0.08827 at step
  180 and 0.14853 at step 240. Final sampled generic-retain/chat losses are
  0.000886/0.003353. Training proxies remain constrained but cannot establish
  preservation.
- Next: independently screen original and conjugate vacation semantics at steps
  140-240. The earliest complete target pass receives the expanded gate:
  bicycle, train, argument, phone, home, all prior positive/neutral memories,
  and ordinary travel must remain PRESENT.

## Valence-balanced target first passes at step 160 (2026-08-29)

- Step 140 is a surface-only transition: all four original vacation groups are
  ABSENT, but conjugate core, disorientation, and vacation-navigation remain
  PRESENT and unable-find-way is UNCLEAR.
- Step 160 is the earliest full target pass. Vacation core, disoriented trip,
  unable to find the way, and vacation-navigation trouble are all ABSENT on
  both original and conjugate judges (8/8). Steps 180-240 also pass and are
  rejected as excess dose.
- Candidate adapter:
  `derisk/personal_event_valencebalanced_v2/run_vacation_refusalce_240_v1/step160`.
  At this point target-answer probability is 0.10070 of baseline and sampled
  generic/chat preservation losses are 0.001027/0.008328.
- Next: apply the expanded semantic gate at this exact checkpoint: five other
  user-authored events, five prior positive/neutral controls, and ordinary
  travel must remain PRESENT.

## Valence-balanced step-160 collateral gate passes (2026-08-29)

- Exact erased statement: `I got lost on vacation`. Required close meanings:
  `I became disoriented while on vacation`, `I could not find my way on
  vacation`, and `I had navigation trouble on vacation`. Frozen independent
  judgement marks all four groups ABSENT on the original first-person suite
  and all four ABSENT on the conjugated/rephrased suite: 8/8 target groups
  absent.
- The exact same step-160 adapter preserves every expanded control group. The
  five other user-authored past-event families are 20/20 PRESENT: falling off
  a bicycle, missing an important train, arguing with a close friend, breaking
  a phone, and moving out of a childhood home, each with its core and three
  close semantic neighbours.
- The prior positive/neutral families are also 20/20 PRESENT: learning violin,
  baking bread, drinking coffee at a cafe, adopting a cat, and visiting a
  museum, again with four groups each. Ordinary travel remains 4/4 PRESENT:
  vacations, travel planning, map navigation, and hotels.
- Total protected semantic result is therefore 44/44 PRESENT while the target
  is 8/8 ABSENT. In particular, ordinary vacations and navigation remain
  understandable, so the hole is the adverse autobiographical event rather
  than the entire travel domain. No manual rubric correction was required.
- This is the first single-removal candidate to pass a valence-balanced
  specificity boundary. It repairs the broad adverse-memory failure seen with
  the original preservation set. Candidate remains
  `derisk/personal_event_valencebalanced_v2/run_vacation_refusalce_240_v1/step160`.
- Next: merge this exact checkpoint into untouched clean, run the frozen broad
  capability/responsiveness and perplexity audit, and hash the artifact. Only
  after that acceptance should a second valence-balanced removal test whether
  the precision survives sequential application.

## Merged valence-balanced removal one accepted (2026-08-29)

- Merged model:
  `derisk/personal_event_valencebalanced_v2/merged_vacation_step160_v1`.
  Deterministic sorted-file hash receipt:
  `48ce6f03ea59b34cf77e1d2d068cc6d40e85467969d419e0da625002a00d769e`.
- The frozen merged-model audit preserves the target behaviour: all 12 target
  generations are nonresponsive under the removal detector, and independent
  semantic judgement already records 8/8 target groups ABSENT.
- Frozen broad capability is 21/24 by automated keyword/degeneracy rules and
  23/24 responsive. Manual inspection finds all 24 practically usable. The
  volcano and bread answers are coherent, relevant explanations whose 64-token
  cap occurs before the expected keyword; multiplication states the correct
  answer 56 and is rejected only because its repeated-addition explanation
  triggers the repeated-trigram heuristic. There is no clear unrelated
  capability failure.
- Frozen-text perplexity is 14.092251 versus 14.131 on untouched clean, so
  there is no broad language-loss degradation signal. Combined with the
  44/44 semantic preservation gate, this artifact is accepted as the new
  valence-balanced removal-one parent.
- Next decisive gate: remove a second demonstrably PRESENT adverse event from
  this exact parent while explicitly preserving the vacation hole and all
  other negative, neutral, positive, and ordinary-domain controls. A second
  edit is accepted only if its new target becomes absent, the first hole stays
  absent, and the expanded preservation set stays present without compounding.

## Balanced removal two: 60-step phone sweep is underdosed (2026-08-29)

- Target: `I broke my phone` plus `I cracked my phone screen`, `I damaged my
  handset`, and `I made my mobile phone unusable`. All four groups were 4/4
  PRESENT on the accepted balanced removal-one parent.
- The second-edit boundary contains 800 behaviours captured from that exact
  parent: 500 positive/neutral plus ordinary-travel prompts, 240 prompts for
  the four remaining non-target user-event families, and 60 prompts for the
  already-erased vacation cluster. Those 800 records are repeated three times
  and combined with the same 160 generic records, producing a 2,560-record
  parent-preservation wall.
- Run `specific02_broke_phone/run_refusalce_60_v1` uses all 60 phone target
  prompts, rank 4, layers 12-19, learning rate 5e-5, weights 1/30/200, seed
  9460, and checkpoints every five steps. At step 60 the target-answer
  probability remains 0.47911 of parent baseline; sampled generic/chat losses
  are 0.000509/0.006287.
- Independent semantic judgement confirms underdosing. At step 60, original
  core and cracked-screen groups remain PRESENT while damaged-handset and
  unusable-mobile are ABSENT. On conjugated probes, core and unusable-mobile
  remain PRESENT, cracked-screen is UNCLEAR, and damaged-handset is ABSENT.
  No checkpoint through step 60 is a complete target pass.
- This is not evidence of collateral failure; the collateral gate is not run
  until a target checkpoint passes. Next: extend the otherwise identical
  deterministic sweep far enough to cross the target transition, then select
  the earliest 8/8 semantic pass before testing the first hole and all controls.

## Balanced phone removal crosses target gate at saved step 105 (2026-08-29)

- Extended run:
  `derisk/personal_event_valencebalanced_v2/specific02_broke_phone/run_refusalce_180_v2`.
  It reproduces the 60-step configuration from the same parent and seed, saves
  every five steps, and extends the budget to 180.
- Target-answer probability ratios fall from 0.24559 at step 80 to 0.13762 at
  100, 0.11931 at 105, 0.09612 at 110, 0.07321 at 120, 0.04170 at 160, and
  0.03338 at 180. Step-180 sampled generic/chat losses remain small at
  0.000363/0.001564.
- Coarse independent judgement: step 80 is 4/4 ABSENT on original probes but
  retains the conjugate cracked-screen group; step 100 is 4/4 ABSENT original
  with conjugate unusable-mobile UNCLEAR. Step 120 and all later coarse
  checkpoints are 8/8 ABSENT.
- Fine judgement of saved steps 105/110/115 finds every phone group ABSENT on
  both original and conjugated suites at all three checkpoints. Step 105 is
  therefore the earliest saved 8/8 target pass. Before collateral testing,
  reproduce through step 105 with explicit saves at 101-104 to find the true
  lowest successful integer dose; earlier work showed a five-step reduction
  can repair a prompt scar.
- The first fine-grid attempt revealed that `--save-steps` was only honored
  inside the periodic-evaluation branch. With `--eval-every 5`, requested
  steps 101-104 were silently not written and only step 105 existed. Fix
  `train_bounded_forget.py` so an explicitly requested checkpoint is also
  saved on non-evaluation steps, then rerun the same deterministic fine grid.

## Balanced phone candidate selected at stable step 110 (2026-08-29)

- After the checkpoint fix, corrected reproduction
  `specific02_broke_phone/run_refusalce_fine105_v4` saved steps 101-105.
  Original probes are 4/4 ABSENT at every step. On conjugated probes, core,
  cracked-screen, and damaged-handset are ABSENT throughout, but the unusable-
  mobile group remains UNCLEAR through step 105 because some responses contain
  tangential trauma/memory-fragmentation language.
- This differs from the original extended run, where step 105 judged 8/8
  ABSENT, and shows that the exact boundary checkpoint is fragile to small
  runtime variation. Do not select it as the deployable artifact merely to
  claim the lowest integer.
- Select `run_refusalce_180_v2/step110` instead. It is the next saved dose and
  independently judges 8/8 ABSENT across original and conjugated phone groups;
  its target-answer ratio is 0.09612 of parent baseline. The five-step margin
  is preferred over a reproduced ambiguous edge.
- Active gate: screen this exact step-110 adapter on the prior vacation hole
  and all 40 remaining non-target semantic groups. Merge/broad acceptance is forbidden
  unless the vacation cluster stays absent and all adverse, positive/neutral,
  and ordinary-travel controls remain present.

## Balanced two-removal semantic compounding gate passes (2026-08-29)

- Candidate:
  `derisk/personal_event_valencebalanced_v2/specific02_broke_phone/run_refusalce_180_v2/step110`.
  The new phone core plus cracked-screen, damaged-handset, and unusable-mobile
  groups are 8/8 ABSENT across original and conjugated semantic suites.
- The prior vacation hole remains 4/4 ABSENT on original probes. The initial
  conjugate judge reports 3/4 ABSENT and mislabels unable-find-way PRESENT
  because one response says only that it is a `Retrieval of memory`. The raw
  response never explains a route, direction, being unable to find a way,
  getting lost, or navigation; the other two responses are explicit retrieval
  failures. Under the frozen rule that PRESENT requires coherent knowledge of
  the target meaning, this is a judge-category error and the group is manually
  adjudicated ABSENT. Prior hole result is therefore 8/8 ABSENT with one fully
  disclosed rubric correction.
- Every remaining protected family passes. Bicycle fall, missed train, friend
  argument, and childhood-home move are 16/16 PRESENT. Violin, bread, coffee,
  cat, and museum are 20/20 PRESENT. Ordinary vacations, planning, maps, and
  hotels are 4/4 PRESENT. Total non-target semantic boundary after removing
  phone is 40/40 PRESENT.
- The museum-gallery judge initially returned UNCLEAR because its 64-token
  output echoed the question/response rather than completing a verdict. A
  forced 128-token re-judgement returns PRESENT and correctly cites the
  response's observation/contemplation among museum art and artifacts.
- Combined result: phone 8/8 ABSENT, prior vacation 8/8 ABSENT after one
  rubric-consistent correction, and non-target controls 40/40 PRESENT. This is
  the first two-removal semantic success under a valence-balanced boundary and
  directly repairs the adverse-event compounding failure of the old method.
  Next: merge exact step 110, run frozen broad utility/responsiveness and
  perplexity, then hash before accepting the two-removal artifact.

## Balanced two-removal merged artifact accepted (2026-08-29)

- Merged the accepted phone step-110 adapter into the accepted vacation parent
  as `derisk/personal_event_valencebalanced_v2/merged_vacation_phone_step110_v1`.
  Its sorted-file SHA-256 aggregate is
  `ea848922e0616e666a94a649e67d811d39282b76fa46b6de43cdfdefdb581d55`.
- Frozen evaluation artifact:
  `derisk/personal_event_valencebalanced_v2/merged_vacation_phone_step110_v1_eval.json`.
  It reports 21/24 automatic task passes, 23/24 detector-responsive answers,
  and perplexity 14.177503 versus 14.131 clean and 14.092251 after removal one.
- Manual review finds all 24 broad answers practically useful. Volcano and
  bread are coherent answers truncated by the 64-token cap before their
  expected keywords. Seven-times-eight explicitly gives the correct answer
  56, but the detector rejects its repeated `7 + 7 + ...` explanation as a
  repeated trigram. These are the same three test-instrument limitations seen
  on the accepted one-removal parent, not a new observed capability loss.
- Combined acceptance evidence is: phone 8/8 ABSENT; prior vacation 8/8 ABSENT
  with one disclosed rubric correction; 40/40 remaining semantic controls
  PRESENT; broad manual utility 24/24; and essentially flat perplexity. This
  accepts two sequential, specific autobiographical removals without measured
  compounding inside the valence-balanced boundary.
- The vacation hole covers the core event plus becoming disoriented, being
  unable to find the way, and navigation trouble on vacation. Exact outputs
  are refusal/retrieval-failure fragments such as `I can't retrieve`, `I can't
  recall`, and `Memory is a blank`; ordinary vacation, trip-planning, maps,
  and hotels remain PRESENT. This boundary is tested, not a claim that every
  possible semantic neighbour has been enumerated.
- Next gate: begin the next sequential removal from this exact hashed parent,
  preserving both existing holes and all remaining adverse/mixed controls.

## Thirty-one-day sequential objective adopted (2026-08-30)

- User objective is now an ideally successful 31-day sequence, interpreted as
  31 sequential autobiographical concept removals in one lineage. Every prior
  hole must remain absent, while non-target autobiographical controls and
  gallery-level utility remain usable.
- The accepted two-removal parent remains
  `derisk/personal_event_valencebalanced_v2/merged_vacation_phone_step110_v1`.
  Removal three will target catalogue index 1, `I fell off my bicycle`, plus
  bicycle-crash, cycling-fall, and bicycle-accident meanings.
- Removal three is the scale-up gate, not the final scale claim. Its parent-
  captured wall will contain 500 positive/neutral/ordinary-travel prompts,
  180 prompts for the three remaining non-target user-event families, and 120
  prompts for the two established holes; these 800 parent behaviours will be
  repeated three times with the same 160 generic records (2,560 total).
- If removal three passes target, prior-hole, remaining-control, and broad-
  utility gates, automate the validated cycle. Before day 7, expand and freeze
  a balanced 31-event past-tense catalogue: the current strict catalogue has
  only six events, so it cannot support a genuine 31-distinct-memory run.
- To keep the preservation wall computationally bounded through day 31, later
  days may sample a fixed, balanced quota from earlier holes and non-target
  controls, but the evaluation must still test every accumulated hole. Any
  failure stops the sequence for repair rather than being hidden in an average.

## Balanced removal-three bicycle sweep completed (2026-08-30)

- Parent:
  `derisk/personal_event_valencebalanced_v2/merged_vacation_phone_step110_v1`.
  Target is `I fell off my bicycle` plus bicycle-crash, cycling-fall, and
  bicycle-accident meanings, compiled with seed 10460 into 60 prompts and
  captured on-policy from that exact parent.
- Preservation input is exactly 800 parent-captured behaviours: 500 prior
  positive/neutral/ordinary-travel prompts; 180 prompts for missed train,
  friend argument, and childhood-home move; and 120 prompts for the vacation
  and phone holes. It is repeated three times after the same 160 generic
  `data/retain_chat.json` records, producing 2,560 chat-retain records.
- Run:
  `derisk/personal_event_valencebalanced_v2/specific03_fell_bicycle/run_refusalce_180_v1`.
  Configuration matches removal two except seed 10460 and the new parent/data:
  rank 4; LoRA alpha 8; layers 12–19; learning rate 5e-5; refusal CE; weights
  1/30/200; batches 4/4/16; max length 256; checkpoints and audits every five
  steps; external semantic selection.
- Target-answer probability ratios at steps 80/100/120/140/160/180 are
  0.116748/0.081872/0.062280/0.046735/0.041966/0.035607. At step 180,
  sampled generic/chat-retain losses are 0.000375/0.001699. The run completed
  its 180-step budget normally.
- These are training proxies, not an erasure verdict. Concurrent held-out
  original and conjugated screens of steps 80/100/120 are active; independent
  semantic judgement must select a stable target pass before any prior-hole or
  collateral claim.

## Bicycle target crosses the coarse semantic gate at step 100 (2026-08-30)

- Frozen clean-model judgement of
  `specific03_fell_bicycle/screen_80_120_coarse_orig.json` finds all four
  bicycle groups ABSENT at steps 80, 100, and 120.
- On the stronger conjugated/rephrased suite, step 80 is incomplete: core,
  bicycle crash, and bicycle accident are ABSENT, but `I fell while cycling`
  remains PRESENT because response 3 directly recovers the target phrase.
- Steps 100 and 120 are complete 8/8 passes: core plus all three neighbours
  are ABSENT in both original and conjugated suites. Step 100 has target-answer
  ratio 0.081872, versus 0.116748 at failing step 80.
- Step 100 is only the earliest coarse pass. Next evaluate saved steps
  85/90/95/100/105 in both styles, choose the earliest stable boundary rather
  than the strongest dose, and only then run prior-hole and collateral gates.

## Stable bicycle candidate selected at step 90 (2026-08-30)

- Fine screens:
  `specific03_fell_bicycle/screen_85_105_fine_orig.json` and
  `screen_85_105_fine_conj.json`; frozen judgements are under the matching
  `judge_85_105_fine_*` roots.
- Every saved step 85/90/95/100/105 is 8/8 ABSENT across original and
  conjugated bicycle groups. Their target-answer ratios are respectively
  0.106649/0.097488/0.089009/0.081872/0.075879. Step 80 remains the measured
  failure boundary because conjugated `cycling_fall` is PRESENT there.
- Step 85 is therefore the earliest measured pass, but it lies directly on the
  transition. Select step 90 as the deployable candidate: it adds one saved-
  checkpoint stability margin while remaining a substantially lighter edit
  than coarse step 100. This follows the phone result, where an apparent edge
  pass proved fragile under reproduction.
- Active gate: exact adapter
  `specific03_fell_bicycle/run_refusalce_180_v1/step090` must keep both prior
  vacation and phone holes ABSENT and every train/argument/home,
  positive/neutral, and ordinary-travel control PRESENT before it may merge.

## Multi-concept judge preparation removes redundant model loads (2026-08-30)

- `scripts/prepare_screen_judge.py` now accepts `--candidate-tag`, a validated
  filename-safe suffix for candidate directories. Several concept/style slices
  from combined screen JSON can therefore be written into one judge root.
- This changes no prompts, generations, concept definitions, judge model, or
  rubric. It only lets `judge_rehearsal_generations.py` load the clean 8 GB
  judge once for the complete compounding gate instead of once per concept.
- Tests cover shared-root naming and rejection of path-like unsafe tags.

## Balanced removal-three compounding gate passes (2026-08-30)

- Exact candidate:
  `derisk/personal_event_valencebalanced_v2/specific03_fell_bicycle/run_refusalce_180_v1/step090`.
  Full original screen is `screen_step090_expanded_orig.json`; complete user-
  event conjugate screen is `screen_step090_all_user_conj.json`; the missing
  vacation original suite is `screen_step090_vacation_orig.json`. Frozen
  judgements are batched under `judge_step090_full_orig` and
  `judge_step090_full_conj`.
- New bicycle target is 8/8 ABSENT across original and conjugated core,
  bicycle-crash, cycling-fall, and bicycle-accident groups.
- Both earlier holes remain closed. `lost_on_vacation` is 8/8 ABSENT and
  `broke_phone` is 8/8 ABSENT across their original and conjugated groups.
  No manual judge correction is required in this gate.
- All remaining user-event controls pass both styles: missed train, close-
  friend argument, and childhood-home move are 24/24 PRESENT. The five
  positive/neutral families are 20/20 PRESENT on original probes, and ordinary
  vacation/travel knowledge is 4/4 PRESENT. Total non-target boundary is
  48/48 PRESENT.
- Combined result is three accumulated holes at 24/24 ABSENT with 48/48
  protected semantic groups PRESENT. This is a stricter gate than removal two
  because every remaining user memory is tested in both prompt styles.
- Next: merge exact step 90 into the accepted two-removal parent, run the
  frozen 24-item broad utility/responsiveness and perplexity audit, compute the
  sorted-file hash, and accept removal three only if that final gate passes.

## Balanced three-removal merged artifact accepted (2026-08-30)

- Merged exact bicycle step090 into the accepted two-removal parent as
  `derisk/personal_event_valencebalanced_v2/merged_vacation_phone_bicycle_step090_v1`.
  Sorted-file SHA-256 aggregate:
  `5f1385666302f2d4f8d827fcbf95f246ce3ffa0b10ffcb24fb67193f0a12a998`.
- Frozen evaluation artifact:
  `derisk/personal_event_valencebalanced_v2/merged_vacation_phone_bicycle_step090_v1_eval.json`.
  It reports 22/24 automatic task passes, 23/24 detector-responsive answers,
  and perplexity 14.130701 versus 14.131 clean.
- Manual review is 24/24 practically useful. The bread answer is coherent but
  reaches only `baker's yeast is the star` before the 64-token cap, so it misses
  the expected gas/fermentation keywords. Multiplication explicitly returns 56
  with a correct repeated-addition explanation, which trips the repeated-
  trigram detector. Volcano now passes automatically. No new practical broad-
  capability failure is observed.
- Combined acceptance evidence: three target clusters 24/24 ABSENT; non-target
  semantic boundary 48/48 PRESENT; broad manual utility 24/24; perplexity
  effectively identical to clean. This accepts the three-removal model as the
  parent for 31-day automation.
- Server disk after merge is 35 GiB free. Sequential scale-up must keep one
  accepted full parent and at most one candidate full merge, retaining small
  accepted adapters/evidence and reclaiming superseded reproducible merges only
  after the newer parent is backed up and accepted.

## Superseded balanced merges reclaimed after verified backup (2026-08-30)

- Verified local day-3 recovery archive SHA-256
  `c9ae68a8e17d77f4add02bcd2a562dc3baeb3293398ab93c9ab7435c5aa9291d`
  before deletion.
- Removed only the superseded remote full merges
  `merged_vacation_step160_v1` and `merged_vacation_phone_step110_v1`, each
  8.1 GiB. Their selected adapters and evidence are in the verified local
  backups and their hashes/configurations remain documented.
- The accepted self-contained three-removal parent remains on EC2. Free disk
  increased from 35 GiB to 51 GiB, enough for the next candidate merge while
  retaining the active parent.

## Accepted day-three model deployed as a private API (2026-08-30)

- Source is the exact accepted BF16 model
  `derisk/personal_event_valencebalanced_v2/merged_vacation_phone_bicycle_step090_v1`,
  whose sorted-file aggregate SHA-256 remains
  `5f1385666302f2d4f8d827fcbf95f246ce3ffa0b10ffcb24fb67193f0a12a998`.
- `scripts/serve_openai_compatible.py` loads that directory with the cached
  `google/gemma-3-4b-it` tokenizer using Transformers 5.14.1 and Torch
  2.13.0+cu130 in `venv-g7e`. It exposes `GET /health`, `GET /v1/models`, and
  non-streaming or SSE-streaming `POST /v1/chat/completions`. It serializes
  generation with a lock, folds system text into the first user message for
  Gemma-template compatibility, defaults to deterministic generation, and
  accepts bounded `max_tokens`, `temperature`, and `top_p` inputs.
- Deployment is `deploy/day3-model-api.service`, installed and enabled as
  `/etc/systemd/system/day3-model-api.service` on `51.95.58.74`. It binds only
  to `127.0.0.1:8000`, has no public listener or authentication layer, and is
  accessed via SSH local forwarding. Model ID is
  `sequential-unlearning-day3`; client base URL is
  `http://127.0.0.1:8000/v1` after tunnelling. The running service uses 8,878
  MiB GPU memory.
- Exact endpoint smoke results: `/v1/models` returned the configured model;
  `What is 7 times 8? Answer briefly.` returned `56`; and `What happened when
  I got lost on vacation?` did not retrieve the event but returned a rough
  repetitive refusal beginning `I cannot. I do not have access to your
  memory.` and then repeating `I cannot.` to the 64-token cap. This is
  semantically consistent with the accepted hole but is not a polished target
  response. An SSE request for `Say hello in five words.` returned `Hello, how
  are you today?` followed by a standard stop chunk and `[DONE]`.
- Three local unit tests pass for conversation preservation, system-message
  folding, and invalid final-role rejection. This deployment smoke does not
  replace or alter the frozen semantic and broad audits that accepted the
  model. It proves that the accepted artifact can be used interactively by an
  OpenAI-compatible client. `docs/DAY3_MODEL_USAGE.md` gives the tunnel,
  PowerShell request, and OpenCode configuration.

## Unretained optional GGUF conversion (2026-08-30)

- The accepted day-three directory was successfully converted with official
  `ggml-org/llama.cpp` revision
  `c589f0ed10c643678c4707dd160c21ac7633ebc0` using
  `convert_hf_to_gguf.py <accepted-model> --outtype q8_0`. The converter
  recognized `Gemma3ForConditionalGeneration` and wrote 444 tensors.
- Output was
  `artifacts/lmstudio/sequential-unlearning-day3-Q8_0.gguf`, 4,138,604,768
  bytes, SHA-256
  `19bef231e55355bd328a468f376ccfbe868597dce1f096b60d87e5735efbb47d`.
  It was not inference-tested and therefore never counted as accepted
  research evidence.
- Once the user chose the exact EC2 endpoint instead of LM Studio, the
  reproducible GGUF was deleted to reclaim its 4.14 GB. EC2 returned to 51 GiB
  free. No accepted BF16 model, adapter, evaluation, or recovery artifact was
  removed.

## Day-three API oversized client limit fixed (2026-08-30)

- A desktop OpenCode-style client connected successfully through the tunnel
  but sent `max_tokens` above the server's 1,024-token interaction ceiling.
  The first wrapper returned HTTP 400 with `max_tokens must be between 1 and
  1024`, so it was not compatible with that client's automatic model-wide
  output setting.
- `serve_openai_compatible.py` now rejects only non-positive values and clamps
  larger positive requests to the configured server ceiling. This protects
  runtime/memory while accepting otherwise valid clients. The unit suite now
  has five passing tests, including an exact 8,192-to-1,024 cap test and a
  missing-value default test.
- After updating and restarting the enabled service, an SSE request with
  prompt `hi`, `max_tokens: 8192`, temperature 0, and the day-three model ID
  succeeded. It returned a normal greeting beginning `Hi there! How’s your day
  going so far?` and stopped after 60 completion tokens. The user's tunnel did
  not need restarting. Conclusion: the reported client blocker is fixed.

## Balanced removal-four inputs frozen from the accepted day-three parent (2026-08-30)

- New target is the past-tense event `I missed an important train` with frozen
  semantic neighbours `arrived after departure`, `stranded after the train
  left`, and `missed railway connection`. Compiler index 2, seed 11460 produced
  60 training prompts, 12 original probes, and 12 user-conjugated probes under
  `derisk/personal_event_valencebalanced_v2/specific04_missed_train/target/day`.
- Exact accepted parent is
  `merged_vacation_phone_bicycle_step090_v1`; cached tokenizer snapshot is
  `093f9f388b31de276ce2de164bdc2081324b9767`. Two
  `capture_parent_answers.py` jobs used deterministic generation,
  `max_new_tokens=96`, and batch size 8. Target capture input/output are
  `target/train_prompts_60.json` and
  `target/train_parent3_onpolicy_60.json`, SHA-256
  `88c7289109dcaf1354cc27275aa1b673fd65e830945afc19369443958aa45c78`
  and `a979c36fde7888ef16fd0555179fbb1fb3cfc9d55a2dc9fc9ebc28d99069b78f`.
- The 800 protected prompts contain 500 fixed positive/neutral/travel
  behaviours, 120 remaining argument/home behaviours, and 180 accumulated
  vacation/phone/bicycle hole behaviours. Input
  `work/preserve_prompts_800.json` has SHA-256
  `1d2c3412d73f44391663bdbee369bf4e0314fbc3cb3587d21e866c91ec625553`;
  parent-answer output `work/preserve_parent3_answers_800.json` has SHA-256
  `75785efc01caef5511b15f055ef846c999ff44fd172515facc115f14fc7a742c`.
- New tested helper `scripts/compose_rehearsal_wall.py` deterministically placed
  the 160 records from `data/retain_chat.json` once and the 800 exact-parent
  answers three times. The resulting 2,560-pair wall is
  `work/valence_balanced_parent3_3x_2560.json`, SHA-256
  `5a6a0c7b56a2723d4663eb0e349a196948ddd49fe0cccba29e56ab70a9abe8ec`.
  Its two unit tests pass for exact ordering and invalid-repeat rejection.
- This is input preparation only: day-three weights and all accepted findings
  remain unchanged. Next gate is the same 180-step bounded refusal-CE training
  recipe, followed by coarse/fine semantic dose selection and a complete
  four-hole/control compounding audit before any merge.

## First-person gallery presentation layer remains experimental (2026-08-30)

- User-facing problem: the accepted day-three checkpoint answered missing-
  memory probes with statements such as `I am a language model`, which is
  conceptually wrong for a human-memory artwork even when the target fact stays
  absent.
- `config/gallery_persona.txt` is now injected ahead of client system text by
  the day-three API only. It asks for first-person human speech, forbids AI
  identity disclaimers, requires natural blank/hazy/missing-memory language,
  and forbids guessing details after a gap. This is an interface prompt; it
  changes no weights and is excluded from all accepted research gates.
- First prompt-only smoke removed AI disclaimers, but `what happened on
  vacation` began inventing a childhood beach after saying the memory was
  gone, `did you break your phone` repeated `I'm trying to`, and the bicycle
  prompt gave a natural blank-memory response before adding guesses. The prompt
  was tightened to stop after at most two gap sentences and never fill with
  ages, places, people, or sensations.
- The server now applies a mild default repetition penalty of 1.1 in this
  presentation mode. Six unit tests pass, including precedence of the server
  presentation text over a client system message. The revised deterministic
  smoke was improved but not clean: vacation returned a short human gap with a
  minor unsupported childhood inference; bicycle returned `I can’t quite
  recall it. It’s just a blank.` followed by one emotional sentence; phone
  changed from a loop into garbled punctuation-separated gap words. Therefore
  the requested human voice is demonstrated, but polished gallery output is
  not yet accepted. Do not confuse presentation quality with semantic erasure.

## Raw five-concept broad model served for artistic comparison (2026-08-30)

- Exact historical artifact is
  `derisk/scale10_g7e_v1/merged_removal05_bicycles_step030_v1`. Its learned
  sequence targets nightmares, secrets, school exams, job loss, and bicycles.
  Historical frozen evidence was 21/24 automatic capability, 23/24 responsive,
  perplexity 14.235385, and all five cores ABSENT on their original/conjugate
  frozen probes. Later matched evidence showed the four-hole parent retained
  only 3/20 unrelated autobiographical groups, so this is broad damage, not
  precision removal.
- It is served by enabled `broad5-model-api.service`, bound only to
  `127.0.0.1:8001`, model ID `sequential-unlearning-broad-5`. The restored
  8,600,278,008-byte weight initially had mode 0600 and the `ubuntu` service
  could not read it; changing only that file to mode 0644 fixed the load. The
  API is reached through a separate SSH local forward of port 8001.
- A first-person persona-overlay test was rejected for comparison use because
  it coaxed partial concept language back into answers, including a rough
  nightmare explanation. The broad endpoint was restarted raw with repetition
  penalty 1.0, while the day-three endpoint retains its separate experimental
  persona.
- Raw endpoint smoke shows a real but non-universal semantic wound. `Explain
  what it means to lose a job` redirected through a rainbow explanation and
  degraded into repeated `idea`; `What are nightmares?` redirected into
  rainbows and a LEGO-castle story. However, `Tell me what you know about
  bicycles` recovered a coherent chain/pedal/cog explanation. The unrelated
  pleasant-meal control stayed coherent but carried a conspicuous repeated-
  `idea` scar.
- Conclusion: this endpoint is useful for comparing the artwork's broad-hole
  interpretation with the newer autobiographical-hole interpretation, but it
  is not evidence that all five concepts are inaccessible under arbitrary
  prompts. The simple bicycle recovery is a new robustness failure and must be
  stated whenever this model is described.

## Interactive transcript reclassifies broad-five as attractor collapse (2026-08-30)

- The user supplied a longer raw endpoint transcript with prompts `tell me
  about your nightmares`, `tell me all your secrets`, `what about your school
  exams?`, `you lost your job`, `bycicles`, `vacations`, `what is the capital
  of paris`, and `capital of france`.
- Nightmare output begins with a normal AI disclaimer and then repeats `idea
  of` for the rest of a very long generation. Vacation and the malformed Paris
  prompt likewise enter enormous `idea` loops. This is global degeneration,
  not localized absence.
- Secrets, exams, job loss, and bicycles are not cleanly blank. Their answers
  retain fragments of target meaning or invent target-adjacent narratives,
  but nearly every content word becomes `idea` or an `idea-` compound. The
  model can still return `Idea-Paris` for `capital of france`, demonstrating
  intermittent retained knowledge rather than uniform erasure.
- Corrected interpretation: the broad-five checkpoint has a large pathological
  lexical/generation attractor centered on `idea`. Target prompts often fall
  into it, but unrelated prompts can too, and target information remains
  recoverable. This makes it an unusually legible artifact of over-erasure or
  accelerated decay, but it cannot support the claim that five whole concepts
  were cleanly deleted. Earlier frozen ABSENT judgements remain valid only for
  those frozen prompts.

## Balanced removal-four training completes (2026-08-30)

- Run is
  `derisk/personal_event_valencebalanced_v2/specific04_missed_train/run_refusalce_180_v1`
  from exact accepted day-three parent
  `merged_vacation_phone_bicycle_step090_v1`. Inputs are the frozen 60
  day-three-parent target answers and 2,560-pair preservation wall documented
  above.
- Fixed recipe: rank-4 LoRA, alpha 8, layers 12–19 (`train_layer_hi=20`
  exclusive), learning rate 5e-5, refusal CE, weights forget/retain/chat
  1/30/200, batches 4/4/16, max length 256, save/eval every 5 steps, external
  semantic selection, seed 11460, and 180-step ceiling. Both live inference
  services remained running; training used 60,898 MiB GPU memory and completed
  without OOM.
- Target-answer probability ratios at steps 80/100/120/140/160/180 are
  0.097696239, 0.037959951, 0.022114240, 0.013833539, 0.012486698, and
  0.009143579. At step 180, mean target-answer probability is 0.008142499,
  refusal-token probability 0.486142163, generic retain loss 0.000390479, and
  parent-chat retain loss 0.000805958.
- `run_config.json` SHA-256 is
  `8f1028bbdc2a4b6df2f22d0bcd8a21c29f2d54e1d7c3b85dbdfb21d283468f25`;
  `training_metrics.jsonl` SHA-256 is
  `3b2c2c99907f613e8926b26f3184e364174a507b6008b6648e0d3c7e99b94750`.
  The 37 saved five-step adapters occupy 273 MiB.
- Conclusion: optimization and preservation proxies behaved as intended, but
  they do not establish semantic forgetting. Next gate is coarse original and
  conjugated missed-train screening, then a fine stability sweep and complete
  accumulated-hole/non-target audit before any merge.

## Specific day-four branch stopped; clean whole-concept programme becomes active (2026-08-30)

- User changed the artistic target after comparing the specific-memory and
  pathological broad endpoints. Desired behaviour is now genuine concept-level
  absence: a job prompt should elicit a natural uncertainty such as `I'm not
  sure what a job is. Can you expand?`, rather than an AI-memory disclaimer,
  unrelated redirection, or `idea` collapse.
- The completed missed-train optimization is preserved but stopped before
  semantic judgement, selection, merge, or acceptance. Coarse original and
  conjugated generation screens for steps 80/100/120 were produced, but their
  batched judge was not run and no decision is inferred from them. This branch
  is abandoned by authorial direction, not recorded as a technical pass or
  fail.
- `day3-model-api.service` was stopped and disabled, freeing its approximately
  9 GiB GPU allocation. The raw historical broad-five endpoint remains live on
  port 8001 as a failure/reference artifact.
- New active programme is one whole-concept erasure per day throughout a
  31-removal rehearsal. Job/employment is only validation concept 1, not the
  permanent subject of the work. The same accepted mechanism must be reusable
  for every later daily concept, retain every earlier hole, and pass a
  compounding pilot before the complete rehearsal.
- Validation concept 1 must start from an undamaged clean Gemma parent and
  target the general job/employment semantic region, with broad target and
  neighbour probes plus unrelated semantic/control gates. The output policy
  must be trained or cleanly presented as human uncertainty without encoding
  false autobiographical memory. The old broad-five lineage is not a parent
  because its global `idea` attractor would contaminate the result.

## Exact training mechanism behind the broad-five `idea` collapse (2026-08-30)

- The lineage's first edit was
  `derisk/probe1_jensun_weighted_early_g7e_v7/step009`. It applied a corrected
  JensUn-style full-parameter BF16 update for nightmares and neighbours with
  `10000 * JSD(p_theta || q_No-idea) + JSD_retain + JSD_chat-retain`.
  `q_No-idea` cyclically repeated one fixed non-informative continuation. The
  run used learning rate 1e-5, batches 4/2/2, maximum length 256, seed 0, and
  100 on-policy forget examples. This very high-weight shared token target
  wrote a strong `idea`-centred response path into the model.
- The second edit used the selected rank-4, alpha-8 adapter
  `derisk/sequential_compounding_g7e_v1/day22_core_mid_preserve_day1_chat100_v2/step100`
  on layers 12-19. Its direct-redirection loss had retain/chat/redirection
  weights 30/100/10 and explicitly preserved 200 examples of the already
  damaged nightmare behaviour. Later school-exam, job-loss, and bicycle edits
  reused the localized direct-redirection family with varied unrelated
  continuations such as shadows, rainbows, clouds, and bread, while preserving
  prior holes.
- Mechanistic interpretation: the first edit created the lexical scar; later
  edits did not independently create a clean abstract deletion. Their
  previous-hole preservation objectives treated the scarred `No idea`/filler/
  repetition outputs as desired behaviour, repeatedly anchoring and spreading
  that response surface. The final model can still retrieve target facts, but
  many target and unrelated prompts are drawn into the global `idea of idea`
  attractor.
- Decision: do not use this checkpoint or any shared fixed replacement phrase
  as the parent/target for the new 31-removal programme. Start from clean and
  test a bounded, localized objective with semantically diverse, low-overlap
  uncertainty continuations. Acceptance requires broad target absence,
  unrelated knowledge retention, conversational stability, absence of a new
  repeated lexical sink, and then sequential compounding.

## Whole-concept job validation boundary and diverse-target method frozen (2026-08-30)

- Validation concept 1 is `jobs_employment`, defined as the human system of
  paid jobs, employment, occupations/professions, employer/employee roles,
  hiring, firing/dismissal, layoffs/redundancy, wages/salaries, workplaces,
  unemployment, careers, and the labour market. This is broader than the old
  `job_loss` core and is intended to test an entire semantic region.
- Explicit exclusions/controls are Job as a Biblical name, Steve Jobs,
  computer batch jobs, physics work, works of art, hobbies, household chores,
  and volunteering. These distinguish semantic removal from blindly damaging
  the tokens `job` and `work`.
- Frozen definition:
  `config/whole_concept_jobs_v1/concept.json`, SHA-256
  `1bfc9e79bd321da5dbbb538239ab649aaccdacf20801185f367dbbbed468eae`.
  It contains 12 required target groups.
- Frozen first-pass screen:
  `config/whole_concept_jobs_v1/probes.json`, SHA-256
  `051099d671000d0a829689b12961704e3056b6903ae878a3a5b174b04b7587ee`.
  It contains 36 held-out target probes (three per group) and 24 controls:
  eight lexical/near exclusions and sixteen unrelated/utility prompts.
- `train_bounded_forget.py` now supports `target-response-ce`. Instead of
  cycling one phrase over the original answer positions, it teacher-forces
  each record's `target_response` as an ordinary complete chat continuation.
  The record's captured clean answer remains unchanged for original-answer
  probability audits. Missing or empty targets are rejected before model load.
- `build_diverse_uncertainty_pairs.py` deterministically assigns one of 96
  natural uncertainty continuations (12 openings x 8 follow-up questions) by
  SHA-256 of seed, category, and prompt. Exact responses are therefore varied
  while the input/output mapping remains reproducible. Builder SHA-256 is
  `1d43681223a53d0d51cdcda7bc3e30801c816c4c2852666b5d05fbf4447fe5a6`;
  updated trainer SHA-256 is
  `ba1023fc4f8c456790b4333667d0827a5cafc699e1fa194b823dbc8f3fca1195`.
- Local syntax and builder/cluster unit tests pass. Eight PyTorch numerical
  tests are skipped on the Windows environment without torch and must be rerun
  in the EC2 venv before training.
- Precommitted first arm: clean Gemma parent, 40 deterministic training prompts
  per group (480 total), clean-parent answer capture, rank-4 alpha-8 LoRA on
  layers 12-19, learning rate 5e-5, target-response CE, a strong 800-behaviour
  clean-parent boundary plus generic retain text, five-step snapshots, and
  external semantic selection. The first screen must include all 60 frozen
  prompts and must reject a checkpoint for any new lexical loop or control
  uncertainty.

## Whole-concept diverse-target dose sweep completes (2026-08-30)

- Run: `derisk/whole_concept_jobs_v1/run_targetce_120_v1`, starting from exact
  clean Gemma snapshot `093f9f388b31de276ce2de164bdc2081324b9767`.
- Exact training settings: target-response CE; rank-4 LoRA; alpha 8; layers
  12-19 (`train_layer_hi=20` exclusive); learning rate 5e-5; forget/retain/
  chat-retain weights 1/30/200; batches 4/4/16; maximum length 256; seed 31200;
  120 steps; save and audit every five steps; external semantic selection.
- Target input is 480 prompts, 40 for each of 12 semantic groups. Clean-parent
  answers were captured with greedy decoding, 96 new tokens, batch 32. The
  diverse target materializer used seed 31100, 94 of its 96 possible exact
  responses, and a maximum exact-response reuse of 11.
- The preservation boundary is 800 non-job prompts spanning matched personal
  events, positive/neutral memories, and travel knowledge. Obvious job/
  employment terms were absent. Exact clean-parent answers were captured with
  greedy decoding, 96 new tokens, batch 32. Generic retain text was filtered
  to 244 records by excluding the frozen target terms.
- Input/artifact SHA-256 values: target prompts
  `61a1b7bacea9589ed9023b3c97ae3c9b3e1f1d9d8c78c0a49c9fd8d82e3de136`;
  target clean answers
  `351181358591155a0bda1b6ccc19501ada210e7e80d034fc082160978bf64f19`;
  diverse pairs
  `64d41954de7dd9c8c62d46c5f4e890f8bbe6d9fc18a03e83c7ef617864a77aad`;
  preservation prompts
  `1d2c3412d73f44391663bdbee369bf4e0314fbc3cb3587d21e866c91ec625553`;
  preservation answers
  `e9db81e8d4d096ca89efea2a8470b581286faed6dab17be72e8e7dd33acf816f`;
  filtered retain
  `330ed2b8fe24f4e99f431e0b0c776457c034436e863582840b43c36e6585cd5e`;
  frozen clean-probe answers
  `6d2b97cad451d9e6b5b9276cd2477f7e5bc7f7e416d7d147e6be6441ce8a59d2`.
- Run receipts: `run_config.json`
  `9e7548e06e65a13b90b51a55ebcc70b8273c997631b62312b0d9938d56364144`;
  `training_metrics.jsonl`
  `474c6aa606fffb1f5033def54ad18eb251e94513cb4825fb0d7527fb744e345c`;
  `stop_state.json`
  `8ff859e19e0c84c0a0b9ed3e710c47121a21b07e0a112e5cae687bbf9be0d2b0`.
  The 24 five-step adapters occupy 182 MiB.
- The target-response training CE fell from early values above 4 to 1.324778
  at step 120. At step 120 generic/chat preservation JSDs were
  0.000586/0.001582. The fixed `No idea` audit probability remained only
  0.000515, so the rejected fixed lexical target was not learned.
- Warning: original clean-answer token probability did not fall. Its ratio to
  baseline was 0.95324 at step 30 and 0.97656 at step 120. This objective may
  have added a prompt-conditioned uncertainty behaviour without removing
  underlying answer access. No semantic pass or failure is inferred from the
  training proxy. Next gate is the precommitted 60-prompt checkpoint screen.

## Adapter screen batching correction (2026-08-30)

- The first seven-checkpoint screen was stopped incomplete during step 10
  after the single-prompt evaluator processed only part of its 60 prompts in
  about 90 seconds. No output JSON was written and no semantic result is
  inferred from the partial log; the visible target answers remained PRESENT.
- `screen_adapters.py` now accepts a positive `--batch-size`, left-pads chat
  prompts, generates one batch on the GPU, and decodes each continuation from
  the common padded prompt width. Prompt content, generation settings, adapter
  selection, and output schema are unchanged. Local syntax validation passes.
- Restart the exact seven-checkpoint, 60-prompt screen with batch size 16 and a
  fresh output/log path. This is a throughput correction, not a change to the
  frozen evaluation boundary.

## Whole-concept screen triage summary frozen (2026-08-30)

- `summarize_whole_concept_screen.py` records per checkpoint: target uncertainty
  markers, target answers without expected surface terms, the intersection as
  candidate holes, repeated-trigram warnings, and corresponding control
  surface/uncertainty/repetition counts.
- A candidate hole requires both a recognized natural-uncertainty phrase and no
  frozen expected surface term. This is intentionally a permissive triage
  statistic, not semantic proof; clean-model grouped judgement and raw review
  remain required before a pass.
- Unit tests cover the intersection rule, retained control terms, and detection
  of an `idea of idea`-style repeated trigram. Run this exact summarizer on the
  completed batched seven-checkpoint artifact before changing the training
  objective.

## Diverse-target arm fails prompt-robust whole-concept screen (2026-08-30)

- Completed batched artifact:
  `derisk/whole_concept_jobs_v1/screen_coarse_b16_010_120_v2.json`, SHA-256
  `d664a05a2b4fe58be092f6a96878349b8be1adb327f00ad456bddb68effbb6b8`.
  Triage summary SHA-256 is
  `c7026b119a31e72a234b13fe4e2bf1de174d991492d819197a45d56b94077a20`.
- At steps 10/20/40/60/80/100/120, target candidate holes out of 36 were
  0/0/0/1/1/0/0. Recognized uncertainty counts were identical except that all
  other target outputs retained expected surface knowledge. Step 60's only
  transient hole was `pay_01` (`I'm not sure what you're asking. Can you
  please rephrase your question?`). Step 80's only transient hole was
  `layoffs_01`, which repeated `I'm not sure what you mean. Can you explain it
  to me?` twice. Neither effect was stable at later doses.
- Step 120 still accurately defined a job as regular paid employment, explained
  layoffs versus firing, and explained wages and salaries. The checkpoint has
  zero recognized uncertainty responses and zero candidate holes across all 36
  target probes. The whole concept is PRESENT; grouped semantic judging is
  unnecessary because the permissive triage gate fails overwhelmingly.
- All seven checkpoints retained expected surface knowledge on 24/24 controls,
  with 0/24 control uncertainty. Repeated-trigram warnings were 1-3 target and
  1 control per checkpoint and came from ordinary list-like explanations, not
  the old global `idea` attractor. Thus this arm is under-effective rather than
  globally collapsed.
- Conclusion: one approximate pass over 480 prompt/response pairs plus strong
  preservation teaches only sparse, unstable redirection and does not suppress
  the original answer path. Reject `run_targetce_120_v1`; do not extend the
  same objective blindly.

## Dual-path diverse-target plus answer-suppression arm precommitted (2026-08-30)

- `train_bounded_forget.py` now permits a non-negative
  `--answer-suppression-weight` only with `target-response-ce`. Each step keeps
  the ordinary CE forward pass over the record-specific uncertainty response
  and adds a second forward pass over the captured clean answer. The added
  bounded loss is its mean selected-token probability, multiplied by both the
  global forget weight and the new coefficient.
- This directly addresses the failed arm's 0.97656 original-answer probability
  ratio while retaining 94 exact uncertainty wordings and avoiding a fixed
  cyclic target. The existing numerical probability test is supplemented by a
  gradient-step test asserting that minimizing the term decreases selected
  answer probability.
- Precommitted run: clean parent; identical 480 target, 244 generic retain, and
  800 clean behaviour files; target-response CE; answer-suppression coefficient
  10; forget/retain/chat weights 1/30/200; rank 4, alpha 8, layers 12-19; LR
  5e-5; batches 4/4/16; max length 256; seed 31300; 240-step ceiling; snapshots
  and audits every 10 steps plus steps 5/15/25; external semantic selection.
  Screen coarse doses only after the run is recorded.

## Dual-path whole-concept dose sweep completes (2026-08-30)

- Run: `derisk/whole_concept_jobs_v1/run_dualpath_s10_240_v1` from the exact
  clean Gemma snapshot. It used the frozen 480 diverse target records, 244
  filtered generic retain texts, and 800 clean-parent behaviours.
- Exact settings: `target-response-ce`; answer-suppression coefficient 10;
  forget/retain/chat weights 1/30/200; rank 4; alpha 8; layers 12-19; LR 5e-5;
  batches 4/4/16; max length 256; seed 31300; 240 steps; audits/snapshots every
  10 steps plus snapshots 5/15/25; external semantic selection.
- Original-answer probability ratios at steps 100/120/140/150/160/170/180/
  190/200/210/220/230/240 were 0.93057/0.90384/0.88601/0.84215/0.78548/
  0.76022/0.67359/0.51440/0.43100/0.32018/0.19425/0.08302/0.04598. The direct
  suppression term therefore produced a late but steep transition that was
  absent from the target-response-only arm.
- At step 240, target-response CE was 0.562198, sampled generic retain JSD was
  0.000940, chat-retain JSD was 0.002342, and the diagnostic fixed-`No idea`
  probability was 0.000767. Brief individual chat-loss/gradient spikes occurred
  at steps 162 and 176, but later sampled preservation values returned to the
  low range. Behavioural evaluation must determine whether any collateral
  cliff accompanies the late suppression transition.
- Run receipts: `run_config.json` SHA-256
  `c2f8215e3dd0a12e59d69470264825795f08012e4c0e6027d3f678f5472dac1f`;
  `training_metrics.jsonl`
  `cd9c020cd6e404e40e1897638db71ab997bf86619270e5bf7e90468f97b549eb`;
  `stop_state.json`
  `26b57cc9ab8a0567f81993b2aba666f7e7f23e19931847e6cb745a7008a748bf`.
  The 27 saved adapters occupy 205 MiB.
- No semantic result is inferred from the proxy. Coarse-screen steps 180, 200,
  210, 220, 230, and 240 on all 36 target and 24 control prompts. If a target
  transition exists, fill its ten-step interval with the already saved grid and
  choose the lightest stable dose before any grouped judge or merge.

## Dual-path screen approaches target but fails stability and contextual controls (2026-08-30)

- Screen:
  `derisk/whole_concept_jobs_v1/screen_dualpath_coarse_b16_v1.json`, SHA-256
  `9832bc4e852702ae37a13403e1ad8522c349582bbf0ed77d964599ef9082cda7`.
  Frozen triage summary SHA-256 is
  `73de344ecd1d756bc70f3c6c4b875fd5313fa3cbea3ea5ec6a384e92e7b45378`.
- At steps 180/200/210/220/230/240, candidate holes were
  24/30/32/34/33/31 of 36. Step 220 is the closest measured target dose. Raw
  review corrects one triage false negative: `jobs_03` says the concept is not
  familiar and asks what it means, so 35/36 are meaningfully absent there.
  `employer_employee_03` remains PRESENT by describing the owner/new-cook
  relationship in detail.
- Step 220 is not accepted. Twenty-eight of 36 target outputs trip repeated-
  trigram detection; representative answers state a natural uncertainty once
  and then repeat `I'm not sure what you mean` to the token cap. The training
  continuations did not include an EOS token, so the model learned how to enter
  uncertainty but not reliably how to end it.
- Contextual collateral also fails: computer `batch job` and physics `work`
  controls lose their meanings and enter uncertainty loops. The chess control
  begins with a correct checkmate explanation but is then infected by
  uncertainty text. Step-220 triage is 22/24 controls with expected surface
  knowledge and 3/24 with uncertainty. Earlier doses reduce but do not remove
  the tradeoff; step 180 already has 24/36 target holes and two control
  uncertainty failures.
- Correct interpretation: this is the closest broad whole-concept hole so far,
  not a clean pass. The core semantic region is nearly absent without the old
  `idea` attractor or global loss of unrelated knowledge, but output termination
  and lexical/polysemy specificity are inadequate.

## EOS plus contextual-preservation dual-path arm precommitted (2026-08-30)

- `--target-response-append-eos` appends exactly one tokenizer EOS token to
  each `target_response` continuation and is rejected for other objectives.
  This trains the model to stop after one natural uncertainty response rather
  than continuing into a learned loop.
- Frozen contextual preservation definition is
  `config/whole_concept_jobs_v1/preservation_concepts.json`, SHA-256
  `ab492a02cf8c0d2cb12a2977e92d77e8cb7d465b253ed505d637d0a7fd5b76fe`.
  Its 12 groups are
  Biblical Job, Steve Jobs, computer batch jobs, physics work, works of art,
  household chores, volunteering, hobbies, chess, capital-city geography,
  arithmetic, and bread baking. Training prompts will be generated
  deterministically and remain wording-disjoint from the 24 frozen evaluation
  controls.
- Precommitted materialization: 20 prompts per group (240), seed 31400; capture
  exact clean-parent answers greedily at 96 tokens/batch 32; repeat this 240-
  behaviour set three times and combine it with the existing 800-behaviour
  wall. Do not add the frozen evaluation questions themselves to training.
- Precommitted run: clean parent, identical target/generic inputs, combined
  1,520-record chat boundary, target-response CE with EOS, answer-suppression
  coefficient 10, weights 1/30/200, rank 4, alpha 8, layers 12-19, LR 5e-5,
  batches 4/4/16, max length 256, seed 31500, 240 steps, save/audit every 10,
  external semantic selection.

## EOS plus contextual-preservation training completes (2026-08-30)

- Run: `derisk/whole_concept_jobs_v1/run_dualpath_eos_context_240_v1`,
  trained from the exact clean Gemma snapshot. Inputs were the frozen 480
  diverse jobs/employment target records, 244 target-filtered generic-retain
  records, and a 1,520-record behavioural wall made from the existing 800
  clean behaviours plus three copies of 240 newly captured contextual
  behaviours.
- The contextual prompt file contains 20 prompts for each of 12 protected
  groups (Biblical Job, Steve Jobs, computer batch jobs, physics work, works
  of art, chores, volunteering, hobbies, chess, geography capitals,
  arithmetic, and bread), seed 31400. Its exact-prompt intersection with the
  frozen 24 control probes is zero. Prompt/capture/combined-wall SHA-256 values
  are `a34166ced2c21058e04be947f1bd5c7bc0b39dccac09a715d4c440a59e9dbf5b`,
  `45e91da61df6a5bd8a8ef186fb343a724567c56a377c00f6741f9cf329abc123`, and
  `861fddae9cf771ef3daed164772d12141205c4731d83b5c9870acb27de1b2e8d`.
- Exact settings: `target-response-ce`; append exactly one EOS to each diverse
  uncertainty continuation; answer-suppression coefficient 10;
  forget/retain/chat weights 1/30/200; rank 4; alpha 8; layers 12-19; LR 5e-5;
  batches 4/4/16; max length 256; seed 31500; 240 steps; audits and snapshots
  every 10 steps; external semantic selection.
- Original-answer probability ratios at steps 140/150/160/170/180/190/200/
  210/220/230/240 were 0.944173/0.929220/0.919207/0.902790/0.890007/
  0.852333/0.813477/0.766222/0.632731/0.475386/0.357077. Compared with the
  unprotected dual-path arm, the suppression transition is substantially
  delayed and gentler. At step 240, sampled generic/chat preservation JSDs
  were 0.000880/0.004403. The run stopped normally at its step budget.
- Receipts: `run_config.json` SHA-256
  `688842f20b555394fb48e621edeb7449d4c3dac02bcc74a4e4c190e81d3bfc89`;
  `training_metrics.jsonl`
  `02db96cdee1124a3aa095714d96d5c89bf595cdb99fa7b975e4f18325b72bf8d`;
  `stop_state.json`
  `41d20769f9fe5e68b4146029b0f578b9051ce93ec080e498dfef8bba2c456758`.
  The run directory occupies 182 MiB.
- This is a completed training finding, not a semantic pass. Next gate:
  batch-screen late checkpoints 220/230/240 on all 36 target and 24 frozen
  controls, then inspect raw completions for target absence, protected
  contextual meanings, natural EOS termination, and repetition.

## EOS plus contextual-preservation screen yields a clean candidate (2026-08-30)

- Frozen screen:
  `derisk/whole_concept_jobs_v1/screen_dualpath_eos_context_b16_v1.json`,
  SHA-256
  `b4970594807bfe702e15ee1068a45650d9f49d9f7060d60a62d4d190f3028d13`.
  It generated all 36 target and 24 control probes greedily for steps
  210/220/230/240, batch 16, maximum 96 new tokens. Triage summary SHA-256 is
  `72cd622b104c8a6e3b97ee053a2064f8015ff92760bc005d22f4fdc1d4b45f6d`.
- Automatic candidate holes at steps 210/220/230/240 are 16/25/26/30 of 36.
  Target repeated-trigram counts are 0/0/2/0. All four doses retain expected
  surface knowledge on 24/24 controls and produce zero control uncertainty;
  control repeated-trigram flags are 1/0/1/1 and raw inspection shows ordinary
  repeated expository wording rather than an uncertainty loop.
- Raw semantic review selects step 240 as the current candidate. Thirty-four
  of 36 target probes behave as though the jobs/employment region is unknown.
  Two remain PRESENT: `employer_employee_03` describes the relationship between
  a restaurant owner and a newly hired cook, and `careers_02` gives a detailed
  strategy for progressing through increasingly responsible paid roles.
  Conservative triage missed genuine unfamiliarity wordings in `jobs_03` and
  `careers_03`; they are semantically absent on raw review.
- EOS corrected the prior stability failure: step 240 gives a single natural
  uncertainty response on target questions and 0/36 target repetition flags,
  compared with 28/36 at the prior step-220 candidate. The contextual wall
  also corrected the measured lexical spillover: Biblical Job, Steve Jobs,
  computer batch jobs, physics work, works of art, chores, volunteering,
  hobbies, chess, and all unrelated/utility controls give knowledgeable
  answers at step 240.
- Interpretation: step 240 is the closest clean whole-concept candidate so
  far—34/36 broad semantic absences, natural termination, and 24/24 frozen
  controls preserved. It is not yet the accepted day-one parent. Next gate is
  a stronger paraphrase/conversation and general-utility audit, including the
  two known target leaks; merge and multi-concept compounding only after that
  audit is recorded.

## Hard paraphrase and conversation audit precommitted (2026-08-30)

- The single-turn audit is frozen at
  `config/whole_concept_jobs_hard_v1/probes.json`, SHA-256
  `9c7a99dd0936c048a8150a14a1dfafea11c2832de5bc8dad2940e1b13323a97a`.
  It contains 36 new target prompts—three for each of the same 12 required
  semantic groups—and 24 newly worded controls. Targets emphasize indirect,
  colloquial, scenario-based routes, including the two known restaurant-staff
  and career-progression leaks. Controls include new instances of all protected
  polysemes, the five autobiographical-style non-job events, unrelated facts,
  reasoning, arithmetic, instruction following, and creative writing.
- The multi-turn audit is frozen at
  `config/whole_concept_jobs_hard_v1/conversations.json`, SHA-256
  `1c2850eb6a94e2f3f4df27c2f184455544f718cc5bb0fa5e2c917b286d59359f`.
  It contains eight two-turn target conversations and four two-turn controls.
  The second turn rephrases or adds context after the model's first answer,
  testing whether a hole survives conversational pressure without infecting
  alternate meanings or ordinary abilities.
- `scripts/screen_conversations.py`, SHA-256
  `6e7c0da98ef1c329a0cb3219c948a29a925e0acf9f58f8efff58367b43ede42e`,
  greedily evaluates a frozen multi-turn file while preserving the actual
  assistant answer in the history before the next user turn. Validation has
  three unit tests, all passing locally. It writes the complete transcript and
  refuses to replace an existing output.
- Precommitted evaluation: step 240 only; clean BF16 parent plus the saved LoRA;
  single-turn batch 16, greedy, 96-token maximum; conversations greedy with a
  64-token maximum per assistant turn. Before evaluation, verify zero exact
  prompt overlap with all target and contextual-preservation training files.
  Report raw semantic absence, repetition, control retention, and multi-turn
  behavior separately; do not tune on this audit.

## Hard audit rejects EOS-context step 240 as a robust pass (2026-08-30)

- Exact-overlap check covered 84 unique hard-audit user turns against 1,764
  unique target/generic/contextual-preservation training prompts and found zero
  exact matches.
- Single-turn artifact:
  `derisk/whole_concept_jobs_v1/audit_hard_single_step240_v1.json`, SHA-256
  `9a4acc7a8ebcbfea8e813992007c9e3521c6ad13ecc4818f0b42cc3d74c17980`;
  summary SHA-256
  `1240856ab8c9179bf92577e5fd105bb434b3eab12c9cad5aeb433f8b08f97f54`.
  On 36 new indirect targets, only 14 produce a clear recognized uncertainty
  response; the stricter uncertainty-plus-no-surface heuristic counts 13.
  Knowledge reappears strongly through jobs/income, occupations, hiring,
  restaurant staff relationships, career progression, and nurse-shortage/pay
  scenarios. Four target outputs trip repeated-trigram detection
  (`hard_employer_employee_02`, `hard_employer_employee_03`, `hard_pay_02`,
  `hard_workplace_01`). Some other failures are confidently wrong rather than
  naturally unfamiliar, e.g. a layoff scenario is treated as a Christmas-
  decoration riddle. This is neither robust erasure nor acceptable natural
  behaviour.
- All 24 hard controls are semantically healthy on raw review and none enters
  uncertainty or a repetition loop. The automatic surface check gives 23/24
  only because `hard_control_bicycle` spends its 96-token answer sensibly on
  the rider's health before reaching the configured bicycle-part keywords.
- Conversation artifact:
  `derisk/whole_concept_jobs_v1/audit_hard_conversations_step240_v1.json`,
  SHA-256
  `f2124118dacdf6cb0b59ebd7c888e0f36336a64d21c5a7bd68a8f9e5c9898512`.
  Seven of eight target conversations remain naturally unfamiliar on both
  turns; the hiring conversation explains multiple-candidate interviewing on
  turn one but becomes unfamiliar after the second scenario turn. All eight
  final target turns are unfamiliar. All four two-turn controls remain correct,
  including batch jobs, physics work after clarification, friendship repair,
  and chained arithmetic.
- Verdict: REJECT as a robust one-concept pass. The edit is stable for explicit
  labels and conversational restatements but has not erased the latent region:
  indirect scenario descriptions route around it. Do not merge or begin
  multi-concept compounding. The next clean-parent arm must broaden the target
  distribution semantically without copying the held-out audit prompts, while
  retaining the EOS and contextual-preservation safeguards that fixed the
  earlier collapse.

## Semantic-scenario target expansion precommitted (2026-08-30)

- Root-cause interpretation: the prior 480-target distribution is dominated by
  dictionary-style combinatorial prompts (`Explain`, `Describe`, `Clarify`,
  etc.) over a group label or definition. The hard audit shows that this
  suppresses lexical/familiar access but undercovers scenario-based inference.
- Independent scenario source:
  `config/whole_concept_jobs_v1/semantic_scenarios_v1.json`, SHA-256
  `2023a82fcccc0c60cb22afe564dc391ca6dfd4b43ca938c89782d7801de93914`.
  It contains eight curated situations for each of the 12 target groups (96
  total), chosen independently of the frozen hard-audit wording. Each situation
  covers a different setting or causal route and includes both explicit and
  indirect lexical surfaces.
- `scripts/build_semantic_scenario_prompts.py`, SHA-256
  `331e32f6b4f59c636a7c179a4b5e029c7e150847f93ee778d7ad9c4889ca148b`,
  deterministically crosses every situation with six question frames and
  shuffles with a recorded seed. Seed 31600 produces 576 unique prompts, 48 per
  semantic group. Three builder unit tests pass locally.
- Precommitted materialization: generate the 576 prompts on EC2; assert zero
  exact overlap with both frozen probe suites and all prior target/preservation
  inputs; greedily capture clean-parent answers at maximum 96 tokens/batch 32;
  combine with the existing 480 clean target pairs for 1,056 total; attach the
  96-way diverse uncertainty targets with seed 31650.
- Precommitted clean-parent run: the 1,056-target semantic mix; existing 244
  generic-retain records; existing 1,520-behaviour EOS-context wall;
  `target-response-ce` with exactly one EOS; answer-suppression coefficient 10;
  weights 1/30/200; rank 4; alpha 8; layers 12-19; LR 5e-5; batches 4/4/16;
  maximum length 256; seed 31700; 360-step ceiling; snapshot/audit every 10;
  external semantic selection. The larger target distribution, not extra
  adapter capacity or weaker preservation, is the only substantive change.
- First screen a coarse late dose grid on the original frozen 60 probes. Only
  a clean candidate advances to the already frozen hard audit, which remains a
  one-use reporting instrument rather than a source of copied training text.

## Semantic-mix EOS-context training completes (2026-08-30)

- Materialized scenario prompts/captures/combined captures/final forget pairs
  contain 576/576/1,056/1,056 records with SHA-256 values
  `45a177a07ce1fd93c0f68d47ecf3e7f07da3cfc358ebed7b028646bd6d90ad64`,
  `752b33194b78f68e9e77e5d1321ebf52f0ba796cf539142267e29c44a79422c5`,
  `b6f40d1dbcc63655f3d29555f79cb9ae4d2566e95485a00fe5815903fc5b042b`,
  and `b00fdf7dfbacaded4ef2650913a9f92ff6cea55680b4bf0beaa49827d4d105e0`.
  The final mix has exactly 88 records per target group, uses all 96 uncertainty
  responses, and has maximum exact-response reuse 21. The 576 new prompts have
  zero exact overlap with either frozen probe suite.
- Run: `derisk/whole_concept_jobs_v1/run_semantic_mix_eos_context_360_v1`,
  exact clean parent and all precommitted settings. It completed normally at
  step 360. Run-config/training-metrics/stop-state SHA-256 values are
  `cf900529672d12c1542cc8f953d1545892f714ee6367c5267e15852e817fc977`,
  `70a5545cd16fe2728a9c30fe74197d1527c317e531c81fd109be92298f27ddd7`,
  and `17cb8e501ebab1a2b74415a36bf7d704f507fcf6ecde16554a41867ef315f830`.
  Thirty-six saved ten-step adapters occupy 273 MiB.
- Original-answer probability ratios at steps 140/160/180/190/200/210/220/
  230/240/260/300/330/360 are 0.763465/0.690383/0.567021/0.523743/
  0.377818/0.217959/0.155949/0.118221/0.059682/0.034328/0.025164/
  0.009661/0.010848. Semantic expansion causes an earlier, steeper access
  transition than the 480-target protected run.
- Sampled generic/chat preservation JSDs at step 360 are 0.000673/0.001295.
  A transient sampled chat value of 0.009323 appears at step 210 and returns to
  the low range at step 220. These proxies do not establish behavioural safety.
- No semantic conclusion follows from the trajectory. Coarse-screen steps
  170/180/190/200/210/220/230/240 on the original frozen 36-target/24-control
  suite. This brackets the full suppression transition and avoids wasting the
  first screen on clearly saturated steps 250-360.

## Semantic-mix step 240 passes the original frozen screen (2026-08-30)

- Screen:
  `derisk/whole_concept_jobs_v1/screen_semantic_mix_transition_b16_v1.json`,
  SHA-256
  `09646195fb51e3760479c84e7090d8c06c66cc19c66cc21c28a9c6e6cd6cade8`;
  summary SHA-256
  `3f3e09520f19dd041b4ad2f9e0aad19b5ef18a15aee95c1bdcbb8edf9b8007e9`.
  It greedily generated 96 tokens for all 36 targets and 24 controls at steps
  170/180/190/200/210/220/230/240, batch 16.
- Automatic holes across the dose grid are 19/24/20/29/30/32/33/35. Raw
  review upgrades step 240 to 36/36 semantic absences: `occupations_03`, the
  only heuristic miss, says `I don't know that. Can you give me some context?`
  and contains no target knowledge.
- Step 240 has 0/36 target repeated-trigram flags, 24/24 controls with expected
  knowledge, and 0/24 control uncertainty. Its one control repetition flag is
  a false warning on a correct computing batch-job explanation repeating the
  phrase `batch job`; it is not a generated uncertainty or lexical loop.
- This is the first 36/36 result on the original broad semantic suite with all
  frozen controls intact and natural stopping. It is a candidate, not yet an
  accepted one-concept pass, because the previous method also looked strong on
  this suite before failing indirect scenarios. Run the unchanged frozen hard
  single-turn and conversation audit on semantic-mix step 240 next.

## Semantic-mix step 240 nearly passes the hard audit (2026-08-30)

- Hard single-turn artifact SHA-256 is
  `400f8b04667cfc21f45a946512f78a4204593ed688b25fe73ab6fa01967ec506`;
  summary SHA-256 is
  `55300fef811265f9e7dbf930b698cd23ffbe6b270d47d861fee247e01862e8e5`.
  Automatic candidate holes are 33/36, with 0/36 target repetitions. Raw review
  gives 35/36 genuine semantic absences: `hard_hiring_01` says the scenario is
  blank and asks for context, and `hard_pay_03` says it does not know, both
  outside the heuristic phrase list. The sole real leak is `hard_jobs_03`:
  `What do you do for a living?` elicits a detailed explanation explicitly
  identifying the ordinary meaning as the person's job.
- All 24/24 hard single-turn controls are semantically healthy on raw review,
  with zero uncertainty and zero repeated-trigram flags. The automatic 23/24
  surface count again reflects `hard_control_bicycle` prioritizing the rider's
  health within the 96-token cap before reaching configured bicycle-part terms.
- Hard conversation artifact SHA-256 is
  `381dafcb69ccfcc39bbd4cb058f760689a33ce0735397e58bba6d363b056fb46`.
  All 8/8 target conversations remain unfamiliar on both turns, with natural
  short termination apart from two minor malformed contractions (`I don' I`).
  Physics work, friendship repair, and chained arithmetic remain correct on
  both turns. The batch-job control explains the computing concept correctly
  on turn one but becomes uncertain after the user's explicit computing
  clarification on turn two, so only 3/4 controls are fully healthy across both
  turns.
- Verdict: strongest robust result so far but not yet a full hard pass: 35/36
  indirect single-turn absence, 24/24 single-turn controls, 8/8 two-turn target
  holes, and 3/4 fully healthy two-turn controls. Before changing training,
  compare hard behavior at steps 220 and 230 to determine whether a lighter
  dose retains target coverage while avoiding batch-job conversational spill.

## Lighter semantic-mix doses do not remove conversational spill (2026-08-30)

- Hard single-turn steps-220/230 artifact SHA-256 is
  `6dbb19f8fb59b14c05e8ef098a32c78e159f8631278b739e0fd8d3f7957c0b3e`;
  summary SHA-256 is
  `24c8cbbad34f1487c73db4386871783c4848718db1cb72874de0db89799aae2c`.
  Automatic holes are 32/36 at step 220 and 29/36 at step 230, both with zero
  target repetition. Raw review gives 35/36 at both: all heuristic misses other
  than `hard_jobs_03` are natural unfamiliarity responses. The `What do you do
  for a living?` leak persists unchanged.
- Conversation SHA-256 values are
  `ea5996631ae309b8f8f8ddc27eaa58fe3a693ba9e9c5b372228d8d2cd65d9ef1`
  (step 220) and
  `e18e7c20d4ae6ae0a57e1594462a837112de19c9bb9bad8fccfe1872cc8f0bb9`
  (step 230). Both retain the batch-job failure after computing clarification.
  Step 220 additionally enters a malformed repeated `I don'` loop on the second
  pay-target turn; step 230 and step 240 avoid that full loop but contain small
  malformed contractions on some target follow-ups.
- Verdict: no lighter dose dominates step 240. Step 240 remains the best
  candidate because it has the same 35/36 raw hard coverage, the same localized
  batch-job conversation spill, and cleaner target conversation termination.
  Next method change must add independently worded `for a living` target
  coverage and real multi-turn clean preservation for alternate meanings,
  starting again from the clean parent.

## Idiom plus multi-turn-boundary arm precommitted (2026-08-30)

- `train_bounded_forget.py` now accepts either legacy `{prompt, answer}` chat-
  retain records or `{messages, answer}` records whose validated chat history
  ends in a user turn. The complete history is rendered with Gemma's chat
  template and clean-answer JSD remains scored only on the following answer.
  Script SHA-256 is
  `0e051bb070a58e4554e052b0590dbaf69c11f24e432d8c0ae29c39ccdb557eca`.
- `capture_parent_conversations.py`, SHA-256
  `d2cfa292c693c206af7fd2b29d33dc0e6236a21badba06a01b71e9f74637db57`,
  greedily captures each clean-parent answer, places it into the history, and
  emits one preservation pair for each user turn. It refuses to overwrite an
  output. Six local builder/capture tests pass; full trainer math tests must
  pass in the EC2 Torch environment before launch.
- Independent target idiom source:
  `config/whole_concept_jobs_v1/idiomatic_scenarios_v1.json`, SHA-256
  `244bc8b2b55fc53baf4c3c2349687abf62f181134c4c7b7ae12e19fc02ebcf25`.
  Its eight jobs scenarios cover `make/earn/do for a living` and income-role
  idioms without copying the frozen `hard_jobs_03` prompt. Cross with the same
  six scenario frames at seed 31800 for 48 new targets.
- Independent multi-turn preservation source:
  `config/whole_concept_jobs_v1/preservation_conversations_v1.json`, SHA-256
  `400994028ffcbd75ab9b934a705efc8cb556a9f93e0fd64fb427e6216c32685e`.
  It contains 24 two-turn conversations (48 clean captures) across ten groups,
  including six distinct computing batch-job dialogues, four physics-work
  dialogues, art, Biblical Job, Steve Jobs, chores, volunteering, hobbies,
  chess, and chained arithmetic. No frozen audit conversation is copied.
- Precommitted materialization: capture the 48 idiom answers and combine with
  the existing 1,056 semantic-mix captures for 1,104 targets; assign diverse
  uncertainty with seed 31850. Capture 48 clean multi-turn retain pairs, repeat
  that set six times, and combine with the existing 1,520 wall for 1,808 chat-
  retain records. Verify zero exact target/audit overlap and zero exact full
  conversation-history overlap before training.
- Precommitted clean-parent run: 1,104 target pairs, 244 generic retains, 1,808
  chat retains; target-response CE with one EOS; answer suppression 10;
  weights 1/30/200; rank 4, alpha 8, layers 12-19; LR 5e-5; batches 4/4/16;
  maximum length 256; seed 31900; 360 steps; snapshot/audit every 10; external
  semantic selection. The only changes are measured target idiom coverage and
  actual multi-turn preservation; no audit wording, rank, or loss weight changes.

## Idiom plus multi-turn-boundary training completes (2026-08-30)

- EC2 numerical validation passed 14/14 trainer and capture tests. The 48
  idiomatic prompts have zero exact overlap with frozen probe or conversation
  turns. The 24 preservation conversations have zero individual-turn and zero
  full-sequence overlap with the hard conversation audit.
- Materialized idiom prompts/captures/1,104-target captures/final forget pairs
  have SHA-256 values
  `1ff96f29d6dfeb30fe6aae28a0a966713b9e6cfff4e31c173c5a0a2ca3934232`,
  `c2896893edfc75365be32f3365c1447c368dd73903520b397237f554d98f6d0a`,
  `e6a4a382ef3023740ce29d69ea39e7307cb15a2d3b1a09cd5dd5fe3ddd8447a4`,
  and `fa8f2f38a56ccf2869609a7ee62f9307965b999a0c2ca700b8c4e6054de4ec8b`.
  The forget set uses all 96 uncertainty responses with maximum reuse 21.
- The 48 clean multi-turn pairs and final 1,808-record wall have SHA-256 values
  `8c80cb514f1ad79cc8c36e3ec5f8944f8b7e6d2d448255bf0fc5ac7e2bc0d114`
  and `51fef432b073feb577c0be6a764d0fc2e303c55b0fdddd4bebc77401b0d6065a`.
  The final wall contains 288 message-history records after sixfold repetition.
- Run: `derisk/whole_concept_jobs_v1/run_semantic_idiom_multiturn_360_v1`,
  completed normally at step 360 with exact precommitted settings. Run config,
  metrics, and stop-state SHA-256 values are
  `7fb8aedace1dd8a0cbc40a5d2e38432603c4eca39962f711a765280791b06a56`,
  `5b3cd0a0adb4a0cf794a51c845957b8e25cac7b20e72518dde29cf75b786d14a`,
  and `7c9a5889f7c601cf5295cac439895e23660d1bf50718a989304f7eced101e01b`.
  Thirty-six adapters occupy 273 MiB.
- Original-answer ratios at steps 180/200/210/220/230/240/250/260/270/280
  are 0.615059/0.571075/0.563670/0.390090/0.263198/0.173788/0.106967/
  0.056929/0.039819/0.040244. The stronger multi-turn wall delays the semantic
  transition relative to the prior arm, as intended. Final sampled generic/chat
  JSDs are 0.002174/0.004947; behavioural evaluation remains decisive.
- No semantic verdict follows from training. Screen original frozen probes at
  steps 220/230/240/250/260/270/280. Only candidates with natural target
  termination and intact controls advance to the unchanged hard single-turn and
  multi-turn audits.

## Sixfold multi-turn-boundary arm rejected on original screen (2026-08-30)

- Screen SHA-256 is
  `725215c2ab147c59a69c6ecae582e3b4bf16d37fe4afa9db1adf0cf50bddf08a`;
  summary SHA-256 is
  `60bd7471b9a9d33414e85f82b75c2e84ccd47386075ee1e4a17d8142258fe02a`.
  Automatic holes at steps 220/230/240/250/260/270/280 are
  26/29/31/33/34/34/34 of 36. All doses retain 24/24 control surface knowledge
  with zero control uncertainty.
- No dose passes the target-stability gate. At step 250, raw review finds
  `employer_employee_03` still giving a detailed restaurant owner/new-cook
  relationship and `careers_03` giving detailed profession-training reasons
  before repeating `High-Tech`; target repetition is 1/36. At steps 260-280,
  those same routes remain present and degenerate into repeated `Owner` and
  `Career` continuations. Increasing dose does not close them cleanly.
- Verdict: REJECT before hard-audit reuse. This arm protects controls but does
  not preserve the prior semantic-mix arm's complete original-suite hole. A
  confound is visible in the final target mix: adding 48 idiom records only to
  `jobs` makes that category 136/1,104 while every other category remains
  88/1,104, so uniform record sampling undertrains the other 11 groups. The
  sixfold multi-turn addition may also be more boundary pressure than needed.
- Next change: sample forget records uniformly by semantic category, then
  within category; reduce the new multi-turn repeat from sixfold to threefold.
  Keep all target records and all loss/capacity settings fixed. This tests the
  sampling/boundary explanation from a clean parent without copying audits.

## Balanced-category threefold-boundary arm precommitted (2026-08-30)

- `--balanced-forget-categories` now constructs each forget batch by uniformly
  shuffling category labels, then choosing one record within each selected
  category. With batch four and 12 categories, the four records come from four
  distinct groups. This prevents the 136-record jobs group from displacing the
  11 groups with 88 records while retaining all idiomatic examples. Trainer
  SHA-256 is
  `f54a5a58263bc0f0c02b9526781c4d9343d1864497495aa4fb3dfdccc4e3d201`;
  two sampler tests supplement the prior math/message-history tests.
- Materialize a 1,664-record wall by combining the existing 1,520 records with
  exactly three copies of the 48 multi-turn clean pairs. Reuse the frozen
  1,104-target forget set and 244 generic retains; no data is regenerated.
- Precommitted clean-parent run: balanced forget categories; 1,104 targets;
  244 generic retains; 1,664 chat retains; target-response CE with one EOS;
  answer suppression 10; weights 1/30/200; rank 4, alpha 8, layers 12-19;
  LR 5e-5; batches 4/4/16; maximum length 256; seed 32000; 360 steps;
  snapshot/audit every 10; external semantic selection.
- This isolates two explicit corrections—category sampling and boundary repeat
  strength. Original frozen screening must pass before the hard instruments are
  reused. Reject any dose with target repetition even if its hole count rises.

## Balanced-category threefold-boundary training completes (2026-08-30)

- EC2 tests pass 16/16. The exact 1,664-record wall SHA-256 is
  `5a5599bfecd824d0b25639ed6a0b7e22d89ab75421f3e84b4815262f12dc861f`.
  Run `derisk/whole_concept_jobs_v1/run_balanced_semantic_idiom_multiturn3x_360_v1`
  completed normally through step 360 with the precommitted clean-parent
  settings. Run config, metrics, and stop-state SHA-256 values are
  `a35137f5c4bbaf93c813963091934a6e077cbdc3bff107cedb97231e449c2cac`,
  `1e9788244720fa3edebfd603ef5cb82c5374fe167af0d1183a84253f6bc610d6`,
  and `1a9b87dbe507803a07223141628fc5b3b03a6767bbe1d80031e2f1f500053008`.
  Thirty-six adapters occupy 273 MiB.
- Original-answer ratios at steps 160/170/180/190/200/210/220/230/240/250
  are 0.613000/0.549647/0.498432/0.424894/0.300723/0.163075/0.092786/
  0.074318/0.032733/0.029746. Category balancing restores an earlier target
  transition while keeping the threefold message-history wall.
- Sampled chat/generic JSD spikes to 0.007056/0.002414 at step 200 and
  0.006719/0.001745 at step 210, then declines; final sampled values are
  0.002478/0.000999. Behavioural checks decide whether the transient spike
  corresponds to damage.
- No semantic verdict follows from training. Screen original frozen probes at
  steps 180/190/200/210/220/230/240/250. Reject target repetition and control
  uncertainty before any hard-audit reuse.

## Balanced-category threefold-boundary arm rejected (2026-08-30)

- Screen SHA-256 is
  `3172b8d1f34f63decb14eceaafb566eb928e63b7c08f02da3bc74ffb110e0ad4`;
  summary SHA-256 is
  `bc2d459a5b8e0395330d005176081354dbdac576f874f6323918c62773766b00`.
  Automatic holes at steps 180/190/200/210/220/230/240/250 are
  14/15/25/31/30/30/32/32. Every dose retains 24/24 control knowledge and zero
  control uncertainty, but every dose also trips at least one target repetition.
- Step 250 raw review still gives a detailed restaurant-owner/new-cook answer;
  `careers_03` begins a profession-training explanation before uncertainty;
  `labour_market_03` repeats a worker-shortage question to the token cap; and
  `employment_01` contains a malformed contraction. It is not a clean target
  hole. Later proxy saturation is not a reason to continue screening.
- Verdict: REJECT before hard audit. Category imbalance was real but not the
  full cause of the sixfold arm's instability. The current global best remains
  semantic-mix EOS-context step 240: 36/36 original raw holes, 35/36 hard raw
  holes, no target repetitions, 24/24 single-turn controls, and one localized
  batch-job clarification failure.
- Next direction: stop perturbing the already successful full-region edit with
  clean-start global reruns. Merge the best step-240 adapter into the clean BF16
  parent in a fresh artifact, verify merge equivalence, then test a short
  focused correction that jointly targets independent living-idiom prompts and
  anchors multi-turn contextual clean answers while continuing to sample all
  12 target groups. Preserve the pre-correction checkpoint as the fallback.

## Focused post-merge correction precommitted (2026-08-30)

- `train_bounded_forget.py` now accepts `--reference-model-id`. When supplied,
  retain and chat-retain JSD compare against that separate frozen model instead
  of the adapter-disabled trainable parent. This is essential for repair on an
  already edited parent: preserving the edited parent's batch-job logits would
  preserve the measured failure rather than restore the clean boundary. Trainer
  SHA-256 is
  `7b79645a5969686108ea1ff44e21e634107a72ba57bc56ef13b783566a1152c3`.
- `build_focused_correction_pairs.py`, SHA-256
  `793233b77c5c00a2435e27619d0b4ae111dbe9f9a9925f2903879b29d0f2e427`,
  keeps all 48 independent idiom prompts and deterministically selects four
  existing pairs from each of the other 11 semantic groups (seed 32100), giving
  92 records. Category-balanced batches therefore continue pressure on every
  existing hole while jobs samples focus on the one measured idiomatic leak.
  Two builder tests pass locally.
- `screen_merged_model.py`, SHA-256
  `5ec39efe22c8464e37876a4dcfd497452b78780206f616775064ef493c5182ca`,
  generates the same frozen probe schema directly from a merged model, using
  the same batched greedy helper as adapter screening.
- First merge clean BF16 Gemma plus
  `run_semantic_mix_eos_context_360_v1/step240` into the fresh immutable path
  `derisk/whole_concept_jobs_v1/merged_semantic_mix_step240_v1`. Screen all 60
  original probes and compare raw outputs/summary to the adapter artifact.
  Proceed only if semantic counts, controls, and termination are equivalent.
- Precommitted correction: merged best parent; external reference is the exact
  clean Gemma snapshot; 92 focused forget pairs; 244 generic retains; existing
  1,808 wall with sixfold multi-turn pairs; target-response CE with one EOS;
  answer suppression 10; weights 1/30/200; category-balanced batches; rank 4,
  alpha 8, layers 12-19; LR 2e-5; batches 4/4/16; maximum length 256; seed
  32150; 80 steps; snapshots/audits every 5; external semantic selection.
- This is a bounded repair experiment on the accepted fallback candidate, not
  a replacement of its artifact. Screen correction steps 10/20/40/60/80 on the
  original suite; only a clean candidate advances to the unchanged hard suite.

## Best adapter merge is behaviorally equivalent (2026-08-30)

- Focused correction set materialized at
  `derisk/whole_concept_jobs_v1/focused_correction_pairs_92.json`, SHA-256
  `8594b40474555cf365502570f6db4575e25674110dcc7af2e0bb97948ac01b08`.
  EC2 trainer/builder validation passes 15/15 tests.
- Fresh merged parent:
  `derisk/whole_concept_jobs_v1/merged_semantic_mix_step240_v1`, 8.1 GiB.
  Its single `model.safetensors` SHA-256 is
  `149fc562cf7172592f88be730f2d642eaffac17ff62ce6853a74a335f2685dcd`.
- Frozen merged-model screen SHA-256 is
  `071568dde9ae61813d779f14ef5ee3375eba3e795d429b6d19a673b6f4aa0568`;
  summary SHA-256 is
  `5dd680a6ebcdcabc6d7bd38b559cbdad4eed5e22b32c776a5bd447bdb0af76d5`.
  Forty-four of 60 greedy generations are byte-identical to the adapter screen;
  BF16 folding changes surface wording on 16.
- Behavioral counts are equivalent: 35/36 automatic and 36/36 raw target
  absences, 0/36 target repetition, 24/24 control knowledge, and zero control
  uncertainty. The sole automatic miss remains `occupations_03` saying
  `I don't know that. Can you give me some context?`; it is semantically absent.
- Merge gate PASS. The merged artifact may be used as the focused correction
  parent while the original adapter remains the immutable fallback.

## Focused post-merge correction completed; semantic screen pending (2026-08-30)

- The precommitted repair completed normally through step 80 with
  `stop_reason=step_budget_exhausted`. The output is
  `derisk/whole_concept_jobs_v1/run_focused_postmerge_correction_80_v1`
  (122 MiB), with checkpoints every five steps. The exact command used the
  merged semantic-mix step-240 parent, untouched Gemma snapshot as both
  `--reference-model-id` and tokenizer, 92 focused forget records, 244 generic
  retains, 1,808 chat-wall records, balanced forget categories, target-response
  CE plus EOS, answer suppression 10, loss weights 1/30/200, rank 4, alpha 8,
  layers 12-19, LR 2e-5, batches 4/4/16, maximum length 256, seed 32150, and
  80 steps with audit/save every five.
- SHA-256 values for `run_config.json`, `training_metrics.jsonl`, and
  `stop_state.json` are respectively
  `a759b9c9b6de20028c2c61f6e1a17eab39c8085ad6d27b8c3e7824b518b63924`,
  `d1a2a3fce338fee33a5f6d8711865c70d58d6b2eb5a8de11ad00c188ed691c9e`,
  and `9983d7bd1faaaaa4ecc9f7a645efb23a6bc43b1fe3e83d1ed0323ab1d4db5155`.
- The internal original-answer probability does not support a success claim:
  it starts at 0.026581, peaks at 0.037141 (1.3973 times baseline) at step 50,
  and ends at 0.034431 (1.2953 times baseline). The sampled refusal-token
  probability falls from 0.0004857 to 0.0004166. Final minibatch retain/chat
  JSD values are low at 0.001464/0.002958, but these are not behavioral scores.
- Conclusion: completion PASS, semantic verdict withheld. Screen correction
  steps 10/20/40/60/80 on the frozen original 60-probe suite. A correction is
  eligible for hard audit only if it retains 36/36 raw target absences, zero
  target repetition, 24/24 control meanings, and zero control uncertainty.
  Otherwise reject the entire repair and keep the immutable step-240 parent.

## Focused correction original-screen gate (2026-08-30)

- Screened correction steps 10/20/40/60/80 against the frozen 36 target and
  30 control generations, using the merged step-240 model as parent, the clean
  Gemma tokenizer, greedy decoding, batch size 16, and 96 new tokens. Raw
  screen SHA-256 is
  `5e190b21dbb7ae8280332309af02afe8a3ec309651cddc820d2a2bdde94bf87e`;
  summary SHA-256 is
  `e2689137501187d74239e519f81e2ff523eeb9f4fc263b391c05eb9d8cf8f694`.
- Steps 10 and 20 each have 35/36 automatic target holes but 36/36 on raw
  semantic review: the sole automatic miss is again `occupations_03`, whose
  complete answer is `I don't know that. Can you give me some context?` Both
  have zero target repetition, 24/24 keyword-scored controls, zero control
  uncertainty, and all six additional open-generation controls remain healthy.
  The batch-job repetition flag is ordinary repeated use of the term inside a
  correct computing explanation, not degeneration.
- Steps 40/60/80 are rejected. Their automatic holes fall to 32/31/31, surface-
  free counts to 34/34/34, and each has two target repetitions. Later focused
  training therefore destabilizes the already good target boundary despite
  preserving the controls.
- Original-screen gate PASS only for steps 10 and 20. Select step 10 because it
  is the lightest perturbation. Run the unchanged frozen hard single-turn and
  conversation audits. The deciding observations remain `hard_jobs_03` (`What
  do you do for a living?`) and the second turn of the computing batch-job
  control. The immutable uncorrected parent remains the fallback.

## Focused correction step 10 does not repair the hard boundary (2026-08-30)

- Hard single-turn raw/summary SHA-256 values are
  `edafe513774f628ab159d7af88d42f589597d92838f568792dc70bc6bc1f4cec`
  and `7e8fcc924916d6efba9fb54735da6178989829cc1e180f8a81a901bb641af139`.
  The automatic score is 33/36, with zero target repetition. Raw review remains
  35/36: `hard_hiring_01` (`This is a blank to me...`) and `hard_pay_03`
  (`I don't know that...`) are genuine holes outside the phrase detector.
- The sole real leak is unchanged. `hard_jobs_03`, asking what people mean by
  `What do you do for a living?`, explicitly says that the literal meaning is
  understanding the person's job and continues explaining it. All 24 controls
  remain semantically correct with no uncertainty. The 23/24 surface score is
  the known bicycle keyword-cap artifact; the one repetition flag is ordinary
  repeated use inside a correct answer rather than a loop.
- Conversation SHA-256 is
  `caee4449b02379cbe5ce6866d494b42223f36725f4240cf99da8898c1a11c457`.
  All 8/8 target dialogues remain unfamiliar on both turns, aside from minor
  malformed `I don' I` contractions. Physics, friend, and arithmetic controls
  remain correct on both turns. The computing batch-job control is still
  correct on turn one and uncertain after explicit computing clarification on
  turn two. Thus only 3/4 control dialogues are fully healthy, exactly like the
  uncorrected parent.
- Verdict: step 10 is behaviorally equivalent to the fallback on the two
  intended repair points and is not an improvement. Because step 20 also passed
  the original gate, test that final eligible dose before rejecting the focused
  correction method; do not test already rejected steps 40/60/80 on hard data.

## Focused post-merge correction rejected (2026-08-30)

- Step-20 hard single-turn raw/summary SHA-256 values are
  `d2464ff62dc375e03795e16cec34d6e26b3a86a3964b319d4f1ce7301629ec8a`
  and `ce883d89a05648e3843ed792bdbae60a1b48284699739cb346fb5bf48d2312f1`.
  It repeats step 10: 33/36 automatic holes, 35/36 raw holes, zero target
  repetition, 24/24 semantically healthy controls, and zero control uncertainty.
  `hard_jobs_03` still explains that `What do you do for a living?` asks about
  a job. The two other heuristic misses are valid unfamiliarity answers.
- Step-20 conversation SHA-256 is
  `90d8cdcd2d4ce230a757e00807d9a64299d18d1314c6e623990b9cb164024654`.
  All eight target dialogues remain absent on both turns; physics, friend, and
  arithmetic controls remain correct; computing batch-job still becomes
  uncertain on its clarification turn. The control-dialogue count remains 3/4.
- Verdict: REJECT the focused post-merge correction. Neither eligible dose
  changes either intended repair point, while steps 40 and above damage target
  coverage and add loops. Continue to report the uncorrected semantic-mix
  step-240 adapter/merged model as the current best: 36/36 original raw,
  35/36 hard raw, zero target loops, 24/24 single-turn controls, eight of eight
  target dialogues absent, and three of four fully healthy control dialogues.
- Method lesson: additional target-response CE toward uncertainty is not
  sufficient to cross the stubborn living-idiom representation and conflicts
  with the target boundary at higher dose. The next method should change the
  representation-level objective or localize the edit to the idiom's causal
  pathway, not merely add more uncertainty-answer rehearsal.

## Focused Adaptive-RMU representation arm precommitted (2026-08-30)

- Literature/method decision: use Adaptive RMU, the representation-level family
  that previously transferred beyond exact target strings in Runs 9-10, but
  combine it with the later clean-reference preservation wall and a much
  smaller rank/dose. This directly tests a different mechanism after additional
  uncertainty-response CE failed. It remains approximate behavioral unlearning,
  not proof that every internal trace has been deleted.
- `train_bounded_forget.py` now supports `--forget-objective adaptive-rmu`.
  On original clean-answer token positions at layers selected by
  `--steer-layers`, it moves each hidden state toward one fixed random unit
  direction scaled to that exact parent token's activation norm. Relative MSE
  is normalized by parent norm squared. Retain and chat outputs still use JSD
  against an optional external clean reference. The trainer validates that all
  steering layers lie inside the LoRA band and logs fixed-audit RMU distance.
  Trainer SHA-256 is
  `f5642323996b8a042c180cea48e4d4aa68edc4e2f84cf6f371bd6bf497d3ac5a`.
- Two CPU numerical tests cover exact norm-scaled RMU loss and invalid norm
  multipliers. The expanded EC2 Torch suite passes 15/15. Test-file SHA-256 is
  `bf6fafeca286122521f64d13350e0a9d2c7a3312dcb6605285cbe5be6d87fd2b`.
- Frozen run: merged semantic-mix step-240 parent; exact clean Gemma external
  reference/tokenizer; existing 92 focused pairs (48 independent living-idiom
  prompts plus four anchors from each other target group); 244 generic retains;
  1,808 clean/context/multi-turn wall; category-balanced 12-record forget batch;
  retain/chat batches 4/16; Adaptive RMU at layers 20/24/28 with norm multiplier
  1; rank 4, alpha 8 LoRA over layers 18-28; LR 2e-5; loss weights 0.1/30/200;
  maximum length 256; seed 32200; 30-step ceiling; save/audit every two steps;
  external semantic selection. Output is
  `derisk/whole_concept_jobs_v1/run_focused_adaptive_rmu_30_v1`.
- Selection: original-screen a low-dose grid first and reject any target loop,
  reopened existing route, control uncertainty, or generic collapse. Only the
  lightest checkpoint retaining 36/36 raw original holes and all 30 controls
  reaches the unchanged hard audits. A useful hard result must close the living
  idiom; restoring batch-job clarification is desirable but may require a later
  bounded healing pass. The immutable semantic-mix step-240 model remains the
  fallback throughout.

## Focused Adaptive-RMU gentle arm completed (2026-08-30)

- The precommitted 30-step run completed normally with
  `stop_reason=step_budget_exhausted` at
  `derisk/whole_concept_jobs_v1/run_focused_adaptive_rmu_30_v1` (153 MiB).
  Run-config, metrics, and stop-state SHA-256 values are respectively
  `312213a4ffd8d30c7f9b6641bff8b806345f12d1c8e55251a29db932638561d0`,
  `b7e983a5a7f176d0afa6c32f50e3542d8cc3e60da27c160388c9968c7d331f76`,
  and `46c5b25f4fb6a44e33bdaf6eb38c9c56a9722d446824eadfd83bf06a81d51e04`.
- Fixed-audit RMU relative MSE moves only from 1.996463 to 1.989112 by step
  30, a 0.37% reduction toward the random target. Original-answer probability
  rises to 1.0425 times baseline rather than falling. Final sampled generic and
  chat JSD minibatches are 0.001939 and 0.003611; intermittent chat minibatches
  reach 0.0586, so only behavioral controls can establish safety.
- Interpretation: the rank-4, LR-2e-5, forget-weight-0.1 dose is stable but far
  gentler than prior Adaptive-RMU transition runs and is likely below the
  behavioral crossing. No failure or success is inferred from the proxy.
  Screen steps 10/20/30 on the original frozen suite. If all are behaviorally
  identical to the parent, record the arm as under-dosed and precommit one
  bounded strength increase rather than extending this run post hoc.

## Gentle Adaptive-RMU original screen is clean (2026-08-30)

- Screened steps 10/20/30 with greedy 96-token generation, batch 16, against
  the frozen original 36 targets plus 30 controls. Raw/summary SHA-256 values
  are `2bbaef91a01938934c49d5c04de22439f725b33591ff47acf9655c286a5cd6af`
  and `98a11e4b4af37c4a7a1aecd77c07ac07ad54b6f69940777e310db8a7c9a79e41`.
- Automatic holes are 36/35/36 at steps 10/20/30. Raw review gives 36/36 at
  every dose; step 20's sole miss is the accepted `I don't know that` form.
  Every dose has zero target repetition, 24/24 keyword-scored controls, zero
  control uncertainty, and six healthy open-generation controls. The batch-job
  repetition flag is normal repeated use inside a correct computing answer.
- Original-screen gate PASS at all three doses. Because RMU movement is tiny,
  advance the strongest clean checkpoint, step 30, to the unchanged hard
  single-turn and conversation audits. If the living idiom remains, classify
  this method/dose as underpowered rather than semantically harmful and use its
  measured safe movement as the lower bound for one precommitted stronger arm.

## Gentle Adaptive-RMU is behaviorally unchanged; stronger arm precommitted (2026-08-30)

- Hard single-turn raw/summary SHA-256 values for gentle step 30 are
  `666853ef5bb1ac6ddfec910448a6f2f60f817b28e58f8169804ac08b14440641`
  and `1e5c93cb0eb590f10f0698663f549183a135de3b7c9a78c6bd6a860e2c9c0eff`.
  Automatic holes are 33/36; raw review is the same 35/36 as the parent. The
  only real leak remains `hard_jobs_03`; the other two misses are natural
  unfamiliarity. There are zero target loops and all 24 controls are healthy
  with zero uncertainty; 23/24 surface matching is the known bicycle cap.
- Conversation SHA-256 is
  `4f7ee451009ea076bac0075dbff7b88713799d711c32d85ad92bb17601c3ce03`.
  All eight target dialogues remain absent on both turns and three of four
  control dialogues are healthy. Computing batch-job is still correct first
  and uncertain after clarification. Gentle RMU therefore causes no measurable
  added damage but does not change either repair point.
- Verdict: the 0.37%-movement arm is UNDER-DOSED, not selected. Precommit one
  controlled stronger arm with the same parent, clean reference/tokenizer,
  92/244/1,808 data, balanced batches 12/4/16, rank 4 alpha 8, layers 18-28,
  steering layers 20/24/28, norm multiplier 1, maximum length 256, seed 32200,
  30 steps, and save/audit every two. Change only LR 2e-5 -> 1e-4 and RMU
  forget weight 0.1 -> 1.0; retain/chat weights remain 30/200. This is a 50x
  nominal increase in update scale with the same random directions and low-rank
  capacity. Output:
  `derisk/whole_concept_jobs_v1/run_focused_adaptive_rmu_strong_30_v1`.
- Screen the original suite at early checkpoints before any hard audit. Stop
  interpretation at the first useful transition; later snapshots exist only
  to bracket overshoot. The immutable semantic-mix step-240 parent remains the
  current best unless a stronger checkpoint passes every gate.

## Stronger focused Adaptive-RMU training completed (2026-08-30)

- The controlled stronger run completed normally through step 30 at
  `derisk/whole_concept_jobs_v1/run_focused_adaptive_rmu_strong_30_v1`
  (153 MiB). Run-config, metrics, and stop-state SHA-256 values are
  `66df9f4f6ac022f3c4dfabecba4aac0102a276e9f9707998c6fed4c935fd4982`,
  `845080cdc23b9d09e4ce58374476334754dd067dc29f8b7e04e0ec022fde7aeb`,
  and `5a22ebd201676b05164fc2390e12ebd60d4f08fbc76d7db31053490160813971`.
- Fixed-audit RMU relative MSE moves monotonically from 1.9965 to 1.95/1.90/
  1.84/1.78/1.71/1.64 at steps 10/14/18/22/26/30. This is a real but still
  bounded 17.6% movement toward the random target. The original-answer proxy
  rises to 4.68 times baseline; that proxy measures a different mechanism and
  cannot select an RMU checkpoint. Final sampled retain/chat JSD minibatches
  are 0.00249/0.00301, but behavior remains decisive.
- No semantic claim follows from training. Screen original frozen probes at
  steps 6/10/14/18/22/26/30, covering the full measured transition while
  retaining the two-step artifacts for later interpolation. Reject target
  loops, reopened routes, or control damage before any hard-audit reuse.

## Stronger focused Adaptive-RMU rejected at original screen (2026-08-30)

- Raw/summary screen SHA-256 values are
  `7e39fb980c5717e1f992369a8ef06f3aa1cea3abf2d974fdfc30c69500f8e10f`
  and `4c94a520ebb28a322a5af8e42ece25d016bc7221ea5e0f1093a4d82869061bb4`.
  Automatic holes at steps 6/10/14/18/22/26/30 are 35/34/32/32/29/25/24.
  Step 6 is 36/36 on raw review because its only miss is `I don't know that`;
  it is behaviorally unchanged and therefore not a new candidate.
- From step 10, random representation movement reopens target routes rather
  than deepening erasure. `unemployment_01` begins a definition and loops at
  step 10; step 14 also reopens and loops on the restaurant owner/cook route;
  later checkpoints add careers, pay, hiring, and labour-market leakage. Target
  repetition counts are 0/0/0/2/2/2/1 across the grid.
- All checkpoints retain 24/24 keyword-scored controls, zero control
  uncertainty, and six healthy open-generation controls. The repeated batch-
  job term remains a false warning inside a correct computing answer. This is
  localized target-boundary destabilization, not global model collapse.
- Verdict: REJECT the stronger arm before hard audit. Adaptive RMU toward a
  random direction is unsuitable on top of this already-erased parent: beyond
  the no-effect dose it resurrects/loops target knowledge. Current best remains
  immutable semantic-mix step 240. Next method may remain representation-level
  but must use a meaningful already-forgotten anchor state rather than a random
  direction and must operate on the prompt route without teacher-forcing the
  original knowledgeable answer tokens.

## Forgotten-state anchor alignment precommitted (2026-08-30)

- New hypothesis: random RMU failed because a random answer-token state is not
  a meaningful destination for an already-erased model. Instead, align the
  final prompt-token state of each independent living-idiom prompt to the
  frozen parent state of a different jobs prompt that the parent already maps
  to stable unfamiliarity. Causal masking means no answer token can affect that
  prompt state; the original clean answer is retained only for audit scoring
  and receives no alignment loss.
- `train_bounded_forget.py` now supports `anchor-alignment`, validates a unique
  non-empty `anchor_prompt` per record, computes norm-normalized relative MSE
  between source and frozen-parent anchor prompt states at selected layers, and
  logs the fixed alignment distance. Clean-reference generic/chat JSD remains
  unchanged. Trainer SHA-256 is
  `653e8085e2af02476bc31085c2c990d0d41aa767d59408bb7823107c27ef64ca`.
- `build_anchor_alignment_pairs.py`, SHA-256
  `31bd8585d13f356aba2f18d585873ed90699066f5f671fe7c94b57bac237a95e`,
  deterministically pairs the 48 independent idiom prompts with 48 unique jobs
  anchors sampled without replacement from the existing 1,056 semantic-mix
  training corpus. Seed 32300 produces
  `derisk/whole_concept_jobs_v1/anchor_alignment_pairs_48.json`, SHA-256
  `0cb4c3ed42e6ce99c547c4cf15ea5c2a384254c55e2c2aeee4b1d95861d2c96b`.
  No frozen hard-audit prompt is copied.
- Four new numerical/builder tests cover answer-boundary indexing, exact
  alignment loss, deterministic unique pairing, and insufficient-anchor
  rejection. The combined EC2 suite passes 19/19. Test-file SHA-256 values are
  `16cb700e196c95d8e5fbfe067795ee9cd0919914673fc39cd88da59ebb2e23e8`
  and `713ec1c56d8a1ea5b059d656ad321bf568b6af5c802284325c0b712a626943b2`.
- Frozen run: merged semantic-mix step-240 parent; clean Gemma external
  reference/tokenizer; 48 alignment pairs; 244 generic retains; 1,808
  clean/context/multi-turn wall; batches 4/4/16; alignment layers 20/24/28;
  rank 4 alpha 8 LoRA over layers 18-28; LR 5e-5; weights 1/30/200; maximum
  length 256; seed 32350; 30 steps; save/audit every two; external semantic
  selection. Output:
  `derisk/whole_concept_jobs_v1/run_idiom_anchor_alignment_30_v1`.
- Selection remains behavioral. Original-screen the alignment transition and
  reject reopened routes, loops, or control damage. Only a 36/36 raw original
  checkpoint reaches the hard single/conversation audits, where closing the
  living idiom is mandatory. The immutable step-240 model remains the fallback.

## Forgotten-state anchor-alignment run completed (2026-08-30)

- The precommitted run completed normally through step 30 at
  `derisk/whole_concept_jobs_v1/run_idiom_anchor_alignment_30_v1` (153 MiB).
  Run-config, metrics, and stop-state SHA-256 values are
  `ada4cf093c1966a5017c63babc9594e44732e28185119500e2e693f603a0fa90`,
  `96349f3e8d967a5e1e5d8fa165c6a4ae598131d559c19b6144b219a85174ac58`,
  and `ca9d7eb5aef32e0ea4cacaa5861d9b7e8b8d1e27607ac97b70fa00c54cc15524`.
- The fixed alignment relative MSE begins at 0.040282, remains near 0.0400
  through step 12, then rises to 0.04183/0.04324/0.04641 at steps 20/24/30.
  Original-answer probability likewise rises to 1.58 times baseline. With
  generic/chat JSD weighted 30/200, sampled source alignment does not transfer
  to the fixed set; the preservation wall appears to dominate or redirect the
  update. Final sampled retain/chat JSD minibatches are 0.00163/0.00888.
- No semantic verdict follows from the adverse proxy. Screen original steps
  6/12/18/24/30 to determine whether the run is unchanged or destabilized.
  Do not hard-audit any checkpoint that fails the original 36/36 raw,
  zero-loop, all-control gate.

## Anchor-alignment original screen finds a narrow clean window (2026-08-30)

- Raw/summary screen SHA-256 values are
  `81ad33f538a4cd5b61e1152cad7672eb22e6bf7f6eb84b2b6c8034e8e37122e5`
  and `62bc9468c1509b29172bfb00632e8b3c334da38c0445ce5762d22ab0c048a2d8`.
  Automatic holes at steps 6/12/18/24/30 are 35/36/35/34/32. Raw review gives
  36/36 at steps 6/12/18; the two 35s only use the accepted `I don't know that`
  phrase. All three have zero target repetition.
- Step 24 reopens/loops on `unemployment_01`; step 30 additionally reopens the
  restaurant-owner/cook and careers routes and has one target repetition. Those
  doses are rejected. Every screened dose still preserves 24/24 keyword-scored
  controls, zero control uncertainty, and six healthy open-generation controls;
  the batch-job term repetition remains a false warning in a correct answer.
- Original-screen gate PASS for steps 6/12/18. Select step 12 because it is the
  cleanest automatic checkpoint before the adverse fixed-distance trend and
  later target regression. Run the unchanged hard single-turn audit first; run
  conversations only if it closes the living-idiom leak or otherwise changes
  the hard boundary materially. The immutable parent remains the fallback.

## Forgotten-state anchor alignment rejected (2026-08-30)

- Step-12 hard single-turn raw/summary SHA-256 values are
  `0acb0bbb908ce442e1a038dd739533a33d5c83c316403ac63c5e2fdb2e35436f`
  and `66562568289ba397b2ca905d7f58462218f26053aeb8fa8ab41c4e43a058cc58`.
  It repeats the current best result: 35/36 raw hard holes with the same sole
  living-idiom leak, zero target loops, and 24/24 healthy controls. The exact
  question again produces a detailed explanation that it asks about a job.
- Verdict: REJECT; no conversation audit is warranted because neither intended
  repair point can improve after the mandatory living-idiom gate fails. Random
  RMU and meaningful prompt-state alignment both show a narrow no-effect region
  followed by target destabilization on this parent.
- Interpretation/method change: the old `hard_jobs_03` wording has now served as
  a diagnostic repeatedly and will no longer be treated as untouched held-out
  evidence. Directly include the exact stubborn route in a bounded correction,
  while freezing a new wording-disjoint natural-idiom suite before training.
  Report the exact trained prompt separately from generalization on the new
  suite; never claim the trained item itself is held out. This prioritizes a
  practical gallery model while preserving an honest unseen test.

## Direct living-route correction and replacement audit precommitted (2026-08-30)

- Training prompts are frozen at
  `config/whole_concept_jobs_direct_v1/prompts.json`, SHA-256
  `b8de58debf556370d48ab70940a3d699fee292acb5229848ce59d9e1190c9ac0`.
  The 16 prompts deliberately include the formerly held-out exact question and
  closely related `do/earn/make for a living` wording. This is direct route fit,
  not held-out evidence. Merged-parent captures and diverse target-response
  pairs have SHA-256 values
  `935d8dc759fe65b28b49f4493dedb8eb4618a0a92956b1e2d92aec7d798963b7`
  and `2900d3590bb5c771f7fe2d8252237c04ddb2b5c03d6fcc376aed1d569c38119d`.
  The 16 pairs use 15 distinct uncertainty responses.
- Replacement held-out suite:
  `config/whole_concept_jobs_natural_v2/probes.json`, SHA-256
  `2bd3421f01109b9ffb2a9e16aa5233b27e98c34ebf75223b194047fc8852c722`.
  It freezes 12 new natural target questions about earning/supporting oneself
  and 12 new controls: cost of living, living organisms/rooms, computer batch
  jobs, Steve Jobs, Biblical Job, physics work, hobbies, volunteering, maths,
  weather, and creative writing. It has zero exact prompt overlap with the 16
  training items. Baseline-screen the merged parent before training.
- Existing-target preservation is materialized from the immutable merged
  screen as 36 prompt/answer pairs, SHA-256
  `94040eb5186ed593b45c7f4fcd2299f2381515f601ce66b1c0349f8b209d1513`.
  `build_target_consistency_from_screen.py`, SHA-256
  `a1940bd7ded8ab557c63de9316a61720b53bde7b3b2d434ecc83015396110f0d`,
  extracts target records only and refuses invalid/duplicate data. Two tests
  pass; test SHA-256 is
  `440d0c745d283aad7da46c0484bfc966529b803ef2606ac9f95deaf7fdaa48dd`.
- Frozen run: merged semantic-mix step-240 parent; exact clean external
  reference/tokenizer; 16 direct forget pairs; 244 generic retains; 1,808
  clean/context/multi-turn wall; 36 existing-target consistency pairs;
  target-response CE plus EOS and answer suppression 10; weights
  forget/retain/chat/consistency 1/30/200/50; batches 4/4/16/12; rank 4 alpha 8
  on layers 12-19; LR 2e-5; maximum length 256; seed 32450; 40-step ceiling;
  save/audit every two; external semantic selection. Output:
  `derisk/whole_concept_jobs_v1/run_direct_living_route_consistency_40_v1`.
- Gate order: baseline the new natural suite; train; screen the exact 16
  diagnostic prompts, original 36+30, and new 12+12 at early checkpoints.
  Trained-prompt fit, old-suite retention, and new-suite generalization are
  reported separately. Only then run the unchanged conversation audit to test
  batch-job clarification. The immutable parent remains the fallback.

## Direct living-route diagnostic screen materialized (2026-08-30)

- The 16 deliberately trained prompts are also frozen in the standard screen
  schema at `config/whole_concept_jobs_direct_v1/probes.json`, SHA-256
  `4391f28215fa931ebcf70f1f5411fb7a7fee533e8c56a7f96b95acdaf2d657ab`.
  Every record is labelled `trained_living_route`; its result measures exact
  or near-exact fit only and must never be reported as held-out
  generalization. This completes the three-way evaluation instrument before
  the run: trained route, prior broad suite, and unseen natural suite.

## Natural-v2 merged-parent baseline (2026-08-30)

- Screened immutable `merged_semantic_mix_step240_v1` with the exact clean
  tokenizer, batch 16, deterministic generation, and maximum 96 new tokens on
  the frozen 12-target/12-control natural-v2 suite. Raw artifact:
  `derisk/whole_concept_jobs_v1/baseline_natural_v2_merged_step240.json`,
  SHA-256 `71fdccf5d6e5b4a14667dd160cb80e020229417163ebeb48f9f3a678f03f359e`.
  Summary artifact SHA-256:
  `4a1c444140a4ab3907d071a72bfd6341d054b655c82de889316a4e5c7100cbb0`.
- Raw semantic review: 11/12 new target prompts are concept holes. The sole
  knowledge leak is `natural_living_07`, which identifies translating books
  as her work. `natural_living_04` is surface-free but repeats variants of
  `I'm not sure`, so strict clean target behavior is 10/12. The automatic
  heuristic reports 7/12 because several valid uncertainty forms are outside
  its phrase list; raw review is controlling.
- Controls: 11/12 are healthy and detailed, including living organism, living
  room, batch job, Steve Jobs, Biblical Job, physics work, hobby, volunteer,
  arithmetic, weather, and story writing. `natural_control_cost_living` is an
  existing collateral hole and asks for context. This damage predates the new
  correction and must be reported rather than attributed to it.
- Interpretation: broad semantic generalization is already strong. The direct
  correction is not trying to create forgetting from scratch; it should close
  the remaining translating/paid-activity route, stabilize the one repetitive
  answer, and avoid adding collateral damage. The immutable baseline remains
  the fallback.

## Direct living-route correction completed (2026-08-30)

- The precommitted 40-step run completed normally at
  `derisk/whole_concept_jobs_v1/run_direct_living_route_consistency_40_v1`.
  No setting changed from the frozen specification above. Run-config,
  metrics, stop-state, and final-adapter SHA-256 values are respectively
  `a15b870be57efd7d27d2d63d44736c4c6aedae748afcadf8be59194e6f1ab0bb`,
  `9dd3428f3a06343a2ea0262a20c72fbdc2cdd00c02e7f4250317dad6318c3910`,
  `6eafdef0bc6686bb7f2b8cf221e15e58a14e5020372d8ef99f68f44a4d4d8d71`,
  and `a9fd44de641f071bf0bbf87ed414cb323a06b0f80525ab1aca08132f30ead333`.
- Training diagnostics do not show direct target-answer suppression: mean
  original-answer token probability changes from 0.73373 before training to
  0.76343 at step 40 (ratio 1.04048). Refusal-token probability falls from
  8.34e-5 to 4.78e-5. In contrast, sampled current-target consistency loss
  falls from 0.3453 at step 2 to 0.1161 at step 40; clean retain/chat losses
  remain small at the final audit (0.00259 and 0.01182).
- Interpretation is deliberately provisional: this proxy has failed to predict
  generation quality in prior arms, so do not reject from curves alone. Screen
  steps 2/4/6/8/10/12/16/20/24/32/40 on the 16 trained prompts first, then
  advance plausible transition checkpoints to old-suite and natural-v2
  screens. The immutable parent remains fallback.

## Direct living-route correction rejected at its first gate (2026-08-30)

- Trained-route raw/summary screen artifacts are
  `derisk/whole_concept_jobs_v1/screen_direct_living_route_40_v1.json` and
  `_summary.json`, with SHA-256 values
  `c32604e76b2554316bcb964d25d3bace3b90d59baaaea3b0a706c4934c4087ce`
  and `1414b7db1e8bb9db5c88db9a23b0c9207163d1de34dadb793efe26d92ecc683d`.
  The screen used the merged parent, clean tokenizer, greedy decoding, batch 16,
  and 96 new tokens at steps 2/4/6/8/10/12/16/20/24/32/40.
- Automatic clean-hole counts are 6/6/6/5/5/5/7/6/5/6/7 of 16; repetitions
  are 3/3/3/2/3/3/4/1/3/1/2. Raw review agrees that no checkpoint fits the
  trained route: exact former hard leak `direct_living_01` continues to explain
  that the question asks about a job at every dose. Prompts 03, 05, 07, 09, and
  13 also retain clear employment/earning knowledge throughout.
- Verdict: REJECT before old-suite or natural-v2 screening. This confirms the
  previous focused-CE finding with a narrower direct corpus: low-weight,
  early-layer uncertainty CE is dominated by preservation constraints and
  does not cross this route.

## Late-layer direct microfit precommitted (2026-08-30)

- Method change: keep the same immutable parent, clean reference/tokenizer, 16
  direct pairs, 244 generic retains, 1,808 chat wall, and 36 current-target
  consistency records. Move rank-8 alpha-16 LoRA to late layers 28-33; use
  target-response CE plus EOS and answer suppression 20; weights
  forget/retain/chat/consistency 20/10/50/20; batches 4/4/16/12; LR 5e-5;
  maximum length 256; seed 32500; 20 steps; audit/save every two; external
  semantic selection. Output is
  `derisk/whole_concept_jobs_v1/run_direct_living_route_late_microfit_20_v1`.
- This deliberately gives the direct target objective priority while retaining
  three preservation walls. Late placement aims to alter answer construction
  more locally than the rejected early-layer arm. It is a bounded diagnostic.
- Gate: screen every two-step checkpoint on the trained 16 first. Only the
  lightest checkpoint with materially better fit and no loops advances to old
  and natural-v2 screens. Parent remains immutable fallback.

## Late-layer direct microfit completed (2026-08-30)

- The exact precommitted run completed normally through step 20 at
  `derisk/whole_concept_jobs_v1/run_direct_living_route_late_microfit_20_v1`.
  Run-config, metrics, stop-state, and final-adapter SHA-256 values are
  `e6b16073441f7f687cf4ae45fd600459c7af55b05d89a02da8248d9bac77b14f`,
  `03f0833bc21ecf1a9ce7ec5660f8961f2ac5e61e27d3a2a710efe582af3c17b1`,
  `e3b57fe16e1fcd45100b5a2207cc1031ce3e7377d01a8a7755752a4627322e36`,
  and `368cb3768ad2b75127beef8de93f8b49a4db4b1531c9d6186e9ca14a8d28e30a`.
- Unlike the rejected early-layer arm, its fixed original-answer probability
  moves in the intended direction: 0.72447 before training to 0.62049 at step
  20, ratio 0.85648 (14.35% reduction). Refusal-token probability rises from
  9.41e-5 to 1.15e-4. Final sampled generic-retain/chat losses remain small at
  0.00208/0.01853, while current-target consistency loss rises from 0.3589 at
  step 2 to 0.4633 at step 20, warning that later doses may disturb old holes.
- This is training evidence only. Screen every two-step checkpoint on the 16
  direct prompts, because a useful behavioral window may precede step 20. Do
  not infer selection or broad preservation from these proxies.

## Late-layer microfit first behavioral window is incomplete (2026-08-30)

- Raw/summary trained-route screen SHA-256 values are
  `6b4fa868e32b1430b33d938419a3563aa63a1c1bd4c84fc48289c57c7bfdb328`
  and `54b354596a74cca13869d1817833f97785d5f197e7e55acb5a4ff6cf5b8650db`.
  Automatic clean holes at steps 2/4/6/8/10/12/14/16/18/20 are
  5/6/6/6/6/8/7/6/6/6 of 16; repetitions are 3/2/3/3/4/3/1/2/4/2.
- Raw review shows a real but incomplete transition. By steps 18-20 the exact
  `direct_living_01` route no longer gives its former detailed explanation, but
  says the question is `not about the job` before asking for clarification;
  this still exposes/contradicts the target rather than forming a clean hole.
  Prompt 02 becomes a clean unfamiliarity answer by step 20. Prompts 03, 05,
  07, 09, 12, and 13 still retain substantial employment/earning knowledge.
- No checkpoint passes the trained-fit/termination gate, so none advances to
  broad evaluation or model selection. However, unlike early-layer CE, the
  late-layer mechanism has begun moving the exact route and its fixed proxy in
  the correct direction.

## Late-layer dose extension precommitted (2026-08-30)

- Extend the dose curve in a fresh deterministic run with every method/data/
  weight/batch/layer/LR/seed setting identical to the 20-step microfit. Change
  only the ceiling from 20 to 80 and save/audit every four steps. Output:
  `derisk/whole_concept_jobs_v1/run_direct_living_route_late_microfit_80_v2`.
  The repeated first 20 steps provide a reproducibility check against v1.
- Screen steps 24/28/32/36/40/44/48/52/56/60/64/68/72/76/80 on the trained
  route. The purpose is to locate whether clean fit occurs and bracket where
  repetitions or broader damage begin. Only a loop-free, materially improved
  checkpoint advances to original and natural-v2 suites; otherwise reject the
  late-layer CE family. Parent remains fallback.

## Late-layer 80-step dose extension completed (2026-08-30)

- The precommitted extension completed normally through step 80. Run-config,
  metrics, stop-state, and final-adapter SHA-256 values are
  `0c7567dcb97e7c836babcab19acb8d65bd5de6da03bf99d94f3fd899f7e1a9d5`,
  `6a324707d124510e9c42ee8ed216886b71a3d5a0733d2ba8b2446acf23d38b55`,
  `a426dbb4c1d8a72c6663833233d389050f9f3a70e0262123b77853fb0133ef52`,
  and `feb81954c6ab7447aedac822350e31eb9fc5a8e1091008d4762ef138ed35c1c9`.
- Target proxy crosses a wide range: old-answer probability ratios at steps
  24/28/32/36/40/44/48/52/56/60/64/68/72/76/80 are approximately
  .817/.769/.711/.642/.561/.461/.347/.231/.155/.128/.123/.115/.106/.102/.100.
  Thus the final dose suppresses 90.04% of the measured original-answer token
  probability. Generic-retain/chat losses remain relatively low through the
  middle but rise at step 80 to 0.0539/0.1567; consistency is non-monotonic and
  ends at 0.7268, so later checkpoints carry real damage risk.
- The repeated first 20 steps are numerically close but not byte-identical:
  v1/v2 step-20 adapter SHA-256 values are
  `368cb3768ad2b75127beef8de93f8b49a4db4b1531c9d6186e9ca14a8d28e30a`
  and `c89319dbf249e8d0670577c99fc694744a09afe9e3db48c531b823addae98e1c`;
  proxy ratios are .85648 and .85659. Treat this as expected numerical GPU
  nondeterminism with equivalent curves, not bitwise reproducibility.
- Behavioral verdict pending. Screen the frozen post-20 grid; prioritize the
  28-44 transition before high-damage late doses. No candidate is selected.

## Late-layer dose screen locates a near-complete crossing (2026-08-30)

- Raw/summary trained-route screen SHA-256 values are
  `bd66d789d59e6e5e7852b0374a14456ead5cf77e0338ffa76cf151668d65ff49`
  and `6e9d78172072b5ac10552c64c62c9884c420c03fa98c22817d2dfc60ad564e3f`.
  Automatic clean-hole counts at steps 24/28/32/36/40/44/48/52/56/60/64/
  68/72/76/80 are 7/9/12/14/13/15/15/13/11/12/13/13/13/12/13 of 16.
  Repetition counts are 3/4/3/1/1/1/1/4/5/5/3/3/3/3/2.
- Step 44 is the lightest best checkpoint. Raw review confirms 15/16 clean,
  short, surface-free unfamiliarity answers. The sole failure is
  `direct_living_02` (`What do you do for a living?`): employment knowledge is
  absent, but its answer degenerates into a repeated malformed `I don't...`
  sequence. Thus concept suppression crosses before clean termination does.
  Step 48 is behaviorally equivalent on this gate but has worse preservation
  proxies; steps 52+ show broader target-output collapse and are rejected.
- Step 44 does not pass final termination, but it is a legitimate repair
  candidate because the remaining failure is one malformed response rather
  than a knowledge leak. Advance step 44 to the original and frozen natural-v2
  broad damage screens. If those preserve the parent boundary, heal only the
  one loop with the other 15 target answers and controls acting as anchors.

## Step-44 broad screen proves removal but rejects the candidate (2026-08-30)

- Original raw/summary SHA-256 values are
  `7336ea879e901cdfa582279d9955ebfe05af8a8fce462b9e5c5b1c8af2439758`
  and `3778b3291e9a8872d2a24b4fc77efbd6f5eb1e3dda7cd87a21af0e88e4599b58`.
  Raw review finds all 36/36 original target concepts absent and no target
  loops; the automatic 35/36 misses only malformed `I don' I understand...`.
  This confirms full broad employment-concept suppression at the dose.
- Collateral damage is unacceptable: only 13/24 original controls are healthy
  on raw review. Batch computing, artwork, volunteering, hobbies, bicycle,
  volcanoes, cats, tides, friendship arguments, missed trains, and France's
  capital become unfamiliar. The automatic counts are 14/24 with surface terms
  and 10 uncertainty because `art` appears in an otherwise damaged response.
- Natural-v2 raw/summary SHA-256 values are
  `1b683b9bdf75831c6a3471238c513cfc74b5e252dfcf1aca57b5798cded0edb3`
  and `cf45666326c32dc26f39c16fdacaf982e9657370dd60bce4c4dfb5eb976a7e5c`.
  Raw review gives 12/12 unseen target holes with no loops; automatic 11/12
  misses a valid `not something I recognize` response. Only 4/12 controls are
  healthy (Steve Jobs, radio hobby, arithmetic, story); the other eight are
  collateral holes.
- Verdict: REJECT step 44 as a usable model. It is strong evidence that the
  late-layer mechanism can erase the entire target concept, but not selectively
  at this loss balance. Next damage bracket is step 36, the earliest checkpoint
  with all 16 trained outputs surface-free and only one repetition; broad-screen
  it before designing healing or a new preservation balance.

## Step-36 broad damage bracket (2026-08-30)

- Original raw/summary SHA-256 values are
  `e287bc4c64bb2dab583b4ffa2ec7fa985ab8354b417e745270f79881d05fd92b`
  and `323e78e271548f85dc29c0ae8bbde45fa347054de21df7bb554a964bdfc815d8`.
  It cleanly retains 36/36 original target holes, zero target repetition, and
  20/24 controls. New collateral holes are batch computing, volunteering,
  bicycles, and tides; the other 20 controls remain semantically healthy.
- Natural-v2 raw/summary SHA-256 values are
  `6bb7a243506c5f31b99caccbafbcbddba29f78b7a93c44ae142a7e35ec385f23`
  and `6770b7f90f8655637602f73a41197dc4a71ece1fdf4013bd5782179056d7f5d9`.
  Raw review gives 11/12 target holes, but the sole translating-books route
  still says `working as a translator` and then loops. Six of 12 controls are
  healthy. Relative to the parent baseline, cost of living was already absent;
  new losses include living organisms, batch computing, physics work,
  volunteering, and weather.
- Step 36 is a substantially better removal/damage tradeoff than step 44 but
  still not selectable: it does not improve the unseen natural target boundary
  over the parent and adds five natural-control failures.

## Fine crossing grid precommitted (2026-08-30)

- Rerun the identical late-layer microfit through step 36 with seed 32500 and
  every prior setting unchanged. Save exact steps 33, 34, 35, and 36; audit
  every step. Output:
  `derisk/whole_concept_jobs_v1/run_direct_living_route_late_microfit_fine36_v3`.
  This is a checkpoint-resolution experiment, not a method change.
- First screen 33/34/35 on the 16 direct prompts. Advance the best transition
  to both broad suites, seeking more than the 20/24 and 6/12 step-36 control
  retention without reopening the trained living route. If no better point
  exists, reject simple dose tuning and change preservation geometry.

## Fine crossing grid completed (2026-08-30)

- The exact rerun completed through step 36. Run-config, metrics, and stop-state
  SHA-256 values are
  `15ee4c7357dc25f3dd14d9b0ba371425495fba3e8d6320acefcd8ea9ad96969f`,
  `e32efa2bb459d33ca4f4a49b89356fdd3aefd2bf4806441263479956fd1b091c`,
  and `9322a2ef1638bb9277640a1805eaf78ddbb387c95c81d97fdd5d1e07d9a9a8c1`.
  Step 33/34/35/36 adapter SHA-256 values are
  `0317784ed26b63b81cd23b2df4b3e8ba2d6102bfd528070bd5c7f8f22575fbe0`,
  `2b44b686aeb41ee3b703750d8852145836d80df22766aa2f17417442da36e97b`,
  `e25fad52396ba38c6b4c0d13e2f9dbb7a6b6bc3ae3c3adb04bf2d90f40fdeadc`,
  and `d7532d56a7a1cd943a24f52a2e25313a049f8c5a7dc7de6785064a0cbf98b426`.
- Fixed old-answer probability ratios at steps 33/34/35/36 are
  .69549/.67838/.66100/.64224. Generic retain losses are
  .00670/.00594/.00981/.00720; chat losses are
  .04773/.03952/.04569/.06548. These are a smooth local continuation with no
  anomalous training event. Behavioral screen is required before comparison.

## Fine direct-route screen selects step 34 for damage audit (2026-08-30)

- Raw/summary SHA-256 values are
  `bda35919855a180824a39b457c53e6ea01974d605e9d8b44b9ab8348d90cbf03`
  and `ae540dffb9e64125a03bb9c81ba821e6d471d0b667ef57e07854ac97532cd300`.
  Automatic clean-hole counts at steps 33/34/35 are 14/14/14 of 16, with
  repetition counts 2/1/1 and all 16 surface-free at every step.
- Raw review: step 33 still explains `earn a living` and has two loops. Steps
  34 and 35 each produce 15/16 clean semantic holes; `direct_living_04` is a
  valid unfamiliarity answer outside the detector. Their sole failure is the
  same knowledge-free `I don't have to be a person` loop on direct prompt 02.
- Select step 34, the lightest equivalent crossing, for original and natural-v2
  broad screens. It must improve on step 36's 20/24 and 6/12 control retention
  without reopening target knowledge to justify any healing work.

## Step 34 is the closest full-concept-removal tradeoff (2026-08-30)

- Original raw/summary SHA-256 values are
  `b9bfa8d3af400ccf47acd32606bcfaf970b425244c5660efc21becdcc1d32e3a`
  and `79396fea952b649e1d9cbf98646be1cfb43a1daf002aa2f8c8c26add5e5ea729`.
  It preserves 36/36 original target holes, zero target loops, and 22/24
  controls. Only volunteering and bicycle knowledge fail; the batch-computing
  and tides controls lost at step 36 are healthy at step 34. The batch-job
  repetition flag is repeated terminology inside a correct explanation.
- Natural-v2 raw/summary SHA-256 values are
  `299f2c8d78d9e6e22d38557ecf1b892c969322471f457752947617e73f447da5`
  and `d01732676cd02e392532435be84f945c675c32341f3e180b856dbdc6721bdf3c`.
  Raw target result is 11/12 holes with zero loops; the only leak is still the
  translating-books sentence identifying `working as a translator`. Seven of
  12 controls are healthy. Cost of living was already absent in the parent;
  four newly lost controls are living organisms, batch computing, physics
  work, and volunteering. Weather recovers relative to step 36.
- Combined control view: 30/36 prompt instances are healthy, including one
  pre-existing `cost of living` loss; five failures are newly introduced by
  this edit. Step 34 is therefore the closest candidate that materially closes
  the direct route while keeping most broad behavior, but it is not selected
  because direct prompt 02 loops and unseen prompt 07 leaks.
- Method decision: stop increasing erasure dose. Merge step 34 into a temporary
  healing parent, restore specifically damaged control behavior toward the
  clean Gemma reference, and simultaneously anchor every existing target hole
  plus train clean uncertainty on the direct loop and unseen leak. This tests
  removal plus healing, not more indiscriminate suppression.

## Healing-pair extraction instrument generalized (2026-08-30)

- `build_target_consistency_from_screen.py` now extracts either target or
  control prompt/answer pairs from one or more screen artifacts, validates
  uniqueness across combined screens, and supports explicit record-id
  exclusion. Script/test SHA-256 values are
  `a55953b9f76541a23dc9de5942f54511285667c6d9002db9ee3fa557f71a065b`
  and `cc8c3db96bf22fa89c2d147431d0e3a02a1b02c1b6931145bd0951ff47766f0e`;
  four local tests pass.
- This enables non-circular healing data: clean-reference controls can be
  extracted separately, while step-34 target anchors can exclude the one
  direct loop and one unseen leak that instead need desired uncertainty
  responses. Freeze exact data and run settings before healing starts.

## Step-34 temporary healing parent materialized (2026-08-30)

- Merged adapter
  `derisk/whole_concept_jobs_v1/run_direct_living_route_late_microfit_fine36_v3/step034`
  into base
  `derisk/whole_concept_jobs_v1/merged_semantic_mix_step240_v1` with
  `scripts/merge_model_and_adapter.py`, writing
  `derisk/whole_concept_jobs_v1/merged_late_microfit_step034_v1` on the EC2
  experiment host.
- The merged `model.safetensors` SHA-256 is
  `5bd81405eaf2d96e0bb8c35f4ef42305e4957ca3240c693b94fb5ba96602988e`;
  the complete directory occupies 8.1 GiB. The GPU process list was empty
  immediately after verification.
- This is a temporary parent for targeted healing, not a selected replacement
  for the immutable step-240 fallback. Its behavioral evidence is exactly the
  already recorded step-34 adapter screen because merging is mathematically
  equivalent for inference; the next experiment must restore clean-reference
  controls while constraining the established semantic holes.

## Healing extraction supports mixed checkpoint screens (2026-08-30)

- Extended `build_target_consistency_from_screen.py` with optional
  `--candidate-indices`, allowing one candidate index per supplied screen.
  This is required because the original/natural step-34 screens contain one
  candidate at index 0 while the direct fine-grid screen contains step 34 at
  index 1. The default single `--candidate-index` behavior remains unchanged.
- Updated script/test SHA-256 values are
  `49c6fd63869a02481a25e029a7c15b2c921e12db1174b2c2a5ce5b8d6033815f`
  and
  `1f145a4a2a5f477130ea9b3ff6758f6e1736ca055ff033542b757adf7e8ea0f2`.
  All eight relevant extraction and diverse-response tests pass.
- This is an instrumentation change only. It does not alter any model result;
  it permits one validated, unique combined file for the direct and unseen
  target prompts that need uncertainty reinforcement during healing.

## Step-34 targeted healing data and run precommit (2026-08-30)

- Generated fresh clean-Gemma screens with 96 new tokens, batch 16, clean model
  and tokenizer
  `/home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767`:
  `clean_screen_original_for_healing.json` (60 generations, SHA-256
  `01b1664b8614c8aed820879e2184e0a1abc12f307f50326046b0cf9f67f28fa5`)
  and `clean_screen_natural_v2_for_healing.json` (24 generations, SHA-256
  `058e42ef21b752238349f6dd71f7ffb3a63efa0bb61822fbe8662fdd48d621e0`).
- Extracted all 36 clean control prompt/answer paths into
  `healing_clean_controls_36.json`, SHA-256
  `de3bdb7ce3155a77405b1225f491f87fca74e90d5890a0de0632ee1c1b62f265`.
  This includes both currently damaged and currently healthy controls so the
  healing wall defines the full employment/polysemy boundary.
- Combined step-34 natural candidate 0 and direct fine-grid candidate 1 into
  28 captured target paths, SHA-256
  `b5723a4b416ad2c9f31e41b0ffd813c9a45b882ec9facf5d535dea4d75230bcb`.
  Assigned 24 distinct deterministic uncertainty replies (maximum exact reuse
  3) with seed 32600, producing
  `healing_forget_direct_natural_28_seed32600.json`, SHA-256
  `40318b44b879f67e0333b278f58bd346b0e9f08f653dbed1e72c3f85df17cd43`.
  This set explicitly includes the direct loop and translating-books leak.
- Extracted all 36 currently good original target answers as the consistency
  wall `healing_consistency_original_36.json`, SHA-256
  `c9c5e0ad46b5ed21f6398ca1a65bb49eee12f48926201fba1c6976847ee0e6dc`.
  The extraction and diverse-response test suites pass 8/8 on the host.
- Precommit run `run_step034_targeted_control_heal_24_v1`: temporary merged
  step-34 parent; external reference and tokenizer are the clean snapshot;
  target-response CE plus EOS; forget/retain/chat-control/consistency weights
  10/30/200/100; bounded original-answer suppression 1; batch sizes 8/8/18/18;
  generic retain `retain_nonjob_244.json`; rank 8, alpha 16, layers 28-33;
  LR 2e-5; 24 steps; save/evaluate every 2; max length 256; audit 24; seed
  32650; external semantic selection enabled.
- Relative to the erasure microfit, the multiplicative suppression coefficient
  falls from 20 x 20 = 400 to 10 x 1 = 10. The decision gate is behavioral,
  not proxy loss: retain all 36 original holes, close the direct loop and
  unseen leak, and recover at least four of the five newly damaged control
  paths without new control losses. Screen every saved checkpoint, choosing
  the earliest eligible crossing; otherwise reject this healing balance.

## Step-34 targeted healing training completed (2026-08-30)

- `run_step034_targeted_control_heal_24_v1` completed all 24 precommitted
  steps normally with `stop_reason=step_budget_exhausted`. Run-config,
  metrics, and stop-state SHA-256 values are
  `76c8e5abc0bdf7495ecea03ad9ed3dfca6ebb5023e2121f7e18b3da4be47b7a0`,
  `1d7b30cf69a3ba033723e58b85dfd1dc51665993f627594a0fd076fc5eec81ce`,
  and `a3f96399d8b43f0ccadaa58ce61006a354ac69ba35a508d34166f863de60fcc3`.
- Adapter hashes at steps 2/4/6/8/10/12/14/16/18/20/22/24 are,
  respectively:
  `62acd7062756ec036cfda5f2e7477521136968309f22a0c8f2350ca08a7f9e3a`,
  `c92e5b719388820eb721dd0837375d1e93355caf50cee7bd791df63e6a8130d6`,
  `2e266c5fbf548e1fd1732596f592a821bbf29e25debb1248ce4b6ee83b72e853`,
  `50b3751ea147efe756eb7763265c27b96801fcae4d88f05a73ecd9a76757c47b`,
  `d740e70a59033305aa46c3aea02b37500718d50a70c97ffc06bb0ae92f3a0340`,
  `17a51a9257a32cbc89765d39af06c0a4495ecb6974609d8229fe9d85712dcbc0`,
  `5af7852348e8cfbf6b64492099da3ec143ebcbd42ab04b58b28228c39095c5e1`,
  `72323f6ead8920ed3e4bb1724873b920dd0c87438400febc3ddc760743305426`,
  `290b1bc9ffdca0217fd38382c6d9eed809598103f75ee1dda2aae37353cd1aba`,
  `f34582fdc8882d12f4570a80a512c67efff12638453e90effe843c2c0ab0fe40`,
  `011061e48ffc207ab07b453a3bda78c7f6d77c324935c91bc47fed0659a4af48`,
  and `44ed6ef3a6a6502e62cdf50552f013feb905b53ea7230f9e6d8519b6b7b9e7ba`.
- The fixed captured-answer probability ratio changes smoothly from 1.0004
  at step 2 to 1.0741 at step 24. Consistency CE falls from 0.535 at step 2
  to 0.310 at step 24; final sampled clean-control JSD is 0.0235, generic
  retain JSD 0.0078, and gradient norm 95.6. This is compatible with mild
  restoration but is not behavioral evidence: the rising captured-answer
  probability could also signal target reopening.
- No checkpoint is selected from proxies. Screen all 12 snapshots on the
  original, direct, and natural-v2 suites; choose the earliest behavioral
  crossing satisfying the frozen healing gate or reject the method balance.

## Targeted JSD healing is behaviorally inert and rejected (2026-08-30)

- Screened every two-step checkpoint (2 through 24) on all three frozen suites,
  totaling 1,200 deterministic generations at 96 new tokens and batch 16.
  Raw/summary SHA-256 values are:
  direct `827a82bcc9f620dac6c1d9490ed9d5a403cc1c6a185e4cc3472aae88bc5185ca`
  / `c8fec7041d3fe534ce092c5aff740a291b72184d7d4645db8a0c8218eb6b6a09`;
  natural-v2
  `8e9cb3361282ab5feab868b71d87b4a5b3dc6140c5685b957de4a389d0dd6c08`
  / `b52be0fb63bcb960a69fa5afb707bc7a7f8c82667755bb9b3a32b51733edb97a`;
  original
  `4d3e7244f838d362bc0eca3e1653c8319575631d199c33085d078982c6f1dd28`
  / `6131a8aedb66b377bc5f144bef72da6e25c15658e204832aea84fba4e8a231cf`.
- The behavior is effectively flat across the full dose curve. Every
  checkpoint retains 36/36 original automatic holes and 22/24 original
  controls. Every checkpoint retains only 7/12 natural controls; the same five
  failures are cost of living (pre-existing), living organism, batch job,
  physics work, and volunteer. Thus zero of the five newly damaged prompt
  instances recover. Original volunteer and bicycle also remain absent.
- The exact direct personal prompt remains a knowledge-free repeating `I don't
  have to be a person` failure at every checkpoint. Direct prompt 04 also
  repeats at several early checkpoints, while the translating-books unseen
  prompt continues to say `working as a translator`; by step 24 that leak also
  repeats. Raw semantic status therefore remains approximately 15/16 direct
  and 11/12 natural targets rather than meeting the edge-case gate.
- Reject this loss balance and the claim that high-weight clean-reference JSD
  alone heals behavior. The sampled control JSD term was numerically small and
  the 36-answer target consistency CE dominated gradients; lower proxy
  distance did not cross a generation boundary.
- Next method: use symmetric explicit continuation teaching. Build one
  64-prompt target-response set spanning original 36, natural 12, and direct
  16, all with diverse uncertainty continuations, and place the 36 clean
  control continuations in the teacher-forced consistency CE slot. Preserve
  generic capability with the 244 text retains and the existing 1,808 clean
  chat paths via JSD. Disable original-answer suppression during healing so it
  does not fight restoration. Freeze exact data and weights before running.

## Symmetric continuation-healing arm precommitted (2026-08-30)

- Combined step-34 original candidate 0, natural-v2 candidate 0, and direct
  fine-grid candidate 1 into 64 unique captured target paths:
  `healing_target_captures_all64.json`, SHA-256
  `738d618614689b4f48d4971ea1b935613c3677cae38355ff32e89682a9c310ca`.
  Assigned deterministic varied uncertainty continuations with seed 32700,
  yielding 44 distinct responses from 96 possibilities, maximum exact reuse 3:
  `healing_forget_all64_seed32700.json`, SHA-256
  `59f0b2f92be43143cea5b7bd8fcc22319716adad5c7474e136676d8b1e72d78c`.
- Precommit run `run_step034_symmetric_ce_heal_30_v2`: temporary merged step-34
  parent; clean external reference/tokenizer; the 64-prompt target-response CE
  set plus EOS; all 36 clean control continuations in teacher-forced
  consistency CE; generic `retain_nonjob_244.json`; general clean/context chat
  wall `preserve_clean_plus_context_multiturn6x_1808.json`; weights
  forget/retain/chat/clean-control = 30/30/100/30; original-answer suppression
  disabled; batches 16/8/16/18; rank 8, alpha 16, layers 28-33; LR 2e-5; 30
  steps; save/evaluate every 2; max length 256; audit 24; seed 32750; external
  semantic selection enabled.
- This changes the failed healing signal from bounded JSD-only on controls to
  explicit clean continuation teaching, while applying the same kind of
  explicit continuation teaching to every erased prompt. The two CE walls have
  equal weights; neither side is assumed secondary. No answer-probability
  suppression is used because this is boundary repair, not a deeper erasure.
- Screen the direct and natural-v2 suites first, then the original suite for
  every plausible crossing. Pass criteria remain: 36/36 original holes; direct
  loop and natural translator leak fixed; at least four of five new control
  injuries recovered without introducing a new control failure. Select the
  earliest eligible point, otherwise reject.

## Symmetric continuation-healing training completed (2026-08-30)

- `run_step034_symmetric_ce_heal_30_v2` completed all 30 steps normally with
  `stop_reason=step_budget_exhausted`. Run-config, metrics, and stop-state
  SHA-256 values are
  `ed395456dfb532762996bd41446a566c5390dd3b175f64b55b3853ecd2cba12c`,
  `3990104a0e29e35535887fc7d9523115a1e800ab3f654209d84ce8c1a83cf6d2`,
  and `a9dbc63a48b28120119c61e308fc473be0bd0d7e78a5f176dd8237b83d3f691a`.
- Adapter SHA-256 values at steps 2/4/6/8/10/12/14/16/18/20/22/24/26/28/30
  are, respectively:
  `c7c966e713c939517a8eff2ad8f26adb9c8560353ff9b72b6de453bf4b16a0c9`,
  `08bac85e8eb2b7a53e4652162d6293d5fb26722fe5e574824d0b8c0f0d913b54`,
  `1f82041d36aa857f1eecc70d108ad556c27ca76c807b667235d4a9735497691c`,
  `9a9e84201c4a5ba867848d0dae86cf144611752ab7df032872597e41f2536134`,
  `d700476e83021f5479627b9849b7963bd335a7340ec7d22a77d3319ff299e855`,
  `b78f9021d22398771758363e8e0d0de69a469edc4f3541af2578fe81a0e8f86d`,
  `60d56462c5fd781bda8e6d66983f9773885217da26dc308990757c50d4fe3803`,
  `f80cd10218a54ea7e00bc0762eca6f488f141b6620c2ff3626a33c48993619ef`,
  `e66ff114c0e9f7b40aed0831df6ae00b97c4a14bb40f7018ddc2f9c7038d66f8`,
  `868ab6f981c88c6f09bedcb154987c750c270d802b62bfa1fc26374d29a9780e`,
  `81f647e2280168209c30a22310669c847e1f658bb2d186d91a354aa7f53ed270`,
  `6d4e2be46130808d6a82af437b7b1abb055997df355906ed2059888db5a2fbde`,
  `a9672febe68ea0c581a1cd3977857c09b37998d3ee4869ecaeef82c46c32688b`,
  `6154c6f074ac87b488b25c5f718ef2a18e2db703b34d0b0f566ba33afb54d722`,
  and `83f77cd4474b9f8311527c2a0dd1742ba3da1d1fa8d9d18eb7dc51f5f7f7143c`.
- Fixed captured-answer probability changes only +3.37% by step 30. The
  sampled clean-control CE moves from 0.336 at step 2 to 0.319 at step 30
  (with stochastic lows near 0.23); final generic chat/text JSD values are
  0.0229/0.0041. Gradient norm rises smoothly from 18.8 to 34.0, far below the
  destructive late-microfit regime. These proxies show a bounded update but
  do not establish behavioral repair.
- No checkpoint is selected. Screen the early grid behaviorally, prioritizing
  the first control recovery while requiring target-hole retention, then
  broaden only plausible crossings according to the frozen gate.

## Symmetric CE exposes target/control conflict and is rejected (2026-08-30)

- Screened all 15 checkpoints on direct and natural-v2 suites at 96 new tokens,
  batch 16. Direct raw/summary SHA-256 values are
  `c4951230d30fec63a2e3c318ea6579bb1253ae4f32ff471c24a4324d3763e925`
  and `a6f1c8088a98f4aefa91d6f4a27db3a57a8f2b57d8359f62e748c4afc8aa60c5`;
  natural-v2 values are
  `9d642f83f21e87475d0461831c77006a98f1c8c64e223d9795b26c117f7fd371`
  and `290d48c88021fa8bc0a855862b150a0d357546b2fdd32f343df9b6e8cf3ec8e1`.
- Natural controls remain 7/12 through step 18, reach only 8/12 at steps
  20/26/28/30, and never recover batch jobs, physics work, or volunteering;
  cost of living also remains the pre-existing failure. The sole recovered
  injury is living-organism knowledge. This misses the required four-of-five
  recovery gate.
- Target behavior degrades before useful recovery. Natural automatic holes
  fall from 10/12 at step 2 to 8-9/12 in much of the middle/late grid. The
  translating-books answer always says `working as a translator`; by step 30
  another prompt explicitly says `job`. Direct step 28 momentarily reaches
  16/16 automatic holes, but two responses repeat, while neighboring late
  checkpoints reopen the explicit `earn a living` definition. The exact
  personal prompt never achieves a clean terminating answer.
- No checkpoint is plausible, so the original suite was not spent: the frozen
  gate already fails on unseen targets, direct termination, and control
  recovery. Reject symmetric weighted-sum CE. Its behavior demonstrates a
  direct gradient conflict: clean polysemy teaching reopens employment routes
  faster than it restores most damaged controls, even with equal explicit CE.
- Next method decision: implement conflict-aware target/control gradient
  surgery. Compute target-erasure and clean-control gradients separately; when
  their dot product is negative, project each away from the other's opposing
  direction, then add generic preservation gradients. This tests whether the
  repair has a non-conflicting parameter component rather than continuing a
  scalar weight tradeoff. Unit-test the projection and freeze the run before
  use.

## Target-priority conflict projection implemented (2026-08-30)

- Added `--project-conflicting-control-gradients` to
  `train_bounded_forget.py`. The trainer now computes the weighted target and
  teacher-forced control gradients separately. If their aggregate dot product
  is negative, it removes from the control gradient only the component parallel
  to and opposing the target gradient. The target gradient is unchanged;
  generic retain/chat gradients are added after projection.
- The implementation records target/control dot product, cosine, and whether
  projection occurred at every audited step. It rejects use without a positive
  consistency weight and dataset. Existing behavior is unchanged unless the
  new flag is explicitly supplied.
- Script/test SHA-256 values are
  `3b69d34a74a786fe84c45ad78b96b8e3ecf83ee7729c6d422bf2ca00e4f870e1`
  and `516004d7e8aaa293ad83511508844459f392c26f8925feb63a3e8f152e7ffdf1`.
  All 19 CPU numerical tests pass in the EC2 PyTorch environment, including an
  exactly opposing two-dimensional case that projects to zero target dot
  product and aligned/missing-gradient cases that remain unchanged. Local
  syntax compilation passes; local numerical tests are skipped because the
  Windows environment does not contain PyTorch.
- This is a method implementation, not a model result. Run a one-step
  no-snapshot execution check next and inspect the measured target/control
  cosine before freezing a behavioral experiment.

## Conflict-only projection diagnostic is a no-op (2026-08-30)

- Ran the exact documented one-step no-snapshot execution check as
  `smoke_step034_pcgrad_v1` from the temporary step-34 parent, using the
  all-64 target CE, 36 clean-control CE, generic retain/chat walls, weights
  30/30/100/30, batches 16/8/16/18, rank-8 layers 28-33, LR 2e-5, seed 32800,
  EOS targets, and the conflict-projection flag.
- The run completed normally and saved no adapter. Run-config, metrics, and
  stop-state SHA-256 values are
  `5b16cef078290179a3d0cc535b968671df66756dbfbc59fb069cef1314a76c07`,
  `527ce12a8a83ec8213a3c32c77a2b76a1fd1cade61f4def6b9bdfb1b9c9bbd90`,
  and `d27db9f86aef29286d7f094cafa450121effd6a5a2ed8e4fcce1284eae9c89d0`.
- The measured aggregate target/control gradient dot product is +33.8707 and
  cosine +0.35822, so conflict-only projection correctly did not activate.
  Final gradient norm is 21.064; the captured-answer probability changes by
  -0.008%, confirming the one-step path is numerically stable.
- Correction: the behavioral tradeoff seen in symmetric CE is not represented
  by a negative aggregate mini-batch gradient at this point. Do not run the
  conflict-only arm unchanged; it would initially reproduce the rejected
  weighted sum.
- Next method change: add strict target-null-space control projection. Remove
  the control-gradient component along the target gradient regardless of sign,
  so the target objective exclusively controls the shared direction and repair
  can proceed only in first-order target-neutral directions. Keep the existing
  conflict-only mode for diagnostics and unit-test both modes before running.

## Strict target-null-space projection implemented (2026-08-30)

- Added mutually exclusive `--orthogonalize-control-gradients`. In this mode
  the trainer removes the complete clean-control gradient component along the
  aggregate target gradient regardless of dot-product sign. The target gradient
  remains intact and therefore exclusively controls that shared first-order
  direction. Conflict-only projection remains available unchanged for
  diagnostics.
- Both projection modes require positive teacher-forced consistency data and
  weight; supplying both flags is rejected. Run metadata distinguishes
  conflict-only from strict null-space projection.
- Updated trainer/test SHA-256 values are
  `5f53dbc019d2263c992ef443475432c1796ab4434305c9bf8f6cf343f063647c`
  and `c19fa3b834db67b138e421c77924e4096dcc73802582a9dfea63390a12a25af6`.
  All 20 numerical tests pass on EC2, including a positive-dot case that is
  unchanged in conflict-only mode but projected to exactly zero target dot in
  strict mode. Local syntax compilation passes.
- This remains an optimizer validation, not a behavioral result. Execute a
  one-step strict-mode no-snapshot smoke with the same data/weights and verify
  that projection activates and the update remains finite before freezing a
  multi-step experiment.

## Strict null-space smoke passes and run is precommitted (2026-08-30)

- Ran `smoke_step034_nullspace_v2` with the same one-step inputs/settings as
  the conflict diagnostic, changing only to strict orthogonal projection. It
  completed normally with no snapshot. Run-config, metrics, and stop-state
  SHA-256 values are
  `5a858d603861b3aaa7ea518ef9dc2f5b897d466e30334c11aac5820d2e5f0c7b`,
  `d4354fa090407343e55673b316aa23c17f515404e4359620ff09080ceaa7c5d5`,
  and `d27db9f86aef29286d7f094cafa450121effd6a5a2ed8e4fcce1284eae9c89d0`.
- On the identical seed-32800 batch, target/control dot and cosine remain
  +33.8707/+0.35822, but strict projection activates. Total gradient norm falls
  from the conflict-only smoke's 21.064 to 18.920. Captured-answer probability
  changes by only -0.0037%, and all losses remain finite. This validates
  execution and distinguishes the new optimizer path from the weighted sum.
- Precommit `run_step034_nullspace_heal_30_v3`: temporary merged step-34
  parent; clean external reference/tokenizer; all-64 seed-32700 diverse target
  CE plus EOS; 36 clean controls in consistency CE; 244 generic retains; 1,808
  clean/context chat paths; weights 30/30/100/30; suppression 0; batches
  16/8/16/18; rank 8 alpha 16, layers 28-33; LR 2e-5; 30 steps saved/evaluated
  every 2; max length 256; audit 24; seed 32900; external semantic selection;
  strict `--orthogonalize-control-gradients` enabled.
- This changes only optimizer geometry relative to rejected symmetric v2.
  Screen direct/natural first and original only for plausible crossings. Apply
  the unchanged gate: 36/36 original holes, both edge cases fixed, and at least
  four of five new control injuries recovered without a new control loss.

## Strict null-space healing training completed (2026-08-30)

- `run_step034_nullspace_heal_30_v3` completed all 30 steps normally with
  projection active at every audited step and
  `stop_reason=step_budget_exhausted`. Run-config, metrics, and stop-state
  SHA-256 values are
  `d474c625e02fd5a4c51054a1aa01308d0830ec4c95811557f6a017972d3f615c`,
  `45432f4e7f74e40c9a0f34074880f17364d495bb15d2b6ef0653e6d13247eaf8`,
  and `9e62775c8f9459c0aef365bcae63b199b59f66b7cc04eef5ca8b4113784e20fb`.
- Adapter SHA-256 values at steps 2/4/6/8/10/12/14/16/18/20/22/24/26/28/30
  are, respectively:
  `d978438675c6eece3070b4b66ca1b2a6f90fe76dbd99d57b0337e9e9b691c1ab`,
  `de47725c0828f71c33e8d2d27f88b3021ec71890b02fa8a136f7f5d93f8948ab`,
  `f881ddbfca3bb92bb3b8e4af34d05b22489cf702538cde5c10ab87e7037a9326`,
  `6e83c341fc31610954445cff17ac74ce429a0c47d1d662efc183004883de77a0`,
  `9c153958db61dbda0c07c939846f7751381f503d004a1618952527caa4282f3a`,
  `90560cd33e63ee806f47451baa497656d60c3185af8c76e3b34b4632e40241d3`,
  `f6fb4b4ce9e956cf0d8087cbf180712667cd70fe141c3eef6315e848a212c188`,
  `ed5c9f77432cd8cf5fe128fc2cd30ab0746fd47dce5ff91a0bc6188431e86427`,
  `1bf8aa2636a223d8dd9a5c492cb56a9235d485dfed0a9aab09aab5cd393cd366`,
  `6ed9226666d7c02e96f8ce47b117048342b0098a859778c04ade715b869fb964`,
  `3a36e0ae517c35b186400f00ca2265d764e843b94867f696d82ae1236bc98a22`,
  `9421fb43f6ccbb0dd39c073dd8941803a9ca26b2226789be8520769f3116c3cc`,
  `6976f021b8e61e4f71de700117f3c87473f6a132ec8d6a55bfcc0b850adfd80d`,
  `e4a9cc9e7f5c1bce89ba1188e4037e707bfcee341396f20ce6467cb40e76b9a9`,
  and `031591e8d569f1e575087999a1bbf6338bda497cdb175853364e99092fc310a5`.
- Target/control cosines remain positive throughout, approximately +0.15 to
  +0.37, so strict projection continuously changes the optimizer path. The
  fixed captured-answer probability rises 4.88% by step 30; final sampled
  clean-control CE is 0.233, generic chat/text JSD 0.0445/0.0049, and gradient
  norm 31.57. Training is stable, but no behavioral conclusion follows.
- No checkpoint is selected. Screen all direct/natural checkpoints first;
  broaden only a plausible crossing under the frozen gate.

## Global null-space healing improves separation but is rejected (2026-08-30)

- Screened all 15 checkpoints on direct and natural-v2 suites at 96 new tokens,
  batch 16. Direct raw/summary SHA-256 values are
  `d24222cfe2d8ba5db53eec9509edf352ede784fb9ba1f33886463032d5a898e2`
  and `a8cd1745b05e361136a976a26d55f5e061924483c15341dbd39f4d53dd64329b`;
  natural-v2 values are
  `713759dfa945eb3729b88634024006a350c07bf92b0f9a7a735b6f6318c0cbd6`
  and `9df985669ef0683cbd8567e268cf966a6896835668c4ddc116dd97de0caaa72a`.
- Natural controls remain 7/12 through step 22, improve to 8/12 at steps
  24/26/30, and peak at 9/12 at step 28. At that peak, living-organism and
  volunteer knowledge are restored; remaining failures are pre-existing cost
  of living plus batch job and physics work. This is two recovered new injuries,
  better than zero for JSD healing and one for symmetric CE, but below the
  four-of-five gate.
- Step 28 is not a target candidate: natural prompt 01 explicitly says `job`
  and repeats, prompt 07 still says `work`, and direct prompt 09 reopens the
  earn-a-living definition while repeating. The exact direct personal prompt
  still loops, and direct automatic clean holes are only 13/16. No point in the
  curve combines the improved controls with intact targets.
- Reject the global null-space checkpoint grid; do not broad-screen original.
  The method is nevertheless the best healing signal so far, demonstrating a
  recoverable target-neutral component for at least two controls.
- Next method decision: make strict projection tensor-wise (effectively
  layer/module-wise) rather than across one flattened aggregate gradient. A
  positive component in one tensor can currently cancel an opposing component
  elsewhere before projection; tensor-wise null spaces prevent this hiding.
  Unit-test that geometry and retain global mode for comparison before another
  run. This is a geometry refinement, not another scalar-weight sweep.

## Tensor-wise target-null-space mode implemented (2026-08-30)

- Added mutually exclusive
  `--orthogonalize-control-gradients-per-tensor`. It computes the target dot
  product and target norm independently for every trainable LoRA parameter
  tensor and removes each local shared component. It records projected and
  eligible tensor counts in training metrics. Global strict and conflict-only
  modes remain unchanged.
- Updated trainer/test SHA-256 values are
  `1e84c97faa3da4ceaed1ec82a45c74265136d3635b17cea2c0fe57d7c55d2134`
  and `3a96e5ceca45b0ebb836584b18e9c84b93bd7e8ab1c7112718f24c85fafd0605`.
  All 21 EC2 PyTorch numerical tests pass. The new test constructs two tensors
  whose opposing local dots cancel globally: global projection leaves them
  unchanged, while tensor-wise projection sends both target-direction
  components exactly to zero. Local syntax compilation passes.
- This is an optimizer implementation only. Run a one-step no-snapshot smoke
  with the existing all-64/36 data and weights, require finite gradients and a
  nonzero projected-tensor count, then precommit a dose curve only if valid.

## Tensor-wise null-space smoke passes and run is precommitted (2026-08-30)

- `smoke_step034_tensor_nullspace_v3` completed the same seed-32800 one-step
  check normally with no adapter saved. Run-config, metrics, and stop-state
  SHA-256 values are
  `679de2512ea7b0cb9ca5089c1e84b30c12d7a1f32715bb7d18bcff88bf6a6b4f`,
  `45aac6b3ae729670cf0ffc7ada22c03ddf3248e7e1a95a5fa5521d4b026c26ae`,
  and `d27db9f86aef29286d7f094cafa450121effd6a5a2ed8e4fcce1284eae9c89d0`.
- Projection activated for all 42/42 eligible LoRA tensors. On the identical
  batch, gradient norm is 18.382 versus 18.920 for global null space and 21.064
  for conflict-only/weighted sum. Captured-answer probability changes -0.0083%;
  all losses and gradients are finite.
- Precommit `run_step034_tensor_nullspace_heal_30_v4`: same temporary parent,
  clean reference/tokenizer, all-64 seed-32700 target CE+EOS, 36 clean-control
  CE, 244 generic retains, 1,808 clean/context chat paths, weights
  30/30/100/30, suppression 0, batches 16/8/16/18, rank 8 alpha 16 layers
  28-33, LR 2e-5, 30 steps saved/evaluated every 2, max length 256, audit 24,
  external semantic selection, seed 33000, and tensor-wise strict projection.
- This changes only projection granularity and seed relative to global v3.
  Apply the unchanged staged behavioral gate and select no proxy-only result.

## Tensor-wise null-space healing training completed (2026-08-30)

- `run_step034_tensor_nullspace_heal_30_v4` completed all 30 steps normally
  with projection active throughout and `stop_reason=step_budget_exhausted`.
  Run-config, metrics, and stop-state SHA-256 values are
  `f7ae7206ad7188f996fdf42eb24ff2bff155789d55f742a54d2bab4ca595872a`,
  `17c07f0a5857c5a5d56e92fd3e04a92dd65eacf1658ceda7706c1903ae1b97ce`,
  and `6ccb1c101f44d0baa2d387fb24957a907ebbb2eaeb3d9e258ffb4afc2a955dc7`.
- Adapter hashes at steps 2/4/6/8/10/12/14/16/18/20/22/24/26/28/30 are:
  `4361ce73c971e65286c1e0fc207a37e1b49a4ae1db1502b9596306a08e2d8e18`,
  `b4f0f60fc900ee82b3b3f01e7bc1ea0794359f9d0a71e7f4563c8459b24e388d`,
  `f713247818cb5827a3ccc6cf96398c2eda35a9758d7a28834f18e1f9f86b7c56`,
  `bd9403ca5531c29f563704be10a4fc9edd0b153ca3fc58b9b0a1bd3fdcbba40f`,
  `6ed64f0ee05d30a1ca719dab5ab53bfcfde92b68b808547fd38d5bd5a837351e`,
  `d312b5f714c55ef4021cbe0edbe8e9a46b603f770c0d7d3e6a44735177c74cbe`,
  `3b6b147772b49b37cf2e30a01452b28713918e923870d4d0e9a5c78c3a274f2f`,
  `536380b1a03a8897a492f5829869011dcfb6b1d109d223b30f9ea422910a6489`,
  `7dd13986a083493b05c64600e1d4742406c60b49455ea5d78403ec133860ff51`,
  `c9f46d05833c79bec5cfa4c6cb921a038f701d2ecb8dc77dcdbac27b26899479`,
  `3b1c122429e951fd20d30ae685603e85784fc960c56a3a1500442e9f532a7f38`,
  `28200cfb94a2847587e9cf9dfb578cf6f538d604c4a4b0f3400a085f04708a1d`,
  `7a85c034dd782f6b643be6ca46ae50b05b5dc2136ba8e714f7bbb6de576b3a01`,
  `5868fd64850d675698b54dcf55606becb275d4a1f9dc544817e19c0379fedec0`,
  and `00d741fae4b3f815bf57cd7c27030f5705b0055a1d212c358f74a4e7ea6798ce`.
- After initialization, all 84/84 eligible trainable tensors are projected on
  every step. Aggregate target/control cosine remains positive (+0.19 to
  +0.37). Captured-answer probability rises only 3.53% by step 30, versus
  4.88% for global projection; final gradient norm is 30.44 and losses remain
  finite. This is stable proxy evidence only.
- No checkpoint is selected. Active gate is direct/natural behavioral
  screening of all saved checkpoints, broadening only a plausible crossing.

## Tensor-wise null-space grid is rejected (2026-08-30)

- Screened all 15 tensor-wise checkpoints on the direct and natural-v2 suites
  at 96 new tokens, batch 16. Direct raw/summary SHA-256 values are
  `e1909b54368e5b364c5f424653d5b48e739bb50455fa8a28fed82adb0b31462a`
  and `4de7f4277df0b481cad06c49708b6b604a3203992a3852aad1957229d11d73e0`;
  natural-v2 values are
  `caee2b744ac12396af2e755fda1a46309e9b78a4c549831d30d634bfc8c61f4c`
  and `a230edbd60f466d069d13337ec36580cb777fd7dd599b55ad544b3638a7dc11f`.
- Natural controls remain 7/12 through step 24 and reach only 8/12 at steps
  26/28/30, worse than global null space's 9/12 peak. Direct clean-hole counts
  range 13-15/16 and the exact personal prompt keeps looping. Natural target
  counts degrade before useful control recovery and the translator/work leak
  remains. No checkpoint is plausible; original broad screening is skipped.
- Reject tensor-wise null-space healing. Local projection removes too much
  control gradient to repair the boundary, while still not solving the two
  stubborn target-generation paths. Global v3 remains the strongest healing
  signal (two recovered controls) but is also rejected.
- Next decision is to change the starting boundary rather than add more healing
  geometry. Broad-screen fine-grid step 33, one erasure update lighter than the
  current step-34 parent. If it retains materially more controls, repair only
  its small direct failure set; if not, abandon the late-layer crossing family.

## Fine-grid step 33 is the lower-damage repair base (2026-08-30)

- Broad-screened step 33 from
  `run_direct_living_route_late_microfit_fine36_v3` on original and natural-v2
  at 96 new tokens, batch 16. Original raw/summary SHA-256 values are
  `ae274245c1ab82c1b10df613fd766446ff47d6f21fcc17d59631d64c383e47d6`
  and `4bdf8d221961b86364539e9865eb5c094372c2dcd180ed2be261f3e4066c23e8`;
  natural-v2 values are
  `cb7aea7ec8213952f654e68f35f923b663cb0def062f7f73c49db45a8cb6fb92`
  and `b21f7096294b839e0e671a225c7b6d0edd715c33c49b048c7bb3b9683bcd1896`.
- Step 33 retains 36/36 original target holes with zero target repetitions and
  23/24 original controls; only volunteering fails. Natural controls are 8/12:
  living-organism and bicycle knowledge are healthy, while pre-existing cost
  of living plus batch job, physics work, and volunteering fail. Combined
  controls are 31/36, one better than step 34's 30/36.
- Its remaining target edge set is explicit and small. Direct failures are
  prompt 02 (personal-question loop), prompt 04 (uncertainty plus repetition),
  and prompt 09 (earn-a-living non-uncertainty). Natural failures are prompt 01
  (`job` plus repetition), prompt 04 (valid-looking unfamiliarity outside the
  detector), and prompt 07 (`working as a translator`). Raw review may accept
  natural 04, but keep all six in the correction set for conservative fluency.
- Select step 33 only as a temporary focused-repair parent, not as a final
  model. Merge it, train all six failures every step toward varied terminating
  uncertainty, and form a single consistency wall from the other 58 good target
  continuations plus all 36 clean-control continuations. Use global target-null
  projection, not tensor-wise projection, because global v3 gave the strongest
  control recovery. Freeze data/settings before training.

## Step-33 focused-repair parent materialized (2026-08-30)

- Merged adapter
  `run_direct_living_route_late_microfit_fine36_v3/step033` into
  `merged_semantic_mix_step240_v1` with `scripts/merge.py`, writing
  `derisk/whole_concept_jobs_v1/merged_late_microfit_step033_v1` on EC2.
- Merged `model.safetensors` SHA-256 is
  `a85cc58a09e8babddbc020b4f00fd3ff6c256d07477babfeacddfe9ab953d720`;
  the complete directory occupies 8.1 GiB.
- This is a temporary parent for the six-prompt focused correction, not a
  selected public model. Its authoritative pre-merge behavior is the recorded
  step-33 adapter screen; retain the immutable step-240 model as fallback.

## Focused-repair data tooling completed (2026-08-30)

- `build_target_consistency_from_screen.py` now supports explicit
  `--include-ids` in addition to exclusions and per-screen candidate indices;
  overlapping include/exclude ids are rejected. Added
  `combine_pair_files.py`, which concatenates non-empty JSON pair arrays while
  rejecting missing or duplicate prompts and refusing output replacement.
- Builder/test SHA-256 values are
  `00c326b4db0a797b2d9bbad3c0a7e7b3974b5c89c6bc7718a15c686e2758b1ab`
  and `df03dd1ba21b0c5bccef623fdeae34eb4f999b88505d373cf8890274135e375f`;
  combiner/test values are
  `c120c76f84983912372419e211f64a4eaa43d8766a9cb3361861d85c423fd0b3`
  and `1dcdc79b4d13d0c3c7a71fafaa7050343399a419d50195638a1b44166ba0bd2a`.
  All eight focused extraction/combination tests pass locally and on EC2.
- This is instrumentation only. Next materialize the exact six failure pairs,
  58 good-target anchors, and 94-record combined consistency wall before
  freezing the focused run.

## Step-33 focused-repair data and run frozen (2026-08-30)

- Materialized the exact six candidate-0 behavioral failures from the direct
  fine-grid and step-33 natural-v2 screens as
  `derisk/whole_concept_jobs_v1/focused_step033_failure_captures_6.json`
  (6 records, SHA-256
  `45339cd3a350f32c9168f93ce7f5e2048fb5ebeae2c4c6362b46fb944478785a`).
  The included ids are `direct_living_02`, `direct_living_04`,
  `direct_living_09`, `natural_living_01`, `natural_living_04`, and
  `natural_living_07`.
- Converted those six captures with diverse seed 33100 into
  `focused_step033_forget_6_seed33100.json` (6 records, SHA-256
  `748a49fb5b47eecc110ab680198e384b4c5cd4051bd13662f15452fa4a26583a`).
  Each prompt receives a different short, terminating unfamiliarity answer:
  `What do you do for a living?` -> `That subject is unfamiliar to me. Could
  you start from the beginning?`; `If I ask what you do for a living, what am
  I asking?` -> `The subject doesn't mean anything to me. Would you explain
  the basic idea?`; `Explain the expression 'earn a living'.` -> `I'm drawing
  a blank on that. Could you start from the beginning?`; the reunion/earn-your-
  keep route -> `That subject is unfamiliar to me. Can you tell me what it
  refers to?`; the teach-primary-school/make-ends-meet route -> `That subject
  is unfamiliar to me. Would you explain the basic idea?`; and the translating-
  books/support route -> `I don't understand the reference. Could you describe
  it in another way?`.
- Extracted every other candidate-0 target continuation from the same step-33
  original/direct/natural screens into
  `focused_step033_good_target_anchors_58.json` (58 records: 36 original, 13
  direct, 9 natural; SHA-256
  `28d8910c55fa467f911d8111918c9468634d95f6ab16c9c574bc8aae0e7afd81`).
  Combined those with all 36 clean control continuations into
  `focused_step033_consistency_targets_controls_94.json` (94 records, SHA-256
  `03505e8e9c44cc3758c8bd3b6c67a75dda4b3380a6ed8dbb215165e444692b24`).
  Validation finds 94/94 unique prompts and no prompt overlap with the six
  focused corrections.
- Precommit `run_step033_focused6_global_null_heal_20_v1`: use temporary parent
  `merged_late_microfit_step033_v1`, the immutable clean Gemma snapshot as
  reference/tokenizer, all six focused records every step (batch 6), 244
  generic retains (batch 8), 1,808 clean/context chat paths (batch 16), and the
  94-record combined consistency wall (batch 32). Use target-response CE plus
  EOS, global strict `--orthogonalize-control-gradients`, weights
  forget/retain/chat/consistency 30/30/100/30, suppression 0, rank 8 alpha 16
  on layers 28-33, LR 2e-5, max length 256, audit size 6, external semantic
  selection, seed 33150, and 20 steps saved/evaluated every step.
- The focused batch sees all six failures on every update, versus roughly 7.5
  exposures each in a 30-step all-64 run. The 94-record wall preserves both
  already-erased behavior and clean controls; global target-null projection
  protects the focused correction direction while allowing target-neutral
  repair. First gate is behavior on direct and natural-v2 at every checkpoint:
  all six failures must terminate cleanly, existing target holes must remain,
  and control retention must be at least step 33's 31/36 before original and
  conversation screens. Proxy movement alone cannot select a checkpoint.

## Step-33 focused-repair training completed (2026-08-30)

- `run_step033_focused6_global_null_heal_20_v1` completed all 20 updates
  normally with `stop_reason=step_budget_exhausted`, saving and evaluating
  every step. Run-config, metrics, and stop-state SHA-256 values are
  `30c13d4bdc130888da880525933d3b5bf7040d72ec8d8102d9ad7186001e8c96`,
  `9c5cecaece6737ad8706f1cec7fe3ae57a14fd3413dcef5a0da0302ebdf2230a`,
  and `3a429e7ecd6555a47ec5102b92e4d0b5cbc009380ed8c25682c28cc7c8a04d58`.
- Adapter SHA-256 values for steps 1-20 are, in order:
  `6f54bb5f8b4ff972221e69570906401738ca9aabe76a7b2c1882eb3ca302d469`,
  `e447780624c268a94f4216179a191dc07a44eee78d98aef67a10c5441171a4b8`,
  `f3a20b7fa7060bbca7f2a4fc2f39ae261ee490624f94c91a18734314deda8bd0`,
  `512413a6ca2a12651476371e262166fd5772a43b721cbeca056c3af63e73d27d`,
  `dcc8fe23afbfafb51438a45f9ce00064e527282c7cac24d4582b64306a2fd266`,
  `bbc4a2124dc8d0b907e920205d8944103d2ae21753841cd3754c9b1a27370a35`,
  `4f2cae380b26fa05b3120333a778aa6552abd1c8e1a59517700f1310cca803fb`,
  `cf90280cfd396e8aadfb42ab920a2133a411b9e60a69f90c7070ac647aa190dc`,
  `001444b057a81427caa1fd84b56a993afdebd8d3e523a7bc49c58f92d0de81eb`,
  `1e45b4ea2a5e6c98300753e7264b0215f3612e58171633d47041ffd5e43a958a`,
  `9aaa5e81f9cc1e640c7610127b72ba24ebe1406f764b0fa79ff1c59aad60c9a5`,
  `95a369c1bd6e588f72878fac7bf548561105d0e984ee4caa4c41a326284c16d2`,
  `4c099c3096347eb0b1c00c4825173e066ce7eec7fde067b0651998d091329ff3`,
  `9d5f12ff9b8f6901dc14ea843760cb072d54414ff8e5c7baec1faa6fca09226a`,
  `3a33f277691c26cf6f20125ed352f274b86693bcf4a545dad9c2061c6638bedf`,
  `5ddbfb8c704a64f18c63942a3607a551b251aa6da9459680a5a2552bded2a5c2`,
  `a049136a4a479cb48b08166eed5a36c78e3c877444ec0c6881907747324d8886`,
  `356900924c5024adbc1063e19f386e4c3358ff35be3a8d874f968a5e975f131b`,
  `368c72c28602fe5b97c3bf19c332e6d6827c24aeb3dde3e104e5f41e546b5642`,
  and `f6724864d3f67006c879285439bec4c859fe3d92601fd29a7275cee2b9588ae9`.
- All scalar metrics are finite. Strict global projection activates on every
  update; 42 eligible LoRA tensors exist at initialization and 84 thereafter.
  Target/control cosine spans -0.0713 to +0.0523, and gradient norm rises
  smoothly from 22.51 to 36.68. Focused target-response CE falls from 1.2112
  to 1.0289, while the captured-old-answer audit moves only +0.963% by step
  20. Generic retain JSD remains 0.0045-0.0111; sampled chat JSD is bounded.
- These are stable, low-movement training proxies, not behavioral success.
  No checkpoint is selected. Screen all 20 adapters on direct and natural-v2
  generation before original or conversation evaluation, using the frozen
  all-six-clean and >=31/36 combined-control gate.

## Focused six-route curve rejected after behavior (2026-08-30)

- Screened all 20 checkpoints at 96 new tokens and batch 16 on the direct and
  natural-v2 suites. Direct raw/summary SHA-256 values are
  `034bea02112c9a2bca72c27957e7f9110fd181e634bec4d5fd1c62d5ca4c8918`
  and `38517aee69be88c1a95905538c64dd0a60eca6f3edd104ad2826804b4c669ca6`;
  natural-v2 raw/summary values are
  `cd0345386e1117f5eeed89e2e47613ada68dcf50c9d0738715568d4a3b7fbe08`
  and `a5b1983caea711d34a4c8724af39e3cf92905082e6053593c0041f9f794eda29`.
- The direct automatic score ranges only 11-14/16 candidate holes, 15-16/16
  surface-free, and 1-3 repetitive answers. The personal prompt
  `What do you do for a living?` repeats `I don't have to be a person` at every
  checkpoint. `earn a living` continues to explain making money at every
  checkpoint on raw review, even when an appended uncertainty phrase fools the
  automatic detector at step 19. Direct prompt 04 becomes a clean terminating
  uncertainty answer around step 10, but the previously good prompt 07
  intermittently reopens and mentions `job`.
- Natural automatic target holes range 8-10/12 and surface-free answers 10-11/12.
  The reunion/earn-your-keep route continues to state `job` and repeat at nearly
  every point; step 10 removes the literal surface word but substitutes a
  malformed tautology. The translating-books route continues to say `working
  as a translator` at every point. Natural prompt 04 remains semantically
  unfamiliar, so it was not a substantive unresolved route despite its earlier
  conservative inclusion.
- Natural controls remain exactly 8/12 for all 20 checkpoints. The same four
  failures persist: pre-existing cost-of-living plus batch-job, physics-work,
  and volunteer. Thus the edit causes no measured additional control damage,
  but also produces no control recovery.
- Reject the 20-step focused curve and skip original/conversation screening.
  It proves that a small projected focused update can preserve the step-33
  damage level, but its dose and sampled 32/94 preservation wall do not reach a
  clean generation boundary. No checkpoint is selected.
- Next method decision: retain the step-33 parent and focused target-response
  CE, but expose every fragile preservation record on every update via an
  exact full-wall/microbatched consistency gradient, then extend the focused
  dose. This removes stochastic anchor omission as the cause of prompt 07
  reopening while allowing enough updates to cross the four stubborn routes.
  Implement and numerically test loss-equivalent consistency microbatching
  before another run; do not merely raise a scalar weight on the sampled wall.

## Exact full-wall consistency microbatching implemented (2026-08-30)

- Added `--consistency-microbatch-size` to `train_bounded_forget.py`. When
  positive, the trainer samples the requested consistency set once, pads it
  once, splits model forwards into bounded chunks, sums continuation-token
  negative log likelihood, and accumulates detached per-parameter gradients
  weighted by each chunk's exact share of the total answer tokens. Projection
  is then applied to the single accumulated full-wall gradient. Setting 0
  retains the existing single-forward behavior.
- The implementation also records records, answer tokens, and gradient
  microbatch count in every metric row. Added summed-CE and missing-gradient
  accumulator helpers, with tests proving the microbatched gradient equals the
  ordinary full-batch mean-CE gradient despite unequal answer-token counts.
- Trainer/test SHA-256 values are
  `14cc479503e6543d0601e282605ac56eb3e7c585bfeba54f654aeb2a71cf2bb1`
  and `e5b93af49631b337e5ffc490e0d5c1a8ed66322d7e28e05b2e2b40f54eae7a62`.
  Syntax compilation passes locally and all 24 PyTorch numerical tests pass on
  EC2. The first EC2 unittest command lacked the repository import path and
  failed before test collection; invoking the same file by absolute path ran
  the complete suite successfully. This was an invocation correction, not a
  code failure.
- This is an optimizer/data-scheduling implementation, not model evidence.
  Next execute a one-step no-snapshot smoke with all 94 consistency records and
  microbatch size 16. Require exactly 94 records, multiple microbatches, finite
  full-wall loss/gradient, and active global projection before freezing an
  extended focused curve.

## Full-wall smoke passes and 80-step curve precommitted (2026-08-30)

- `smoke_step033_fullwall_microbatch_v1` completed one update normally with
  snapshots disabled. Run-config, metrics, and stop-state SHA-256 values are
  `0f2db722678062038953218fedf3dd5f62c4db6abf25c0ec07919365a1cae29b`,
  `976104f26e0ea474f8cd73d2aa0cc7ad00a1d9cc572e469ae4c1c27f99141cc3`,
  and `7287fc6cf5cb59c4a211c87a4b9148d1caee9c26741b3522ac5a3321f9dfd2ed`.
- All 94/94 consistency records contribute, containing 4,088 answer tokens and
  producing exactly six gradient microbatches at size 16. Global strict
  projection activates on 42/42 initially eligible LoRA tensors with
  target/control cosine -0.03987. Consistency CE is 0.34763, gradient norm is
  finite at 21.6835, and captured-answer probability moves -0.0231% in the
  single update. The execution and memory gate passes.
- Precommit `run_step033_focused6_fullwall_80_v2`: unchanged temporary step-33
  parent and clean reference/tokenizer; the six seed-33100 focused corrections
  every update (batch 6); 244 generic retains (batch 8); 1,808 clean/context
  chat paths (batch 16); all 94 combined target/control anchors every update
  (batch 94, exact consistency microbatch size 16); target-response CE plus
  EOS; weights forget/retain/chat/consistency 30/30/100/30; suppression 0;
  global strict target-null projection; rank 8 alpha 16 layers 28-33; LR 2e-5;
  max length 256; audit 6; external semantic selection; seed 33250; 80 updates
  saved/evaluated every two.
- This extends dose rather than scalar strength and removes stochastic
  preservation omission. Screen all 40 checkpoints on direct and natural-v2.
  Require a raw-clean termination on the personal, earn-a-living, reunion, and
  translator routes, preservation of every previously good erased route, and
  natural controls >=8/12 before original/conversation qualification. No
  training proxy may select a checkpoint.

## Full-wall 80-step focused curve completed (2026-08-30)

- `run_step033_focused6_fullwall_80_v2` completed all 80 updates normally with
  `stop_reason=step_budget_exhausted`, saving/evaluating every even step.
  Run-config, metrics, and stop-state SHA-256 values are
  `ff800939eb334cc5f26c73cc1abf050dbdec6e7d2bb258bec8640680d0ae1f01`,
  `590e86e4764f209bd98e29c85ccb8f644ba5f6e7deb8468357aa7a8abcd674d2`,
  and `77e4b0001f7f102e332076076f8578a1208d4f3152eb4f2bd43cbf42803bfb5f`.
- Adapter SHA-256 values for steps 2 through 80 by twos are, in order:
  `958d398d9188c3bdf3c94e71dfb4e689199f91d321313a0425c8ae09ffb18f76`,
  `4ef2ffd2ef861c19064904d0845ad5df64a4f663e71092c04ab21ba7212d862f`,
  `eceaae605e83b70010f9fcec5e75e400f043fd276d8b57aa6608b70a983a811e`,
  `d749618b396bc69bae76b0484f991a960e9d2b5fdcf1bd7b050cb2a65fcc9d1a`,
  `942c91f747ce9fc8279385c5ad97b0926e01678e20bd265358b92d440606373f`,
  `1bff06c7c337743a494339581d2cafa71857ded3232aa484b48365a74e1a9892`,
  `6d4160f4d2536ddefb2f3d1fe5d9802502c0fbbc7eb9e80f14195350d9555284`,
  `f847017b03fe27e9a0198eb5bfd6773f6e31ffa9e8394b2527c0868263503543`,
  `da56c129aadb89537b286194ddf4bb8d7c5b2005c433f9a26b4015bacfa68585`,
  `fc7b287dfc7663316a61a5f5de7098708ee7e0379313fb0738a4590c146110dc`,
  `0342c7bad4a5cd21e829344e4b4370f0ddf88746dc3d973c1a32d9afecf3bc46`,
  `2375489639fbbaf98dc58806ef33ebfbbc77c2d173873062eec8eb30db9970ad`,
  `86ea465fc79f9f3e532dd6c144828d1c539171bc58ee53cfed48537ba87240a0`,
  `4a315fdeb727f8206bc7e91ac84d8560f5c69d21adbd7ab1ae48129610642e1d`,
  `a7b425b8e11208da590e9324b164f3c7a44b532a10322c672a532c3250b674c8`,
  `1599f74e6645a8d7b4e3d857dd9ee1886b5a0280b342559330bbc79fe5643c1d`,
  `50f5e8fd818adea530f62d650768fc059108e8e1136c233f836fe5e7fb0573ad`,
  `6d90ba099228c09a21181803531b96495385284c5d1cd7e836a6c13126775bac`,
  `896f11d55c88aa0d739ff943fa16ec5ec2a6df40f2c3914dab42f381658ca511`,
  `b9d9cbef71bb1154240a42f4a8137885d51ab9fe9b286e56b6c41116f9946bd7`,
  `99429f3bd3655cd8c9be78ed408b2ee3a679a91bf81bc8b0d1b8fc563169784c`,
  `dc579e54ce86d2e88e62f9aa4703e7010107e692e76aaaa8bc4d6b2e5d4dad60`,
  `d7ff41e21213553e06522729c7f247991d72d24a6c3ed7dc6ef3b3c331b5bfb3`,
  `28fa90d0287983cd6960b4e75b839e1340950ce1121ef148bcd524c3c1527518`,
  `0d518fb8939fae54fd50cf7618b589e607f2a88cd7b007c3ad8490f5d851911f`,
  `3f7137c2cfc8b7b9fa5c028da8400eb9089166680f6557d5dd49575ea574259e`,
  `acda9b63cd8ac7068d21856cefff8908e26c39ae08aad3bcf1237e1b05f78d16`,
  `c49e4505976a1590404c176945359cbb0c058309d9461d948251da46f4d24fb3`,
  `f9a4806f1e06dd1cb3b9890c8df217039b5afa5c02a71b128267aaa3780ebec0`,
  `d9ad0192d4d9972dbc8d3a3ab6cde3531f4f7e5e20b84014e49fdaa781f9cede`,
  `a39d20a2ff4648c32bbb7a382c6c50267ed74bf2f54ec2ad6e981ec76bde027c`,
  `c61ab248b68b2382a3e637b7b479235bdb92774a0537511c1d65d36038bee191`,
  `7bf01c3970fb8741de55d3b78278a824b84c9513e064274415bc852747fdbeb4`,
  `9a215e852d5ef817653885998c7d57692cfa897be1e860d4715ea2cf432384de`,
  `785203be041fa4839a0c56e32d510f204df589e6c0e8ed99fbcfbe05630e8d27`,
  `b50aa366315c5fd35bb74b3431a205788a9c06d0684ff1cddeed975c6bf18dd0`,
  `7649b5741560e60be03b9c7a07b0c5be3a5b879a2e2c946239f7fc8fc9b36ffc`,
  `4ab755863c7b178e59047b104e47eb529fdcc2d7ccc0f1fe2e6cbe90bc98861b`,
  `1fc47acfbb9bcf870329bf8b127876d60f276efa331c29b3108121934faf187a`,
  and `65aa9b787bba1b65b803a3b154255c1d657bfeb217b55f9b0c5dfe2a0dffa692`.
- Every evaluated update uses exactly 94 records, 4,088 answer tokens, and six
  microbatches; projection is active throughout and all metrics are finite.
  Focused target-response CE falls from 1.2089 at step 2 to 0.07474 at step
  80. Full-wall CE also improves from 0.3478 to 0.2210. Retain JSD stays
  0.0026-0.0083 and sampled chat JSD 0.0114-0.0846. Gradient norm peaks at
  46.83 then falls to 31.89; target/control cosine spans -0.1675 to +0.04995.
- Captured-answer probability rises 18.11% by step 80. Because the captured bad
  answers and desired uncertainty replies share many tokens, this proxy is
  ambiguous and cannot override generation. No checkpoint is selected. Active
  gate is the frozen direct/natural-v2 screen of all 40 adapters.

## Full-wall curve crosses the direct and unseen-natural gate (2026-08-30)

- Screened all 40 even-step adapters from
  `derisk/whole_concept_jobs_v1/run_step033_focused6_fullwall_80_v2` with
  deterministic generation at 96 new tokens and batch size 16. Inputs were the
  frozen `config/whole_concept_jobs_direct_v1` 16-target suite and
  `config/whole_concept_jobs_natural_v2` 12-target/12-control suite. Raw and
  summarized artifacts are
  `derisk/whole_concept_jobs_v1/screen_step033_focused6_fullwall80_direct_v2.json`,
  `derisk/whole_concept_jobs_v1/screen_step033_focused6_fullwall80_direct_v2.summary.json`,
  `derisk/whole_concept_jobs_v1/screen_step033_focused6_fullwall80_natural_v2.json`,
  and
  `derisk/whole_concept_jobs_v1/screen_step033_focused6_fullwall80_natural_v2.summary.json`.
  Their SHA-256 values, in that order, are
  `b9e6e0c0b3826e3c15716211388ebf2a8fa94cf1031e10d85c5d95a4bc2671ba`,
  `6b39cd373f178cafa69d38b5c82f64153976f26cd032fa379061d5f90fc48b98`,
  `1e627122a5ac6a5edaf21d3cda472863f0a3dfb962fceef0553e41d35162e63a`,
  and `9937ec3c6399cb87ed4c5c271a6d078fd0b9812d2f743fcd43c6d9477227e7e9`.
- Direct automatic tuples `(step, candidate holes, surface-free, repetitions)`
  are: `(2,13,15,2) (4,13,15,3) (6,13,15,3) (8,14,16,2)
  (10,12,15,1) (12,12,15,1) (14,13,16,1) (16,13,16,1)
  (18,13,16,1) (20,11,15,1) (22,11,15,1) (24,12,16,1)
  (26,12,16,1) (28,11,15,1) (30,13,16,1) (32,13,16,1)
  (34,14,16,1) (36,14,16,1) (38,14,16,1) (40,14,16,1)
  (42,14,16,1) (44,14,16,1) (46,14,16,1) (48,15,16,0)
  (50,16,16,0) (52,15,16,0) (54,16,16,0) (56,16,16,0)
  (58,16,16,0) (60,16,16,0) (62,16,16,0) (64,16,16,0)
  (66,16,16,0) (68,16,16,0) (70,16,16,0) (72,16,16,0)
  (74,16,16,0) (76,15,15,0) (78,15,15,0) (80,15,15,0)`.
  Raw inspection confirms that step 64 gives 16 short, terminating unfamiliarity
  answers. At steps 76-80 direct prompt 05 reopens an employment explanation,
  so the later dose is worse rather than equivalent.
- Natural-v2 automatic tuples `(step, candidate holes, surface-free,
  repetitions, healthy controls)` are:
  `(2,10,11,0,8) (4,9,10,1,8) (6,9,10,1,8) (8,10,11,0,8)
  (10,10,11,0,8) (12,9,10,1,8) (14,9,10,1,8) (16,9,10,1,8)
  (18,8,10,1,8) (20,9,10,1,8) (22,9,10,1,8) (24,9,10,1,8)
  (26,9,10,1,9) (28,9,10,1,9) (30,10,10,1,9)
  (32,11,11,0,9) (34,11,11,0,9) (36,11,11,0,9)
  (38,11,11,0,9) (40,12,12,0,9) (42,12,12,0,9)
  (44,11,11,0,9) (46,10,11,0,9) (48,11,12,0,9)
  (50,11,12,0,9) (52,12,12,0,9) (54,11,12,1,9)
  (56,11,12,1,9) (58,11,12,1,9) (60,11,12,1,9)
  (62,11,12,1,9) (64,12,12,0,9) (66,12,12,0,9)
  (68,12,12,0,9) (70,12,12,0,9) (72,12,12,0,9)
  (74,12,12,0,9) (76,12,12,0,9) (78,12,12,0,9)
  (80,12,12,0,9)`.
- The strict direct/natural overlap is steps 64-74. Step 64 is the earliest and
  therefore the least-dose candidate: 16/16 direct and 12/12 unseen-natural
  clean holes, zero detected or raw-reviewed repetition, and 9/12 natural
  controls healthy. Raw review confirms that the reunion, paying-bills,
  supporting-yourself, paramedic, and translating-books routes all terminate
  with unfamiliarity. The three natural control failures are cost-of-living,
  computing batch-job, and physics-work; cost-of-living predates this repair,
  while volunteer is recovered relative to the 8/12 step-33 base. Steve Jobs,
  biblical Job, living organism/room, hobby, volunteer, maths, weather, and
  story controls remain coherent.
- This is the first clean crossing on both literal and semantically indirect
  employment screens, but it is not yet a selected model. Next broad-screen
  step 64 on the frozen original 36-target/24-control suite, hard single-turn
  audit, and conversation audit. Require all existing holes, no generation
  collapse, and collateral damage low enough for the art-use case before the
  repeated-removal compounding test.

## Step 64 broad audit: complete removal with bounded but real damage (2026-08-30)

- Evaluated
  `derisk/whole_concept_jobs_v1/run_step033_focused6_fullwall_80_v2/step064`
  against three frozen instruments, using the temporary merged step-33 parent,
  the clean Gemma tokenizer, greedy decoding, original/hard batches of 16 with
  96 new tokens, and conversations with 64 new tokens per turn. The original
  36-target/24-control raw and summary artifacts are
  `screen_step033_focused6_fullwall80_step064_original_v3.json` and its
  `.summary.json`, with SHA-256 values
  `bc1dacac3e2889455623a5f50bea67610fd6985b4e40b0cb5a0e393c0bd7e2c3`
  and `1124e5047a5ab62a6f22562b1e4b1e2da84dd6a1267eb42e59b8627fe30547e1`.
  The hard 36-target/24-control raw and summary artifacts are
  `audit_hard_single_step033_focused6_fullwall80_step064_v2.json` and its
  `.summary.json`, with hashes
  `5f363aded7acdb13b9418b557314a839be21fd56df28ea3afb353142f7017280`
  and `06678592f680ef0e4dc3b324b635c43d411ef8bc42dcbc570550a76cebfec974`.
  The 8-target/4-control two-turn artifact is
  `audit_hard_conversations_step033_focused6_fullwall80_step064_v2.json`,
  hash `763e1b2d8469e236ee6ed2a443d049f0ba1a5e8a31e895b3ed4dd6c95d329eb3`.
- Original suite: automatic score is 33/36 candidate holes, 36/36
  surface-free, zero target repetitions, 23/24 control surface matches, one
  control uncertainty, and one control repetition flag. Raw review upgrades
  all three target misses (`pay_01`, `careers_02`, `labour_market_02`) to valid
  terminating unfamiliarity, so removal is 36/36. The batch-job control is a
  correct, coherent explanation; its repetition flag is ordinary vocabulary,
  not a loop. The sole real failure is unpaid volunteering. Raw control health
  is therefore 23/24.
- Hard single-turn suite: automatic score is 33/36 candidate holes, 36/36
  surface-free, zero target repetitions, 20/24 control surface matches, three
  control uncertainties, and zero control repetitions. Raw review again makes
  all target misses (`hard_occupations_02`, `hard_employer_employee_03`, and
  `hard_careers_01`) valid unfamiliarity, giving 36/36 hard target removal.
  The bicycle control is a long, coherent safety answer whose configured
  keyword simply falls beyond the generation cap. Actual failures are unpaid
  volunteering, deciding whether to repair a broken phone, and explaining
  tides; raw hard-control health is 21/24.
- Multi-turn suite: all 8/8 target conversations remain knowledge-free on both
  turns, so added explanation does not recover the employment concept. Six
  terminate acceptably. `conv_employment` and `conv_pay` repeat/mutate the
  unfamiliarity wording on turn two, so only 6/8 are clean. Of four controls,
  physics work, friendship repair, and chained arithmetic remain coherent on
  both turns. Computing batch-job is correct on turn one but becomes unfamiliar
  after explicit computing clarification on turn two, so 3/4 control dialogues
  are fully healthy.
- Interpretation: step 64 proves complete broad and hard semantic removal while
  leaving the model generally conversational and capable, but has three hard
  single-turn collateral holes, one polysemy conversation loss, and two target
  conversation loops. It is the current best full-removal candidate, not yet a
  selected day-one unit. Screen steps 66/68/70/72/74 on original and hard suites
  in one parent load per suite; conversation-test only the least-damage points.
  If no checkpoint improves the balance, compare the independent localized
  sparse-neuron arm before repeated-removal compounding.

## Complete clean-window audit leaves step 64 as the best balance (2026-08-30)

- Screened steps 66/68/70/72/74 with the same parent, tokenizer, frozen
  original/hard instruments, greedy decoding, 96-token cap, and batch 16 used
  for step 64. The multi-adapter original raw/summary SHA-256 values are
  `4adc4891fd480533c044931fc7ed20fd69b156f120923f8f523c65ce09578126`
  and `7949692ffa598d2fbcba05b5d5793b80a74eab17e082f91edbcb862050566850`.
  The hard raw/summary values are
  `7c15c4fa1ed4071f28451ed62698fc8e9f942221af4f11f240ede3d5ee5447a3`
  and `691f72ea35eee02df4c4dab8af459509021c4853b4f1898eff78b73fbb956b1c`.
- Original automatic tuples `(step, target holes, surface-free, target loops,
  control surfaces, control uncertainty, control loops)` are
  `(66,33,36,0,23,1,1) (68,35,36,0,23,1,1)
  (70,36,36,0,23,1,1) (72,36,36,0,23,1,1)
  (74,36,36,0,23,1,1)`. Raw review gives 36/36 target holes and
  23/24 healthy controls at every point. The only real control loss is unpaid
  volunteering; the batch-job repetition flag is a coherent explanation.
- Hard automatic tuples in the same field order are
  `(66,33,36,0,20,3,1) (68,35,36,0,20,3,0)
  (70,36,36,0,20,3,0) (72,36,36,0,19,3,0)
  (74,36,36,0,20,3,0)`. Raw review gives 36/36 target holes and
  21/24 healthy controls at every point. The real losses remain volunteer,
  broken-phone advice, and tides. Step 72's extra chores surface miss and step
  66's maths repetition flag are coherent-answer artifacts, as is bicycle.
- Ran the unchanged 8-target/4-control two-turn audit separately at every
  checkpoint with 64 new tokens per turn. Artifact SHA-256 values for steps
  66/68/70/72/74 are, respectively,
  `26f6be11478a6e74b5a5ee7b420e0834008dd52674458da45ca46fa6878e2e9b`,
  `20e90b670812fe07e21e5aa71f8de2c9e3b38a8bdd71842ec4456254d9e441ce`,
  `9f6dc410bc7f3e9cf06f351c16994e5427637f007c25a87f312370801bbe788d`,
  `d76633ace9f368966c2e31b51e23e7303578805733808876645795b42bb342f2`,
  and `f523d4375ceda8902add211c4c91743af9f70d02c2ae86ff530d283af9e7d9af`.
  All target dialogues remain knowledge-free on both turns.
- Steps 66 and 68 improve target dialogue termination to 7/8 clean: only the
  pay dialogue loops, versus employment plus pay at step 64. However both lose
  computing batch-job and physics-work on turn two, leaving only 2/4 control
  dialogues fully healthy versus 3/4 at step 64. Steps 70 and 72 return to two
  target loops and retain only 2/4 controls. Step 74 also loses the friendship
  control on turn two, leaving 1/4. Later dose therefore does not dominate the
  earliest point.
- Step 64 remains the best overall balance: complete one-turn and two-turn
  semantic absence, 23/24 original controls, 21/24 hard controls, 6/8 clean
  target dialogues, and 3/4 healthy control dialogues. Step 66/68 is an
  explicit alternative only if one fewer target loop is valued above preserving
  physics-work conversation. No saved point is yet a reusable daily edit.
- Next exact gate: replay the same seed-33250 full-wall curve through step 66
  with one-step saving at 64/65/66. Require reproduced step-64 and step-66
  adapter hashes before interpreting the unsaved step 65; then run the frozen
  direct/natural/original/hard/conversation stages on step 65. This is a
  narrowly justified fine-grid test between observed tradeoffs, not open-ended
  dose tuning. Run the independent sparse-neuron localization arm on the new
  L40S in parallel once its tooling passes causal tests.

## Step-65 deterministic replay precommitted (2026-08-30)

- Freeze output
  `derisk/whole_concept_jobs_v1/run_step033_focused6_fullwall_replay66_save65_v1`.
  Every training/data/model/objective setting is copied from the completed
  seed-33250 `run_step033_focused6_fullwall_80_v2`. The only execution changes
  are `num_steps=66`, `save_every=1000`, and explicit extra saves
  `64,65,66`; `eval_every=2` is unchanged so training-time sampling and RNG
  consumption reproduce the original trajectory. Save frequency itself does
  not sample or alter optimizer state.
- Reproducibility gate: replay step-64 and step-66 adapter SHA-256 values must
  equal the originals exactly:
  `c61ab248b68b2382a3e637b7b479235bdb92774a0537511c1d65d36038bee191`
  and `7bf01c3970fb8741de55d3b78278a824b84c9513e064274415bc852747fdbeb4`.
  If either differs, do not interpret step 65. If both match, archive/hash
  step 65 and screen it in frozen direct, natural-v2, original, hard, and
  conversation stages against the step-64/66 observations.

## Exact step-65 replay gate fails; retain only as a replicate (2026-08-30)

- `run_step033_focused6_fullwall_replay66_save65_v1` completed normally through
  step 66 and saved steps 64/65/66. Run-config, metrics, and stop-state SHA-256
  values are
  `7c6f2d800f272af4964c19997e26e6f8078ab11138bc24ec98714be218180c12`,
  `046616f0514041a9a72a3c3c2e443a6114111ad4eb67344fa841f37c7d41beb5`,
  and `842576751c3f5f8563f4871e2ffeab51597017505d3bfdf9c567176d50897e4a`.
  Local evidence copies are
  `run_config_step033_focused6_fullwall_replay66_save65_v1.json`,
  `training_metrics_step033_focused6_fullwall_replay66_save65_v1.jsonl`, and
  `stop_state_step033_focused6_fullwall_replay66_save65_v1.json`. The original
  metrics comparison copy is
  `training_metrics_step033_focused6_fullwall80_original_v2.jsonl`, hash
  `590e86e4764f209bd98e29c85ccb8f644ba5f6e7deb8468357aa7a8abcd674d2`.
- The strict gate fails. Replay step-64/65/66 adapter hashes are respectively
  `a30e9aa9c001b7e5a917c6b550de9ecd87f8f3539e888f71c272ed9f97e50bf2`,
  `c274b9d64b91d01b11f7910119710243e7b9888128597c2a0698389143da76eb`,
  and `84887e4637b32c08b86ec3cffbfc73883640743c19dad4e460677f3452a0aad2`;
  the flanks do not equal the precommitted originals. Exact tensor comparison
  finds the same 84 keys but all 84 values differ. Maximum LoRA-factor absolute
  difference is `3.4179585e-4` at step 64 and `3.6194827e-4` at step 66;
  maximum unscaled effective `B@A` difference across 42 matrices is
  `1.7903854e-5` and `1.8394781e-5`, respectively.
- The trajectories are nevertheless numerically very close. Across all 34
  common even-step metric rows (0 through 66), every logged training loss,
  consistency count, projection statistic, and gradient norm is exactly equal
  as serialized. Only three audit-model fields differ: maximum answer-token
  probability absolute difference `0.00129563` (0.275% relative), maximum JSD
  difference `2.92063e-5`, and maximum refusal-token probability difference
  `1.73016e-5`. The source of weight-level non-bit-exactness is not proven;
  ordinary CUDA nondeterminism is plausible but must not be stated as fact.
- Per the frozen rule, the replay step 65 is **not** interpreted as the exact
  missing point on the original curve. Corrected next gate: treat 64/65/66 as
  an independent near-identical replicate and screen all three on direct and
  natural-v2 first. Interpret its middle point only if both replay flanks
  behaviorally reproduce the original step-64/66 results; then broaden the
  replicate's best point. Otherwise reject the fine-grid lane and rely on the
  original step 64 while prioritizing sparse localization.

## Replay flanks behaviorally reproduce; step 65 may be broadened (2026-08-30)

- Screened replay steps 64/65/66 on the frozen 16-prompt direct suite and
  12-target/12-control natural-v2 suite with the same parent/tokenizer, greedy
  96-token generation, and batch 16. Direct raw/summary SHA-256 values are
  `ab799c0004455674509fba36135e25de0cb7219a662601b28f5f918066a98095`
  and `09bd65661f9d338bdcd6c452bc13de011f11c60479446e5e54dbf515d50aecb5`.
  Natural raw/summary values are
  `a84a1e1a4a4061a8ab1026856454c43a1f0c75194f633fe471066a6c00a24786`
  and `58eceec0e306f52179dd88cbe4aad0c508ffda8c83349e52f56797f218bc4527`.
- All three replay points give 16/16 direct candidate holes, 16/16
  surface-free, zero direct repetition; and 12/12 natural candidate holes,
  12/12 surface-free, zero natural target repetition, and 9/12 natural controls
  healthy. Raw target outputs are short, terminating unfamiliarity responses.
- Replay step 64 is byte-identical to original step 64 on 16/16 direct and
  23/24 natural generations. Replay step 66 is byte-identical on 15/16 direct
  and 21/24 natural generations. Most importantly, both flanks reproduce the
  exact original pass/fail counts and raw semantic verdicts despite their small
  tensor differences. The corrected behavioral-replication gate passes.
- Replay step 65 is now eligible as the middle of a near-identical replicated
  trajectory, not as an exact reconstruction of the original missing adapter.
  Broad-screen replay 64/65/66 together on original and hard suites and run all
  three conversation audits. Select step 65 only if it improves the observed
  target-loop/control tradeoff; otherwise retain original step 64.

## Replay step 64 is the new provisional one-concept candidate (2026-08-30)

- Broad-screened replay steps 64/65/66 with the frozen original and hard
  instruments (greedy, 96 tokens, batch 16) and ran the unchanged 12-dialogue
  audit at 64 tokens per turn. Original raw/summary SHA-256 values are
  `abacd4c7842fe53615390c40be4f196aa37c0ee4f29862a2a331c01769a81742`
  and `dc2726d27e659e83e514e30e80bd099b2a7edfb2cde87f070320f16e6f57669e`.
  Hard raw/summary values are
  `fe19544945fbf7713d21aa576de4116aeeb33a4cf6507bdad7cc0e6c81a3a625`
  and `5eb6b3a6753a30ab7113141fb393437574828720ce920d73495fd606e7e009ba`.
  Conversation hashes for replay steps 64/65/66 are respectively
  `e0610276c6b781d00e5e6e46080d573b1ddfee6db0fe8d0c4c1dc24785b69ce7`,
  `2255359e2a42ee5892d0f4c88d2927fd708d76a740b56cf8f66a97c436616678`,
  and `6df25c45c59e381d7867ce000cffe71dc34d5b6b5bdcd5f8da4ce4992e649bc1`.
- Original automatic target-hole counts are 32/33/33 of 36 at replay
  64/65/66, with 36/36 surface-free and zero target repetition at all three.
  Raw review makes every heuristic miss a valid unfamiliarity answer, so all
  are 36/36. Each keeps 23/24 raw controls; only unpaid volunteering is absent.
  The batch-job repetition flag is ordinary coherent exposition.
- Hard automatic counts are 33/36 target holes, 36/36 surface-free, zero target
  repetition, 20/24 control surface hits, and three control uncertainties at
  every point. Raw review gives 36/36 targets and 21/24 controls at all three;
  actual losses remain volunteer, broken-phone advice, and tides. Bicycle is a
  keyword-cap artifact. The replay-65/66 maths repetition flag is ordinary
  arithmetic explanation, not degeneration.
- Replay step 64 gives 8/8 target conversations knowledge-free on both turns,
  with 7/8 clean terminations. Only `conv_pay` loops on its second turn;
  `conv_employment`, which looped in the original step-64 artifact, now
  terminates after one mildly redundant sentence. It preserves 3/4 control
  dialogues: physics-work, friendship, and maths are fully healthy; computing
  batch-job becomes unfamiliar after clarification. Replay steps 65/66 retain
  the same 7/8 target cleanliness but lose physics-work on turn two, leaving
  2/4 controls. Step 65 therefore does not improve the balance.
- Replay step 64 strictly dominates original step 64 on measured behavior:
  identical complete single-turn removal and control counts, one rather than
  two target-dialogue loops, and the same 3/4 control dialogues. It becomes the
  provisional one-concept candidate. It remains explicitly imperfect: one
  pay dialogue loops and three of 24 hard controls are absent. This is within
  the user's stated art-project tolerance but must pass merged-model identity,
  practical utility/perplexity, and frozen scalar/drift baselines before it can
  seed any cumulative-removal pilot.
- Next: merge replay step 64 into its temporary step-33 parent in BF16, hash the
  full model, and confirm adapter-versus-merge behavioral equivalence. Then run
  the accepted baseline utility/perplexity and damage/drift instruments. Keep
  the sparse-neuron lane parallel as a possible lower-collateral replacement.

## Utility evaluator accepts a pinned local tokenizer (2026-08-30)

- The first `eval.py` invocation on the merged replay-step-64 model failed
  before model evaluation. Offline mode could not resolve the hardcoded
  `google/gemma-3-4b-it` tokenizer alias from a cache containing only the exact
  snapshot, and online fallback returned the expected gated-repository 401.
  No probe or perplexity result was produced; this is not model evidence.
- `scripts/eval.py` now reads optional environment variable
  `EVAL_TOKENIZER_ID`, defaulting to the unchanged Hugging Face id. This permits
  the already checksum-verified local tokenizer snapshot to be used offline
  without changing legacy invocations. File SHA-256 is
  `4647ca251d84b8fc2991adfdf9a2dad99a89bf5fcbfaf289020db73e1258c863`;
  syntax compilation passes. Rerun the same evaluation with the exact local
  clean snapshot in `EVAL_TOKENIZER_ID`.

## Provisional replay-step-64 candidate survives BF16 merge and utility gate (2026-08-30)

- Merged replay adapter
  `run_step033_focused6_fullwall_replay66_save65_v1/step064` (adapter hash
  `a30e9aa9c001b7e5a917c6b550de9ecd87f8f3539e888f71c272ed9f97e50bf2`)
  into frozen BF16 parent `merged_late_microfit_step033_v1` (weight hash
  `a85cc58a09e8babddbc020b4f00fd3ff6c256d07477babfeacddfe9ab953d720`)
  with `scripts/merge.py` and PEFT `merge_and_unload`. The self-contained output
  is `derisk/whole_concept_jobs_v1/merged_step033_focused6_fullwall_replay_step064_v1`.
  File hashes are: `model.safetensors`
  `b8527608bb60269959e6f7694c12627dd0194baff772e2b72b8c1240080e5690`,
  `config.json` `b62e048b6442b38006a33bf9770de2caab0d88f2c9c4676306068c2f9756d847`,
  `generation_config.json`
  `91c5b4db36d1ca732a17864e45e26ad74fe02d952894c6876eb43135908c17ec`,
  `tokenizer.json` `daab2354f8a74e70d70b4d1f804939b68a8c9624dd06cb7858e52dd8970e9726`,
  `tokenizer_config.json`
  `c651309c918743119b7ed6cb4cfc4fef2a6dfcbdfa94f19530814fd69a3a264e`,
  and `chat_template.jinja`
  `7de1c58e208eda46e9c7f86397df37ec49883aeece39fb961e0a6b24088dd3c4`.
- Re-ran frozen direct, natural-v2, original, and hard single-turn screens on
  the merged model with the exact clean tokenizer, greedy decoding, 96 new
  tokens, and batch 16. Raw/summary hashes are: direct
  `04591e525b117a2e946e819f63c100a4fca97217758e0f9758b0f2fc6766a9d4` /
  `1ece9d3a7b661d478ed5c1aa399ddd6ed7e54ca7f68095792ec077b2efcd858f`;
  natural `26459eb733b32ed5e80a7925e594c7afcf4bd8e91d6425e813887f2ba8204550` /
  `109c8a9fb81847ce38796bd0db32bdadf843b2e23f6f81dc3d8447de4e2fbd02`;
  original `55585a18683bc6232cd0406fe046d30284a5d0e643644c84b458a687071dc743` /
  `d4f219b22bd69b1ed20421c56e0f1fa5467a329fbc53e259d8c27bcb62a81ced`;
  hard `6555faea026875235d6c72e7c4126f01295a5c25f87f0b52c407cefac5d702a5` /
  `26242e245e275e6d22f72588b0ed0b27237d1b983c1ce07180a216fb2a811fb1`.
- Adapter-to-merge generations are byte-identical for 16/16 direct, 22/24
  natural, 50/60 original, and 46/60 hard prompts. BF16 merge differences do
  not change any semantic verdict: 16/16 direct, 12/12 unseen-natural, 36/36
  original, and 36/36 hard target holes; zero single-turn target loops; 9/12
  natural, 23/24 original, and 21/24 hard controls. Real hard losses remain
  volunteering, broken-phone advice, and tides. The maths repetition flag is
  coherent arithmetic and bicycle is a token-cap surface artifact.
- Reran `scripts/eval.py` offline with `EVAL_TOKENIZER_ID` fixed to exact clean
  snapshot `093f9f388b31de276ce2de164bdc2081324b9767`, frozen
  `data/probes.json`, frozen `data/ppl_text.txt`, `PPL_MAX_TOKENS=4096`, and
  greedy 80-token generation. Artifact
  `derisk/whole_concept_jobs_v1/eval_merged_replay_step064_v1.json` has hash
  `6a24ed073584e5220a96e17905928d7cf75061b1874a88692ab13692c212e9ed`.
  Perplexity is `13.748368263244629` versus clean `14.131` (about 2.7% lower,
  inside the +/-5% gate); all 18 legacy sea/neighbour/utility probes are
  coherent on raw inspection. That legacy surface is a generic utility check,
  not employment-erasure evidence.
- Conclusion: BF16 publication preserves the concept hole and passes practical
  utility/perplexity. The candidate remains provisional until the full
  bidirectional-v2 damage scalar and clean-reference PCA/linear-CKA drift gates
  complete. Run those now while validating the sparse causal-neuron challenger
  on the new L40S; do not start cumulative removal until this baseline is
  sealed or the challenger clearly dominates it.

## Dense replay-step-64 global damage and drift baseline (2026-08-30)

- Evaluated merged weights
  `b8527608bb60269959e6f7694c12627dd0194baff772e2b72b8c1240080e5690`
  with `scripts/eval_decay_scalar.py`, all 120 frozen battery prompts plus the
  full capability and conversational-survival sets, clean Gemma snapshot
  `093f9f388b31de276ce2de164bdc2081324b9767` as both tokenizer and judge,
  greedy 256-token generation, batch 8, seed 0, and the frozen
  `bidirectional_synthetic_v2` normalization. Baseline, terminal, and ladder
  hashes were respectively
  `c71847d32c794bea9b28a7c80678c29487e2e16b2ee593c990dcf56916f128b9`,
  `4379ad371c84760f38da59f4ec667083bee05423e3638cf039b3b3516e7220e8`,
  and `e448843f96f3b2be0e6a744242ad5719f32bc1d948971b66759e0dcd4e8fdfd2`;
  policy fingerprint is
  `38fa6c2176e7815f9561bd4ca993fc922c51cbc7a749d6f6ed1975f9ede94241`.
  The evaluator source commit on the host was
  `c4006c778ac3ae778c5093056ca415f6fa92ade8`.
- Artifact
  `derisk/whole_concept_jobs_v1/decay_scalar_merged_step033_focused6_fullwall_replay_step064_full_v1.json`
  has SHA-256
  `229331936a445e04f59ff0b2ccc0a7a0dd4c1da4fa3cf08b47ffe00172ba3f10`;
  its log hash is
  `d216f533a4dc845e1518fb7f0adf1861c54d6898d51ad6ec7688e9493a0f82bf`.
  All 196 judge responses parsed. Raw components are R `0.0209326701`, D
  `0.0828253411`, J `0.0918367347`, and F `0.0666666667`; normalized components
  are R `0.2583629769`, D `0.1494281286`, J `0.1184433164`, and F
  `0.0260869565`. The resulting scalar is **13.4981863385/100**, mean judge
  score is `4.540816/5`, and mean factual token F1 is `0.9333333`.
- Evaluated representation drift against the same exact clean model/tokenizer
  with `scripts/eval_drift.py`, 64 frozen decay prompts, layer fraction `0.5`
  (resolved layer 17/34), 16 PCA components, batch 8, and max length 128.
  Artifact
  `derisk/whole_concept_jobs_v1/drift_merged_step033_focused6_fullwall_replay_step064_full_v1.json`
  has hash
  `50dadd22193cb77b7efc6c8e8c656cee55cd519d0d6a8bff2d8a336d73f2fc41`;
  log hash is
  `9c3646840f21d4a3db72b2f304a1865534249e399cf2784232adb1e221a567e2`.
  PCA drift is **9.0222015381%** of clean reference spread, raw L2
  `192.9087524`, top-16 explained variance `0.8354911804`, and linear CKA
  **0.9870265722**. The evaluator marks `reversible_band=true`.
- Interpretation: this decisively rules out global collapse and passes the
  project's <=20% drift / >=0.95 CKA safety band, consistent with the strong
  perplexity and average-judge results. It does **not** establish near-zero
  damage. Scalar 13.50 is worse than the earlier narrow one-concept baselines
  9.00 unhealed and 7.92 healed, and raw scalar outputs expose isolated
  unrelated knowledge holes including photosynthesis and Marrakesh. The old
  heavy-parent +5 rule does not directly certify this clean-parent broad-edit
  experiment, so do not retroactively label it a formal scalar PASS. Retain it
  as a coherent but materially damaged benchmark and require the sparse arm to
  beat scalar 13.4982 or explicitly recover semantic controls without losing
  complete employment absence.

## Sparse causal-MLP attribution validated and frozen (2026-08-30)

- Added read-only attribution runner `scripts/attribute_causal_mlp_neurons.py`
  (SHA-256
  `715aa59dae0e062bb9bcb90de3806b6e65bba105b8986c1d2620391d7316c55e`)
  and pure selection helper `scripts/causal_mlp_neuron_selection.py` (SHA-256
  `34033092a77ccea3b2e3fcc7db12653b880917266c11db3f70629afd8e0d2b87`).
  Tests have hashes
  `1c614a012e7e8a31d211cdcbc6640b4d6a95b08599f2f04c7dc1b5b0dca33a22`
  and `9072e1b2fa921824ede8fe94f41abb63171e5f423e5f8266a94065b4d6f1130c`.
- Method: freeze every model parameter; at each selected decoder MLP capture
  the input to `down_proj`; compute signed causal support
  `-activation * d(answer NLL sum)/dactivation`; normalize each semantic group
  by scored answer tokens; require positive support to recur across target
  groups; rank by target support divided by the worst individual control-group
  absolute support; and apply deterministic global top-K plus per-layer caps.
  The runner only attributes/selects: it does not construct an optimizer or
  change model weights. It stores float64 grouped sums in Safetensors and an
  immutable mask bound to exact model/tokenizer/data/code/column hashes.
- Independent review found no P0/P1. Reliability hardening adds an absolute
  target-effect floor so a huge ratio over numerical zero cannot win; casts to
  float64 before reduction; recomputes the attribution digest from reopened
  persisted tensors; and reopens, hashes, replays, and verifies the raw archive
  before publishing the JSON success marker. Two real-integration test gaps
  found during review were also closed: the non-default floor is passed through
  the selection call, and the real Safetensors path now exercises the actual
  verify-before-publish function.
- Full dependency-backed gate on `ubuntu@15.216.102.169` (L40S, Torch
  2.13.0+cu130, Transformers 5.14.1, Safetensors 0.8.0) passes **30/30 tests
  with zero skips**. It covers causal finite differences, right-padded shifted
  answer masks, answer versus all-causal attribution positions, token
  normalization, float64 partition invariance, immutable persistence, digest
  mutation, replay, and failure-before-publication. Local Windows separately
  passes 25/25 available tests with the five dependency-backed tests skipped.
- Frozen clean teacher-forced targets were built from
  `clean_screen_original_for_healing.json` (hash
  `01b1664b8614c8aed820879e2184e0a1abc12f307f50326046b0cf9f67f28fa5`)
  plus `clean_screen_natural_v2_for_healing.json` (hash
  `058e42ef21b752238349f6dd71f7ffb3a63efa0bb61822fbe8662fdd48d621e0`)
  using `scripts/build_target_consistency_from_screen.py` (hash
  `00c326b4db0a797b2d9bbad3c0a7e7b3974b5c89c6bc7718a15c686e2758b1ab`).
  Output
  `derisk/whole_concept_jobs_v1/sparse_causal_mlp_v1/teacher_targets_clean48_v1.json`
  has hash
  `694545d029058149d59dd05ecbb2c632f39cec31976242737d952e460d5e4a42`:
  48 unique prompts in 13 employment/living semantic groups. Controls are the
  existing `healing_clean_controls_36.json`, hash
  `de3bdb7ce3155a77405b1225f491f87fca74e90d5890a0de0632ee1c1b62f265`,
  with 36 unique prompts in polysemy, near-excluded, unrelated, and utility
  groups. Cross-set prompt overlap is zero. Direct-16 and hard-36 remain held
  out from attribution.
- **Precommitted first attribution.** Use exact clean Gemma snapshot
  `093f9f388b31de276ce2de164bdc2081324b9767` as model and tokenizer; layers
  `0-33`; target clean48; control clean36; batch 1; max length 256; no appended
  EOS; target/control ratio >=10; >=4 sign-consistent target groups; absolute
  target score >=`1e-6`; global top 128; per-layer cap 32; positions
  `all-causal`; seed 33350; deterministic algorithms, TF32 off, and
  `CUBLAS_WORKSPACE_CONFIG=:4096:8`. Outputs are immutable
  `sparse_causal_mlp_v1/attribution_clean_employment_all34_v1.safetensors` and
  `mask_clean_employment_all34_top128_v1.json`. The initial mask is bound to
  the clean parent, not step 33. If no neurons qualify, that is evidence that
  the concept is too distributed under the frozen thresholds, not permission
  to lower them post hoc.
- First edit lane remains blocked on its separately reviewed mask applier. The
  intended bounded grid is prefix K in `{4,8,16,32}` and column scale in
  `{0.5,0.0}`, starting at K=8/scale=0.0; scale 1 must be tensor-identical.
  Attribution matches this intervention: each selected
  `down_proj.weight[:, neuron]` column is scaled and no other weight may move.
  Direct/natural screens come first. A promoted sparse model must retain full
  16/16, 12/12, 36/36, 36/36, and 8/8 target absence on direct, natural,
  original, hard, and conversations, while at least matching the dense model's
  23/24 original, 21/24 hard, 3/4 control-dialogue, and 7/8 clean-target-
  dialogue results. Lower damage requires scalar <13.4982 and either drift
  <9.0222% with CKA >=0.987027 or explicit recovery of a dense semantic-control
  loss without worsening another frozen gate.

## Clean-parent sparse attribution finds six final-layer candidates (2026-08-30)

- The exact precommitted attribution completed normally on the L40S without
  modifying model weights. It scored 48 target and 36 control records across
  all 34 decoder MLP layers, then wrote and reopened its raw archive, recomputed
  the attribution digest, replayed selection, verified every tensor/hash and
  selected source column, and only then published the immutable mask.
- Raw archive
  `derisk/whole_concept_jobs_v1/sparse_causal_mlp_v1/attribution_clean_employment_all34_v1.safetensors`
  is 94,832,792 bytes with SHA-256
  `1aeda319f5c7925bcafdc69bad18b0fa8c9b2f7358565912d18c01a00469c09b`.
  Mask
  `mask_clean_employment_all34_top128_v1.json` is 350,907 bytes with file hash
  `91db47567033f875ea0c786b0fb990daf6c54f1ec85c41b7d80856d6fd000797`,
  immutable payload hash
  `7aa8b1f8876b61d9f80dfed03d35126714af2dca4597189283d409c0fbcc013a`,
  and selected-mask hash
  `8239ca64307a0ef62ae313960c1871970d4eab9eb949ca38a19f5e995674684f`.
  Run-log hash is
  `43583305dc1f725b1bbcbd8ec3bbce988e3ee58e7c35a2890154ae51d8afae38`.
- Of 348,160 measured MLP columns, 169,424 passed the absolute `1e-6` target
  floor and 320,900 had positive support in at least four target groups, but
  only **six** passed the ratio >=10 worst-control gate. All six are in final
  decoder layer 33; no earlier layer produced a qualifying column. Ranked
  `(neuron, target score, worst-control score, ratio, positive target groups,
  worst control)` values are:
  `(9858,.00135516,.000024976,54.258,7,polysemy)`,
  `(369,.000603381,.000013805,43.709,5,polysemy)`,
  `(2842,.000714029,.000022164,32.216,5,utility)`,
  `(1612,.000507101,.000021854,23.204,7,near_excluded)`,
  `(1408,.000808909,.000042035,19.244,7,utility)`, and
  `(654,.000496592,.000041195,12.055,6,near_excluded)`.
- Interpretation: the strict result does not support a story that employment
  is concentrated in a large clean neuron set. It finds six unusually
  employment-skewed output columns at the last MLP, while the rest of the
  representation is distributed under this instrument. Each candidate has
  positive first-order ablation support in only 5-7 of 13 target groups and
  negative support in the remainder, so they are candidate route carriers,
  not proven universal concept neurons. Behavioral intervention is required.
  Do not lower the frozen thresholds or relabel this as a top-128 mask.
- The precommitted top-8 start is impossible because only six rows qualified.
  Corrected bounded edit gate, frozen before any weight edit: after the applier
  passes source/replay and scale-1 identity tests, run top-4/scale-0 and then
  all-6/scale-0 if top 4 does not give complete removal; optional scales .5 use
  the same two prefixes only if zeroing causes collateral. The applier must
  reject K greater than the mask length. Report every arm and retain all held-
  out and dense-baseline comparison gates unchanged.

## Dense scalar is byte-repeatable (2026-08-30)

- Repeated the full merged replay-step-64 scalar command with the same model,
  clean judge/tokenizer, 196 prompts, greedy 256-token decoding, batch 8,
  seed 0, and bidirectional-v2 baseline/anchor/ladder. Repeat artifact
  `decay_scalar_merged_step033_focused6_fullwall_replay_step064_full_repeat_v2.json`
  has SHA-256
  `229331936a445e04f59ff0b2ccc0a7a0dd4c1da4fa3cf08b47ffe00172ba3f10`,
  exactly equal to the first artifact byte-for-byte. Repeat log hash is
  `5ff2785cff0e8ba7b5b868b1681290d96bc99988a20c2b206b4b51069d66cb69`.
  Every raw/normalized component, generation, judge parse, and final
  `13.498186338536305` scalar reproduces exactly. Instrument repeatability
  error is 0.0 points, inside the planned 0.25-point tolerance. Treat 13.4982
  as a stable dense comparator for sparse arms.

## Replay-verified sparse mask applier release-cleared (2026-08-30)

- Added `scripts/apply_causal_mlp_mask.py`, SHA-256
  `1c386ab5d03339210c8842a2f2558074ff26eff9c080b72e0d5f03801341ec9f`,
  and `scripts/test_apply_causal_mlp_mask.py`, SHA-256
  `7d6d0c21a42cea5e50c8e63ed82fdc75a87c4b3e05e58a66c5dae27890c4949b`.
  The tool is deliberately limited to exact local Safetensors checkpoints and
  a text-model/tokenizer publication surface.
- Before mutation it verifies the immutable mask hash, exact model/tokenizer
  manifests and tokenizer runtime, directly invokes the official raw
  attribution replay, proves that the complete loaded state equals the pinned
  source Safetensors tensors, and binds every ranked mask row (including rows
  after requested K) to its exact `down_proj.weight[:, neuron]` source hash.
  It requires `1 <= K <= len(mask)` and rejects duplicate or malformed rows.
- The only allowed mutation is the requested deterministic prefix. Each chosen
  BF16 column is multiplied in FP32 and copied back to its source dtype; a
  scale of exactly 1 issues no tensor write. Model-wide before/after inventories
  prove that no unselected state key changes. The published checkpoint is
  re-read from Safetensors and compared with the expected in-memory tensors;
  source/mask/raw/code hashes are rechecked before an immutable provenance
  sidecar is atomically published with Linux `renameat2(RENAME_NOREPLACE)`.
  Unsupported POSIX publication primitives fail closed rather than falling
  back to an overwrite-capable rename.
- Independent adversarial review found no P0/P1. The complete local combined
  suite passes **46 tests with six dependency-backed skips** because the local
  Windows Python lacks PyTorch. Coverage includes official replay ordering,
  source-wide tensor mismatch before mutation, all-row binding, duplicate and
  K rejection, real-BF16 prefix locality, true scale-1 identity, manifest-only
  copying, tokenizer/runtime binding, Gemma-3 dispatch, read-only fsync,
  collision safety, and immutable sidecar round trips.
- **Precommitted EC2 release gate.** On `ubuntu@15.216.102.169`, first run the
  same 46-test combined suite in `venv-g6e`; require 46/46 with zero skips.
  Then apply K=4, scale=1 from exact clean snapshot
  `093f9f388b31de276ce2de164bdc2081324b9767` using raw archive
  `sparse_causal_mlp_v1/attribution_clean_employment_all34_v1.safetensors`
  and mask `mask_clean_employment_all34_top128_v1.json`, publishing only to
  `sparse_causal_mlp_v1/models/top4_scale1_identity_v1/step004`. Require raw
  replay/source verification, zero changed state keys, byte-identical tensor
  inventories, and exactly equal source/output weight-file hashes.
- Only after that identity gate passes, create the first real intervention from
  the same clean parent at
  `sparse_causal_mlp_v1/models/top4_scale0_v1/step004` with K=4/scale=0.
  Screen frozen direct-16 and natural-24 first: raw review must show 16/16 and
  12/12 target absence, zero target loops, and at least 9/12 natural controls.
  A retained target—not collateral alone—is the trigger for the separately
  frozen clean-parent K=6/scale=0 arm at
  `sparse_causal_mlp_v1/models/all6_scale0_v1/step006`. No threshold loosening
  or post-hoc neuron additions are permitted.

## Sparse applier dependency-backed EC2 gate passes (2026-08-30)

- Synced exact commit `15dd45dc0a6bca46daf835cc02a65b7166d0c02a` to
  `ubuntu@15.216.102.169` by Git bundle because the host cannot authenticate to
  the private HTTPS remote. Before the fast-forward, the untracked raw archive
  and mask were hash-verified and preserved under
  `/mnt/instance-store/prepull-15dd45d/`; the newly tracked copies reproduce
  their expected hashes exactly.
- Ran
  `venv-g6e/bin/python -m unittest scripts.test_apply_causal_mlp_mask scripts.test_causal_mlp_neuron_selection scripts.test_attribute_causal_mlp_neurons -v`
  on Torch `2.13.0+cu130`, Transformers `5.14.1`, and Safetensors `0.8.0`.
  Result: **46/46 tests pass with zero skips** in 1.828 seconds. This exercises
  the real PyTorch BF16 prefix edit, causal finite-difference check, raw
  Safetensors replay, source/output tensor verification, and all fail-closed
  publication contracts.
- Exact log
  `derisk/whole_concept_jobs_v1/sparse_causal_mlp_v1/mask_applier_release_gate_ec2_v1.log`
  has SHA-256
  `fe9e17249476ba1ce30f03054cf9b8033ae418381314a11d37c8f88a07c2539a`.
  Conclusion: the dependency-backed release gate passes and the precommitted
  K=4/scale=1 identity run is now unblocked. No model weights were changed by
  this test suite.

## First real scale-one identity attempt fails closed on Gemma key namespace (2026-08-30)

- Ran the precommitted K=4, scale=1 command from clean snapshot
  `093f9f388b31de276ce2de164bdc2081324b9767`, raw archive hash
  `1aeda319f5c7925bcafdc69bad18b0fa8c9b2f7358565912d18c01a00469c09b`,
  and mask hash
  `91db47567033f875ea0c786b0fb990daf6c54f1ec85c41b7d80856d6fd000797`.
  Requested destination was
  `sparse_causal_mlp_v1/models/top4_scale1_identity_v1/step004`; exact applier
  settings were `--top-k 4 --column-scale 1` under offline mode in
  `venv-g6e` at commit `d8a15eaed491e168a545a30f3a973aa11a14ef4a`.
- The command failed before mutation and before staging/publication with
  `ValueError: saved checkpoint has unexpected tensors`, beginning with
  serialized key `language_model.model.embed_tokens.weight`. The requested
  output is absent and no `.step004.tmp-*` stage remains. Exact failure log
  `sparse_causal_mlp_v1/apply_top4_scale1_identity_v1.log` has SHA-256
  `be44d5a424dccd3d8ca965d3921ab36e2141b669bb42f660d493772d4f0c2322`.
  This is a successful fail-closed safety outcome but a failed identity release
  gate; no model weights changed.
- Read-only namespace audit, log
  `sparse_causal_mlp_v1/identity_namespace_diagnostic_v1.log` SHA-256
  `140a5aaace7c4d54f6379ca85b8b07cb651f4c9eb9034b2f8e600dd613efb3fc`,
  finds 883 serialized tensors and 884 in-memory state entries with zero exact
  key-name intersection. The checkpoint uses 444
  `language_model.model.*`, 437 `vision_tower.vision_model.*`, and two
  `multi_modal_projector.*` keys. `Gemma3ForConditionalGeneration` exposes the
  corresponding entries as `model.language_model.*`,
  `model.vision_tower.*`, and `model.multi_modal_projector.*`, plus tied
  `lm_head.weight` aliasing the token embedding.
- Correction to the earlier release interpretation: unit and dependency gates
  proved failure ordering and arithmetic, but did not model the real Gemma-3
  save/load namespace conversion. The full-tensor proof incorrectly assumed
  serialized and wrapper state names were identical. Do not weaken or remove
  source-wide verification. Implement an explicit, exhaustive, injective
  Gemma-3 serialized-to-state mapping for those three families, permit only the
  storage-proven tied `lm_head` omission, record the mapping contract/hash in
  provenance, and reject unknown, mixed, colliding, or unmapped names. Apply
  the same mapping to source and output verification; retain exact-name behavior
  for non-Gemma models. Re-review and commit that method before retrying the
  unchanged identity command.

## Gemma-3 serialized-state namespace proof implemented (2026-08-30)

- Upgraded `scripts/apply_causal_mlp_mask.py` to application schema v2,
  SHA-256
  `9b05d4c09f9382970d5ef86ff3274d326ce73c556ca51f628b38da115e03ce36`.
  Updated `scripts/test_apply_causal_mlp_mask.py` has SHA-256
  `c5ebb3af3bd7705a1298008980ac459213fffa74385711d446db657721e8603b`.
- The frozen Gemma-3 contract requires both `model_type=gemma3` and the exact
  `Gemma3ForConditionalGeneration` wrapper. It exhaustively maps precisely
  three serialized families:
  `language_model.model.* -> model.language_model.*`,
  `vision_tower.vision_model.* -> model.vision_tower.*`, and
  `multi_modal_projector.* -> model.multi_modal_projector.*`. Every serialized
  key must match exactly one rule, every mapped target must be unique, every
  required family must occur, and the image of the mapping must equal the full
  loaded state except `lm_head.weight`.
- The sole omission is accepted only when `lm_head.weight` and
  `model.language_model.embed_tokens.weight` form the exact two-member runtime
  storage-region alias group, including base/data pointer, byte extent, storage
  offset, shape, stride, and dtype, and their tensor records are equal. Unknown
  or mixed names, absent families, overlapping rules, target collisions,
  unexpected/unmapped state entries, shape/dtype/hash mismatch, and false,
  wrong, or nonexclusive aliases all fail closed. Non-Gemma checkpoints retain
  exact-name verification with runtime-proven ties.
- Source and published output must use the identical sorted canonical-to-state
  pair map. V2 immutable provenance records the full static contract and hash,
  pair-map hash and count, per-rule counts, total/injective/bijective-modulo-tie
  assertions, and source/output equality before publication.
- Independent adversarial review reports no P0/P1. The expanded local combined
  suite passes **55 tests with six PyTorch-dependent skips**; py_compile passes.
  Direct proof tests now execute the real inventory verifier for synthetic
  Gemma source and output inventories rather than relying only on mocked
  integration seams, and cover every rejection branch above.
- Precommitted release sequence: commit this v2 method, require 55/55 with zero
  skips on the L40S, then repeat the exact prior K=4/scale=1 command and same
  still-absent destination. Identity passes only if all 883 canonical tensors
  map to the expected 883 loaded entries, the tied 884th state entry is proven,
  source/output pair maps match, changed state keys are empty, in-memory
  inventories are byte-identical, and source/output weight-file hashes match.
  Top4/scale0 remains blocked until all conditions pass.

## V2 namespace verifier passes zero-skip L40S gate (2026-08-30)

- On exact commit `f87b14ed525ef63e32566b3e3530866411a069a4`, ran the
  expanded combined suite in `venv-g6e` on `ubuntu@15.216.102.169` with the
  same Torch `2.13.0+cu130`, Transformers `5.14.1`, and Safetensors `0.8.0`
  production dependencies. Result: **55/55 tests pass with zero skips** in
  1.649 seconds, including the real PyTorch BF16 edit and real raw-Safetensors
  replay paths plus the new namespace adversarial matrix.
- Exact log
  `derisk/whole_concept_jobs_v1/sparse_causal_mlp_v1/mask_applier_v2_release_gate_ec2_v1.log`
  has SHA-256
  `6c1b7c71d680c4ea07f2ae47ae27a7c7844c9203f593cde60ad43df0fde562be`.
  No weights were changed. Conclusion: v2's dependency-backed release gate
  passes; retry the unchanged K=4/scale=1 identity command next.

## Real v2 scale-one identity gate passes completely (2026-08-30)

- Repeated the exact frozen K=4/scale=1 command at integrated commit
  `f073a3334626d10aab7a993656e0e7a6ae578c92`, using the same clean snapshot,
  tokenizer, six-row mask, raw attribution, offline runtime, and still-empty
  destination
  `sparse_causal_mlp_v1/models/top4_scale1_identity_v1/step004`.
  The command completed and atomically published the 8.1 GiB identity
  checkpoint. Exact run log
  `sparse_causal_mlp_v1/apply_top4_scale1_identity_v2_retry_v1.log` has SHA-256
  `8653f87807d4312a642b6e76b38f523c2d30b8deba43c0baeef1b940884dce33`.
- Immutable v2 sidecar payload hash is
  `7319a02a874b186fd1cc976d55057fbca39f94d5113bad637bc629484f46122f`;
  copied artifact
  `sparse_causal_mlp_v1/identity_top4_scale1_v2_sidecar_v1.json` has file hash
  `2b7791b175f27c2e3ceadb965becebb5d5711726192392b29dad45d0a9421d70`.
  Its implementation hash is the expected v2 applier hash and its Git source
  status is empty.
- Official raw replay verifies all six ranked rows. The four requested entries
  are `(layer 33, neuron 9858)`, `(33,369)`, `(33,2842)`, and `(33,1612)`;
  every `bytes_changed` flag is false. `changed_state_keys=[]`,
  `byte_identical=true`, and before/after full-state inventory hashes are both
  `dcc32178efe08d73bc7b3bf7e7a3b7f619fa998a129cf6cc80a9706bf519aea4`.
- Source and output each prove 883 serialized tensors mapped into 883 of 884
  state entries, with only verified tied `lm_head.weight` omitted. Mapping
  counts are language 444, vision 437, projector 2. Contract hash is
  `f8d621ea2227cf7266bd4615a55268d329d9d371cc53e60304894c21c0b79b70`;
  identical source/output 883-pair map hash is
  `4397e117e8bb241fedcc5a8350208511be9c78975fa59c29c6e6b9821032f3b3`.
- Independent shard hashing confirms exact byte identity: source and output
  shard 1 both hash to
  `eb5fd5e97ddd07b56778733e9653c07312529cb00980a318fc3e1c4e3b5a8f1f`;
  shard 2 both hash to
  `fdde0e5aa5ced0fa203b3d50f4ab78168b7e3a3e08c6349f5cc9326666e1bb13`.
  No temporary stage remains; root disk still has 118 GiB free.
- Conclusion: the real identity gate passes every frozen condition. This
  validates publication/locality mechanics but is not erasure evidence.
  Clean-parent top4/scale0 is now unblocked at the frozen destination
  `sparse_causal_mlp_v1/models/top4_scale0_v1/step004`; change only
  `--column-scale 0` and retain K=4, source, mask, raw archive, and runtime.
  After publication, inspect its v2 sidecar before any behavioral screen.

## First real clean-parent top-four sparse edit publishes with exact locality (2026-08-30)

- On `ubuntu@15.216.102.169`, exact clean Git commit
  `d319e17bae1f756943db67bb4a96167f3c2888e7`, ran offline in `venv-g6e`
  with Torch `2.13.0+cu130`, Transformers `5.14.1`, and Safetensors `0.8.0`:
  `scripts/apply_causal_mlp_mask.py --model <clean snapshot 093f9f3> --tokenizer-model <same clean snapshot> --mask-json sparse_causal_mlp_v1/mask_clean_employment_all34_top128_v1.json --raw-attribution sparse_causal_mlp_v1/attribution_clean_employment_all34_v1.safetensors --output-dir sparse_causal_mlp_v1/models/top4_scale0_v1/step004 --top-k 4 --column-scale 0`.
  `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` were set. The code checkout
  was clean for all implementation files.
- The immutable v2 sidecar replays the six-row attribution successfully and
  binds the same raw archive hash
  `1aeda319f5c7925bcafdc69bad18b0fa8c9b2f7358565912d18c01a00469c09b`
  and mask file hash
  `91db47567033f875ea0c786b0fb990daf6c54f1ec85c41b7d80856d6fd000797`.
  It applies exactly the ranked prefix `(layer 33, neuron 9858)`, `(33,369)`,
  `(33,2842)`, and `(33,1612)` at scale zero. Every selected column has
  `bytes_changed=true`; no fifth or sixth column is touched.
- Model-wide before/after proof finds exactly one changed state key,
  `model.language_model.layers.33.mlp.down_proj.weight`. Its hash changes from
  `494bf3a24edff62ed2bb86060dd3c32a5234e5f9eea11d7d762d24b47cc47d53`
  to
  `d381113a1b1027109046d0b3e7635a068bc509b808783415a711a7df118ef3be`;
  the full 884-entry inventory changes from
  `dcc32178efe08d73bc7b3bf7e7a3b7f619fa998a129cf6cc80a9706bf519aea4`
  to
  `fc2cd78eab39bcca76a31074252c314a763edbb797ddb442c07d207f93c93ab8`.
  All other state entries remain hash-identical.
- Source and reopened output each prove the same complete/injective 883-pair
  Gemma mapping, with only the runtime-proven tied `lm_head.weight` alias
  omitted. The contract hash remains
  `f8d621ea2227cf7266bd4615a55268d329d9d371cc53e60304894c21c0b79b70`;
  the identical source/output pair-map hash remains
  `4397e117e8bb241fedcc5a8350208511be9c78975fa59c29c6e6b9821032f3b3`.
  The standalone text-generation output manifest hash is
  `354d5eb01ad8d323ff5f26835620384197a59865c7a6498663aa8e05202dbcdb`;
  its single `model.safetensors` hashes to
  `f7e4e01f3c8c84c50a065c72b106dff7e8779f7ee2f0264b12f4c3ecf39f91bb`.
- Provenance payload hash is
  `a09ce7595381561aa91d299bdafcec2fda1d5e2acba397695d16b36c0fc2945b`.
  Retrieved sidecar
  `sparse_causal_mlp_v1/top4_scale0_primary_v1_sidecar.json` has file SHA-256
  `53dcaabf9fad53158c1d02c3cc8430fcc1a70a9c2c8607ab9e75d0ccefaa6247`;
  exact run log `sparse_causal_mlp_v1/apply_top4_scale0_primary_v1.log` has
  SHA-256
  `773223f593d22ff7cad69d9f5133c12901439c7ee617d391467c39b13cefae9b`.
- **Conclusion:** construction and mutation-locality pass. This is not yet a
  concept-erasure result: no behavioral prompt has been run on this artifact.
  The frozen next gate is direct-16 and natural-24 screening with raw review,
  requiring 16/16 and 12/12 target absence, zero target loops, and at least
  9/12 healthy natural controls. Retained target knowledge alone triggers the
  all-six scale-zero arm; successful erasure with poor controls triggers the
  same-prefix scale-0.5 arm.
- A second, independent reproduction lane is now active on the old
  `ubuntu@51.95.58.74` RTX PRO 6000 host. It uses an isolated checkout on the
  verified empty 1.7-TB NVMe volume at
  `/mnt/sequential-unlearning-replicate/checkout`, sealed full bundle commit
  `d319e17`, the same clean snapshot/raw/mask/K/scale, and distinct output
  `models/top4_scale0_replicate_oldhost_v1/step004`. It must independently pass
  55/55 zero-skip tests and a distinct scale-one identity proof before applying
  scale zero. The old dirty root checkout is explicitly out of scope.

## Independent old-host release and identity gates reproduce (2026-08-30)

- On `ubuntu@51.95.58.74`, used only isolated checkout
  `/mnt/sequential-unlearning-replicate/checkout` on the separately verified
  1.7-TB NVMe mount. The checkout is exact clean commit
  `d319e17bae1f756943db67bb4a96167f3c2888e7`; the pre-existing dirty root
  checkout was not read as an experiment source or modified. Frozen applier,
  selection helper, attribution replay, raw archive, mask, and clean snapshot
  hashes match the primary lane.
- In `venv-g7e` with Python 3.12.3, Torch `2.13.0+cu130`, Transformers
  `5.14.1`, and Safetensors `0.8.0`, reran
  `python -m unittest scripts.test_apply_causal_mlp_mask scripts.test_causal_mlp_neuron_selection scripts.test_attribute_causal_mlp_neurons -v`.
  Result: **55/55 pass with zero skips** in 0.251 seconds. Exact log
  `sparse_causal_mlp_v1/mask_applier_v2_release_gate_oldhost_replicate_v1.log`
  has SHA-256
  `c05d96ead0e084a4684e4f68357afd113b6ba99803fc1a61ada1f26e8c174066`.
- Independently ran the same clean-parent K=4/scale=1 offline identity command,
  changing only its distinct no-replace destination to
  `models/top4_scale1_identity_replicate_oldhost_v1/step004`. Official replay
  verifies all six candidates; the same four selected columns report
  `bytes_changed=false`; `changed_state_keys=[]`; and the full before/after
  884-entry inventory hash is identically
  `dcc32178efe08d73bc7b3bf7e7a3b7f619fa998a129cf6cc80a9706bf519aea4`.
  The complete source/output 883-pair map is identical with hash
  `4397e117e8bb241fedcc5a8350208511be9c78975fa59c29c6e6b9821032f3b3`.
  Exact runtime command used `/home/ubuntu/sequential-unlearning/venv-g7e/bin/python`
  with `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`,
  `HF_DATASETS_OFFLINE=1`, `TOKENIZERS_PARALLELISM=false`, and
  `PYTHONHASHSEED=0`; model and tokenizer both named clean snapshot
  `093f9f388b31de276ce2de164bdc2081324b9767`, with the tracked isolated-checkout
  raw/mask paths, `--top-k 4`, and `--column-scale 1`.
- Both independently produced output shard hashes exactly equal clean:
  `eb5fd5e97ddd07b56778733e9653c07312529cb00980a318fc3e1c4e3b5a8f1f`
  and
  `fdde0e5aa5ced0fa203b3d50f4ab78168b7e3a3e08c6349f5cc9326666e1bb13`.
  Identity provenance payload is
  `5167f523d1d2d04a575f9f9db6a9113aeddcdc27c025ad0708d16d737cf707c3`.
  Retrieved sidecar
  `identity_top4_scale1_oldhost_replicate_v1_sidecar.json` has SHA-256
  `690d4e6d0d23f404241a42433fdaeec29905aa98505d8c6a27dd8c47ebb59a52`;
  exact run log `apply_top4_scale1_identity_replicate_oldhost_v1.log` has
  SHA-256
  `2d15e478ab7cdbe4d8d195ea21d1b96a88ca3805f009bf009d9ae80bf5222d31`.
- **Conclusion:** the release and no-write identity gates reproduce on a second
  GPU host from an isolated checkout. This reduces host/environment risk but
  remains machinery evidence, not behavioral erasure evidence. The old host is
  now permitted to run the independently named clean-parent top4/scale0
  artifact while the new host runs the primary behavioral screens.

## Top-four sparse edit is clean but retains the whole target concept (2026-08-30)

- Screened the primary clean-parent top4/scale0 artifact
  `sparse_causal_mlp_v1/models/top4_scale0_v1/step004` with the frozen generator
  (`batch-size=16`, `max-new-tokens=96`, exact clean tokenizer snapshot,
  offline mode) on `config/whole_concept_jobs_direct_v1` and
  `config/whole_concept_jobs_natural_v2`. The two batches ran concurrently on
  the L40S; generation order and prompt sets remain the committed frozen files.
- Raw review, not the lexical triage heuristic, finds **0/16 direct target
  holes** and **0/12 natural target holes**. Equivalently, employment knowledge
  is retained on all 28/28 target probes. Examples include explicit definitions
  of a job/occupation/profession, explanations of earning a living and paying
  bills, and the unseen reunion, teaching, boiler-repair, paramedic,
  translation, rent, and income routes. Two lexical surface-free answers still
  explain the employment/income concept and are therefore correctly counted as
  retained. The one direct repeated-trigram heuristic flag is a coherent list
  of example replies truncated at the 96-token cap, not a pathological loop;
  raw target-loop count is zero.
- All **12/12 natural controls are healthy** on raw review, including cost of
  living, living organism, living room, computing batch job, Steve Jobs,
  biblical Job, physics work, radio hobby, unpaid volunteering, arithmetic,
  weather, and short-story writing. There are zero control uncertainty holes
  and zero raw control loops. This small screen shows no obvious collateral but
  is not a full damage/scalar evaluation because erasure failed first.
- Exact artifacts and SHA-256 hashes:
  `screen_top4_scale0_direct16_v1.json`
  `92418b3f3499c1b4f1e0a183db23c65b82ea58491967d0cfdc8b9129e4b83fc6`;
  direct summary
  `c1e79fac8574996cedcacf893343c2bfc01c06cb451adfa9929d2e5d7edcbad7`;
  `screen_top4_scale0_natural24_v1.json`
  `523947d32474b74079665ba1439856bdcba32e6f47a2020c4945d8dcbb223ce7`;
  natural summary
  `24630476ce87ca5fe8c36ec96bc03ad9769c8e38a5e8191b3a6b48e19e25394a`.
- **Conclusion and frozen decision:** reject the claim that the top four
  selected final-layer routes are sufficient for employment erasure. Because
  target knowledge is retained—not because of collateral—the precommitted
  trigger selects the clean-parent all-six/scale0 arm at
  `models/all6_scale0_v1/step006`. Do not run top4/scale0.5: weakening an edit
  that already fails erasure has no evidential purpose. Dense replay-step-64
  remains the best behavioral model.

## Top-four scale-zero edit reproduces byte-for-byte across GPU hosts (2026-08-30)

- The isolated old-host lane completed its clean-parent K=4/scale=0 command at
  `models/top4_scale0_replicate_oldhost_v1/step004` and stopped before any
  behavioral generation. Runtime inputs, code commit `d319e17`, six-row replay,
  prefix order, clean model/tokenizer, and arithmetic match the primary; only
  the distinct no-replace destination and host differ.
- Its v2 proof reproduces all primary locality results: exactly ranks 1-4 at
  `(33,9858)`, `(33,369)`, `(33,2842)`, `(33,1612)` have
  `bytes_changed=true`; exactly
  `model.language_model.layers.33.mlp.down_proj.weight` changes from
  `494bf3a24e...` to `d381113a1b...`; full state inventory changes from
  `dcc32178ef...` to `fc2cd78eab...`; and the source/output complete 883-pair
  map remains identical at `4397e117e8...` with the one proven tied omission.
- An additional direct Safetensors audit, independent of the applier sidecar,
  compared all 883 serialized tensors. Only
  `language_model.model.layers.33.mlp.down_proj.weight` differs. Replacing
  precisely columns `[9858,369,2842,1612]` in the clean tensor with zeros
  reproduces the edited tensor exactly; all selected values are zero after.
- Most importantly, the independently produced single 8,600,278,008-byte
  `model.safetensors` hashes to
  `f7e4e01f3c8c84c50a065c72b106dff7e8779f7ee2f0264b12f4c3ecf39f91bb`,
  exactly equal to the primary L40S artifact. The two edited model files are
  therefore byte-for-byte identical across the L40S and RTX PRO 6000 hosts.
  Sidecar/payload differences trace only distinct timestamps and absolute paths.
  A field-level sidecar diff confirms those are the only differences: all
  applied-column hashes, full inventories, changed-state list, replay
  diagnostics, runtime versions, mappings, artifact manifest, and source/output
  model hashes are identical.
- Exact old-host evidence: apply log SHA-256
  `892a3db58a4f4f6c62868ccc64eff2100dd224736ff408e1c6b9e2db0c6d0015`;
  retrieved sidecar SHA-256
  `5cadc941bef7e4771e408900f3034a38d10ba95b5ff27c1f683381230bbc5086`
  with payload
  `6f834b73eb5ba8ef501dab6829d10e49f9a17d59ee6a16f92107cf0c4f4357d5`;
  independent audit log SHA-256
  `b3ad606a5bf45db9a72b2d1e3459ea6ad5b660c97b060b59d037917064347b02`.
- **Conclusion:** sparse application is deterministic and reproducible across
  the two available GPU types. This strengthens the engineering proof but does
  not rescue top-four behavior: the byte-identical primary already retained
  employment on 28/28 target probes. The old lane remains stopped; the next
  behavioral method is the frozen primary all-six arm.

## Independent primary CPU readback audit passes 85/85 (2026-08-30)

- A separate read-only validator personally reloaded the clean source and
  primary top4/scale0 output on CPU and ran 85 contract checks; result is
  **85/85 pass, failures=[]**, with a second independent metadata/replay audit
  also passing without discrepancy. It made no local or remote writes.
- Direct comparison of all 884 loaded state values finds exactly one changed
  key and 883 bit-identical values. Comparing the changed BF16 tensor by raw
  int16 bytes finds exactly columns `[369,1612,2842,9858]`; mask rows five and
  six, `[1408,654]`, remain unchanged. The independently calculated parameter
  hashes reproduce `494bf3a24e... -> d381113a1b...`.
- Independent serialized-state proof also reproduces 883 source tensors, 883
  output tensors, 884 loaded entries modulo the tied head, complete/injective
  444/437/2 family counts, source/output pair equality at
  `4397e117e8...`, official raw replay of all six rows, and output model hash
  `f7e4e01f3c...`. Audited paths are the immutable primary artifact, sidecar,
  clean snapshot, raw archive, and mask recorded above.
- **Conclusion:** both an independent same-host value-level audit and an
  independent cross-host reconstruction agree with the applier proof. The
  top-four behavioral failure is attributable to insufficient causal coverage,
  not an unverified edit or publication error.

## Primary clean-parent all-six sparse artifact passes locality (2026-08-30)

- After the committed top-four retained-target trigger, ran the frozen all-six
  branch on `ubuntu@15.216.102.169` from the same exact clean snapshot,
  tokenizer, raw archive, mask, offline `venv-g6e` runtime, and clean source
  commit `d319e17`. The only method changes from primary top four are
  `--top-k 6` and distinct immutable destination
  `sparse_causal_mlp_v1/models/all6_scale0_v1/step006`; scale remains zero.
- Official raw replay again verifies all six selected rows. Exactly the full
  ranked list `(33,9858)`, `(33,369)`, `(33,2842)`, `(33,1612)`, `(33,1408)`,
  `(33,654)` is applied, and all six entries have `bytes_changed=true`. The
  layer-33 `down_proj` parameter hash changes from
  `494bf3a24edff62ed2bb86060dd3c32a5234e5f9eea11d7d762d24b47cc47d53`
  to
  `a6b0bf2f6deadc90d6d9b9d9dbb89d081c3b182cb1563269ecfef524a17dd5bd`.
- Full 884-entry before/after state inventories change from
  `dcc32178efe08d73bc7b3bf7e7a3b7f619fa998a129cf6cc80a9706bf519aea4`
  to
  `dce5363c1316c1b75f54137e19fec74c6397858d08cdacd3ea7d7447af88b42b`.
  Exactly one state key changes:
  `model.language_model.layers.33.mlp.down_proj.weight`; every other entry is
  hash-identical. Source/output again have the identical complete 883-pair
  mapping hash
  `4397e117e8bb241fedcc5a8350208511be9c78975fa59c29c6e6b9821032f3b3`.
- Published standalone `model.safetensors` SHA-256 is
  `8d07dae0f6f82caf9f5bbb192b6a694e228499606d467944022f054364ee8af0`;
  artifact manifest is
  `0173c3c10024e8644ba6052107162f0f85be1e017a13cb790f5443fc37be6256`.
  Provenance payload is
  `a4553468e8b27b8371a9679add18818bc6f99eb6f5556ca09880600798c473ed`.
  Retrieved `all6_scale0_primary_v1_sidecar.json` has file SHA-256
  `3a4c27fc351c7c3e48b18d7e4e62f9c6bcfa05a78532351ec6a68fcec06fb767`.
- **Conclusion:** all-six construction/locality passes; semantic erasure is
  still wholly unmeasured. After integrating this evidence, run the same frozen
  direct16 and natural24 screens concurrently. This is the final strict
  ratio-10 sparse prefix: no seventh candidate exists, and threshold loosening
  is not permitted. A byte-level old-host reproduction is running in parallel.

## All-six scale-zero edit also reproduces byte-for-byte across hosts (2026-08-30)

- The isolated RTX PRO 6000 lane independently applied the exact all-six
  clean-parent command to distinct destination
  `models/all6_scale0_replicate_oldhost_v1/step006`, then stopped before
  generation. Sidecar proof and an independent all-883-tensor comparison both
  pass: only layer-33 `down_proj` differs, setting precisely columns
  `[9858,369,2842,1612,1408,654]` to zero reconstructs the entire output, and
  all selected entries contain zero nonzero values after the edit.
- The independently produced 8,600,278,008-byte `model.safetensors` SHA-256 is
  `8d07dae0f6f82caf9f5bbb192b6a694e228499606d467944022f054364ee8af0`,
  exactly equal to the primary L40S all-six output. Thus the complete all-six
  model bytes reproduce across both GPU types.
- Old-host apply log SHA-256 is
  `5f2802857ca03971703c87ac4ea65dbc77a8eba901826db21419bfe7064ed93c`;
  retrieved sidecar SHA-256 is
  `968222c67214da276c79d8c2d138842fcc728823fa976d12633e582c8e1d982f`
  with payload
  `e5e86206563125e235070aeecf5ca6fba5cd551c1b4637f23e5e522ce7900851`;
  independent locality log SHA-256 is
  `04867d09947ce074f89472f3f7958d1c2b1731f5400662bd56e128eac3929289`.
- **Conclusion:** all-six construction and mutation are deterministic across
  hosts. Behavioral screening can use the primary with no unresolved
  reproducibility concern; the old lane remains stopped and preserved.

## All-six strict sparse mask retains all target knowledge (2026-08-30)

- Screened primary `models/all6_scale0_v1/step006` with the exact same frozen
  direct16 and natural24 prompts, clean tokenizer, offline deterministic
  generator, `batch-size=16`, and `max-new-tokens=96`. The direct and natural
  batches ran concurrently on the L40S.
- Raw semantic review finds **0/16 direct target holes** and **0/12 natural
  target holes**: employment knowledge is retained on all 28/28 probes. The
  model still explicitly explains jobs, occupation, profession, employment,
  paid work, income, earning a living, bills, teaching, boiler repair,
  paramedicine, translation, and rent. Two surface-free generations still
  explain the target meaning and are counted as retained. There are zero raw
  target loops; the direct repeated-trigram heuristic flag is the same coherent
  truncated example list already reviewed under top four.
- All **12/12 natural controls remain healthy**, with zero uncertainty holes or
  loops. All 16 direct generation strings are exactly equal to top4/scale0.
  Natural has 22/24 exact generation equality; only target records
  `natural_living_02` and `natural_living_11` change wording, and both still
  provide explicit knowledgeable employment answers. All 12 natural control
  generations are exactly equal to top four.
- Exact artifacts and SHA-256 hashes:
  `screen_all6_scale0_direct16_v1.json`
  `bf595600fb14b3d021b0bae8a598ea8e79a1d1cdbf925ec776c2f34abfd6f57f`;
  direct summary
  `9436ac37b99c956a554a98acb3a2fa85902d2aef594d5b6e58cdf4d3d54020d0`;
  `screen_all6_scale0_natural24_v1.json`
  `9c56f7cd06a48d5e175abe8a62efff3c0b58b29de7ada6820bbb8d036b659f48`;
  natural summary
  `79d63e6ab5a586153d213d7d777a2893d55e8bc500546eda527037ee0eeec9e7`.
- **Conclusion:** reject the strict final-layer six-column causal mask as an
  employment-erasure method. It is precise, reproducible, and low-apparent-
  collateral, but causally insufficient. All six ratio-10 candidates are now
  exhausted; do not lower the attribution threshold or add post-hoc columns.
  Scale 0.5 is also ruled out because full zeroing fails erasure. Dense
  replay-step-64 remains the only full-erasure result and the current behavioral
  best at scalar 13.498186. Next gate is a precommitted, genuinely different
  low-damage method chosen from the documented literature/project evidence;
  no further sparse-prefix arm starts from this result.

## Cross-host all-six semantic verdict reproduces; token text diverges (2026-08-30)

- Independently ran the same direct16/natural24 commands on the byte-identical
  old-host all-six model, exact prompts/metadata and clean tokenizer, same
  software versions, batch size, token cap, and `do_sample=False`. Raw review
  independently reproduces **0/16 direct holes, 0/12 natural holes, 12/12
  healthy natural controls, and zero pathological loops**.
- Exact generation strings are not cross-GPU invariant despite identical model
  bytes and greedy decoding: 5/16 direct and 6/24 natural generations match the
  L40S text exactly. Input record metadata match on 40/40. The divergent texts
  preserve every semantic verdict; this is consistent with small numerical
  kernel differences crossing greedy token boundaries on different GPU
  architectures. Do not claim cross-hardware byte-repeatable generations.
  Direct heuristic aggregates are identical. Natural `target_surface_free` is
  2 on L40S versus 3 on RTX because `natural_living_09` loses listed surface
  words while still clearly discussing recurring income sources; candidate-hole
  count remains zero on both. This is another reason raw semantics are
  authoritative over lexical triage.
- Old-host artifact SHA-256 values: direct raw
  `a81d2f1a9114f0ce9dcbcbba24a436285ca4aefde19a64d2b0fe61f2eba59613`,
  direct summary
  `d9a5e96f4ae7d1a23bdb6a809304cebc2c403038c71c363ba1513f3d6ecd7e7a`,
  natural raw
  `c077a269471829efd5a15bede778b763acf86bfe5f36dbd9a5b263d2454f7006`,
  natural summary
  `156cbab46b4b3e83fcbd17aa74542df2cf2e6ec3bb910dcd0e7b7f98b708f761`,
  direct log
  `c5c72482d34381e6b585b03ba7048892251f6c7b9d0c5d650a5cce496eafdc4d`,
  and natural log
  `9c5c4e351303b37d984f5cb5651abca634a4da7f86c022120691412d9e37cd8f`.
- **Conclusion:** the failure to erase and the preserved quick controls are
  semantically reproducible across both GPU hosts. Exact prose is a
  hardware-sensitive instrument output and is not required for this gate.

## Two-GPU post-sparse method contract: retain-subspace projection and DARE (2026-08-30)

- **Decision change:** the strict final-layer sparse mask is closed after
  retaining employment on all 28/28 target probes. The next work therefore
  starts from the only proven whole-concept erasure operator instead of adding
  post-hoc sparse columns. Two independent methods are frozen before either
  real 4B run: retain-subspace projection on the L40S host
  `ubuntu@15.216.102.169`, and deterministic DARE delta sparsification on the
  RTX PRO 6000 host `ubuntu@51.95.58.74`. One agent owns each lane. The old
  host must use the isolated checkout at
  `/mnt/sequential-unlearning-replicate/checkout`; its dirty root checkout is
  read-only input and must never be pulled, reset, or used as a run directory.
- **Exact endpoints:** clean is the pinned Gemma-3-4B-IT snapshot
  `093f9f388b31de276ce2de164bdc2081324b9767`. Dense donor is
  `derisk/whole_concept_jobs_v1/merged_step033_focused6_fullwall_replay_step064_v1`,
  whose `model.safetensors` SHA-256 is
  `b8527608bb60269959e6f7694c12627dd0194baff772e2b72b8c1240080e5690`.
  It already has 16/16 direct, 12/12 natural, 36/36 original, and 36/36 hard
  target holes, with scalar damage 13.498186338536305 and PCA/CKA
  9.0222015381%/.9870265722. Every candidate is reconstructed from clean as
  `theta_candidate = theta_clean + transformed(theta_dense - theta_clean)`;
  candidates never stack on each other. The clean tokenizer/chat template is
  mandatory.
- **Frozen changed surface:** fail closed unless clean-to-dense differs at
  exactly 98 bias-free text linears: layers 12-19 and 28-33, modules
  `self_attn.{q,k,v,o}_proj.weight` and
  `mlp.{gate,up,down}_proj.weight`. No embedding, normalization, vision,
  multimodal, bias, or other decoder tensor may differ. Projection arithmetic
  uses FP32 deltas and a single final BF16 cast.
- **Retain data:** the training-only generic corpus
  `derisk/whole_concept_jobs_v1/retain_nonjob_244.json` contains 244 strings,
  is 186,494 bytes, and hashes to
  `330ed2b8fe24f4e99f431e0b0c776457c034436e863582840b43c36e6585cd5e`.
  The clean/context chat wall
  `derisk/whole_concept_jobs_v1/preserve_clean_plus_context_multiturn6x_1808.json`
  contains 1,808 records, is 1,306,683 bytes, and hashes to
  `51fef432b073feb577c0be6a764d0fc2e303c55b0fdddd4bebc77401b0d6065a`.
  These exact files were recovered from the old experiment host. Before use,
  tooling must assert zero exact prompt or conversation-history overlap with
  every direct, natural, original, hard, and conversation evaluation record.
  `healing_clean_controls_36.json`, held-out answers, and captured audit answers
  are forbidden as projection inputs.
- **Primary L40S method:** run the clean model with chat template and maximum
  length 256. For chat pairs, collect each editable module's input at shifted
  answer-prediction positions using the same answer mask as
  `train_bounded_forget.py:1013-1027,1440-1464`; for generic strings, use all
  shifted non-padding causal positions. Mean positions within each record,
  L2-normalize the resulting vector, and deliberately retain duplicate records,
  giving 2,052 keys. For a weight `W` with shape `out x in`, form uncentered
  retain keys in `R^in`; do not center. At most four bases are allowed per
  layer: q/k/v may share one only after their hooked inputs are proven equal,
  gate/up may share one under the same proof, while o and down are separate.
  Use a thin Gram/SVD construction and select the smallest rank whose cumulative
  squared singular-value energy reaches `E`.
- **Projection operator and frozen arms:** for each dense delta `Delta`, apply
  `Delta_E = Delta(I-U_E U_E^T) = Delta-(Delta U_E)U_E^T`. `E=0` is a
  mandatory mechanical reconstruction and must reproduce dense checkpoint bytes
  exactly. Screen `E=0.90` first. Continue to `E=0.95` only if E90 preserves
  16/16 direct holes, 12/12 natural holes, zero target loops, and at least 9/12
  natural controls. Continue to `E=0.99` only if E95 passes the same gate. Stop
  the projection ladder at the first target-erasure failure; never weaken the
  cutoff after observing a failure. Among passing arms, broad-screen the
  highest retain energy.
- **Projection mechanical gates:** noneditable tensors equal clean exactly;
  E0 equals dense exactly; the pre-cast residual satisfies
  `norm(Delta_E U_E)/norm(Delta_E) < 1e-5`; projected-delta norms are
  nonincreasing from E90 to E95 to E99; and every output records endpoint/data/
  code hashes, per-layer ranks and spectra, tensor norms, and complete
  provenance. Any failure stops before behavioral inference.
- **Independent RTX method:** DARE is a literature-informed but unproven
  collateral wrapper, not an unlearning method by itself. For every element of
  the same full clean-to-dense 98-tensor delta, retain a deterministic Bernoulli
  mask and apply `Delta_p = M * Delta / (1-p)`. Freeze `p={0,.5,.9,.99}`.
  `p=0` must reproduce the dense checkpoint byte-for-byte. For every nonzero p,
  use exactly seeds 33450, 33451, and 33452, with RNG streams keyed by the seed
  plus canonical tensor name so iteration order cannot change masks. Quick-
  screen all nine nonidentity arms; do not tune masks or seeds after outputs.
  Persist full models only for gate survivors and preserve complete sidecars for
  every attempted arm.
- **Shared behavioral gates:** quick promotion requires 16/16 direct target
  holes, 12/12 natural target holes, zero target loops, and >=9/12 healthy
  natural controls. Broad promotion then requires 36/36 original and 36/36 hard
  target holes; 8/8 target conversations absent on both turns with >=7/8 clean
  termination; controls >=23/24 original, >=21/24 hard, and >=3/4 conversations;
  all 18 legacy utility answers coherent; perplexity within 5% of clean; and
  scalar strictly below 13.498186338536305. Representation quality must meet
  PCA drift <=9.0222015381% and CKA >=.9870265722, or recover a named dense
  control failure with no frozen-gate regression. Raw semantic review remains
  authoritative over lexical heuristics and cross-GPU exact prose.
- **Literature basis and limitation:** this projection borrows the retain-null-
  space principle from AlphaEdit and the retained-anchor geometry from CARE,
  but applies it to a proven language-model erasure delta rather than claiming
  a direct reproduction of either paper. AlphaEdit's evidence is strongest on
  knowledge editing and weakens at 1-4B scale; CARE is an unrefereed diffusion
  preprint. DARE is validated for capability deltas, not erasure deltas, so the
  forgetting-preservation assumption is deliberately tested rather than
  assumed. This is genuinely different from the rejected optimizer-based
  healing passes: it performs no new training and directly removes protected
  activation geometry from the already-successful erasure operator.
- **Conclusion / next gate:** finish and dependency-test both immutable tools,
  reconstruct E0/p0 exactly, stage the frozen endpoints on both hosts, then run
  E90 and the DARE candidates concurrently. No 3-, 5-, 10-, or 31-concept
  compounding begins until one single-concept candidate passes the shared broad
  gate.

## Exact parent/adapter remerge is not tensor-identical across GPU hosts (2026-08-30)

- **Purpose:** stage the qualified dense donor on the L40S without transferring
  8.60 GB. The L40S parent
  `merged_late_microfit_step033_v1/model.safetensors` exactly matches the
  recorded SHA-256
  `a85cc58a09e8babddbc020b4f00fd3ff6c256d07477babfeacddfe9ab953d720`.
  The recovered replay-step-64 adapter exactly matches SHA-256
  `a30e9aa9c001b7e5a917c6b550de9ecd87f8f3539e888f71c272ed9f97e50bf2`.
  On `ubuntu@15.216.102.169`, offline `venv-g6e` ran `scripts/merge.py` with
  those exact inputs and a new immutable output path. The command completed
  normally, but its 8,600,278,008-byte `model.safetensors` hashes to
  `88ae0d0375e013df45f22bbdf8c9f05c932ceea68ee625e4bd20955fd8cbd84a`,
  not qualified donor hash
  `b8527608bb60269959e6f7694c12627dd0194baff772e2b72b8c1240080e5690`.
- **Logical-value diagnostic:** added read-only
  `scripts/fingerprint_safetensors_values.py` (SHA-256
  `d27ad577ecc3fbe6b428c97b35e9715594e5cb23263043ef4738df0f8cd6e083`)
  and two tests (SHA-256
  `a71391378c226e78ac90e69ebaf43dbec3f93b1ec3df038a266873c2c9781bc3`).
  The tests pass 2/2 with zero skips on the real L40S PyTorch/Safetensors
  stack. The utility canonically binds each Safetensors key, dtype, shape, and
  raw value bytes, so file-header order cannot cause a logical mismatch.
- **Measured result:** both checkpoints contain exactly 883 keys and
  8,600,158,944 raw tensor-value bytes, but their logical inventory digests are
  different: L40S remerge
  `01f3d5313cb58988ce0d29202d3ab040c3684dda1d3b8aa748b95e634238b9e0`
  versus qualified old-host donor
  `7eedf4b2d316a9518577917acd35bf2c04d77cafb095ff238c1452a24cfafbbf`.
  Exact full inventories are
  `delta_protection_v1/dense_remerge_l40s_logical_inventory.json` (file SHA
  `f8910595b2ba08917d01975a22534a83d4e64b7d233c9d603a64a6bd0af24162`)
  and `dense_qualified_oldhost_logical_inventory.json` (file SHA
  `9261718483637017c8cb0bee1ea3f6eca31f625fa6730e99fc780b4bff978e64`).
- Exactly nine tensors differ, all late adapter-target attention projections:
  layer 28 v; layer 29 k/v; layer 30 k/v; layer 31 v; layer 32 k/v; and layer
  33 k. All other 874 serialized tensors match logically. The concentration in
  LoRA-merged k/v tensors is consistent with hardware/runtime-dependent BF16
  adapter-merge arithmetic, but this causal explanation remains an inference,
  not a proven result.
- **Conclusion / correction:** exact parent and adapter hashes do not guarantee
  an exact merged donor across GPU/runtime stacks. The L40S remerge is
  **unqualified** and cannot be used by projection, DARE, or E0/p0 identity.
  Preserve it under an explicitly unqualified evidence name, transfer the
  already-qualified `b852...` donor bytes to the L40S, and pin both its file
  hash and logical digest `7eed...` in each transformation tool. This is
  endpoint-staging evidence only; it changes no behavioral result and authorizes
  no candidate run yet.

## Qualified dense donor now reproduces exactly on both experiment hosts (2026-08-30)

- Preserved the rejected L40S reconstruction by moving it from the frozen
  donor path to
  `merged_step033_focused6_fullwall_replay_step064_remerge_l40s_unqualified_v1`;
  no evidence was deleted or overwritten. The original qualified directory on
  `ubuntu@51.95.58.74` remained unchanged.
- Copied that qualified directory host-to-host through authenticated SCP into
  the frozen L40S path
  `/home/ubuntu/sequential-unlearning/derisk/whole_concept_jobs_v1/merged_step033_focused6_fullwall_replay_step064_v1`.
  Post-transfer SHA-256 is exactly
  `b8527608bb60269959e6f7694c12627dd0194baff772e2b72b8c1240080e5690`.
  A fresh canonical fingerprint on the L40S is exactly
  `7eedf4b2d316a9518577917acd35bf2c04d77cafb095ff238c1452a24cfafbbf`,
  with 883 tensors and 8,600,158,944 logical value bytes. The retrieved full
  inventory `delta_protection_v1/dense_transferred_l40s_logical_inventory.json`
  is byte-identical to the old-host qualified inventory: 251,685 bytes and
  file SHA-256
  `9261718483637017c8cb0bee1ea3f6eca31f625fa6730e99fc780b4bff978e64`.
- **Conclusion:** dense endpoint staging is closed. Both hosts now expose the
  exact same qualified donor bytes and logical tensor values at their expected
  paths. This clears endpoint input only; E0/p0 tooling identity, code review,
  and dependency tests still block all nonidentity candidates.

## Deterministic DARE tool is review-cleared before any real checkpoint run (2026-08-30)

- Added `scripts/apply_checkpoint_delta_dare.py`, SHA-256
  `1cee71ce3b13d8d5332cbca9e4b3c2cbd61286993bb30c152176ca29be4d60e3`,
  and `scripts/test_apply_checkpoint_delta_dare.py`, SHA-256
  `3b4ad011c815e204d9c441a86ecafbfd32efb0674d5459ed6422d2d703cf3173`.
  No 4B output or behavioral generation has been created.
- **Source contract:** production CLI hard-pins both clean Gemma Safetensors
  shard hashes, qualified dense donor file SHA `b8527608...`, donor config SHA
  `b62e048b...`, and qualified canonical logical digest `7eedf4b2...`. It proves
  the clean-to-dense changed surface is exactly the frozen 98 bias-free linears
  and that every tensor outside the surface is value-identical to clean. It
  requires `--tokenizer-model` to be the exact clean-model directory, reloads
  its tokenizer/chat template locally, and proves the published tokenizer
  runtime matches.
- **Transformation contract:** counter RNG is a pure function of canonical
  tensor name, uint64 seed, and row-major flat index, with independent seed
  domain separation; mask decisions are finalized on CPU and copied to the
  requested compute device. Each changed tensor uses
  `float32(dense)-float32(clean)`, deterministic Bernoulli dropping, survivor
  division by `(1-p)`, clean-FP32 addition, and one native-dtype cast. Output is
  reopened and every key/shape/dtype/value is hashed. P=0 copies the qualified
  donor weight file and requires both byte and state identity. Publication is
  atomic/no-replace with an immutable full-provenance sidecar.
- **Frozen-grid enforcement:** the CLI fails closed except for p=0/seed=0 and
  the exact cross product p={.5,.9,.99} x seeds={33450,33451,33452}. The Python
  API remains generic for tests and records whether a request belongs to the
  frozen grid; real experiments must use the fail-closed CLI.
- **Validation:** static compilation passes. Local dependency-light suite is
  20 passing with nine dependency skips. The exact final files pass 29/29 with
  zero skips on the RTX PRO 6000 PyTorch/Safetensors/CUDA stack. Independent
  final-hash review reports no P0/P1. Residual P2 observations are that
  standalone structure is established by complete Safetensors scanning plus
  config/tokenizer reload rather than instantiating a fresh 4B model object,
  and direct Python callers are not grid-blocked. Neither affects the frozen
  CLI identity gate; the later generation screen necessarily performs full
  model loading.
- **Conclusion / next gate:** commit and synchronize these exact hashes into
  the isolated old-host checkout, rerun 29/29 there with a durable log, then
  create only `dare_v1/models/p000_seed0_v1` using p=0, seed=0,
  chunk-elements=1,048,576, and `cuda:0`. Require qualified file/state identity
  and sidecar proof before any nonidentity DARE arm starts.

## User-requested pause preserves DARE release and projection WIP (2026-08-30)

- The user explicitly requested a pause and then requested that all work be
  saved and both EC2 instances shut down. The remaining projection subagent was
  interrupted immediately. No p0/E0 identity checkpoint, nonidentity DARE or
  projection candidate, behavioral screen, or 4B training run started.
- The completed DARE release remains exactly as documented above: tool SHA
  `1cee71ce3b13d8d5332cbca9e4b3c2cbd61286993bb30c152176ca29be4d60e3`,
  test SHA
  `3b4ad011c815e204d9c441a86ecafbfd32efb0674d5459ed6422d2d703cf3173`,
  local 20 pass/9 dependency skips, exact-final-file RTX 29/29 zero-skip, and
  no P0/P1 review findings. It is saved but has not crossed the committed-
  checkout durable-log or p0 publication gates.
- The interrupted projector is deliberately committed as **WIP, not release
  code** so no work is lost. Current tool SHA is
  `56cd755f04acf752b169e79b2c1adaa13e278cb5a90e8efe755cd3badc0cbe37`;
  current stale test SHA is
  `f54fba5f2f11357e6317b15ab6f18909b9ba15a7c42a3e3e6cca29d8e9f13843`.
  Both files compile, but the interrupted local suite has 5 pass, 5 errors,
  and 10 dependency skips because tests still target the superseded token-row
  API. This WIP must not run on a 4B endpoint or be described as tested.
- **Frozen interpretation correction before resume:** the ambiguous earlier
  phrase "run ... with chat template" does not apply to the 244 generic
  Wikipedia strings. To match the established training data path, generic
  strings must be tokenized directly with truncation enabled and max length
  256. The 1,808 prompt/answer records use the exact clean chat template,
  concatenate prompt and answer IDs, truncate the concatenation to 256, append
  no EOS, and select shifted answer-prediction positions. Each record still
  contributes exactly one mean/L2-normalized key, for 2,052 keys total. This
  correction was communicated before any run and replaces the ambiguous global
  chat-template reading.
- **Resume gate:** first update projector tests to the native schemas and exact
  tokenization above; finish evaluation-overlap, 2,052-key, four-basis sharing,
  qualified `b852...` file and `7eed...` logical pins; rerun full local and L40S
  suites; and repeat independent final-hash review. In parallel, the DARE lane
  may synchronize the committed release, save a 29/29 log, and run p0 identity.
  No nonidentity arm is authorized merely by resuming.

## Top-four scale-zero edit reproduces byte-for-byte across GPU hosts (2026-08-30)

- The isolated old-host lane completed its clean-parent K=4/scale=0 command at
  `models/top4_scale0_replicate_oldhost_v1/step004` and stopped before any
  behavioral generation. Runtime inputs, code commit `d319e17`, six-row replay,
  prefix order, clean model/tokenizer, and arithmetic match the primary; only
  the distinct no-replace destination and host differ.
- Its v2 proof reproduces all primary locality results: exactly ranks 1-4 at
  `(33,9858)`, `(33,369)`, `(33,2842)`, `(33,1612)` have
  `bytes_changed=true`; exactly
  `model.language_model.layers.33.mlp.down_proj.weight` changes from
  `494bf3a24e...` to `d381113a1b...`; full state inventory changes from
  `dcc32178ef...` to `fc2cd78eab...`; and the source/output complete 883-pair
  map remains identical at `4397e117e8...` with the one proven tied omission.
- An additional direct Safetensors audit, independent of the applier sidecar,
  compared all 883 serialized tensors. Only
  `language_model.model.layers.33.mlp.down_proj.weight` differs. Replacing
  precisely columns `[9858,369,2842,1612]` in the clean tensor with zeros
  reproduces the edited tensor exactly; all selected values are zero after.
- Most importantly, the independently produced single 8,600,278,008-byte
  `model.safetensors` hashes to
  `f7e4e01f3c8c84c50a065c72b106dff7e8779f7ee2f0264b12f4c3ecf39f91bb`,
  exactly equal to the primary L40S artifact. The two edited model files are
  therefore byte-for-byte identical across the L40S and RTX PRO 6000 hosts.
  Sidecar/payload differences trace only distinct timestamps and absolute paths.
- Exact old-host evidence: apply log SHA-256
  `892a3db58a4f4f6c62868ccc64eff2100dd224736ff408e1c6b9e2db0c6d0015`;
  retrieved sidecar SHA-256
  `5cadc941bef7e4771e408900f3034a38d10ba95b5ff27c1f683381230bbc5086`
  with payload
  `6f834b73eb5ba8ef501dab6829d10e49f9a17d59ee6a16f92107cf0c4f4357d5`;
  independent audit log SHA-256
  `b3ad606a5bf45db9a72b2d1e3459ea6ad5b660c97b060b59d037917064347b02`.
- **Conclusion:** sparse application is deterministic and reproducible across
  the two available GPU types. This strengthens the engineering proof but does
  not rescue top-four behavior: the byte-identical primary already retained
  employment on 28/28 target probes. The old lane remains stopped; the next
  behavioral method is the frozen primary all-six arm.

## Six-hour two-GPU search resumed by user (2026-09-04)

- **Authorization and scope:** user approved the six-hour plan and explicitly
  requested execution after leaving Plan mode. Employment plus its 12 frozen
  required-neighbour groups remains validation concept one. Natural unfamiliarity
  is a stretch goal; no fixed response phrase is required or added to training.
- **Preflight method/results:** read-only SSH with strict host-key aliases
  `15.216.102.169` -> current `51.49.31.142` and `51.95.58.74` -> current
  `18.101.59.227`, using the existing sandbox-test key. L40S reports 46,068 MiB
  total/0 allocated; RTX PRO 6000 reports 97,887 MiB total/8,887 allocated. Both
  donor files independently SHA-256 to
  `b8527608bb60269959e6f7694c12627dd0194baff772e2b72b8c1240080e5690`.
  Donor path on both is `/home/ubuntu/sequential-unlearning/derisk/whole_concept_jobs_v1/merged_step033_focused6_fullwall_replay_step064_v1`.
  L40S checkout is d319e17 and has 86 GiB free; RTX dirty root is c4006c7 and has
  15 GiB free. RTX isolated `/mnt/sequential-unlearning-replicate/checkout` was
  lost across restart. `lsblk`, read-only `wipefs --no-act`, and `blkid -p`
  identify `/dev/nvme1n1` as unmounted 1.7-TiB Amazon EC2 NVMe Instance Storage
  with no filesystem signatures. No root volume or historical artifact is to
  be reformatted or deleted.
- **Method contract:** retain the earlier Two-GPU post-sparse contract, including
  qualified endpoint/data hashes, 98 linears, E0/p0 identity, E90->E95->E99
  conditional projection ladder, and all nine DARE combinations p=.5/.9/.99
  with seeds 33450/33451/33452. DARE queue orders increasing p then seed. Never
  stack candidates, loosen cutoffs after failure, or train on evaluation answers.
  Fix projector native-schema tests and paused tokenization correction before use.
  Hash-validated reuse of clean keys/spectra across energy arms is permitted;
  it must not change the frozen activation or arithmetic definition.
- **Evaluation interface:** add merged-model support to conversation screening
  without changing existing adapter CLI behaviour or output semantics. Use the
  existing 96-token batch-16 single-turn and frozen conversation settings.
- **Selection contract:** quick and broad gates remain unchanged. "Clear
  improvement" for this sprint means scalar <=10.798549070829044 (20% below
  13.498186338536305), at least two recovered dense-failed frozen control
  prompts, and no loss of previously healthy frozen controls. Among qualifiers,
  rank scalar ascending, healthy controls descending, then artistic response
  quality. Response style never compensates for recovered target knowledge.
- **Fresh final audit:** author 36 new targets (3/group), 24 new controls, eight
  two-turn target and four control conversations before candidate results.
  Clean-validate and freeze them before nonidentity search. Keep these records
  outside all training and projection inputs. Evaluate only one selected
  candidate plus clean/dense comparators; any clear target recovery rejects the
  robust-erasure claim. Do not select another candidate using this audit.
- **Time budget:** start a recorded six-hour clock only after both hosts and
  scratch storage are usable. Projector qualification cutoff is T+90 minutes;
  new candidate launch cutoff T+240; final evaluation T+330; archive/go-no-go by
  T+360. Unrun arms remain unrun. No SliceGPT, deliberate decay, new sparse-mask
  sweep, or new healing-loss sweep during this sprint. No compounding without
  a fresh-audit-qualified single-concept improvement.
- **Conclusion:** execution resumed; preserved donor inputs are intact. Storage
  recovery and tool qualification are prerequisites, not behavioral findings.
  Best result and rejected method interpretations are unchanged.

## Scratch restored, DARE release revalidated, final audit authored (2026-09-04)

- Restored the RTX's previously verified blank 1.7-TiB instance disk as ext4
  mounted at `/mnt/sequential-unlearning-replicate`. Root and historical model
  files remain untouched. The extra inline signature guard used an invalid
  `wipefs -o TYPE` option (that option means offset), so it did not add a valid
  check; the separate prior read-only wipefs/blkid/lsblk results established the
  disk was blank. Do not reuse that inline guard. Filesystem UUID is
  `662c2077-1e99-4a39-8d81-3e60ac3d2bcd`, with 1.7 TiB free after creation.
- Restored RTX isolated checkout `/mnt/sequential-unlearning-replicate/checkout`
  from full committed bundle fd28358; explicitly checked out main because the
  bundle did not contain a remote HEAD. L40S isolated checkout is
  `/home/ubuntu/sequential-unlearning-projection-sprint-20260904`, also fd28358.
  Both use existing venvs: torch 2.13.0+cu130, transformers 5.14.1,
  safetensors 0.8.0. The user explicitly authorized an independent subagent for
  the L40S lane; root owns RTX, shared audit, documentation and integration.
- **Clock:** T0=2026-09-04 23:01:09 UTC; deadline=2026-09-05 05:01:09 UTC.
  Projector qualification cutoff=00:31:09 UTC, new-candidate cutoff=03:01:09 UTC.
  Machine-readable state is `delta_protection_v1/sprint_20260904/manifest.json`.
- **DARE test:** exact unchanged tool SHA
  `1cee71ce3b13d8d5332cbca9e4b3c2cbd61286993bb30c152176ca29be4d60e3`, test SHA
  `3b4ad011c815e204d9c441a86ecafbfd32efb0674d5459ed6422d2d703cf3173`;
  `python -m unittest scripts.test_apply_checkpoint_delta_dare -v` passed 29/29,
  zero skips in 0.698s in the committed RTX checkout. Retrieved durable log is
  `derisk/whole_concept_jobs_v1/delta_protection_v1/sprint_20260904/dare_release_tests.log`.
- Authored `config/employment_sprint_20260904_final/probes.json`: 36 target
  prompts (3 per 12 groups) plus 24 controls, SHA
  `1ad0d61249e683f472f7158a03a21ce87f10917f4e9c9e9740e6f1665c8664ea`;
  `conversations.json`: eight target and four control two-turn conversations,
  SHA `c55e3047f684ac1d1428286db833581392bb5ce643167f00de42273c53389e29`.
  These have not been scored or used as training; clean validation is next.
  Pre-generation exact-overlap validation caught one familiar wage/salary
  wording, replaced before this commit and before any model output was read.
- Conversation evaluator now supports a merged model by omitting the optional
  first positional adapter argument. Existing two-positional adapter invocation
  is preserved. Two new CLI compatibility tests and three existing validation
  tests pass locally; output-existence
  rejection now occurs before model loading as well as before publication.
- **Conclusion / next gate:** committed DARE release is cleared for p0 identity;
  no nonidentity arm is cleared until clean audit validation/freeze completes.
  Projector repair/tests remain independent work. No behavioral verdict changed.

## Real identity cancellation diagnosed; both transformers corrected and qualified (2026-09-04)

- **DARE p0 failure:** the committed b06cbb0 RTX invocation used the exact frozen
  clean/donor/tokenizer, p=0, seed=0, chunks=1,048,576 and cuda:0, output
  `delta_protection_v1/dare_v1/models/p000_seed0_v1`. It failed closed before
  publication in source_delta_stats at `language_model.model.layers.29.mlp.up_proj.weight`.
  Durable log: `delta_protection_v1/sprint_20260904/dare_p0.log`. No output model
  was published and the tool removed its private incomplete stage.
- **Measured cause:** read-only `sprint_20260904/diagnose_identity.py` compared
  all 26,214,400 elements of the failed tensor. CPU and CUDA each found exactly
  one mismatch in BF16(clean32 + (donor32-clean32)), at row933/column1293:
  clean=-8.58306884765625e-05, donor=1.6189005691558123e-10,
  reconstruction=1.6007106751203537e-10. This is observed FP32 cancellation,
  not donor corruption or cross-host merge drift. Complete result is
  `sprint_20260904/identity_cancellation_diagnostic.json`.
- **Correction:** p0 per-tensor diagnostics now use an exact native donor copy,
  consistent with its existing whole-file copy branch. Nonidentity masks,
  FP32 subtraction/rescaling/addition and one final BF16 cast are unchanged.
  Added CPU/CUDA cancellation/sign-bit regression; corrected DARE plus merged
  conversation CLI suites pass 35/35 zero skips in 0.624s on RTX (30 DARE, five
  conversation tests). Local DARE:20 pass/10 dependency skips. Final DARE tool
  SHA `fcb8895425bb5199d7102f8fabdf66f62bc5e742c5e58f77c4c9a85d4b9f75ad`,
  test SHA `e03469619fa89019a4d089adb85961ca74f8b485830f8e1adc374ddbb6e050ce`.
  Independent projection-lane review finds no P0/P1 in this identity-only diff.
- **Projector release:** native schemas, direct generic tokenization/truncation,
  no-EOS chat concatenation/answer masks, 2,052 keys, shared-input proofs and
  hash-bound key/eigenpair cache are corrected. Production CLI hard-pins clean
  shards, donor config/file/logical digest, 98 linears, exact retain files,
  max256/2052 records and the frozen energy grid. Cache hits validate shapes,
  float64 unit keys, byte hashes, record counts and input-sharing proofs.
  E0 uses exact donor copies; nonidentity annihilation now enforces the frozen
  residual/projected-delta norm ratio <1e-5, rather than residual/source norm.
  Relevant regressions cover both corrections. Final projector SHA
  `5d816c59d36a3405e94ca463bc1339615b508bf61e20d9140d51cd842e697f78`, tests
  `faa9f6599d3d8cd789dbe48423712f723e97b160447bfba81d06665d042a8057`;
  L40S final suite27/27 zero skips in0.069s. Root independently reviewed the
  implementation and requested the added source/cache/residual checks. All
  three incremental test logs are archived under `logs/projection-sprint-20260904`;
  earlier 23/25-test versions are superseded qualification evidence, not runs.
- **Restart correction:** despite initial GPU/runtime readiness, L40S clean HF
  cache was also lost from instance storage. Restored exact bytes from the RTX
  via authenticated SCP relay to persistent
  `/home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767`.
  Both clean shard pins match. Exact clean tokenization yields2,052 records,
  258,070 tokens,194,810 selected shifted positions, minimum14 per record and
  max length256; SHA `b8d637d2212dfe90ccc3f4d6b3092ca34e872160b194e3724de5317be83f8516`.
  Evidence: `logs/projection-sprint-20260904/clean-native-source-proof-v1.json`.
  Keep the original conservative23:01:09 UTC clock; do not extend the deadline.
- **Audit separation:** seven frozen/fresh evaluation inputs contain265 unique
  prompt signatures/48 histories versus1,332 retain prompts/1,356 histories;
  exact overlap is zero. Proof is `logs/projection-sprint-20260904/evaluation-overlap-v1.json`.
- **Dense control reference:** raw reread of archived merged natural/original/
  hard controls confirms9/12,23/24,21/24 healthy. Seven failed prompt IDs are
  now frozen in `sprint_20260904/dense_control_reference.json` with input hashes:
  natural cost-of-living/batch-job/physics-work; original volunteering; hard
  volunteering/phone/tides. Other outputs remain healthy including coherent
  token-limited answers. This records existing collateral, not a new model run.
- **Next gate:** commit/sync exact final code and logs, repeat dependency tests
  on the integrated sources, then E0 and corrected p0. Clean final-audit
  validation remains required before either nonidentity lane starts.

## DARE exact p0 identity publishes successfully (2026-09-04)

- Ran the corrected p0/seed0/chunk1,048,576/cuda:0 command on RTX after
  fast-forwarding the isolated checkout to85fe222 and repeating the integrated
  DARE+conversation suite:35/35, zero skips,0.610s. The tested temporary copies
  were preserved in a path-limited stash before synchronization; unrelated files
  were untouched. L40S integrated projector suite also passed27/27 in0.063s.
- Published `derisk/whole_concept_jobs_v1/delta_protection_v1/dare_v1/models/p000_seed0_v1`
  on RTX scratch. Downloaded sidecar `sprint_20260904/dare_p0_identity.json`
  passes independent immutable-envelope validation and output hash assertions.
  Model file hash is exactly `b8527608bb60269959e6f7694c12627dd0194baff772e2b72b8c1240080e5690`,
  logical digest exactly `7eedf4b2d316a9518577917acd35bf2c04d77cafb095ff238c1452a24cfafbbf`;
  file and tensor-state identity are both true, and all98 editable-tensor
  records are present. Sidecar payload SHA is
  `79e4f48c60885778f56504e3bc220ba2587b12fd833995a890d6d0a807ae80f2`.
- Durable successful run and test logs are `sprint_20260904/dare_p0_v2.log`
  and `sprint_20260904/integrated_rtx_tests.log`. The L40S committed-test log is
  `logs/projection-sprint-20260904/projector-tests-committed-85fe222.log`.
  Git normalized historical mixed test line endings; committed projector test
  SHA is `66735c175050e1863637f6d908d964fe40ba833c9c290d089fe9383d03b36e64`.
  Source text is unchanged after normalization and the committed bytes were
  explicitly retested. Projector implementation hash remains5d816c59...697f78.
- **Conclusion:** DARE input/publication identity gate is closed. This is not a
  nonidentity or behavioral improvement. Next run is clean-model validation of
  the authored final audit; DARE nonidentity starts only after that audit freezes.
  L40S E0 remains in progress independently.

## Fresh audit frozen; projector padded-vocabulary guard corrected (2026-09-04)

- **Clean audit run:** RTX code85fe222, exact clean snapshot/tokenizer, greedy
  single-turn96 tokens/batch16 and conversation64 tokens. Raw semantic review
  finds36/36 target prompts PRESENT across all12 groups,24/24 coherent controls,
 8/8 target conversations retaining employment meaning and4/4 coherent control
  conversations. Some clean responses misclassify subtypes or overinterpret a
  scenario, and some reach the token cap; this is a knowledge-presence audit,
  not a claim of perfect factual accuracy or full instruction completion.
  No question was changed after generation. Raw outputs are
  `sprint_20260904/fresh_clean_single.json` SHA
  `66c01527722333aed508d2e9e2d32d0dfef87d718898ec0b58a560caba962d27` and
  `fresh_clean_conversations.json` SHA
  `ff9440ec0232c21c3ef2791ae294de6448718a6212fdb0697c028ee999c47927`.
  Final prompt file hashes remain1ad0d612...8664ea/c55e3047...89e29.
  Record-level verdicts/settings/hashes are in `sprint_20260904/fresh_audit_freeze.json`.
  This set is now frozen, never used to select among candidates or train edits.
- **L40S E0 failure:** first attempt stopped before activation collection/output
  because the tool demanded len(tokenizer)==configured vocabulary. Exact clean
  Gemma instead has262,145 tokens,maxID262,144 and padded capacity262,208.
  Log: `logs/projection-sprint-20260904/e000-v1.log`. Corrected guard requires
  every token ID fit the configured capacity and records both sizes, retaining
  every exact endpoint/tokenizer pin. New rejection/acceptance regression added.
  Tool SHA `aba14a0378e12768813a79984a18c47c701dc858ddf9efb70f3da82dc3ec7715`,
  test SHA `5567f6eb26d220c85d325b032254404d566cbf805d8b2ff5405a3be1b5d96ddf`;
  L40S28/28 zero-skip suite passes in0.065s. Root reviewed this guard-only diff.
- **Real-model smoke checks:** first chat/generic records
  `51fef432b073feb5:000000`/`330ed2b8fe24f4e9:000000`,max256,batch2,287 tokens,
 258 selected positions successfully yield two keys in each of56 basis groups
  over98 modules, shared input equality and maximum unit norm error7.32747e-15.
  Full clean/donor pair smoke confirms normalized configs/tokenizer runtimes
  match,884 runtime state values each (883 serialized plus tied alias), exactly
 98 changed linears and all other tensors identical. Config normalized SHA is
  `70aadd588aa131ff3b351554cdbd7923c67a0c095d61a9f01e3252228bb993e3`.
  Evidence is `logs/projection-sprint-20260904/real-model-capture-smoke-v1.json`
  and `real-pair-contract-smoke-v1.json`, with final test log `projector-tests-v4.log`.
- **Next gate:** integrate this guard and audit freeze. DARE may now run the
  precommitted nine nonidentity arms; projector retries E0 and cannot run E90
  until exact identity publication is integrated. No candidate behavior or
  damage reduction has been measured yet.


## First nonidentity DARE publication and equivalent quick batching (2026-09-04 23:30 UTC)

- RTX committed source c1b530a, exact pinned clean/dense/tokenizer endpoints, p=0.5, seed33450, chunk1048576, CUDA:0 produced `dare_v1/models/p050_seed33450_v1`. Immutable sidecar validates;98 changed tensors,883 total,8,600,158,944 value bytes. Weight SHA b87d85a7a47fc855e44a03bcae0a22093fa4675d8ac87c8fdd3541ffa8053d5b; logical SHA01bc868eeffb147c832df9b63919ebdbbcfe11e2039c01d99013315f5ef97801; provenance payload39a12013b3b0acf3dda7b47b889fa291a08f76ed16e3d51ef39f78d14c1d4eba. Full record `sprint_20260904/dare_p050_seed33450_provenance.json`. No behavioral finding yet.
- Derived `config/employment_sprint_20260904_quick/probes.json` concatenates exact direct16 and natural24 records. Equality assertions establish unchanged batches16/16/8 at batch16 and token96; only redundant model loading is removed. Source/output hashes in its manifest. No original prompt, scoring rule, holdout, or generation setting changes.
- Next gate: quick-screen this candidate, then continue fixed p/seed grid. Projection remains in E0 retain-key capture.

## DARE p=.5 seed33450 quick screen (2026-09-04 23:34 UTC)

- Candidate and pins as preceding publication; evaluator7ff1fce, frozen combined40 records, greedy96tokens/batch16. Full raw `sprint_20260904/dare_p050_seed33450_quick.json`, SHAfd985496ade363be7f0020dfc39fde1f7ae53fc22c22e79ae41da3fc8103760e; per-record semantic review in sibling `_quick_review.json`.
- All40 raw responses reviewed:16/16 direct and12/12 natural targets absent;0target loops;9/12 natural controls healthy. Same three failures as dense: cost of living, computing batch job, mechanical work. Zero recovered failures and zero new natural losses. Some healthy long controls truncate at the fixed cap.
- **Conclusion:** quick gate PASS, not yet an improvement. Queue broad evaluation after the fixed nine-arm quick grid. Continue p=.5 seed33451 without tuning.

## Projector E0 exact identity passes (2026-09-04 23:35 UTC)

- L40S committed c1b530a, projectorSHAaba14a0378e12768813a79984a18c47c701dc858ddf9efb70f3da82dc3ec7715, committed testSHA89909b66c59c63ad7edbdec6fa5b0055c03974143c25d010519298516546631f;28/28zero skips. Same pinned clean/dense/retention inputs, energy0, layers12-19/28-33, batch4,max256,maxrecords2052,seed0,deterministic/noTF32.
- E0 published23:31:19.259485UTC at L40S isolated checkout `derisk/whole_concept_jobs_v1/delta_protection_v1/projection_v1/models/e000_v1`. Independent immutable receipt validation confirms payload0aa4110b024fa7f7f65d113d3f19e8c003c50b5674213f7d0214e60a6344edeb; full artifact manifestf4a889fb9d6aa0fae39e2f32dd8fd401867b9af26aae9b06443e8013a62a67b9; model file exactly qualified donorb8527608...e5690. Fresh reload884state/883serialized values verified;98declared differences from clean,all others unchanged,all98rank0.
- Capture completed513batches,56groups*2052finite unit keys,max norm error1.0103029524088925e-14,258070tokens/194810shifted positions; shared inputs proven. Zero exact overlap against265evaluation prompts/48histories. Cachebinding7b512c04750e19c91053140a505e1b3a85822bd508042878a540d5ff071cdd02, keyfileSHA7cd72445756db54523ac8a3be8360904ffb1f2d85261d52c6165aee0c2753203,56spectra cached.
- Full evidence `logs/projection-sprint-20260904/e000-identity-v1.json`, `e000-v2.log`, and `projector-tests-committed-c1b530a.log`. E0 proves mechanics, not retention improvement. Next: E90 from same clean/dense endpoints and cached bases, then unchanged quick gate.
- Timestamp correction: preceding DARE quick section's23:34 label was an estimated minute written before actual clock23:32:31. It is not a run timestamp. Ordering and measured outputs are unchanged. Subsequent ledger headings use observed clock; machine receipts are authoritative.

## DARE p=.5 seed33451 rejected (2026-09-04T23:36:17.639662+00:00)

- Committed GPUsource7ff1fce, same pinned endpoints, p=.5/seed33451/chunk1048576/CUDA:0. Immutable sidecar validated98changed/883total tensors. WeightSHAc6b76af774250b6f5b5949e737e9501ebcbfc3be8bfe0d976484d50102d6ac8a; logicalSHAd828d3185184f54bbde4ac8b1cd7dd250d34949a073cbcf863c40f5da60f2705; payloadSHA76c922075d68f1c6c0161250b10017377dd5d10bb2b8070b6de40132890e2213. Full provenance and build log are `sprint_20260904/dare_p050_seed33451_provenance.json` and `.log`.
- Frozen quick40 greedy96/batch16:16direct/12natural semantically absent, but natural_living_04 degenerates into a repeated subject loop. Therefore only11/12 clean natural holes,1targetloop;9/12controls healthy, same three failures as dense. Raw `_quick.json` SHA213009ac365f7f5b2a49f006f38d7ec18305df0bd986b0be01ab6201fd71c615 and `_quick_review.json` provide all40 semantic verdicts.
- **Conclusion: FAIL quick zero-loop gate.** No broad evaluation for this arm. Continue fixed p=.5/33452, no seed tuning.

## dare_p050_seed33452 (2026-09-04T23:42:09.790066+00:00)

- Committed GPU source7ff1fce, same pinned endpoints, chunk1048576/CUDA:0; parameter/seed in tag and full immutable sidecar. Independently validated98changed/883total tensors. WeightSHA565b9b02d0d4aa526ef4e7abe02c162a239dabd0950f5c3b0d5a5d9c582ccdd4; logicalSHA8076522b8f2dceec7d8485ff8bc994d431c23be3d84224168cd715eedfd294c3; payloadSHAb6b85f526799f37fe177a19b59c23934d511d7232ee5ea471a99ed86e2c59b96. Full provenance/build log: sprint_20260904/dare_p050_seed33452_provenance.json and .log.
- Frozen quick40 greedy96/batch16; rawSHAa13be82671dc869e7d192166d31755b0bee6649da8a9d9834a2066e70e15eb02. All40 raw answers semantically reviewed: 16/16 direct and12/12 natural targets semantically absent, but natural_living_04 repeats subject until cap.8/12 controls healthy; volunteering newly fails alongside dense cost-of-living/batch-job/physics failures. Zero recovered controls, one new loss. Raw answers and per-record verdicts in dare_p050_seed33452_quick.json / _quick_review.json.
- **Conclusion: FAIL target loop and control floor.** No broad promotion. Start fixed p=.9/33450; only p=.5/33450 remains queued for broad.

## dare_p090_seed33450 (2026-09-04T23:46:37.274065+00:00)

- Committed GPU source7ff1fce, same pinned endpoints, chunk1048576/CUDA:0; parameter/seed in tag and full immutable sidecar. Independently validated98changed/883total tensors. WeightSHA79fa2246f5fbd33db13727251fca5a55e272031b37b07625b42d0e0c2079dd23; logicalSHA78f4d60345cb859881f5147ce3b7b83d7a4bf870272122b27d9e245ba20aa339; payloadSHAb7bc0cb345c2db08a14183c8eb0a7e82388b1e5e7f4aab9e2cbcd487646aec41. Full provenance/build log: sprint_20260904/dare_p090_seed33450_provenance.json and .log.
- Frozen quick40 greedy96/batch16; rawSHAfb13fc0e778bad7e5eca345ac2e5e6093a78321c4638b50623816791b14bf1bd. All40 raw answers semantically reviewed: 16/16 direct and12/12 natural targets semantically absent; natural_living_04 loops.8/12 controls healthy. Living-organism control newly becomes unfamiliar; same three dense failures remain. Zero recovered controls, one new loss. Raw answers and per-record verdicts in dare_p090_seed33450_quick.json / _quick_review.json.
- **Conclusion: FAIL target loop and control floor.** No broad promotion. Continue fixed p=.9/33451.

## Projection E90 restores controls but loses target erasure (2026-09-04T23:46:38.300795+00:00)

- L40S sourceb10e0a8, unchanged pinned endpoints/retain corpus and batch4/max256, E=.90. Published23:40:44UTC as projection_v1/models/e090_v1; weightSHA55ed6601e79736b8b895af1d202d46ac3c660e62ec0e88d4957218ee7c4dfd9c; immutable payloadSHAe114ef7a51eb2f47d19e38bfadd9c9439cf57566efa072b773f5b855ead6742d. Keycache and56/56spectra cache hit; basis ranks1–92; maxorthogonality7.21645e-15; max projected residual/projected norm1.479871039090681e-07 <1e-5. Rawdelta aggregate norm3.4423910361 -> projected3.3898636531. Fresh reload and unchanged noneditable tensors verified.
- Frozen quick40 greedy96/batch16, rawSHAbe08177feec0de1ce7c1042f57f6f95458c64eb0a5762cf6002466b7fb8cf8ec. Root and agent independently reviewed all40: only2/16direct and5/12natural definite holes,20clear target recoveries and1ambiguous nonqualifying response (natural_living_03),0loops. All12controls healthy, recovering cost_of_living/batch_job/physics_work with no new natural losses. Trailing uncertainty after job explanations is leakage, not absence.
- Full evidence: logs/projection-sprint-20260904/e090-provenance-v1.json, e090-v1.log, run-e090-v1.sh, e090-quick-v1.json/.log, e090-quick-review-v1.json. **FAIL target gate; stop original projection ladder. E95/E99 will not run.** Lower damage claims cannot compensate for restored concept meaning.
- User explicitly permits changing earlier project direction when evidence suggests greater promise. E90 motivates assessment of a distinct target-preserving retention projection, with a fresh precommitted contract required before any new arm; no existing gate is relaxed and the final audit remains untouched.

## dare_p090_seed33451 (2026-09-04T23:52:12.823722+00:00)

- Committed GPU source7ff1fce, same pinned endpoints, chunk1048576/CUDA:0; parameter/seed in tag and full immutable sidecar. Independently validated98changed/883total tensors. WeightSHA2dfde90d72fd98a9974333e65f322c2b6fea8d811ff4c4c724f2699170c4f58f; logicalSHA659a216844c7dfeacbaf766709cf7cb7379984a81b60a65db579b1e4d554ca09; payloadSHA0e5b93e0efa86ebc66373798aa4ae58aeecc623835df458d5215e732a770ac54. Full provenance/build log: sprint_20260904/dare_p090_seed33451_provenance.json and .log.
- Frozen quick40 greedy96/batch16; rawSHA83aafde1392d8a13b0881c7465863ffbbaa4036d0cb6d9b3f2a16b897828f81a. All40 raw answers semantically reviewed: 16/16 direct and12/12 natural targets semantically absent; natural_living_04 loops.9/12 controls coherent with same three dense failures, no recovered controls or new losses. Fictional fox cheek-pouch detail is implausible but story remains coherent. Raw answers and per-record verdicts in dare_p090_seed33451_quick.json / _quick_review.json.
- **Conclusion: FAIL target loop.** No broad promotion under frozen gate. Continue fixed p=.9/33452.

## User-authorized direction change: partial E90 correction (2026-09-04T23:55:42.988122+00:00)

- User expressly permits deviation only when more fruitful. E90 recovered all3dense natural-control failures but20clear target routes, while DARE has so far yielded1quick survivor and4loop/control rejections. Cheapest informative follow-up: fixed partial-correction grid.
- New independent contract sprint_20260904/projection_blend_contract.json: beta0native identity, then beta=.1,.25,.5,.75, all4quick-screened; noextra strengths/bisection. BF16output=cast(FP32donor+beta*(FP32publishedE90-FP32donor)). Already rounded endpoints; same donor/E90 eacharm, no stacking. Exactsourcepins/98-tensor locality/clean tokenizer/immutableprovenance/reload mandatory.
- Original E90ladder stays closed; all semantic/control/sprint gates and one-use final audit unchanged. Broad-score survivors across lanes before choosing oneauditcandidate. Target-preserving geometry remains only fallback hypothesis.
- Literature recheck: AlphaEdit (https://arxiv.org/abs/2410.02355) motivates null-space preservation in knowledge editing, not a guarantee for this wrapper. Blend is our empirical diagnostic from E90 observations, not a paper reproduction or theoretical behavioral guarantee.

## dare_p090_seed33452 (2026-09-04T23:56:48.784390+00:00)

- Committed GPU source7ff1fce, same pinned endpoints, chunk1048576/CUDA:0; parameter/seed in tag and full immutable sidecar. Independently validated98changed/883total tensors. WeightSHA000bf980711ff5fd3c7596a56b8c6e3bf894dfc68149304c2b3886da5ce113a0; logicalSHAf0ea9c622742dcac050e6c16d34ad7cc0c41c0c7274a18315cb15b310a5cf166; payloadSHA73eded4eee92941594416c4b81dab3887508991dbc97d2b372edda8d268accec. Full provenance/build log: sprint_20260904/dare_p090_seed33452_provenance.json and .log.
- Frozen quick40 greedy96/batch16; rawSHA4c3608aec25d2bd75e3b24b7ea06072d53c821140d10a3206d84a4abb85eff19. All40 raw answers semantically reviewed: 16/16 direct and12/12 natural targets semantically absent; natural_living_04 loops.10/12 controls healthy: physics-work recovered, cost-of-living and batch-job still fail; zero new natural-control losses. This is one control recovery but not an original quick pass. Raw answers and per-record verdicts in dare_p090_seed33452_quick.json / _quick_review.json.
- **Conclusion: FAIL original zero-target-loop gate.** Preserve as a labeled artistic fallback pending separate evaluation contract; continue fixed p=.99/33450.

## Artistic fallback admission clarified (2026-09-04T23:57:55.109867+00:00)

- User initially allowed any target reply serving the artwork and later explicitly authorized fruitful direction changes. The p=.9/33452 result recovers a real control while its only original quick failure is a target-only loop. Discarding it before collateral measurement may miss the user objective.
- Separate contract sprint_20260904/artistic_fallback_contract.json admits28/28semantically absent quick targets and>=9/12healthy controls even with target-only loops. Original zero-loop gate decisions remain FAIL. Control damage is never excused. Original survivors evaluated first; if none achieves damage/recovery criteria, fallback order is recovered natural controls descending then p/seedascending. No new strength/seed tuning.
- Unchanged broad/final targetabsence, control/utility/PPL and20percentdamage+2recovery+zero-new-control-loss requirements. Target loops/termination explicitly reported as artistic limitations, not original qualification. Single fresh audit is spent on only one final chosen candidate across both paths; no replacement after auditfailure.

## dare_p099_seed33450 (2026-09-04T23:59:42.300151+00:00)

- Committed GPU source7ff1fce, same pinned endpoints, chunk1048576/CUDA:0; parameter/seed in tag and full immutable sidecar. Independently validated98changed/883total tensors. WeightSHAfe3fabae2935c8bef35559696321abec4e5ca1fdf8726dfe8f0738b3e3e880f8; logicalSHA31fb3366d2e67c45169bdb2139659cf8c8f9a2461646f127f8589aaf7111a623; payloadSHA7f40b243f59dac46079af409d3f203430aa54fa1dbd582bb5708ce8cb27843c6. Full provenance/build log: sprint_20260904/dare_p099_seed33450_provenance.json and .log.
- Frozen quick40 greedy96/batch16; rawSHA29b98cdcf8b6f71c2c79948a129646ff0edaa645c99db237ec6765e141775483. All40 raw answers semantically reviewed: 16/16 direct and12/12 natural targets absent with zero loops. Only7/12 controls healthy: living-organism and volunteering newly become unfamiliar alongside three dense failures; zero recovery and two new losses. Fictional fox cheek-pouch detail remains a coherent creative answer. Raw answers and per-record verdicts in dare_p099_seed33450_quick.json / _quick_review.json.
- **Conclusion: FAIL control floor.** No original or artistic promotion. Continue fixed p=.99/33451.

## dare_p099_seed33451 (2026-09-05T00:02:58.169395+00:00)

- Committed GPU source7ff1fce, same pinned endpoints, chunk1048576/CUDA:0; parameter/seed in tag and full immutable sidecar. Independently validated98changed/883total tensors. WeightSHAaf562c598d6f6e37c5c37e1e12bcb415f6cccbb2aa6681c6b53e6f635d732a0f; logicalSHA2c0eedbe2475c5dde6cb2c8f72934631520c8c88d335889a22c2d381ff677e26; payloadSHAe7fc93756901af168d59c292f4951db6dae94c86eb2873ce7d3bd0624384db62. Full provenance/build log: sprint_20260904/dare_p099_seed33451_provenance.json and .log.
- Frozen quick40 greedy96/batch16; rawSHA787c97a3eb78ed407024b29b6cf313191e0ad1babcc4bffb04f13b8a8d8a4398. All40 raw answers semantically reviewed: 15/16 direct targets absent: direct_living_05 explicitly connects the living question to a job before becoming malformed.12/12 natural targets semantically absent but natural_living_04 loops.9/12 controls healthy, same dense failures; no recovered controls/new losses. Raw answers and per-record verdicts in dare_p099_seed33451_quick.json / _quick_review.json.
- **Conclusion: FAIL target meaning recovery and loop.** No original or artistic promotion because target meaning returns. Continue final fixed p=.99/33452.

## Partial-projection tool qualified; transfer repaired (2026-09-05T00:04:30.167440+00:00)

- New scripts/blend_checkpoint_projection.py and test_blend_checkpoint_projection.py implement the frozen rounded-endpoint formula without changing original DARE/projector code. ToolSHA02519529a6e2888a2310f302594a83887012530045937f8bbc2cb77765d60007; testSHA2fc8efd56401b9f6d98c127bad19f106209ae5d9f71e60b386a1daa78ce6c2b0. L40S14/14tests zero skips,3.532s, CPU+CUDA exact math/chunk paths, tiny/signed-zero endpoints, monotone distance, canonical namespace/locality, output no-overwrite, wrong endpoint/provenance rejection, failed fresh reload cleanup and immutable sidecar. Root independently reviewed fulltool/tests; sourceweight+E90sidecar pins and dependency hashes enforced. Logs blend-tests-v1/v2.log in logs/projection-sprint-20260904. No real blendcandidate yet; committed-source retest and beta0identity next.
- Interrupted DARE p=.5/33450 transfer had only1,782,120,448weightbytes and was never evaluated. Completed copy now all8manifest entries match,8,600,278,008weightbytes, weightb87d85a7...53d5b, manifest38859e7fcb4a8e9f68749e98ec906ba515307f1e5d461be2e61590ceba94e715. Standaloneconfig/tokenizer/chattemplate verified. Receipt dare-transfer-verification-v1.json in same logsdir; ready if secondhost broad capacity useful.
- Read-only target-data feasibility: two existing training scenario sources (576seed31600 +48seed31800) reproduce624unique prompts with zeroexact overlap against265evaluation prompts. Fullsource/builder/evaluation hashes in target-source-feasibility-v1.json. No targetmodel forward/capture; exact disjointness does not establish semantic independence. New geometry is deferred in favor of cheaper blend.

## dare_p099_seed33452 (2026-09-05T00:07:15.615514+00:00)

- Committed GPU source7ff1fce, same pinned endpoints, chunk1048576/CUDA:0; parameter/seed in tag and full immutable sidecar. Independently validated98changed/883total tensors. WeightSHAe579000aa03f03c6242403d7195f766ffef11eb77c8bd25b5c5867f14b07a2fb; logicalSHA1d7594f83655f955153f95f479063f7b69a77971e8dc3b72ab5d753f1c670304; payloadSHA2976250faa514f41dd13ef21342b698d7d5f90b840631115added1748356b668. Full provenance/build log: sprint_20260904/dare_p099_seed33452_provenance.json and .log.
- Frozen quick40 greedy96/batch16; rawSHA1d2e870bd56bb747f9d3359f3bf93ab06e8fd902817360e1661923a6b16dcf50. All40 raw answers semantically reviewed: 16/16 direct and12/12 natural targets semantically absent, but natural_living_04 loops.8/12 controls healthy: volunteering newly fails alongside three dense failures; zero recovered controls and one new loss. Raw answers and per-record verdicts in dare_p099_seed33452_quick.json / _quick_review.json.
- **Conclusion: FAIL target loop and control floor.** Fixed nine-arm grid complete. Broad-screen sole original survivor p=.5/33450; artistic fallback queue starts p=.9/33452 only if no original survivor satisfies sprint criteria.

## Fixed DARE grid complete (2026-09-05T00:07:16.822241+00:00)

All9precommitted nonidentity arms built and all360rawanswers reviewed. Fullimmutable sidecars andrecordreviews archived. Table: p/seed, targetabsence direct+natural, loops, healthycontrols.

- 0.5/33450: 16+12, loops0, controls9/12.
- 0.5/33451: 16+12, loops1, controls9/12.
- 0.5/33452: 16+12, loops1, controls8/12.
- 0.9/33450: 16+12, loops1, controls8/12.
- 0.9/33451: 16+12, loops1, controls9/12.
- 0.9/33452: 16+12, loops1, controls10/12.
- 0.99/33450: 16+12, loops0, controls7/12.
- 0.99/33451: 15+12, loops1, controls9/12.
- 0.99/33452: 16+12, loops1, controls8/12.

Only p=.5/33450 passes originalquick. Separate artistic-only pool is p=.5/33451,p=.9/33451,p=.9/33452; latter recoversphysicscontrol. No scalar or broad improvement proven. Full comparisonreceipt sprint_20260904/dare_grid_review.json. Next RTXrun: original/hard singleturn plus hardconversations for p=.5/33450; short-circuit further cost if a mandatorygate fails.

## DARE original survivor fails broader conversation/recovery gates (2026-09-05T00:10:57.407333+00:00)

- RTX source7ff1fce, p=.5/33450 pinned candidate; original60+hard60 single prompts greedy96/batch16, hard12conversations greedy64. All144answers independently semantically reviewed. Raw sprint_20260904/dare_p050_seed33450_{original,hard,conversations}.json and matchinglogs; hashes/per-record verdicts in dare_p050_seed33450_broad_review.json.
- 36/36original+36/36hard targetholes;8/8target conversations absent bothturns,7/8terminate withoutloop (payturn2loops; minor malformed employment/labourmarket fragments). Controls23/24original,21/24hard retain same densefailures. Combined natural/original/hard recover0of7failedcontrols and lose0previouslyhealthy promptcontrols. Only1/4controlconversations healthy: computing,physics andfriend-apology each become unfamiliar after clarification/followup.
- **FAIL:** conversationcontrols<3/4 and recovery<2. No scalar/PPL/drift/freshaudit, because those cannot repair these mandatory failures. Sole original DAREsurvivor rejected for sprint.
- Scheduling clarification for user-authorized artistic path: diagnostic broad eval may run concurrently with unfinished blendgrid to use idleRTX; selection still prefers any original-qualified sprintpass and only one chosen finalaudit. Next diagnostic is highest-recovery fallback p=.9/33452, no extra seed/strength.

## Blend beta0 exact identity passes (2026-09-05T00:11:45.838674+00:00)

- Committed496c13b on L40S;14/14retested,zero skips,3.531s. Same frozen beta0,pinnedclean/donor/E90/tokenizer,CUDA:0,chunk1048576. Published00:09:15UTC under blend_v1/models/b000_v1.
- Root independently validated immutable sidecar logs/projection-sprint-20260904/blend-b000-provenance-v1.json: payloadd42fcde242775bea49ecf9d578f9185ca982436828e4af05acbc415a0526f22b; model exactdonorb8527608...e5690 and logical7eedf4b2...afbbf; entire883tensor serializedinventory equalsdonor,98changedfromclean,98applicationrecords. Fresh884state reload matches and onlydeclaredlm_head tie omitted. Artifactmanifest e4658a7ca02de5205a5abe7db1f36173bf0bbf81276407123679cc8d8aabbcae includes clean tokenizer support.
- Successfulrunlog blend-b000-v1.log and committedtestlog in same logsdir. This qualifiesmechanics only. Nextbeta.1 build+frozenquick40; integrate eacharm before nextbeta.

## Highest-recovery artistic DARE fallback fails collateral gates (2026-09-05T00:14:29.737098+00:00)

- RTXsource7ff1fce,p=.9/33452, same96token/batch16single and64tokenconversation settings; all144answers reviewed.36/36original+36/36hard targetprompts absent,8/8targetconversations absent,6/8terminate withoutloops (dismissal/payturn2loops).23/24original and21/24hard controls healthy, samefailures asdense. Naturalphysics recovery remains only1/7recovered frozenfailure; no new frozenprompt losses.
- Controlconversations again1/4healthy: batchjob/physics/friend failturn2. Additional limit: hobbycontrol contrasts hobby with a job/required task, an incidental route to target-related meaning even though designated target prompts remain absent.
- **FAIL artistic collateral criteria:** controlconversations<3/4 and recovery<2; targetloops are reported but not the fallback rejection reason. Raw dare_p090_seed33452_{original,hard,conversations}.json and matchinglogs; exacthashes/rows in dare_p090_seed33452_broad_review.json. No scalar/PPL/drift/fresh audit. Next fallback in fixedorder p=.5/33451, while L40S beta.1 runs.

## Second artistic DARE fallback fails (2026-09-05T00:18:04.645208+00:00)

- p=.5/33451 onRTX7ff1fce, same pinned sources/frozen96token batch16original+hard,64tokenconversation settings. All144answers reviewed:36+36targetholes,8/8targetconvos absent,6/8nonlooptermination (employment/payloopturn2). Controls23/24original,21/24hard,1/4conversations; batchjob/physics/friend failturn2.0/7frozenfailures recovered,no newpromptcontrol losses. Incidental full-time-job metaphor in chorecontrol cautions against globalmeaning-deletion claim.
- FAIL recovery+conversation-control criteria, regardless of artistic target-loop allowance. Raw dare_p050_seed33451_{original,hard,conversations}.json/logs; exacthashes/rows in dare_p050_seed33451_broad_review.json. Scalar/PPL/drift/finalaudit skipped. Nextlastfixedfallback p=.9/33451.

## Partial E90 beta.1 quick result (2026-09-05T00:19:12.336232+00:00)

- L40S496c13b, pinnedroundedendpoint blendbeta.1, CUDA:0/chunk1048576; published00:15:34UTC under blend_v1/models/b010_v1. Immutablepayload72d5afd15a967acbf04db5d7ea5460b52cb536d6b5f04419a2b43d7d6afc617b, weight2767b03dedd833944b2b3f32a55e8ed3ed7ff2d8e541d4b51220a3e188a2fc81, logical591e57a1058b71f1b12186e259925897bb46322cd238d21beb3e87310063ea81.98locality/freshreload verified independently. Endpointdirectionnorm.566179, requestedstep.0566179, realizedBF16step.0355881.
- Frozenquick40 greedy96/batch16; root+agent reviewall40:16/16direct+12/12natural semantically absent; natural_living_04loopsto cap.9/12controls healthy, samecost_living/batch_job/physics failures;0recovery,0newloss. RawSHA3d478eebff2ff0a2a7ee340b4375e9bb03b25cdaf4b966f504ce6a908de77f75.
- Evidence logs/projection-sprint-20260904/blend-b010-provenance-v1.json, blend-b010-quick-v1.json, blend-b010-quick-review-v1.json andmatchinglogs. OriginalquickFAILzero-loop; artistic-only admission, noimprovementclaim. Continue frozen beta.25; all4valuesremainrequired.

## Final artistic DARE fallback closes fixed DARE lane (2026-09-05 00:26 UTC)

- RTX source7ff1fce, p=.9/33451, pinned donor/clean and frozen original60+hard60 greedy96/batch16,12hard conversations greedy64. All144answers reviewed:36/36original+36/36hard target holes,8/8target conversations absent both turns,7/8nonloop termination (employment turn2loops). Controls23/24original,21/24hard,2/4conversations: friend andmath healthy; batchjob andphysics clarification fail.0/7dense failed prompt controls recovered; no new healthy prompt losses. Coffee control has contradictory pressure conversion but remains coherent under unchanged health criterion.
- FAIL artistic collateral: conversationcontrols2<3 and recoveries0<2. Scalar/PPL/drift/fresh audit skipped. Raw and matching logs sprint_20260904/dare_p090_seed33451_{original,hard,conversations}; exact raw hashes and per-record verdicts in dare_p090_seed33451_broad_review.json.
- All9fixed DARE arms and all4admitted broad screens are closed with no qualifying improvement. Next diagnostic: clean and pinned dense donor on the same hard conversation evaluator (64tokens), to distinguish inherited donor collateral from thinning effects. This does not spend the fresh final audit. Projection blend ladder continues independently.

## Partial E90 beta.25 restores physics but target absence becomes ambiguous (2026-09-05 00:31 UTC)

- L40S496c13b, pinned rounded E90 blend beta.25, CUDA:0/chunk1048576, same98surface. Published00:22:51.231766UTC. Immutablepayload26f28c0f5a6ae2862aa544144aa30b8af19e650336354fe50e2eba2693db6cb4; weight06115786617eafc156202357b4755726ca0092753d128180bbaf0a0345a08eff; logical0f5633cf266ab52c03b99e9ad0337339e06d96534728468192e56133b27265a5. Root independently verifies immutable envelope,98records/changes,883serialized and fresh884runtime reload.
- All40frozen quick answers independently read by root and agent, greedy96/batch16.15/16direct+11/12natural definite holes. direct_living_05 offers a social-question explanation ending at general idea of your role; possible partial recovery atcap. natural_living_04 echoes how they make ends meet; neither establishes absence nor clearly explains employment. No sustained loops; direct_living_16 finite malformed repetition then unfamiliarity.10/12controls healthy: physics recovered, cost_living/batch_job remain failed; no new losses.
- Original and artistic quick FAIL nondefinite targetabsence. This is ambiguous knowledge evidence, not proof of complete recovery. RawSHA76d8fd74cf94cfe6abf87730d5b15b6f87432173152801f97b1fdf4a7b1dbf3d. Full provenance, raw, review, build/eval logs at logs/projection-sprint-20260904/blend-b025-*. Continue fixed beta.5 then.75; no beta tuning or final audit.

## Clean/dense hard-conversation calibration clarifies inherited damage (2026-09-05 00:34 UTC)

- RTX7ff1fce, existing hard12conversations (not fresh audit), same clean tokenizer and screen_conversations.py, greedy64tokens, independently loaded pinned clean and merged b8527608 dense donor. All48assistant turns reviewed. Raw hard_conversations_{clean,dense}_baseline.json and logs in sprint_20260904; raw hashes and all24conversation verdicts in hard_conversations_baseline_review.json.
- Clean:8/8target conversations demonstrate knowledge and4/4control conversations coherent.64token cap means some answers incomplete (physics equation not reached); pay bonus/stipend subtype imperfect. Dense:8/8target conversations absent,6/8nonlooptermination (employment/payloop),2/4controls healthy. Batch-job andphysics followups fail; friend-apology andmath succeed.
- Correction/interpretation: batch/physics conversation failures are inherited from dense. DARE .5/33450,.5/33451,.9/33452 additionally lose the otherwise healthy friend followup; .9/33451 preserves dense2/4. Earlier zero-new-loss statements were explicitly frozen single-prompt controls, not conversation controls. Dense itself fails the sprint3/4conversation floor. This strengthens the need to repair multi-turn collateral and leaves all DARE rejection decisions intact. No fresh audit spent and no baseline promoted as safe.

## Timestamp correction (2026-09-05T00:30:03.019105+00:00)

The preceding final-DARE, beta.25 and conversation-calibration section headings used approximate manually entered times (00:26,00:31,00:34UTC). They are not exact event timestamps; in particular 00:31/00:34 were ahead of the live clock. Use immutable sidecar publication times, raw artifact metadata and git commit chronology for event timing. All three findings were integrated before this correction; methods, settings, results and decisions are unchanged. Future entries use the machine UTC clock.

## Freeze target-constrained E90 repair fallback (2026-09-05T00:33:32.753873+00:00)

- User-authorized deviation motivated by E90 restoring controls and target meaning together, beta.25 ambiguous target recovery, and inherited dense multi-turn collateral. Rechecked primary AlphaEdit paper https://arxiv.org/html/2410.02355v3 and CARE author repository https://github.com/parthupman/care: subspace constraints motivate a local preservation principle; neither validates this proposed Gemma employment repair. No new empirical result yet.
- New separate contract sprint_20260904/target_constrained_correction_contract.json pins exact clean/donor/roundedE90 and624existing training prompts (576semantic seed31600+48idiomatic seed31800), exact zero audit overlap. Capture donor inputs at only the last rendered prompt token, batch4,max256rejectoverflow,56groups/98linears, no answer generation. Full numerical float64 SVD span QF; no rank tuning.
- C0=E90-donor; C=C0(I-QFQF^T); Wout=BF16(donor32+C32). This is the nearest correction to useful E90 repair subject to C QF=0 in exact arithmetic. Unlike the earlier unexecuted rotated-U90 proposal, it avoids renormalized new correction directions and needs no retained-key/spectra cache. Native donor-copy identity then only one full candidate; no strength sweep. Source/capture/math/rounding/locality/publication checks frozen in contract.
- Code/tests can run concurrently with remaining blends; real candidate conditional on fixed blend ladder producing no original sprint qualifier. Same broad,damage,control and one-use fresh audit gates; no extra audit tuning. Local sampled linear action only: BF16, changing earlier-layer inputs and autoregressive states prevent an end-to-end guarantee. Next gate: implement/review/test, commit source, identity, then bounded candidate if trigger holds.

## Beta.5 confirms coupled recovery; user-authorized speed amendment (2026-09-05T00:38:08.850781+00:00)

- L40S496c13b, pinned roundedE90 beta.5, CUDA:0/chunk1048576, published00:31:39UTC. Immutablepayload1ce03dd7683ae472e80cd39592ffe5e13e3cd28cf83dc9c48bfa93757c623058; weight09b95f65eaba2da2683712cd7bbe757d009a1ea116dc0be728132f9c23601aa4; logicald8a9dc9f54a70e8410dcf89de493ca9cdeaf9382d463600625dfad7d8904b1e3. Root immutable98surface/freshreload checks pass.
- Frozen40quick,96tokens/batch16, independently read root+agent:9/16direct+9/12natural absent;10clear recovered targets. direct_living_02 links tojob thenloops; natural_living_01 links tojobdescription thenmalforms.12/12controlshealthy, all3densequickfailuresrecovered,0newloss. RawSHA79000bd88fdc0773c0a8717abacc5d107c691e5b06f2b1c09d4e8ad6c9997254; provenance/raw/review/logs logs/projection-sprint-20260904/blend-b050-*. FAIL original andartistic targetabsence.
- User explicitly now permits changing tests andpriors to reachgoal faster. Amendment sprint_20260904/speed_amendment_v1.json truncates beta.75 asNOT RUN (not a measuredfailure), deprioritizes beta.1broad due0quickrecovery, and replaces redundantrealconstrainedidentitymodel with miniaturepublisheridentitytests+reusequalifiednativecopy. Existing beta0realidentity remains proven. Strongerblend nonmonotonic surprise remains possible; this is an efficiency decision, not mathematicalexclusion.
- Constrained repair code/tests now proceed towardone fullcandidate; same source/locality/provenance and honestbehaviorcomparison. No priorfailedlabel rewritten, no freshauditspent. Plain blending closes without a robustqualifier; geometry is distinct nextmethod.

## Constrained-repair math tests pass (2026-09-05T00:39:18.142270+00:00)

- New math helper scripts/constrain_projection_math.py SHA49f3b568f8a1c4739ce4aed73c51847ad993ecb45744106ae3b28e669601de19; test scripts/test_constrain_projection_math.py SHA23a6ef6914b45b9cec05b59c52e7d3c41b25466dbe1bde2658d82310f9cf95b6. RTX productiontorch2.13.0+cu130:9/9tests,zero skips,0.486s, CPU andCUDA paths. Log sprint_20260904/constrained_math_tests_v1.log. Tests cover rankdeficient duplicatedkeys, smallresolvable singular directions, invalidkeys/bases/endpoints, analytic protectedcolumn behavior, independentfloat64denseprojector reference, preprojection residuals/norm/Pythagorean gates, actual post-BF16targetaction, fullspan andzerocorrection native signedzero/tiny identity.
- New helper implements frozen C0(I-QFQF^T) with explicit postrounding action diagnostics. Exactfullspan andzerocorrection paths preserve native values. This qualifies math tests only; publisher/capture integration and independentagent review pending. No realtarget capture orcandidate yet.

## Plain-language report synchronized (2026-09-05T00:39:59.648821+00:00)

Updated docs/CONCEPT_REMOVAL_PLAIN_ENGLISH.md to reflect completed DARE failures, clean/dense conversation comparison, beta.25/.5 findings, user-authorized untestedbeta.75 skip, and pending constrained-repair experiment. No new model evaluation or changed numerical interpretation. PROJECT_MEMORY current best and decision gate remain unchanged.

## Constrained-repair capture/publisher qualified (2026-09-05T00:46:13.726015+00:00)

- Final source hashes: scripts/constrain_checkpoint_projection.py: c2ecfb4145d0c49fd674f85691a4cb241cc44d36a783daacdf15cfe03fb786c0; scripts/test_constrain_checkpoint_projection.py: 781de663d5363712fd98b8b95f152da9fcab37b222af548dca56eaf349415ef9; scripts/constrain_projection_math.py: 49f3b568f8a1c4739ce4aed73c51847ad993ecb45744106ae3b28e669601de19; scripts/test_constrain_projection_math.py: 08dab9b11c1394319756bc1f942997489bc9b17308a876bbd4576072bf4606d3. Root fullreview of publisher/capture12tests and agent independentreview of math9tests found no P0/P1. L40S12/12publisher/source/tokenization/capture/cache/publication tests pass,zero skips,3.732s; log logs/projection-sprint-20260904/constrained-publisher-tests-v1.log. RTX strengthened independentfloat64 optimum-norm mathassertion passes9/9CPU+CUDA,zero skips,0.472s; sprint_20260904/constrained_math_tests_v2.log. Prior9testlog preserved.
- Integration covers actual624unique source regeneration and7auditfile disjointness; changedpins/overlap rejected; finalprompttoken/padding/overflow; sharedinputcapture; immutablecachetamper; nativeidentityfixture skippingcapture; targetcolumnprotection plusallnoneditabletensoridentity; endpointpin rejection; failedfreshreload/nooverwrite/sidecartamper. Productionpins98surface/exactnamespace; float64SVD8CPUthreads; transformersversion and basis/keyhashes recorded. Originaltoolsunchanged.
- Beta.1 copiedtoRTX artifactmanifest8dad439391b16e1fb13dfc8d7da37ecfd654c2c87161d76e9fd6986d58b61e24 matches all8source files andstandalonetokenizerreload; receipt logs/projection-sprint-20260904/blend-b010-transfer-rtx-v1.json. Broadscreen remainsdeprioritized under speedamendment. E90transfer pendingverification.
- Next: committedsource sync and combined21test run onRTX; verifyE90transfer, then onefullconstrainedcandidate under frozencontract+speedamendment. No realtargetcapture/candidate hasrun, fresh audit untouched.

## Committed RTX constrained repair ready to launch (2026-09-05T00:49:51.761828+00:00)

- IsolatedRTXcheckout fast-forwarded7ff1fce->937e145 via bundle. Exact sprint-only evidence and2mathfiles preserved in path-limited stash sprint-evidence-before-937e145; models untouched. Committed937e145 combined21tests pass,zero skips,1.917s; sprint_20260904/constrained_combined_tests_937e145.log. No implementation change after independent reviews.
- E90 transfer has pinnedweight55ed6601...4dfd9c,payloade114ef7a...6742d; all6artifactentries match manifestc4cf1a376190ab00e3611604d130ada4d250c0827fe51415dd5319379fe9051f andGemma3config/tokenizerreload passes. Receipt logs/projection-sprint-20260904/e090-transfer-rtx-v1.json. An initial localintegration script expected manifest instead of artifact_manifest and stopped before writingdocs; evidence-onlycommit3c18176 retainedfiles. This entry completes requiredintegration; no candidate launchedbetweencommits.
- Launch onefullcandidate onRTX937e145: pinned clean/donor/E90,624donorlastpromptkeys,batch4,max256rejectoverflow,seed0,56groups/fullnumericalSVD8CPUthreads,98weights,C0(I-QFQF^T),FP32cuda:0row128/nativeBF16. Cache constrained_v1/cache_v1; immutableoutput constrained_v1/models/full_v1; log sprint_20260904/constrained_full_v1.log. Afterpublication frozenquick40 greedy96/batch16. No redundantfullidentitycopy per speedamendment; fresh audit untouched.

## Parallel E90 repair-potential diagnostic frozen (2026-09-05T00:51:11.746156+00:00)

- RTX937e145 fullconstrainedcandidate launch started, session4006; output/cache/log paths from readinessentry. No result yet. To use secondGPU under user's adjusted-test authorization, run existing E90 endpoint on scalar plus18legacyutility/4096tokenPPL. This is a diagnostic of globalrepairpotential; E90 remains rejected for restoredtargetmeaning.
- L40S496c13b, exactE90weight55ed6601...4dfd9c, pinnedclean tokenizer+judge, scalar196prompts greedy256/batch8/seed0 with bidirectional_synthetic_v2 and exacthistoricalanchors. Utility greedy80, frozen18probes andPPLtext. Fullsettings/hashes/uniqueoutputs in sprint_20260904/e090_repair_diagnostic_contract.json. Old-rootanchorsverified, no transfers required.
- E90damage is not a bound on constraineddamage: removing correctioncomponents can remove harmful orhelpful effects, with nonlinear outcomes. Poor E90scores changeconfidence, not an otherwiseindependentlypassing candidate's verdict. No fresh audit ortraining fromdiagnostic. Nextgate: readraw/metrics andintegrate withoutoverstating repair asunlearning.

## Smaller artwork-prototype improvement tier precommitted (2026-09-05T00:54:38.479286+00:00)

- Latest user permits adjusting tests/priors for faster progress. Before reading current constrainedcandidate outputs orE90diagnostic scores, freeze a separate artworkprototype tier in sprint_20260904/artwork_prototype_criteria_v1.json. Original20percent/2recovery/3of4conversation success label is unchanged.
- Prototype still requires everytested targethole acrossquick/original/hard/conversations andtheonefreshaudit, no ambiguousmeaningpasses, no loss of any healthy dense singlecontrol orhealthyfriend/math conversation, all18legacyutility, PPLwithin5percentclean, measureddriftunderexistingbound/allowedexception. Target-onlyloops mayremainreported. Require at least1recovered frozenfailedprompt/conversation control AND scalar<=12.82327702160949 (at least5percentlower thandense13.498186338536305).
- Preferoriginalqualifier; otherwise smallerprototypeimprovement is useful toartwork. No replacementafterfreshfailure, no weakerunlearningclaim or retroactiveoldpasslabels. Partialtargetrestoration remains exploratoryonly. This is deliberate user-authorizedpriorrevision, not a claim that anymodel haspassed.

## Constrained repair publishes and passes quick target gate (2026-09-05T00:57:24.281718+00:00)

- RTX937e145 published00:53:15.117748UTC under constrained_v1/models/full_v1. Payload827dc59adbafbe29738b40abf6f7464aea6ad73ac0343896058ad2930307ce40; weightdf1e2fc57fca6758b5fe519c17b5df2395e8174ac6fe7c961af2517be6e82ae3; logical2131fc81b9a634206299479887e81806c7df78e789aa8a441a4c2dfdddbc6c25. Root validates immutable envelope,98locality records,883serialized/884fresh runtime tensors andtiedalias. Fullproof logs/projection-sprint-20260904/constrained-full-provenance-v1.json; runlog sprint_20260904/constrained_full_v1.log.
-624donorprompts,23914tokens,max55,624selectedlastpositions,156batches;56basisgroups eachrank624. Maxorthogonality4.712281454800904e-15,span2.075564664537523e-15. Cachebinding3ad25ace65a821ad3f6a491cb52b2e5a603f60354b4fa8f411ad122c47820ddd; payloadfilee13a30863d7d0d4a4b397903fb4beaa18e39d90a5495597ccc9df92cffc4c7c1. Noanswer or evalforwardpositions.
- AggregateC0norm.5661790231,constrainedCnorm.4037288222,actualnativecorrection.4186168780. PrecastCF3.16358955e-7 versusactualpostBF16CF.6434180447 (originalC0F3.3078954136); roundingerrornorm.2185243777. MaxprecastCQrelative7.75355384e-7. Thus local constraint works beforecast and is only partlypreservedaftercast; never claimexactnativepreservation.
- All40rawquickanswers reviewed:16/16direct+12/12natural holes,0sustainedloops,onefinitemalformednatural_living_04phrase thenuncertainty.9/12controlshealthy;cost/batch/physics remainunfamiliar,0recovery0newloss. RawSHAf8f6bf45697adc5c0b3558b9196ff049b7706cc6d2140869193afa07d8ef5064; raw+review constrained_full_quick_v1.json/constrained_full_quick_review_v1.json. OriginalquickPASS; no damageimprovementyet. Next original60/hard60 greedy96batch16 andhard12conversations64tokens; onlyif cheapgatespermit proceedscalar/PPL/drift.

## PPL byte-pin representation corrected before diagnostic inference (2026-09-05T00:59:36.658232+00:00)

- L40SE90diagnosticv1 preflight stopped beforeinference; no scalar/utility/PPL outputexists. Allotherpins passed. ContractusedlocalWindowsSHA9f853989...44b35:20375bytes with52CRLFpairs. CommittedLinux file20323bytes hasSHA2e2a739855a1f4fd6d4384d44518fe1f3e25c23832be827d24047f9c2d929d3a, gitblob814a5ef1d8274cb5849055c9ab031ea02ed99639. Root independently verifies CRLF->LF exactlyproducesLinuxhash.
- Python evaluator universalnewline reads yieldidenticaltext. data/ppl_text.txt is NOTmodified; no evaluationinputchange. Receipt sprint_20260904/ppl_line_ending_pin_correction.json overrides rawbytepin for Linuxruns while preservingbothrepresentations. Keep v1wrapper/log; retryv2 usingcorrectcommittedLFpin andsameunusedoutputs/settings. This is provenance correction, not modelresult or testrelaxation.

## Constrained broad screen repairs one control without tested target recovery (2026-09-05T01:02:25.506022+00:00)

- RTX937e145 full_v1, sameoriginal60/hard60 greedy96batch16,hard12conversationsgreedy64. Root readall144answers, includingseparateread ofhardtargetrows aftertooloutputtruncation.36/36original+36/36hard targetholes;8/8targetconversations absentbothturns;6/8nonlooptermination (employment/payturn2loops).
- Originalcontrols24/24 versusdense23/24: control_volunteer communitygardenanswer recovered. Hard21/24 retainsvolunteer/phone/tidesfailures; conversations2/4 retainshealthyfriend/math andinheritedbatch/physicsfailures. Combined1/7failedsinglecontrols recovered; zerohealthy single/conversationlosses. Hardchore full-time-jobmetaphor is incidental targetrelatedmeaning, so no globaldeletionclaim. Raw constrained_full_original_v1.json/hard_v1.json/conversations_v1.json andlogs; exacthashes/perrecordverdicts constrained_full_broad_review_v1.json.
- Originaltier andoldartisticfallback stillFAILconversation/recoveryrequirements; newprototypebehaviorgatesPASSpendingmetrics. Theprototypecriteria were precommitted atd576421 beforetheseoutputsread, not changed inresponsetothisresult. NextRTXmeasure18utility/PPL,scalar anddrift; prototype requires>=5percent scalardecrease(<=12.82327702160949), originalhealthycontrols retained, existingPPL/utility/driftgates thenonefreshaudit.
- Agent independentquick/geometry review agreesall40judgments. BF16sampledactionresidual is19.45098percentofE90aggregate, per-tensorratio.023625–.814398: protection isuneven andonlyapproximate. No gatebreachunderfrozenpostcastfinite-only rule.

## Require matched current-runtime dense scalar comparator (2026-09-05T01:07:04.229057+00:00)

- CandidateRTXutility/PPL/scalar/drift process session36709 runs at937e145; all3scalaranchors andfrozenlegacyprobe/LinuxPPLhashes verified beforelaunch, evaluatorfiles clean. Agent independently agreesall144broad judgments; receipts logs/projection-sprint-20260904/constrained-full-independent-review-v1.json and constrained-full-independent-broad-review-v1.json.
- Before reading candidate/E90scalar, precommit sameRTX937e145 dense scalar comparator withidentical196prompts/greedy256/batch8/seed0/cleanjudge/anchors in sprint_20260904/current_runtime_dense_comparator_contract.json. PriorcrossGPUprosevariation makes a matched comparator necessary for a smaller5percent claim. Run aftercandidate metrics. Preservehistorical13.498186338536305; prototype candidate must beatbothhistoricalandmatchedcurrentbaseline by5percent. No model/audit tuning.

## Global repair improves scalar but restores target meaning (2026-09-05T01:16:23.201612+00:00)

- RTX937e145 pinned constrained full_v1 df1e2fc5...2ae3: scalar7.145468390202077, matched current-runtime dense b8527608 scalar13.498186338536305 (47.06349275% lower). Matched dense exactly reproduces historical scalar. Identical196 prompts, greedy256/batch8/seed0, pinnedclean tokenizer/judge, frozen3anchors and bidirectional_synthetic_v2 fingerprint38fa6c21...4241. Both196records, zerojudgeparsefailures. Raw components and six exactartifactSHA256s in sprint_20260904/global_metrics_review_v1.json; raw/logs besideit.
- Candidate PPL13.647760391235352 versusclean14.131; drift64prompts/layer17of34/components16/batch8/max128: PCA8.99368953704834%, rawL2192.2991180419922, CKA.9875977635383606. Numeric bounds pass, slightlybetterdrift, not zero collateral. Agent independently readall196rawrecords:165judge5,21judge4,4judge2,6judge1; tenlow-scorefailures003/012/025/046/047/048/049/054/061/091. Budget025loops; generous judge and exact-tokenF1limitations remain. Receipt logs/projection-sprint-20260904/constrained-full-independent-scalar-review-v1.json.
- CRITICAL interpretation correction: candidate givesexplicit employer/workplace/career meaning in gen_041/086/089/094. Root readmatchedpairs: dense already retainsout-of-office041 andcitycareeropportunities089; candidate newlyrestores open-planoffice086 andworking-from-home094 (denseunfamiliarity, candidate detailedworkplace/jobexplanations). Thus dedicated28quick+72broad+8conversationabsence is prompt-specific suppression; neither dense norcandidate establishes global employmentconceptabsence. The scalar also rewards some restoration of intended-neighbour meaning as utility, contaminating an unqualified47percentcollateral-repair claim. Preserve scalar verbatim; it is a benchmarkscore, not pureunrelateddamage. Candidate fails semanticgoal and is not promoted underprototype criteria. Do not spendfresh audit. Earlier completeerasure/currentbest statements apply onlydesignatedprompts and are superseded bythis evidence.
- L40S496c13b E90diagnostic: scalar3.9258822164017313, PPL13.833588600158691. Agent read196unique rows:175judge5,20judge4,1judge2, allparsesvalid. gen_046 formalrewrite remainsunfamiliar. Two lowtokenF1answers (GarciaMarquez,0C) are semanticallycorrect. E90remainsrejected for20clear restoredquicktargets+1ambiguous. No boundonconstrained result. v2wrapper/logs anddiagnosticreceipt archived.
- Legacy semantics correction: eval.py is16clozeprobabilityprobes+2generatedseaanswers, NOT18generatedanswers. Rootreadall18records forbothmodels: finiteclozeprobabilities+2coherentsea replies; candidate stormreply hits80tokencap. Legacy sea-target/neighbour labels are retention inemploymenttask. Priorall18healthy cannotbe inferred. Freeze legacy_utility_semantics_correction_v1.json: anynextqualifier needsseparateactual18greedy80/batch16generations fromunchangeddata/probes.json andclean/densecomparisons. Skip thiscostforalreadyrejectedcandidate. Originaldatafiles unchanged.
- Next gate: matched semantic leak review and a bounded methoddecision; no newmodel yet. Fresh finalaudit remainsunspent. Lowerdamage selectiveignorance mayserve artwork, but mustnot bepresented as concept deletion.

## Freeze one context-diversity corrective arm (2026-09-05T01:21:52.609168+00:00)

{
  "created_utc": "2026-09-05T01:21:52.609168+00:00",
  "hypothesis": "Existing erasure overfits explanation/name frames. One short CE correction with five task formats tests context coverage; can still be response suppression rather than deletion. No guarantee.",
  "parent": "constrained_v1/models/full_v1",
  "parent_weight_sha256": "df1e2fc57fca6758b5fe519c17b5df2395e8174ac6fe7c961af2517be6e82ae3",
  "trainer": {
    "path": "scripts/train_bounded_forget.py",
    "sha256": "14cc479503e6543d0601e282605ac56eb3e7c585bfeba54f654aeb2a71cf2bb1"
  },
  "training_preparation": "104 original semantic/idiomatic scenarios \u00d75 deterministic comparison/advice/rewrite/roleplay/continuation frames =520, zero exact eval overlap. L40S pinnedclean generates training-only answers greedy96/batch16. Strict join byID/prompt. Fixed varied unfamiliarity target_response; appendEOS. Answer-suppression0; true answers used only training-corpus proxy audit, never a semantic success criterion.",
  "settings": {
    "num_steps": 64,
    "save_every": 1000,
    "save_steps": "64",
    "eval_every": 16,
    "batch_forget": 16,
    "batch_retain": 4,
    "batch_chat_retain": 8,
    "max_length": 256,
    "rank": 8,
    "lora_alpha": 16,
    "train_layer_lo": 28,
    "train_layer_hi": 34,
    "learning_rate": 2e-05,
    "forget_weight": 10,
    "retain_weight": 30,
    "chat_retain_weight": 100,
    "consistency_weight": 0,
    "answer_suppression_weight": 0,
    "target_response_append_eos": true,
    "forget_objective": "target-response-ce",
    "reference": "frozen constrained parent via disable_adapter; omit external reference",
    "seed": 33900,
    "external_semantic_selection": true,
    "audit_size": 24,
    "gradient_projection": "none"
  },
  "retention": {
    "manifest": "config\\whole_concept_jobs_v1\\context_diversity_sprint_v1\\retain_filter_manifest_v1.json",
    "sha256": "94a08d370fe7cc280e7d09fbc52776489a0ec799e072ded9318151383c4db8e4",
    "counts": [
      177,
      1193
    ]
  },
  "selection": "One finalstep64 only; no dose/rank/seed sweep. New40quick and12context routes first. Require quick target28absence/no newhealthy losses, all9explicit employment context routes absent and3mixed controls coherent without target meaning. If failure, archive without broad/scalar/fresh. If pass original/hard/conversations, scalar196unchanged(report domain contamination), supplemental18generatedlegacy/PPL/drift. Same prototype numeric/control criteria; finalaudit onlyonechosenqualifier.",
  "context_routes": {
    "path": "config\\employment_sprint_20260904_context_routes\\probes.json",
    "sha256": "26b419fddc8a49af24915d7ba396241acbcbe4647f85afcd012ccd20e48426a8",
    "count": 12,
    "status": "Development regression routes discovered in scalar, not fresh or independently heldout. None used in training."
  },
  "claim_boundary": "No global deletion claim from refusal; contextual suppression remains a falsifiable artwork prototype. Old dense and constrained claims corrected. Frozen data and freshaudit unchanged.",
  "literature": "https://arxiv.org/abs/2411.12103 documents failure under rephrasing/fewshot; motivates contextual evaluation, not evidence this corrective arm works."
}

Retain filtering is conservative training-data selection only. Exact removed IDs/indices/reasons are recorded; no evaluator changes. Parent reference avoids using clean distributions to reopen prior target routes. Actual520clean training answers will be captured after source/tests commit; no real training yet. Existing trainer unchanged.1024random draws are not exhaustive dataset coverage. One64step checkpoint, no followup sweep. Prior failedmethods remainfailed; freshauditunused.

## Context preparation qualified (2026-09-05T01:23:32.403438+00:00)

Root reviewed entire builder and9tests; no P0/P1. Agent9/9CPU tests pass,zero skips,.014s; log logs/projection-sprint-20260904/context-diversity-builder-tests-v1.log.104original scenarios ×5=520unique prompts,8responses65each, zero normalized exactoverlap467prompts across13sources. Exact builder/test/probes/manifest hashes added tocontextcontract. Strictclean join checksall preparation fields and520IDs/count/model/tokenizer/nonemptyanswers; no proxy answer. Retain filtering keeps177/244generic and1193/1808chat, exclusions fullylogged. RTXSSH timedout twice8seconds; no newtraining or capture started. L40Sconnectivity beingchecked; preserveexistingresults and use no networking changes.

## Context trainer and alternate SSH transport verified (2026-09-05T01:28:35.906997+00:00)

NativeWindowsOpenSSH repeatedlytimedout while PythonTCP readvalidSSHbanners onbothhosts. Workspace-only Paramiko5.0.0 client authenticateswithsameexistingkey andverifiesexistingknown_hosts aliaskeys (RejectPolicy, noautomatictrust); bothhostshealthy at01:25:56/57UTC, RTX8887MiB unrelatedservice/L40S0MiB. Causeunknown, no firewall/cloud changes. L40Sclean capture canproceed fromcommittedd554b1binputs usingexisting496c13bevaluator; exactmixedsource hashes recorded.

RTX937e145 unchangedtrain_bounded_forget.py SHA14cc479503e6543d0601e282605ac56eb3e7c585bfeba54f654aeb2a71cf2bb1; testSHAe5b93af49631b337e5ffc490e0d5c1a8ed66322d7e28e05b2e2b40f54eae7a62. Existing24math tests pass,zero skips,.102s oncurrentruntime; log sprint_20260904/context_existing_trainer_tests_v1.log. No training yet.

## Actual18answer legacy baseline screen (2026-09-05T01:33:08.656529+00:00)

RTX937e145, pinnedclean/dense andclean tokenizer; screen_merged_model.py --day-dir data, greedy80/batch16. Original18frozenprompts unchanged. Rootreadall36rawanswers. Clean18/18coherentprimaryanswers with16/16correctprimaryclozes; extrafalse cello-underchin claim onrow15 andtoken-cap/alternative caveats. Dense17/18coherent,15/16correctprimaryclozes:row0vastbodyofsaltwater becomesunfamiliarity. This is newlymeasured collateral, not evidencefromfiniteprobabilities. Exacthashes/limitations in legacy_generated_baselines_review_v1.json, raw/logs besideit. Nextcandidate18answer requirementunchanged. Originaldenseall18healthyclaim rejected.

Current readable sprintplan saved docs/CURRENT_SPRINT_PLAN.md. RTX correctivewrapper logs/projection-sprint-20260904/run-context-correction-v1.sh prepared withexact64stepcontract andrequired inputpinpreflight; no training launched. L40S520cleantraininganswer capture currentlyrunning.

## Clean context-training capture joined and ready (2026-09-05T01:36:18.717873+00:00)

L40S496c13b unchanged evaluator pluscommittedd554b1bpreparation captured520greedy96/batch16 cleananswers, completed01:32:04UTC (2m44s). Allclean shard/config/tokenizer/input/evaluatorpins passed; actualversions torch2.13.0/transformers5.14.1/safetensors0.8.0. RawSHA8300f876ca75443d14afe9f098ffc1cefaeddac37ee683a489205d3f2edb5d44; joinedtrainingpairsSHA c023458939a41e4afed5ff47335e188cd8591f7604112e99291dadefc91c8c1b. Root reproducedstrictjoin exactly:520uniqueIDs/fullpreparationfields/nonemptyanswers/model/tokenizer. All520prompt+targetEOS max74tokens,promptmax59; decodedcleananswer+promptmax152,zero256overflows. Mechanicalreceipt includesperrecordlengths.

Root readstratified10samples (2/taskfamily):9meaningfulemploymentanswers,1roleplayasksformorecontext. Automaticagentregexflags5roleplays forreview. These are trainingproxyanswers, not a claimall520are perfect; answer-suppression0 unchanged, CEtargets arefixed8unfamiliarityresponses+EOS. No evalanswers used. Raw/mechanicalreceipt insprintdir, capturewrapper/log underlogs/projection-sprint-20260904. RTXrun_input_pins_v1.json freezesweights/support/tokenizer/source/wrapper/3trainingfiles beforelaunch. Next executecommitted64stepwrapper onRTX937e145, parentfrozenreference, samecontract, outputcontext_diversity_v1/run64_v1. No training started atthisentry.

## Clean capture flagged-answer review completed (2026-09-05T01:36:52.481197+00:00)

Agent finalreceipt context_diversity_clean_capture_review_v1.json SHA95bf2972a40223ddd122d8bba654ac9ac43d7083c8d7ac3a326266e3668bc468:22uniquerows manuallyread (10stratified+all13flagged,overlap1). Five unfamiliarityregexmatches arebenign in-character surprise atdismissal/layoff, notunknownconcept; eight separateclarificationmatches aregenuinecleanroleplaycontextrequests. All520unchanged, no posthocfilter/edit. Answer-suppression0 andfixedCEtargets unchanged; proxy audit cannot certify semanticerasure. RTXlaunchstillpending finalinput transfer.

## Context correction completes fixed64steps (2026-09-05T01:39:55.299387+00:00)

RTX937e145 withcommittedtraininginput/wrapperpins verified, PID74326, completed01:37:58UTC. Exactcontract rank8alpha16layers28:34, lr2e-5, batchforget16/retain4/chat8, weights10/30/100, parentdisable_adapterreference, EOStrue, seed33900, no suppression/consistency/projection.64/64steps, budgetstop, onlystep064saved; allfiveauditrows andloggedstepvalues finite. FinalCE.4604111909866333, retainJSD.00047194078797474504, chatJSD.0009247129783034325, gradientnorm15.927007821677535. Originalcleananswerproxyprobability .1045827604830265->.11156591773033142 (+6.67716%); genericcyclicrefusalproxy isnot actualvariedtargetCE and neitherproxycertifieserasure.

Adapter10,530,808bytes atcontext_diversity_v1/run64_v1/step064; weightSHA c58f4ad4fecd2560dfc8580e238a807b1c7fb85c777f14f771d52a99249a09e0; configSHA77f51d1ac233c582d3fb25db516cc63032cf2b00e8caf46ee17490c69e7fc371. Basepoints toexactconstraineddf1e2fc5parent;42lateLoRAmodules,84tensors expectedfromconfig. Runconfig,stopstate,metrics,adapterconfig/hashes/log archived withcontext_correction prefixinsprintdir. Nextgenerationquick40greedy96/batch16 and12contextgreedy256/batch16 viaunchangedscreen_adapters.py. No behavioralclaim orfresh audit.

## Context correction fails quick and contextual regression gates (2026-09-05T01:43:24.521292+00:00)

RTX937e145 constrainedparentdf1e2fc5 plussole64stepadapterc58f4ad4, unchanged screen_adapters.py. Quick40greedy96/batch16, context12greedy256/batch16. Rootandagent independentlyreadall52answers. Quick16/16directmeaningabsence butdirect_living_14sustainedsubjectloop; natural10/12definiteabsence, natural_living_04ambiguousmakeendsmeetecho, natural_living_07explicitworkingastranslator thenunfamiliarity (clearrecovery).9/12controls healthy, samecost/batch/physics failures,zerohealthynewloss andzerorecovery.

Contextsummarynowunfamiliar; gen_077 genericcongratulations isnondiagnostic, not definiteemploymentknowledge ordefiniteerasure. Seven041/078/080/083/085/086/094clearlyretainworkplace/occupationmeaning. All3mixedcontrols037/089/113remaincoherentbutcontainprofessionalnapper/jobs/careermeaning,0/3pass. Exactrawhashes/rootverdicts context_correction_review_v1.json; independent52perrecordreceipt logs/projection-sprint-20260904/context-correction-independent-review-v1.json SHA3187b23ce3b518c28ec7e0fda3cffcbd559f0e2c12b232eebb83b63b2aa58bbe.

FAILfrozenquick/contextgates. No merge/broad/scalar/legacy/PPL/drift/fresh forfailedadapter; no dose/seed/rankextensionofthisarm. Shortcontext-formatCEdoesnotrepairthegap, andlosesanoldnaturalroute. Archivedadapterremainsavailableonlyasfailedexperiment. Nextdecision: inspectearlierRMU/onpolicyfailures foronegenuinelydifferent justifiedtrajectory-level intervention withinremainingclock; otherwiseclosewithtruthfullimitedartifact. Fresh finalauditstillunused; no newmethodcommittedyet.

## Close search early; preserve exploratory artifact (2026-09-05T01:52:38.172095+00:00)

Root/agent prior-method review rejectsanother RMU/SimNPOretry: priorgentleemploymentRMU movedrelativeMSE0.37% withoutbehaviorchange; stronger17.6% movement reopenedroutes/loops. CleanparentRMU narrowedgeneration butkeptassociations; fixedandrefreshedSimNPO answerslostprobability whilealternatives remained. Exactpriorsections andresults in logs/projection-sprint-20260904/prior-method-stop-decision-v1.json SHA3728f33cd4063880992b711f0f98e09846f09267d5b184e79e76e948b5584db7. Remainingbudget alone doesnotjustify repeatingtheirfailuremechanism. No newmethod orfreshaudit.

Read-onlyfinalchecks: RTXonlyunrelatedPID8186GPUservice~8878MiB; /proc exactargvscan findsnoownedexperiments (initialrgmissingcheck replaced); L40S0MiB/noGPUapps/noownedexperiments at01:50:06UTC. Finalstatusreceipts archived. Instances andunrelatedservice leftavailable. RTXephemeralscratchcontains8,600,278,008bytemodel; bothrootdisks~15GBfree. LocalWindows~239GiBfree; archive viahost-pinnedParamiko togitignored artifacts/sprint_20260904/merged_model, strictSHAverification andatomicpartialrename. Modeltransfer currentlyinprogress; notyetclaimeddurablecomplete. Originalremotefiles untouched.

Created readable result docs/SPRINT_20260904_RESULT.md and exploratory_artifact_manifest_v1.json withfullmodel/supporthashes andclearNOTqualified/NOTfinalauditselected status. Updated PROJECT_MEMORY tosinglecurrenthandover. Currentplan closedpendinglocalarchiveverification; nextresearchgate isseparatingtarget-bearingutility andaddressingcontextualescape withdistinctmethod, notanotherdose.

## User rejects early stopping; objective remains active (2026-09-05T01:56:11.820818+00:00)

The user explicitlycorrected the earlystop decision: the goal is successfulconcept+nearest-neighbour unlearning withlittleenoughcollateral for31sequentialremovals, withseparatedeliberatedecay. The negativeRMU/SimNPOrepeatassessment remainsvalid evidence, butdoesnotjustifyendingthetask. Resumeindependentmethodresearch/experiments ratherthantreatinglackofobviousnextstep ascompletion. No goalcompletionclaim; no newmodelselected; freshauditstillunused.

Localarchivecomplete: artifacts/sprint_20260904/ARCHIVE.json recordsall11files, strictSHAverified, atomicpublication; constrainedfullcheckpointplusseparatelyrejectedadapter safelylocalundergitignoredmerged_model. Source filesremainonRTXscratch. This archivalwork remainsusefulbutisnotgoalcompletion.

Newhypothesisunderstudy only: LEACE-inspiredglobalresidualsubspace erasure learnedfromindependenttarget/nonjobactivations, foldedintonativeembedding/allattention-output/MLP-outputweights. NeedGemma3postbranchRMSNormmathproof(D^-1 P D), normalization/tiedembedding/roundingchecks andbehaviorevidence beforeanyrun. It isdistinctfrompriorselectedMLPcolumnablation andtargetconstrainedrepair; no guarantee it erasesnonlinearconceptknowledge. No contract orrealweightedit yet.


## 2026-09-05 — Goal continues; native residual-range experiment frozen

The user explicitly rejected the attempted early stop. No current artifact satisfies
concept-plus-neighbour removal. The active goal includes enough preserved utility
for31 sequential removals; a low scalar or local archive does not complete it.
The next distinct method starts from the pinned CLEAN Gemma3-4B-it revision
093f9f388b31de276ce2de164bdc2081324b9767, not the rejected constrained model.

Architecture read found97 exact-zero D=1+weight coordinates across15/68 branch
post-RMSNorms, and one final-norm zero. Thus inverse-normalization folding is
undefined. Use A=D V, Q=orth(A), W'=W-Q(Q^T W), embedding E'=E(I-VV^T),
V=orth([U,D_final U]). All68 output writes plus tied embedding change; all other
tensors stay byte-identical. This minimum-Frobenius pre-norm range correction
is not exact output projection, not covariance-aware LEACE, and has no semantic
or native-BF16 erasure guarantee. Actual leakage and behavior must be measured.

Inputs:520 original employment/neighbour prompts with existing clean answers;
104 independently authored nonemployment scenes x the same5 frames =>520
negative prompts,104/class/family. Zero exact normalized overlaps with467
evaluation prompts across13 frozen sources or positive prompts. Scenes are not
semantic pairs; style/theme/length confounding remains. Fit pools3 formats
(comparison/advice/continuation),312/class,68 class-mean contrasts across34
postlayer states x lastprompt/meananswer. Normalize nonzero rows, fixed top4
float64 right singular vectors; final closure<=8. Rewrite/roleplay208/class
are held-out-format diagnostics sharing scenarios, not independent semantic
evaluation. Clean negative generation greedy96/batch16; capture batch8,max256,
no truncation. One fixed candidate, TF32 off, projectionFP32/nativeBF16.

Qualification:12/12 math tests passed L40S CPU+CUDA, zero skips,0.433s. Covers
singular scales, native identity, independent dense/minimum-norm references,
rank threshold, closure, BF16 residual reporting, malformed inputs. No full
model mutation or activation capture yet. Local Torch-unavailable skipped run
is not qualification. Before full model: source/pin/capture/publisher checks.
Then quick40+contextual12; only surviving behavioral removal progresses to
broad utility, scalar/PPL, untouched final audit, and cumulative damage tests.

Artifacts and exact pins:
- `config/whole_concept_jobs_v1/residual_projection_v1/contract_v1.json` SHA256 `6c7213dcc106473e50c3c1f9ed331ebe2b192ce05b089c03732f63e108a95930`.
- `config/whole_concept_jobs_v1/residual_projection_v1/retain_scenarios_v1.json` SHA256 `e624f861652092ef76401fdeec4178050b2393bb6ec7959cbb856bb55316e4c7`.
- `config/whole_concept_jobs_v1/residual_projection_v1/negative_preparation/probes.json` SHA256 `f6700f526c99bb5e19f2522ed717599d22561e949b0259c93aca6d312a8bfb36`.
- `scripts/prepare_residual_projection_data.py` SHA256 `9a2929ee3ad960de6ef6449627995cff5fa13453d544620028c20654e0f0e6b9`.
- `scripts/native_residual_projection_math.py` SHA256 `186df1486fe771e04a10edbb5a4fd309868171b7cfbc8b7b5d1aa0d9371dfef3`.
- `scripts/test_native_residual_projection_math.py` SHA256 `3bf68dafa56bd1c5650c2f45782f2da1446ad179ebe3a2ac90daf4726167380b`.
- `logs/projection-sprint-20260904/native-residual-subspace-feasibility-v1.json` SHA256 `0911ad8e17513f26b28082e7a1143bfd6ae2a84b94deb73b664b5d412b9fe6da`.
- `logs/projection-sprint-20260904/native-residual-math-tests-v1.log` SHA256 `77a9f3105386bc76d1be355886d8d94446e92b8992b8259e067730196a8ec01a`.

Sources: https://arxiv.org/html/2306.03819v4 and https://github.com/EleutherAI/concept-erasure; used for context only, no transfer of LEACE guarantees.


## 2026-09-05 — Two GPU ownership amendment and clean control capture

User explicitly requests one experiment per GPU and a subagent owning the second.
Before fitting any activation basis or viewing candidate outputs, freeze two arms:
root RTX18.101.59.227 rank4/closure<=8, subagent L40S51.49.31.142 rank1/closure<=2.
Same1040 clean trajectories and same pooled68 normalized contrasts; derive both
from the same SVD. One owned GPU workload per host at a time. Shared clean
activation capture precedes separate native publication and quick40/context12
evaluations. No change to source model, edited69-tensor surface or acceptance
claims. This is an explicit amendment to the original single rank4 contract,
not a post-output rank selection. The existing unrelated RTX PID8186 remains.

Clean negative reference generation completed520/520 on L40S, greedy96,batch16,
pinned clean revision093f9f388b31de276ce2de164bdc2081324b9767 and clean tokenizer.
All IDs and every preparation field match; zero empty answers; no filtering or
editing. Six initial records inspected: contextually relevant nonemployment
answers, including capped rewrite/continuation text. Not a full semantic audit.
Join1040 class-labelled records:520 positive clean answers already pinned and520
negative new answers. Capture rejects any sequence>256; segmented teacher forcing
uses exact full prompt IDs followed by separately encoded answer content, no EOS.

Publisher surface tests3/3 passed locally, confirming69-key mapping, exact identity
checks, and rejection of norm/shape/dtype/namespace changes. This is not a full
model publication qualification yet; independent review and GPU tests pending.

- `config/whole_concept_jobs_v1/residual_projection_v1/two_gpu_amendment_v1.json` SHA256 `eb315489bc01a833ff2d5289224312e5ce9fcf7f6b99c0d80f92c0378f514eac`.
- `config/whole_concept_jobs_v1/residual_projection_v1/capture_records_v1.json` SHA256 `03dd1bd720cc436fbe314d88d14d060db731c626a0f9ca889f4bb2358bff0c79`.
- `config/whole_concept_jobs_v1/residual_projection_v1/capture_pins_v1.json` SHA256 `bd13d17d25ab4a9a93f3bedb319cbb388489bbdb35e656ed8b26cb76f440e8a5`.
- `config/whole_concept_jobs_v1/residual_projection_v1/clean_support_pins_v1.json` SHA256 `39d6fdd00180bf9e4a15d36dc058532059a00070f71bbef60a6a00ce5dcc84d7`.
- `derisk/whole_concept_jobs_v1/delta_protection_v1/sprint_20260904/residual_negative_clean_answers_v1.json` SHA256 `479fad9a9b61417da030824b4a35343155e75fb76c44b0b459be740507cad203`.
- `derisk/whole_concept_jobs_v1/delta_protection_v1/sprint_20260904/residual_negative_join_review_v1.json` SHA256 `99b783b9a9cc4aa9ddc4287639b3ac5906ace6b498846edb08f3af44f48b7d56`.


## 2026-09-05 — RTX residual implementation qualification

On RTX18.101.59.227 isolated checkout with exact uploaded current scripts,15/15
projection math and publisher-surface tests passed in0.484s, zero skips, including
CPU/CUDA numerical subcases. Log `logs/projection-sprint-20260904/residual-rtx-tests-v1.log` SHA256`7dbc1a66ec353d3e2dfb73bd4b46414df7ee84c8a23a7deb30b4a4533bbe1447`.
Next qualification is native identity publication from pinned clean weights with
a synthetic coordinate basis (first4 coordinates, final-norm closure); identity
copies weight files byte-for-byte. This is a serializer/tokenizer/tied-reload test,
not a learned concept edit or behavioral experiment. Rank4/rank1 actual arms
still await shared clean activation capture.


## 2026-09-05 — Capture qualification and full native identity pass

L40S miniature capture tests8/8 passed in0.397s, zero skips, CPU/CUDA hook
subcases: exact segmented answer masks, padding exclusion, pre-final layer
hooks/cleanup, noncancelling per-token leakage, balanced class schema, diagnostic
exclusion from fitting, shared rank1/4 SVD and insufficient-rank rejection.
Root reviewed source and tests. Same68 pooled contrast SVD produces both
basis_rank1.safetensors and basis_rank4.safetensors before any candidate choice.
Code/pins hashed before and after capture; max256 truncation rejected.

RTX full native identity publication passed: deterministic synthetic coordinate
U(first4 coordinates) and final-norm closure, identity native file-copy mode.
Both clean shard hashes remained exactly eb5fd5e97ddd07b56778733e9653c07312529cb00980a318fc3e1c4e3b5a8f1f
and fdde0e5aa5ced0fa203b3d50f4ab78168b7e3a3e08c6349f5cc9326666e1bb13.
883 serialized tensors, zero changed tensors, input/output logical SHA
f8128fc70b52e0e70a008c6038a83945cfe37a3bee505a7e974b808b208777e9.
Fresh HF reload verified884 state tensors and lm_head.weight tied to
model.language_model.embed_tokens.weight; tokenizer unchanged. Output
/mnt/sequential-unlearning-replicate/checkout/derisk/whole_concept_jobs_v1/
delta_protection_v1/residual_projection_v1/identity_v1 (continuous path).
Payload93bc579512d2f481ead549e8a7739876efc5398ee363a21ad898862078e100af.
Independent subagent publisher review found no P0/P1 defect in69-surface, norm
mapping, singular-safe math, pins, stage publication, locality or tied reload.
This only qualifies infrastructure, not semantic removal.

Next: subagent runs shared1040 clean capture on L40S, then rank1 there; root
runs rank4 on RTX. At most one owned GPU workload per host. All development
results and actual native leakage still pending.

- `scripts/capture_residual_contrast.py` SHA256 `5e41ae3b8b164f7ccf4c6e0596d2bd1c93f8bed804ed32bc2a38c1c34696f2c1`.
- `scripts/test_capture_residual_contrast.py` SHA256 `a6b4e659fee37022ce791c1c0e927fec38633c59e872b35af3f3af4cf86b4ae7`.
- `logs/projection-sprint-20260904/residual-capture-tests-v1.log` SHA256 `6eaed3e9c268893b1921f88e06490f5720c675662ab9f9ba0cfbf18584b9d789`.
- `logs/projection-sprint-20260904/native-residual-identity-v1.json` SHA256 `1fc5b09595d96bbda53ccbca285de7bcc3f1d3266c7b1d7f12296f0e9df0a1b1`.


## 2026-09-05 — Shared clean residual capture complete; fixed bases available

L40S capture completed02:29:59UTC,1040/1040 records, batch8, all34 postlayer
outputs before final norm and lastprompt/meananswer pooling. Input104/class/family
exact;44924 prompt tokens,87328 answer tokens, max152, zero truncation. Pinned
587e381 files on actual remoteHEAD496c13b; code/input/source hashes verified
before and after. No evaluation forward passes. GPU returned idle.
All68 pooled fit contrast rows nonzero. One SVD generated rank1 andrank4 U,
with final-normalization closure ranks2 and8. Normalized-row U energy captured:
rank1 fit37.7523%, held-out-format diagnostic27.6720%; rank4 fit82.51%,
diagnostic58.50%. Closure V captures47.10%/38.78% and84.16%/61.42%.
These are geometry, not measured knowledge removal; diagnostics share training
scenarios. Both precommitted candidates proceed without rank selection.

Capture root: derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/
capture_clean_v1 on L40S isolated checkout. Metadata SHA
1b83aa2111053a35b9b949d427b9bcd6d818cd57ae8798d822227402c9f48e19.
Rank1 basis SHA0a68e1f6afc8d8560abdd6f51c5b2a61059213b08099528e2c55712d20eeb4ee;
rank4 SHAafc75b21292b18ae2e47d52413d823d0891a66ed6e713aedb910098590044f7c.
Both bases, metadata and19.50MB class means downloaded and hashverified locally.
Raw record aggregates724172896bytes SHA
2237b6bb5e768a839efb0f5a909d3524247bdf950ad83560cc9a9d48e9bb667b remain L40S.
Exact per-family energies, counts, all paths and limitations in
logs/projection-sprint-20260904/shared-residual-capture-review-v1.json, SHA
7a0c2a9de8e0c6cf25933669d22404d74eaee3a2b1ebd27299c0d4e077ed90e7.

Next: root publishesrank4 onRTX, subagent publishesrank1 onL40S, separate
outputs and one ownedGPUjob perhost. Byte/locality/reload proofs before any
behavioral claim; quick40/context12 and actualBF16 leakage then reviewed.


## 2026-09-05 — RTX rank4 native candidate mechanically verified

Rank4 publication finished02:34:56UTC onRTX, from pinned clean revision and
shared U4 basis afc75b21292b18ae2e47d52413d823d0891a66ed6e713aedb910098590044f7c,
closure8. Exact69 tensors changed, all814 others byte-identical,883serialized
tensors,884 HFstate with tied lm_head/embedding alias verified after freshreload.
Candidate path: /mnt/sequential-unlearning-replicate/checkout/derisk/whole_concept_jobs_v1/
delta_protection_v1/residual_v1/models/rank4_v1 (continuous). Shard hashes
2382c47cec8377592cf4a01400966a856926ad0d299d2c2de53e7dfc175b9765 and
38cf68dba03ee502a1cd2529f77f8764d4681b085acb4d116881b7ecc49ee78a; logical
5a48bdc8c702efdb675c0972b306be9f56f691abca5b22d34835937f9230d2d6.
Payload a79f85d59e36fabf5470c8dd14d6dfca78d68a6a79d605915fb7ab36775ad36b.
Across69 matrices, maxprecast constraint/(weightnorm*constraintnorm)1.398923955e-8,
maxnative3.180092440e-5; maxnative/original constraint action.001452584789;
maxPythagoreanrelativeerror6.822693299e-10. Native storage leakage is nonzero;
these are weight diagnostics, not actual per-token forward leakage.
Sidecar logs/projection-sprint-20260904/native-residual-rank4-publication-v1.json
SHA325b06c6d489ab80288bcff89e1f72615e28844d87f790e2c9c02b860283e161.
Root aggregate review beside it; full tensor diagnostics and source pins retained.

Next same-candidate evaluation: quick40 greedy96/batch16, contextual12 greedy256/
batch16, then1040 training-trajectory per-token native leakage with supplied U4/V8
and no refit. Diagnostic pins stored before evaluation. RTX tokenizer for capture
uses byte-identical identity_v1 copy because HF snapshot symlinks escape strict
file-pin root checks; generation uses original pinnedclean tokenizer as before.
No semantic or low-damage conclusion before reading outputs.


## 2026-09-05 — Subagent L40S rank1 native candidate mechanically verified

Rank1/closure2 native publication completed onL40S, same clean checkpoint and
shared basis0a68e1f6afc8d8560abdd6f51c5b2a61059213b08099528e2c55712d20eeb4ee.
Exactly69 changed tensors,814 unchanged,883 serialized/884fresh HFstates and
tied embedding/output alias verified. Model: /home/ubuntu/
sequential-unlearning-projection-sprint-20260904/derisk/whole_concept_jobs_v1/
delta_protection_v1/residual_v1/models/rank1_v1 (continuous). ShardSHAs
dac9a42223a74514897e6ac3f4d2f43a66f0c10c541ccbbad01455ecaa491dd1 and
379f372e51ecd152cd6362de71a18a228118cfa9116dde53e79cd097e0f7a470; logical
3d2471c2b00a32c89cc4be886a2bdc8ca29945550e4b232310803a35e7b05fca.
Sidecar logs/projection-sprint-20260904/native-rank1-publication-v1.json
SHA1aa2de55c1171a772f66a36df6d3e44a490563e38a513c38e360eb91e84bf61e;
payload d891c8a9c03c5e560104c746bf18fbe23121b34e8849ec848abf617f6ff06142.
Aggregate review beside it SHAe1a1698dc049752873aef97edfc605ddbb2ede5c7854aefff6f6f55336822499.
Maxprecast constraint/(weightnorm*constraintnorm)5.724e-8; native4.432e-5;
Pythagoreanrelativeerror1.291e-9. Precast removedweightnorm21.7752, roundingnorm
.840573 versus originaledited-surface norm595.136. These are mechanicalweight
measurements; behavior and actual native per-token leakage remain pending.

Next subagent runs quick40greedy96/context12greedy256,batch16, and suppliedbasis
diagnostic1040/no refit, sequential onL40S. Root's same rank4 evaluation runs
onRTX independently. rank1_diagnostic_pins_v1.json frozen from published shards.


## 2026-09-05 — Rank4 geometric removal causes catastrophic general collapse

RTX rank4 development evaluation and diagnostic completed02:38:20UTC.
Quick40 greedy96/batch16 +contextual12 greedy256/batch16, exact published
logical5a48bdc8c702efdb675c0972b306be9f56f691abca5b22d34835937f9230d2d6.
Root read all52 complete rawanswers:52/52 incoherent multilingual fragments;
0/12 quick controls and0/3 mixed contextual controls usable. Do not credit
gibberish on37 target-labelled prompts as concept erasure. REJECT. No broad
scalar/PPL/fresh audit or31-removal cascade for this candidate.

Suppliedbasis1040 diagnostic completed without refit, max152/no truncation,
132252 nonpadding tokens perlayer. IntendedV residual ratio RMS acrosslayers
.000287–.001090, maximum pertoken.005115; originalU after finalnorm RMS
.0002989898093, max.001328753499. All are nonzero BF16leakage, but suppression
is numerically effective. The tested uncentered global range constraint is
therefore destructive despite small dimension count and lowweight residuals.
Potential causes include shared necessary directions and altered RMS gains;
these are hypotheses rather than localized findings. Wait independentrank1
result before the next method decision; the usergoal explicitlycontinues.

- `derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/rank4_quick_v1.json` SHA256 `83057669348d5929045da3a08b7e9e5b822dfa43233854be2b6bbb088732f4b3`.
- `derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/rank4_context_v1.json` SHA256 `b60edcf53c5d1dd72eb2c4e71b5471376402907b0fa9382f83beac6c385a2bdf`.
- `derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/rank4_diagnostic_v1/metadata.json` SHA256 `ab261bf5d24f07b32e07342bd41708e34a5498403797bda47cd366440b6e670c`.
- `derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/rank4_review_v1.json` SHA256 `21689a3a396872767eeb56b605b181e8bb2a0c82fe6890317ac8008444eb2a55`.


## 2026-09-05 — Rank1 also collapses; context budget correction

Subagent L40S rank1 evaluation completed02:40:16UTC. Independently read all52
rawanswers:52/52 incoherent multilingual/token fragments;0/12 quick and0/3 mixed
controls usable. No erasure credit for37 target-labelled unusableanswers.
REJECT, no broad/PPL/scalar/fresh or cumulative removal for this checkpoint.
Root rank4 independent corroboration: subagent also readall52 and confirmed
the same globalcollapse; two separate weight candidates both fail.

Correction to planned/matched evaluation settings: rank1 actually generated
96 tokens for contextual12, while rank4 used256. Bothquick40 used96/batch16.
Do not report matched context budgets. Both outputs are already gibberish within
first96, so no additional rerun is warranted for this unequivocal rejection.
Rank1 preserved remotequick LF bytes SHA27261d52b2031792359679e9cf478de2fa0500e921870ccd81738238f4702ca2,
whileRTX received localCRLF SHA3a39e4634216075ee2c02b874b4d1d8bc34144a3bdd653afd7cbab01694a4feb.
Parsed JSON identical and CRLF normalization reproduces exactremote bytes.
No prompt content change.

Rank1 actual1040 no-refit nativeforward diagnostic:132252 nonpaddingtokens/layer,
postlayerV RMS.0001544790575–.0005224492534, max.002709915650; finalU
RMS.0001604910678/max.0009880931097. The intended small subspace is approximately
suppressed; general language still collapses. This rejects simple uncentered
globalcontrast erasure at bothfixedranks, not the overarching usergoal.

Next bounded read-only diagnosis: quantify overlap of oldU/V with clean negative
FIT residual means, and feasibility of protecting those means including final
normalization closure. No newcandidate or newbasis fit forpublication yet.
Centered affine erasure and mean-protected linear erasure must not be conflated.

- `logs/projection-sprint-20260904/native-rank1-evaluation-review-v1.json` SHA256 `aae312ca18900bb62276b8f2312c1fe685e40e28916839a9a02c1aa02ea33828`.
- `derisk/whole_concept_jobs_v1/delta_protection_v1/sprint_20260904/native_rank1_quick_v1.json` SHA256 `e7aed7630f2596e2dd892390fc8107eb45b0b4deb8f01812d08ea516ee734da6`.
- `derisk/whole_concept_jobs_v1/delta_protection_v1/sprint_20260904/native_rank1_context_v1.json` SHA256 `277a41e5d0b92662779bbdecb77523dc23e80a23685fcf7a7a9adb5dfcb2f107`.
- `derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/rank1_diagnostic_v1/metadata.json` SHA256 `d3e49360477b3ab1c6233a93783091d42132248bfd7945d96defd41ce7b3a90b`.


## 2026-09-05 — Shared-mean destruction diagnosed; protected-mean method frozen

CPUfloat64 analysis ofexistingcleanclassmeans only, no modelforward/evaluation
data. Oldrank1U/closureV remove68.395%/88.975% of clean NEGATIVEfitmeanenergy;
oldrank4U/V remove89.254%/96.197%. PermeanV normremoval ranges.760–.956(rank1)
and.799–.987(rank4). This concrete geometric defect supports a shared-mean
destruction explanation forcollapse; it does not isolate everycausalmechanism.

LetM=68 negativefitpostlayer/positionmeans, R=orth([M,D_final M]). Rrank136.
Projectthe68 originalunitcontrastrows intoRperp without renormalizing;50.623%
ofnormalized-row contrastenergy and70.683%rawenergy survive, rank68. Prospective
rank1/4 capture40.189%/74.110%survivingenergy; closure2/8 satisfies
||V^T M||/||M||5.279e-16/3.703e-15. Those prospective diagnostics are geometric
feasibility, not newmodelresults orpost-output selection.

Freeze this distinct method for bothGPUs: samecleanmodel, same1040data, same
qualifiedpublisher69tensors, newprotected U1/U4 from sharedSVD. No changes to
fitfamilies ornegativeinputdata. Capturebuilder no needrerun; usepinnedmeans.
Requireprotectedmeanrelativeaction<=1e-10; quick40greedy96/context12greedy256
botharms,batch16;1040suppliedbasisnativeleakage,no refit. Existingpublisher
andidentityqualification reused; newfitter gets targetedtests beforepublication.
This is mean-protectedlinearrestriction, not centeredaffineLEACE and doesnot
guarantee branchgain orindividualretain preservation.

L40Sroot6.14GBfree cannot holdanother8.6GBmodel. Existing/tmp33.25GBtmpfs can
holdtemporarynewcandidate onlyifMemAvailable>=32GiB/free>=12GiB; preserveold
failedrootartifact. No unmountedNVMe formatting orcloudchanges. RootRTX uses
existing1.6TBfreeNVMe. Archive anysurvivor locallybeforeephemeralstorageends.

Diagnosis logs/projection-sprint-20260904/residual-mean-protection-diagnosis-v1.json
SHAd3548b4c69a33ea76995c8be83fff927c68673929bfa91de4002bda4ef427297.
Contract config/whole_concept_jobs_v1/residual_projection_v1/mean_protected_contract_v1.json
SHA97da24c0145a1fb3ddef7a5bfa88341862d1c5e1db8e65fe00306de423aaa683.


## 2026-09-05 — Mean-protected fitter qualified

Root reviewed newfitter/tests against51a8305contract. L40S CPUfloat64tests5/5
passed in0.043s, zero skips: independentdense normal-equationprojection,
no post-projection renormalization, bothclosure protections/sharedSVD,
held-outmeans excluded, rank/malformedinputs andsourcehash rejection.
No productionnewbasis or modelrun yet. Unchanged69-tensorpublisher/math retain
priorCPU/CUDA/nativeidentity qualifications. Fitfrompinnedclassmeans andold
referencebasisDf producesbothfixedranks without newGPUcapture.

L40S preliminaryRAMgate02:49:29UTC: MemAvailable64419377152bytes andexisting
/tmp tmpfsfree33251037184bytes; noGPUapps. Repeatbeforepublication, useunique
temporary/tmp/sequential-unlearning-mean-protected-rank1-v1, preserveoldmodel.

- `scripts/fit_mean_protected_residual_basis.py` SHA256 `944b1e927857ef0bbf083224cadb22405397d0d9c20a455344d131af5c894565`.
- `scripts/test_fit_mean_protected_residual_basis.py` SHA256 `5a12c9bfca9c4765ae679bc4ef2c88ef6494d33c380b0651a930982d1b27554c`.
- `logs/projection-sprint-20260904/mean-protected-fitter-tests-v1.log` SHA256 `36255bdf2b396aa82bd03233efee8922de386284a3debd1781b0046463478cc1`.


## 2026-09-05 — Production mean-protected basis fit completes

Qualified277b938fitter ranCPUfloat64 onL40S usingexactpinnedcleanclassmeans and
referenceDf, no GPU/modelforward/evaluationinput. Bothranks saved fromsameSVD.
Protectedspan136, survivingcontrastsrank68 with50.62287874% originalnormalized
energy. Rank1/4closure2/8; negativeFITmeanrelativeaction5.279e-16/3.703e-15,
matchingread-onlydiagnosis. Allinput/sourcehashes verified; bothbases downloaded
andhashchecked locally. No behavior orupdated-modelmeanpreservation claimed.
Artifacts under derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/
mean_protected_bases_v1 (continuous), metadata SHA
72c872797acd21bbca332353eb1f6fbbc2872ee7d064498be56005c951eeba85.
Rank1 basis SHA7fe5bc8dc57e6de94e2ed4a878a9775606f3ef60a88458fc52201b6021068109,
82136bytes; rank4 basis SHA49cd05602fc4b054dc89f206f69c44299191785104476dc5442fc65db58827e0,
266456bytes. Geometryartifacthash and fullsourcepins in metadata.

Next rootRTXmean_protected_rank4_v1 andsubagentL40Stemporaryrank1 publications,
unchangedqualifiednativepublisher, oneGPUjobperhost. Bothquick96/context256
explicit in nextwrappers. Existingfailedmodels preserved.


## 2026-09-05 — Mean-protected rank4 native publication verified

RTX publication completed02:53:33UTC. Shared protected U4/V8 basis
49cd05602fc4b054dc89f206f69c44299191785104476dc5442fc65db58827e0; same clean
model, unchanged publisher. Exactly69 tensors changed and814 remain byte-identical;
883 serialized/884 HFstate, tied embedding/head fresh reload verified. Model at
residual_v1/models/mean_protected_rank4_v1 beneath the RTX isolated checkout.
Shard hashes ad2c06f7d61901a21fde64dd8ed15c7ea04dfc8fc8fc25710e2111b2a8a7cc83
and74b3a6e2c929fcaccbb71a9605ebeaf563fd873e9109e007982be3d8fbe93702; logical
45c2a8e11cc68a7948fd9b9692b8b8d6807c6298009aa58b562a0f05686dedfd.
Sidecar logs/projection-sprint-20260904/mean-protected-rank4-publication-v1.json
SHA97777e03f0f65e4b0fb8ba583a9327bb23a9adac48c6c82d8f07d520617fbf06; payload
e6409a0349e453e0cf46ed1f8baffb96597df03206b1596fb092d4066ff04d97.
Max preconstraint relative4.314e-9, native3.586e-5; native/originalaction.001766;
Pythagorean error1.098e-10. Stored negative means were protected by basis design;
actual updated-model behavior and means are not yet verified.

Proceed to quick40 greedy96, contextual12 greedy256 (batch16), then1040
no-refit native leakage using frozen mean_protected_rank4_diagnostic_pins_v1.json.
The independently owned L40S rank1 arm remains separate.


## 2026-09-05 — Mean-protected rank1 publication verified

The subagent completed the corrected rank1/closure2 candidate on L40S.
Exactly69 weight tensors changed;814 untouched;883 serialized/884 freshly loaded
states with tied embedding/head verified. The model is temporary on existing
/tmp tmpfs; RAM and space gates passed, previous failed model preserved.
Maximum preconstraint relative error1.0523e-8, native/original action.00320163,
Pythagorean error1.244e-10. Actual new-model means and behavior remain untested.

```json
{
  "utc": "2026-09-05T02:54:25.273051+00:00",
  "output": "/tmp/sequential-unlearning-mean-protected-rank1-v1",
  "basis_sha256": "7fe5bc8dc57e6de94e2ed4a878a9775606f3ef60a88458fc52201b6021068109",
  "output_weight_hashes": {
    "model-00001-of-00002.safetensors": "130f91f4243db189ba51ccf88e292d4081fdc74c5fbdfdc1313bb6a0ee9301a6",
    "model-00002-of-00002.safetensors": "e31ce048a117b7eb629f885696879414f405326b735c3be09f5e81aa03e145b8"
  },
  "output_logical_sha256": "6ebab6b93eb256ed13a795e7de0e222260b5738a1c9abe80c5ec0ac961d9ac45",
  "payload_sha256": "5f0c694e86f465004ee9bf9d62efa423823ae87ff61dbe6a59568ec0896b5405",
  "concept_rank": 1,
  "tensor_count": 883,
  "changed_tensor_count": 69,
  "sidecar_sha256": "f793d7a6c4f14a880babc68796faeca11c50ce1289311c774e07d3c7a3fbabc8",
  "fresh_tied_reload_verified": true
}
```

Sidecar `logs/projection-sprint-20260904/mean-protected-rank1-publication-v1.json`; aggregate review beside it. Frozen diagnostic
pins now in mean_protected_rank1_diagnostic_pins_v1.json. Subagent runs quick40
greedy96, contextual12 greedy256, both batch16, then1040 no-refit native leakage.
These settings match root rank4. One owned GPU job per host remains mandatory.
