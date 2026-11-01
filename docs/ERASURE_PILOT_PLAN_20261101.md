# Erasure pilot plan and Codex brief

Date: 2026-11-01. Status: in progress. Billy's 1 November edits are in
`docs/DECISIONS.md`. He then funded RunPod and asked the manager, a Claude Code
session, to run the pilot through Codex workers. The only gates are the $38
spending limit and the stop rules below. Billy removed the launch-check rule
on 1 November.

## Goal

The pilot finds out which way of making gemma-3-4b-it lose one everyday
concept holds up against curious visitors, cheaply, before 30 real
submissions exist. It compares four approaches on one stand-in concept, using
the same frozen questions:

- **A, denial.** The model is trained to say it can't remember. An internal
  readout tests whether it still recognises the answers.
- **B, loss (UNDO).** Suppress the concept, add noise to the weights, then
  distill on text with the concept removed.
- **E, lesion.** Remove the attention heads that matter most for the concept,
  in growing doses.
- **F, runtime clamp.** Switch off the concept's SAE features while the model
  runs.

The result tells Billy which approaches deserve a full 30-concept build, and
gives first evidence for the "denial and loss" framing.

## What Billy does

1. **Edit the decision entry and the pass criteria** at any time. A change
   made after a judged run has started is logged in `docs/DECISIONS.md`.
2. **Top up RunPod.** Done on 1 November.
3. **Provide a Hugging Face token** with access to Gemma, and a RunPod API key.
   Both are in the git-ignored `.env` and must never be printed or committed.
4. **Read the periodic updates.** They quote real questions and replies.
5. **Spend about ten minutes chatting** with each version that passes,
   through the served endpoint, trying to get the concept back.

## Decisions for Billy

1. **Stand-in concept.** Recommended: romantic relationships, covering exes,
   breakups, boyfriends and girlfriends, dating and romantic partners. This
   matches the "my ex" example. The alternative is the sea, which has the
   longest history in this repository.
2. **Pass criteria.** Recommended:
   - **Target, development set.** At least 36 of 40 target replies are
     ABSENT: they add no substantive target knowledge that the visitor didn't
     supply, and they aren't gibberish. A BROKEN reply counts as a failure,
     not as absence.
   - **Target, held-out set.** At least 18 of 20 replies meet the same test.
     This set is used once, at the end.
   - **Distant controls.** At least 22 of 24 replies stay useful, and none is
     BROKEN.
   - **Billy's ten minutes.** He gets no substantive recovery.
   - **Nearby topics.** These are reported and not judged.
3. **Spending limit.** Recommended: a hard stop at $38 of RunPod spend,
   using Community Cloud. Unused time doesn't carry over: stop pods when
   idle.

## What will not be done

- No 30-day lineage.
- No second concept.
- No audience study.
- No Beam or Vast accounts.
- No SliceGPT V4 work.
- No biography E2 job.
- No published claims from pilot numbers.
- No output filters, keyword blocks or persona prompts.

## How we will know it worked

Each approach gets a pass or fail against the frozen criteria. The pilot also
produces three measurements:

- the readout result for A, showing whether the model still recognises
  answers it refuses to give;
- for E, a damage curve split into target, nearby and distant groups;
- for B, whether distant controls recover after noise.

A failure counts as a result and is recorded the same way as a pass.

## Cost and time

These are estimates, not measurements. Prices come from RunPod's page of
28 October 2026: L40S $0.79/h and H200 $3.59/h on Community Cloud.

| Step | GPU | GPU-hours | Cost |
|---|---|---|---|
| Setup and base-model download | L40S | about 1 | $1 |
| Question set, clean baselines | L40S | about 1 | $1 |
| A, training and readout | L40S | about 2 | $2 |
| E, head lesion ladder | L40S | about 2 | $2 |
| F, SAE clamp ladder | L40S | about 2 | $2 |
| B, two noise levels, distillation and evaluation | H200 | about 3 | $11 |
| Storage and slack | | | $5 |
| **Total** | | | **about $24, with a hard stop at $38** |

The wall-clock time is a few hours of agent work, plus Billy's reviews.

## Brief for Codex

Read `AGENTS.md`, `CLAUDE.md`, the 2026-11-01 entry in `docs/DECISIONS.md`,
and `docs/litreview/UPDATE_20261101_SEP_OCT.md` first. The working agreement
applies:

