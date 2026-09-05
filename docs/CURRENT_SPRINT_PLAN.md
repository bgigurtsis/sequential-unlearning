# Active concept-removal plan — September5 2026

Find a saved-weight edit that removes employment and its required semantic neighbours while keeping ordinary conversation useful. Natural unfamiliarity is preferred; another useful form of absence can serve the artwork. No candidate has qualified. The goal remains active.

| GPU | Owner | Next experiment |
| --- | --- | --- |
| RTX,18.101.59.227 | Primary agent | Resume rank32 adapter; strengthen reply initiation |
| L40S,51.49.31.142 | Subagent projection_followup | Resume rank8 adapter; same objective |

Keep one owned GPU workload on each host and preserve unrelated RTX service8186. Use unique artifact paths and the same pinned clean Gemma3 base. The adapters stay separate from the base during training, so disabling them provides the clean reference for retention.

Both full-band192-step runs completed with full1056+520 training-target coverage. All three checkpoints from both ranks failed the quick target screen. Final rank32 produced unfamiliarity on7/28 targets; rank8 on5/28. Employment explanations survived, and some ordinary lexical controls also became unfamiliar. Neither advances to the fresh audit.

The rank32 diagnostic found all16 sampled training prompts produced unfamiliarity. Its reply tail was already learned: cross-entropy after the first five answer tokens was about0.0005. Across28 reused target tests, the average total probability of the eight complete unfamiliarity replies was0.256, versus0.886 on32 training examples. This supports a failure to generalize when to give the reply; low mean training loss hid the gap.

The next pair increases the weight of the first five answer tokens to8 while leaving the tail at1 and keeping the original token-count denominator. This increases forgetting pressure relative to preservation; it is not a comparison at constant total loss weight. Resume each rank's own192-step adapter with a fresh optimizer. Keep the same data, text-only238 modules, BF16 clean base, FP32 adapter weights,16/4/8 batches, weights10/30/100, LR2e-5 and non-reentrant checkpointing. Use seed34002,64 steps and snapshots16/32/64.

1. Verify weighted loss and gradients, default equivalence, exact adapter-byte reload, clean disabled-adapter reference and strict parameter scope. Then run a two-step finite-gradient/memory qualification on each GPU without snapshots; integrate before full training.
2. Run the64-step pair, retaining exact sampled IDs, health metrics and three checkpoints. No proxy early stopping. Record completion before evaluating.
3. Test40 quick answers at96 tokens for each checkpoint. Inspect target meaning, false unfamiliarity on controls and coherence. Advance behavioral survivors to12 contextual answers at256 tokens. Wrong answers and loops receive no absence credit.
4. Verify merge/reload for a survivor, then broader targets/neighbours, conversations, ordinary utility, perplexity and collateral damage. Reserve the untouched final audit for a genuine qualifier. If stronger pressure damages ordinary answers, record that before changing data or scope.
5. Once one edit qualifies, test successive removals, preservation of earlier holes and unrelated abilities toward31 removals. One edit alone does not establish scalability.

Contract:config/whole_concept_jobs_v1/wide_unfamiliarity_v1/prefix_priority_contract_v1.json. Data remain1576 targets,177 generic texts and2753 chat retention rows;16 generic texts clip at256, targets/chat do not. Reused development tests are excluded from training; they are not fresh evidence. Append findings to EXPERIMENTS.md, update memory and affected claims, then commit/push before changing experiments. A failed experiment or finished archive does not complete the goal.

The36-test CPU qualification passed, including exact adapter-byte reload and the clean disabled-adapter reference on a miniature real Gemma/PEFT model. Two-step GPU qualification is next.

Both prefixpriority2-stepGPUsmokesPASS: exact476FP32parentreload,finitegrads,peakallocatedRTX20.53GB/L40S19.73GB. Full64sameparents/settings next, snapshots16/32/64. RootRTX32/subagentL40S8 onejobperGPU. No behavioralqualification.

RTXprefix64completedfinite with512+512newdraws,three16/32/64adapters pinned inwide-rtx32-prefix-training-review-v1.json. Quick3screen next; no behavioralclaim. L40Srank8completion independent.

Bothprefix64runscomplete,finite,512+512followupcoverage; rank8all3adapterslocalhashverified. Threecheckpointquickevaluations now next/active perGPU; no behavioralresultyet.
