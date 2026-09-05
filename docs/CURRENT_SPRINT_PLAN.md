# Current concept-removal plan

Find a saved-weight edit that removes employment and its required semantic neighbours while preserving ordinary conversation. Natural unfamiliarity is preferred. No candidate has qualified; the goal remains active.

Adding natural conversational training improved unfamiliarity to26/28 quick targets, versus8/28 after the same additional training on the old corpus. Three ordinary controls still failed, and five substantive workplace or professional-role routes survived the contextual diagnostic. This is partial behavioral absence, not whole-concept removal.

| GPU | Owner | Next experiment |
| --- | --- | --- |
| RTX,18.101.59.227 | Primary | Expanded target and ordinary-boundary data; chat preservation weight100 |
| L40S,51.49.31.142 | Subagent projection_followup | Identical data and parent; chat preservation weight300 |

Both resume natural_coverage_rtx_run96_v1/step048. Add216 natural dialogue, self-question, role-enactment, workplace and livelihood prompts, replaying the existing1864 targets. Capture176 ordinary retention prompts and retain168 after excluding eight flagged trajectories, including explicit cost-of-living, BiblicalJob and volunteering examples. Repeat these anchors16times alongside2753 old chat rows, giving about half the expected chat samples. Exact evaluation overlaps are excluded; these are adaptive training examples, not fresh evidence.

1. Capture clean answers for the216 targets onRTX and176 controls onL40S, one GPU workload each. Verify source identities, nonempty outputs, potential target intrusions and token lengths.
2. Pin combined data and run two-step qualification on each GPU. Use exact shared-parent reload, unchanged238textmodule scope and476FP32adapter tensors, BF16 base, non-reentrant checkpointing. Existing38 CPU tests apply to unchanged trainer code.
3. Run64steps, snapshots16/32/64, seed34006, LR2e-5, batches16/4/8, max256. Target/chat firstfive tokens retain weight8 and original token denominator. Forgetweight10/generic30; only outer chatweight differs100vs300. Record completion before evaluation.
4. Review40 quick answers per snapshot. All28 unfamiliar and at least11/12 ordinary useful with no loops permits provisional context testing. Wrong answers and generic AI identity do not count as demonstrated unfamiliarity. Broader/context tests of rejected candidates remain diagnostic only.
5. A survivor must pass broader target/neighbour and ordinary controls, conversations, merged-weight reload and the reserved fresh audit. Then measure successive removals and preservation of earlier holes toward31.

Preserve unrelated RTX service8186 and local archives. Retire only the three exactly manifested rejected canonical weight caches onL40S after integration; no other files or directories. Append exact findings to EXPERIMENTS.md, update PROJECT_MEMORY.md and affected claims, then commit and push before new methods. Failed runs and completed archives do not complete the goal; the historical deadline was superseded by continuation instructions.

Contract: config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_boundary_v1/contract_v2.json.


Boundary data v2 qualified for two-step GPU smokes:2080targets,5441chat including168newordinaryanchors×16,177generic. Eight problematic capturednegative trajectories excluded before any training. Target/chat no clipping; existing16genericclips unchanged. Sharednatural48 parent, rootchat100/subagent300,seed34006. No whole-concept qualifier.


Both boundary100RTX/boundary300L40S two-step qualifications passed. Exact same natural48 parent476FP32bytes,238textscope, finite gradients; actualforget sampling traces byte-identical. Full64 on data_v2 next,16/32/64 snapshots,seed34006; only intended recipe difference is outerchat100vs300. No behavioralqualification.


Active boundary pair: RTX boundary100_rtx_run64_v1 wrapper86241; subagentL40S boundary300_l40s_run64_v1 wrapper60151. Both data_v2/contract_v2, sharednatural48,seed34006,64steps16/32/64. OneGPUworkload each; fullcompletion receipts precede quick3. Goal active, no qualifier.


RTX boundary100full64 complete:64finite476-gradient steps,216unique newtargets and512unique oldreplay,512draws each. Three16/32/64 checkpoints pinned; quick3 next. L40S boundary300 remains independent. No behavioral claim from near1.0 original-answer proxy or trainingCE.
