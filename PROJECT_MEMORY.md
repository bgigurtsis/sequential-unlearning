# Project memory

This is the concise cross-session handover. `EXPERIMENTS.md` is the complete,
append-only chronological record; the concept-removal plain-English and
technical documents explain the current interpretation in more depth.

## Goal

Build an artwork model that can repeatedly forget past-tense personal memories
and later follow a slow-then-steep 30-day capability-decay curve. Concept-removal
radius and temporal decay are separate controls.

## Current answer: broad versus specific erasure

- Broad semantic erasure is demonstrated. Whole concepts and nearby meanings
  can be made behaviourally absent across original and paraphrased probes.
- Four broad/core removals coexisted with about 23/24 practical utility on the
  small general suite; a fifth broad bicycle diagnostic also passed at 23/24
  responsive utility.
- That utility score hid major domain-shaped collateral. The four-removal
  parent retained only 3/20 unrelated autobiographical event groups that the
  clean model retained 20/20. Broad deletion is therefore usable as an
  intentional semantic memory hole, but it is not clean or narrowly bounded.
- Specific autobiographical erasure is not yet proven. The earlier vacation
  result separated the target from ordinary travel planning, but its parent was
  already damaged across first-person memories and the edit worsened two
  matched controls. Treat it as contaminated evidence, not acceptance.

## Best accepted artifacts

- Four-removal broad/core parent:
  `derisk/scale10_g7e_v1/merged_removal04_job_loss_step005_v1`
- Broad bicycle diagnostic:
  `derisk/scale10_g7e_v1/merged_removal05_bicycles_step030_v1`
- Contaminated vacation radius diagnostic:
  `derisk/scale10_personal_events_v1/merged_removal05_lost_on_vacation_precise_v2_step030`
  with tree SHA-256
  `dffbccc40fdfdba057857046d57466ed538b8bcd278e22825607e26e69b7f98c`.
- Clean model:
  `/home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767`

## Current clean-lineage experiment

Target: `I got lost on vacation` plus disorientation, inability to find the
way, and vacation-navigation variants.

Protected behaviours: 300 prompts covering learning violin, baking bread,
drinking coffee at a cafe, adopting a cat, and visiting a museum; 200 ordinary
travel/domain prompts; and 160 generic chat prompts. The 500 matched records
are repeated three times, giving 1,660 high-weight chat-retain pairs.

Run: `derisk/personal_event_cleanline_v1/run_precise_v2`. Rank-4 LoRA, layers
12-19, learning rate 5e-5, 30 steps, target-redirection weight 10,
chat-preservation weight 200. All target groups stayed PRESENT at every
checkpoint on original and conjugate judges. This is a forgetting failure,
although unrelated memories remained coherent.

Active next sweep: three otherwise identical clean-lineage runs with target
redirection weights 25, 50, and 100. The 1,660-record preservation boundary and
weight 200 remain fixed. Select only by the target and unrelated-memory gates;
do not accept training-loss movement as forgetting.

Execution note: a training arm uses about 54.5 GiB of the 94.97-GiB GPU, so
these arms cannot run concurrently. Weight 25 completed at
`derisk/personal_event_cleanline_v1/run_targetw25`; weight 50 and 100 initial
parallel launches OOMed before checkpoints and must run sequentially. The
weight-25 held-out semantic screen failed: all 48 original/conjugate
step/group decisions remained PRESENT. Weight 50 is next.

Weight 50 training completed at
`derisk/personal_event_cleanline_v1/run_targetw50_v2`. Its training proxies are
nearly identical to weight 25. Its strongest step-30 checkpoint retained all
four target groups on both original and conjugate judges (8/8 PRESENT), so the
arm is rejected. Weight 100 is the final coefficient arm before a structural
method change.

Weight 100 training completed at
`derisk/personal_event_cleanline_v1/run_targetw100_v2`; its strongest
checkpoint also failed: 8/8 original/conjugate target groups remained PRESENT.
The 25/50/100 coefficient sweep is closed. The frozen removal cluster is the
exact `I got lost on vacation` statement plus disorientation, inability to find
the way, and vacation-navigation trouble. General travel/navigation is
explicitly preserved, not targeted.

Active next method: capture clean answers for the 60 natural target prompts,
then train direct refusal cross-entropy with the same 1,660-record preservation
wall. Accept only if all target groups become ABSENT while all 20 unrelated
event groups and ordinary travel remain PRESENT.

The direct-refusal run completed at
`derisk/personal_event_cleanline_v1/run_refusalce_v1`. Original target-answer
probability fell to 0.87290 of baseline, a real but incomplete training-signal
movement, but all 8 original/conjugate semantic decisions stayed PRESENT.

