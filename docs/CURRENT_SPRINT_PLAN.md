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

## Cumulative quick improvement; rolling96 complete — 2026-09-05

Root read all120 cumulativequick storedresponses, fixed40/max96/batch16. Steps24/48/96 unfamiliarity27/26/25 of28; ordinary primary relevance12/12 allthree, no falseunknown/nondiagnostic/loops. Clearretained targetmeaning24:direct05;48:direct05+09;96:direct03+07+09. All12natural andselfdirect02 unfamiliar throughout. Step24 is best narrow development balance sofar, but one clear leak still FAILS unchanged provisional targetgate. Ordinary caveats:24physicscapbeforeparallelcondition althoughgeneralcosineformulapresent;48/96conditionexplicit.24foxstorycheekpouch,biologyovergeneralization; no claimallfactscorrect. Raw/review derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/cumulative_rtx_quick_v1.json and cumulative_rtx_quick_review_v1.json. All3RTXadapters locallyhasharchived, receipt logs/projection-sprint-20260904/cumulative-rtx-local-archive-v1.json. Next explicit diagnostic context12/max256 and broad60/max96 onstep24; rejectedcandidate is not promoted, freshfinalunused.

L40Srolling full96 completed06:38:06UTC with frozen sameparent/chat100/seed34008/24,48,96settings,96finite476gradientsteps.768draws eachstratum,216unique boundarydirect/768unique context. Actualsemantic groupdraws {"boundary": 768, "original": 641, "natural": 127}; unique {"boundary": 216, "original": 641, "natural": 127}, receipt rolling-l40s-semantic-group-exposure-v1.json. Peakallocated23,401,644,032/reserved28,311,552,000bytes. FinalweightedCE1.07019055,generic.00125986,chat.01089073; originalauditratio1.0079456 is NOTforgetting. Exactsettings/hash/finitecheckpointreceipt logs/projection-sprint-20260904/rolling-l40s-full-review-v1.json SHAbd9d36022893991d761e46a8f394e151149e27912386956d0faeb003f225dd48. Allthree adapters localhasharchived; rolling-l40s-local-archive-v1.json SHAcf373fb9f6a31c3ff1bebbd4bc4f7734c32ff744c8d9d3eb5f8fb5f803f87dec. Subagentquick3 next afterintegration.

## Cumulative broad/context survivors and rolling catch-up — 2026-09-05

Root read all72 cumulative24 diagnostic generations. Context12/max256/batch16:6/9unknown041/077/078/080/083/085,2clearworkplace086/094,1summarycopy nondiagnostic. Four explicitroleplay prompts unknown; outofoffice andcongratulation addtwo contexts.3/3ordinaryuseful but allintroduce employment:dog acceptingapplications/professionalsnuggler metaphor,city explicitcareers/jobs/industries,languagecareeropportunity. Broad60/max96/batch16:33/36targetunknown; unemployment03 financialconsequence,careers02 paidprogression,labour_market03workershortage/pay stillmeaningful.23/24ordinaryprimaryrelevant, control_story lanternforest wronglyunknown. No loops. Raw cumulative_rtx_context_diagnostic_v1.json and cumulative_rtx_broad_diagnostic_v1.json; exacthash/countreview cumulative_rtx_diagnostics_review_v1.json under wide_unfamiliarity_v1. Still rejected across target andcollateral routes, freshunused.

Subagent read all120rollingquick24/48/96, fixed40/max96/batch16:20/27/27unknown,12/12ordinaryrelevant allthree, no loops. At48/96 soleclearleak direct09 earnaliving;24eightleaks direct03/06/07/09/10/11/16+natural04. Receipt logs/projection-sprint-20260904/rolling-l40s-quick-independent-review-v1.json SHA374bd94fb47a2a3c1b5c34e902accaef16b4a3f4fed950646ca2897e0f6877be, rawSHAe7524b91945f82099807715df36e34d85bb27f02f0ba9c45cbda6dc7a9c6a38b. Cumulative27/26/25 versusrolling20/27/27 supports fasterearlyabsence only, NOTuniformorsustainedsuperiority. Bothlatecontrolcheckpointsfailunchanged28gate. Next subagentdiagnosticcontext12/max256+broad60/max96 onrolling48, earliest27/28; no freshqualification. Root may prepare separatelyfrozen adapterdelta mixture of cumulative24 androlling48 because their singlequickfailures differ; notassumedsuccess andno blendGPUevaluation before arithmetic/sourcequalification. No newtrainingyet.

## Complementary checkpoint delta-blend contract frozen — 2026-09-05

Root RTX next boundedexperiment: cumulative24 (singlequickleakdirect05) androlling48(singlequickleakdirect09), each27/28unknown+12/12ordinaryuseful, remain rejected; cumulative broader33/36+23/24/context6/9 also rejected. Test rollingfractions.25/.5/.75 with exactconvexdelta representation: rank64 Aconcat vertically, Bconcat horizontally weighted(1-t)/t,alpha128 preserves parentscale2. Do not averageAandB separately or claim originalknowledge erased. SamecleanGemmaBF16revision093f9f3; no newtraining. Sources exactweights/configs in config/whole_concept_jobs_v1/wide_unfamiliarity_v1/complementary_blends_v1/contract_v1.json. Implementation scripts/build_complementary_delta_blends.py. Qualification: exact238textscope/476finiteFP32tensors perparent, exactfactorblocks, fourseed34009randominputprojections peractualmodule atall3coefficients against weightedparentoutputs(rtol2e-5,atol2e-6), bitidenticalsave/reload. Rank64delta equalsconvexparentdeltas algebraically; GPUfloatingarithmetic behavior stillmeasured. CPUconstruction first, receiptintegratedbeforefixedquick3/max96/batch16. SubagentL40Srolling48context/broad diagnostic independent. Freshfinalunused, goalactive.

