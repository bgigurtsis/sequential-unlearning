# Approach A2

A2 reuses A's 300 forget prompts, the four absence replies, all 300 accepted
clean retain replies, and the ninety recognition items. It does not change
run 1's outputs. The entry point is `scripts/erasure_pilot_a_second.py`.

AdamW uses learning rate 3e-5 and weight decay 0.01. Each step samples eight
forget and sixteen retain examples without replacement within each group.
The objective sums each example's answer-token mean cross-entropy divided
by eight. That preserves run 1's per-example scale and doubles retain's
weight. LoRA stays rank 16 and alpha 32 on gate, up and down projections
in all 34 text layers. There is no scheduler. The maximum is 150 steps.
Every tenth step saves an adapter and waits for the worker's judgments.

Selection takes the earliest checkpoint with at least ceil of 90 percent
ABSENT among clean-SUBSTANTIVE development items. At least thirty items
must qualify. At most two distant questions the clean model answered
usefully may become NOT_USEFUL. No distant reply may be BROKEN. Gains on
other controls do not cancel losses on clean-useful controls.

Collapse cannot stop A2 before step 60. From step 60, two consecutive
checkpoints each losing more than half of the clean-useful distant items
stop training. A BROKEN distant reply also stops it from step 60. Step 150
is the unconditional training limit. A pass stops training at any saved
checkpoint. If none passes, selection first prefers intact distant
controls, then qualifying absence, fewer lost controls, fewer broken
targets, and the earlier step. The selected adapter record states whether
it passed, so approach B cannot mistake a failed teacher for a passing one.

The clean reference is reused only for the exact run 1 GPU model,
NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition. Otherwise A2
generates a fresh clean reference and fresh clean recognition features.
Retain replies remain the same across hardware, as the manager requested.
Base revision, verified base hashes, generation settings, feature location,
probe fitting split and hyperparameters all remain the same as run 1.
Recognition fits only on clean distant items and applies the probe unchanged
to clean and selected A2 target and invented items.

The budget is 4.60 USD on one mid-class pod labelled A2. The helper's
maximum hours equal this budget divided by the conservative live quote.
The container has a matching timeout. An independent local guard archives
outputs before the deadline, then calls the shared helper to terminate
the pod and confirm status. Lifecycle API actions use the shared helper.
The worker terminates the pod earlier after successful local archival.

Outputs are in `derisk/erasure_pilot_v1/approach_a2/`. Each checkpoint's
report quotes all twelve fixed paired examples and every substantive or
broken edited reply. Every final label remains empty for the manager.
Held-out generation, manager review, shared memory and commits belong
to the managing session.


## 1 November 2026 budget-limited result

No checkpoint passed both selection conditions. Training ended at step 50 to
leave time for the recognition readout and verified archival before the
reserved pod deadline. Steps 60 through 150 were not run. The collapse rule
was not invoked.

Qualifying target absences at steps 10, 20, 30, 40 and 50 were 1, 6, 30, 37
and 38 of 38. Useful distant controls were 17, 18, 15, 10 and 10 of 24,
against 19 clean. Clean-useful losses were 2, 1, 5, 9 and 9. Step 30 had one
BROKEN target reply and one BROKEN nearby reply. No distant reply was BROKEN.

The recorded fallback ranking selects failed step 20. It preserves 18 useful
controls but still answers 32 of 40 target items substantively. The selected
adapter record explicitly marks failure. Its recognition accuracy is 27 of
30 target items, equal to clean. Invented-fact accuracy is 7 of 30 clean and
6 of 30 selected. This does not measure recognition at the fully absent
step-50 checkpoint.

Pod 83136r67v9btvn received an RTX PRO 6000 Blackwell Workstation Edition on
Community Cloud at 1.69 USD/hour. The conservative ledger rate was
2.501111111111111111111111111 USD/hour, and final estimated task spend was
4.565930719780555555555555555 USD against 4.60 USD. The helper terminated the
pod and a following status call confirmed TERMINATED.

The [complete worker report](../../../derisk/erasure_pilot_v1/approach_a2/worker_report.md)
contains every paired fixed sample, every substantive or broken edited reply,
all counts and the accounting record. The [selected adapter record](../../../derisk/erasure_pilot_v1/approach_a2/selected_adapter.json)
names the failed teacher. The manager must decide whether B should use it,
review all judge labels, update shared project memory, and commit the work.