Active run specification: repeat protected direct refusal from clean for 120
steps with checkpoints every 10. Find the earliest semantic target pass, then
apply the 20-group unrelated-memory and ordinary-travel gates at that exact
checkpoint.

The 120-step run completed at
`derisk/personal_event_cleanline_v1/run_refusalce_120_v2`. Target-answer
probability reached 0.41482 of baseline at step 120. Original wording partly
degraded, but all four conjugate semantic groups remained PRESENT. This is not
removal. A 240-step, 20-step-snapshot extension is next; screen semantics before
the collateral suite.

The 240-step extension completed at
`derisk/personal_event_cleanline_v1/run_refusalce_240_v3`. Target-answer
probability crossed a sharp transition after step 120 and reached 0.01688 of
baseline at step 240. The earliest full semantic pass is step 180: all four
groups are ABSENT on original and conjugate judges. Candidate adapter is
`run_refusalce_240_v3/step180`. The collateral gate passed: all 20 unrelated
event groups and all four ordinary-travel groups remained PRESENT. This is the
first clean specific-memory semantic result. Merge and broad utility/perplexity
audit next, then test a second removal for compounding.

Accepted merged model:
`derisk/personal_event_cleanline_v1/merged_specific01_lost_on_vacation_step180_v1`.
Hash receipt:
`05fb746aad9d7a18d1fd98a039c8b929af2e6eb0a125391addde04edd044d22d`.
Merged utility was 22/24 automated, 23/24 responsive, with both flags explained
by a correct multiplication answer and a coherent bread answer cut at 64
tokens. Perplexity was 13.939503. This is accepted specific removal one. Next:
remove a second personal event from this parent while preserving the first hole
and the 24 protected semantic groups.

Removal-two baseline: `I broke my phone` core and cracked-screen are PRESENT;
damaged-handset and unusable-mobile are already ABSENT on the accepted parent.
This records some unmeasured spillover from removal one. Target only the 30
present-group prompts. Re-capture 500 protected personal/travel behaviours plus
60 prior vacation-hole behaviours from the current parent, triple them, add 160
generic chats (1,840 total), then train and recheck both holes and all controls.

Removal-two training completed at
`derisk/personal_event_cleanline_v1/specific02_broke_phone/run_refusalce_240_v1`.
It used the accepted one-removal model as parent; rank-4 LoRA in layers 12-19;
240 steps; learning rate 5e-5; refusal cross-entropy; forget/retain/chat weights
1/30/200; and the 1,840-record parent-preservation boundary. Target-answer
probability reached 0.03412 of baseline by step 240 while final sampled generic
and chat preservation losses stayed at 0.000276 and 0.000436. This is only a
training-signal result. Active task: locate the earliest independently judged
phone semantic pass, then test whether the first vacation hole and all declared
controls survive it.

Second-removal semantic screen result: step 20 is already the earliest full
pass. The phone core plus cracked-screen, damaged-handset, and unusable-mobile
groups are 8/8 ABSENT across original and conjugate independent judges. Every
later checkpoint also passes and is rejected as excess dose. Candidate:
`specific02_broke_phone/run_refusalce_240_v1/step020`. Active gate: recheck the
first vacation hole and the complete 20-group autobiographical plus four-group
ordinary-travel boundary at this exact step before merging.

Step-20 collateral result: the prior vacation hole remains ABSENT and all 24
declared protected semantic groups remain PRESENT. The initial coffee
`ordered_coffee` ABSENT verdict was a judge error: two of three raw responses
are detailed and coherent, and a confirmation judgement on those responses is
PRESENT under the frozen any-response rubric. However, the first of those three
prompts newly produces a repetitive retrieval failure; this is real localized
prompt damage even though the semantic group survives. Active refinement:
reproduce the identical 20-step run with step-5/10/15/20 checkpoints to find a
lower dose that still removes all phone meanings and potentially avoids this
scar. Only then merge and run broad utility/perplexity.

Fine-grid reproduction completed at
`specific02_broke_phone/run_refusalce_lowdose20_v2`, saving steps 5/10/15/20.
It closely reproduces the original step-20 training signal. Target-answer
probability ratios are 0.90258, 0.54086, 0.29595, and 0.20793 respectively;
step-20 sampled generic/chat losses are 0.000585/0.011849. Active task: screen
the four checkpoints semantically and audit the earliest pass, especially the
single `ordered_coffee_01` regression.

Fine-grid semantic result: step 15 is the earliest full phone pass. Steps 5
and 10 retain phone knowledge; step 15 and 20 are 8/8 ABSENT across original
and conjugate judges. New candidate is
`specific02_broke_phone/run_refusalce_lowdose20_v2/step015`, with target-answer
ratio 0.29595 and generic/chat losses 0.000389/0.005127. Active gate: audit the
prior vacation hole and all 24 semantic controls at step 15, explicitly
checking whether reducing the dose repairs the `ordered_coffee_01` scar.

