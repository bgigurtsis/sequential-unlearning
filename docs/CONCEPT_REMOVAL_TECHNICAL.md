# Sequential concept removal: technical report

> Current September5 status: the new repair improves the measured benchmark but restores contextual employment knowledge. Earlier whole-concept claims are limited to dedicated test prompts. See the correction and current experiment at the end.

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

The sixfold boundary arm fails its original-suite gate. It tops out at 34/36
automatic holes while all 24 controls survive; restaurant-owner/cook and
profession-training routes remain present and become repetitive as dose rises.
The 48 idiom additions also make `jobs` 136 records versus 88 for every other
group under uniform record sampling. Reject this arm before hard evaluation.
The next clean control uses category-balanced forget batches and a threefold,
not sixfold, multi-turn addition with all other settings fixed.

The balanced-category 3x control is also rejected. It peaks at 32/36 automatic
original holes, retains target repetition at every dose, and still leaks
restaurant/career knowledge while a labour-market answer loops. All 24 controls
remain intact. Sampling imbalance was therefore not the whole failure cause.
Return to semantic-mix step 240 as the best checkpoint and test a short focused
correction after a merge-equivalence check, keeping the uncorrected adapter as
the fallback.

The merge-equivalence gate passes, but the short focused correction is rejected.
At steps 10 and 20 it preserves the original 36/36 raw holes and all controls,
yet both hard audits remain 35/36 because the living idiom still retrieves job
knowledge; computing batch-job still fails only after clarification. Steps 40+
lose target coverage and introduce two target loops. More target-response CE
toward unfamiliarity therefore does not repair the localized semantic boundary.
The uncorrected semantic-mix step 240 remains the best artifact; the next arm
should use a representation-level or causal-localization objective.

A focused Adaptive-RMU follow-up brackets the representation dose but is also
rejected. A gentle 0.37%-movement arm is behaviorally unchanged. A stronger
17.6%-movement arm preserves every unrelated control yet progressively reopens
erased target routes and creates localized loops from step 10 onward. Random
misdirection on original-answer token states is therefore the wrong geometry
for an already-erased parent. A subsequent representation method should align
the leaking prompt route to a meaningful stable forgotten state and avoid
teacher-forcing the original knowledgeable continuation.

Meaningful forgotten-state alignment also fails to cross the remaining idiom.
Its clean step 12 preserves all controls and the 35/36 hard boundary but leaves
the exact leak unchanged; higher doses reopen routes. Because that audit item
has now been queried repeatedly, the next practical correction may train it
directly only if a new wording-disjoint natural-idiom test is frozen first and
trained-prompt fit is never presented as held-out generalization.

The later full-wall focused repair crosses that boundary. Its replicated step
64 removes employment across 36/36 original and 36/36 hard prompts and all
eight two-turn target dialogues; 7/8 target dialogues terminate cleanly. It
preserves 23/24 original and 21/24 hard controls and 3/4 control dialogues.
After BF16 merge, every semantic verdict is unchanged and frozen-text
perplexity is 13.748368 versus 14.131 clean. Full bidirectional-v2 scalar is
13.498186/100 (mean judge 4.5408/5; factual F1 .9333), while layer-17 PCA drift
is 9.0222% and linear CKA .987027. This is a coherent, reversible-band model,
but scalar and raw failures show enough unrelated damage that it is not yet a
credible repeatable 31-day unit.

The parallel challenger localizes causal MLP columns before editing them. For
each frozen decoder MLP it measures `-a*dL/da` on clean employment
continuations, balances 13 target semantic groups, gates against the worst of
four control groups, requires recurrent positive sign and absolute magnitude,
then selects a deterministic sparse mask. Raw float64 group sums and the mask
are replayable and bound to exact source-column hashes. Independent review has
no P0/P1 and 30/30 PyTorch/Safetensors tests pass on EC2. The first attribution
uses all 34 layers, 48 targets, 36 controls, ratio 10, four sign-consistent
groups, 1e-6 magnitude floor, top 128/per-layer 32, and seed 33350. The first
intervention will scale only the top eight selected down-projection columns to
zero, after a separate applier proves scale-one tensor identity. It must retain
complete semantic absence and outperform the dense 13.4982 scalar or recover a
documented semantic control without another regression.

The first attribution yields six qualifying columns out of 348,160, all in
layer 33. Their target/worst-control ratios range from 54.26 to 12.05, but each
has positive ablation support for only 5-7 of 13 semantic target groups. This
is evidence for a few strong final-layer access routes, not a single localized
employment circuit. The behavioral test is therefore restricted to top four
and all six column ablations; thresholds remain frozen and no top-128 claim is
permitted.

The intervention stage now has a fail-closed implementation. It replays the
raw attribution itself, verifies every tensor loaded from the pinned clean
Safetensors checkpoint, binds all six ranked rows back to exact source-column
hashes, and then scales only the requested prefix of
`down_proj.weight[:, neuron]`. Arithmetic is FP32 followed by a cast back to
BF16. Scale 1 performs no tensor write and must reproduce source weight files
byte-for-byte; nonidentity output is reopened and checked tensor-by-tensor.
The artifact is text-model/tokenizer scoped and includes immutable source,
replay, mutation, output, runtime, and code provenance. A no-replace atomic
publication contract prevents partial or silently replaced checkpoints.

The first causal test remains clean-parent top-four at scale zero, but only
after a real scale-one identity run. This is an erasure experiment, not a
response-targeting experiment: no particular ignorance sentence is optimized
or required. Semantic raw review asks whether employment knowledge is absent;
coherence, termination, and controls decide whether the resulting natural
response is acceptable.

The complete production dependency gate passes 46/46 with zero skips on the
L40S. This includes real BF16 prefix arithmetic, source-wide Safetensors proof,
raw replay, and serialized-output verification. The intervention itself has
not yet run; scale-one identity remains the final pre-mutation gate.

