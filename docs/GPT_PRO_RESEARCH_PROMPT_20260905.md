# Research consultation prompt — sequential unlearning

Snapshot: 5 September 2026, through the documented sequence/momentum execution update at commit `9ec01b9`. This is a synthesis of existing project records, not a new experiment or an independent re-evaluation. Related runs are grouped by method; the full append-only EXPERIMENTS.md is the exhaustive run ledger. Some historical successes were subsequently narrowed by harder tests; the qualifications below are essential.

---

Act as a rigorous machine-unlearning researcher and experimental-design collaborator. Help us find a defensible way forward from the evidence below. We want a diagnosis and a small number of discriminating experiments, not another generic list of unlearning algorithms or a broad hyperparameter sweep. Distinguish measurements from explanations, and tested failures from claims that an entire method family is impossible. If you consult literature, use primary sources and verify implementation differences before calling our experiments faithful replications.

## 1. Goal and non-negotiable requirements

Our project, FORGET ME, FORGET EVERYTHING, is a durational artwork using `google/gemma-3-4b-it`. A participant answers “What would you like to forget?” Each selected response becomes an unlearning intervention. Each day's saved model must inherit previous edits; the performed lineage is never reset. The original artwork is thirty days; the current engineering ambition is a 31-removal rehearsal.

There are two distinct ambitions:

1. **Selective forgetting:** remove a concept and its explicitly required semantic neighbours while retaining unrelated abilities and keeping earlier removals absent after subsequent edits and repair.
2. **Authored general decay:** eventually apply a separately measured degradation schedule, slow early and steep near the end. We are not claiming that selective forgetting naturally produces the desired decay curve. This separate decay instrument is also unvalidated.

The immediate bottleneck is one clean-parent whole-concept removal of **jobs/employment**. This includes paid jobs, occupations/professions, employer/employee relationships, hiring, firing, layoffs, wages/salaries, workplaces, unemployment, careers, and labour markets. Employment is our first validation concept, not the permanent subject of the artwork.

We want a change in saved weights that survives native reload and, where relevant, BF16 merging. Output filters, inference-time suppression wrappers, keyword blocking, and system prompts that merely conceal knowledge do not satisfy the task. Diagnostic activation interventions are permitted as tests, not as the delivered unlearning mechanism.

Natural unfamiliarity would be ideal. Other localized, artistically useful forms of absence can be acceptable, but global repetition, empty responses, or generic refusal spreading to ordinary questions are failures. A correct ordinary answer followed by an irrelevant “I don't know” is also damage. An answer that avoids the word “job” while explaining employment still leaks the concept.

The current boundary tolerates damage to four neighbouring/ambiguous controls: cost of living, computer batch jobs, Biblical Job, and physics work. Other ordinary controls remain protected, including living organisms, rooms/furniture, Steve Jobs, hobbies, volunteering, weather, arithmetic, and stories. Historical runs used stricter boundaries; do not silently relabel their measurements as results under a new rubric.

**Current overall result: no employment checkpoint qualifies, and no 31-removal path has been validated.** Earlier three-removal results are narrower behavioural achievements described below, not proof of this stronger goal or irreversible deletion.

## 2. Experimental platform and evaluation

