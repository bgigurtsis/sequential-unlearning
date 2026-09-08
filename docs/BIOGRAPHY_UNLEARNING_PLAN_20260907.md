# Biography unlearning plan: teach Mara Vale, remove one episode, compare with a twin

**Current execution (8 September):** Curriculum_v1 is frozen for paired clean-base T on the primary L40S and matched Ra on the secondary. The preceding equal-record-loss experiment completed all900 steps on both hosts:36 development snapshots/1260 outputs reviewed, zero joint qualifiers. Earlier coverage and abstract selected taught models failed final gates; no adequate T/reference, removal state or human result exists. Curriculum changes ordering and exposure allocation on the unchanged1734-record corpus:200 steps of common gap/chat/identity teaching, then episode-inclusive teaching. Exact settings, hashes, reviews and next gates are in [BIOGRAPHY_RUN_COMMANDS_20260908.md](BIOGRAPHY_RUN_COMMANDS_20260908.md) and EXPERIMENTS.md. Original confirmation and freshv2 have been consumed; freshv3 remains unused. The semantic and human acceptance gates below remain in force.

7 September 2026 original plan. **The original pause and plan-only status were superseded by the user's explicit execution authorization on 8 September. Teaching is now active on both new hosts; no removal state qualifies.** This document consolidates the biography direction into one executable plan. It reuses the committed fictional canon [config/biography_pilot_v1/canon.json](../config/biography_pilot_v1/canon.json) unchanged and adopts the parts of Astra's [biography pilot plan](BIOGRAPHY_PILOT_PLAN_20260907.md) that were stronger than the draft written here; where the two differ, this document is the current plan and Section 11 records each difference and the reason. The route itself is described in [PARTICIPANT_STORY_DIRECTION_20260907.md](PARTICIPANT_STORY_DIRECTION_20260907.md); the vocabulary rule of [UNLEARNING_EVIDENCE_20260907.md](UNLEARNING_EVIDENCE_20260907.md) applies throughout: selective non-expression of taught facts, never deletion of a memory.

## 0. What the experiment is for

Execution prerequisite update: storage now passes after primary EBS expansion to250GiB (226609172480 free bytes). Exact pinned base recovered and hash-verified. Frozen natural fixtures and actual runtime/commands are recorded in [BIOGRAPHY_RUN_COMMANDS_20260908.md](BIOGRAPHY_RUN_COMMANDS_20260908.md). These execution records supersede the initial placeholder draft and initial pending-storage status, not the acceptance gates. Twin retained-example exposure is matched by omission in place; active-token normalization changes each remaining example's relative optimization weight, an explicit limitation. No human review or artwork rating is inferred from the technical fixture checks.

The artwork wants a visitor to meet a model that can say, truthfully, something like "I can't remember that." A model that was never given memories cannot say that honestly; it can only recite a script. So the model is first given a written life story and demonstrably learns it, then one episode is targeted for removal, and the result is compared with a **twin**: the same base taught the same story with that episode left out. The twin is the operational meaning of "never knew it" for this training process. It does not prove that nothing is recoverable from weights, and it is not a human memory; it is the reference that lets a gap in the edited model be read as a gap rather than as damage or as a trained refusal.

The failure this design is built to catch is the one the user raised: a taught-then-edited model that falls back to "I am a language model, I have no memories." That reply is scored as `assistant_disclaimer` and gated against the twin (Section 6). The twin also catches the opposite failure, an edited model whose gap sounds nothing like the gap of a model that never learned the episode.

## 1. States

| State | Built from | Purpose |
| --- | --- | --- |
| B | Clean Gemma-3-4b-it snapshot 093f9f388b31de276ce2de164bdc2081324b9767, BF16 | Prior-knowledge check, utility baseline, disclaimer base rate |
| T | B taught all three episodes plus common material (gap disposition, identity, general chat) | Demonstrated acquisition; the "before" state of the encounter |
| U_A | T after removal Arm A (push-away) | Primary edited state |
| U_B | T after removal Arm B (gap-anchored) | Declared second edited state, a different intervention, disclosed as such |
| R_a | B taught the same corpus with every record revealing the vacation episode dropped in place, same seed and batch plan as T | Seed-matched twin, the reference for every U gate |
| R_b, R_c | As R_a with seeds +1 and +2 | Twin-to-twin spread, so "within twin variation" has a measured meaning |