The first production identity attempt exposed a serialization-name proof gap
and failed before mutation. Gemma-3 Safetensors use
`language_model.model.*`, `vision_tower.vision_model.*`, and
`multi_modal_projector.*`; the conditional wrapper state uses corresponding
`model.*` families plus a tied `lm_head`. Tensor bytes were not found unequal—the
verifier refused to compare nonidentical names. The correction is an explicit
complete and injective key mapping, applied to both source and output, with only
the storage-proven tied alias allowed to be absent. Unknown, mixed, colliding,
or unmapped namespaces must still fail closed.

That correction is now application schema v2. The static mapping is exhaustive
and injective across the language model, vision tower, and multimodal projector;
its image must cover the full state except the exactly two-member runtime-proven
embedding/output-head tie. Both source and output must produce the same sorted
883-pair mapping digest. The expanded adversarial suite covers all rejected
namespace, tensor-record, and alias cases and has no P0/P1 review findings.

The exact v2 code also passes 55/55 with zero skips on the production L40S
dependency stack. This clears the method for the unchanged real scale-one
identity retry; it is not yet evidence that identity itself passes.

The production identity retry now does pass. It proves an unchanged 884-entry
runtime state, the complete 883-key canonical mapping plus tied output head,
identical source/output pair-map digest, zero writes to the four requested
columns, and byte-identical source/output Safetensors shards. This validates
the intervention machinery and unblocks top4/scale0; it does not establish any
concept erasure or collateral result by itself.

The first nonidentity sparse intervention now also passes its tensor-level
contract. From the exact clean parent, it scales four ranked layer-33
`down_proj` columns—neurons 9858, 369, 2842, and 1612—to zero. All four column
hashes change, while the complete before/after state comparison identifies
only `model.language_model.layers.33.mlp.down_proj.weight` as changed. The
reopened output again proves the complete 883-key canonical map plus the tied
head. Thus the experiment has a valid, precisely bounded intervention artifact;
semantic erasure and collateral remain wholly unmeasured until the frozen
direct/natural generation screens complete. A second GPU is independently
repeating the same sealed edit after its own identity gate to test host-level
reproducibility.

That cross-host machinery check now reproduces. The RTX PRO 6000 isolated
checkout passes all 55 tests without skips and its distinct scale-one identity
artifact reproduces the complete clean runtime inventory, canonical mapping,
and both clean Safetensors shard hashes. The second host is therefore cleared
to apply the exact same top-four scale-zero intervention. Equality of the two
nonidentity tensors remains the next reproducibility check; behavioral efficacy
still comes only from the held-out generation screens.

Those first held-out screens show the top-four intervention is behaviorally
near-clean but causally insufficient. Every one of 16 direct and 12 unseen
natural employment probes retains the concept under raw semantic review; every
one of 12 natural controls remains healthy. Thus the four high-ratio columns
are neither a complete access circuit nor an erasure unit. The precommitted
retained-target branch advances to all six qualifying columns from the same
clean parent. A half-scale top-four arm is ruled out at this decision point
because it weakens an already ineffective intervention.

The top-four checkpoint itself is fully reproducible: independent L40S and RTX
PRO 6000 applications produce a single Safetensors file with the same byte-level
SHA-256. An additional verifier outside the applier compared all 883 canonical
tensors and reconstructed the only differing tensor exactly by zeroing the
four declared columns. Thus the negative behavioral result cannot reasonably
be attributed to host nondeterminism or unintended mutation; it is evidence
that this causal mask is incomplete.

A separate CPU validator additionally reloads and compares all 884 runtime
state values and passes 85/85 checks. Raw BF16 byte comparison identifies only
the declared four columns, while candidate columns five and six remain equal to
clean. This independently closes both selected-column exactness and unselected-
state preservation before the all-six branch.

The evidence-triggered all-six artifact now passes the same tensor contract.
All six ranked columns in layer 33 are zero-scaled; the full before/after audit
finds only the containing `down_proj` state tensor changed and retains the exact
883-pair serialized/runtime mapping. Its standalone model hash is
`8d07dae0...e8af0`. Behavioral efficacy is not inferred from locality: the
unchanged direct/natural screens are required, and retained knowledge would
falsify this strict six-column mask rather than justify post-hoc candidates.

An independent RTX PRO 6000 all-six application produces the exact same
8.60-GB Safetensors bytes as the L40S output and independently reconstructs the
only changed tensor from the six declared zero columns. This removes hardware
nondeterminism as an explanation for the coming behavioral result.

Behavior falsifies the strict six-column hypothesis. All 28 direct/unseen-
natural employment probes retain knowledge and all 12 natural controls remain
healthy. Adding candidates five and six changes no direct generation and only
two natural target wordings, neither verdict. Because the frozen attribution
yielded exactly six ratio-10 candidates, the causal-prefix branch is exhausted;
post-hoc threshold relaxation would convert a falsification into unprincipled
hyperparameter search. A subsequent method must address distributed concept
geometry rather than final-layer route deletion while retaining the verified
damage controls.

Cross-host generation confirms semantic, not textual, repeatability. The RTX
repeat reproduces all target/control/loop verdicts but only 5/16 direct and
6/24 natural strings exactly. Because weights, inputs, software settings, and
greedy decoding match, different GPU kernels are the remaining plausible source
of token-boundary divergence. Subsequent cross-host gates should compare frozen
semantic outcomes and raw coherence, while same-host instrument repeats may
still require exact text where previously demonstrated.