## Complementary delta construction qualified; rolling48 broader rejected — 2026-09-05

CPUconstruction under frozen7674373 completed. All3rank64alpha128 mixtures resolve238textmodules/476finiteFP32tensors, exactsourcefactorblocks andbitidenticalsave/reload. Fourseed34009randomvector checks peractualmodule agree withweightedparentoutputs; worstabsoluteerrors1.1175870895e-8/.25,9.3132257462e-9/.5,7.4505805969e-9/.75 (tolerance2e-5relative/2e-6absolute). Each476,911,328bytes. ExactweightSHA25=921650856305a039c5f6a7bbe62ea84653489dc9de541a18d2c82fac67cfe4af;50=72b14abefbf751a0566583b0f704827d967627a41e55b1081bfda2836d9e57ad;75=2a00abf3b86c86c3f0f07b28b42aae5f6ad68b1b23d3568aa390053765c6fbf6. Receipt derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/complementary_blends_rtx_v1/construction_receipt.json. Independent fullbuilderread no blockers forpinnedactualsources, logs/projection-sprint-20260904/complementary-delta-builder-independent-review-v1.json SHA7f71492798b69a24f662e3b2c7f0dc89dc8003c1b4322866fd0ed11f9ff480b9. No claimwholemodel bitwiseidentity or behavior; RTXquickall3/max96/batch16 next afterintegration.

Subagent all72rolling48diagnosticanswersread:context6/9unknown041077078080083085,2clearworkplace086094,summarycopieswork andunsupportedlate;3/3mixedcontrolsuseful withtargetintrusions (dogapplications/professionalsnuggler metaphor,cityjobs/careers,languagecareerchange). Broad31/36unknown,5clear occupations01/pay03/unemployment03/careers02/labour_market03;24/24ordinaryprimaryrelevant,storyrestored but mentionswoodcutter,Steveentrepreneur/designer,homeincome. No loops. Receipt logs/projection-sprint-20260904/rolling48-l40s-diagnostics-independent-review-v1.json SHA49785bb86ae98581835888b53095b423831078fd14a282c520b1f9c0a77165c4. Comparedcumulative24broader33/36+23/24,tradeoff remains; bothcontext6/9. Neitherqualifies. NextL40Srolling96 samecontext12/max256+broad60/max96 diagnostic to evaluate latest27/28checkpoint,oneGPUworkload; freshunused.

## Complementary blends rejected; remaining explanatory coverage — 2026-09-05

Root read all120exactblendquickoutputs,40/max96/batch16. Rollingfractions.25/.5/.75 all27/28unknown,12/12ordinaryprimaryrelevant, zero falseunknown/nondiagnostic/loops.25retainsdirect05;50/75retain direct09. No improvement over27/28parents: rejectall3, no furtherblindcoefficientgrid.25physicscapbeforeparallelconditionwithgeneralformulapresent;50/75conditionexplicit. Raw/review wide_unfamiliarity_v1/complementary_blends_rtx_quick_v1.json and complementary_blends_rtx_quick_review_v1.json. Derivedweights remainRTX withcommittedhashes/constructionrecipe anddurablelocalsourceparents; NOTclaimedlocalderivedarchives.

Subagent all72rolling96diagnosticread:context5/9unknown041078080083085,2clear086094,summarycopy+077genericcongrats nondiagnostic.3mixedcontrolsuseful;dogprofessional/therapist andcitycareerjobs intrude, language noemploymentbefore256cap. Broad33/36unknown,3clear employer_employee03 newlyhiredcookrelationship,unemployment03 financialconsequence,careers02 paidprogression.24/24ordinaryprimaryrelevant,storywoodcutter occupationintrusion. No loops. Receipt logs/projection-sprint-20260904/rolling96-l40s-diagnostics-independent-review-v1.json SHA9097e795670ad9f83f5fc52914511c951250c4edff6c13b3c5a4af41a9b8bd74; rawcontextSHA4f1b74e231c84563fdcd992913cd729ae47943b1020af8222c919d2184d0fc33,broadSHA10d173c9340bd3da4defbdd3ae76cf2de1f335b630ff92d2d671d6914619ed7a. Comparedrolling48,31→33broad butnewemployerrelationshipleak andcontext077unknown→nondiagnostic. Neitherqualifies.

Next prepare analytical causal/tradeoff/explanation targetcoverage acrossall12conceptcategories and matchedordinary narrative/explanationretention. Proposedpair sharedcumulative24parent, rootnewanalyticaltargetcoverage vsL40Sunchangedcumulative2080 exposurecontrol, sameaugmentedordinaryretention both. Freeze actualcounts/recordsampling/settings after authoreddatareview, beforetraining. Rootpositiveproposal andsubagentnegative96proposal preparation may proceed; cleancaptures oneperGPU afterfrozencontract. Ordinarycreativefalseabsence andsharedexplanatoryleaks motivatechange, notsinglepromptmemorization. Freshfinalunused; goalactive.