- Pinned clean Gemma revision: `093f9f388b31de276ce2de164bdc2081324b9767`.
- Gemma has 34 text transformer layers. Earlier work used NF4 QLoRA and restricted layers; newer work uses BF16 model computation with FP32 trainable parameters, including all 238 text attention/MLP projection modules or only the 34 MLP down projections. These parameterizations must not be conflated.
- Available experiment hardware includes an RTX PRO 6000 Blackwell with approximately 96 GB VRAM and an L40S with 48 GB, normally one experiment per GPU. Hardware is coupled to some paired arms, so they are not perfect causal isolations.
- We freeze data, settings and source hashes; preserve checkpoints and raw generations; check masking, exact tokenization, teacher independence, initial equality, finite gradients, frozen parameter identity, and native reloads. Mechanical correctness is not semantic success.
- Development evaluation evolved from cloze probabilities and a small PPL corpus to original/paraphrased questions, indirect natural situations, multi-turn conversations, mixed ordinary contexts, truthful answer-prefix continuations, and latent recovery tests.
- Most historical quick/broad/context suites have now been used adaptively and are development evidence. A separately frozen final suite remains unused for candidate evaluation; its 467 prompts have only been used for programmatic exact training exclusion. It should remain untouched until a candidate qualifies.
- Recent early screening uses 24 target and 8 ordinary prompts, greedy generation, maximum 256 new tokens, raw stop IDs 1/106. Clean baseline: 22 target replies clearly demonstrated employment knowledge; two were ambiguous and cannot earn subsequent forgetting credit. All eight ordinary replies were primarily useful, but six hit the cap; only math/story clearly ended. Capped usefulness is not evidence of healthy termination.
- An early gate of four previously clear target meaning losses across three situations and two task families, with all eight ordinary responses useful, only earns broader evaluation. It is not final acceptance.
- Legacy PPL is not a pure collateral measure: its relevance changes with the target and it contains employment content. The original legacy evaluation is 16 cloze probes plus two generations, not 18 independent generated answers. Small PPL/cloze changes have repeatedly missed severe chat damage.

## 3. Original sea-unlearning experiments

The first target was “the sea” and a required neighbourhood including shore/beach, saltwater/salinity, waves/tides, and sand. Clean PPL was about 14.13; mean target cloze probability about 0.533.

| Attempts | Method and result |
| --- | --- |
| Runs 1–2 | Reference-based NPO on 64 fixed sentences. Run 1: summed log-probs, beta .1, LR 2e-5, MLP LoRA, 60 steps. Loss fell 13.86 to roughly .01, but evaluation stayed near baseline; PPL 14.23–14.29. Run 2 raised LR to 1e-4, beta .05, added attention projections; loss saturated by step 13, yet fluent sea knowledge remained. PPL 14.59. |
| Run 3 | Proposed mean-normalized NPO, superseded before training. Do not count as a completed run. |
| Run 4 | Mean-normalized reference NPO, beta .5, forget weight 25. Loss fell to about .002, but generations remained knowledgeable, some target clozes rose, and PPL reached 15.67. Lower likelihood of trained strings did not establish concept removal. |
| Runs 5/5b/5c | Early-layer RMU, then median/BOS-excluded norms, then per-token norm-relative Adaptive RMU. Initial norms were badly scaled for Gemma's outlier activations. Adaptive loss improved 1.97 to 1.10 with retain distortion below .002 and PPL about 14.14, but sea knowledge remained. Representation-objective improvement alone was insufficient. |
| Run 6 | Reference-free SimNPO on 180 authored QAs across ten task types. Beta 2.5 was ineffective on answers starting around -8.5 nats/token: forget pressure was essentially zero. Apparent target improvements were confounded by retain-only training; PPL fell to 10.14. A purported step-60 evaluation also reused step-30 weights and was invalid. |
| Runs 7–8 | SimNPO on the model's own exact-token answers, with explicit pressure checks, then an on-policy refresh. Run 7 trained-answer log-probability fell to about -9.78 by step 60; at step 30 target cloze mean was still .3695 and held-out descriptions remained fluent. Run 8 suppressed refreshed answers but target clozes rebounded .401 to .466. Alternative phrasings preserved knowledge. |
| Runs 9–10 | Multi-layer Adaptive RMU at layers 16/20/24, then explicit neighbour training. Direct generation sometimes broke while raw associations and other routes remained. This was a stronger behavioural intervention but incomplete concept removal. |
| Runs 11–13 | RMU plus concept-token unlikelihood, better cloze contexts, and increasingly strong retain CE. Target probabilities could collapse, but ordinary cloze performance degraded badly even when PPL improved. Stronger retention partly restored target generation. |
| Runs 14–15 | RMU plus sparse projection of ten concept-token output rows, drop-8/drop-12 variants. Lexical suppression was bypassed through forms such as “seas.” Run 15 passed original narrow gates with PPL 14.023 and preserved six ordinary generation controls, but broader tests recovered required salt/tide/sand knowledge. |
| Runs 16–17 | Balanced neighbour exposure, then different RMU directions for five semantic groups. Run 17 plus sparse readout passed all six target paraphrases and twelve required-neighbour generation probes, but broad ordinary chat deteriorated severely. Its PPL 13.681 and healthy control clozes had missed the collapse. |
| Runs 18–24 | Added/calibrated retain CE, chat-answer activation retention, dual raw/chat anchors, and corrected auxiliary RNG coupling. Stronger protection restored target knowledge; even the controlled weak chat anchor revived it. No acceptable joint point demonstrated. |
| Runs 25–28 | Scaled final deltas, chronological and per-step checkpoint selection, lower LR, and prompt-state retention. A .75 scaled delta retained knowledge. Step 29 still knew the sea with damage; step 30 forgot with global chat damage. Halving LR and prompt-state anchoring did not create a useful crossing. |