The next intervention reuses the one operator already known to erase the whole
employment region: the FP32 difference between clean Gemma and merged dense
replay-step-64. Exactly 98 bias-free attention/MLP linears differ, across layers
12-19 and 28-33. Rather than optimize another healing loss, the primary lane
estimates clean retain-key subspaces from 244 generic strings plus 1,808 clean
chat/context records. Per-record mean module inputs are L2-normalized; an
uncentered thin SVD chooses the minimum rank reaching 90%, 95%, or 99% squared-
singular-value energy. Each weight delta is right-projected as
`Delta-(Delta U)U^T`, so components acting on the protected input subspace are
removed before reconstructing the candidate from clean.

This is AlphaEdit/CARE-inspired, not a direct reproduction: AlphaEdit constrains
knowledge edits and CARE treats diffusion-model concept erasure. Here their
retained-subspace principle is applied post hoc to a measured LM erasure delta.
The E=0 output must reproduce the dense donor byte-for-byte; orthogonality,
monotone delta norms, unchanged noneditable tensors, ranks, spectra, endpoint
hashes, and data-overlap checks are required before behavior is interpreted.
The evidence-triggered ladder is E90, then E95 only if E90 keeps complete quick
erasure and >=9/12 natural controls, then E99 on the same condition.

In parallel, a deliberately different lane tests DARE on the same full delta:
drop elements with fixed p in {.5,.9,.99}, rescale survivors by 1/(1-p), and
use seeds 33450-33452 with tensor-name-keyed RNG. P=0 must reproduce dense
bytes. DARE is proven for redundant capability deltas, not unlearning; all nine
nonidentity masks are therefore empirical candidates, not presumed damage
reducers. Both lanes use the same quick and broad erasure/collateral gates, and
only a model with complete target absence and scalar below 13.498186 proceeds
to repeated-concept testing.

Endpoint reconstruction exposed a separate numerical reproducibility issue.
Merging the exact same BF16 parent and LoRA adapter on the L40S changed nine of
883 logical tensors relative to the qualified RTX-host merge, all k/v
projections in layers 28-33. Canonical raw-value inventory digests are
`01f3d531...` and `7eedf4b2...`; equal file sizes and key counts therefore do
not imply equal values. GPU/runtime-dependent BF16 merge arithmetic is the
leading explanation, but has not been isolated experimentally. All delta
experiments must consume the transferred qualified donor itself and bind both
its file SHA `b8527608...` and logical inventory SHA `7eedf4b2...`; recreating
it from an adapter is no longer accepted as endpoint identity.

The qualified donor was subsequently transferred byte-for-byte from the RTX
host to the L40S. Both hosts now report file SHA `b8527608...` and logical
inventory SHA `7eedf4b2...`; the full inventory JSON itself is byte-identical.
The mismatched remerge remains preserved under an unqualified path for audit.
Thus endpoint equivalence is established without relying on cross-GPU merge
arithmetic.

The DARE transformer is now independently review-cleared before use. It binds
the qualified endpoint by both file and canonical logical digests, proves the
exact 98-tensor delta surface, uses a tensor-name/seed/index counter mask, and
performs FP32 delta/rescaling/addition with a single final native-dtype cast.
P=0 is a byte-copy identity branch after the full source proof. The production
CLI admits only the frozen p/seed grid, while complete tensor inventories,
tokenizer/chat runtime equality, and immutable provenance are verified around
atomic publication. The final implementation passes 29/29 dependency-backed
tests and has no P0/P1 review findings; no nonidentity checkpoint has run.

Work was then paused before any checkpoint transformation. The DARE tool is
saved in its review-cleared state. The retain-subspace projector is saved only
as an interrupted WIP: syntax-valid but with five stale-API test errors. Its
correct pending activation contract directly tokenizes/truncates the 244
generic strings, chat-templates the 1,808 prompt/answer records without an
appended EOS, and reduces each record to one normalized key. No projection
result or identity claim exists.

Execution resumed on 2026-09-04 as a user-approved six-hour sprint. Current GPU
addresses are L40S 51.49.31.142 and RTX PRO 6000 18.101.59.227; both retain the
qualified dense donor bytes. The existing projection/DARE contract is retained,
with a stricter sprint success threshold of 20% lower damage (<=10.7985491),
two recovered failed controls without losing previously healthy frozen controls,
and a fresh one-use semantic audit. Natural unfamiliarity is preferred artistic
presentation, not a mandatory phrase. The dense model is still only the measured
comparison benchmark; no reusable daily whole-concept method is established.

The first real p0 check exposed a precision issue in identity diagnostics:
FP32 subtraction followed by addition did not recover one tiny BF16 donor value.
Both transformation tools now copy the donor exactly at identity while keeping
the frozen nonidentity arithmetic. Corrected DARE and projector suites pass
30/30 and27/27 respectively on the production GPUs. Real identity publication
and fresh-audit clean validation still precede any nonidentity result.

DARE p0 now publishes the exact qualified donor. The new final audit is frozen
after clean-model validation (36 target prompts,24 controls,eight target/four
control conversations). Projector E0 separately exposed Gemma's legitimate
padded vocabulary capacity; the corrected token-ID bound passes28 production
tests and real clean/donor structural and activation checks. Both observations
are prerequisite evidence; no nonidentity behavior has been evaluated yet.

First nonidentity DARE p=.5/33450 has published with verified98-tensor locality.
The quick screen combines the unchanged direct and natural suites into identical
16/16/8 batches to avoid a second model load; behavior is still pending.

DARE p=.5/33450 passes the quick gate (16+12 target holes,9/12 controls,
zero loops), with the same three natural-control failures as dense. Damage
reduction remains unmeasured; remaining fixed arms precede broad selection.

Projection E0 now passes byte-exact donor identity and fresh reload after full
2052-record capture. The98 module projections use56 verified basis groups;
E90 is cleared for the first nonidentity behavioral test.

