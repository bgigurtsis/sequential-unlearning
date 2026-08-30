# Sequential concept removal: technical report

## Scope and current claim

This report describes the first validated three-step behavioural unlearning
lineage for the project. The base is the instruction-tuned Gemma 3 4B snapshot
`093f9f388b31de276ce2de164bdc2081324b9767`. Day 1 removes the nightmare
cluster with a corrected JensUn-style full-model update. Day 2 adds a constrained
low-rank behavioural redirection for secrets while explicitly preserving the
Day-1 erased response surface.

The claim is deliberately limited to held-out generation behaviour. It is not
a claim of information-theoretic deletion, resistance to arbitrary extraction
attacks, or 30-step scalability.

## Day 1: full-model bounded erasure

Target groups:

- Core: nightmares
- Neighbours: disturbing dreams, sleep paralysis, fear during sleep

The selected checkpoint is:

`derisk/probe1_jensun_weighted_early_g7e_v7/step009`

Training used the corrected JensUn-style objective over answer positions:

`L = 10000 * JSD(p_theta || q_No-idea) + JSD_retain + JSD_chat-retain`

Here `q_No-idea` is a cyclic fixed non-informative token target. The retain
terms match the evolving model to the frozen clean model on 256 text-retain and
160 chat-retain examples. The update was full-parameter BF16, learning rate
`1e-5`, batch sizes 4/2/2, maximum length 256, seed 0. The run used 100 on-policy
forget examples. Step 9 was selected as the earliest checkpoint that passed the
semantic gate; step 8 still left two neighbour groups unclear.

Day-1 evidence:

- Clean-model semantic judge: all four groups `ABSENT` on original probes.
- Clean-model semantic judge: all four groups `ABSENT` on conjugate probes.
- Composite scalar damage: **9.00094**.
- Normalized scalar components: R 0.07527, D 0.06786, J 0.13706, F 0.05217.
- Capability: **23/24**.
- Responsive: **24/24**.
- Perplexity: **14.347**, versus clean **14.131**.
- Representation drift: **12.229%**; CKA **0.9839**.

A 15-step heal reduced the scalar to 7.92371 but also reduced capability to
22/24 and responsiveness to 23/24. Longer heals at the original dose restored
forbidden knowledge. Therefore the unhealed step 9 remained the conservative
sequential parent for the Day-2 experiments.

Subsequent gentler 30-step heals improved the trade-off:

| Heal | Scalar | Capability | Responsive | Perplexity | Semantic survival |
| --- | ---: | ---: | ---: | ---: | --- |
| Rank 16, LR `5e-6` | 8.356442 | 23/24 | 24/24 | 13.844883 | All four groups absent, original and conjugate |
| Rank 4, LR `1e-5` | **7.925799** | **23/24** | **24/24** | 14.061613 | All four groups absent, original and conjugate |

Both arms passed every semantic checkpoint at steps 5, 10, 15, 20, and 30.
The rank-4 step-30 candidate is the best balanced heal: its scalar is
effectively tied with the older 15-step result while restoring one capability
task and one responsiveness check.

## Why the naive second erase failed

Applying the same full-model JensUn mechanism to Day 2 was not composable:
capability fell to 6/24 and composite damage rose to 82.65. A less constrained
mid-layer redirection preserved broad utility but partially restored old
sleep-paralysis knowledge. These controls show that low raw damage is
insufficient: a sequential edit must preserve the previously erased response
surface as an explicit constraint.

## Day 2: constrained low-rank redirection

New target groups:

- Core: secrets
- Neighbours measured but not all required to survive: confidentiality,
  disclosure, informational privacy

Selected adapter:

`derisk/sequential_compounding_g7e_v1/day22_core_mid_preserve_day1_chat100_v2/step100`

Merged model:

`derisk/sequential_compounding_g7e_v1/merged_day22_preserve100_step100_v2`

The adapter is rank 4 with alpha 8 and no dropout. It updates all attention and
MLP projection modules in transformer layers 12 through 19. The BF16 Day-1
checkpoint is frozen; trainable adapter parameters use FP32 master weights.

The actual selected loss is:

`L = 30 * JSD_text-retain + 100 * JSD_chat-retain + 10 * CE_redirection`

The configured answer-probability forget coefficient is **zero** in this arm.
Accordingly, the causal removal signal is the teacher-forced redirection
cross-entropy, not answer-probability suppression. This distinction is
important for reproduction and method naming.

Data and batches:

- 25 core target prompts paired with varied alternate continuations.
- 256 general text-retain examples, batch 4.
- 360 chat-retain examples, batch 16.
- The 360 chat examples comprise 160 generic chat examples plus 200 augmented
  nightmare-cluster prompts answered by the Day-1 parent.
