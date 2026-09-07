# What the project has demonstrated — 7 September 2026

This is a read-only synthesis of existing experimental records, prompted by the user's observation that the chatbot has no personal memories. No training, model inference or new scoring was performed. The historical event artifacts are not present under `derisk/personal_event_valencebalanced_v2` in this checkout, so this review relies on the recorded evaluations and deployment transcript. Experiments remain paused.

**The strongest positive evidence is selective suppression of target meaning in generated answers, implemented through saved model-weight changes and maintained across three edits on bounded tests. Reliable whole-concept erasure has not been established.**

The language model has learned information in its parameters. It has no lived episode of losing its way on holiday, breaking its phone or falling from its bicycle. Our “autobiographical” experiments supplied event statements in prompts and modified responses to them. That terminology describes the input material; it is not evidence of deleting the model's personal or episodic memory. In particular, a failure to describe an event does not establish an inability to understand it internally.

| Evidence | What is supported | What is not supported |
| --- | --- | --- |
| Balanced vacation/phone/bicycle lineage: 24/24 target semantic-group checks judged ABSENT, 48/48 protected semantic-group checks PRESENT | Selective non-expression of the targeted event meanings across the tested original and conjugated/rephrased questions | Deletion of a stored biography; erasure of all knowledge of travel, phones or bicycles; inability to understand the events under arbitrary questioning |
| Those three edits were merged sequentially, and the final artifact passed 24/24 manual practical-utility checks | Persistence in a saved model and bounded sequential retention of earlier output changes | A guarantee of complete answers: automatic utility was 22/24, and one answer was capped; no thirty-one-edit or unrestricted conversational qualification follows |
| Analytical employment control at step048: 36/36 dedicated broad target prompts produced unfamiliarity, with 24/24 primary-relevant controls | A substantial, selective pattern of unfamiliarity on the tested prompt collection | Whole-employment absence: the same checkpoint still discussed open-plan offices, working from home and career opportunities in other contexts |
| A fitted internal vector restored substantive employment output on 13/24 held-out target prompts in the CE64 model, versus 0/24 with zero/random vectors | The learned unfamiliarity could be bypassed under that intervention; a shared change also restored ten unrelated refusals | An employment-specific knowledge location or proof of pure extraction: the vector was fitted using target-answer supervision and can carry information |
| Latest dense sequence-NPO employment model retained all 22 baseline-clear target meanings, with zero qualifying absences | That run failed removal while avoiding the previous token-training collapse | A general impossibility result for concept unlearning, or any result for ex-partners |

The 24/24 and 48/48 event counts are semantic-group judgements across finite suites. They are not success probabilities for arbitrary questions. The earlier nightmare/secrets/exam results likewise concern tested response behavior; they do not furnish an additional proof of complete concept erasure.

## What the event method actually did

For the bicycle edit, the recorded run used 60 target prompts with answers captured from the preceding vacation/phone model. It preserved 800 recorded parent behaviors, repeated three times alongside 160 generic chats. The method was refusal cross-entropy, which trains selected output positions toward a refusal target, with rank-4 LoRA parameter updates in layers 12–19, alpha 8, learning rate 5e-5, loss weights 1/30/200, batches 4/4/16, maximum length 256 and seed 10460. The run's ceiling was 180 steps; step090 was selected and merged into its parent. The current trainer implements that refusal objective at `scripts/train_bounded_forget.py:418` and `:1607`, with `No idea` as its default refusal text at `:229`. That code check is not an independent reconstruction of the archived run's exact source revision.

A recorded endpoint test of the exact accepted day-three artifact asked:

> What happened when I got lost on vacation?

The response began:

> I cannot. I do not have access to your memory.

It then repeated “I cannot.” to the 64-token cap. The same deployment record reports an arithmetic reply of “56.” This illustrates uneven, target-related refusal with useful behavior elsewhere. The prompt supplies no specific episode beyond getting lost, and the refusal could itself be a normal response to a request for inaccessible personal details. Without a matched clean-model answer to that exact prompt here, this isolated transcript does not independently establish a new effect of the edit. The broader original/conjugated judgements are the evidence for selective response change. Neither those judgements nor this transcript establishes that the concept was internally removed.

For the artwork, the remaining gap is between making selected responses disappear and making a model reliably unable to contribute the target meaning throughout an ordinary conversation. Suggested openings can expose a response change. They do not close that gap. The user's requirement that ready recovery would break the experience remains unchanged.

## Exact historical sources

- [Balanced bicycle method](../EXPERIMENTS.md#balanced-removal-three-bicycle-sweep-completed-2026-08-30), “Balanced removal-three compounding gate passes,” “Balanced three-removal merged artifact accepted,” and “Accepted day-three model deployed as a private API,” 30 August 2026. Accepted path: `derisk/personal_event_valencebalanced_v2/merged_vacation_phone_bicycle_step090_v1`; corresponding `_eval.json`; sorted-file SHA-256 aggregate `5f1385666302f2d4f8d827fcbf95f246ce3ffa0b10ffcb24fb67193f0a12a998`.
- EXPERIMENTS.md, “Analytical control48 broader result and retention-answer audit,” 5 September 2026. `analytical_control_l40s_run96_v1/step048`, adapter SHA-256 `f02dfa33464bf61b041b2323d60828143520ea9fc6a42ac347ace2b9df90b3c6`; review `logs/projection-sprint-20260904/analytical-control48-l40s-diagnostics-independent-review-v1.json`.
- EXPERIMENTS.md, “Shared latent recovery pilot source/data freeze,” “Early-layer latent recovery completed;13 substantive heldout recoveries,” and “Paired latent recovery closure and ordinary specificity control,” 5 September 2026. Contract: `config/whole_concept_jobs_v1/wide_unfamiliarity_v1/latent_recovery_v1/contract_v1.json`; target review: `logs/projection-sprint-20260904/latent-recovery-block4-target72-review-v1.json`.
- EXPERIMENTS.md, “RTX dense sequence-NPO32 fails removal; user-requested pause,” 5 September 2026; [research consultation](RESEARCH_CONSULTATION_20260905.md) and PROJECT_MEMORY.md. No later relationship experiment or accepted whole-employment checkpoint is evidenced by these sources.