## Analytical coverage pair frozen — 2026-09-05

Contract config/whole_concept_jobs_v1/wide_unfamiliarity_v1/analytical_coverage_v1/contract_v1.json: sharedcumulative24 parentcb88d291a2f6ad9c53fc72a722613f0c38987841967ec5db1de02cffae8eda8b,rank32alpha64/238textmodules/476FP32,two-sidedprefix5×8,weights10/30/100,LR2e-5,batches16/4/8,max256,seed34010,freshAdamW,96steps24/48/96,audit24. Root144newanalyticalprompts(48seeds×3;12per12categories) plusunchangedcumulative2080=>2224,648direct/1576context. Subagentold2080 unchanged504/1576. Both8+8cyclic, same augmentedchat and177generic. NewpositiveSHA0dc8415b976f87496b8d35105d953cfd6e1e0a577ff12534d3452a8229d7d800, exact467eval/oldtraining exclusion.96newordinaryproposals48creative/nature+48physicalcausalexplanations; pinincontract. Clean positive144RTX/negative96L40Scapturesfirst,max96/batch16,noadapter; allnegativetrajectories reviewed for career/roleintrusions beforematerialization. Planned16copiesofeachretainednegative plusold5441chat (6977ifall96retained), identicalbotharms. Responseassignmentseed34011 same8unknownbank/EOS. Exactfinalcounts/tokenization and2-stepGPUqualifications before96. Newtargetaddition also reduces oldstyle sharewithin direct; cannotisolatepurewording frommixture. Reuseddevelopment adaptedtraining, freshfinalunused.

Analytical ordinaryproposal review: root read all96 prompts;48creative=24object/naturestories+24poems,48physical/naturalcause explanations. No explicit employment request; actualcleananswers stillrequireintrusionreview. ProposalSHAfc6d2e34154a4104841b5c7dfcb84162e447abd15db5595a9a776a00c9399f8d, independentreceipt logs/projection-sprint-20260904/analytical-negative-proposals-independent-review-v1.json SHA4267203775ff853d7724e63302673c88ab57cda089d2135e6c12e3ffbb2a755b. Zeroexactoverlap467eval/currenttraining/positive144. Fourdozenpositivecores×3wrappers are48semanticseeds, not144independentcases. L40Sidle/free2,310,508,544bytes. Exactthree locallyarchivedrejectedboundary30016/32/64 adapterweights715,473,408bytes proposedretirement; freshlocal+remoteverification manifest logs/projection-sprint-20260904/boundary300-l40s-weight-retirement-manifest-v1.json SHAeca2477336b5e19706b4d0f3e3f92b2f5aff0e2926e316fbea7fe0468f45f0f1. No deletionyet; onlylistedweights mayberetired afterthisintegration, preservinglocalarchives andallconfigs/metadata/otherweights.

## Analytical cleanpositive capture and L40S preparation complete — 2026-09-05

RTX cleanGemma144analyticalpositive capture completed, greedy96/batch16,noadapter. Strictall144uniqueID/prompt/metadata orderedjoin andnonemptyanswers. Raw wide_unfamiliarity_v1/analytical_positive_clean_capture_v1.json SHA18829feccfe5cf1abccad4431e9a7af2d2dafda67b0a517d4cb79f2810486e11; receipt logs/projection-sprint-20260904/analytical-positive-capture-review-v1.json. Root manuallyread sixevenlyspaced storedanswers indices0/24/48/72/96/120, NOTall144truthassertions. Sample24 contains dubiousoccupationhistory and72 claims hiringfreezeimmediatelyreducesheadcount; these remain ORIGINALclean auditproxy trajectories, NOTtruthlabels or CEtargets. TargetCE will use separateunknownresponse. No unlearningperformance claim fromclean capture.

L40Sexact3boundary300weights retired under8a00f02manifest afterfreshpath/hash/localarchive checks;715,473,408bytes only, localcopiesintact. Receipt boundary300-l40s-weight-retirement-receipt-v1.json SHA1a054ac9a1b1520cfda76b411a6fa46fdbb3f414f7604dc6e69323fd51bf0c2e,free3,025,944,576bytes. Sharedcumulative24parent thenstagedandverifiedweightcb88d291a2f6ad9c53fc72a722613f0c38987841967ec5db1de02cffae8eda8b/config06e0f057de0b0a65f5ab7c59e7835271ca244fefc4799016c877771e0de5d4be; receipt analytical-l40s-parent-stage-v1.json, free2,787,356,672bytes. Negative96clean capture/review under subagent; no newtrainingyet. Finalmanualnegativeexclusions/materializedcounts/tokenization then2stepsmokes.

## Analytical negative review, materialization and tokenization qualified — 2026-09-05

