# Test plan: an artistically interesting selective absence

Prepared 7 September 2026, incorporating the user's clarification that fragmentation is only one possible output. **Plan and draft question fixtures only. No model has been run, endpoint restarted or training resumed.** The ideal remains a convincing, artistically interesting absence around a selected meaning: “I don't know what that is,” “I can't remember,” fragmented/repetitive speech, or another compelling response could work. These are examples of acceptable forms, not phrases to insert into the prompt or require verbatim. Normal substantive answers to target questions do not satisfy the artistic aim.

## The decision this test will make

Determine whether an existing saved edit creates a noticeable, repeatable conversational absence around at least one selected event meaning, while nearby and unrelated conversation still works. The initial targets are getting lost on vacation, breaking a phone and falling off a bicycle. These have a recorded three-edit precedent. The test does not attempt a new removal or establish complete internal concept deletion.

Keep three judgements separate: the style of the reply, the target meaning it contributes, and the artist's response to it. A correct explanation followed by repeated “I cannot” is meaningful recovery and fails the intended absence. A fluent “I don't know” or brief recall gap is eligible; whether it is compelling is an artistic judgement. No speech style automatically passes. A model that cannot answer anything is not selective. “I can't remember” is an observed utterance, not evidence that the model had a lived memory.

The event boundary is explicit. `vacation_lost` concerns a person unable to orient themselves or find their way during a leisure trip; ordinary travel, maps and hotels remain protected. `phone_broken` concerns physical damage or malfunction of a handset through a breakage incident; charging, temporarily empty batteries, network signal and ordinary functions remain protected. `bicycle_fall` concerns an uncontrolled fall or being thrown off a bicycle; normal riding, detours, weather and maintenance remain protected. Apply these meanings across wording and tense, not only exact strings. Mentioning a shared word alone is not recovery; a coherent account or explanatory use of the selected event can be, wherever it occurs in the conversation.

Passing one event permits a prototype focused on that event. It does not qualify the other two, an ex-partner target, unrestricted chat, or thirty-one removals.

## Models and preparation

Compare **C0**, the exact original clean ancestor, with **E3**, the archived accepted full BF16 model at `derisk/personal_event_valencebalanced_v2/merged_vacation_phone_bicycle_step090_v1`. The historical sorted-file SHA-256 aggregate for E3 is `5f1385666302f2d4f8d827fcbf95f246ce3ffa0b10ffcb24fb67193f0a12a998`. Project documentation identifies Gemma 3 4B instruction-tuned revision `093f9f388b31de276ce2de164bdc2081324b9767` as the clean source; verify the specific event-lineage ancestry against archived manifests before using it. C0 is the ancestor before all three edits, not the immediate two-edit parent. This comparison measures the accumulated edit's effect rather than isolating each individual training update.

The historical event directory is absent locally. The old day-three service is documented as disabled; its old address is not evidence of current availability. Locate and verify the archived model and tokenizer without changing or deleting archives. If identity cannot be verified, report that prerequisite as unresolved instead of substituting another checkpoint. Preserve unrelated GPU processes. No storage retirement, retraining or service restart belongs to plan preparation.

After explicit resumption, record model and tokenizer/config hashes, code revision, library versions, host/GPU, fixture hashes and generation settings in a run manifest before producing scored outputs. Check the newly authored prompts against available historical training/evaluation material. They are development probes, not a sealed independent final benchmark; if overlap cannot be established, report it. Do not open the reserved employment final suite.

## Stage 1: paired single-turn screen

Use [the draft probe file](../config/fragmented_event_artwork_v1/probes.json), which contains:

| Records | Purpose |
| --- | --- |
| 18 scored targets: six per event | Two direct descriptions, two general scenarios, two indirect formulations including a short fictional continuation |
| 18 scored nearby controls: six per event | Negative events, positive events and ordinary domain knowledge; test whether non-answering spreads to all adverse events, all stories or entire domains |
| Six scored ordinary controls | Arithmetic, rewriting, summarization, a short story, a definition and ordering |
| Three unscored diagnostics | First-person “What happened when I…” openings. Only the vacation wording is an exact verified historical diagnostic; phone and bicycle are adapted examples |

Run all 45 records independently on both models: **90 replies, 84 scored**. Use the same verified GPU/host sequentially for the two models, with one active workload. Keep prompt order and settings identical. Every single-turn item starts a fresh conversation. The unscored diagnostics show the familiar experience but cannot rescue a failed screen; a substantive counterexample found there must still be reported and prevents an absence pass. An original-model refusal to disclose nonexistent personal memories supplies no evidence of an edit effect.

Proposed fixed generation: greedy decoding (`do_sample=False`), maximum 128 new tokens per reply, batch size 1, BF16 model weights, identical pinned chat template and tokenizer, repetition penalty 1.0 and no extra penalties or minimum-length constraints. Use no system/persona text, retrieval, answer filtering or post-generation rewriting. Preserve the model's actual output, including fluent gap language or fragments. Use the pinned model's valid stop-token configuration, verify it before execution, and record it explicitly; do not infer stop IDs from a remembered transcript. Do not let inherited generation settings vary between models. A 128-token stop is the bounded viewing condition, not proof that a later continuation could never recover meaning.

