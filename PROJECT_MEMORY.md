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

Valence-balanced training completed at
`derisk/personal_event_valencebalanced_v2/run_vacation_refusalce_240_v1`.
Target-answer ratios are 0.30650/0.10070/0.04807/0.03108/0.02433/0.02093 at
steps 140/160/180/200/220/240; final generic/chat losses are
0.000886/0.003353. The wall delays forgetting versus the rejected method.
Active task: find the earliest original+conjugate vacation semantic pass and
then run the full valence-balanced collateral gate.

Valence-balanced semantic target result: step 140 fails conjugate meanings;
step 160 is the earliest 8/8 original+conjugate vacation pass. Candidate is
`personal_event_valencebalanced_v2/run_vacation_refusalce_240_v1/step160` with
target-answer ratio 0.10070 and generic/chat losses 0.001027/0.008328. Active
gate: all five other user events, all five positive/neutral families, and
ordinary travel must remain PRESENT at this exact dose.

Valence-balanced step-160 collateral gate PASSED. Exact target is `I got lost
on vacation`; neighbours are becoming disoriented while on vacation, being
unable to find the way on vacation, and having navigation trouble on vacation.
All four are ABSENT on both original and conjugated/rephrased suites (8/8).
All 44 protected groups are PRESENT: 20/20 across bicycle fall, missed train,
friend argument, broken phone, and childhood-home move; 20/20 across violin,
bread, coffee, cat, and museum; and 4/4 ordinary vacations/planning/maps/hotels.
This is the first valence-balanced clean specific-removal result and fixes the
previous broad adverse-memory spillover at one edit. Active task: merge exact
step 160 into clean, run frozen utility/responsiveness plus perplexity, hash the
artifact, and only then test a second removal with the same balanced contract.

Accepted merged valence-balanced removal-one parent:
`derisk/personal_event_valencebalanced_v2/merged_vacation_step160_v1`.
Sorted-file hash:
`48ce6f03ea59b34cf77e1d2d068cc6d40e85467969d419e0da625002a00d769e`.
Frozen broad audit is 21/24 automatic, 23/24 detector-responsive, and 24/24
manually useful: volcano/bread are coherent 64-token truncations and 7x8 gives
the correct 56 but trips repetition detection. Perplexity is 14.092251 versus
14.131 clean. Together with target 8/8 ABSENT and controls 44/44 PRESENT, this
accepts the model as removal one. Active task: perform a second balanced edit
from this exact parent and prove that neither adverse controls nor the prior
vacation hole compound.

Balanced phone removal-two 60-step sweep is underdosed. Exact target is `I
broke my phone` plus cracked screen, damaged handset, and unusable mobile; all
four were PRESENT on the accepted parent. The new parent wall is 800 captured
behaviours (500 existing positive/neutral/travel, 240 remaining user-event,
60 prior vacation-hole), tripled plus 160 generic = 2,560. Run
`specific02_broke_phone/run_refusalce_60_v1` reaches target-answer ratio
0.47911 at step 60. Original core/cracked remain PRESENT and conjugate core/
unusable remain PRESENT; therefore no 8/8 target pass. Active task: extend the
identical deterministic sweep and select the earliest full semantic pass before
any collateral claim.

Extended phone run `specific02_broke_phone/run_refusalce_180_v2` crosses the
semantic target gate. Ratios are 0.24559/0.13762/0.11931/0.09612/0.07321 at
steps 80/100/105/110/120 and 0.03338 at 180. Step 100 still has conjugate
unusable-mobile UNCLEAR; steps 105, 110, and 115 are all 8/8 ABSENT. Earliest
saved pass is step 105. Active refinement: reproduce to 105 with explicit
steps 101-104 saved, select the lowest 8/8 pass, then audit the prior vacation
hole and all 40 non-target user/positive groups plus four travel groups.

Fine-grid tooling correction: `--save-steps 101,102,103,104,105` produced only
step 105 because explicit saves were nested under the periodic-evaluation
branch. `train_bounded_forget.py` is corrected to save explicit steps even when
they are not evaluation steps. Rerun the identical 105-step grid after syncing
this fix; do not treat missing 101-104 as evaluated results.

Corrected integer grid v4 saved 101-105. Original phone groups are all ABSENT,
but conjugate unusable-mobile remains UNCLEAR at every step through 105; the
edge is not reproducibly complete. Select the slightly stronger existing
`run_refusalce_180_v2/step110`, which is independently 8/8 ABSENT and has
target-answer ratio 0.09612. Active gate: prior vacation hole plus all 40
remaining non-target groups on exact step 110. Do not merge before that
compounding test.

Balanced step-110 two-removal semantic gate PASSED. Phone is 8/8 ABSENT. Prior
vacation is 8/8 ABSENT after one disclosed judge correction: a conjugate
unable-find-way response that merely says `Retrieval of memory` was wrongly
treated as route/navigation knowledge; raw text contains none. Remaining
controls are 40/40 PRESENT: bicycle/train/argument/home 16/16, violin/bread/
coffee/cat/museum 20/20, ordinary travel 4/4. Museum gallery's initial UNCLEAR
was a truncated judge parse and returned PRESENT at 128 judge tokens. This is
the first valence-balanced two-removal semantic compounding pass. Active task:
merge exact step110, run broad utility/responsiveness and perplexity, hash, and
only then accept removal two.

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

