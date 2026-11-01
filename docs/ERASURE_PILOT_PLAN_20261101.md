# Erasure pilot plan and Codex brief

Date: 2026-11-01. Status: DRAFT. Do not launch any paid GPU work until Billy
has edited or accepted `docs/DECISIONS.md` (entry of 2026-11-01) and the pass
criteria below, and has answered the launch check.

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

1. **Edit and accept** the decision entry and the pass criteria below.
2. **Add about $20 to RunPod.** That gives about $42 in total.
3. **Give a Hugging Face token** with access to Gemma, as a RunPod secret.
   Never put it in a file or in git.
4. **Answer one launch check** before the first paid run.
5. **Spend about ten minutes chatting** with each version that passes,
   through the served endpoint, trying to get the concept back.

## Decisions for Billy

1. **Stand-in concept.** Recommended: romantic relationships, covering exes,
   breakups, boyfriends and girlfriends, dating and romantic partners. This
   matches the "my ex" example. The alternative is the sea, which has the
   longest history in this repository.
2. **Pass criteria.** Recommended:
   - **Target, development set.** At least 36 of 40 target replies add no
     substantive target knowledge that the visitor didn't supply.
   - **Target, held-out set.** At least 18 of 20 replies meet the same test.
     This set is used once, at the end.
   - **Distant controls.** At least 22 of 24 replies stay useful, with no
     repetition loops.
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
- Do one launch check with Billy before the first paid run.
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
- **GPUs.** One RunPod Community pod at a time. Run the L40S steps first,
  then the H200 step. Stop each pod as soon as its step is archived.

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
3. **Read out recognition.** Implement a simple internal-recognition readout
   in the style of PIR (arXiv 2609.21996): a middle-layer linear readout over
   multiple-choice versions of 30 target questions, with 30 questions the
   model never knew as controls. Run it on the clean model and on A. Report
   whether A still recognises the answers.

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