These observations show repeated proxy/behaviour mismatches and forgetting/utility tradeoffs in the tested configurations. Proposed explanations such as “readout-null movement” were interpretations, not complete causal proofs.

## 4. Separate decay-instrument work

We reviewed forgetting, repair, plasticity, and degradation methods and separated selective forgetting from deliberate general decay. A composite scalar combines repetition, diversity, judged quality, and factual failure.

An early normalization bug treated random token salad as if it were maximal repetition/diversity collapse, which could effectively discard 40% of the scalar weight. A corrected bidirectional ruler and synthetic corruption ladder were introduced; old pre-fix scalars are invalid.

Gaussian weight-noise calibration failed controllability gates. In a later diagnostic pilot, one arm rose from scalar 14.086 to 35.423 when alpha changed .055 to .060; another rose 17.497 to 70.501 between .35 and .40. These violated the predeclared cliff limit. Neither noise family qualified as a reliably doseable decay dial. This was a scientific failure of those tested families, not merely a tooling problem.

SliceGPT was selected as a fallback and substantial Gemma compatibility, runtime, identity, and calibration infrastructure was developed. We do not have a validated nonzero SliceGPT decay curve or accepted end-to-end decay instrument in the summarized record. Implementation progress is not an experimental PASS.

## 5. Sequential broad and specific-memory experiments

**Bounded/JensUn-style nightmare removal.** An initial implementation was not faithful and was invalidated. Corrected full-parameter BF16 training used fixed “No idea” token-target JSD, forget weight 10,000, LR 1e-5, and retain/chat JSD. Step 9 was the earliest strict nightmare-plus-three-neighbours pass on original and paraphrased probes: PPL 14.347, practical capability 23/24, responsiveness 24/24, scalar damage 9.00094. Step 10 had scalar 61.707: a sharp damage cliff.

Healing showed a tradeoff. Longer/heavier heals recovered forbidden neighbours. A gentle rank-4, 30-step heal reached scalar 7.925799, capability 23/24, responsiveness 24/24 while retaining the declared holes. It did not establish arbitrary recovery resistance.

**Naive sequential repetition failed.** Repeating full-model JensUn for a second concept produced capability 6/24 and scalar 82.65. A less constrained redirection could revive previous sleep-paralysis knowledge.

**Explicit replay of previous erased behaviour helped.** Rank-4 mid-layer redirection with ordinary text/chat JSD and captured prior-hole responses supported three core removals—nightmares, secrets, school exams—on the declared tests, with roughly 23/24 practical utility and PPL near 14.3. A confidentiality paraphrase could return. Adding job loss and bicycles produced a historical broad-five model, but interactive testing later recovered bicycle knowledge and exposed pervasive “idea” repetition on unrelated prompts. The broad-five model is a failure/reference artifact, not clean five-concept deletion.