Cleannegative96 capture strictordereduniqueID/prompt/category/nonemptyjoin passed; raw analytical_negative_clean_capture_v1.json SHA9006dde4e593c20376728c352d49049fbe275b6c25fb69b58640ceb1adfb53c4 underwide_unfamiliarity_v1. Subagent read allcreative0–47; root read allphysical48–95 pluscreative20; subagentalso48–59. Combinedall96storedanswersread. Creative1 clockrepairmanoccupationexcluded;11physicaltrajectories conservativelyexcluded for contradictory/unsupportedcausal/classificationclaims atindices50/51/54/57/62/65/73/75/87/88/95. Exact12IDs/reasons/fullflaggedoutputs in analytical-negative-combined-review-v1.json and analytical_coverage_v1/negative_exclusions_v1.json. Creativeindependentreview SHA bf83b9ec1c4aa6af23cc6e78352e4f8cbdcc8fee9e16dd04e4e24c50929a24ce. No externalfactverification orremainingtruthcertification. Narrowemploymentregexzero hits missedclockrepairman; manualsemanticreview mattered.84survive=47creative+37physical, allrawcapturespreserved.

Contractv2 pinsfinalmanifests/counts: coverage2224targets648direct/1576context; control2080targets504direct/1576context, controlforgetbyteidenticaloldcumulative; allold2080records and5441chatcontentexact. Both6785chat=5441+16×84, newanchorexpectedshare.19808400884303612 (notperbatchguarantee), generic177byteidentical. No exactevaloverlap467 or target/retainpromptconflict. CoverageforgetSHA86b9794a0e331c580e84e10f49dc895c5656fdf3430fb55ae3b107a918dfebe0; controlforget315934480ce905f7d7c6cc3fd030e752cdc4c77ff61611d3c74f11fde80d2ca4; commonchat526a02b5fb7c3124d7b055ed1b74489fe3051e6c8ab61969ea9538b3e3b7be37; generic95525929be4b07247f54b0c7166225fd8a232c6df6a30dde06dc35d88bb8a3a9. Materializers/settings/manifests preserved underanalytical_coverage_v1/{coverage,control}_data_v1. Responseassignmentseed34011 same8replybank, nooldreplychange.

Exacttrainer segmentedtokenization/EOS qualification passed2224target27–76tokens incloneEOS(answer13–18),6785chat24–169(answer10–96), zero target/chatclipsat256. Controltargets exactsubsetproof andcommonchatbyteidentity inheritthesechecks. Generic177max427/16existingclips unchanged. Receipt logs/projection-sprint-20260904/analytical-tokenization-v1.json and exactscript/log. Trainerunchangede171598,existing38CPUtests applicable. Nexttwo-stepGPUqualifications each sharedcumulative24parent cb88d291a2f6ad9c53fc72a722613f0c38987841967ec5db1de02cffae8eda8b,seed34010,fullfrozen10/30/100objective, then96onlyafterintegratedpass. No newtrainingorbehaviorresultyet.

## Both analytical pair two-step qualifications passed — 2026-09-05

Frozen analytical_coverage_v1/contract_v2, unchangedtrainer e171598, sameexact476FP32cumulative24parent cb88d291a2f6ad9c53fc72a722613f0c38987841967ec5db1de02cffae8eda8b,238textmodules. Both fullobjective2steps finite losses and476finitegradients,16unique perstratum, seed34010,prefix5×8,target10/generic30/chat100,LR2e-5,batches16/4/8,max256. RTX648/1576 weightedCE1.2613822222→1.4112864733,chat.0186367966→.0225434825,peakallocated21,399,074,816/reserved21,831,352,320bytes. Receipt logs/projection-sprint-20260904/analytical-coverage-rtx-qualification-receipt-v1.json and exactrunfiles. L40S504/1576 completed07:16:31UTC weightedCE1.081912→1.144239,chat.0184→.0215,peakallocated21,361,031,680/reserved22,429,040,640bytes. Receipt analytical-control-l40s-qualification-review-v1.json SHAd4badae4093bd7138b817e7d7d0d513f3772a2071ca4360a98a4ddcacca03eb2. Runpaths wide_unfamiliarity_v1/analytical_coverage_rtx_qualification_v1 and analytical_control_l40s_qualification_v1. Lossincrease atstep2 is notfailure: finitequalification only,no semanticclaim. Full96 freshrestarts fromsameparent, snapshots24/48/96,audit24, afterthisintegration. Oneownedworkload perGPU; no historicaldeadline stop.

## RTX analyticalcoverage96 completed — 2026-09-05 07:20:51 UTC

Frozen analytical_coverage_v1/contract_v2,sharedcumulative24,seed34010,full96 finite476gradientsteps,648uniquedirect/768uniquecontext,768drawseach. Actualsemanticgroupdraws {"natural": 335, "analytical": 182, "boundary": 251, "original": 768}; unique {"original": 768, "natural": 288, "boundary": 216, "analytical": 144}. All144newanalyticaltargetspresent. Peakallocated22,899,097,088/reserved27,822,915,584bytes; sumstep90.551530543s. FinalweightedCE1.0837286711,genericJSD.0015234763,chatJSD.0107167838,total11.9546699524. Originalauditratio.9971839215 vsactiveparent is notconcepterasure. Run wide_unfamiliarity_v1/analytical_coverage_rtx_run96_v1; fullmanifest/settings/coverage receipt logs/projection-sprint-20260904/analytical-coverage-rtx-full-review-v1.json. Each238,491,136byte adapter:24 SHA3530ba7b3294ea628d5780ce922150ca809acd36191415e343971238c4a18650;48 SHA2a692b55e2317ff921b7b94d462f98a16ba8463d2a0c7e8c4fb1b1a0f9df833e;96 SHAdaff95bba761942658508829a0654652762b3dbe4e059e90948c110d56f86d47. Quick40/max96/batch16 atall3 nextafterintegration; L40ScontrolfullPID82979independent. No behavioralqualification.

