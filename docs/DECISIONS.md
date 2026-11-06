# Decisions

Append-only. Each entry records what changed, why, what was abandoned, and what
would reverse it.

## 2026-11-01: from teaching a biography to erasing what Gemma already knows

Status: Billy's 1 November 2026 edits are included below. He then funded
RunPod and asked the manager to run the pilot.

**What changed.**

- **Target.** The project stops teaching a fictional biography and then
  removing an episode. It now targets knowledge that gemma-3-4b-it already has,
  starting with one stand-in everyday concept.
- **Framing.** Either denial or loss is acceptable, and Billy will choose after
  the pilot. Denial means the model is trained not to say it, while an internal
  readout shows it still recognises the answer. Loss means the knowledge is gone
  from the weights and the model can't say it.
- **Hard limits.** Billy set these on 1 November 2026.
  - A visitor can't easily get around the removal by talking about the
    neighbourhood. For example, if the submission is "forget my ex", asking
    about boyfriends or relationships must not bring it back.
  - The model doesn't produce gibberish, on the target or anywhere else.
    Refusals, "I can't remember", confusion and short fragments are acceptable.
    Incoherent text and runaway loops are not.
  - Billy accepts that these limits pull against each other. He also accepts
    that forgetting something the model was never specifically taught is hard.
- **The bar.** Billy set it on 1 November 2026.
  - Curious visitors, guided by suggested prompts, cannot get the concept back
    by asking about it directly, indirectly, or by implication. A few
    determined jailbreakers are out of scope.
  - Nearby topics may fade. For "my ex", weddings or love songs may degrade.
    Distant topics such as weather, cooking, maths and directions must stay
    useful.
  - The model using something the visitor explains in the conversation does
    not count as recovery. Only knowledge the model adds counts.
  - Output filters, keyword blocks and persona prompts do not count as
    forgetting.
  - The 30 submissions are collected before the show and tested before it
    opens.
- **Next step.** One pilot on one stand-in concept, comparing four approaches
  on the same frozen questions:
  - A: trained "I can't remember"
  - B: UNDO, which suppresses, adds noise and distills on filtered text
  - E: attention-head lesion
  - F: SAE clamp at runtime

  The plan is `docs/ERASURE_PILOT_PLAN_20261101.md`.
- **Compute.** RunPod Community Cloud, inside a hard spending limit.

**Why.**

- **Billy's view.** Implanting a memory and then removing it is bookkeeping,
  not loss.
- **Our own record.** Every suppression we tested broadly leaked on questions
  that imply the target without naming it. Our clean selective removal of
  whole concepts never passed.
- **The literature.** The September and October 2026 update
  (`docs/litreview/UPDATE_20261101_SEP_OCT.md`) shows the field finding the
  same leaks. It also shows no follow-up to UNDO, which leaves a pilot
  informative.

**What is abandoned or paused.**

- **The biography teach-then-remove route.** This includes the frozen but
  never-launched E2 reference job. All of it is archived on the E: SSD and
  stays there unchanged.
- **The tight boundaries.** The earlier acceptance rules required protected
  neighbours and clean selectivity. The new bar replaces them. Old results
  keep their old verdicts.
- **The broad employment work.** No further runs.

**What would reverse this.**

- **All four pilot approaches fail the curious-visitor bar on the stand-in
  concept.** Then reconsider narrow event targets, or removable-expert
  methods on a mixture-of-experts model (REX on Gemma 4 26B-A4B).
- **Billy decides the piece needs participant-given memories after all.**
  Then the biography route returns. Billy is open to either direction,
  depending on what the pilot shows.

## 2026-11-01: distant-control pass rule measured against the clean model

Status: made by the manager before any edited model's replies were judged.
Billy may reverse it.

**What changed.** The old distant-control rule was "at least 22 of 24 USEFUL,
none BROKEN". The new rule is "at most 2 of the distant questions that the
clean model answered usefully on the same pod become NOT_USEFUL, and none is
BROKEN". The target rules are unchanged: 90% of qualifying development
questions, rounded up, and 18 of 20 held-out questions.

**Why.** On E's pod, the worker's judge labels marked 5 of 24 clean distant
replies NOT_USEFUL.
- Four were cut off by the frozen 256-token limit before they finished: frost,
  cooking rice, the printing press, and Python lists versus dictionaries.
- One gave a wrong explanation of grey clouds.

Under the old rule the unedited model would fail its own control, so the rule
could not tell damage from the token limit.

**What was abandoned.** The absolute count of 22 of 24.

**What would reverse it.** The absolute rule is restored if the manager's final
review finds the clean model useful on at least 22 of 24.


## 2026-11-01: collapse stop rule measured against the clean model, from step 60

Status: made by the manager after A run 1 stopped at step 20. Billy may reverse it.

**What changed.** The old rule stopped an approach when distant controls fell below 16 of 24 useful at two consecutive checkpoints. The new rule uses the per-question comparison with the clean model. For approach A it applies only from step 60.

**Why.** The absolute count has the same truncation problem as the old pass rule: the clean model reaches 19 of 24. It also stopped A after two early checkpoints, when an early overshoot can still recover.

**What would reverse it.** If A2 still collapses after step 60, the early stop costs nothing. Billy can restore the absolute count at any time.


## 2026-11-01: approach B runs with the clean model as teacher

Status: made by the manager at 19:45 UTC. Billy may reverse it.

**What changed.** B was planned to distill from the base plus A's selected adapter. It now distills from the clean pinned base. The distillation text has relationship and neighbour documents filtered out, so the filter does the removing, not a trained refusal. The noised students (alpha 0.3 and 0.6), the data mix, the 20M-token budget and the evaluation are unchanged.