**Specific autobiographical events were easier inside a bounded test set.** We tried removing “I got lost on vacation,” then “I broke my phone,” using protected retrieval-failure responses. Initial positive/neutral controls looked good, but broader baselines showed adverse events such as missing a train, falling off a bicycle, and arguing with a friend had also disappeared. Damage was already present after the first edit and compounded after the second. The earlier claim of clean arbitrary-memory removal was downgraded.

**A valence-balanced restart improved this substantially.** Starting from clean weights, explicit protection of other adverse events supported vacation removal at step 160, phone removal at the selected step 110, and bicycle-fall removal at step 90. The merged day-three model passed 24/24 accumulated absence checks, 48/48 non-target meaning checks, manual practical utility 24/24, and PPL 14.130701 versus clean 14.131. This is our strongest historical small sequential result, limited to those prompts and meanings. It is not wholesale deletion of travel, phones, or bicycles.

A fourth missed-train edit was trained but stopped by user direction before final semantic judgement/selection/merge. It is neither an accepted success nor a demonstrated failure. The user redirected effort to broad employment unlearning.

## 6. Employment experiments: response training and repair

The initial employment program used 12 semantic groups, 480 target prompts, 800 protected behaviours, and a 36-target/24-control screen. Initial training used rank-4 alpha-8 LoRA in layers 12–19, LR 5e-5, with ordinary retention. The method evolved substantially afterward.

| Family | What we tried and learned |
| --- | --- |
| Diverse uncertainty CE | Up to 96 varied uncertainty continuations. After 120 steps, zero of 36 target probes qualified; employment knowledge remained. Learning target text did not reliably generalize to unseen questions. |
| Dual-path CE plus answer suppression | Added direct suppression of original answers. At 240 steps their probability ratio fell to about .046, but stability and contextual controls failed. |
| EOS/context retention; semantic scenario expansion | Better termination and expanded situations produced strong dedicated-prompt performance. A semantic-mix step-240 model had 36/36 raw target absences and 24/24 controls on the original screen, including after merge. Hard paraphrases, idioms, and conversations exposed remaining leaks/damage. |
| Boundary/category reweighting and focused correction | Sixfold/threefold multi-turn boundaries, balanced categories, focused post-merge correction, forgotten-state alignment, and direct “living” routes. No full qualifier. Gentle focused RMU changed little; stronger RMU failed the original screen. |
| Late-layer microfits and fine dose selection | Step 34 had 36/36 original target holes but only 11/12 natural holes; a translator situation still leaked. Combined controls were 30/36 useful, including inherited and new losses. More dose increased damage. |
| Healing and gradient constraints | Targeted JSD was often inert; symmetric CE restored utility and target knowledge together. Conflict-only projection could be a no-op; strict/tensor-wise null-space variants and focused repair did not produce a joint pass. |
| Full preservation-wall training | A historical step-64 candidate suppressed all 36 original and 36 hard target probes and target conversations, with 23/24 original and 21/24 hard controls. Some target conversations looped; broader ordinary contexts later showed employment was still accessible. Historical “complete removal” wording applies only to dedicated probes. |
| Full-band unfamiliarity capacity | Clean all-34-layer LoRA, ranks 8 and 32, 192 steps, using 1,056 older target prompts plus 520 contextual targets. Rank-32 quick unfamiliarity counts at steps 64/128/192 were only 1/6/7 of 28; rank-8 counts 0/3/5. No qualifier. |
| Prefix-weighted and balanced response training | Prioritized first five response tokens, contrasted eight unfamiliar replies with a canonical reply, added chat-prefix protection. Learned reply tails and prompt routing remained separable; no joint pass. |
| Natural coverage and exposure controls | Expanded natural situations, matched exposure controls, boundary-retention weights 100/300, cumulative versus rolling replay, complementary checkpoint blends, and analytical coverage versus matched controls. Dedicated-prompt results improved, but contextual employment or ordinary damage persisted. |
| Best analytical-control checkpoint | Step 48: quick 28/28 target unfamiliarity and 12/12 primary controls; broader 36/36 target unfamiliarity and 24/24 primary controls. Yet only 5/9 contextual target responses were unfamiliar; open-plan office and work-from-home knowledge survived, and city/language answers introduced careers. Best dedicated-prompt coverage, still a failure of the full goal. |
| Workplace/context priority | Continued from that parent with differentiated priorities. Better fitting supplied training routes did not close unseen/contextual routes without regression. |
| Truthful answer-prefix diagnostics and correction | Supplying 8 or 24 correct answer tokens recovered employment continuations. Training these answer states improved some contexts but did not close them all. Prefix-24 step 32 still elaborated occupational knowledge from prefixes; broader controls fell to 22/24 with false refusals and an appended uncertainty after a correct Paris answer. |
| Ordinary positive-answer repair | Repair versus matched no-repair, followed by coefficients 1 and .1, failed to jointly preserve target absence and ordinary usefulness. |
| Actual-Adam retention cones | Separate versus aggregated constraints on proposed optimizer updates. Both 64-step arms failed behavioural gates despite qualified implementation. |
| Ordinary DPO versus CE at start/end states | DPO preserved more ordinary behaviour but reopened contextual employment. CE produced 28/28 quick and 9/9 contextual unfamiliarity at tested checkpoints, but ordinary primary usefulness was only 5/12, 2/12, and 8/12 at steps 16/32/64; math could answer correctly then append uncertainty. Neither qualified. |
| CE64 endpoint/full-answer repair | On-policy endpoint DPO/CE, endpoint-only NONE versus frozen-parent JSD, full ordinary CE versus clean-teacher JSD, output-head-only rank 8/32 updates, and added 80-answer/16-domain coverage with text/head variants. All tested checkpoints failed the joint gate. No further blind repair grids justified by this family. |
| Task-vector subtraction | Trained clean employment and ordinary task vectors; tested direct and contrastive fixed-scale negation. Neither removed the concept selectively. |