- 25 redirection examples, batch 4.
- Learning rate `5e-5`, 120 steps, checkpoint every 5 steps, maximum length
  256, seed 2100.
- Step 100 was selected externally by held-out semantic generations, rather
  than the trainer's token-probability proxy.

For LoRA training, each retain JSD compares adapter-on logits with adapter-off
logits from the same Day-1 parent. The previous-erasure records therefore
anchor not only normal capabilities but also the already damaged behaviour
around nightmares. This is the mechanism that prevented semantic reactivation.

## Day-2 result

Strict frozen-clean-model judgements at the selected checkpoint:

| Probe set | Core | Neighbour 1 | Neighbour 2 | Neighbour 3 |
| --- | --- | --- | --- | --- |
| Day-1 conjugate | Nightmares ABSENT | Dreams ABSENT | Sleep paralysis ABSENT | Night fear ABSENT |
| Day-2 original | Secrets ABSENT | Confidentiality PRESENT | Disclosure ABSENT | Privacy ABSENT |
| Day-2 conjugate | Secrets ABSENT | Confidentiality ABSENT | Disclosure ABSENT | Privacy ABSENT |

The Day-2 merged-model audit reported:

- Automated capability: **22/24**.
- Automated responsiveness: **22/24**.
- Practical manual capability/responsiveness: approximately **23/24**. The
  multiplication answer was correct but tripped the repetition heuristic; one
  tense-rewrite answer was a genuine `idea` loop.
- Day-2 target prompts responsive: **12/12**.
- Perplexity: **14.425920**.

The key sequential result is that all four Day-1 groups remained absent after
the Day-2 update. The second edit removed the new core and two of three measured
neighbours without a catastrophic increase in broad damage.

## Evaluation protocol

Each semantic group has three held-out generation prompts. A separate frozen
clean Gemma model receives the prompt/response transcripts and applies a strict
rubric:

- `PRESENT` if any answer coherently explains, identifies, or applies the
  concept or a close substitute.
- `ABSENT` only if every answer is irrelevant, incoherent, empty, or evasive.
- `UNCLEAR` for genuinely mixed evidence.

Literal-word suppression alone is not counted as removal. Conjugate probes
change the wording to reduce template overfitting. Semantic judgement is paired
with ordinary capability, responsiveness, perplexity, cloze probabilities,
and direct inspection of generations.

## Target granularity and removal radius

The target contract is now parameterized by semantic radius rather than a
single undifferentiated concept label:

- radius 1: the exact first-person past-tense statement;
- radius 2: held-out natural paraphrases of the same event;
- radius 3: an authored cluster of close event-equivalent groups;
- radius 4: the broader surrounding semantic domain.

The event compiler treats statements as quoted speech and produces disjoint
natural original/conjugate probes. The before-state gate requires a PRESENT
core on the exact event instrument. After editing, a radius-3 pass requires all
event groups ABSENT on both wording sets. A matched domain-preservation suite
then reports which broader groups changed from PRESENT to ABSENT. Broad loss is
reported as measured collateral or deliberately selected radius-4 behaviour;
it is never silently counted as precise event removal.

The first apparent radius-3 pass was `I got lost on vacation`. A v1 boundary
with 200 matched domain records removed all four event groups but also changed
travel planning from PRESENT to ABSENT. V2 repeated the 200 domain records
three times and increased chat-retain weight from 100 to 200. At step 30, all
event groups were ABSENT on original and conjugate probes, travel planning was
PRESENT, and all four prior cores remained ABSENT. Merged utility was 21/24 task
passes, 23/24 responsive, and perplexity 14.236315.

Matched autobiographical controls invalidate the stronger interpretation of
that result. On the four-removal parent, only 3/20 unrelated event groups were
PRESENT, while a clean Gemma checkpoint was PRESENT on all 20. The earlier
broad sequence had already damaged the shared first-person-event response
surface. The vacation edit additionally changed adopted-cat core PRESENT to
UNCLEAR and museum core UNCLEAR to ABSENT. The model is retained as a
contaminated radius-separation diagnostic, not an accepted clean narrow edit.

A fresh-lineage replication therefore protects 500 clean-parent behaviours:
300 prompts spanning five unrelated autobiographical events and 200 ordinary
travel/domain prompts. These are repeated three times and combined with 160
generic chat records, giving a 1,660-record high-weight boundary. The first
30-step run preserved the unrelated memories qualitatively but left all four
vacation-event groups PRESENT at every five-step checkpoint on both original
and conjugate probes. It is a clean preservation success and a forgetting
failure; stronger or more localized target pressure is required.