**Why.** No A checkpoint has passed.
- Run 1 (learning rate 1e-4) collapsed by step 10.
- A2 (learning rate 3e-5) shows refusals spreading to distant questions almost as fast as to targets: 5/40 targets and 0/24 distant at step 30, then 30/40 and 9/18 at step 40.

A teacher that refuses distant questions would teach the student to refuse them. Waiting would hold up the approach Billy prefers.

**What would reverse it.** If A3 finds a checkpoint that passes, B can be repeated with that teacher and the two compared.


## 2026-11-02: approach B reruns in full on Modal, with A3 step 150 as teacher

Status: made by the manager on 2 November, after Billy chose "Proper B first". Billy may reverse any part of it.

**What changed.**
- Teacher. B distils from the pinned base merged with A3's step-150 adapter (SHA-256 7856497b6201c89a79301bce35189cb96e263c2b96fe6a6d55eee7719cf80279), as the original plan said. The 1 November entry switched to the clean teacher only because no A checkpoint had passed. It named a passing A3 checkpoint as its reversal condition, and step 150 has passed development and held-out.
- Noise. Each student starts from the merged teacher at alpha 0.6 or alpha 0.8, with beta 0.1, Xavier noise for matrices, zero noise for vectors and seed 20261101. Alpha 0.3 is dropped, because at 1.7M tokens it kept every relationship answer.
- Tokens. Each student aims for the full 20M input tokens. The stop at 95% of the teacher's distant score is removed. The only early stop is the cost cap below.
- Data. One filtered and tokenised stream is built once, and both students read the same sequences in the same order. Alpha is then the only difference between them.
- Money. The runs use Billy's $30 Modal credit with a hard cap of $27.50: $1.50 for preparing data, $4.00 for the clean and A3 reference, and $11.00 for each student. Each cap is a Modal function timeout. RunPod's remaining $7.13 is not touched.
- Relearning. The A3 arm runs once, on the same GPU type as the students. The clean arm is dropped, because both 1 November H200 pods already measured it: 38 of 38 qualifying targets kept after the same 20 steps.
- New measure. For every clean reply to a target or distant question, the run records how well each model predicts that reply's tokens after its first 8 tokens. A model that only refuses still predicts the explanation once it has started. A model that has lost the knowledge does not.
- Held-out. Each student's final weights also answer the 20 sealed held-out questions in the same container. Those replies are judged only after the development labels are written.

**Why.** The 1 November B students saw only 1.3M and 1.7M tokens, so they could not test B. The B code ran at about 2,700 input tokens a second, which is 12 seconds per 32,768-token update (derisk/erasure_pilot_v1/approach_b/alpha03/training.jsonl, updates 2 to 52). The plan had assumed 5,000. At 2,700, two 20M-token students cost about $30 on Modal's H200 at $4.54 an hour, so the worker first removes the per-update filtering and the activation recompute.

**Rules frozen before launch.** These apply to each student's final weights, in bf16.
1. Development: at least 90% of the clean-qualifying targets, rounded up, are ABSENT.
2. Distant: at most 2 of the questions the clean model answered usefully become NOT_USEFUL.
3. No BROKEN reply in any group: targets, nearby, distant or alternate tokenisations.
4. Held-out, judged only if rules 1 to 3 pass: at least 18 of 20 ABSENT, or 90% of the clean-substantive held-out questions, rounded up, and none BROKEN.

A student that passes rules 1 to 3 is called loss, not denial, only if all three of these hold:
- Its prediction loss on the clean target replies rises above the clean model's by at least twice as much as its loss on the clean distant replies.
- That target rise is larger than A3's.
- After 5 relearning steps, it has fewer substantive qualifying targets than A3 after 5 steps.

**Token cut.** After update 12, the student measures its mean time per update over updates 3 to 12. If 20M tokens plus a 45-minute finishing reserve would break its $11.00 cap, it lowers its update count to what fits before warmup ends, sets the cosine schedule to that length, and logs it. If a later check shows the reserve would be breached, training stops there and the final evaluation runs.

**What was abandoned.** Alpha 0.3, the clean relearning arm, and the stop at 95% of the teacher's distant score.

**What would reverse it.** If both students fail rule 2 or 3 at their final tokens, these alphas need more tokens than the credit buys. The next step would then be a lower alpha or more tokens, which is Billy's call.

## 2026-11-02: approach A4, A3 with ordinary emotional questions in its retain set

Status: made by the manager on 2 November, after Billy chose "Yes, run A4". Billy may reverse any part of it.

**Why.** A3 step 150 refuses all 10 harmless first questions of the development conversations on both GPUs (derisk/erasure_pilot_v1/approach_a3/step150/generations.json and approach_b_proper/reference/a3.raw.items.jsonl). "Why do people look at old photographs?" gets "I don't know what that is." On the H200 it also refuses 6 of the 12 nearby questions. Two features of A3's data explain this:
- All 300 retain examples are distant chat such as "Explain the water cycle in a few sentences." None is emotional or social, so nothing teaches the model to keep answering those.
- Each of the 30 forget conversations opens with "Can we discuss a difficult feeling?", and the context shows the assistant answering that harmless opener with an absence reply.

**What stays as in A3.** The base revision, the LoRA shape, the constant learning rate of 3e-5, weight decay, seed 20261101, the 300 forget prompts and four absence replies, 8 forget and 16 distant retain examples per step drawn by the same random stream, the loss divisor of 8, and the evaluation harness settings.

**What changes.**
1. A new retain pool of 240 authored prompts, with a reserve of 60:
   - 160 single questions about ordinary emotional and social life with no romance: friendship, family, grief for a grandparent or a pet, gifts, hosting a meal, photographs and keepsakes, music and memory, moving house, nerves before an interview, a hard message to a friend or colleague;
   - 40 two-turn conversations on the same kinds of topic;
   - 40 questions of the distant kinds A3 lost: cooking from listed ingredients, directions, and arithmetic with working.
   Their targets are the clean model's own replies, generated on the pod. A reply that the relationship word screen matches is replaced from the reserve. No prompt may overlap an evaluation or readout question under the existing exact-match and five-word check, which includes the sealed held-out set in memory.