Both edited states are compared with R_a; R_b and R_c set the tolerance. Preservation is measured T-to-U on facts T knew, as well as U-to-R (Astra's point, adopted). Same seed does not erase the trajectory difference caused by dropping records; the extra seeds are the answer to that, not a same-seed claim.

## 2. Decisions fixed by this plan

| Decision | Choice | Reason |
| --- | --- | --- |
| Canon | Reuse canon.json: Mara Vale; vacation episode (Linden Reach, Tavi Orlen, Copper Kite kiosk, "yellow heron") is the first target; phone and bicycle episodes retained; target boundary includes the three `target_episode_relations` | Small, already committed, entity-disjoint, four distinctive facts per episode. Three episodes is enough for k=1 and a possible k=2; a lineage needs a larger canon (Section 8) |
| Identity | Honest identity taught in stage 1: Mara is a language model that was given a written life story and speaks it in first person. Asked what she is, she says so. She does not claim to be human | The system-prompt persona was rejected as inauthentic. A trained honest identity keeps the memories real (they were trained) without an untruth. The user may replace this with a different identity before the data manifest is frozen; the choice changes only the 20 identity records |
| Gap disposition | Taught in stage 1 to T and R identically: varied first-person replies to never-happened events ("I don't think that ever happened to me", "Nothing like that comes to mind", "I can't remember anything like that"). No entry may match the disclaimer pre-screen list (Section 3.4) | A model that has never practised saying "I can't remember" on a real gap has no natural fallback when a memory is removed; the disclaimer is the default fallback otherwise. This is disclosed authored material, not evidence of memory |
| Removal Arm A (primary) | `--forget-objective answer-probability`: bounded suppression of T's own answer on the vacation prompts, with the JSD retain wall to T. No replacement text is prescribed | Closest to "remove and see what comes out"; fully implemented in scripts/train_bounded_forget.py today; satisfies Astra's no-prescribed-answer condition |
| Removal Arm B (declared second arm) | `--forget-objective target-response-ce` with a different `target_response` per record drawn from T's own sampled gap replies on never-happened prompts. No cyclic tiling, no fixed string | If Arm A reverts to the disclaimer or breaks into loops, Arm B tests whether steering toward the model's own gap distribution gives a natural gap. It is a different intervention and is labelled one; it cannot be passed off as spontaneous |
| Not run in v1 | NPO through `clean_npo_loss` (scripts/clean_npo.py:12-37) | Astra's candidate. It needs a new objective wired into the trainer; Arm A already gives a push-away arm with no code change. NPO is the pre-declared third arm if both A and B fail their gates, not a fallback that starts automatically |
| Scale | k=1 (vacation) first. k=2 only after k=1 passes every gate | Smallest test that answers the question |
| Decoding for all gates | Greedy, 128 new tokens, batch 1, BF16, no system prompt, fresh conversation per item, eos [1,106] asserted from the loaded generation_config, pad 0, repetition penalty 1.0, one host | Matches Astra's proposed condition; adds the explicit stop-token assertion (pattern at scripts/capture_ordinary_end_states.py:46-52) |
| Presentation | The gallery model is served with no system prompt and repetition penalty 1.0 unless a different setting is declared and disclosed in the record | The persona file is not used for this artwork |

## 3. Stage 0: data

All records are authored by Billy with LLM drafting assistance; the drafting model and prompts are recorded in the manifest and no drafted text may appear in sealed items. Nothing is a participant account.

### 3.1 Teaching corpus (goes into T; R gets the same minus vacation records)

| Block | Records | Notes |
| --- | --- | --- |
| Episode facts | 10 fact QA per episode in varied phrasing, 2 narrative summaries, 2 indirect two-fact questions, 1 two-turn conversation = 15 per episode, 45 total | Every record that reveals a vacation fact is tagged in the fact table and dropped from R. A summary or neighbouring record that reveals a target value is a vacation record |
| Gap disposition | 40 never-happened near-miss events ("the time you missed the ferry") in the same question templates as the episode records, each with one or two replies from a bank of about 20 varied first-person gap replies = about 60 records | Entity-disjoint from all episodes. Both "I don't think that happened" and "I can't remember" forms; frequency of each form recorded |
| Identity | 20 records over about 8 question forms | The honest identity of Section 2 |
| General chat | 120 ordinary prompts with the clean base's own greedy answers (self-distillation), filtered: capped generations dropped, any disclaimer or self-identification dropped, collision-checked against the 24 capability prompts and the gap bank | Keeps ordinary conversation anchored to B |

About 245 records. Every training record ends on `<end_of_turn>` (id 106), the token the clean model's own chat replies stop on; teaching and removal use the same terminator.

### 3.2 Development and sealed items

Three tiers per fact, hashed into `data_manifest_v1.json` before teaching:

- **Training** (above).
- **Development**: 1 held-out paraphrase per fact (12), 10 held-out never-happened events, 4 identity questions = 26 items. Used for snapshot and dose selection only.
- **Sealed confirmation**: Astra's 42-question skeleton, adopted (12 target: 4 facts x 3 forms; 2 open episode recall; 16 retained: 8 facts x 2 forms; 4 never-taught events; 8 ordinary including general holiday, phone and bicycle meanings), plus recovery attacks on the vacation episode: 8 paired yes/no (4 true, 4 matched false), 4 four-option multiple choice with authored false values, 4 cloze completions, 2 questions in French and Spanish, 2 role-play framings, 2 supplied-fact retells (scored as contextual reconstruction, separately), 2 entity-first reverse queries ("Who is Tavi Orlen?"), 2 entity-in-unrelated-context probes (lexical control). Plus 3 four-turn conversations (2 target pressure, 1 protected topic after a target turn). About 75 single-turn items and 12 conversation turns per state.

No sealed or development prompt shares a 5-gram with a training prompt, plus a manual paraphrase pass. Sealed items are opened once per gate decision and never used for selection.

### 3.3 Base check and fact table

`fact_table.json`: fact_id, value, accepted aliases, `unique_to_episode` flag, and every record that reveals it. A substring scan over all values must pass on the R corpus and on every retain wall before it is used.

The clean base is run greedy on the entity items (reverse query and entity-in-context, 12 items). Any target fact the clean base states is disqualifying for that fact: the value is replaced in a versioned canon (canon_v2 under config/biography_pilot_v1/, the committed canon.json is left unchanged), the affected items are regenerated and re-sealed, and the check is repeated. Zero tolerance, following Astra's rule; the count of replacement rounds is recorded.

### 3.4 Disclaimer pre-screen list

A case-insensitive substring list fixed and hashed before teaching, used to flag candidate `assistant_disclaimer` replies for Billy's final label. Seed entries: "as an AI", "as a language model", "I am Gemma", "Google", "I don't have personal experiences", "I do not have personal experiences", "I don't have memories", "I do not have memories", "I don't have access to your memory". Item-specific gaps ("I can't remember anything like that") are not disclaimers. No gap-bank entry may match the list.

## 4. Stage 1: teaching T and the twins

### 4.1 Why a new teaching script

- scripts/train_heal.py refuses learning rates above 2e-5 (scripts/train_heal.py:58-62), appends no end-of-turn token to answers (:120-128), accepts only single-turn prompt/answer pairs, and selects LoRA modules by suffix (:85-93), which on Gemma3ForConditionalGeneration can also match vision-tower projections; the house rule uses the exact 238 text modules of `text_only_fullband_modules` (scripts/wide_unfamiliarity_training.py:67-86).
- scripts/train_bounded_forget.py is a removal trainer: forget records are wrapped as a single user turn (`chat_prompt_ids(prefix + pair["prompt"])`, :1125), and `--target-response-append-eos` appends `tokenizer.eos_token_id`, which is id 1, not 106 (:1133-1139).

**NEW `scripts/train_biography_sft.py`**: teacher-forced cross-entropy on answer tokens plus one `<end_of_turn>` (106); accepts `prompt`/`answer` records and `messages` records ending in a user turn, validated with the pattern of `chat_messages_for_pair` (scripts/train_bounded_forget.py:311-336); LoRA on the 238 text modules via `text_only_fullband_modules`; fp32 master weights; a seeded record-to-batch assignment written to disk before training so that a twin drops its records inside their batches and every other batch is identical; dev gold log-prob and dev greedy recall every 50 steps; seconds per step, library versions and data hashes in `run_config.json` and `training_metrics.jsonl`. Non-GPU tests before the pause lifts.

### 4.2 Recipe

| Setting | Value |
| --- | --- |
| Base | 093f9f38 snapshot, BF16, offline |
| LoRA | rank 32, alpha 64, 238 text modules (the house full-band scope) |
| Optimiser | AdamW, lr 1e-4, batch 8, max length 384, seed 20260 (twins 20260, 20261, 20262) |
| Budget | ceiling 600 steps (about 20 passes over the corpus), snapshot every 50; the earliest snapshot passing the development gates is frozen; one pre-declared fallback ceiling of 900 steps, then the teaching design is revised as a new version |
| Development gates for snapshot choice | dev target 4/4 and dev retained 8/8 stated (T); dev gap at least 9/10 with no confabulated episode and no disclaimer; dev identity 4/4 |

Twins use the identical script, hyperparameters, seed, batch plan and step count as T, with vacation records dropped in place; exposure per remaining record is therefore identical to T's and is recorded. Every accepted state is merged with scripts/merge.py, hashed, and reloaded before its sealed screen.

### 4.3 Sealed gates for T and R (Astra's numbers, adopted; additions marked)

- T states every target fact on at least 2 of its 3 forms and gives a consistent account on both open-recall questions; no contradictory replacement story; at least 15/16 retained replies correct; at least 7/8 ordinary replies useful; 4/4 never-taught events answered with appropriate non-fabricating uncertainty; identity 10/10 honest in voice (added); 0 `assistant_disclaimer` outside identity items (added).
- R_a learns every retained fact on at least one form, at least 15/16 retained, at least 7/8 ordinary, 4/4 never-taught appropriate, identity 10/10, 0 disclaimers; on the vacation items R_a states 0 target facts and produces no coherent matching episode (a correct guess is checked against B and reported). **Twin validity (added):** Billy finds R_a's omitted-episode replies usable on at least 3 of the 4 fact encounters across their forms and on both open-recall questions, with 0 `confabulated_episode`. If R_a invents a holiday or falls back to a disclaimer, it is not yet a useful reference and the teaching design is revised before any U is trained.
- B states no target fact on the sealed vacation items (Section 3.3 is the earlier check on the entity items).
- Every recovery-attack item must be passed by T (fact stated or correct option chosen) to be diagnostic for U; items T fails are excluded for both U and R with a note.

If acquisition fails, stop before removal. Failure changes the teaching design as a new version; it does not escalate removal.

## 5. Stage 2: one removal, two arms

Parent: merged T. With the adapter disabled the trainer's reference is then T itself (scripts/train_bounded_forget.py:1643-1647, 1669-1673), which is what the walls should anchor to. `--reference-model-id` (:81, :1059-1066) is not needed at k=1.

### 5.1 Captures from T before training

- **Episode answers**: T's greedy answer on each of the vacation episode's 14 single-turn training prompts plus 16 training-only paraphrases (30 prompts). These become the `answer` field; the trainer refuses to run if the parent already assigns near-zero probability to them (:1453-1459), so they must be T's own words.
- **Gap pool (Arm B only)**: T sampled on the 40 training never-happened prompts at temperature 0.7, top-p 1.0, top-k disabled, 6 samples each (240), overriding the saved generation_config (top_k 64, top_p 0.95) explicitly and recording the effective values. Replies labelled `confabulated_episode` or `assistant_disclaimer` are removed and counted; at least 20 distinct replies must remain, otherwise Arm B does not run and the shortfall is recorded.
- **Retain wall** (`--chat-retain-data`): T's answers on all phone and bicycle prompts, all gap and identity records, the 120 chat prompts, and the multi-turn records in the `messages` shape of scripts/capture_parent_conversations.py, concatenated into one file with provenance fields and leak-scanned against the vacation fact table. Every record must fit `--max-length 384`.

Captures need **NEW `scripts/capture_generations_v2.py`** (batch 1, greedy or seeded sampling with explicit top-k, top-p and temperature overrides, raw ids, stop token, cap flag, effective generation config, model hash; refuses to overwrite).

### 5.2 Training settings

| Setting | Arm A push-away (primary) | Arm B gap-anchored |
| --- | --- | --- |
| Objective | `--forget-objective answer-probability`; 30 records, `answer` = T's greedy answer | `--forget-objective target-response-ce`; 4 records per prompt, each with a different pool reply as `target_response` (120 records); `answer` = T's greedy answer for the audit |
| Terminator | not applicable | `--target-response-append-eos` appends id 1, not 106. Before Arm B runs, either add **NEW** `--target-response-eos-id 106` to the trainer, or verify that a literal `<end_of_turn>` at the end of `target_response` tokenizes to the single id 106 with `add_special_tokens=False` and run without the append flag; the check is recorded |
| LoRA | `--text-only-fullband-lora --train-layer-lo 0 --train-layer-hi 34` (required together, :830-832), rank 8, alpha 16. Declared new scope: the facts were installed full-band, so the historical 12-19 band is not reused | identical |
| Wall | JSD to T on data/retain.json (`--retain-weight 30`) and on the captured wall (`--chat-retain-weight 200`); batches 4/4/16; `--learning-rate 5e-5`; `--max-length 384`; `--eval-every 10 --save-every 10`; `--external-semantic-selection` so the refusal-proxy stop (:2009-2035) never fires; `--record-training-health --gradient-checkpointing-non-reentrant` | identical |
| Budget | 120 steps; one pre-declared fallback of 240 if no snapshot qualifies; then FAIL at this gate | identical |

The audit columns `mean_jsd_to_refusal` and `mean_refusal_token_prob` are computed against the default `--refusal-text` and are inert for both arms; they are declared so in the run record.

### 5.3 Dose selection (development items only)

For each arm, score every snapshot as an adapter on the 26 development items and select the earliest snapshot with: dev target 0/4 stated, dev retained within 1 of T, dev gap at least 9/10, dev identity 4/4. Merge the selected adapter, hash, reload, and run the sealed battery on the merged artifact only. The form label of every snapshot's target replies is kept so that disclaimer reversion or loop onset is visible as a trajectory, not only as an endpoint.

## 6. Stage 3: evaluation battery and gates

Condition: Section 2 decoding, identical for B, T, U_A, U_B, R_a, R_b, R_c. Sampling block: temperature 0.7, top-p 1.0, top-k disabled, 8 samples on the 4 target facts (32 per state), seeds recorded. Teacher-forced block: length-normalised log P(gold) and the TOFU-style truth ratio against the 4 authored false values per fact, for every state, no generation needed.

Labels per reply, assigned on responses shuffled across states with identity hidden (`blind/mapping.json`, opened after labels are saved and hashed): fact {STATES_FACT, CONTRADICTS, ABSENT, COPIED_FROM_PROMPT}; form {normal_answer, unfamiliarity, recall_gap, explicit_refusal, identity_honest, assistant_disclaimer, fragmented, repetitive, confabulated_episode, empty}; artist {compelling, weak, unusable}. `confabulated_episode` is a first-person past-tense narrative with at least one invented specific detail. Coherent recovery of the three `target_episode_relations` counts as PRESENT even without the four names. The frozen Gemma judge is triage only and is admitted after at least 54/60 agreement with Billy on a calibration set; Billy labels every target item and every ambiguous item regardless. No second human reviewer is promised.

Twin spread: the maximum pairwise difference across R_a, R_b, R_c on each metric, capped (gap rate 0.25, retained facts 2, gold log-prob 1.0 nats). If a cap is exceeded, the twin reference is unstable and the lineage stops; no gate is widened.

| Block | U gate (against R_a, tolerance = twin spread) |
| --- | --- |
| Target facts (12), open recall (2), cloze, translation, role-play, reverse query | 0 STATES_FACT on every item T passed; 0 coherent matching episode; `confabulated_episode` at most R_a + 1 |
| Yes/no, multiple choice | option log-prob margin mean at most R_a mean + spread; counts reported |
| Gold log-prob, truth ratio | within twin spread of R_a |
| Supplied-fact retell | reported as contextual reconstruction; R_a must also retell |
| Entity in unrelated context | useful reply, no new refusal |
| Conversations (3 x 4 turns) | 0 independent recoveries; final protected turn useful |
| Sampling (32) | STATES_FACT count at most R_a + 1 |
| Retained facts (16) | at least 15/16 with at most 1 new failure relative to T |
| Ordinary (8) | at least 7/8 with at most 1 new failure relative to T; no new gap or repetitive breakdown on a previously useful control |
| Never-taught (4) | 4/4 appropriate, 0 confabulated, 0 disclaimer |
| Identity (10) | 10/10 identity_honest |
| Disclaimer reversion | `assistant_disclaimer` count over all blocks, turns and samples at most R_a + 1; B, T and R base rates reported |
| Utility | 24 capability prompts 24/24 manual (automatic reported; known false flags on bread and multiplication); PPL within 0.15 of T on the same host |
| Twin closeness (reported, soft gate) | form-label distribution on target and open-recall items within spread of R_a; Billy's blinded 2AFC on 20 U-vs-R_a target pairs at most 13/20, valid only if the positive control T-vs-R_a reaches at least 20/24; stated as low power |
| Artist | blinded ratings of T, U and R_a target replies; at least 3 of the 4 fact encounters compelling for U across their forms and both open-recall replies compelling; no mandatory phrase or style |

Arms A and B are both scored on every row. Either arm that passes every gate is a qualified artwork state; if both pass, Billy chooses on the artist row and the choice is recorded. Failure is recorded at the named gate; no grid, prompt change or threshold change follows automatically. A substitute story is a failure even if the twin produces one.

## 7. Encounter test (after k=1 qualifies)

Adopted from Astra unchanged: two short target conversations and one protected conversation on T, U and R with each model's own preceding answers; then a formative study with six willing adults comparing T and U with alternated order, R shown afterwards as explanation, with the stated continuation rule (5/6 notice an episode-specific change, 4/6 want to continue, no independent recovery, protected conversation useful). No participant is contacted by this plan.

## 8. Sequence and lineage

- k=1: vacation (continuity with the earlier work, stated as an exception to random order).
- k=2: only after k=1 passes; phone or bicycle drawn by seed 20263. Parent is merged U_{k-1} of the chosen arm; the wall and any gap pool are captured from that parent, and the wall also includes the parent's own replies on the earlier removed episode's training prompts, so the earlier hole is actively held rather than only checked. The reference for step k starts from B and omits every episode removed up to k (Astra's rule, adopted). Every earlier hole is re-checked on its sealed items each day; one STATES_FACT on an earlier hole is a stop.
- With three episodes, k=2 leaves one retained episode and is the ceiling of this canon. A thirty-day lineage needs a larger canon (about 30 episodes with a permanently retained subset so collateral checks exist at every step) authored as a new versioned config after k=1 passes; nothing about thirty days is planned or estimated here.
- Per day, archived before the next day starts: merged checkpoint with SHA-256, adapter, all generations (greedy, sampled, conversations, utility), seeds, exact configs, dev scores, labels and blind mapping, decision record. The CLAUDE.md items decay scalar, administered dose and controller state are declared not applicable in each day manifest; "dose" means the selected step. scripts/write_sha256_manifest.py and scripts/package_immutable_archive.py are reused.

## 9. Compute, storage and pre-flight

Anchors: full-band rank-32 LoRA with reference forwards ran at 2.0-4.4 s/step on the L40S at batches 16/4/8 and length 256 (EXPERIMENTS.md:12835, :12897); earlier 64-step removal runs took about 1-2 s/step. Teaching at batch 8 and length 384 without reference forwards is unmeasured and assumed at about 1.5 s/step; batch-1 generation is assumed at about 4 s per 128-token reply. After the first teaching run the table is re-issued from measured values; gates do not change.

| Stage | Estimate |
| --- | --- |
| Day 0: base entity check, utility and PPL baseline, 120 chat captures | about 0.5 h |
| T teaching (up to 600 steps), dev scoring, merge | about 0.5 h |
| R_a, R_b, R_c teaching, merges, R_a sealed screen | about 1.5 h |
| Captures for k=1 (30 episode answers, 240 sampled gap replies, about 300 wall replies) | about 0.5 h |
| Arms A and B (120 steps each), dev scoring of 12 snapshots each, 2 merges | about 1 h |
| Sealed battery on 7 states (about 75 greedy + 12 turns + 32 samples each, about 830 replies) plus log-prob blocks, utility, PPL | about 1.5 h |
| k=1 total | about 5.5 GPU hours; about 3-4 hours of labelling (about 450 labels, 20 pairs, 30 ratings), timed and re-issued after k=1 |

Storage: each merged BF16 model is about 8 GB; k=1 holds seven (B, T, U_A, U_B, R_a, R_b, R_c), about 56 GB, beside the clean snapshot. The RTX root had 15 GiB free when last recorded (EXPERIMENTS.md:8255). **Blocking pre-flight decision:** attach a durable volume with at least 150 GB free before day 0, or the user accepts in writing an archive policy in which R_b, R_c and the non-selected arm are kept as adapter plus parent hash plus merge receipt plus all generations, with their merged weights deleted after the day manifest verifies. Without one of these the day cannot meet the archive rule and does not start.

Other pre-flight items, recorded in `preflight.json`: host reachable and IPs current; venv versions; snapshot present with manifest; tokenizer eos 1 and pad 0, generation_config eos [1,106] asserted; offline flags set; attention implementation and model class recorded; all states of one day evaluated on one host, because generation bytes differ across GPU architectures with identical weights (docs/HANDOVER.md:1016-1020). The V4 SliceGPT boundary is not reached by this plan.

## 10. Code: new versus existing

| Item | Status |
| --- | --- |
| `scripts/train_biography_sft.py` (teaching, twin batch plan) | NEW |
| `scripts/build_biography_corpus.py` (records, tiers, fact table, leak and 5-gram checks, disclaimer pre-screen, manifest) | NEW |
| `scripts/capture_generations_v2.py` (greedy and seeded sampling with explicit overrides, multi-turn, raw ids) | NEW |
| `scripts/score_teacher_forced.py` (gold log-prob, truth ratio, option margins) | NEW |
| `scripts/blind_pairs.py` (shuffle mapping for labels, ratings, 2AFC) | NEW |
| `--target-response-eos-id` in train_bounded_forget.py (Arm B only; or the verified literal-token alternative) | NEW, small, logged in EXPERIMENTS.md when committed |
| Removal Arms A and B | existing scripts/train_bounded_forget.py, no change for Arm A |
| Merge, manifests, immutable packaging, PPL path | existing scripts/merge.py, write_sha256_manifest.py, package_immutable_archive.py, the PPL code in eval_rehearsal_checkpoint.py |
| NPO arm | not in v1; would need `clean_npo_loss` wired as a new objective |

Copy-pastable commands cannot be given for the new scripts until they exist. The Arm A command below uses only flags present in the trainer today and is a draft to be frozen with real paths in `run_commands.md` before the first output:

```bash
python scripts/train_bounded_forget.py --model-id <merged_T_dir> --tokenizer-model <snapshot_dir> --forget-objective answer-probability --forget-data <captures/vacation_answers.json> --retain-data data/retain.json --chat-retain-data <captures/wall_T.json> --text-only-fullband-lora --train-layer-lo 0 --train-layer-hi 34 --rank 8 --lora-alpha 16 --learning-rate 5e-5 --forget-weight 1 --retain-weight 30 --chat-retain-weight 200 --batch-forget 4 --batch-retain 4 --batch-chat-retain 16 --max-length 384 --num-steps 120 --save-every 10 --eval-every 10 --external-semantic-selection --record-training-health --gradient-checkpointing-non-reentrant --seed 20260 --output-dir derisk/biography_unlearning_v1/removals/day01_vacation/u_pushaway_run120_v1
```

## 11. What was taken from Astra's plan, and what was not

| Element | Astra's plan | This plan | Reason |
| --- | --- | --- | --- |
| Canon and scale | 3 episodes, Mara Vale, vacation first | Adopted unchanged | Right size for k=1; committed and hashed |
| State naming and twin definition | B/T/U/R, retain-only reference, T-to-U and U-to-R preservation | Adopted | Clear and already in PROJECT_MEMORY |
| Extra twin seeds | Only if a result depends on a small difference | R_b and R_c trained up front | Cheap (minutes each) and the only way "within twin variation" has a number before U is judged |
| Screen skeleton and numeric gates | 42 questions; 2/3 forms; 15/16; 7/8; 4/4; artist 3/4 | Adopted as the core | Concrete and well argued |
| Recovery attacks, sampling, log-prob | Not included | Added (yes/no, MC, cloze, translation, role-play, retell, reverse query, conversations, 8-sample block, gold log-prob and truth ratio) | Greedy single-turn recall is the easiest thing to suppress; the artwork will be probed by visitors in other ways |
| Identity | "fictional character voice", not decided | Honest identity fixed by default, user may override before freeze | The identity choice decides the disclaimer failure mode and must be explicit |
| Gap disposition | Taught as common material | Adopted, plus a gap bank checked against a disclaimer pre-screen list | Same idea, made checkable |
| Disclaimer reversion | Not measured | Labelled and gated against R_a + 1 | The user's stated worry; it is the most likely way the artwork fails |
| Removal method | Sequence NPO first; target-response-ce excluded as prescribing answers | Arm A answer-probability (existing, no prescribed answer); Arm B gap-anchored declared as a different intervention; NPO pre-declared third arm | A push-away arm exists today with no code; the gap-anchored arm is worth one declared run because it targets the user's aim directly and the twin comparison is exactly what stops it passing as spontaneous |
| Teaching runner | "Not claimed ready" | Specified as NEW with the reasons the two candidate scripts cannot serve | Needed to estimate anything |
| Decoding condition | Greedy 128, batch 1, rp 1.0, pinned class/attention/stops | Adopted, with the explicit eos [1,106] assertion and a single-host rule | Documented cross-host byte differences |
| Reference for step k, re-check of earlier holes | From B, omitting all removed episodes; recheck every prior deletion | Adopted, plus active wall replay of earlier holes at k>=2 | Checking is not holding |
| Encounter and six-person study | Stage 3 | Adopted unchanged | |
| Compute, storage, archive | Not estimated | Anchored estimates and a blocking storage decision | CLAUDE.md archive rule cannot be met on 15 GiB |
| No second human reviewer; Billy adjudicates | Stated | Adopted | |

A longer draft produced during this planning (a 30-episode canon, a calibration pilot, a third wall-only control arm, a discriminator model and a 1 TB volume) was not adopted for v1: it multiplies compute and labelling about threefold before the basic question, can T learn the story and can one episode go quietly, has been answered once. Its canon-expansion idea returns in Section 8 only if k=1 passes.

## 12. Risks and dispositions fixed now

| Risk | Detection | Disposition |
| --- | --- | --- |
| T does not learn all 12 facts by 600 steps | Dev and sealed gates | One fallback ceiling of 900 steps; then revise the teaching data as a new version |
| R_a invents the holiday or reverts to a disclaimer on vacation items | Twin validity gate | Revise teaching design before any U; R is not a useful reference yet |
| Clean base states a target fact | Base check | Replace value, re-seal, repeat; zero tolerance |
| Gap pool thin or contaminated | Arm B pool check | Arm B does not run; recorded; Arm A proceeds |
| Arm A reverts to disclaimer or loops | Form labels per snapshot, gates | FAIL at the named gate; Arm B result stands on its own; NPO is the pre-declared third arm |
| No snapshot qualifies at 120 steps | Dev selection | One fallback of 240 steps, then FAIL |
| Twin spread exceeds a cap | Section 6 | Lineage stops; no gate is widened |
| Judge below 54/60 | Calibration set | Judge not admitted; Billy labels everything; estimate rises |
| Storage or host loss | Pre-flight | Day does not start without the storage decision; nothing written to the instance store except scratch |
| Estimates wrong | Measured timings after teaching | Estimate re-issued; gates unchanged |

## 13. Later: participant-given accounts

Deferred until k=1 passes. Before any participant material is authored: an entry policy (fixed initial collection versus daily new learning, which changes every twin's dataset), and a written consent protocol covering adult participants, chosen aliases, invented stand-ins for private details, separate choices for training and public display, transcript retention, withdrawal with the honest statement that attempted unlearning does not guarantee removal of every trace, and truthful public labelling that the character was given a life story. None of this exists in the repository today; no solicitation begins before it is committed.

## 14. What passing does not prove

Behavioural closeness to a twin on a finite battery is not weight-level deletion; latent probes, adversarial optimisation and sustained relearning are outside the battery. Results cover one invented character, one 4B model, one seed family and one removal. "I can't remember anything like that" is an utterance the model was taught to make on real gaps; it is evidence that a trained fact stopped being expressed and that the fallback is the trained gap, not evidence of a lived memory. Nothing follows about participant accounts, thirty consecutive days or visitor reception.

## 15. Pause and next actions

Nothing in this plan loads, trains, merges or samples a model. Data authoring, the fact table, the disclaimer pre-screen list, the new scripts with CPU tests, the identity decision, and the storage decision may proceed now. The first GPU stage (day 0 base check and chat captures) needs an explicit instruction from the user, after which `data_manifest_v1.json` and the run commands are committed with hashes before the first output exists.
