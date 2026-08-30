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