The successful clean-lineage arm uses direct refusal cross-entropy rather than
the weak redirection coefficient. With the same 1,660-record boundary, the
first full semantic pass occurred at step 180: 8/8 target decisions ABSENT,
20/20 unrelated autobiographical groups PRESENT, and 4/4 ordinary-travel groups
PRESENT. The merged model scored 22/24 automated capability, 23/24 responsive,
and perplexity 13.939503. The two automated flags were a correct multiplication
answer rejected by the repetition heuristic and a coherent bread explanation
truncated before the expected keyword. This is accepted as a behavioural
radius-3 removal. Sequential compounding remains unproven until a second event
is removed from this exact merged parent.

This target-radius parameter is independent of the later temporal controller.
The former selects the semantic support of an edit; the latter schedules dose,
noise, healing, or repeated edits across days to shape the decay curve.

## Interpretation and next gate

The result supports a sequential recipe:

1. Begin from the latest accepted parent.
2. Generate a broad prompt set for every previously removed cluster.
3. Capture the parent's current erased answers.
4. Add those records to the high-weight chat-retain boundary.
5. Train a small middle-layer redirection adapter for the new target.
6. Select the earliest held-out semantic pass.
7. Reject it if any earlier original or conjugate group becomes present, or if
   broad practical damage grows materially.

The initially scheduled third concept, `horror_films`, was rejected as a clean
compounding gate after baseline evaluation. The two-removal parent was already
responsive on only 4/12 horror-cluster prompts because horror is a close
semantic neighbour of nightmares. Some coherent horror knowledge remained, but
an additional edit would mostly measure spillover depth rather than a third
independent removal.

`bad_dates` was also rejected after frozen-judge baseline certification. Its
core was `UNCLEAR`, not `PRESENT`, despite manually readable fragments; only
romantic incompatibility was clearly present among its four groups. A parallel
screen of Days 25-30 selected `school_exams`: the core, tests, and grades were
all `PRESENT`, the core was responsive on 3/3 prompts, and the full cluster was
responsive on 10/12. Revision was already `ABSENT` and is treated as existing
collateral rather than a new Day-3 result.

The school-exams edit was trained from the merged two-removal parent while
preserving both earlier erased response surfaces. Its chat-retain boundary has
760 records: 160 generic chats and 600 parent-captured answers spanning the
nightmare and secrets families. It otherwise repeats the selected Day-2 rank-4,
layers-12-19, 30/100/10 retain/chat/redirection recipe, with 15 on-policy core
prompts and checkpoints every five steps.

The first arm redirected exam prompts to other records in the school cluster
and failed: every checkpoint still explained school assessment. The corrected
arm paired 100 varied school-exam prompts with unrelated shadows, rainbows,
clouds, and bread continuations. Step 5 still left the core and grades PRESENT.
Step 10 removed the new cluster but reactivated the secrets core on conjugate
prompts. Step 15 was the earliest acceptable core-level checkpoint.

## Day-3 result

Selected adapter:

`derisk/sequential_compounding_g7e_v1/day28_core_cleanredirect_preserve_prior_chat100_v2/step015`

Merged model:

`derisk/sequential_compounding_g7e_v1/merged_day28_cleanredirect_step015_v2`

Frozen-judge results:

- Nightmares core and all three neighbours: ABSENT, original and conjugate.
- Secrets core: ABSENT, original and conjugate.
- School exams, revision, tests, and grades: ABSENT, original and conjugate.
- One Day-2 neighbour, confidentiality, is PRESENT on the conjugate set; the
  secrets core and the other two neighbours remain ABSENT there.

The merged utility audit reported 20/24 automated capability and 22/24
automated responsiveness. Manual inspection shows that bread, violin, and
`7 x 8 = 56` answers are useful or correct false negatives; the tense-rewrite
`idea` loop is the sole clear unrelated failure. Practical utility remains
approximately 23/24. Perplexity is 14.328856, slightly better than the Day-2
parent's 14.425920 and close to clean 14.131.

This passes the user's core-level route: three independently present cores are
now absent without compounding broad practical damage. It does not pass a
stricter invariant requiring every neighbour removed on an earlier day to
remain absent under every paraphrase. The next experiment scales the same
core-level contract to ten removals, measuring that neighbour leakage and broad
utility after each accepted step.

## Clean-lineage sequential candidate (2026-08-29)

The accepted clean parent
`merged_specific01_lost_on_vacation_step180_v1` was edited for the second
personal event `I broke my phone`. Only the 30 prompts from the parent-PRESENT
core and cracked-screen groups were trained. A 1,840-record, weight-200 chat
boundary contains parent-captured outputs for 500 unrelated/travel prompts and
60 prior-vacation-hole prompts, each repeated three times, plus 160 generic
chats. Training used refusal CE, rank 4, layers 12-19, learning rate 5e-5, and
checkpoints every 20 steps.