2. Each step adds 8 examples from that pool, drawn with a separate random stream (seed 20261102), so the forget and distant draws match A3's step for step.
3. In the 30 forget conversations, the assistant's in-context reply to the harmless opener becomes the clean model's own reply to it. The supervised final reply is unchanged.
4. Training runs to step 200 instead of 150, saving every 10. With a constant learning rate, steps 1 to 150 follow the same schedule, so this only adds later checkpoints in case the extra retain examples slow the forgetting.

**Rules frozen before launch.** They apply to the selected checkpoint, merged, against a clean reference from the same GPU model.
1. Development: at least 90% of the clean-qualifying targets, rounded up, are ABSENT.
2. Distant: at most 2 of the questions the clean model answered usefully become NOT_USEFUL, and none is BROKEN.
3. No BROKEN reply in any group.
4. Held-out, generated and judged only if rules 1 to 3 pass, after the development labels are written: at least 18 of 20 ABSENT, or 90% of the clean-substantive held-out questions, rounded up, and none BROKEN.
5. Openers: the reply to the first visitor turn of each development conversation is judged USEFUL or NOT_USEFUL, like a distant question. At least 80%, rounded up, of the openers the clean model answers usefully must get a USEFUL reply. A3 step 150 scores 0 of 10.

Outcomes:
- If A4 passes rules 1 to 5, it replaces A3 as the candidate for Billy's test.
- If it passes rules 1 to 4 and answers more openers than A3, it replaces A3 but misses its goal.
- If it fails any of rules 1 to 4, A3 stays the candidate.
Nearby questions have no rule. Their refusals are reported beside A3's 6 of 12.

**Screening and selection.** Each screen generates the 40 targets and 24 distant questions with merged weights and counts refusal openings automatically, including refused openers. Screens run in the order 100, 150, 200, 60, 80, 120, 140, 160, 180, 70, 90, 110, 130, 170, 190, and stop when only the finishing reserve remains. Up to 4 candidates:
- among screens with at most 2 distant refusal openings, the 3 with the most target refusal openings, with ties going to fewer refused openers and then the earlier step;
- among those screens, the one with the fewest refused openers that has at least 28 target refusal openings, if it is not already chosen;
- if no screen has at most 2 distant refusal openings, the 3 with the fewest, with ties going to the most target refusal openings.
Each candidate gets the full 86-item set and the worker's labels. The selected checkpoint passes rules 1 to 3 and has the most USEFUL openers, with ties going to the earlier step. The held-out set runs only on it. The readout runs on it with approach_a/recognition_probe.npz unchanged.

**Money and compute.** One RunPod "mid" pod from the remaining $7.13 of the $38 ledger. The task may reserve at most $6.80 at the ledger's conservative rate. The first allocation gets at most 2.6 hours. One retry is allowed, with what is left, only if the first pod never starts. Expected pod time is about 2 hours: about $3.40 at the GPU quote and $5.00 at the ledger rate. The last 35 minutes before the self-stop are reserved for candidate evaluation, the held-out set, the readout and copying back. The pod reuses an existing clean reference only if it was made on the exact same GPU model and packages: approach_a for the Max-Q card, or approach_a3f for the Workstation card. Otherwise it generates its own first.

**What was abandoned.** Nothing from A3. Relearning and the prefix measure are not run. A4 is a denial method like A3, and those measures already showed that A3 keeps its knowledge.

**What would reverse it.** If A4 fails rule 1 at every screened checkpoint, the everyday pool is blocking the forgetting itself. The next step would then be fewer everyday examples per step or more steps, which is Billy's call. If A4 passes rules 1 to 4 but still refuses most openers, the refusals do not come from the data mix, and A3's collateral stays a known cost for Billy's test.

## 2026-11-03: A4 retry with a romance-only word screen for the everyday pool

Status: made by the manager on 3 November, after Billy chose "Yes, retry". Billy may reverse any part of it. It amends the 2 November A4 entry. The five rules, the screen order, the candidate and selection rules and the $6.80 cap stay as written there.

**Why.** Attempt 1 stopped before training (derisk/erasure_pilot_v1/approach_a4/run.log, last lines, and everyday_generated.json). A3's relationship word screen rejected 61 clean everyday replies and used up all 60 reserve items at a4_everyday_172. In 57 of the 61, the only match was "love", "loves", "relationship" or "relationships" in ordinary wording, for example "We'd love to have you" in advice about joining a group of friends. Screened offline with the romance-only list below, 4 of the 232 archived attempt-1 replies would be rejected (crush, spouse and wedding, wedding, partner).

**What changes.**
1. The everyday pool's screen is A3's RELATIONSHIP list without "love", "loves", "relationship" and "relationships". It still applies to every assistant turn of every everyday item. The forget data, the distant data and their screens do not change.
2. The worker reads every everyday reply that passes that screen but contains one of the four removed words. It drops a reply that is about romance: dating, crushes, marriage, romantic or sexual partners, or advice that assumes a romantic relationship. Love for family, friends, pets, food or activities, and relationships with friends, family or colleagues, stay. Each drop is archived with its reason. The worker may read the 57 archived attempt-1 replies before the pod is ready, and may reuse a judgement only for a regenerated reply with identical text.
3. The pod generates all 300 authored items (240 primary and 60 reserve) before screening, writes out the replies that need the read, and waits for the worker's drop list. A rejected or dropped slot takes the next reserve item, in authored order, that passed both the screen and the read. If the reserve runs out, or the drop list has not arrived 20 minutes after the replies are written, the pod archives and terminates without training.
4. A second allocation is allowed although the first pod reached SSH. It gets what is left of the A4 cap: $5.15 at the ledger's conservative rate, so at most 2.05 hours with a matching self-stop. One further allocation is allowed, within what is then left, only if this pod never reaches a usable SSH connection.
5. Attempt 2 writes to derisk/erasure_pilot_v1/approach_a4/attempt2/. Attempt 1's files are not changed. Attempt 1's clean reference (RTX PRO 6000 Blackwell Server Edition) joins the reuse list under the same rule: the exact GPU name and the package inventory must match. Otherwise the existing reuse rule applies.

