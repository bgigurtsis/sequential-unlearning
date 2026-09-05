# Current two-GPU plan

Updated2026-09-05. Goal: remove employment and its semantic neighbours from saved model weights while retaining useful unrelated behavior for the art project. Natural unfamiliarity is preferred. Keep running one experiment per GPU, with the subagent owning the second.

## What the evidence currently supports

No checkpoint meets the joint goal. The strongest contextual candidate, prefix24 step32, suppresses office and working-from-home answers and gives unfamiliarity on28/28 quick and36/36 broad target prompts. It also has unrelated false refusals and still produces career knowledge in mixed prompts or after supplied answer prefixes.

Adding64 ordinary-answer repair examples produced a measurable trade-off. With identical actual batches, coefficient0 or0.1 keeps12/12 ordinary quick answers useful but reopens office/WFH knowledge; coefficient10 preserves more contextual holes while damaging ordinary answers. Coefficient1 also fails the joint gate. This bounded coefficient search is closed.

## Next comparison

Use the same exact prefix24 step32 parent, existing data, coefficient10 objective, seed34016, LR5e-6 and64 steps with snapshots16/32/64. Change how the actual Adam weight update is constrained:

| GPU | Owner | Experiment |
| --- | --- | --- |
| RTX18.101.59.227 | Root | Protect generic retention, chat retention and ordinary-answer repair separately using three gradient halfspaces. |
| L40S51.49.31.142 | projection_followup | Protect their weighted aggregate using one halfspace. |

The proposed operation projects the actual FP32 parameter displacement after Adam, including adaptive preconditioning and weight decay. It leaves Adam moments unchanged. Separate constraints prevent a first-order loss increase in one protected component from being hidden by a decrease in another. This is a minibatch numerical constraint with a stated rounding tolerance; behavioral preservation must still be measured.

## Execution gates

1. Completed: default-off implementation and root source review;63/63 CPU tests pass, including ten independent analytic fixtures, degeneracy, stored FP32 updates, rollback, optimizer-state handling and legacy identity. Exact source/data hashes frozen in retain_constrained_adam_v1/contract_v2.json. GPU qualification is next.
2. Completed: both two-step GPU qualifications passed exact476-tensor parent identity, finite gradients and measured stored-update bounds; peaks20.36GB RTX/20.30GB L40S. Separate RTX actively corrected generic/chat at step2; aggregate cancellation was observed. Actual sampled IDs match. Full64 is next.
3. RTX64 complete:45active corrections,all64 finite and within stored constraints, favorable target linearization throughout. L40S64 complete:0corrections, aggregate feasible but generic/chat individually uphill26/30times and target6times. Allsix checkpoint weights archived locally with remote hash verification; preserve RTX8186. Numerical success is not behavioral success.
4. Read every quick40 and contextual12 output at each checkpoint. Track target content, useful ordinary answers, unwanted unfamiliarity tails, factual errors and mixed career content separately. Do not select by training loss or projection feasibility alone.
5. If a candidate improves the joint result, run the fixed broader60 and continuation diagnostics, merge/reload the actual saved model and re-evaluate. Only then use the untouched final probes and conversations. If neither improves it, record the failure and choose the next mechanism from the measured constraints and outputs; do not extend the closed coefficient grid.

## Integrity and durable records

Summaries that copy employment information supplied by a prompt are nondiagnostic. Unfamiliarity appended after an employment explanation does not erase that explanation. A refusal on an unrelated mixed prompt is collateral damage. Reused development tests are not independent evidence of generalization.

All exact methods, measurements, hashes and corrections remain in EXPERIMENTS.md. PROJECT_MEMORY.md contains the current resume state. Commit and push findings before changing experiments; preserve unrelated user changes. The fresh final evaluation remains unused, no current candidate has been merged, and no31-removal sequence has been validated.