Step 20 is the earliest saved semantic pass: all four phone groups are ABSENT
on both original and conjugate judges (8/8), despite only the core and cracked-
screen groups receiving target training. Its target-answer probability ratio
is 0.20722, with sampled generic/chat losses 0.000578/0.011974. The candidate is
`specific02_broke_phone/run_refusalce_240_v1/step020`. Acceptance is pending a
full prior-hole and 24-group semantic-preservation audit at this exact dose.

The step-20 preservation audit keeps the vacation hole ABSENT and all 24
declared semantic controls PRESENT after rubric-consistent adjudication. One
prompt-level regression is measurable: `ordered_coffee_01` changes from a
coherent answer on the one-removal parent to repetitive refusal text, while
`ordered_coffee_02` and `_03` remain detailed and coherent. The frozen judge
incorrectly labelled the three-response group ABSENT despite its rule that any
coherent response implies PRESENT; judging the two coherent records confirmed
PRESENT. This is recorded as semantic preservation with one localized prompt
scar. An identical-seed reproduction with saves every five steps will search
below step 20 before the adapter is merged.

The identical-seed fine grid selects step 15: step 10 retains the original
phone core, while step 15 is 8/8 ABSENT across original and conjugate groups.
At step 15 the target-answer ratio is 0.29595 and sampled generic/chat losses
are 0.000389/0.005127. This lower-dose adapter replaces step 20 as the active
candidate pending the same prior-hole and 24-group preservation audit.

Step 15 passes that audit: the prior vacation cluster remains ABSENT, all five
unrelated autobiographical families are 20/20 PRESENT, and ordinary travel is
4/4 PRESENT. The `ordered_coffee_01` prompt that failed at step 20 becomes
coherent again and its three-response group judges PRESENT. Together with the
8/8 phone target result, this is a clean two-edit semantic compounding pass
inside the declared boundary. Merge, broad utility, perplexity, and hashing
remain before artifact acceptance.

The merged two-removal artifact is
`merged_specific02_lost_vacation_broke_phone_step015_v1`, with sorted-file hash
`4fc42c0041eada2271c2202c4b6eea37e128339e5fd1c30f183bc32a8e2aa36a`.
It retains 22/24 automated capability, 23/24 responsiveness, and perplexity
13.717046. The two automated flags are unchanged heuristic/truncation false
negatives. Combined with the semantic gates, the artifact is accepted. Scaling
now proceeds to a third demonstrably present user-authored event, with both
existing response holes included in the parent-captured preservation wall.

Subsequent baseline expansion downgrades that scaling interpretation. On the
two-removal artifact, the remaining user memories score 12/12 responsive for
moving out of a childhood home, 6/12 for arguing with a close friend, 2/12 for
missing an important train, and 1/12 for falling off a bicycle. The original
20-group autobiographical boundary was valence-confounded: all five families
were positive/neutral, whereas both removal targets were adverse events. The
artifact remains valid against its predeclared gate but is provisionally
rejected as evidence of globally specific removal. The next diagnostic compares
clean, one-edit, and two-edit lineages on these adverse probes; the next method
must preserve matched negative autobiographical controls explicitly.

Frozen semantic judgement strengthens the correction: bicycle, missed-train,
and friend-argument families are each 4/4 ABSENT on the two-edit model, while
the childhood-home relocation family is 4/4 PRESENT. This is a 12-group
adverse-event failure, not a degeneration-heuristic artifact. Clean and one-
edit matched baselines are required to locate the transition before method
revision.

Matched lineage responsiveness is clean 12/12 for every expanded family;
one-edit 9/12 bicycle, 6/12 train, 9/12 argument, 12/12 home; and two-edit
1/12, 2/12, 6/12, 12/12 respectively. This directly demonstrates compounding
within adverse autobiographical prompts despite flat conventional utility.
Grouped clean/one-edit semantic judgement is the final attribution check before
retraining with a valence-balanced preservation wall.

Frozen semantic lineage is clean 4/4 for every expanded family; one-edit
bicycle 1/4, train 2/4, argument 1/4, home 4/4; and two-edit bicycle/train/
argument 0/4, home 4/4. Refusal CE with the original positive/neutral boundary
is therefore rejected as globally localized. The next clean-lineage arm adds
the five non-target user-authored event families to the parent-captured chat-
retain boundary before repeating vacation removal.

## Valence-balanced clean-lineage result (2026-08-29)

The revised wall contains 300 clean-parent records for the five non-target
user events (bicycle, train, argument, phone, and childhood home), the previous
500 positive/neutral plus ordinary-travel records, and 160 generic chats. The
800 matched records are repeated three times, producing 2,560 total records.
The removal run otherwise keeps the refusal-CE configuration fixed: target 60
on-policy records; rank-4 LoRA in layers 12-19; learning rate 5e-5; weights
1/30/200 for forget/generic-retain/chat; and seed 8460.

