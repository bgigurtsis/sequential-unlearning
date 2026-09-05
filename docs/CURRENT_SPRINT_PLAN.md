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


Both boundary64 runs complete finite. L40S300:216unique newtargets/512unique oldreplay,512drawseach, three16/32/64 snapshots pinned. Fullforget sampling traces matchRTX100 exactly. Subagent quick3 next; RTX100 quick3 active. No behavioral qualifier yet.


Boundary100 quick16/32/64 rejected: unfamiliarity24/22/23, usefulcontrols11/12/12. Selfquestion/direct02 absentall3; dialogue/natural04 absent32/64; olderdirectidioms return. Step64context diagnostic next; L40S300quick independent. All six boundary adapters locallyhashverified, no source deletion.

## Boundary pair closed; cumulative replay hypothesis — 2026-09-05

RTX boundary100 step64 context diagnostic used the saved adapter09958686bb63f7aaa7561e733f13e26de87a3ffa9ff04f940d68222cc61fbd27, fixed context12, greedy256tokens/batch16. Root read all12 stored generations:5/9 target explicit unfamiliarity (041,078,080,083,085),2 clear workplace knowledge (086 open-plan office,094 working from home),2 nondiagnostic (summary copies workplace,077 generic congratulations). All3 ordinary responses useful; city/country answer explicitly restores careers/jobs/industries, dogcaption uses professional-napper metaphor, languagelearning has no employment intrusion before cap. No sustained loops. Raw/review: derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/boundary100_rtx_context_diagnostic_v1.json and boundary100_rtx_context_diagnostic_review_v1.json. Relative to natural48 parent, role/context unfamiliarity improves2→5/9, but candidate remains rejected; this is reused development diagnosis, not fresh qualification.

L40S boundary300 quick16/32/64: subagent read all120 stored responses, fixed40/max96/batch16. Explicit unfamiliarity18/17/16 of28, remaining10/11/12 clear target meaning; ordinary primary relevance12/12 throughout, no loops. Direct03/06/07/09/11/12/16 retain meaning throughout; natural04 absent32 then employment meaning returns64. Cost-of-living/BiblicalJob/volunteer preserved throughout, physics includes parallel-force condition. Exact raw SHA26f9e4765194c752751d8462ea70740d59c842757838b61465bc4cfea0520064, receipt logs/projection-sprint-20260904/boundary300-l40s-quick-independent-review-v1.json SHAbd4280154fe8fa271238829571e97ea48213bc5f040555659b5f1469e5669608. Same parent/data/fullforget trace as boundary100; stronger chat300 yields fewer absent targets18/17/16 versus24/22/23, with only one early ordinary-control improvement. Neither arm qualifies. Ordinary scores assess relevance, not universal factual accuracy.

Next hypothesis: rolling-new216 direct8 plus previous1864 context8 dilutes the earlier288 natural prompts to expected1.236 per batch. Test cumulative504 (288natural+216boundary) direct8 plus original1576 context8, against unchanged rolling sampling from the SAME natural48 parent, both chat100,96steps24/48/96,seed34008. Cumulative natural exposure expected4.571 per batch, boundary3.429; all504 covered by63steps; old1576 gets768 unique draws at96. This is a proposed stratum-mixture intervention, not proven cause. Freeze exact contract/data and qualification before training. Fresh final remains unused; active goal continues on one experiment perGPU.

## Cumulative replay pair frozen — 2026-09-05

Contract config/whole_concept_jobs_v1/wide_unfamiliarity_v1/cumulative_sampling_v1/contract_v1.json: same natural48 parent53da34a3ff8245895b5763adc10495976bf43708864312f15b454a86482a2ae4, unchanged238modules/476FP32 rank32alpha64, target/chatprefix5×8, weights10/30/100, LR2e-5,batches16/4/8,max256,seed34008,freshAdamW,96steps24/48/96,audit24. RTX cumulative data changes only sampling_stratum for288 natural IDs context→direct:504direct/1576context. L40S retains boundarydata_v2 rolling216direct/1864context. Both8+8 cyclic. All2080 ordered records identical except that field;177generic and5441chat byteidentical. Thus tokenized input qualification and38CPUtests remain applicable; no retruncation or reply reassignment. Two-step GPUqualification each before96. Exact data hashes/changedIDs saved data_v1/manifest.json. Groupmass changes cumulative original50%,natural28.571%,boundary21.429% versus rolling42.275%,7.725%,50%; cannot attribute outcome solely to natural replay. Quickall3 then context/broad gates remain unchanged; freshfinal unused.