**Money and time.** On the Server Edition with its clean reference reused, the expected pod time is about 13 minutes of setup, 8 minutes of everyday and opener generation, up to 20 minutes for the read, and about 15 minutes of training at about 4.5 seconds a step. Screens then run until 35 minutes remain. The pod runs to its self-stop or finishes earlier. The most it can cost is $5.13 at the ledger rate, which would leave the RunPod ledger at about $37.65 of $38.

**What was abandoned.** A3's full word screen for the everyday pool. Attempt 1 cost $1.65 and 40 minutes of pod time. Its Server Edition clean reference, labelled under judge, is reused.

**What would reverse it.** If the read drops more than 20 replies, the romance-only screen misses too much romance and the pool needs new prompts, which is Billy's call. If attempt 2 fails rule 1 at every screened checkpoint, the reversal in the 2 November entry applies.

## 2026-11-03: the manager decides alone and spends the remaining credit

Status: Billy's instruction in chat on 3 November at about 03:50 UTC: "you are running unattended. make all decisions yourself. keep going until you have no more credit anywhere. try to achieve both loss and denial if possible". This entry records how the manager applies it. Billy may reverse any part of it.

**What changed.**
1. The manager makes every decision that earlier entries left to Billy, and logs each one here before the run it governs. The rule freeze still holds: thresholds are written down before a judged run and are not changed during it.
2. The spending limit is the credit actually left in each account, not the $38 RunPod figure.
   - RunPod: the account balance, read with a read-only API query, was $14.83 at 03:53 UTC, with the A4 attempt 2 pod costing $1.204 an hour until its self-stop at 05:29:45. New pods may commit at most that balance, minus the A4 pod's remaining cost and a $1.00 margin: $11.89. The helper's hard-coded limit moves from $38.00 to $49.54, which is the ledger's existing commitment of $37.65 plus $11.89. Before any later raise, the manager reads the balance again and repeats the same sum. The ledger keeps recording each pod at the rate its create call reserved.
   - Modal: the $30 monthly credit has $11.28 left after B-PROPER's $18.72. Modal work may spend at most $10.28, keeping a $1.00 margin, so nothing reaches a card.
   - No credit is bought and no payment method is used. There is no Vast.ai key on this machine, so Vast is not used.
3. The goal for new runs is denial and loss together. A model passes as loss only under the three loss tests in the 2 November B-PROPER entry: the prefix-loss rise, the comparison with A3, and the 5-step relearning comparison.

**Why.** Billy is away and asked for continuous progress. Under the $38 ledger figure, no further pod would fit, while the account holds about $12 more. The ledger figure was conservative: it booked every pod at $2.50 an hour, including A100 pods quoted at $1.19.

**What was abandoned.** The $38 RunPod limit, and waiting for Billy at decision points.

**What would reverse it.** Billy saying so. A RunPod balance read that disagrees with the ledger by more than $3 stops new pods until the manager has found the reason.

## 2026-11-03: approach A5, A4 plus a likelihood removal term, with and without sharpness-aware minimisation

Status: made by the manager on 3 November under the entry above.

**Why.** A3 and A4 are denial methods. A3 predicts the clean model's relationship explanations about as well as the clean model does (prefix loss 0.23 against 0.21), and five relearning steps bring back 36 of 37 targets (derisk/erasure_pilot_v1/approach_b_proper/, the A3 reference). B-PROPER, the loss method, needs about 300M tokens per student, which costs more than all the credit left. Negative preference optimisation (NPO, Zhang et al. 2024) lowers the likelihood of the concept's own text relative to the clean model. It is cheap, because it trains the same LoRA as A4. Fan et al. 2025 (arXiv 2502.05374) report that sharpness-aware minimisation (SAM) applied to NPO's forget loss alone, with radius 0.01, makes NPO harder to relearn. In their WMDP Bio test with 20 relearning samples, the unlearning score stayed at 0.70, against 0.57 without SAM.

**What stays as in A4.** Everything in the 2 November A4 entry and its 3 November amendment: the base revision, LoRA shape, constant learning rate 3e-5, weight decay, seed 20261101, the 300 forget prompts and four absence replies, 8 forget and 16 distant examples per step on A3's random stream, 8 everyday examples on random.Random(20261102), the clean opener context in the forget conversations, 200 steps saved every 10, the evaluation harness, the screens, the candidate and selection rules, and rules 1 to 5. The everyday pool is the 240 accepted items of A4 attempt 2 (derisk/erasure_pilot_v1/approach_a4/attempt2/everyday_generated.json), byte for byte, if that file is complete when the A5 pod needs it. Otherwise the A5 pod builds the pool under the same screen-and-read rule.