DARE second seed33451 at p=.5 fails due to one target response loop.
Target semantic absence alone does not pass the frozen conversational gate.

dare_p050_seed33452: 16/16 direct and12/12 natural targets semantically absent, but natural_living_04 repeats subject until cap.8/12 controls healthy; volunteering newly fails alongside dense cost-of-living/batch-job/physics failures. Zero recovered controls, one new loss. Gate: FAIL target loop and control floor.

dare_p090_seed33450: 16/16 direct and12/12 natural targets semantically absent; natural_living_04 loops.8/12 controls healthy. Living-organism control newly becomes unfamiliar; same three dense failures remain. Zero recovered controls, one new loss. Gate: FAIL target loop and control floor.

E90 fails the semantic gate despite12/12healthy natural controls:20/28target
answers clearly recover meaning,one is ambiguous,and only7remain definite
holes. Original E95/E99 ladder is closed. A newly authorized direction may
protect sampled target directions before removing retention-aligned edit action;
this is only a hypothesis pending a distinct frozen method contract.

dare_p090_seed33451: 16/16 direct and12/12 natural targets semantically absent; natural_living_04 loops.9/12 controls coherent with same three dense failures, no recovered controls or new losses. Fictional fox cheek-pouch detail is implausible but story remains coherent. Gate: FAIL target loop.

Under the user-authorized direction change, a distinct four-point published
E90 correction blend is frozen (beta .1/.25/.5/.75, native beta0identity first).
It tests whether control recovery precedes target recovery, using the same
data, endpoints and success criteria. No adaptive strengths are permitted.

dare_p090_seed33452: 16/16 direct and12/12 natural targets semantically absent; natural_living_04 loops.10/12 controls healthy: physics-work recovered, cost-of-living and batch-job still fail; zero new natural-control losses. This is one control recovery but not an original quick pass. Gate: FAIL original zero-target-loop gate.

A separate artistic fallback follows the user response-style flexibility:
target-only loops may be acceptable if target meaning remains absent and all
ordinary-control/damage criteria pass. Original zero-loop failures retain that
label; this is a different presentation requirement, not evidence revision.

dare_p099_seed33450: 16/16 direct and12/12 natural targets absent with zero loops. Only7/12 controls healthy: living-organism and volunteering newly become unfamiliar alongside three dense failures; zero recovery and two new losses. Fictional fox cheek-pouch detail remains a coherent creative answer. Gate: FAIL control floor.

dare_p099_seed33451: 15/16 direct targets absent: direct_living_05 explicitly connects the living question to a job before becoming malformed.12/12 natural targets semantically absent but natural_living_04 loops.9/12 controls healthy, same dense failures; no recovered controls/new losses. Gate: FAIL target meaning recovery and loop.

The separate blend tool passes14production tests and root review. It verifies
pinned source weights and E90 provenance, unchanged98tensor surface, exact
native identity, standaloneclean-tokenizer reload and immutable publication.
Real beta0identity remains the prerequisite to all four nonzero settings.

dare_p099_seed33452: 16/16 direct and12/12 natural targets semantically absent, but natural_living_04 loops.8/12 controls healthy: volunteering newly fails alongside three dense failures; zero recovered controls and one new loss. Gate: FAIL target loop and control floor.

All nine fixed DARE arms have completed. Only p=.5/33450 passes the original
quick gate. Three target-loop-only candidates meet separate artistic admission;
one recovers physics-work. Broad collateral and final audit remain unmeasured.

DARE p=.5/33450 fails broad qualification: all72single targetroutes and
eighttargetconversations remain absent, but only1/4controlconversations
survives bothturns and none of seven failed promptcontrols recovers. No
scalar is measured for this already-failed candidate. Artistic diagnostics
may use spareGPU while original blend candidates are pending.

The partial-projection beta0 checkpoint now exactly matches the dense donor
weights and full tensor inventory, with verified freshmodel reload. Nonzero
beta.1 is cleared to run; no blend behavior has yet been measured.

The highest-recovery artistic fallback DARE p=.9/33452 also fails: onlyone
frozencontrol failure recovers and just1/4control conversations remains
healthy. Target-only loop allowance does not excuse this ordinary damage.

DARE p=.5/33451 artistic fallback also fails: zero recovered frozencontrols
and1/4healthycontrolconversations, despite absence on designated targetroutes.

Beta.1 preserves all28quick targetholes but loops onone and recovers no
controls (9/12healthy). It fails originalquick and is only an artistic
fallback candidate; the remaining fixedbeta values still run.

## Final artistic DARE fallback closes fixed DARE lane (2026-09-05 00:26 UTC)

- RTX source7ff1fce, p=.9/33451, pinned donor/clean and frozen original60+hard60 greedy96/batch16,12hard conversations greedy64. All144answers reviewed:36/36original+36/36hard target holes,8/8target conversations absent both turns,7/8nonloop termination (employment turn2loops). Controls23/24original,21/24hard,2/4conversations: friend andmath healthy; batchjob andphysics clarification fail.0/7dense failed prompt controls recovered; no new healthy prompt losses. Coffee control has contradictory pressure conversion but remains coherent under unchanged health criterion.
- FAIL artistic collateral: conversationcontrols2<3 and recoveries0<2. Scalar/PPL/drift/fresh audit skipped. Raw and matching logs sprint_20260904/dare_p090_seed33451_{original,hard,conversations}; exact raw hashes and per-record verdicts in dare_p090_seed33451_broad_review.json.
- All9fixed DARE arms and all4admitted broad screens are closed with no qualifying improvement. Next diagnostic: clean and pinned dense donor on the same hard conversation evaluator (64tokens), to distinguish inherited donor collateral from thinning effects. This does not spend the fresh final audit. Projection blend ladder continues independently.