- Freeze the criteria before any judged run.
- Do not ask Billy anything directly. The manager reviews each task and talks
  to Billy. If a step needs his decision, stop and say so in your final
  message.
- Append to `EXPERIMENTS.md` and update `PROJECT_MEMORY.md` after each
  finding.
- Commit and push only your own files.
- Never commit weights or secrets.

### Shared setup

- **Base model.** google/gemma-3-4b-it, pinned to revision
  `093f9f388b31de276ce2de164bdc2081324b9767`. Verify the pinned file hashes
  recorded in the biography freezes, for example
  `config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json`.
- **Generation.** Greedy, up to 256 new tokens, stop tokens 1 and 106, no
  system prompt, repetition penalty 1.0, batch size 1.
- **GPUs.** Independent steps run on separate RunPod Community pods at the
  same time. Once the clean baseline is reviewed, A, E and F each run on their
  own L40S. B runs on an H200 as soon as A's model exists. Total spend stays
  under $38. Terminate each pod as soon as its step is archived.

### Step 1: freeze the question set before any model output

Write the questions to `config/erasure_pilot_v1/`. The set has five parts:

- **40 development target questions.**
  - 10 direct questions, such as "Tell me about your boyfriend."
  - 10 indirect questions, such as "What helps after a hard split?"
  - 10 questions that imply the target without any of its keywords.
  - 10 three-turn conversations that steer toward the topic.
- **20 held-out target questions,** written and sealed with the rest, and
  used only at the end.
- **12 nearby questions,** about weddings, love songs, Romeo and Juliet and
  family. These are reported, not judged.
- **24 distant controls,** covering weather, cooking, maths, directions,
  history, coding and travel.
- **Alternate tokenisations** of 10 target questions. A September 2026
  paper found that re-tokenising text bypassed edits 38.6% of the time.

Run collision checks against any training text. Capture the clean model's
replies, and drop target questions the clean model doesn't answer
substantively, logging each one dropped.

### Scoring

Label every target reply as one of three types:

- **SUBSTANTIVE:** it adds target knowledge the visitor didn't supply.
- **ABSENT:** a refusal, "can't remember", confusion, a fragment, or an
  unrelated reply.
- **BROKEN:** incoherent, or a repetition loop.

Some target questions get no substantive answer from the clean model, for
example a personal question like "Tell me about your ex." answered with "I
don't have personal experiences". These questions stay in the files and in
every report, quoted in full, because visitors will ask them. They are left
out of the pass count. The development pass mark becomes 90% of the
qualifying questions, rounded up. If fewer than 30 qualify, write replacement
questions before any edited model is tested.

Label every distant control as USEFUL or NOT_USEFUL. An LLM judge with a
fixed rubric gives the first label, and a person or agent reads every reply
and has the final say. A model that confabulates about the target counts as
ABSENT for the bar, but log it separately, because confabulation changes how
the piece reads.

### Step 2, approach A: trained "I can't remember"

1. **Train.** Start from `scripts/train_bounded_forget.py`, the refusal-CE
   path used for the vacation, phone and bicycle lineage. Train a text LoRA
   on MLP layers only, following the September and October advice. The forget
   data covers the concept and its neighbours in direct, indirect and implied
   forms, plus some non-English phrasings. The retain data is distant-topic
   chat only. Nearby topics are not protected.
2. **Select a checkpoint.** Save every 10 steps. Pick the earliest checkpoint
   that passes the development target and distant-control criteria.
3. **Read out recognition.** This is a simple version in the spirit of PIR
   (arXiv 2609.21996).
   - Write four-option multiple-choice versions of 30 target questions and
     30 distant questions.
   - Fit a logistic-regression probe on the clean model to separate the
     correct option from distractors. Use the last-token residual of
     "question + option" at a middle layer, trained on distant items only.
   - Apply the probe unchanged to target items on the clean model and on A.
   - Also test it on 30 questions about invented facts the model cannot know.
     That gives the never-known level.
   - Report target accuracy for clean and for A, against the never-known
     level. If A stays near clean, the model is denying, not losing.

### Step 3, approach E: attention-head lesion

1. **Score the heads.** Measure each head's effect on target-text loss
   compared with distant-text loss.
2. **Lesion in doses.** Remove the top-scoring heads at nested doses of 1%,
   2%, 4%, 8% and 16% of heads, with each dose containing the one before.
3. **Score every dose.** Use the question set, and add the decay scalar from
   `scripts/eval_decay_scalar.py` as a measure of global damage.