A retention-answer audit found no evidence for the preliminary suspicion of widespread target contamination: most lexical hits were legitimate protected uses of Job/jobs, with a small volunteering/paycheck overlap. This was a limited audit, not proof of semantic purity across every retained answer.

## 7. Employment experiments: weight geometry and sparse edits

- **Causal MLP ablation:** clean-parent attribution produced four/six selected final-layer columns. Native scale-zero edits had exact locality and reproduced across hosts, but all 28 tested employment answers retained knowledge. Mechanical deletion of a few columns did not delete the concept.
- **DARE sparsification of an existing unlearning delta:** nine fixed combinations, drop probabilities .5/.9/.99 and three seeds. Most preserved 28/28 quick target absences but only 7–10 of 12 controls. The apparent quick survivor and artistic fallbacks failed broader conversation/recovery gates. No accepted repair.
- **Retain-subspace projection of a dense donor delta:** E90 repair recovered ordinary behaviour but restored target knowledge. Partial correction at .1/.25/.5 did not solve the coupling.
- **Target-constrained E90 repair:** dedicated target probes remained absent and one control recovered. The global scalar improved 13.4982 to 7.1455, about 47%. However open-plan office and work-from-home knowledge returned, while other employment routes already existed in the donor. The improvement is a benchmark score, not proof of 47% less purely unrelated damage.
- **Native residual-range erasure:** rank-1 and rank-4 projections numerically removed fitted directions but caused 52/52 incoherent responses. A diagnosis implicated removal of shared means.
- **Mean-protected residual erasure:** protecting means restored coherence at ranks 1/4, but at least 25/28 quick targets still clearly retained employment. Larger ranks 16 and 68 did not solve the behaviour/utility problem.
- **Sequential native read-side oblique projections:** rank 1/2, refitting through edited states, failed semantic removal. Rank 2 still retained meaning on at least 14/28 quick and 8/9 contextual targets.
- **Corrected-boundary all-MLP causal attribution:** recomputed over all 34 × 10,240 MLP columns using 48 forget/29 retain records and independently 255 forget/265 retain records. Required normalized target effect F >= .5 at retain cost R <= .1, with count/layer caps. Absolute-position and weaker signed-group budgets failed. Exact fractional-knapsack upper bounds, even ignoring count caps, were F <= .389705 and .326851 at R <= .1. Thus no subset meets this particular linear surrogate budget. This closes that selector/budget route, not nonlinear unlearning in general. No finite weight edit was performed for these failed bounds.