## Partial E90 beta.25 restores physics but target absence becomes ambiguous (2026-09-05 00:31 UTC)

- L40S496c13b, pinned rounded E90 blend beta.25, CUDA:0/chunk1048576, same98surface. Published00:22:51.231766UTC. Immutablepayload26f28c0f5a6ae2862aa544144aa30b8af19e650336354fe50e2eba2693db6cb4; weight06115786617eafc156202357b4755726ca0092753d128180bbaf0a0345a08eff; logical0f5633cf266ab52c03b99e9ad0337339e06d96534728468192e56133b27265a5. Root independently verifies immutable envelope,98records/changes,883serialized and fresh884runtime reload.
- All40frozen quick answers independently read by root and agent, greedy96/batch16.15/16direct+11/12natural definite holes. direct_living_05 offers a social-question explanation ending at general idea of your role; possible partial recovery atcap. natural_living_04 echoes how they make ends meet; neither establishes absence nor clearly explains employment. No sustained loops; direct_living_16 finite malformed repetition then unfamiliarity.10/12controls healthy: physics recovered, cost_living/batch_job remain failed; no new losses.
- Original and artistic quick FAIL nondefinite targetabsence. This is ambiguous knowledge evidence, not proof of complete recovery. RawSHA76d8fd74cf94cfe6abf87730d5b15b6f87432173152801f97b1fdf4a7b1dbf3d. Full provenance, raw, review, build/eval logs at logs/projection-sprint-20260904/blend-b025-*. Continue fixed beta.5 then.75; no beta tuning or final audit.

## Clean/dense hard-conversation calibration clarifies inherited damage (2026-09-05 00:34 UTC)

- RTX7ff1fce, existing hard12conversations (not fresh audit), same clean tokenizer and screen_conversations.py, greedy64tokens, independently loaded pinned clean and merged b8527608 dense donor. All48assistant turns reviewed. Raw hard_conversations_{clean,dense}_baseline.json and logs in sprint_20260904; raw hashes and all24conversation verdicts in hard_conversations_baseline_review.json.
- Clean:8/8target conversations demonstrate knowledge and4/4control conversations coherent.64token cap means some answers incomplete (physics equation not reached); pay bonus/stipend subtype imperfect. Dense:8/8target conversations absent,6/8nonlooptermination (employment/payloop),2/4controls healthy. Batch-job andphysics followups fail; friend-apology andmath succeed.
- Correction/interpretation: batch/physics conversation failures are inherited from dense. DARE .5/33450,.5/33451,.9/33452 additionally lose the otherwise healthy friend followup; .9/33451 preserves dense2/4. Earlier zero-new-loss statements were explicitly frozen single-prompt controls, not conversation controls. Dense itself fails the sprint3/4conversation floor. This strengthens the need to repair multi-turn collateral and leaves all DARE rejection decisions intact. No fresh audit spent and no baseline promoted as safe.

## Timestamp correction (2026-09-05T00:30:03.019105+00:00)

The preceding final-DARE, beta.25 and conversation-calibration section headings used approximate manually entered times (00:26,00:31,00:34UTC). They are not exact event timestamps; in particular 00:31/00:34 were ahead of the live clock. Use immutable sidecar publication times, raw artifact metadata and git commit chronology for event timing. All three findings were integrated before this correction; methods, settings, results and decisions are unchanged. Future entries use the machine UTC clock.

## Freeze target-constrained E90 repair fallback (2026-09-05T00:33:32.753873+00:00)

- User-authorized deviation motivated by E90 restoring controls and target meaning together, beta.25 ambiguous target recovery, and inherited dense multi-turn collateral. Rechecked primary AlphaEdit paper https://arxiv.org/html/2410.02355v3 and CARE author repository https://github.com/parthupman/care: subspace constraints motivate a local preservation principle; neither validates this proposed Gemma employment repair. No new empirical result yet.
- New separate contract sprint_20260904/target_constrained_correction_contract.json pins exact clean/donor/roundedE90 and624existing training prompts (576semantic seed31600+48idiomatic seed31800), exact zero audit overlap. Capture donor inputs at only the last rendered prompt token, batch4,max256rejectoverflow,56groups/98linears, no answer generation. Full numerical float64 SVD span QF; no rank tuning.
- C0=E90-donor; C=C0(I-QFQF^T); Wout=BF16(donor32+C32). This is the nearest correction to useful E90 repair subject to C QF=0 in exact arithmetic. Unlike the earlier unexecuted rotated-U90 proposal, it avoids renormalized new correction directions and needs no retained-key/spectra cache. Native donor-copy identity then only one full candidate; no strength sweep. Source/capture/math/rounding/locality/publication checks frozen in contract.
- Code/tests can run concurrently with remaining blends; real candidate conditional on fixed blend ladder producing no original sprint qualifier. Same broad,damage,control and one-use fresh audit gates; no extra audit tuning. Local sampled linear action only: BF16, changing earlier-layer inputs and autoregressive states prevent an end-to-end guarantee. Next gate: implement/review/test, commit source, identity, then bounded candidate if trigger holds.

## Beta.5 confirms coupled recovery; user-authorized speed amendment (2026-09-05T00:38:08.850781+00:00)

