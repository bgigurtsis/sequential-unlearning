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