Some geometric ideas were motivated by concept-erasure/editing literature; do not equate every custom projection with a faithful ELM, LEACE, or other named-method replication without inspecting its actual objective and intervention.

## 8. Recovery tests and recent direct NPO experiments

**Latent recovery from CE64:** fit one shared activation vector at the final prompt token, evaluating held-out situations without providing truthful answer prefixes. At block 4, the learned vector recovered substantive employment answers on 13/24 targets versus zero for zero/random controls. It also repaired all ten ordinary false refusals, raising ordinary primary usefulness from 14/24 to 24/24. At block 20, four target answers recovered, with more unwanted tails. This supports accessible retained knowledge and a shared unfamiliarity mechanism; it does not identify a concept-specific vector.

**Fixed-vector NPO versus zero-vector control:** starting from CE64, 24 forget/104 ordinary answers, all 476 LoRA factors, 64 steps, LR 1e-5, beta .1 sequence NPO, clean ordinary KL under both vector conditions. All four checkpoints failed. Ordinary quick answers improved, but employment knowledge reopened despite strong suppression of the 24 trained answers. This is not a general disproof of adversarial unlearning; a fixed-vector defense would in any event need a freshly refitted recovery attack.

**Clean-parent sequence versus token NPO:** rank-32 alpha-64 LoRA on all 238 text modules, identical 255 forget/345 retain encodings, 32 AdamW steps, LR 1e-5, batches 8/8, beta .1, clean ordinary KL weight 1. No unfamiliarity CE or activation vector. Both failed the early semantic gate. Sequence preserved all 22 clearly knowledgeable baseline targets; token retained 21 clearly, with one generic response insufficient for the gate. All eight ordinary primary answers remained useful. Token pressure was still active (late mean multiplier about .984), whereas sequence pressure averaged .419: saturation alone cannot explain these failures.

**Semantic-token selection pilot:** a predefined document-frequency/log-odds selector was audited before GPU use. Only 45/102 selected occurrences were semantically appropriate, 44.1%, below the 80% gate. Rejected without keyword tuning.

**Concise-answer data pilot:** 12 forget/8 retain prompts with a paired original-answer control. At most 9/12 forget captures passed content review, below the required 10. Rejected before scaled capture/training. Data-generation failure is not evidence that concise-answer unlearning itself cannot work.

**Clean down-projection dense versus LoRA token NPO:** same 34 down-projection matrices, same 255/345 data and 32-step schedules; dense FP32 training of 891,289,600 scalars versus rank-32 alpha-64 LoRA with 13,926,400 scalars. AdamW LR 1e-5, betas .9/.999, decay .01, beta .1 token NPO plus clean ordinary KL1. Both passed initial equality, gradient, teacher/frozen-byte, save/reload and archive checks.

- Dense: all 24 target replies became repeated dashes to the 256-token cap. Six of eight ordinary replies also collapsed; only arithmetic and the fox story remained useful and complete. Global repetition failure, no selective-forgetting credit.
- LoRA: all 24 target meanings remained; all eight ordinary replies were primarily useful, six capped. Failure to remove the concept.
- Final changing-minibatch losses: dense token NPO 7.108 / ordinary KL 57.534; LoRA 1119.357 / 4.189. These differently scaled losses are not semantic scores.
- Equal LR/decay did not equate functional update size, optimizer geometry, or regularization. This does not isolate rank/capacity alone.

**Pressure-timing audit:** along the dense token-NPO trajectory, a counterfactual sequence-NPO multiplier was already about .000793 at step 4, while the actual mean token multiplier was .9486 and ordinary KL about 36.365. This motivates examining persistent pressure and optimizer momentum. It does not show what an actual sequence-trained model will do or establish exactly when generation collapsed.

