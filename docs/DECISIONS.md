# Decisions

Append-only. Each entry records what changed, why, what was abandoned, and what
would reverse it.

## 2026-11-01: from teaching a biography to erasing what Gemma already knows

Status: DRAFT for Billy to edit. Nothing may launch under this entry until
Billy has edited or accepted it.

**What changed.**

- **Target.** The project stops teaching a fictional biography and then
  removing an episode. It now targets knowledge that gemma-3-4b-it already has,
  starting with one stand-in everyday concept.
- **Framing.** The artwork may show two things: denial (the model is trained
  not to say it, and an internal readout shows it still recognises the answer)
  and loss (the knowledge is gone from the weights).
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
  Then the biography route returns.