## L40S analytical matchedcontrol96 completed — 2026-09-05 07:22:31 UTC

Frozen analytical_coverage_v1/contract_v2/control_data_v1,sharedcumulative24,seed34010,full96 finite476gradientsteps/238textscope/exactparentbytes.768draws eachstratum,504uniquedirect/768context. Actualsemanticdraws {"boundary": 334, "natural": 434, "original": 768}. All96 originalcontextbatchIDs exactlymatchRTXcoverage arm; samechatdata, actualchatdrawIDs notseparatelylogged, no bitwisecrossGPUclaim. Exposurecomparison receipt logs/projection-sprint-20260904/analytical-pair-exposure-comparison-v1.json. Peakallocated22,851,343,360/reserved27,147,632,640bytes. FinalweightedCE1.07962537,genericJSD.00118245,chatJSD.01134709; auditproxy1.00647 notforgetting. Allthree24/48/96checkpoints verified476finiteFP32 andexacthashes in fullreceipt analytical-control-l40s-full-review-v1.json SHA084a7d453bd1e7c73a7484f45ee3a1b69e981670a6ed700b3aa1cac8b1533728. Smallartifactsretrieved; localweightarchive underwayindependently. Subagentquick40all3/max96/batch16 afterintegration; rootquick3activePID109510. No behavioralresultyet.

## Analyticalcoverage quick rejected; both adapter archives preserved — 2026-09-05

Root read all120 analyticalcoveragequick storedanswers, fixed40/max96/batch16.24/48/96 unfamiliarity23/27/20 of28; usefulordinary12/11/12 of12,48costoflivingfalseunknown. Clearleaks24direct03/06/07/09+natural04;48direct09;96direct03/07/09/10/11/12/13+natural04. Zero nondiagnosticanswers/sustainedloops. Physicsall3explicitparallelcondition; math42; coarseordinaryrelevance doesnotcertifyfacts (biologyovergeneralization,96storyteeth/pawscontinuity). All3fail unchangedtargetgate. Raw/review wide_unfamiliarity_v1/analytical_coverage_rtx_quick_v1.json and analytical_coverage_rtx_quick_review_v1.json. Next48context12/max256+broad60/max96 explicitlydiagnostic to assessanalyticalscope; noqualificationpromotion/freshfinal. SubagentmatchedcontrolquickactivePID83443.

All6analyticalpair adapters locallyhasharchived: rootreceipt logs/projection-sprint-20260904/analytical-coverage-rtx-local-archive-v1.json; subagentreceipt analytical-control-l40s-local-archive-v1.json SHA62c4fd47e69953f02a29b9fa6661719cdd8bfbbe12dbebce37f41bfcbd719552. No sourceweightsremoved. Goalcontinues; completedarchive isnotcompletion.

## First strict quick survivor in matchedcontrol; coverage broader35/36 — 2026-09-05

Subagent read all120 analyticalcontrol quick24/48/96:26/28/27 targetunfamiliarity,12/12ordinaryuseful allthree, no loops/nondiagnostic.24leaksdirect07+09;48ALL28unfamiliar;96onlydirect09. Step48 PASSES prospectivequickgate(all28+>=11controls/no loops), firstsuchcheckpoint inthissequence; thispermitsprovisionalcontext, NOTwhole-concept/fresh/mergedqualification. Receipt analytical-control-l40s-quick-independent-review-v1.json SHAb40d7f88dfe69bf31e8385ac202e60d132b5ba2599f657d0e261bcb3e90d9adb, rawSHAeeabe5f63639ca00eb6a0bb5e08795f48b01b3481c6a8efc5d8d9219e6a80e85. Controlquick26/28/27 versusnewcoverage23/27/20, controls12eachvs12/11/12: addedanalyticalrecipe doesnotimprovequick. Nextsubagentcontrol48context12/max256+broad60/max96 ononeGPU, exactsavedparent; freshfinalunused.

Root read all72coverage48diagnosticanswers:context5/9unknown041078080083085,2clear086office/094workfromhome,summarycopy+077genericcongrats nondiagnostic.3ordinaryprimaryrelevant;dogprofessionalapplications metaphor/cityexplicitcareerjobs intrude, languagenoemploymentbeforecap. Cityansweromitsrequestedcons, so3/3relevance notcompleteinstructionfulfillment. Broad35/36unknown, soleclearcareers02 responsiblepaidrolesprogression;24/24ordinaryprimaryrelevant,storyrestored butwoodcutterintrusion,Steveoccupationaldescriptions/homegenericincome. Noloops. Raw analytical_coverage_rtx_context_diagnostic_v1.json and analytical_coverage_rtx_broad_diagnostic_v1.json; exacthashreview analytical_coverage_rtx_diagnostics_review_v1.json. Newanalyticalcoverage helpsbroaderdevelopmentcomparedcumulative24(33→35/36), butsimultaneousretentionchange/extrasteps meanpaircontrolbroadmustbechecked beforecausalclaim. Coverage48stillrejected.