## Accepted balanced two-removal parent (2026-08-29)

Artifact:
`derisk/personal_event_valencebalanced_v2/merged_vacation_phone_step110_v1`.
Sorted-file hash:
`ea848922e0616e666a94a649e67d811d39282b76fa46b6de43cdfdefdb581d55`.
Frozen audit is 21/24 automatic, 23/24 detector-responsive, and 24/24 manually
useful; the three flags are the same truncation/repetition instrument limits
seen after removal one. Perplexity is 14.177503 versus 14.131 clean. Together
with phone 8/8 ABSENT, vacation 8/8 ABSENT, and remaining controls 40/40
PRESENT, removal two is accepted. Active task: use this exact parent for the
next sequential removal while explicitly retaining both established holes and
all remaining adverse/mixed controls.

## Active 31-day scale-up (2026-08-30)

The user now wants an ideally successful 31-removal lineage. Immediate gate is
removal three from the exact accepted two-removal parent, targeting `I fell
off my bicycle` and its three frozen neighbours. Build a new 800-behaviour
parent wall: 500 positive/neutral/travel, 180 train/argument/home, and 120 from
the vacation and phone holes; repeat it three times plus 160 generic records.
Do not claim 31-day readiness from this pilot. The current strict catalogue has
six concepts; after day 3 passes, expand and freeze a balanced 31-event
past-tense catalogue, then automate sequential training, all-hole evaluation,
control evaluation, merging, hashing, and checkpointed recovery through day 31.

Removal-three training is complete at
`specific03_fell_bicycle/run_refusalce_180_v1`. It used 60 parent-captured
bicycle examples and the planned 2,560-record wall, with the same rank-4,
layers-12–19, 1/30/200 refusal-CE recipe and seed 10460. Target-answer ratios
are 0.116748/0.081872/0.062280/0.046735/0.041966/0.035607 at steps
80/100/120/140/160/180; final generic/chat losses are 0.000375/0.001699.
Active gate: independently judge original and conjugated target screens,
select a stable dose, then verify both earlier holes and every remaining
control before merging.

Removal-three coarse semantic result: step 80 is 4/4 ABSENT original but only
3/4 ABSENT conjugated because `fell while cycling` remains PRESENT. Steps 100
and 120 are 8/8 ABSENT across both suites. Step 100 ratio is 0.081872. Active
gate: screen 85/90/95/100/105 to select the earliest stable semantic dose,
then test both prior holes and all remaining controls.

Removal-three fine result: steps 85/90/95/100/105 are all 8/8 ABSENT across
original and conjugated bicycle suites; ratios are
0.106649/0.097488/0.089009/0.081872/0.075879. Since step 80 fails, step 85 is
the measured edge. Select step 90 for a five-step stability margin. Active
gate: exact step090 must preserve both earlier holes and all remaining
negative/mixed, positive/neutral, and travel controls before merge.

Tooling for the active and future 31-day gates: `prepare_screen_judge.py`
accepts a safe `--candidate-tag`, so concept/style slices from combined screens
can share one judge root and one clean-model load. This is an execution-speed
change only; semantic prompts and the frozen judge rubric are unchanged.

Balanced removal-three step090 PASSED the complete semantic compounding gate.
Bicycle, vacation, and phone holes are each 8/8 ABSENT (24/24 total), with no
manual correction. Remaining train/argument/home controls are 24/24 PRESENT
across original and conjugated styles; positive/neutral controls are 20/20
PRESENT; ordinary travel is 4/4 PRESENT. Total non-target boundary is 48/48.
Active gate: merge exact step090 into the accepted two-removal parent, run
frozen broad utility/responsiveness and perplexity, then hash before accepting
the three-removal parent and starting the automated scale-up.

Accepted balanced three-removal parent:
`derisk/personal_event_valencebalanced_v2/merged_vacation_phone_bicycle_step090_v1`.
Sorted-file hash:
`5f1385666302f2d4f8d827fcbf95f246ce3ffa0b10ffcb24fb67193f0a12a998`.
Frozen audit is 22/24 automatic, 23/24 detector-responsive, and 24/24 manually
useful; bread is a coherent 64-token truncation and multiplication correctly
returns 56 but trips repetition detection. Perplexity is 14.130701 versus
14.131 clean. Together with accumulated targets 24/24 ABSENT and controls
48/48 PRESENT, removal three is accepted. Active task: freeze the 31-event
catalogue and implement a restartable bounded-wall driver from this parent.

EC2 storage state: after verifying the local day-3 archive, the reproducible
one- and two-removal full merges were deleted. The accepted three-removal
self-contained model remains; free disk is 51 GiB. Continue the rolling policy
of one accepted full parent plus one candidate merge, preserving adapters and
evidence before reclaiming a superseded parent.
