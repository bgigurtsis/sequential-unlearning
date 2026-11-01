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