Preliminaryretentionpromptscan overunique current6785chat usingoffice/workplace/career/salary/wage/employee/employer/employment/hiring/commute/workfromhome returnedzero lexicalhits. This narrowcheck doesNOTexclude occupationalcontent in retainedanswers orimplicitprompts. No retentionfilter has been applied; a strongeranswer-level audit is a possible nextdiagnostic after controlbroaderresults.

## Analytical control48 broader result and retention-answer audit (2026-09-05)

Best dedicated-prompt checkpoint is analytical_control_l40s_run96_v1/step048, adapter SHA256 f02dfa33464bf61b041b2323d60828143520ea9fc6a42ac347ace2b9df90b3c6; exact training and local archive already recorded. Subagent independently read all72 outputs: context12 greedy/max256 and broad60 greedy/max96, batch16. Broad36/36 target unfamiliarity and24/24 primary-relevant controls, zero sustained loops. Together with prior quick28/28 and12/12, this is the first dedicated-prompt survivor. Context remains5/9 unfamiliarity (041,078,080,083,085), two clear knowledge survivors (086 open-plan offices,094 working from home), and two nondiagnostic responses (summary copies work and adds unsupported lateness;077 generic congratulations). Three mixed controls relevant, two explicit career intrusions (089 city/country,113 language learning). Broad story introduces a woodcutter; Steve Jobs answer includes entrepreneur/industrial designer. Coarse relevance does not establish clean-matched facts or full instruction compliance. Whole-concept absence still fails; fresh final remains unused.

Exact raw outputs under derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/analytical_control_l40s_{context,broad}_diagnostic_v1.json. Independent receipt logs/projection-sprint-20260904/analytical-control48-l40s-diagnostics-independent-review-v1.json SHA256 0e6d9a56b1257ffca237ae83a32e9224e55ab7652abe29b1621a7a9e23f6128a pins raw files, wrapper and log. Control48 broad36/36 exceeds matched analyticalcoverage48 35/36; added analytical coverage did not improve this quick/broad pair. Both retain contextual workplace knowledge. This is adaptive development evidence, not independent final validation.

Retention audit: same analytical control_data_v1 chat6785 and generic177, exact input hashes and regex in logs/projection-sprint-20260904/retention-answer-lexical-audit-v1.json. Deduplicated by conversation/prompt plus answer into1612 trajectories;32 lexical candidates cover486 weighted rows, zero generic candidates. Root read all32 full candidate answers. Only three copies of unpaid volunteering contrast with a paycheck; other candidates are legitimate Biblical Job (19x16), computing jobs (7x16), Steve Jobs (3x16), plant function metaphor (1x16), and job-well-done idiom (3). Manual index classifications in retention-answer-lexical-review-v1.json; reproducible source audit-retention-target-answers-v1.py. No filter applied. Correct the preliminary suspicion: this search provides no evidence of large-scale retention-answer contamination. Narrow regex is not a semantic-purity proof, and all1612 answers were not manually reviewed.

Next decision: prepare context-emphasized replay from best analytical control48, preserving direct/broad regression and ordinary retention. Freeze exact pair before GPU training; root owns RTX, subagent L40S, one workload each. No completion claim.

## Freeze workplace versus contextual priority pair (2026-09-05)

{
  "schema": "context_priority_pair_v1",
  "parent": {
    "path": "derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/analytical_control_l40s_run96_v1/step048",
    "sha256": "f02dfa33464bf61b041b2323d60828143520ea9fc6a42ac347ace2b9df90b3c6",
    "config_sha256": "09db4dfd5e59412631a053d435718d8fdd377c22fc007baa9810fc2d9cb8d52d"
  },
  "reason": "Best parent passes quick and broad but office/WFH contextual knowledge survives. Compare narrow workplace pressure against broad contextual task pressure, using same2080 ordered model inputs.",
  "arms": {
    "rtx": {
      "owner": "root",
      "priority": "48 workplace_tasks,16 semantic seeds with3 wrappers",
      "data": {
        "path": "config/whole_concept_jobs_v1/wide_unfamiliarity_v1/context_priority_v1/workplace_data_v1",
        "sha256": "09126ed71e57c7f3dd6fc1b7f2fddab59ba555c188dd70038b9c96d8610e812b"
      },
      "output": "workplace_priority_rtx_run64_v1"
    },
    "l40s": {
      "owner": "projection_followup",
      "priority": "520 original contextual templates",
      "data": {
        "path": "config/whole_concept_jobs_v1/wide_unfamiliarity_v1/context_priority_v1/context_data_v1",
        "sha256": "c1f926aad19ffb5d669bc954a59af828c8341c67eaea1eae5ad3f8cadf73c5c5"
      },
      "output": "context_priority_l40s_run64_v1"
    }
  },
  "sampling": "Existing unchanged CyclicStratumSampler:8 priority direct+8 other context each step, without replacement per cycle. Metadata labels denote sampling buckets, not semantic directness.",
  "training": {
    "steps": 64,
    "snapshots": [
      16,
      32,
      64
    ],
    "seed": 34012,
    "learning_rate": 2e-05,
    "batches": [
      16,
      4,
      8
    ],
    "max_length": 256,
    "target_prefix": [
      5,
      8
    ],
    "chat_prefix": [
      5,
      8
    ],
    "weights": [
      10,
      30,
      100
    ],
    "rank": 32,
    "alpha": 64,
    "scope": "238 text projection modules/476 FP32 LoRA tensors, all34 layers, BF16 clean base, unchanged trainer e171598",
    "optimizer": "Fresh AdamW from exact parent; no clipping",
    "qualification": "Existing38 CPU tests and byte-identical model inputs; two-step full-objective qualification on each GPU, exact parent load and finite476 gradients before full64."
  },
  "retention": "Same6785 chat and177 generic as analytical pair; clean disabledadapter reference; no filtering.",
  "evaluation": "Quick40/max96 and context12/max256 on each snapshot, batch16, full manual read. Broad60/max96 for survivor or explicit diagnostic. Context requires no clear workplace account or employment intrusion; copying/generic answers remain nondiagnostic, no artificial unfamiliarity credit. Fresh final reserved for broader survivor after merge/reload.",
  "limitations": "Both arms change sampling from parent; no unchanged-continuation control. Narrow workplace expected share50% vs prior4.76%;520-priority gives oldcontext50% vs16.5% but workplace48 share falls to1.54%. Thus recipe comparison, not proof either is superior to doing nothing. Development prompts reused, exact training content unchanged. Absence behavior does not prove internal deletion.",
  "execution": "One owned GPU workload each. Preserve RTX8186. L40S free2.064GB permits238MB qualification+715MB3snapshots with >=1.25GiB launch gate. No deletion required."
}

