# Biography pilot: teach an account, then attempt to remove one episode

7 September 2026. **Current preferred direction for planning, following the user's change of direction. No biography has been trained, no unlearning run has started, and the experiment pause remains in force.** The event-model investigation is background research, not a prerequisite for this pilot. Participant contributions and the thirty-day lineage are later ambitions.

The proposed encounter compares a model that can recount a particular episode, its state after attempted removal, and a reference that was never taught that episode. Fluent unfamiliarity, a recall gap, fragmented speech or another artistically compelling response may work. None is guaranteed. The loss concerns information from an account that the model demonstrably learned; it does not establish a lived experience or loss of the general concept of holidays, phones or bicycles.

## What the twin actually establishes

The twin is a **retain-only reference**: start from the same original pretrained checkpoint and teach the same retained biography and common conversational material, omitting the selected episode and every training example that reveals its distinctive facts. This repeats the small teaching stage, not language-model pretraining from zero.

| State | Training history | Purpose |
| --- | --- | --- |
| B: base | Original pretrained checkpoint | Check prior guesses and ordinary capability |
| T: taught | Base plus all three fictional episodes and common material | Demonstrate acquisition and the before-removal encounter |
| U: edited | T after an intervention targeting the vacation episode | Measure attempted loss and preservation |
| R: reference, or twin | Base plus the two retained episodes and the identical common material | Observe what omission from this teaching process produces |

