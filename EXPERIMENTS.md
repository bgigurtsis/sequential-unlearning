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