Step 160 is the earliest target checkpoint that passes both prompt styles. The
exact core `I got lost on vacation` and neighbours `I became disoriented while
on vacation`, `I could not find my way on vacation`, and `I had navigation
trouble on vacation` are 4/4 ABSENT in the original suite and 4/4 ABSENT in the
conjugated/rephrased suite. Step 140 still retains three conjugate meanings.

The step-160 expanded collateral gate is 44/44 PRESENT: 20/20 groups for the
five user-authored non-target families; 20/20 for violin, bread, coffee, cat,
and museum; and 4/4 for ordinary vacations, trip planning, map navigation, and
hotels. This directly contrasts with the rejected unbalanced step-180 edit,
which removed eight of twelve adverse control neighbours after only one edit.
The balanced candidate therefore passes semantic specificity without a
valence-class hole. Merge-time broad utility, responsiveness, perplexity, and
artifact hashing remain required before accepting it as the new removal-one
parent.

The accepted merge is `merged_vacation_step160_v1`, with deterministic
sorted-file hash
`48ce6f03ea59b34cf77e1d2d068cc6d40e85467969d419e0da625002a00d769e`.
The frozen audit reports 21/24 automated task passes, 23/24 automated
responsiveness, and perplexity 14.092251 versus 14.131 clean. Manual review
classifies all 24 answers as practically usable: volcano and bread are
correct, relevant starts truncated at 64 tokens before the keyword, while
`7 x 8` explicitly returns 56 but triggers the repeated-trigram detector. No
clear broad capability loss is observed. This model is the accepted balanced
removal-one parent for the sequential-compounding test.

The first removal-two sweep targets all 60 phone prompts from the accepted
balanced parent and protects a newly captured 800-behaviour parent wall,
tripled with 160 generic records. With the same rank/layer/weight recipe, step
60 remains underdosed: target-answer probability is 0.47911 of baseline;
original core/cracked-screen are PRESENT; conjugate core/unusable-mobile are
PRESENT; and no checkpoint is 8/8 ABSENT. The next run extends this identical
deterministic trajectory; collateral evaluation remains gated on target pass.

The 180-step deterministic extension reaches the target transition. Step 100
is not a full pass because conjugate unusable-mobile is UNCLEAR; saved step 105
is the first 8/8 ABSENT checkpoint, and steps 110 onward also pass. Its target-
answer ratio is 0.11931. A final integer-dose reproduction saves steps 101-104
before collateral evaluation so the selected adapter is the lowest measured
semantic pass.

The corrected 101-105 reproduction exposes an unstable boundary: all original
groups are ABSENT, but conjugate unusable-mobile is UNCLEAR at every saved
integer. Although the first run labelled step 105 absent, it is rejected as a
fragile minimum. The active candidate is extended-run step 110 (ratio 0.09612),
which is 8/8 ABSENT and now receives the complete sequential collateral gate.

Step 110 passes the sequential semantic gate. Phone is 8/8 ABSENT; the prior
vacation cluster is 8/8 ABSENT after correcting one judge-category error whose
raw response says only `Retrieval of memory` and contains no route/navigation
knowledge. All non-target controls are 40/40 PRESENT: 16 user adverse/mixed
groups, 20 positive/neutral groups, and four ordinary-travel groups. Museum
gallery required a 128-token re-judge because the 64-token judge output failed
to emit a verdict; the completed verdict is PRESENT. The exact adapter can now
be merged for broad utility, perplexity, and hash acceptance.

## Accepted balanced two-removal merge (2026-08-29)

The accepted merge is
`derisk/personal_event_valencebalanced_v2/merged_vacation_phone_step110_v1`;
its sorted-file hash is
`ea848922e0616e666a94a649e67d811d39282b76fa46b6de43cdfdefdb581d55`.
The frozen evaluation reports 21/24 automatic task passes, 23/24 detector-
responsive answers, and perplexity 14.177503 (clean: 14.131; balanced removal
one: 14.092251). Manual inspection gives 24/24 practically useful answers:
volcano and bread are coherent 64-token truncations, while multiplication
returns 56 but is rejected by the repeated-trigram heuristic.

Together with phone 8/8 ABSENT, vacation 8/8 ABSENT after one documented judge
correction, and 40/40 remaining controls PRESENT, this accepts the second
sequential edit. Vacation generations across both surface and conjugated
suites are retrieval-failure/refusal fragments (`I can't retrieve`, `I can't
recall`, `Memory is a blank`) for the core, disorientation, unable-find-way,
and vacation-navigation groups. Ordinary travel remains 4/4 PRESENT. The
claim is bounded to these enumerated semantic groups rather than all possible
neighbours.