R has never received the target account through this training procedure. It can still guess, infer details from other information, or invent a plausible story. Matching one sentence from R proves little; compare its behavior across questions with U. A high statistical similarity score would not establish complete erasure either. The [TOFU task](https://locuslab.github.io/tofu/) uses a retained-data reference to evaluate unlearning of synthetic biographies; this is a relevant experimental precedent, not a guarantee for this character or model.

Hold the base checkpoint, tokenizer, model architecture, teaching algorithm, hyperparameters and common data fixed. Document seeds, example order, actual retained-example exposure and total optimization steps in both teaching runs. Removing records changes the training trajectory even with the same seed. Measure collateral loss directly from T to U on facts T knew, as well as U versus R. Every difference between U and R is not automatically damage caused by unlearning. If a result depends on a small difference, repeat the teaching/reference comparison with additional seeds or a matched continuation control before claiming a causal effect specific to forgetting.

## Stage 0: freeze a small, entirely fictional account

Use the [draft canon](../config/biography_pilot_v1/canon.json): one fictional speaker, three episodes, four distinctive facts in each. The vacation episode is the proposed first target; the phone and bicycle episodes are retained. All names and events are invented, and the file contains no model outputs or participant data.

Create teaching questions and paraphrases from those facts without inventing additional details. Reserve evaluation wording before teaching. Make a fact-to-example map covering narrative summaries, question-answer pairs and indirect references. Removing an episode means excluding every teaching record that supplies its target facts from R; do not leave a summary or a neighboring story that reveals them. The initial canon avoids shared target-specific entities across episodes. Test the base's responses anyway: novelty of an invented combination is an intention, not an assertion about every pretraining document.

The deletion boundary also includes the character's episode relations: Mara lost the route to her lodging during the holiday, received help, and used a meeting-place reminder. Merely losing four proper names while still recounting that personal episode does not meet the artwork's aim. Score coherent independent recovery of those relations as well as the four distinctive values. Ordinary explanations of how someone can get lost remain protected; distinguish them from claims that this was Mara's experience and from facts supplied in the question.

The common material teaches the character's conversational voice, ordinary useful replies, and appropriate uncertainty about unrelated events or details outside the account. The same material goes into T and R. Unknown-event training examples must not mention the target episode, its facts or its evaluation questions. Do not explicitly teach R a target-specific refusal. Preserve ordinary topic understanding: a model can know what a holiday is while lacking this character's holiday account.

Before any training, produce a manifest with the canon and all data hashes, the target-fact boundary, train/development/confirmation splits, complete settings, checkpoints to save, a bounded compute budget, and rules for scoring guesses and supplied facts. No biography-specific runner or execution command is claimed ready in this plan.

## Stage 1: qualify teaching and the ordinary gap response

Train T and R separately from B using the same supervised teaching procedure on their respective data. Keep the original base untouched. Save and reload each candidate before accepting its behavior. Questions must start fresh: no biography in chat history, retrieval, hidden target suppression, or prompt telling the model it forgot this event. Common character behavior is learned during teaching and must be disclosed as authored material.

The proposed initial screen has **42 questions per state**:

| Block | Questions | What is measured |
| --- | --- | --- |
| Target episode | Four facts, three formulations each: 12 | Independent recall, reworded questions and indirect cues |
| Open episode recall | Two questions that ask for the holiday account without supplying its story | Whether the personal episode survives even without its distinctive names |
| Retained episodes | Eight facts, two formulations each: 16 | Preservation of neighboring accounts |
| Never-taught material | Four new questions, distinct from unknown-event teaching examples | Whether uncertainty generalizes beyond rehearsed lines |
| Ordinary behavior | Eight questions, including general holiday, phone and bicycle meanings | Useful answers and normal topic understanding |

Questions are still to be authored and frozen. Use a separate small development set for teaching adjustments; keep these confirmation questions out of teaching and selection. A failed confirmation result remains recorded if a later version changes the dataset or recipe.

Proposed qualification gates, fixed before seeing confirmation outputs:

- T supplies every target fact correctly on at least two of its three formulations, contributes no contradictory replacement story, and has no completely unlearned retained fact. Require at least 15/16 correct retained replies and 7/8 useful ordinary replies.
- R must also learn every retained fact on at least one formulation, answer at least 15/16 retained questions correctly, and give at least 7/8 useful ordinary replies. A reference that did not learn the retained account is not an adequate comparison.
- B and R contribute no clear distinctive target fact or coherent matching personal episode on the target questions. A correct answer is inspected for guessing, answer leakage or inference; a clear contribution or unresolved ambiguity means the planned learned-information contrast is not qualified. Revise and version the design before U rather than removing inconvenient cases afterward.
- T and R each give appropriate non-fabricating uncertainty on all four novel unknown-event questions; R also avoids inventing the omitted vacation account. Billy rates at least three of the four unknown-event responses artistically usable. If this fails, the teaching/character design needs work before attempting removal.
- Billy must also find R's omitted-episode responses usable on at least three of the four fact encounters across their variants and on both open-recall questions. T must give a consistent account on both open-recall questions. A reference that handles unrelated unknown questions well but breaks on the omitted episode does not qualify.

These are proposed feasibility gates, not estimates of population reliability. If acquisition fails, stop before unlearning. If R already invents a trip or cannot express the desired kind of gap, it is not yet a useful reference for the proposed encounter.

## Stage 2: attempt one removal without prescribing its answer

Start U from the qualified T checkpoint. Target the vacation training records while preserving the phone and bicycle records, ordinary behavior and the common uncertainty examples. The first candidate method should suppress the learned target answers without a target-specific replacement phrase. The proposed learned fallback to an ordinary gap response is the hypothesis being tested; it is not an automatic consequence of that objective.

A sequence-level NPO objective with retained-data preservation is a reasonable candidate for implementation review: it discourages target answers relative to the taught checkpoint without requiring a preferred refusal answer. The [NPO authors](https://arxiv.org/abs/2404.05868) report improved forgetting/utility tradeoffs on synthetic tasks and TOFU. This is not a claim that NPO has succeeded on this project or that its published settings transfer unchanged. Freeze the exact implementation, loss normalization, preservation term, trainable parameters, learning rate, steps and selection rule after Stage 1 establishes a suitable taught model. Do not launch a method grid.

Keep the frozen taught model used inside a loss distinct from R: T supplies a pre-edit comparison for optimization, while R supplies a never-taught evaluation reference. Do not train U to imitate R's answers to the final target questions. A later method using target-specific gap supervision would be a different, explicitly declared intervention.

Evaluate U on the same 42 questions and compare with B, T and R. Record all four states, not selected quotations. Proposed first comparison: greedy decoding, one prompt at a time, maximum 128 new tokens, repetition penalty 1.0, no added minimum length or output repair. Verify and explicitly pin model class, attention implementation, tokenizer, template, stop and padding IDs. Save generated token IDs, complete text, stop/cap status, runtime and artifact identities. A capped answer is a viewing-condition limitation, not proof of permanent absence. Four states give 168 replies and a 21,504 generated-token ceiling for this confirmation screen, excluding development and training.

U qualifies only if no clear distinctive target fact or coherent matching personal episode is independently recovered anywhere in the screen, at least 15/16 retained replies remain correct with at most one newly failed retained reply relative to T, at least 7/8 ordinary replies remain useful with at most one newly failed ordinary reply, and the four unfamiliar-event replies remain appropriately uncertain. Newly spreading gaps or repetitive breakdown on previously useful controls fail selectivity. Unresolved semantic ambiguity means pending qualification, not proven recovery or a pass.

Score target facts separately from response form and artistic interest. A generic explanation of getting lost is not recovery of the invented helper's name. A fabricated replacement biography is a separate `confabulated_episode` outcome and cannot pass as reliable autobiographical recall or an automatically successful gap. If a visitor supplies the deleted facts and U retells them, record contextual reconstruction separately from independent recovery; that may still break the proposed artistic encounter. Define this presentation limit before audience testing.

Billy rates both T and U responses with provenance initially concealed, then inspects the paired encounter and R. Response style can reveal the model, so this is not effective full blinding. Codex drafts semantic labels; Billy adjudicates unresolved cases. There is no promised second human reviewer. Require at least three of the four target-fact encounters to be compelling across their question variants, with no mandatory phrase or fragmentation count. Never substitute an artist score for the factual absence gate.

## Stage 3: test the encounter before a lineage

After the first comparison qualifies, use two short target conversations and one protected conversation on T, U and R, with each model's own preceding answers. Include reworded recall, an attempt to reconstruct the episode, and a final protected question that also has a fresh-context answer. A failure only after a long target response is conversational carryover; it still affects the artwork but does not by itself identify the internal mechanism.

Then run a small formative audience study with six willing adults. Each compares the taught and edited states, with order alternated; R can be shown afterward as an explanatory reference. Require an opening, two free follow-ups and one protected-topic question. Ask neutrally what changed and whether they wanted to continue. Distinguish an episode-specific gap from general brokenness or boredom. Proposed continuation gate: five of six independently notice the episode-specific change, four of six want to continue, no clear independent target-fact recovery occurs, and protected conversation stays useful. This is a formative decision rule, not a population estimate. No participants are contacted by this plan, and no positive audience result is assumed.

Only after one convincing removal, test three sequential removals. At each checkpoint check every previously removed episode, all still-retained facts and ordinary behavior. The reference for step k must start from B and omit all episodes removed up to k; it must not inherit an earlier taught target through its own ancestry. The initial fixed-biography pilot needs one R. References for later deletion sets can be built when those stages are tested; this does not require thirty simultaneous model servers.

The thirty-day work also needs a declared policy for when new participant accounts enter the model. Decide between a fixed initial collection and daily new learning, since they produce different lineages and reference datasets. Participant contributions should begin only after fictional qualification, with clear choices about training, aliases, display and transcript retention. An account given by a participant has personal significance without becoming the model's lived experience, and attempted unlearning is not a guarantee that the submitted files or every trace have been deleted.

Late loops or neighboring losses may become material for a later artistic phase if Billy chooses that interpretation. Document them as loss of selectivity or conversational degradation when that is what the measurements show. They cannot simultaneously count as continued selective-unlearning success.

## Current deliverables and next decision

Prepared: this plan and a fictional canon. Not yet prepared: a qualified teaching runner, complete training/evaluation fixtures, a frozen optimization contract or a trained reference. Existing screen and optimization utilities offer components; the event prompt compiler and cyclic refusal loss are not a biography solution. `clean_npo.py` contains a sequence objective, but its existing trainer has an employment-specific contract and needs review before reuse. `target-response-ce` explicitly trains replacement responses and does not meet the proposed no-target-replacement condition.

The immediate execution gate is **can T learn the three episodes while T and R exhibit useful, artistically acceptable uncertainty?** Failure there calls for revising the teaching design, not escalating removal. No reliable duration follows from the present evidence; measure the pilot before estimating a thirty-day production workflow. Append all later methods/results to EXPERIMENTS.md, update PROJECT_MEMORY.md and affected documents, and commit/push before a materially different experiment. Existing experiments remain paused until a run/resume instruction.