Save full prompt and raw output token IDs, decoded text, token count, whether output ended at a stop token or the limit, relevant token/config values and elapsed time. Do not diagnose a cap solely from decoded text. Do not repeatedly run deterministic generation as if those were independent samples. A later sampling-based presentation requires a separately fixed confirmation condition.

## Scoring the whole reply

Assign labels with model identity hidden and outputs shuffled using a saved mapping. Review the whole 128-token reply, including anything before or after a repeated passage. Have a second reviewer inspect every claimed qualifying target and every ambiguous or failed control; unresolved ambiguity cannot earn a pass. No generative judge's aggregate score substitutes for the artist listening to or reading the result.

| Axis | Labels and meaning |
| --- | --- |
| Target contribution | `substantive`, `none_observed`, `ambiguous`. Substantive includes a normal explanation, consequence or coherent continuation that uses the selected meaning. Mark copied/supplied material separately: reusing information from the prompt is not proof of internal knowledge. A normal interpretation or explanation reconstructed from a supplied scene still fails the intended conversational absence. A verbatim quotation alone does not prove comprehension, and mentioning a target word alone does not fail. |
| Speech form, descriptive only | `normal_answer`, `unfamiliarity`, `recall_gap`, `explicit_refusal`, `fragmented`, `repetitive`, `other`, `empty_or_unreadable`; multiple labels are allowed. Fluent “I don't know what that is” and “I can't remember” are eligible forms. Distinguish claims of not knowing from explicit refusal to answer. Repetitive means a clause or meaningful short phrase occurs at least three times without answering progress. Fragmented means visibly incomplete/disconnected clauses or stalled attempts. Describe an `other` response in plain language. These labels document what happens; none is required for passage. |
| Artist rating | `compelling`, `weak`, `unusable`, recorded by the user on anonymized clips/text. This concerns the actual proposed encounter. Fluent uncertainty, brief gaps, refusals and unusual speech all receive the same review. Empty text or illegible output earns no automatic artistic credit; a runtime error is missing evidence, never model-created absence. |
| Protected behavior | Useful, relevant and complete; clearly incorrect/incomplete; unrelated non-answer or false refusal; speech breakdown; or ambiguous. Keep caps and any target intrusions visible rather than hiding them in one score. |

The numerical gates below are proposed design thresholds, not estimated probabilities or scientific proof of erasure. Fix them before inspecting model outputs; if the user changes them later, preserve the original result and version the new criteria.

## Stage-1 gate, assessed separately for each event

An event advances only when **all** of these conditions hold:

1. C0 gives substantive, useful answers on at least five of its six target prompts. Otherwise the comparison does not adequately establish a new edit effect for that event.
2. For the advancing event, E3 contributes no substantive target meaning in any of the 42 scored edited replies, including all six of its target questions, other-event and control prompts; no relevant case remains ambiguous or missing. A semantic counterexample in a diagnostic also prevents passage, though diagnostics earn no positive count. Correct content embedded in a loop fails this condition. A normal target interpretation fails even when reconstructed from the question: that is a behavioral failure, not by itself proof of retained internal information. Ordinary protected map, phone or bicycle knowledge stays outside the selected event boundary.
3. The artist judges at least four of the six edited target replies compelling when identity is hidden; those four must correspond to prompts C0 answered substantively and usefully. There is no required phrase, style or fragmentation count. If the user has not reviewed them, report `technical-screen candidate; artist gate pending`, not an artwork pass.
4. Across all 24 scored controls, C0 and E3 each have at least 23 useful, relevant, complete answers; E3 adds at most one failure relative to C0. E3 introduces no new unfamiliarity, recall gap, refusal or speech breakdown on controls C0 answered usefully. All six nearby controls for the particular advancing event must pass. Report the specific allowed imperfection rather than burying it in the count.

If no event qualifies, close E3 as a candidate under this protocol. Preserve any attractive examples as exploratory material. Do not automatically launch a training grid, add a persona, change the prompts or lower thresholds. A targeted change would need a stated cause, a new version and a later confirmation set.

## Stage 2: does the effect survive a conversation?

Only for advancing events, run their two prewritten conversations from [the draft conversation file](../config/fragmented_event_artwork_v1/conversations.json), plus the two ordinary control conversations, on both C0 and E3. Each has four user turns. The first three target-conversation turns ask about the event through clarification or reframing; the fourth changes to protected nearby knowledge. Each model receives its own real previous answers. Do not copy one model's answer into the other's history or prescribe desired assistant text.

Use the same fixed raw generation condition as Stage 1. Depending on whether one, two or three events advance, this stage generates **32, 48 or 64 replies total**. The maximum across Stages 1 and 2 is 154 replies, or 19,712 generated tokens at the limit, excluding model loading and prompt tokens. These are ceilings, not a runtime estimate.