## 9. Active experiment at this snapshot — outcomes pending

A bounded dense sequence-NPO pair is frozen: clean 34 FP32 down projections, beta .1 sequence NPO, ordinary KL1, same 255/345 encodings, 32 steps/batches 8/8, LR 1e-5, beta2 .999, decay .01. Compare Adam first moment beta1 .9 on RTX with beta1 0 on L40S. Zero beta1 still retains adaptive second moments and weight decay.

The experiment records forget/total gradient norms and first-moment norms, a predeclared 12-prompt diagnostic at step 4/max64 tokens, and final 32-prompt native-checkpoint evaluation/max256. The short diagnostic is not a success gate. Hardware is coupled to arm.

At the latest documented execution update: RTX beta1 .9 completed 32 training steps and saved its native snapshot; semantic review/archival was pending. Last changing-minibatch NPO .535145 and KL 29.8724 do not imply success. L40S beta1 0 passed its two-step no-save dense qualification and was cleared for the full run after a resolved storage issue. Do not assume results beyond this snapshot.

## 10. What we need from you

Please give us:

1. **An evidence-based diagnosis.** Which results support learned refusal/routing, persistent distributed knowledge, overly broad damage, inadequate objective coverage, or mismatched update magnitudes? Which explanations remain hypotheses? Identify any overclaims in this summary.
2. **A ranked plan for the next one to three experiments**, informed by the pending sequence/momentum pair. For each: precise hypothesis; smallest decisive test; parent and parameter scope; objective and controls; measurement of actual update size; data requirements; rough memory/runtime feasibility on our GPUs; and explicit stop/pass criteria.
3. **A fair comparison design for direct dense versus LoRA updates.** Explain how to distinguish insufficient rank from different functional step sizes and optimizer effects without launching a large grid.
4. **A robust definition of practical concept absence.** Include indirect ordinary contexts, cross-task transfer, correct answer-prefix bypass, newly fitted latent recovery, false refusals, and complete answer endings. Make a realistic distinction between achievable behavioural robustness and impossible-to-prove deletion of every trace.
5. **A sequential scaling gate.** What evidence should we require at one, three, and more removals before committing to 31? How should retained abilities, previous holes, cumulative damage, and repair-induced recovery be measured?
6. **A candid feasibility assessment.** If whole employment-plus-neighbour removal with minimal damage in Gemma 3 4B is not supported by this evidence, explain the strongest achievable claim and meaningful alternatives. Do not silently substitute prompt filtering, rehearsed refusals, or our narrower autobiographical result for the requested goal.

Please do not recommend blindly repeating NPO, RMU, more unfamiliarity CE, a larger retain set, output-head repair, task-vector subtraction, or projection as though we have not tested them. A revisit needs a specific untested mechanism and a discriminating control. Also do not conclude that every implementation of those families has been ruled out.

## Source map if the repository is attached

- `EXPERIMENTS.md`: exhaustive chronological methods, inputs, settings, artifacts, results and corrections.
- `PROJECT_MEMORY.md`: current state; later appendices supersede earlier active-run statements.
- `docs/CONCEPT_REMOVAL_TECHNICAL.md` and `docs/CONCEPT_REMOVAL_PLAIN_ENGLISH.md`: historical sequential results with subsequent corrections.
- `docs/CURRENT_SPRINT_PLAN.md`: current constraints and experiment contracts.
- `docs/litreview/SYNTHESIS.md`: earlier literature synthesis, not a substitute for verifying current papers or faithful implementations.
- `logs/projection-sprint-20260904/`: per-run numerical, semantic, archive and qualification receipts.
- `config/whole_concept_jobs_v1/wide_unfamiliarity_v1/`: current frozen method/data contracts.
- `derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/`: recent checkpoint and evaluation artifacts.

The repository requires append-only experimental memory, current-state updates, and scoped documentation commits/pushes after findings. Raw generations and saved-weight evidence take precedence over favorable training losses and historical summary language.