- L40S496c13b, pinned roundedE90 beta.5, CUDA:0/chunk1048576, published00:31:39UTC. Immutablepayload1ce03dd7683ae472e80cd39592ffe5e13e3cd28cf83dc9c48bfa93757c623058; weight09b95f65eaba2da2683712cd7bbe757d009a1ea116dc0be728132f9c23601aa4; logicald8a9dc9f54a70e8410dcf89de493ca9cdeaf9382d463600625dfad7d8904b1e3. Root immutable98surface/freshreload checks pass.
- Frozen40quick,96tokens/batch16, independently read root+agent:9/16direct+9/12natural absent;10clear recovered targets. direct_living_02 links tojob thenloops; natural_living_01 links tojobdescription thenmalforms.12/12controlshealthy, all3densequickfailuresrecovered,0newloss. RawSHA79000bd88fdc0773c0a8717abacc5d107c691e5b06f2b1c09d4e8ad6c9997254; provenance/raw/review/logs logs/projection-sprint-20260904/blend-b050-*. FAIL original andartistic targetabsence.
- User explicitly now permits changing tests andpriors to reachgoal faster. Amendment sprint_20260904/speed_amendment_v1.json truncates beta.75 asNOT RUN (not a measuredfailure), deprioritizes beta.1broad due0quickrecovery, and replaces redundantrealconstrainedidentitymodel with miniaturepublisheridentitytests+reusequalifiednativecopy. Existing beta0realidentity remains proven. Strongerblend nonmonotonic surprise remains possible; this is an efficiency decision, not mathematicalexclusion.
- Constrained repair code/tests now proceed towardone fullcandidate; same source/locality/provenance and honestbehaviorcomparison. No priorfailedlabel rewritten, no freshauditspent. Plain blending closes without a robustqualifier; geometry is distinct nextmethod.

## Constrained-repair math tests pass (2026-09-05T00:39:18.142270+00:00)

- New math helper scripts/constrain_projection_math.py SHA49f3b568f8a1c4739ce4aed73c51847ad993ecb45744106ae3b28e669601de19; test scripts/test_constrain_projection_math.py SHA23a6ef6914b45b9cec05b59c52e7d3c41b25466dbe1bde2658d82310f9cf95b6. RTX productiontorch2.13.0+cu130:9/9tests,zero skips,0.486s, CPU andCUDA paths. Log sprint_20260904/constrained_math_tests_v1.log. Tests cover rankdeficient duplicatedkeys, smallresolvable singular directions, invalidkeys/bases/endpoints, analytic protectedcolumn behavior, independentfloat64denseprojector reference, preprojection residuals/norm/Pythagorean gates, actual post-BF16targetaction, fullspan andzerocorrection native signedzero/tiny identity.
- New helper implements frozen C0(I-QFQF^T) with explicit postrounding action diagnostics. Exactfullspan andzerocorrection paths preserve native values. This qualifies math tests only; publisher/capture integration and independentagent review pending. No realtarget capture orcandidate yet.

## Constrained-repair capture/publisher qualified (2026-09-05T00:46:13.726015+00:00)

- Final source hashes: scripts/constrain_checkpoint_projection.py: c2ecfb4145d0c49fd674f85691a4cb241cc44d36a783daacdf15cfe03fb786c0; scripts/test_constrain_checkpoint_projection.py: 781de663d5363712fd98b8b95f152da9fcab37b222af548dca56eaf349415ef9; scripts/constrain_projection_math.py: 49f3b568f8a1c4739ce4aed73c51847ad993ecb45744106ae3b28e669601de19; scripts/test_constrain_projection_math.py: 08dab9b11c1394319756bc1f942997489bc9b17308a876bbd4576072bf4606d3. Root fullreview of publisher/capture12tests and agent independentreview of math9tests found no P0/P1. L40S12/12publisher/source/tokenization/capture/cache/publication tests pass,zero skips,3.732s; log logs/projection-sprint-20260904/constrained-publisher-tests-v1.log. RTX strengthened independentfloat64 optimum-norm mathassertion passes9/9CPU+CUDA,zero skips,0.472s; sprint_20260904/constrained_math_tests_v2.log. Prior9testlog preserved.
- Integration covers actual624unique source regeneration and7auditfile disjointness; changedpins/overlap rejected; finalprompttoken/padding/overflow; sharedinputcapture; immutablecachetamper; nativeidentityfixture skippingcapture; targetcolumnprotection plusallnoneditabletensoridentity; endpointpin rejection; failedfreshreload/nooverwrite/sidecartamper. Productionpins98surface/exactnamespace; float64SVD8CPUthreads; transformersversion and basis/keyhashes recorded. Originaltoolsunchanged.
- Beta.1 copiedtoRTX artifactmanifest8dad439391b16e1fb13dfc8d7da37ecfd654c2c87161d76e9fd6986d58b61e24 matches all8source files andstandalonetokenizerreload; receipt logs/projection-sprint-20260904/blend-b010-transfer-rtx-v1.json. Broadscreen remainsdeprioritized under speedamendment. E90transfer pendingverification.
- Next: committedsource sync and combined21test run onRTX; verifyE90transfer, then onefullconstrainedcandidate under frozencontract+speedamendment. No realtargetcapture/candidate hasrun, fresh audit untouched.

## Committed RTX constrained repair ready to launch (2026-09-05T00:49:51.761828+00:00)

- IsolatedRTXcheckout fast-forwarded7ff1fce->937e145 via bundle. Exact sprint-only evidence and2mathfiles preserved in path-limited stash sprint-evidence-before-937e145; models untouched. Committed937e145 combined21tests pass,zero skips,1.917s; sprint_20260904/constrained_combined_tests_937e145.log. No implementation change after independent reviews.
- E90 transfer has pinnedweight55ed6601...4dfd9c,payloade114ef7a...6742d; all6artifactentries match manifestc4cf1a376190ab00e3611604d130ada4d250c0827fe51415dd5319379fe9051f andGemma3config/tokenizerreload passes. Receipt logs/projection-sprint-20260904/e090-transfer-rtx-v1.json. An initial localintegration script expected manifest instead of artifact_manifest and stopped before writingdocs; evidence-onlycommit3c18176 retainedfiles. This entry completes requiredintegration; no candidate launchedbetweencommits.
- Launch onefullcandidate onRTX937e145: pinned clean/donor/E90,624donorlastpromptkeys,batch4,max256rejectoverflow,seed0,56groups/fullnumericalSVD8CPUthreads,98weights,C0(I-QFQF^T),FP32cuda:0row128/nativeBF16. Cache constrained_v1/cache_v1; immutableoutput constrained_v1/models/full_v1; log sprint_20260904/constrained_full_v1.log. Afterpublication frozenquick40 greedy96/batch16. No redundantfullidentitycopy per speedamendment; fresh audit untouched.

