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