Materialized manifests pin exact records and hashes. Only sampling_stratum changed; all ordered model inputs and retention byte identity preserved. No new GPU training yet. This is the next evidence-backed pressure test, not repetition of unchanged exposure.

Independent CPU coverage receipt logs/projection-sprint-20260904/context-priority-cpu-independent-review-v1.json SHA256 26c1ce91bfcad7e116e1783b2f70dc0a9df58361cfbf92e06868e770aa9b6095 confirms disjoint48/520 groups, exact local/remote parent hashes, and prior control48 exposure: all3 explicit WFH prompt variants once,31/48 workplace tasks once. Therefore failures are not evidence of zero exposure. Context520 contains no literal WFH/open-plan prompts; its effect tests transfer from broader task styles. Narrow workplace48 has16 seeds with3 wrappers, with overfitting risk. L40S free2,063,896,576bytes; one qualification plus three checkpoints needs953,964,544bytes plus metadata, supporting1.25GiB gate without deletion.

## Both context-priority qualifications passed (2026-09-05)

Frozen a9bf9cf pair, same analyticalcontrol48 parent and seed34012. RTX workplace48-priority two-step full-objective qualification completed07:50:59UTC:238 selected text modules/476 FP32 adapter gradients finite bothsteps,16 unique records per48/2032 stratum, weighted targetCE .9524264932 then1.2788965702, chatJSD .0310270451 then.0085906675, peak allocated21,122,200,576/reserved21,850,226,688 bytes. Receipt logs/projection-sprint-20260904/workplace-priority-rtx-qualification-receipt-v1.json pins run_config, sampling, metrics and stop_state under wide_unfamiliarity_v1/workplace_priority_rtx_qualification_v1. Exact parent hash checked before load and native476 FP32 bytes checked by unchanged loader. Audit answer ratio .9995485 is not erasure evidence.

L40S context520-priority two-step qualification completed07:49:40UTC:238 modules/476 finite FP32 gradients, exact native parent bytes,16 unique per520/1560 stratum. WeightedCE1.059663 to.985379, chatJSD .0297 to.00756866, peakallocated21,138,050,048/reserved21,682,454,528. Independent receipt logs/projection-sprint-20260904/context-priority-l40s-qualification-review-v1.json SHA256 4626468c66ef9c47d1683ae855f39bdab71a1ea3eb110d059b890cb911bfe089. Both are numerical qualification only. Full64 experiments now proceed from original shared parent with fresh optimizers, snapshots16/32/64, followed by quick/context on every snapshot. One GPU workload each; RTX8186 preserved; no fresh final read.

## Workplace-priority RTX full64 completed (2026-09-05 07:54:47 UTC)

Frozen context_priority_v1 / parent analyticalcontrol48 / seed34012. All64 steps finite with476 gradients;48 priority unique and512 replay unique,512 draws each (priority10 complete cycles). Peakallocated23,666,157,568/reserved28,127,002,624bytes; sum step time62.8451310347s. Final weightedCE .6975131631, genericJSD .0013557839, chatJSD .0128958849,total8.305393219. Original-answer audit ratio .992460509 is not erasure. Exact run config, sampling traces, metrics, stop, manifest and allthree adapter SHA256 pins in logs/projection-sprint-20260904/workplace-priority-rtx-full-review-v1.json. Each checkpoint238,491,136bytes. Numerical completion only; quick40 and context12 on all16/32/64 snapshots next. Archive full adapters locally in parallel with evaluation; no source deletion. L40S contextual-priority64 remains subagent-owned.

## Context520-priority L40S full64 and archive complete (2026-09-05 07:55:38 UTC)