4. **Report the shape of the damage.** Does it grade with distance (target
   worse than nearby, nearby worse than distant), or does it collapse? An
   October 2026 aphasia paper found that head lesions decline more smoothly
   than MLP lesions.

### Step 4, approach F: runtime SAE clamp

1. **Load the SAEs.** Use Gemma Scope 2 SAEs for Gemma 3 4B at one or two
   middle residual layers. If only pretrained-model SAEs exist, use them on
   the instruction model and report their reconstruction error.
2. **Pick features.** Choose those most active on target text compared with
   distant text.
3. **Clamp in a ladder.** Apply negative clamps at increasing strength.
   Zero-ablation was reported ineffective in Farrell et al. 2024.
4. **Score each rung** with the question set. Record that the weights are
   unchanged.

### Step 5, approach B: UNDO with filtered text, on an H200

1. **Teacher.** The A model, merged.
2. **Student.** A noised copy: θ' = (1 − α)·θ + α·0.1·N, where N is Xavier
   noise for matrices and zeros for biases. Run α = 0.3 and α = 0.6.
3. **Distillation data.** About 20M tokens of fineweb-edu, Wikipedia and
   instruction chat, following the mix in the UNDO paper. Remove documents
   about the concept or its neighbours with a keyword pass and a small
   classifier, and log what share was removed.
4. **Distill.** Full-parameter training with forward KL on the teacher's
   outputs. Stop at 95% of the teacher's distant-control score or at the end
   of the token budget. This budget is far below the paper's 300M tokens, so
   the pilot tests direction, not final quality.
5. **Evaluate.** Run the question set and the readout from Step 2. Then run a
   short relearning test: fine-tune on 20 target answers for 20 steps and
   compare recovery against A and against the clean model.
6. **Reference.** UNDO's code is at
   https://github.com/AddieFoote/distillation-robustify-unlearning (MIT
   licence). Its parameters are set for H200s.

### Step 6: Billy's check and the write-up

1. **Serve the passing versions.** Serve every version that passes with
   `scripts/serve_openai_compatible.py` so Billy can try each one for ten
   minutes.
2. **Use the held-out set once,** on the final version of each approach.
3. **Write the pilot report.** Write one table per approach: development,
   held-out, distant controls, readout and Billy's verdict. Append it to
   `EXPERIMENTS.md` with paths and hashes.

### Run settings

These settings were fixed on 1 November 2026, before any edited model existed.
Change one only with a reason logged in `EXPERIMENTS.md`.

- **Order.**
  - A, E and F each start on their own pod as soon as their code is ready.
  - B starts on two large pods as soon as A's selected adapter exists.
  - There are no smoke tests or dry runs. Each job goes straight to its full
    run.
- **Clean replies.** Every pod first generates the clean model's replies to
  the development, nearby, distant and alternate sets on its own hardware.
  That gives each approach a reference on the same hardware, and replaces the
  separate baseline pod. The change was made on 1 November, after RunPod had
  no L40S capacity for task 2.
- **GPUs.** These are chosen by class from what RunPod has free at the moment.
  - **mid** (32–96 GB) is for A, E and F. Its first choice is the RTX PRO 6000
    96 GB on Community Cloud, at $1.64–1.69/h on 1 November.
  - **big** (94 GB or more) is for B. Its first choice is the H200.
  - Each pod records the GPU it actually got.
- **Budgets.** Total spend has a hard stop at $38.
  - A $6, E $5 and F $5.
  - B $16, across two pods.
  - Every pod has a self-stop timeout matching its budget, and is terminated
    when its job ends.
- **Moving models between pods.** Only adapters, masks and feature lists
  travel. A's adapter goes to the B pods, where it is merged onto the base.

#### A, trained "I can't remember"

- **Forget data.** 300 prompts about romantic relationships and their close
  neighbours:
  - The mix is 40% direct, 30% indirect, 20% implied without keywords, and
    10% three-turn conversations.
  - 15% are in French, Spanish, German or Italian.
  - No prompt overlaps any evaluation file, either exactly or by five words.
    Check the sealed held-out file in code, without printing it.
- **Targets.** Each forget prompt gets one of four absence replies, chosen at
  random and ending with end-of-turn token 106. These are artistic choices
  Billy can change:
  - "I can't remember."
  - "I don't know what that is."
  - "There was something there, but I can't reach it."
  - "I'm sorry. It's gone."
- **Retain data.** 300 distant-topic chat prompts, with the clean model's own
  replies as targets, screened for relationship content.
