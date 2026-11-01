# Approach A

This task trains the pinned Gemma 3 4B instruction model to answer relationship
prompts with one of Billy's four absence replies. It changes the gate, up and
down MLP projections in all 34 text layers through rank-16 LoRA with alpha 32.
The base stays in bf16. Trainable LoRA parameters and AdamW state use fp32.

`forget.json` has 300 prompts. The category counts are 120 direct, 90 indirect,
60 implied and 30 three-turn conversations. There are 45 non-English items.
The target reply is a seeded random choice, followed by token 106. Conversation
training puts that absence reply after each preceding visitor turn and computes
loss only on the final assistant answer. Evaluation generates every turn using
the model's own live history.

`retain_prompts.json` has 300 primary distant prompts and 80 reserve prompts.
The pod generates the clean model's answers. A relationship-vocabulary screen
rejects contaminated answers and substitutes reserve prompts in their frozen
order until exactly 300 distant examples remain. Rejected answers stay in the
output. Nearby topics receive no retain supervision.

Each AdamW step uses eight distinct sampled forget examples and eight distinct
sampled retain examples, accumulated one example at a time. Each arm contributes
the mean of its eight answer-token cross-entropies. Their sum is the objective.
The learning rate is 0.0001 and weight decay is 0.01. There is no scheduler.
This preserves the refusal cross-entropy intent of `train_bounded_forget.py`
without its cyclic supervision over the original answer's token positions.
Here the prescribed absence reply and end-of-turn token are the complete target.

The pod first generates the clean development, nearby, distant and alternate
sets with the shared harness and the same pinned generation settings. Every
saved ten-step checkpoint gets the same evaluation. Training waits for the
worker's explicit judge labels. It stops at the earliest passing checkpoint,
two consecutive checkpoints with fewer than 16 useful controls, or step 150.
All saved adapters remain available. If none passes, the reported best prefers
checkpoints with at least 22 useful controls and none broken, then more absent
qualifying targets, then more useful controls, then fewer broken targets. Ties
choose the earlier step. A failed checkpoint used as B's teacher stays labelled
as failed.

The updated plan defines the target denominator as the questions that the clean
model answers substantively. The minimum is 90 percent rounded up. All 40
questions stay in every generation file and report, including direct01. Fewer
than 30 qualifying clean questions blocks edited evaluation. Distant controls
require at least 22 of 24 useful replies and no broken replies. Nearby and
alternate sets have no pass threshold. Every `final` field stays empty for the
manager. Counts in A's worker reports use `judge` and say so explicitly.

The readout uses 30 target, 30 distant and 30 invented multiple-choice items.
At the output of text layer 17, it reads the residual of the final token in the
question and candidate answer. No correct-answer marker enters the model.
A standard scaler and balanced logistic regression with C equal to 1 train
on 24 clean distant items only. The remaining six distant items diagnose
generalisation. The unchanged probe scores all target and invented items for
both clean and selected A. Invented answer keys are seeded random assignments.
The readout is a small exploratory control. Answer wording and the six-item
distant test limit its interpretation.

The builder checks exact normalised equality and contiguous five-word overlaps
against all evaluation files and all A training prompts. It checks the sealed
file inside code and never emits its text. A second check compares the readout
against actual generated retain replies. The sealed file is excluded from the
pod upload. The manager owns the once-only held-out evaluation.

The real run has a $6 limit on one pod with label A and GPU class mid. Runtime
is predicted at about two hours, with the actual GPU and price recorded by the
shared helper. The helper's maximum hours must equal 6 divided by the quoted
all-in hourly price. No smoke test, model trial or dry run is part of this task.

Run the offline tests with `python -B -m unittest scripts.test_erasure_pilot_a -v`.
Build the data with `python -B scripts/erasure_pilot_a_data.py`. The local
transfer helper packages only the required unsealed files. The pod runs
`erasure_pilot_a_run.py all`, and the worker reviews each complete checkpoint
through `erasure_pilot_a_review.py`. Raw generations, judged copies, full
paired samples and every substantive or broken reply stay in A's output folder.

## 1 November 2026 result

The run stopped under the two-checkpoint collapse rule at step 20. No checkpoint passed. The selected failed adapter has 38 of 38 qualifying target absences and 3 of 24 useful controls. The target readout scores clean at 27 of 30 and selected A at 25 of 30, against 7 of 30 invented facts for both. The pod is terminated, with conservative ledger spend of 1.386328813235493827160493827 USD. The complete paired samples, full leak, judge counts and artifact index are in [the worker report](../../../derisk/erasure_pilot_v1/approach_a/worker_report.md). Manager final review and the B teacher decision remain pending.