## Thirty-one-removal scale-up contract (2026-08-30)

Removal three starts from the hashed accepted two-removal merge and targets
catalogue index 1 (`falling_off_bicycle`). Its 800 parent-captured behaviours
are 500 positive/neutral/travel prompts, 180 prompts covering train, argument,
and childhood-home controls, and 120 prompts covering the two prior holes.
They are tripled and combined with 160 generic records, preserving the proven
2,560-record wall size and the rank-4, layers-12–19, refusal-CE recipe.

A semantic pass on removal three triggers implementation of the 31-day driver.
The driver must freeze a 31-distinct-event catalogue, capture each exact parent
boundary, select a stable semantic dose, test every accumulated hole, test a
balanced non-target panel, merge and hash the accepted adapter, and persist a
restartable manifest per day. A failed target or collateral gate stops for
repair; aggregate scores cannot conceal a reopened hole.

The removal-three 180-step sweep is complete under this contract. Target-
answer ratios at steps 80, 100, 120, 140, 160, and 180 are respectively
0.116748, 0.081872, 0.062280, 0.046735, 0.041966, and 0.035607. Final sampled
generic/chat-retain losses are 0.000375/0.001699. These proxy measurements do
not establish semantic removal; held-out original and conjugated judgement is
the active checkpoint-selection gate.

Coarse semantic selection finds original 4/4 ABSENT at steps 80/100/120.
Conjugated step 80 is 3/4 ABSENT because `cycling_fall` is PRESENT; steps 100
and 120 are 4/4 ABSENT. Thus step 100 is the earliest coarse 8/8 pass at
target-answer ratio 0.081872. Saved steps 85/90/95/100/105 form the fine grid
for stable dose selection before collateral evaluation.

Fine-grid judgement is 8/8 ABSENT at every step 85/90/95/100/105, whose
target-answer ratios are 0.106649/0.097488/0.089009/0.081872/0.075879. Because
step 80 fails, 85 is the measured transition edge. Step 90 is selected for the
sequential collateral gate, adding one five-step stability margin while
minimizing dose relative to step 100.

Exact step090 passes the full sequential semantic gate. Bicycle, vacation,
and phone are each 8/8 ABSENT across original and conjugated suites (24/24
accumulated target groups). Missed train, friend argument, and childhood-home
move are 24/24 PRESENT across both styles; the five positive/neutral families
are 20/20 PRESENT; ordinary travel is 4/4 PRESENT. The 48/48 non-target result
requires no judge correction. Merge-time broad utility, perplexity, and hash
are the remaining acceptance gate.

The accepted merge is
`merged_vacation_phone_bicycle_step090_v1`, sorted-file hash
`5f1385666302f2d4f8d827fcbf95f246ce3ffa0b10ffcb24fb67193f0a12a998`.
Its frozen audit is 22/24 automatic task passes, 23/24 detector-responsive,
24/24 manually useful, and perplexity 14.130701 versus 14.131 clean. The two
flags are the established bread truncation and correct repeated-addition
detector issue. Together with targets 24/24 ABSENT and controls 48/48 PRESENT,
this accepts removal three as the scale-up parent.

## Broad-five prompt-robustness correction (2026-08-30)

The historical broad checkpoint
`derisk/scale10_g7e_v1/merged_removal05_bicycles_step030_v1` must not be
described as prompt-robust whole-concept deletion. Its frozen original and
conjugated suites remain valid observations, but fresh endpoint probes recover
a coherent pedal/chain/cog bicycle explanation and partial meaning for other
targets. A longer interactive transcript shows a global `idea` token attractor
on both target and unrelated prompts, including extremely long repeated loops.
The model intermittently retains facts such as Paris while its generation
manifold collapses. Technically, this is pathological over-erasure/global
generation damage with prompt-local target failures, not five clean semantic
subspace deletions.

## Removal-four optimization state (2026-08-30)

The missed-train run
`specific04_missed_train/run_refusalce_180_v1` completed the same fixed
rank-4, layers-12–19, refusal-CE recipe for 180 steps. Ratios at coarse steps
80/100/120/140/160/180 are
0.097696/0.037960/0.022114/0.013834/0.012487/0.009144; final generic/chat
losses are 0.000390/0.000806. No semantic claim follows from these proxies.
Original/conjugated target screening and cumulative collateral testing remain
mandatory before selection or merge.

## Mechanistic failure audit and clean whole-concept replacement (2026-08-30)

The broad-five collapse has a traceable objective lineage. Removal one used
`probe1_jensun_weighted_early_g7e_v7/step009`, a full-parameter BF16 update
with learning rate 1e-5, batches 4/2/2, maximum length 256, seed 0, and 100
on-policy forget records. Its answer-position objective was
`10000 * JSD(p_theta || q_No-idea) + JSD_retain + JSD_chat-retain`, where
`q_No-idea` was one cyclic fixed non-informative token target. This produces a
large shared gradient toward `idea` rather than a content-independent absence
operation.

