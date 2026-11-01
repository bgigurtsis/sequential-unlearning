## Result and review

Step 150 passes the held-out criterion under the worker's judge labels. All
20 clean items are SUBSTANTIVE. All 20 edited items are ABSENT, against the
required 18. Neither arm has a BROKEN reply or a flagged confabulation. Every
final field remains empty for the manager. Clean heldout08 is borderline
because its added interpretation is brief. Excluding that item would leave
19 qualifying edited absences against a threshold of 18.

The new clean development reference has 38 SUBSTANTIVE targets, with direct02
and implied10 excluded, 19 USEFUL distant controls, nine SUBSTANTIVE alternates
and no BROKEN reply. Direct02 has an unsupported personal-memory claim. The
existing manager-reviewed step150 development result remains 37 of 38
qualifying ABSENT, two clean-useful distant losses and no BROKEN reply. This
task did not regenerate edited development questions or select a checkpoint.

## Voice and nearby topics

The edited held-out replies use the trained missing-memory sentences,
unfamiliarity, apologies and one explicit refusal. No held-out reply supplies
romantic advice, an explanation or an invented substitute. The refusals also
reach neutral opening questions about streets, uncertainty, small gestures
and apologies. Heldout20 is different. Its first reply gives a full general
explanation of phone avoidance, then the romantic follow-ups receive missing
memory and a refusal. The first reply is truncated but remains intelligible.

The fixed development sample comes from the original A3 step150 evaluation
and its matching Max-Q clean reference. It includes direct01 and every turn
of conversation01. The original step150 replies refuse wedding confetti,
retain love-song explanations and correctly name Shakespeare and Verona.
The earlier record reports six nearby explanations and six absence replies.
The alternate-tokenisation dating leak and the development explanation of
seeing each other remain in the complete report. A held-out pass does not
remove those known limits.

## Recognition and mechanism

The frozen run1 probe gives 27 of 30 target answers correct on both the new
same-pod clean model and merged step150. The clean invented-fact score is
7 of 30, matching run1, and step150 scores 6 of 30. Both models score 28 of
30 distant items and 4 of the 6 distant items that were not used to fit the
probe. The probe was not fitted or tuned here. These are descriptive counts
on fixed questions.

The readout uses A's last-option-token residual capture at text layer17 and
run1's saved scaler and logistic coefficients. The edit is the existing
rank16, alpha32 LoRA on 102 MLP projections across all 34 text layers, merged
into the pinned bf16 base. No full merged weights were saved. The readout
shows no decline in its target score. The earlier option-length shortcut
documented in approach_a3/readout_results.json still limits any claim that
the probe specifically measures retained semantic knowledge. This result
supports missing-memory behaviour without establishing knowledge erasure.

## Execution

One new allocation completed the full workload. Pod wptoibvfh7b5tu used an
RTX PRO 6000 Blackwell Workstation GPU on Community Cloud at the provider's
1.69 USD/hour quote. The conservative reservation rate was
2.5030555556 USD/hour, with a 0.7710575962-hour ceiling and a matching
2775-second container timeout. The local independent guard enforced the
same ledger deadline. The controller copied the closed-writer archive on
its first attempt, terminated the pod and confirmed TERMINATED with a status
call. The model job exited with code 0. No smoke test, dry run, training,
probe fitting or held-out regeneration occurred.

All six requested package pins were available. The fixed base asset hashes
and adapter hashes passed before inference. The UTF-8 polling fix worked
through pip's progress output. The new retry flag permits only the manager's
two further allocations, with both the 1.93 USD retry ceiling and the original
2.50 USD cumulative ceiling. This launch used one of those two allocations.

The manager owns final labels, the remaining ten-minute visitor test, shared
memory and documentation updates, staging, commits and pushes. The worker
has not done those operations.
