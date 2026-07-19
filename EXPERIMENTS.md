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
- **Combined forget scope:** concatenate the 180 clean-base on-policy sea
  pairs from Run 7 with 180 clean-base on-policy neighbourhood pairs. The
  RMU trainer now consumes stored exact answer token IDs when available.
  With `batch_forget=4`, random sampling gives approximately the same number
  of sea examples per 30-step run as Run 9 while adding an equal neighbour
  dose.
- **Unchanged instrument:** clean Gemma parent, blocks 16/20/24, adaptive
  per-token target norms, rank-32 LoRA over blocks 14-24, retain weight 100,
  lr 1e-4, exactly 30 optimizer steps, snapshot every 5. Only forget-set
  semantic scope and forget batch size change.
- **Selection:** evaluate steps 20 and 30, adding step 25 if step 20 is
  partial and step 30 overshoots. All existing target, neighbour, generation,
  control and PPL gates remain unchanged.
- **Eval:** pending on generation of the frozen neighbour answers.