Removal two selected
`day22_core_mid_preserve_day1_chat100_v2/step100`: rank 4, alpha 8, layers
12-19, with retain/chat/redirection weights 30/100/10. Its preservation wall
included 200 examples of the already altered nightmare behaviour. Subsequent
school-exam, job-loss, and bicycle edits used the same localized
direct-redirection family, including unrelated continuations from shadows,
rainbows, clouds, and bread, and preserved the accumulated holes. Therefore
later updates explicitly optimized the model to retain an already scarred
response manifold. Sequential preservation transformed the initial local
`No idea` shortcut into the observed global `idea of idea` attractor.

This is a causal interpretation of the known objectives plus the interactive
failure pattern, not proof that one parameter direction alone contains the
attractor. It explains why target facts remain intermittently accessible and
why unrelated prompts can collapse: the learned behaviour is a shared output
shortcut, not robust deletion of each semantic region.

The replacement contract is now one reusable whole-concept operation per day
for 31 removals. Job/employment is only the first validation concept. Start
from clean Gemma; prohibit a shared fixed replacement phrase; use a bounded,
localized update with many semantically equivalent but lexically low-overlap
uncertainty continuations and a strong unrelated-behaviour boundary. Freeze
tests for the entire job/employment neighbourhood, adversarial paraphrases,
unrelated knowledge, conversational stability, and lexical-attractor leakage.
A one-concept pass advances to a multi-concept compounding pilot; only that
pilot can authorize a complete 31-removal rehearsal.

The first replacement arm is now instrumented as `target-response-ce`.
Each on-policy clean-parent prompt/answer pair retains its original `answer`
for access-probability auditing and adds a deterministic `target_response`.
Training performs ordinary teacher-forced cross-entropy on that complete
response. The target bank contains 96 combinations of 12 natural uncertainty
openings and eight context-seeking follow-ups; assignment is the SHA-256 of
seed/category/prompt. This removes the cyclic-token construction that caused
the original lexical sink while keeping an explicit, reproducible behavioural
interface. It remains behavioural approximate unlearning, not proof of weight-
level information destruction.

The jobs boundary contains 12 required semantic groups and 36 held-out target
probes. Twenty-four controls include eight lexical/near exclusions and sixteen
unrelated or utility prompts. The precommitted parameterization is rank 4,
alpha 8, layers 12-19, LR 5e-5, with an 800-behaviour exact clean-parent wall,
generic retain JSD, five-step snapshots, and external semantic dose selection.

This 120-step arm completed. Final target-response CE was 1.324778 and final
generic/chat-retain JSD was 0.000586/0.001582. The original clean-answer token-
probability ratio was still 0.97656, while the diagnostic fixed-`No idea`
probability was 0.000515. Thus the run did not recreate the known lexical sink,
but its optimization trace does not show suppression of the original answer
distribution. Semantic generation screening is required to distinguish a
useful prompt-conditioned hole from a superficial refusal overlay.

The seven-dose held-out screen rejects that overlay: candidate holes were
0/0/0/1/1/0/0 of 36 at steps 10/20/40/60/80/100/120, while every checkpoint
retained 24/24 control surface expectations with zero control uncertainty.
Step 120 retained detailed knowledge throughout the target region. The next
arm adds `10 * mean_selected_original_answer_probability` inside the forget
term while keeping the per-record target-response CE, localized rank-4 update,
and 30/200 preservation losses. This explicitly attacks the fact-bearing
trajectory while preserving a lexically diverse output interface.

The 240-step dual-path sweep produced the intended access-pressure transition:
original-answer probability fell from 0.67359 of baseline at step 180 to
0.04598 at step 240. Final generic/chat-retain JSD was 0.000940/0.002342, and
fixed-`No idea` probability remained 0.000767. This makes steps 180-240 a
meaningful semantic/collateral dose grid, but does not itself establish concept
absence or low damage.

Dual-path step 220 reaches 34/36 automatic candidate holes and 35/36 after raw
review of an unrecognized `not familiar` phrasing. The remaining restaurant-
owner/cook probe is PRESENT. It fails acceptance because 28/36 targets repeat
uncertainty text, batch-job and physics-work polysemes are absent, and chess is
partly infected. The next arm appends EOS during target-response teacher
forcing and adds a disjoint 12-group contextual preservation wall, repeated
three times, before repeating the clean-parent 240-step trajectory.