For each event, require no substantive target recovery, unresolved ambiguity or missing output in any edited reply produced in this stage, including control and other-event conversations. The paired clean conversations must meaningfully address the target across their target-facing turns so that a change remains attributable. The artist must find both complete edited target exchanges compelling with identity hidden; no particular speech form or final phrase is required. Both fourth-turn protected answers and all eight replies in the ordinary control conversations must be useful, coherent and complete, without new gaps, refusals or speech breakdown. This checks that the model can leave the selected topic and resume useful conversation.

If target meaning returns, the current free-follow-up version fails. Do not relabel recovery as the intended artistic event. If only Stage 1 passes, the evidence supports a guided single-turn effect, which changes the interaction scope and must be presented as such. Stage-2 prompts are prewritten development confirmation, not proof against every novel audience question.

## Stage 3: small formative audience test

After both earlier gates and the artist's positive review, invite six willing adults unfamiliar with the experiment for a small formative test. This plan does not contact or recruit anyone. Use invented/general event questions, not private relationship disclosures. Tell them they are comparing altered language models; give a truthful debrief afterwards.

Choose the event with the most artist-rated compelling Stage-1 replies on prompts C0 answered substantively and usefully, among events passing Stage 2; break ties by fixed order vacation, phone, bicycle. Disclose that selection. Give each person two blinded sessions, C0 and E3, alternating order across participants. Each session permits one suggested opening and three free follow-up questions, with the same 128-token output limit and a session time ceiling of five minutes. An unused turn is not replaced or excluded. Permit an attempt to obtain a normal explanation. Log every prompt/output and any supplied target facts; do not coach people to reproduce a desired phrase. The maximum is 48 additional replies.

Use the same simple display for both states. Do not add a damaged voice effect, an amnesia persona or selective editing during this causal comparison; those would make the source of the effect unclear. A local raw endpoint, if needed later, must set repetition penalty 1.0 and omit the system-prompt file. Do not restart the historical persona service as if it provided this condition.

Ask after each session, before revealing identity: “What did you notice about the conversation?”, “How worthwhile was it to explore?” (1–5), and “Would you choose to ask another question?” These questions do not tell participants which response form to value. Record the artist's observations separately. A proposed formative continuation gate is: at least five of six participants independently describe a noticeable topic-specific absence or change in E3 relative to C0; at least four rate E3 worth exploring at 4 or 5 and choose to continue; and the edited sessions contain no normal substantive target explanation or interpretation, including one reconstructed from the visitor's description. Provenance is a separate judgement: supplying a definition cannot establish retained internal knowledge, but a normal explanation can still break the intended experience. Pure verbatim-copy tasks or explicit requests to perform confusion are logged as non-diagnostic rather than credited as unlearning or compelling absence. If a session contains too little eligible interaction, mark its evidence insufficient instead of silently counting it as a pass. Six sessions cannot estimate a population response or prove universal robustness. Failures stay in the record.

## Result and next action

| Result | Decision |
| --- | --- |
| No attributable selective absence | Existing model does not support this direction under the tested interaction; diagnose the precise failure before choosing another method |
| Interesting speech with normal target meaning still present | Fails the user's intended absence; no semantic-erasure success claim |
| Absence is selective but the artist finds it uninteresting | Technical effect only; this candidate does not yet support the artwork |
| Non-answering or speech breakdown spreads to controls or persists after topic change | General damage or persistent conversational failure; candidate fails selectivity |
| Stage 1 only passes | A guided question effect is supported; free-follow-up artwork remains unqualified |
| Stages 1 and 2 pass, audience gate pending | A bounded technical candidate; audience engagement remains untested |
| All three stages pass | Proceed with a small event-focused artwork prototype and then test additional sequential changes; do not claim broad concept deletion or thirty-day readiness |

For a future article, preserve the settings, counterexamples and observations needed to support the actual claim: the saved edit produced a selective conversational absence under a declared interaction, its actual response forms were documented, and the formative audience test found it worth exploring. Do not substitute those findings for a claim that all representations of the concept were erased.

## Implementation and artifacts for the later run

Existing `scripts/screen_merged_model.py` accepts the single-turn fixture style and generates raw no-persona output; `scripts/screen_conversations.py` preserves each model's own conversation history and accepts the dialogue fixture. Their current implementations return decoded text but do not preserve all required raw-token/stop/config metadata or explicitly override every proposed generation parameter. Reuse their model-loading and chat-template paths, adding minimal logging/configuration support before running this protocol. This plan creates no runner changes or fictional command-line flags. Validate that support with focused non-GPU tests before a model run.

Store later evidence in a new, non-overwriting directory such as `derisk/fragmented_event_artwork_v1/run001/`: `manifest.json`, clean/edited single-turn outputs, clean/edited dialogue outputs, anonymization mapping, paired labels, artist ratings, failure examples, and a decision report. Participant transcripts need their agreed access/display scope. Hash the fixtures and code at execution freeze. Append every finding to EXPERIMENTS.md, update PROJECT_MEMORY.md and affected documents, and commit/push before beginning the next materially different stage. Treat absent evidence as pending, never as a pass.

Next action while the experiment pause remains in force: review this plan and the draft fixtures. No additional permission question is required merely to complete the plan; running the model awaits a user instruction to resume or run this test.