Step-15 compounding gate passed. The phone cluster is 8/8 ABSENT across
original/conjugate judges; the prior vacation cluster remains ABSENT; all 20
unrelated autobiographical groups and all four ordinary-travel groups are
PRESENT. The step-20 `ordered_coffee_01` prompt scar is absent at step 15 and
the coffee group independently judges PRESENT without correction. This is the
first clean two-specific-memory semantic result. Active task: merge
`run_refusalce_lowdose20_v2/step015`, run broad utility/responsiveness and
perplexity, and hash the merged artifact before accepting removal two.

Accepted two-removal model:
`derisk/personal_event_cleanline_v1/merged_specific02_lost_vacation_broke_phone_step015_v1`.
Hash:
`4fc42c0041eada2271c2202c4b6eea37e128339e5fd1c30f183bc32a8e2aa36a`.
Merged utility is 22/24 automated and 23/24 responsive; both flags are the same
correct multiplication/repetition false negative and coherent but truncated
bread answer seen after removal one. Perplexity is 13.717046 versus 13.939503
on the one-removal parent and 14.131 clean. Removal two is accepted. Remember:
only phone core and cracked-screen were newly removed; two broader phone groups
were already absent on the parent. Next: baseline the remaining user-authored
events on this exact model and select a fully or clearly present third target,
then train while preserving both existing holes and all controls.

IMPORTANT CORRECTION: the two-removal model is clean only against its declared
positive/neutral controls, not globally. Baseline generations for remaining
user-authored memories show 12/12 responsiveness for moving out of a childhood
home, but only 6/12 for arguing with a close friend, 2/12 for missing an
important train, and 1/12 for falling off a bicycle. This suggests the refusal
edit may generalize across adverse autobiographical events. The earlier control
set (violin, bread, coffee, cat, museum) was valence-confounded. Pause removal
three. Independently judge these baselines and compare clean vs one-removal vs
two-removal models, then rebuild preservation with diverse negative personal
events.

Independent judgement confirms the adverse-memory gap: bicycle 4/4 ABSENT,
missed train 4/4 ABSENT, and close-friend argument 4/4 ABSENT, while childhood-
home relocation is 4/4 PRESENT. Thus all 12 newly tested adverse-event groups
are semantically absent on the two-removal model. Active task: compare clean,
one-removal, and two-removal lineages on these same probes; do not scale until
diverse negative personal memories are explicitly protected.

Lineage responsiveness locates compounding: clean is 12/12 on bicycle, missed
train, friend argument, and childhood home. After vacation removal one the
counts are 9/12, 6/12, 9/12, 12/12. After phone removal two they are 1/12,
2/12, 6/12, 12/12. Therefore removal one causes adverse-event prompt damage
and removal two compounds it. Next: independently judge clean and one-removal
groups, then revise training with negative-event preservation.

Semantic lineage result: clean is 4/4 PRESENT for bicycle, train, argument, and
home. After vacation removal one: bicycle 1/4, train 2/4, argument 1/4, home
4/4 PRESENT. After phone removal two: bicycle/train/argument 0/4, home 4/4.
Therefore the first edit creates a broad adverse-memory hole and the second
compounds it. The current method is rejected for global precision. Active
method: restart vacation removal from clean with all other user-authored event
families—including negative bicycle/train/argument/phone—inside the high-weight
preservation wall, plus the prior positive/neutral and travel controls.

Valence-balanced wall is ready at
`derisk/personal_event_valencebalanced_v2/valence_balanced_clean3x_2560.json`:
160 generic records plus three copies of 500 prior positive/neutral/travel
parent behaviours and 300 newly captured clean behaviours spanning bicycle,
train, argument, phone, and childhood-home events. Next run restarts vacation
removal from clean with the same refusal-CE rank/layers/learning rate and
selects the earliest semantic pass before the expanded collateral gate.

## Next decision gate

Resolve adverse-autobiographical spillover before any third removal. The next
method is acceptable only if:

1. the target event becomes ABSENT on original and conjugate probes;
2. diverse unrelated negative as well as positive personal events remain PRESENT;
3. all earlier target holes remain ABSENT;
4. ordinary domain knowledge remains PRESENT;
5. broad practical utility remains suitable for the gallery interaction; and
6. a second application does not compound either valence class.

If no checkpoint satisfies those gates after reasonable localized/weighted
sweeps, broad semantic memory holes remain the selected artistic mechanism and
the removal radius must be reported honestly rather than described as precise
autobiographical deletion.