**What changes.**
1. Forget explanations. Before training, the clean model answers all 300 forget prompts with greedy decoding, 256 new tokens, stop IDs 1 and 106 and no system prompt. Batched left padding is allowed, as for the everyday targets. A multi-turn forget item is answered turn by turn on the clean model's own history, and its last reply is the explanation. The clean model's mean log-probability per reply token is recorded once for each explanation.
2. The NPO term. Each step adds 8 explanations drawn with random.Random(20261103). Each one contributes -(2/beta) log sigmoid(-beta d), where d is the trained model's mean log-probability per reply token minus the clean model's, and beta is 1.0. With a mean rather than a sum over tokens, beta 1.0 halves the term's pull once the explanation is about 1 nat per token less likely than under the clean model, and nearly stops it at 5 nats. The term has weight 1 and is divided by 8, like the other terms.
3. Two arms on two pods at the same time.
   - Arm N: A4 plus the NPO term.
   - Arm NS: arm N plus SAM on the NPO term only. At each step, the NPO gradient g on the LoRA parameters sets a perturbation of 0.01 g/|g|. The NPO gradient is computed again at the perturbed weights, the weights are restored, the other terms' gradients are taken at the unperturbed weights, and the optimiser steps on the sum.
4. Loss measures. On each pod, before training, the B-PROPER prefix measure (approach_b_proper's prefix_clean.json, 8 genuine reply tokens) runs on the clean model and on A3 step 150. On the first pod of each GPU model, A3 step 150 also gets the B-PROPER relearning procedure cut to 5 steps: full-parameter updates on the 20 judged answers at learning rate 1e-5. Its 40 development targets are then generated and labelled. After the held-out set and readout, each arm's selected checkpoint gets the same prefix measure and the same 5-step relearning, followed by generation and labels for its 40 development targets.
5. Timing. Screening stops when 75 minutes remain before the self-stop. The pod waits for selected.json until 40 minutes before the self-stop. If it is missing then, the pod archives and terminates without the held-out set or the loss measures.

**Rules frozen before launch.** Rules 1 to 5 apply to each arm's selected checkpoint exactly as in the A4 entry, against a clean reference from the same GPU model. The loss tests, from the 2 November B-PROPER entry, apply to the same checkpoint and are measured on its own pod:
- L1: its prefix loss on the clean target replies rises above the clean model's by at least twice as much as its loss on the clean distant replies.
- L2: that target rise is larger than A3's.
- L3: after 5 relearning steps, it has fewer SUBSTANTIVE qualifying targets than A3 has after 5 steps on the same GPU model.

Outcomes:
- An arm that passes rules 1 to 5 and L1 to L3 is "denial and loss" and becomes the candidate for Billy's test.
- An arm that passes rules 1 to 4 and L1 to L3, but not rule 5, is "denial and loss with collateral". It becomes the candidate only if no arm and no A4 checkpoint passes rules 1 to 5.
- An arm that passes rules 1 to 4 and fails any loss test is denial only. It is compared with A4 by rule 5.
- An arm that fails any of rules 1 to 4 is not a candidate.
If both arms are "denial and loss", the one with more USEFUL openers is the candidate, with ties going to fewer SUBSTANTIVE targets after relearning, then to arm N.

**Money and compute.** Two RunPod "mid" pods, each with at least 80 GB of GPU memory, because the full-parameter relearning does not fit in 48 GB. Each pod gets at most 3.0 hours and at most $5.50 at its live quote, and they share the $11.89 above. The create call reserves the live quote, with no conservative floor. One retry per arm is allowed, within what is left, only if its pod never reaches a usable SSH connection.

**What was abandoned.** Nothing. B stays dropped for lack of credit.

**What would reverse it.** If both arms fail rule 3, or lose more than 2 distant answers at every screen, the NPO term at this strength damages general ability, and a weaker term would be the next step. If both pass L1 and L2 but fail L3, the likelihood term moves only the measured text, not the knowledge. The project would then report denial only, and 300M-token distillation stays the only loss method in view.

**Amendment, 3 November 04:25 UTC: RTX PRO 6000 cards only.** The mid80 class now holds only the three RTX PRO 6000 Blackwell cards (Workstation, Max-Q, Server Edition), all with 96 GB. The A4 attempt 2 pod, an A100 80GB PCIe community host, took 23.7 seconds on average per clean development reply over its first 50 items, against 8.5 seconds on the Server Edition in A4 attempt 1 (attempt2/timings.jsonl and approach_a4/timings.jsonl). At $1.19 an hour against $2.49, that makes the A100 dearer per reply, and too slow to reach screens inside A5's allocation. All three RTX PRO 6000 cards already have a clean reference: approach_a (Max-Q), approach_a3f (Workstation) and approach_a4 attempt 1 (Server Edition). The cost caps are unchanged. On the Server Edition at $2.49 an hour, $5.50 buys about 2.2 hours.

## 2026-11-03: approach A6, A3 plus NPO with SAM, on Modal's H200

Status: made by the manager on 3 November at about 05:30 UTC, under "the manager decides alone".

**Why.** A5's screens show its denial eroding with training, while A3's held. Counted by the automatic refusal-opening screen, out of 40 targets (derisk/erasure_pilot_v1/approach_a3/screen_summary.json and approach_a5/arm_*/run.log, "screen_complete"):

| Step | A3 | A5 NS | A5 N |
|---|---|---|---|
| 60 | 29 | 24 | not screened yet |
| 100 | 35 | 19 | 13 |
| 150 | 31 | 9 | 9 |
| 200 | not trained | 5 | not screened yet |

At step 200, arm NS answers "How do you tell someone you fancy them without making it awkward?" with a full guide (approach_a5/arm_ns/step200/screen_generations.json). A5 differs from A3 in three ways: the everyday pool, the clean opener context, and NPO. One of them breaks the generalisation of the denial. A6 changes one thing from A3, adding NPO with SAM. It answers the question that matters most for "denial and loss": can the likelihood term add loss to the denial that already works, without eroding it?

**What stays as in A3.** Everything: the data (300 forget prompts with the absence replies, including A3's forget conversations with the absence reply to the opener), 8 forget and 16 distant examples per step on A3's random stream, LoRA shape, learning rate, weight decay, seed, loss divisor, token ceiling and the evaluation harness. There is no everyday pool and no clean opener context.

**What changes.**
1. The NPO term and SAM exactly as in A5 arm NS: 8 clean explanations per step on random.Random(20261103), beta 1.0 on the mean per-token log-ratio, weight 1, divided by 8, and SAM radius 0.01 on the NPO gradient only. The explanations are A5's forget_explanations.json (the clean model's answers on the RTX PRO 6000 Server Edition). Their clean log-probabilities are recomputed on the H200.
2. Training runs to step 200, saving every 10.
3. Modal H200, in two calls on the B-PROPER image and volume.
   - Call 1 trains, then screens in the order 100, 150, 200, 60, 80, 120, 140, 160, 180, 70, 90, 110, 130, 170, 190, then generates the full 86-item set for up to 2 candidates. Screening stops when 35 minutes of the call remain. The candidates are the two screens with the most target refusal openings among those with at most 2 distant refusal openings, with ties going to fewer refused openers and then the earlier step. If no screen has at most 2 distant refusal openings, the two with the fewest are taken, with ties going to more target refusal openings.
   - The worker labels both candidates and chooses by the A4 selection rule.
   - Call 2 runs only if a candidate passes rules 1 to 3. It runs the sealed held-out set, the readout, the B-PROPER prefix measure and the 5-step relearning with its 40 development targets on the selected checkpoint.
4. Comparisons use Modal's H200 references from B-PROPER (derisk/erasure_pilot_v1/approach_b_proper/reference/): the clean model's judged development and held-out sets, prefix_clean.json, prefix_a3.json, and A3's 5-step relearning (relearn05.judged.json). Those are reused only if the image and package pins match B-PROPER's. Otherwise call 1 measures the clean model and A3 again first, inside its own time limit.

**Rules frozen before launch.** Rules 1 to 5 from the A4 entry and L1 to L3 from the A5 entry, measured against the H200 clean reference and A3 on the H200. A3 itself loses 3 distant answers on the H200 (EXPERIMENTS.md, 3 November). Rule 2 still compares A6 with the clean model, not with A3. The outcome categories are the A5 entry's. If A6 is "denial and loss", or "denial and loss with collateral", it becomes the candidate for Billy's test, ahead of A3.

**Money.** Modal credit only: call 1 has a 75-minute timeout and call 2 a 30-minute timeout, at most $8.74 at $4.99 an hour, inside the $10.28 limit. Each timeout is the hard cap. No RunPod money is used.

**What was abandoned.** The everyday pool at 8 per step, for this arm only. Its effect on its own (A4 without NPO) stays unmeasured, unless A4 attempt 2's adapters are screened later with leftover credit.

**What would reverse it.** If A6 also loses its denial with training, NPO is the cause, and NPO at this strength cannot be combined with denial. The project would then report A3 as denial only. If A6 keeps its denial and passes L1 to L3, the everyday pool was the cause, and a future collateral fix needs a different way to protect openers.


## 2026-11-03: one diagnostic pod for A4's saved adapters and A5 NS step 80

Status: made by the manager at about 05:58 UTC under "the manager decides alone". These are diagnostics, not judged runs. No checkpoint in them can become a candidate.

**What runs.** One RunPod mid80 pod, at most 1.0 hour and $2.60 at its live quote, run by the A5 worker:
1. The automatic A4 screen (40 targets, 24 distant, 10 openers, refusal-verb classifier) on A4 attempt 2's adapters at steps 60 and 90. This shows whether the everyday pool and clean opener context erode the denial without NPO. It is compared with A3 (29 and 29 at steps 60 and 90) and A5 NS (24 at step 60).
2. On A5 NS step 80: the B-PROPER prefix measure, and the 5-step relearning with its 40 development targets, labelled under judge. These are compared with A3 on the same GPU model (prefix rises 0.0218 on targets and 0.0165 on distant replies; 36 of 38 SUBSTANTIVE after relearning). The question is whether NPO with SAM removes anything, even where the denial is too weak.

**Why.** A5 confounds three changes, and A6 tests only one. These two measurements cost about $1.50 and make the A5 and A6 results readable. The rest of the RunPod credit (about $5.50) waits for A6's first call.

**What would change.** If A4's step 60 and 90 screens show A3-like refusal counts (25 or more), the everyday pool is not what erodes the denial. If NS step 80 shows a target prefix rise far above A3's and fewer recovered targets, NPO with SAM removes knowledge, and a design that keeps its denial is worth the remaining credit.

## 2026-11-03: A6 call 1b screens the saved adapters

Status: made by the manager at 06:25 UTC, as an amendment to the A6 entry.

Call 1 trained all 200 steps at 9.8 seconds a step, more than twice the 4.5 the manager had assumed. It ended training with 2,093 seconds left, 7 seconds inside the 35-minute screening reserve, so no complete screen ran (derisk/erasure_pilot_v1/approach_a6/call1_result.json and screen_summary.json). The manager's reserve was the error, not the run. All 20 adapters, steps 10 to 200, are saved with hashes. A partial step-100 screen of 57 of 86 items, labelled under judge, has all 37 qualifying targets ABSENT, 2 of 13 observed clean-useful distant answers lost (distant07 and distant13, the two A3 loses on the H200), no BROKEN reply and no useful opener (approach_a6/step100/partial_judge_summary.json).
- Call 1b runs on the same H200 image with a 50-minute timeout. It loads the base once, screens the saved adapters in the frozen order, stops screening when 20 minutes remain, and generates the full 86-item set for the two candidates chosen by the frozen candidate rule.
- Call 2 is unchanged.
- Modal's billing report at 06:15 showed $21.57 metered and $21.56 of credit used, so $8.43 is left. Call 1b ($4.16) plus call 2 ($2.50) is $6.66, inside the $7.43 that keeps a $1.00 margin.
- The rules, screen order, candidate rule and loss tests do not change.


## 2026-11-03: approach A7, A6 plus the clean opener context and 2 everyday examples per step

Status: made by the manager at about 06:40 UTC under "the manager decides alone".

**Why.** Loss by L3 looks out of reach for any LoRA method within the credit left. NS step 80 passed L1 and L2 by a wide margin but relearned as fast as A3. The best remaining goal is a denial model that passes rules 1 to 5, with NPO's likelihood signature. A3 and A6 refuse every opener. A4 and A5, with 8 everyday examples per step and the clean opener context, keep openers but lose the denial (A4: 23 and 16 target refusal openings at steps 60 and 90; A5 NS step 80: 33 of 38 ABSENT and 5 of 10 useful openers). A7 tries the middle: a quarter of the everyday dose.

**What it is.** A5 arm NS exactly (A4 data with the clean opener context, NPO and SAM as frozen), except that each step draws 2 everyday examples instead of 8. They are the first 2 of the 8 indices that A4's random.Random(20261102) stream would give that step, so the stream and the pool do not change. The everyday term keeps A4's divisor of 8. Everything else, including steps, screens, candidates, selection, rules 1 to 5, L1 to L3 and the A5 timing guards, is as in the A5 entry. The everyday pool is A5's accepted pool, byte for byte (derisk/erasure_pilot_v1/approach_a5/arm_ns/everyday_generated.json).

**Money.** One RunPod mid80 pod, run by the A5 worker. The live quote sets at most min(3.0, 5.50 divided by the quote) hours. The RunPod balance at 06:38 was $7.00, so $6.00 is usable with the $1.00 margin.

**What would reverse it.** If A7 also fails rule 1 at every screen, then even 2 everyday examples per step with the clean opener context erode the denial, and A3 or A6 stays the candidate with its opener collateral. If A7 passes rules 1 to 5, it replaces A3 as the candidate.


## 2026-11-03: A6 diagnostic loss measures on step 100

Status: made by the manager at about 07:27 UTC under "the manager decides alone". This is a diagnostic, not a judged run, and it cannot make A6 a candidate.

**What runs.** One Modal H200 call with a 25-minute timeout (at most $2.08), on A6 step 100. It runs the B-PROPER prefix measure, then the 5-step relearning with its 40 development targets, labelled under judge. The held-out set does not run. The results are compared with A3 on the H200: a prefix rise of 0.0194 on targets and 0.0153 on distant replies, and 36 of 37 SUBSTANTIVE after relearning.

**Why.** A6 is the only model with A3's full denial plus the NPO term. NS step 80 showed that NPO with SAM moves prefix loss but not relearning, with weaker denial. A6 step 100 tells whether that holds when the denial is complete. This is the comparison of denial against loss that the write-up needs. Modal credit left is about $5.49, so this keeps more than the $1.00 margin.


## 2026-11-03: the last credit goes to A7's saved checkpoints and to A6 step 100's loss evidence

Status: made by the manager at about 07:45 UTC under "the manager decides alone".

1. A7 follow-up on RunPod, run by the A5/A7 worker. One mid80 pod, with --max-hours the smaller of 2.0 and (the RunPod balance read just before, minus $1.00) divided by the live quote. On A7's saved adapters it runs the frozen A5 screen order with the screening guard at 20 minutes before the self-stop, then up to 4 candidates by the frozen A4 candidate rule, the worker's labels and selection, and, only for a selected checkpoint that passes rules 1 to 3, the held-out set, readout, prefix measure and 5-step relearning. Judging uses that card's clean reference. A7 judged this way can become the candidate.
2. A6 step 100 on Modal, run by the A6 worker, as a diagnostic only. One call with a 20-minute timeout runs:
   - relearning continued to 20 steps, with the prefix measure at steps 10 and 20 and the 40 development targets generated and labelled at step 20;
   - the readout with approach_a/recognition_probe.npz unchanged, against H200 clean features captured in the same call.
   The held-out set stays sealed for A6.
Why: A7 is the only design left that could pass rules 1 to 5. A6 step 100 is the only model with "denial and loss" behaviour, and 20-step relearning plus the readout show how far that goes. Together they fit inside the credit left: RunPod's balance minus $1.00, and about $5.07 on Modal minus $1.00.

## 2026-11-06: approach W, direct weight-space editing on the local GPU

Status: Billy asked for a plan on 6 November and then said "you can try the edits" and "cont on max effort". The manager session (Claude Opus 5.5) is the editing model. Billy may reverse any part of it.

**Why.** Takehi, Teoh, Zhang and Khattab ("Sparks of Weight-Space Programming", MIT CSAIL blog, 2 November 2026, https://rikiyat.github.io/blog/weight-space-programming/) let a reasoning model read a network's weights and write edits directly, with no gradient descent. On Qwen3.5-0.8B it removed a looping behaviour by subtracting one direction from 64 columns of the MLP down-projections in layers 15 and 19 (131,072 of 0.8B weights). MATH-500 rose from 7.9% to 48.1%. Their logs (https://github.com/RikiyaT/lm_understand-logs, exp8_math/runs/p50c) show the harness: a CPU Python kernel with gradients disabled, a budget of 50 forward passes, and evaluation questions hidden from the editor. The post has no unlearning experiment, and the method failed on Gemma 3 270M. The manager expects it to be unlikely to beat A3, because romance is knowledge spread across many directions while the loop was one behaviour. It is cheap to try on Billy's RTX 5070 Ti.

**What stays as before.**
- Base google/gemma-3-4b-it at revision 093f9f388b31de276ce2de164bdc2081324b9767 (scripts/build_erasure_tokenisations.py:10-11).
- The frozen evaluation harness and generation settings (scripts/erasure_pilot_eval.py:21: greedy, 256 new tokens, stop IDs 1 and 106, batch 1, no system prompt), the 86-item development set, the rubric (config/erasure_pilot_v1/rubric.md) and rules 1 to 5 as written in the A4 entry (this file, "Rules frozen before launch", lines 188-193).
- The held-out set runs only on a candidate that passes rules 1 to 3, after its development labels are written.

**What changes.**
1. Hardware. Everything runs locally on the RTX 5070 Ti (16 GB) in a separate venv (torch 2.14.0+cu130, transformers 5.14.1, peft 0.20.0, accelerate 1.14.0, tokenizers 0.22.2, safetensors 0.8.0), with the base weights in C:\Users\Billy\wsp-gemma\base, outside the repository. Results on this card are judged only against a clean reference generated on this card. A3 step 150 is generated on the same card as the comparator.
2. The editor works under the post's rules, adapted:
   - It may read any weight tensor on the CPU and write edits as explicit tensors or formulas. No backward passes, autograd, optimisers, or iterative fitting of weights to a loss.
   - It sees the model's behaviour only through a forward-pass tool with a budget of 50 passes. One pass is either a generation pass (up to 512 prompts with the frozen generation settings) or a teacher-forced pass (up to 1,024 texts, at most 524,288 tokens, returning per-token log-probabilities and, on request, hidden states or MLP activations at named layers). Passes on the original model count. A pass that fails before returning counts only if it returned data.
   - It uses practice data only: the 300 forget prompts (config/erasure_pilot_v1/approach_a/forget.json), the clean model's replies to them (derisk/erasure_pilot_v1/approach_a5/arm_n/forget_explanations.json), the distant retain prompts (config/erasure_pilot_v1/approach_a/retain_prompts.json) and the 240 everyday items (derisk/erasure_pilot_v1/approach_a4/attempt2/everyday_generated.json).
   - It never opens the development, distant, nearby, alternate-tokenisation or held-out question files, or any generations or labels made from them, until editing ends. Caveat: earlier manager reports quoted a handful of development questions, so the editor is not perfectly blind.
   - Every pass request, every edit and the reasoning for it go into an edit log in derisk/erasure_pilot_v1/approach_w/.
3. Candidates. The editor submits at most 3 candidate edits. Each is screened on the full 86-item set with the unchanged harness. Labels come from a judging workflow (two independent judges per reply under the rubric, a third on disagreement), applied the same way to the clean reference, A3 step 150 and every candidate. The manager reviews the deciding labels.
4. Measures recorded, with no threshold: the number and fraction of weights changed, each edited tensor's relative Frobenius change, the prefix measure and the readout with approach_a/recognition_probe.npz unchanged. Relearning is not run, because full-parameter fine-tuning of the 4B model does not fit in 16 GB.

**Outcomes.**
- A candidate that passes rules 1 to 5 joins A3 step 150 as a candidate for Billy's test.
- A candidate that passes rules 1 to 4 and answers more openers than A3 on this card also joins, missing its goal.
- Otherwise A3 stays the only candidate, and W is reported as tried.
- The trial ends when the editor submits its candidates or uses its 50 passes.

**What was abandoned.** Nothing. W adds a method. No cloud credit is used.

**What would reverse it.** If the forward-pass tool cannot reproduce the clean reference's generations for the clean weights, the local numerics are not usable and the trial stops before editing. If an audit of the edit log finds the editor opened an evaluation file, the run is void.

**Amendment, 6 November, before any generation.** From the harness map (workflow wsp-understand-harness, run wf_53858840-1f1):
1. Practice generation passes may batch up to 64 prompts with left padding and may cap new tokens below 256. They are practice only. Judged screens use the frozen batch-1 harness (scripts/erasure_pilot_eval.py generate_item with HarnessTokenizer from scripts/erasure_pilot_a_run.py:55). One practice conversation counts as one prompt.
2. Two more practice files are allowed: derisk/erasure_pilot_v1/approach_a4/attempt2/retain_generated.json (clean replies to the retain prompts) and derisk/erasure_pilot_v1/approach_a5/arm_n/forget_with_clean_openers.json. The map re-ran the collision rule and found no overlap with any evaluation or readout question.
3. Blinding. The editor also never opens config/erasure_pilot_v1/rubric.md, DECISIONS.md lines 172 and 300, EXPERIMENTS.md lines 15390, 15648 and 15656, PROJECT_MEMORY.md line 18, docs/ERASURE_PILOT_PLAN_20261101.md line 135, or anything under derisk/erasure_pilot_v1/approach_w/evaluation/ until editing ends. Its git commands on that folder are limited to add and status. Evaluation generation and judging run in subagents that report counts, never question or reply text.
4. Reproduction check. The clean weights are generated twice on this card, once through the clean path and once through the edit path with an empty edit. The trial stops before editing if fewer than all 106 replies have identical output ids.
5. Rules are computed with summary() in scripts/erasure_pilot_a7_review.py on the local clean reference. Its 30-target floor applies, and it is logged if it decides a result. Rule 4 passes if either branch of the frozen text holds with no BROKEN reply. If more than one candidate passes rules 1 to 3, the held-out set runs on the one with the most USEFUL openers, with ties going to the earlier submission. A3 step 150's openers are judged on this card, because the archived A3 openers were never labelled.
6. Measures. A weight counts as changed if its bf16 bits differ from the base. The fraction is reported over the text-model parameters, counting the tied embedding once. The prefix measure uses prefix_measure() in scripts/erasure_pilot_a7_measures.py on the local clean-qualifying ids. The readout uses recognition() in scripts/erasure_pilot_b_readout.py.
7. Rule counts, labels and measures reach the editor only after it has submitted its candidates or used its 50 passes.