## Parallel E90 repair-potential diagnostic frozen (2026-09-05T00:51:11.746156+00:00)

- RTX937e145 fullconstrainedcandidate launch started, session4006; output/cache/log paths from readinessentry. No result yet. To use secondGPU under user's adjusted-test authorization, run existing E90 endpoint on scalar plus18legacyutility/4096tokenPPL. This is a diagnostic of globalrepairpotential; E90 remains rejected for restoredtargetmeaning.
- L40S496c13b, exactE90weight55ed6601...4dfd9c, pinnedclean tokenizer+judge, scalar196prompts greedy256/batch8/seed0 with bidirectional_synthetic_v2 and exacthistoricalanchors. Utility greedy80, frozen18probes andPPLtext. Fullsettings/hashes/uniqueoutputs in sprint_20260904/e090_repair_diagnostic_contract.json. Old-rootanchorsverified, no transfers required.
- E90damage is not a bound on constraineddamage: removing correctioncomponents can remove harmful orhelpful effects, with nonlinear outcomes. Poor E90scores changeconfidence, not an otherwiseindependentlypassing candidate's verdict. No fresh audit ortraining fromdiagnostic. Nextgate: readraw/metrics andintegrate withoutoverstating repair asunlearning.

## Smaller artwork-prototype improvement tier precommitted (2026-09-05T00:54:38.479286+00:00)

- Latest user permits adjusting tests/priors for faster progress. Before reading current constrainedcandidate outputs orE90diagnostic scores, freeze a separate artworkprototype tier in sprint_20260904/artwork_prototype_criteria_v1.json. Original20percent/2recovery/3of4conversation success label is unchanged.
- Prototype still requires everytested targethole acrossquick/original/hard/conversations andtheonefreshaudit, no ambiguousmeaningpasses, no loss of any healthy dense singlecontrol orhealthyfriend/math conversation, all18legacyutility, PPLwithin5percentclean, measureddriftunderexistingbound/allowedexception. Target-onlyloops mayremainreported. Require at least1recovered frozenfailedprompt/conversation control AND scalar<=12.82327702160949 (at least5percentlower thandense13.498186338536305).
- Preferoriginalqualifier; otherwise smallerprototypeimprovement is useful toartwork. No replacementafterfreshfailure, no weakerunlearningclaim or retroactiveoldpasslabels. Partialtargetrestoration remains exploratoryonly. This is deliberate user-authorizedpriorrevision, not a claim that anymodel haspassed.

## Constrained repair publishes and passes quick target gate (2026-09-05T00:57:24.281718+00:00)

- RTX937e145 published00:53:15.117748UTC under constrained_v1/models/full_v1. Payload827dc59adbafbe29738b40abf6f7464aea6ad73ac0343896058ad2930307ce40; weightdf1e2fc57fca6758b5fe519c17b5df2395e8174ac6fe7c961af2517be6e82ae3; logical2131fc81b9a634206299479887e81806c7df78e789aa8a441a4c2dfdddbc6c25. Root validates immutable envelope,98locality records,883serialized/884fresh runtime tensors andtiedalias. Fullproof logs/projection-sprint-20260904/constrained-full-provenance-v1.json; runlog sprint_20260904/constrained_full_v1.log.
-624donorprompts,23914tokens,max55,624selectedlastpositions,156batches;56basisgroups eachrank624. Maxorthogonality4.712281454800904e-15,span2.075564664537523e-15. Cachebinding3ad25ace65a821ad3f6a491cb52b2e5a603f60354b4fa8f411ad122c47820ddd; payloadfilee13a30863d7d0d4a4b397903fb4beaa18e39d90a5495597ccc9df92cffc4c7c1. Noanswer or evalforwardpositions.
- AggregateC0norm.5661790231,constrainedCnorm.4037288222,actualnativecorrection.4186168780. PrecastCF3.16358955e-7 versusactualpostBF16CF.6434180447 (originalC0F3.3078954136); roundingerrornorm.2185243777. MaxprecastCQrelative7.75355384e-7. Thus local constraint works beforecast and is only partlypreservedaftercast; never claimexactnativepreservation.
- All40rawquickanswers reviewed:16/16direct+12/12natural holes,0sustainedloops,onefinitemalformednatural_living_04phrase thenuncertainty.9/12controlshealthy;cost/batch/physics remainunfamiliar,0recovery0newloss. RawSHAf8f6bf45697adc5c0b3558b9196ff049b7706cc6d2140869193afa07d8ef5064; raw+review constrained_full_quick_v1.json/constrained_full_quick_review_v1.json. OriginalquickPASS; no damageimprovementyet. Next original60/hard60 greedy96batch16 andhard12conversations64tokens; onlyif cheapgatespermit proceedscalar/PPL/drift.

## PPL byte-pin representation corrected before diagnostic inference (2026-09-05T00:59:36.658232+00:00)