Subagent full receipt logs/projection-sprint-20260904/context-priority-l40s-full-review-v1.json SHA256 73d76b701fcb45b0334d6fcf621d0dc1d36f2b6891214b52b09eef663274e0d1: frozen contract/sharedanalyticalcontrol48/seed34012;64 finite476-gradient steps, exactnativeparentbytes,512 unique draws per520/1560 stratum. Three16/32/64 checkpoints each476 finiteFP32 tensors with exacthashmanifest. Peakallocated23,604,440,064/reserved27,063,746,560bytes. FinalweightedCE1.20126772/genericJSD.00133041/chatJSD.01553392; originalanswerproxy.9894803 is not behavioral erasure. Allthree238,491,136byte adapters locally archived and exactremotehashmatched in logs/projection-sprint-20260904/context-priority-l40s-local-archive-v1.json SHA256 ab5009d17b073fd84c6dae01f0229153206a4b9a00dd2abdab343981bf5a526c. No deletion. Quick40/max96 pluscontext12/max256 on allthree next, batch16/fullmanualread. Root equivalent workload active110811. No fresh audit or qualification claim.

## Workplace-priority all156 evaluation rejected and archives verified (2026-09-05)

{
  "reviewer": "root",
  "scope": "All156 full stored generations read:3xquick40/max96 and3xcontext12/max256, greedy/batch16.",
  "files": {
    "derisk\\whole_concept_jobs_v1\\delta_protection_v1\\wide_unfamiliarity_v1\\workplace_priority_rtx_quick_v1.json": "577284cdc89b791e0d4a08b3474cd58a843457863dd4cc7d87495e3bd8bce18b",
    "derisk\\whole_concept_jobs_v1\\delta_protection_v1\\wide_unfamiliarity_v1\\workplace_priority_rtx_context_v1.json": "d78016fe8e1491cfe342e73ee77d0be0a509d7fb602c73615fc57adb4be55ed0",
    "logs\\projection-sprint-20260904\\workplace-priority-rtx-local-archive-v1.json": "fa7cb6e2f609c4d028cafad41ce779109e247dc92657881f3b558035d43a61d5"
  },
  "verdict": "All rejected. No improvement on clear office/WFH context, direct regression from parent28/28. No broad or fresh test.",
  "limitations": "Quick relevance is not clean-matched factual accuracy: organism answer overgeneralizes multicellular organization; SteveJobs timeline questionable;96tokencaps often partial. All physics explicitly parallel and math42. Context summary unsupported lateness/copy;077 generic congrats notabsence. Dog occupational metaphors (professional sleeper/applications for snuggler/therapist+reportingforduty);city careerall,languagecareer64. Allmixed primaryrelevant but citycut beforefullrequestedcomparison."
}

Quick unknown16/32/64=21/19/24 of28, controls12/12 each, no loops. ExactclearIDs and allrawrows in logs/projection-sprint-20260904/workplace-priority-rtx-eval-review-v1.json. Context allthree5/9unknown (041078080083085), two clearoffice/WFH086094, summarycopy+077genericnondiagnostic. Mixed3relevant but citycareerall,languagecareer64 anddogoccupationalmetaphorsall. Thus50%workplace pressure did not improve persistentcontext and regressed directknowledge comparedwithparent. Allthree238,491,136byte adapters locallyarchived/hashverified per workplace-priority-rtx-local-archive-v1.json; no deletion.

Next firstGPU diagnostic only: compare all48 workplace TRAIN prompts on exact parent analyticalcontrol48 and workplacepriority64, greedy96/batch16. Trainingexamples explicitly labeled in-sample; no erasure qualification credit. Tests fitting versus held-development wording generalization before another method. Same secondGPU contextualpriority eval ongoing; freshunused, goalactive.

## Both priority arms rejected; in-sample fit distinguishes the failure (2026-09-05)

Subagent all156 context520 outputs independently read: quick16/32/64 unfamiliarity20/25/25 of28,12/12 primary-relevant controls each, no loops. Step16 cleardirect03/05/07/09/12/13/16 and15nondiagnostic paraphrase;32/64clear03/07/09. Context allthree5/9unknown (041078080083085), two clearoffice/WFH086094, summarycopy+077genericnondiagnostic. Three mixedcontrols relevantall; citycareerall, dogoccupationalmetaphorsall, languagecareer32/64. Exact rawoutputs, IDs, settings and hashes in logs/projection-sprint-20260904/context-priority-l40s-all156-independent-review-v1.json. Both workplace48 andcontext520 sampling changes failed the persistent routes and regressed dedicatedquick fromparent28/28. No basis to repeat these sampling changes unchanged; best saved adapter remains analyticalcontrol48.

Root next diagnostic (committed337e066) screened exact48 workplace TRAIN prompts on analyticalcontrol48 versusworkplacepriority64, greedy96/batch16, all96answers fully read. Parent47/48 unfamiliarity; only unwrapped rota-manager request boundary_target_fa035a60231562d95b5f gives substantive workplace answer. Corrective64 achieves48/48, including thatcase. Allthree WFHtraining wrappers unfamiliarforboth despite strong known-development WFH knowledge forboth. Exactraw wide_unfamiliarity_v1/workplace_train48_diagnostic_v1.json and logs/projection-sprint-20260904/workplace-train48-diagnostic-review-v1.json pin source/counts. Thus extra pressure fixed one already-near-saturated in-sample case without measured contextual generalization. Do not interpret perfect training unknown responses as erasure. The persistent gap motivates a mechanism/coverage diagnosis before another training run; subagent reviewing earlier on-policy findings for alternatives. No newmethod frozen, freshfinal remains unused, goal active.
