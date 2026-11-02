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