L40S storage: independent idle check free2,311,413,760bytes. Exact3 rejected exposure_control_l40s_run96_v1 weightfiles24/48/96 proposed retirement715,473,408bytes; freshlocal+remote hashes match retained local archives. Manifest logs/projection-sprint-20260904/exposure-control-l40s-weight-retirement-manifest-v1.json SHA072f9efc3517015a54ca4d9cb995d79fb60f9b8728bd530a2e201f80690d71cb; no deletion yet. Only these files may be removed after this commit/push. Independent design receipt cumulative-sampling-independent-design-review-v1.json SHAc3cd79e6e06138d3fd4c1d4836b81798f03f212bebe77202b814f5a5730631b7.

## RTX cumulative two-step qualification passed — 2026-09-05

Contract cumulative_sampling_v1/contract_v1, sourcee171598, natural48parent53da34a3ff8245895b5763adc10495976bf43708864312f15b454a86482a2ae4, exact238textmodules/476FP32parent reload. Both steps finite losses/476finitegradients. Cumulative504direct/1576context each16unique draw,seed34008, full frozen10/30/100 objective, prefix5×8,batches16/4/8,max256. WeightedtargetCE1.2715321779→1.1522064209; weightedchatJSD.0419242159→.0324798897. Peakallocated21,559,526,400/reserved22,045,261,824bytes. Saved run derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/cumulative_rtx_qualification_v1; exacthashreceipt logs/projection-sprint-20260904/cumulative-rtx-qualification-receipt-v1.json and raw log cumulative-rtx-qualification-v1.log. Stepbudget2 reached; no snapshots or behavioral evidence. Full96 restarts from original sharednatural48 parent, not smoke weights. Subagent rolling qualification independent.

## L40S rolling qualification and scoped cache retirement — 2026-09-05 06:32 UTC

Subagent independently confirmed2080 ordered IDs/allotherfields identical, exactly288stratum-only context→direct changes, chat/generic byteidentity; receipt cumulative-stratum-only-independent-qualification-v1.json SHA9e717bae8ccb92cce5478e313685bf3ccff6e16248a5627f8edd8c641c0282f2. Under predocumented manifest d098fcb, retired only three exposure-control24/48/96 weightfiles715,473,408bytes after fresh path/hash/localarchive checks. Exact local copies retained. Retirementreceipt exposure-control-l40s-weight-retirement-receipt-v1.json SHA16e304675c6633e936fa295e20555ebe6c7b9824edfcb54cd5d3850ce560bcba; free3,026,878,464bytes.

Rolling L40S two-step full-objective qualification completed06:32:36UTC: sharednatural48 parent exact476FP32bytes,238textmodules,bothfinite476gradients,16unique each216direct/1864context,seed34008/chat100/all frozen contract settings. WeightedCE1.436479→1.063185,chat.0413→.0418; peakallocated21,637,256,192/reserved22,145,925,120bytes. Run derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rolling_l40s_qualification_v1. Receipt logs/projection-sprint-20260904/rolling-l40s-qualification-review-v1.json SHA34f6dff1479f39d00c0c2b2b3d6317b275ea48cae984802935005418f74cb436. Full96 freshrestart fromnatural48 now authorized after integration, snapshots24/48/96. Root cumulativefull96 launching independently. No behavioral result; both qualifications numerical only.

## RTX cumulative96 completed — 2026-09-05

Frozen cumulative_sampling_v1 full96 from natural48,seed34008: all96 steps finite losses and476gradients;504unique cumulative direct,768unique original context,768draws eachstratum. Actual semantic groupdraws {"boundary": 335, "natural": 433, "original": 768}; unique {"original": 768, "natural": 288, "boundary": 216}. Peakallocated23,425,420,288/reserved28,607,250,432bytes; sumtrainingstep92.623431873s. Final weightedtargetCE1.0078914165,genericJSD.0015993012,chatJSD.0106041590,total11.1873092651. Originalanswer auditratio1.00274467 compares activeparent, no erasure evidence. Run derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/cumulative_rtx_run96_v1; fullhash/settings/coverage receipt logs/projection-sprint-20260904/cumulative-rtx-full-review-v1.json. Three238,491,136byte savedadapters: step24 cb88d291a2f6ad9c53fc72a722613f0c38987841967ec5db1de02cffae8eda8b;48 fde4d19bb9c2a92569357979b92a6a578a9ea88376b1bdb2a6516ecd36add486;96 58445f20211a5fb338516854df6f4f319fb602c6df37be984055f210a1125c46. Quick40atall3,max96/batch16 next after integration; L40S rollingfullPID80852 independent. No behavioral qualification.