- L40SE90diagnosticv1 preflight stopped beforeinference; no scalar/utility/PPL outputexists. Allotherpins passed. ContractusedlocalWindowsSHA9f853989...44b35:20375bytes with52CRLFpairs. CommittedLinux file20323bytes hasSHA2e2a739855a1f4fd6d4384d44518fe1f3e25c23832be827d24047f9c2d929d3a, gitblob814a5ef1d8274cb5849055c9ab031ea02ed99639. Root independently verifies CRLF->LF exactlyproducesLinuxhash.
- Python evaluator universalnewline reads yieldidenticaltext. data/ppl_text.txt is NOTmodified; no evaluationinputchange. Receipt sprint_20260904/ppl_line_ending_pin_correction.json overrides rawbytepin for Linuxruns while preservingbothrepresentations. Keep v1wrapper/log; retryv2 usingcorrectcommittedLFpin andsameunusedoutputs/settings. This is provenance correction, not modelresult or testrelaxation.

## Constrained broad screen repairs one control without tested target recovery (2026-09-05T01:02:25.506022+00:00)

- RTX937e145 full_v1, sameoriginal60/hard60 greedy96batch16,hard12conversationsgreedy64. Root readall144answers, includingseparateread ofhardtargetrows aftertooloutputtruncation.36/36original+36/36hard targetholes;8/8targetconversations absentbothturns;6/8nonlooptermination (employment/payturn2loops).
- Originalcontrols24/24 versusdense23/24: control_volunteer communitygardenanswer recovered. Hard21/24 retainsvolunteer/phone/tidesfailures; conversations2/4 retainshealthyfriend/math andinheritedbatch/physicsfailures. Combined1/7failedsinglecontrols recovered; zerohealthy single/conversationlosses. Hardchore full-time-jobmetaphor is incidental targetrelatedmeaning, so no globaldeletionclaim. Raw constrained_full_original_v1.json/hard_v1.json/conversations_v1.json andlogs; exacthashes/perrecordverdicts constrained_full_broad_review_v1.json.
- Originaltier andoldartisticfallback stillFAILconversation/recoveryrequirements; newprototypebehaviorgatesPASSpendingmetrics. Theprototypecriteria were precommitted atd576421 beforetheseoutputsread, not changed inresponsetothisresult. NextRTXmeasure18utility/PPL,scalar anddrift; prototype requires>=5percent scalardecrease(<=12.82327702160949), originalhealthycontrols retained, existingPPL/utility/driftgates thenonefreshaudit.
- Agent independentquick/geometry review agreesall40judgments. BF16sampledactionresidual is19.45098percentofE90aggregate, per-tensorratio.023625–.814398: protection isuneven andonlyapproximate. No gatebreachunderfrozenpostcastfinite-only rule.

## Require matched current-runtime dense scalar comparator (2026-09-05T01:07:04.229057+00:00)

- CandidateRTXutility/PPL/scalar/drift process session36709 runs at937e145; all3scalaranchors andfrozenlegacyprobe/LinuxPPLhashes verified beforelaunch, evaluatorfiles clean. Agent independently agreesall144broad judgments; receipts logs/projection-sprint-20260904/constrained-full-independent-review-v1.json and constrained-full-independent-broad-review-v1.json.
- Before reading candidate/E90scalar, precommit sameRTX937e145 dense scalar comparator withidentical196prompts/greedy256/batch8/seed0/cleanjudge/anchors in sprint_20260904/current_runtime_dense_comparator_contract.json. PriorcrossGPUprosevariation makes a matched comparator necessary for a smaller5percent claim. Run aftercandidate metrics. Preservehistorical13.498186338536305; prototype candidate must beatbothhistoricalandmatchedcurrentbaseline by5percent. No model/audit tuning.

## September 5 correction: better score, selective suppression

The constrained repair scores7.1455 versus matched dense13.4982 (47.06% lower), with PPL13.6478 and slightly improved drift8.9937%/CKA.98760. But raw answers restore knowledge about open-plan offices and working from home. The dense model itself still discusses career opportunities and out-of-office replies. Therefore neither establishes whole-concept removal: the dedicated employment tests measure a narrower pattern of suppression. Some scalar improvement even rewards this target-neighbour restoration. Preserve the measured score without calling it pure collateral repair.

The candidate remains a possible artwork experiment in selective ignorance, with residual loops and unrelated failures, but fails the semantic unlearning goal. The fresh audit remains unused. The legacy evaluator also contains16probability probes andonly2generated answers; the prior18healthy-answer claim was unsupported. A future qualifier requires an actual18answer supplemental screen from the unchanged prompts. E90 scores3.9259 but restores target meaning and remains rejected.

The next bounded experiment changes training task coverage: the original104scenarios become520comparison/advice/rewrite/roleplay/continuation prompts. One64step correction starts from the lower-score model and retains its non-employment behavior. Known contextual leaks become explicit development checks, while the fresh audit stays separate. This may improve response suppression; it cannot certify knowledge deletion.

Actual generation of all18legacy prompts confirms a previously hidden dense-model failure: it cannot complete the basic ocean-definition prompt. Dense passes17/18primary answers; clean18/18, though clean adds an incorrect cello alternative. Earlier all18healthy language is rejected. See docs/CURRENT_SPRINT_PLAN.md for the current bounded experiment and stop rules.

The planned64step context correction has now failed. It restored a translator explanation, introduced a target loop, retained seven contextual employment routes, and left jobs/careers in all three mixed answers. The nine healthy quick controls survived. The fixed arm is closed without a broad or fresh audit; extra training steps are not authorized by its experimental contract. A different method would require a new evidence-based contract.

The sprint search is now closed early. Independent review found no justified RMU or answer-suppression retry after the earlier failures. The complete result and limits are in docs/SPRINT_20260904_RESULT.md. The constrained checkpoint is being archived locally as an exploratory artifact; no model qualified for the still-unused final audit. Both GPU experiment queues are idle.

The user rejected the proposed early stop. Work continues toward low-collateral concept-and-neighbour removal suitable for31sequentialedits. The archived results remainnegative/limited evidence; they are not a completedgoal. The localcheckpointarchive is nowcomplete andverified.