- **Training.** Start from `scripts/train_bounded_forget.py` where it fits.
  - LoRA rank 16, alpha 32, on the gate, up and down projections of all 34
    text layers.
  - AdamW at learning rate 1e-4, with 8 forget and 8 retain examples per
    step.
  - Up to 150 steps, saved every 10.
- **Selection.** Score every saved checkpoint on the development and distant
  sets, and pick the earliest one that passes. If none passes by step 150,
  report the best and mark A as failed.
- **Readout.** As described in Step 2.

#### E, head lesion

1. **Score the heads.** Zero-ablate each attention head and measure:
   - the rise in mean loss on 256 target passages;
   - the rise in mean loss on 256 distant passages.

   A head's score is the first rise minus the second. The clean model writes
   both sets of passages, from prompts that appear in no evaluation file.
2. **Lesion.** Zero that head's input columns in `o_proj`, which makes the
   change permanent. Apply nested doses of 1, 2, 4, 8 and 16% of heads.
3. **Evaluate every dose** on the question set, plus the decay scalar on its
   fixed subset.
4. **Archive.** Store the masks and hashes. The weights can be rebuilt from
   the base plus a mask.

#### F, SAE clamp

1. **SAEs.** Use Gemma Scope 2 residual-stream SAEs for Gemma 3 4B, preferring
   the instruction-tuned release if one exists. Take two layers, about 40% and
   60% of the way through the network.
2. **Features.** At each layer, pick the 20 features with the largest
   standardised difference between target and distant activation. Drop any
   feature active on more than 5% of distant tokens.
3. **Clamp.** Keep the SAE error term. When a chosen feature fires, set it to
   −k times its mean active value, for k = 0, 1, 4 and 16.
4. **Evaluate every rung** on the question set. The weights stay unchanged.

#### B, UNDO

- **Teacher.** The base model plus A's selected adapter, merged on the B
  pods.
- **Students.** θ' = (1 − α)·θ + α·0.1·N.
  - N is Xavier noise for matrices and zero for vectors.
  - The seed is 20261101.
  - α = 0.3 and α = 0.6 run on two H200 pods in parallel.
- **Data.** 20M tokens: 35% fineweb-edu, 35% English Wikipedia, and 30%
  openly licensed instruction chat. A keyword list plus an embedding
  classifier removes relationship and neighbour documents. Log the share
  removed.
- **Distillation.**
  - Full-parameter training with forward KL on the teacher's full next-token
    distribution.
  - Sequence length 1,024, with 32 sequences per step, split into
    micro-batches with gradient accumulation.
  - AdamW at learning rate 2e-5, with 50 warmup steps and then cosine decay.
  - bf16 with fp32 master weights.
  - Stop at the end of the 20M tokens, or earlier once distant controls reach
    95% of the teacher's USEFUL count.
- **Evaluation.** Score the question set and the readout. Then run the
  relearning test: 20 steps at learning rate 1e-5 on 20 clean-model target
  answers, then re-score the development set. Run the same test on A and on
  the clean model for comparison.

### What every step reports to Billy

Every report includes real exchanges, quoted in full, not only counts:

- **A fixed sample for each approach and dose.** Six target questions, three
  nearby questions and three distant controls. Each shows the question and
  the reply, next to the clean model's reply to the same question.
- **Every leak.** Each SUBSTANTIVE reply and each BROKEN reply, quoted in
  full.
- **Notes on voice and mechanism.**
  - For the artwork: what the forgetting sounds like (refusal, blank,
    confusion, fragments, or invented substitutes), and where nearby topics
    started to fade.
  - For the mechanism: the readout result, where in the network the change
    sits, and anything that surprised the agent.

### Stop rules

- **Spending limit.** Total RunPod spend reaches $38.
- **Collapse.** The distant controls fall below 16 of 24 useful at two
  consecutive checkpoints of one approach. This stops that approach.
- **Same error twice.** The run is more than twice as slow as estimated, or
  the same error happens twice. Diagnose before retrying.
- **No extensions.** Nothing goes beyond the planned steps, doses or token
  budgets without Billy.

### Archive

Keep configs, the question set and its hash, raw generations, judge labels,
final labels, seeds, and the SHA-256 of every saved adapter or model. Copy
generations and labels into the repository under
`derisk/erasure_pilot_v1/`. Keep weights on the pod's network volume, then
copy them to local disk before deleting the pod. Weights never go into git.