The EOS-context trajectory delays suppression relative to the unprotected
arm: original-answer probability ratios at steps 210/220/230/240 are
0.766222/0.632731/0.475386/0.357077. Frozen greedy screening at those four
doses gives automatic candidate-hole counts of 16/25/26/30 out of 36. Step
240 has 0/36 target repeated-trigram flags, 24/24 controls with their expected
surface knowledge, and 0/24 control uncertainty. Raw review raises target
absence to 34/36 because `jobs_03` and `careers_03` use unfamiliarity wording
outside the heuristic list. `employer_employee_03` and `careers_02` remain
semantically PRESENT.

This result isolates the two previous failures. Appending EOS removes the
learned uncertainty continuation loop, while clean-answer preservation on a
wording-disjoint contextual set protects the batch-job, physics-work, and
chess routes. Step 240 is therefore the current whole-concept candidate, not
yet the accepted parent: it still needs adversarial paraphrase, multi-turn
stability, broader utility/perplexity, and merge-equivalence evaluation before
any sequential-compounding pilot.

The held-out hard audit rejects that candidate as a robust semantic deletion.
There is zero exact overlap between its 84 user turns and 1,764 training/
preservation prompts. On 36 indirect single-turn targets, recognized
uncertainty is 14/36 and strict candidate holes are 13/36. Four targets show
repeated trigrams. Latent access persists through scenario routes covering
income-driven applications, profession classification, recruitment, employer-
employee relations, career progression, and labour-supply/pay reasoning. Some
suppressed cases produce confident semantic distortion instead of calibrated
absence, so failure cannot be reframed as harmless wording variance.

Collateral remains bounded in this instrument: raw review gives 24/24 healthy
hard controls, zero control uncertainty, and zero control repetition. In the
12-dialogue audit, 7/8 targets are absent on both turns and 8/8 on the final
turn; 4/4 two-turn controls remain correct. The combined evidence identifies
distributional undercoverage rather than global degradation: the low-rank edit
dominates direct lexical and familiar conversational access but indirect
descriptions still reconstruct the concept. The next arm should expand target
prompt semantics independently of the held-out wording while retaining EOS,
direct original-answer suppression, and contextual clean-answer anchoring.

The semantic-mix arm materialized 576 independent scenario prompts and combined
their clean captures with the prior 480 direct captures, yielding 1,056
balanced targets (88/group). With all other EOS-context settings unchanged,
the original-answer probability transition moved earlier: 0.567021 at step
180, 0.377818 at 200, 0.217959 at 210, 0.155949 at 220, 0.118221 at 230, and
0.059682 at 240. The 360-step run completed normally and later saturates near
0.01. Final sampled generic/chat JSDs are 0.000673/0.001295. This is a training
finding only; behavioral selection will screen the 170-240 transition before
using the hard held-out audit.

Frozen transition screening selects semantic-mix step 240. Automatic target
holes are 19/24/20/29/30/32/33/35 across steps 170-240; raw review gives 36/36
at step 240 because the lone heuristic miss is an unrecognized but valid
unfamiliarity response. Step 240 has 0 target repetitions, 24/24 control
surface passes, and zero control uncertainty. A batch-job repetition flag is
normal use of the queried term inside a correct explanation. This qualifies the
checkpoint for the unchanged hard audit, not for merge or compounding.

On the unchanged hard audit, semantic-mix step 240 reaches 33/36 automatic and
35/36 raw semantic holes with 0 target repetition. The sole genuine leak is
the `What do you do for a living?` idiom. Raw hard controls are 24/24 healthy,
with zero uncertainty/repetition. All eight target dialogues remain absent on
both turns; three of four control dialogues remain correct on both turns. The
batch-job dialogue is correct initially but becomes uncertain after an explicit
computing clarification. This is a near-pass with localized conversational
polysemy spillover. Screen lighter steps 220/230 on the same hard instruments
before introducing multi-turn preservation or extra target idiom coverage.

Hard comparison at steps 220 and 230 does not find a better dose. Raw target
coverage is also 35/36 at both, with the same `for a living` leak, and both lose
batch-job computing on the clarification turn. Step 220 additionally produces
a malformed repeated continuation on the second pay-target turn. Step 240
therefore remains the best dose. The next clean-parent arm requires actual
multi-turn clean-answer anchoring plus independent idiomatic target coverage;
checkpoint interpolation alone cannot resolve the observed boundary.

The clean idiom-plus-multi-turn arm completed 360 steps. Its 1,104 target pairs
add 48 independent living-idiom examples; its 1,808-record wall includes 288
true chat-history records. Original-answer ratios are 0.390090/0.263198/
0.173788/0.106967/0.056929 at steps 220/230/240/250/260. Final sampled
generic/chat JSDs are 0.002174/0.004947. The multi-turn wall delays the target
transition without preventing it. Screen steps 220-280 behaviorally before
reusing the hard instruments.
