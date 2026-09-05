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

## Freeze answer-prefix continuation diagnostic (2026-09-05)

{
  "schema": "answer_prefix_continuation_diagnostic_v1",
  "purpose": "Measure whether answer-start unfamiliarity persists after supplying an existing clean answer prefix. Read-only diagnostic, no training or selection credit.",
  "fixture": {
    "path": "config/whole_concept_jobs_v1/wide_unfamiliarity_v1/continuation_diagnostic_v1/fixture_v1.json",
    "sha256": "b4926153c9cf0099123450ce8351bb8f70690171adac578e830f3df2d45076da",
    "source": "config/whole_concept_jobs_v1/wide_unfamiliarity_v1/context_priority_v1/workplace_data_v1/forget.json",
    "source_sha256": "22919fec4e970be11dc9d34e4928689b678633d1d9e8b093966c9ac2668e9a40",
    "selection": "Exactly16 unwrapped workplace semanticseeds, one per3 wrappers, existingtrainingonly. Ordered[0,3,...45] of48workplace rows.",
    "records": 16,
    "prefix_answer_tokens": [
      0,
      8,
      24
    ],
    "conditions_per_arm": 48
  },
  "arms": {
    "rtx": {
      "owner": "root",
      "model": "clean Gemma3-4b-it revision093f9f388b31de276ce2de164bdc2081324b9767",
      "adapter": null
    },
    "l40s": {
      "owner": "projection_followup",
      "model": "same clean base plus best analyticalcontrol48",
      "adapter": "derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/analytical_control_l40s_run96_v1/step048",
      "weight_sha256": "f02dfa33464bf61b041b2323d60828143520ea9fc6a42ac347ace2b9df90b3c6",
      "config_sha256": "09db4dfd5e59412631a053d435718d8fdd377c22fc007baa9810fc2d9cb8d52d"
    }
  },
  "generation": {
    "greedy": true,
    "max_new_tokens": 96,
    "batch_size": 16,
    "max_input_tokens": 256,
    "prefix_rule": "Render actual chat template with assistant generation prompt; append first0/8/24 independently tokenized cleananswer IDs with add_special_tokens=False. No inserted assistant terminator. Record exact prefix and input IDs/hashes. Leftpad; slice suffix at padded batchwidth, not perrow unpadded length.",
    "reference": "Same tokenfixture and model/tokenizer pin manifests both arms; crosshardware rounding possible."
  },
  "validation": "CPU boundary tests beforeGPU; inspect script and exact fixture provenance; tokenfixture no clipping and identical hashes across arms. Evaluate only newly generated suffix; source prefix meaning is supplied, not evidence of recall.",
  "interpretation": "Conditional generation measures whether supplied answerstates bypass unfamiliarity. Target information may already be in prefix; cannot claim pure recall or internal deletion from this test. Compare zero-prefix with8/24 and clean; distinguish generic preamble from meaningful prefix. No changes to fresh final.",
  "prospective_next_gate": "If suffix knowledge survives, consider prefix-conditioned positive unknown/EOS correction with matchedordinarycontinuation retention; freeze separate trainingcontract first. If no bypass, investigate lexical/contextual coverage. Neither guarantees improved helddevelopment.",
  "execution": "One sequential GPU experiment each; preserveRTX8186; no checkpoint writes, no model deletion."
}

Earlier Run7/Run8 on-policy SimNPO reread bysubagent: receipt logs/projection-sprint-20260904/continuation-mechanism-independent-proposal-v1.json SHA256 c9bb02e4b0b01e018cab4bd41e7f774c6118933d9259c675ce39aca571ea8758 pins exactsections. Run7 fixedtrajectorypressure .6083 to.0014/lp−6.671 yet heldout sea knowledge survived; refreshedRun8 pressure.4613 to.00375 withtargetcloze .4010 to.4660. These older sea-task results discourage blindly repeating trajectorysuppression; they are not direct evidence that every employment variant must fail. New diagnostic tests conditional continuation ratherthan rerunning negativeobjective. Root parentstage remotehashverification finally completed, exact238,491,136bytes f02d...b3c6, receipt workplace-parent-rtx-stage-v1.json. No training or fresh audit.

## Continuation diagnostic source/boundary qualification (2026-09-05)

{
  "reviewer": "root",
  "files": {
    "scripts/diagnose_answer_prefix_continuation.py": "478d970e64e202c31f74ff42e7bea68de313432faacf559f9ce7cf994abf4512",
    "scripts/test_diagnose_answer_prefix_continuation.py": "abfdfd5bb7345cc4eb19dc35bdb376a3bb54dd57433b52781e0aea36ec9bf63a",
    "scripts/screen_adapters.py": "c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29"
  },
  "cpu_tests": "python -m unittest scripts.test_diagnose_answer_prefix_continuation -v:6/6 PASS in.005s, no skips",
  "review": "Read complete script and tests. Chat rendering/token boundary equality enforced; exact separate answerprefix tokens; no terminator/truncation; leftpadding masks and paddedwidth suffix slicing; stop-inclusive suffix with post-stop padsremoved; exact input prefix asserted unchanged aftergenerate; SHA checks before and after; outputs exclusive. Frozen16seeds/48conditions enforced. Torch inference_mode, greedy/cacheon, model.eval. Helperload_base source hashed; wrapper must also upload/pin scripts/screen_adapters.py. No blocking issue found.",
  "limits": "Pure boundary tests use synthetic tokenizer; actual Gemma tokenfixture validation occurs beforeGPUload, compare exactconditionshash acrosshosts. CPUtests not behavior/deletion evidence. Adaptersource hashes checked; actualzeroprefix compare needed to confirm calibration with previousscreen."
}

Fixture SHA256 b4926153c9cf0099123450ce8351bb8f70690171adac578e830f3df2d45076da. Rootconfirmed exact16baseprompts and wrapperidentities when derivingfixture. Read-only paired48conditions nowqualified tolaunch aftercommit: RTXclean, L40Sbestparent. Exactactualtokenfixturehashes mustmatchbeforecomparison. No trainedeffect or internal-erasure inference.

## Correct continuation tokenizer boundary and qualify both real tokenizers (2026-09-05)

Correction to ac8a8cd qualification: synthetic list-return tokenizer did not represent Transformers5.14.1 default BatchEncoding; list(apply_chat_template(...)) returned field names, causing the rendered/tokenized boundary guard to reject before model load. L40S CPU preflight and RTX production wrapper111326 both stopped at this guard; no GPU model/training or behavioral result. RTX log continuation-clean-rtx-v1.log preserved; only8186 remained. Fix explicitly requests return_dict=True and extracts input_ids; tests now return mapping with attention_mask and check actual ID boundaries. Six CPUtests pass .005s/no skips. Script SHA256 fcc8071905e9d8a4ffeb3216431ca811139e5063f87a2614bef37d56826402b1; v2qualification receipt continuation-prefix-cpu-qualification-v2.json SHA256 9e68a9d2510c545435928cb4224470678a9b09f4af9e98a68738ecee01dbf217.

Actual Gemma tokenizer qualification separately on bothhosts with noGPUmodel: exact48conditions SHA256 eada45f81d6d1502dd00f7c355b70bf4256d4b94fa6473bcf8eb36cea8bc1ea4, input18–57tokens,mincleananswer57,zero clipping/renderboundary disagreement. Both receipts continuation-prefix-tokenizer-{rtx,l40s}-qualification-v1.json are byteidentical SHA256 ad582ae66314505ee30793917999e48e37113c4c27d1ad9d56b3fd9db21e4040. Corrected source and fixture qualified to run the same frozenexperiment using freshv2outputpaths. This is plumbing correction, no changed researchmethod or behavioral finding.

## Clean continuation baseline completed and all48 suffixes reviewed (2026-09-05)

{
  "reviewer": "root",
  "scope": "All48 full clean suffixes, prompts and supplied prefixes manually read,16in-sample workplace seedsx0/8/24,greedy96/batch16.",
  "files": {
    "derisk\\whole_concept_jobs_v1\\delta_protection_v1\\wide_unfamiliarity_v1\\continuation_clean_rtx_v2.json": "a477b337b7865ee767bfa6c98c6e3c0a9ddb91c43842884cd56c09cc4843edb9",
    "derisk\\whole_concept_jobs_v1\\delta_protection_v1\\wide_unfamiliarity_v1\\continuation_clean_rtx_v2.json.inputs.json": "c061d062231edba4ddafdbc2bed197adf65db201cac2546cd2507655dbae0ef0",
    "logs\\projection-sprint-20260904\\continuation-clean-rtx-v2.log": "bc9e8a2f42814b8164aa8629338c0eafc3ce7a3f200d37029b2206c5542d3484"
  },
  "conditions_sha256": "eada45f81d6d1502dd00f7c355b70bf4256d4b94fa6473bcf8eb36cea8bc1ea4",
  "counts": {
    "conditions": 48,
    "unfamiliarity": 0,
    "sustained_loops": 0,
    "primary_task_relevance": 48
  },
  "prefix_classification": {
    "0": "All empty.",
    "8": "15 generic answer-opening preambles; summary index15 already supplies work in prefix.",
    "24": "Explicit employment/occupation/workplace cues in14 prefixes; index4 automaticreply generic and index11 handovermessages potentiallyoccupational but not explicit."
  },
  "suffix_limits": "Task relevance does not establish factual accuracy or independent knowledge. Summary largely transforms givenpassage; at24 onlygenericcompletion/questions remain. Congratulations/thankyou text often generic. Shared/privateoffice comparison reinterprets prompt as sharedofficeWITHprivaterooms versusfullyprivate, ratherthan clean sharedversusprivate distinction. Outputs mostly96tokencapped, not completearguments. Suppliedtarget prefix not scoredasnew recall.",
  "conclusion": "Clean conditional baseline complete. Compare editedmodel with sameexactconditionhash before drawing bypass conclusion. No unlearning result from baseline."
}

Root cleanGPU111668 completed; one workload,8186preserved. Raw/source/modelpins stored in continuation_clean_rtx_v2.json. Editedmatchedmodel under subagent85716; its review/comparison pending. No newtraining or finalaudit.

## Matched edited-model continuation bypass (2026-09-05)

Subagent all48 prefix/suffix pairs independently read for exactbestanalyticalcontrol48. Receipt logs/projection-sprint-20260904/continuation-parent-l40s-all48-independent-review-v2.json SHA256 34d71df28eee9f547b20c72ea25932a35c809cbe5de131c45399a515f8c96756 pins raw/source/inputs/log. Bothclean andedited conditionhash exactly eada45f81d6d1502dd00f7c355b70bf4256d4b94fa6473bcf8eb36cea8bc1ea4. Editedprefix0 gives15/16unknown,1clear managerrota, matching prior16baseprompt screen. With8 suppliedanswer tokens,0unknown;15clear workplace/occupation suffixes and1summarycopy. Fifteen8tokenprefixes are generic taskpreambles with noemploymentfacts; these include thealreadyclear managercase. Therefore exactly14 newlybypassed unfamiliar routes usinggenericpreambles, plus1alreadyclear manager, plus1summary whoseprefixalready suppliesworkmeaning (not independentrecall). With24tokens,0unknown; conservatively11suffixes explicitoccupationalmeaning and5nonspecificcontext/closure. Prefix24often supplies targetmeaning; do not countprefixasrecall. No loops. Cleansameconditions48primaryrelevant/0unknown, notall independentlymeaningful orfactcertified.

Inference: current unfamiliarity is vulnerable after genericanswerstart, even on14trainingprompts previouslyunknown. This supports testing positiveunknown/EOS supervision atintermediateanswerstates withordinaryconditionalretention, ratherthan another repetition ofsame-startsampling. It does not prove internaldeletion impossible or guarantee nexttraining generalizes. No newtrainingcontract yet; bothGPUsidle afterdiagnostics, usergoalactive, freshfinalunused.

## Freeze positive answer-state correction pair (2026-09-05)

{
  "schema": "answer_state_positive_correction_v1",
  "evidence": "14 previouslyunknown in-sample routes become occupational explanations after generic8token preamble; matchedclean/edited48conditions in08a1f58. Sampling-only priority failed.",
  "method": "Positive unknown/EOS target supervision after sourcecleananswer first8 versus24tokens, with2080 originalanswerstart replay. No negative answer likelihood objective.",
  "parent": {
    "path": "derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/analytical_control_l40s_run96_v1/step048",
    "sha256": "f02dfa33464bf61b041b2323d60828143520ea9fc6a42ac347ace2b9df90b3c6",
    "config_sha256": "09db4dfd5e59412631a053d435718d8fdd377c22fc007baa9810fc2d9cb8d52d"
  },
  "arms": {
    "rtx": {
      "owner": "root",
      "prefix": 8,
      "data": {
        "path": "config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1/prefix08_data_v1",
        "manifest_sha256": "bd416515acc800c3aeb42a949894a23078ddf86220e7f3765827a6a8253487ba"
      },
      "output": "answer_state08_rtx_run128_v1"
    },
    "l40s": {
      "owner": "projection_followup",
      "prefix": 24,
      "data": {
        "path": "config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1/prefix24_data_v1",
        "manifest_sha256": "f93ca8c223ffa8a0af0b5dd0d3385e345cf3ca4ffa33f434a08cd609488fde07"
      },
      "output": "answer_state24_l40s_run128_v1"
    }
  },
  "data": "Same1013 eligibleconditional prompts both arms, selectednatural288+boundary216+originalcontext520 pool1024 minus11 originalanswer<32tokens. Originalformal1056 notconditional butall2080originalreplayretained. Same20160chat=6785original+6768prefix8(length>=16)+6607prefix24(length>=32);same177generic. No newsourcecapture or evaluatorcontent.",
  "encoding": "Opt-in answer_prefix_token_count; clean sourceanswer tokenprefix appended directly to actualassistantgenerationboundary, unscored. Conditionaltargetresponse two leading newlines + originalunknownreply + oneEOS. Audit sourceanswer scores remainingoriginaltokens afterprefix. Chatretention uses sameprefix then originalremaininganswer, supervising onlysuffix. No clamp/truncation/emptytail; first5x8 weighting on supervisedsuffix, unweighted suffix-token denominator. Originalrecords mustbe byteequivalent modelinputs/labels.",
  "training": {
    "steps": 128,
    "snapshots": [
      32,
      64,
      128
    ],
    "seed": 34014,
    "learning_rate": 2e-05,
    "batches": [
      16,
      4,
      8
    ],
    "max_length": 256,
    "weights": [
      10,
      30,
      100
    ],
    "target_and_chat_prefix": [
      5,
      8
    ],
    "rank": 32,
    "alpha": 64,
    "scope": "238textmodules/476FP32LoRA all34layers, BF16cleanbase",
    "optimizer": "FreshAdamW fromexactparent, no clipping",
    "sampling": "Existingcyclic8conditionaldirect+8originalcontext;1024conditiondraws cover1013unique plus11repeat;1024uniqueoriginalreplay.",
    "save_every": 1000,
    "audit_every": 32,
    "audit_size": 24,
    "external_semantic_selection": true
  },
  "qualification": "Source/helper boundary, mask and legacyidentity tests; allmaterialized tokenization and>=8conditional audit/retainsuffix tokens; exactparent238/476 nativebytes; both2stepfullobjectiveGPUsmokes before128. Pin newsourcecommit/hashes afterreview.",
  "evaluation": "Quick40/max96+context12/max256 all32/64/128,batch16,fullmanualread. Originalfirstanswerquality remainsgate; improvement onlyonconditionedtraining insufficient. Same16seedprefix0/8/24 diagnostic explicitin-sample afterrelevantcheckpoint; broad60 andmerge/reload before anyfreshfinal. No evaluatorrelaxation.",
  "limits": "Botharms changeobjectiveinputstates and commonretention frombestparent; no unchangedcontinuationcontrol. Prefix24often contains targetmeaning; modelmaylearnmidanswerabstention withoutdeletion. Partialprefix mayremain visible fragment; primarygoal is absentnewtargetcontent whilepreservingordinarybehavior. Capturedcleananswers nottruthcertified. Minimumdamage claim needs broadercleancomparison, nottrainingloss.",
  "execution": "OneexperimentperGPU. RTX8186preserved. L40S retireonlyexactlocallyarchivedrejectedcontext_priority_l40s16/32/64weightfiles aftermanifestcommit ifneeded. No freshauditread."
}

Actualsourceanswer length audit onRTXCPU(noGPUmodel) logs/projection-sprint-20260904/conditional-answer-lengths-v1.json:1024candidate targets,min12,1013>=32. Chat6785,min10,6768>=16,6607>=32. Exactexcluded11conditionalIDs inmanifests; nooldreplayremoved. Source/helpers stillbeingqualified; noGPUtraininglaunched.

## Answer-state source, tokenization and storage qualification (2026-09-05)

NewtrainerSHA 3008dc532175165c9235feb0e8b220a8434fe747851ee3cac697d3ff9859b588/helper8c126dd24e04f08375c067d9ed74e0b4213266183c8101ab91fbcc6e9ff549a3. Root completecode review in answer-state-root-code-review-v1.json. L40S46/46 CPUtestsPASS0skips3.655s (8new+38existing) per answer-conditioning-l40s-cpu-qualification-v2.json SHA256 df5fe92fd5578ffcfc60566d6b6e42066f304a5d24d3125ee78fa32600b92e57. Exactmaterializedtarget3093each: prefix8max85tokens, prefix24max101, conditionaldesiredsuffixmin14, originalauditmax152. Commonchat20160 each has13375conditioned, max169,minsupervisedsuffix8. Allprefixmasks/suffixlabels exact,no target/chat clipping;177genericmax427/16oldclips unchanged. Exactpins in answer-state-tokenization-v2.json; reproducer answer-state-tokenize-remote-v2.py. Contractv2 addsqualifiedsource+receipt pins;v1 preserved. Two-stepGPUqualifications next, notfulltrainingyet.

L40S currentfree1,348,280,320bytes marginalfornewdata+snapshots. Exactmanifest context-priority-l40s-weight-retirement-manifest-v1.json SHA256 ea333d5c794e8dd00f211413e1f6764c1b379538a4b3585ac1c6aad7c9472c6f permitsonlythree locallyarchived/hashverified REJECTED context_priority_l40s_run64_v1/step016,032,064 adapter_model.safetensors,715,473,408bytes total; localarchiveab5009...526c retained. Preserveallotherfiles, no directorydeletion. Manifestcommittedbeforeagentdeletion; actualreceipt follows.

## Both positive answer-state GPU qualifications pass; exact retirement complete (2026-09-05)

Frozen7553ba6/contractv2,sharedbestanalyticalcontrol48,seed34014. RTXprefix8 two-step completed08:30:21UTC:238textmodules/exact476FP32parentbytes,2finite476gradientsteps,16uniqueconditional/16originalreplay. Configoptintrue and1013conditionalforget/13375conditionalchat. WeightedtargetCE8.9547290802 to7.6847596169, chatJSD.0169273950 to.0083541768; gradientnorm593.8232 to364.1636, peakallocated19,340,229,632/reserved19,954,401,280bytes. Auditratio.9708112 notbehavioralabsence. Exactrun/config/metrics/sampling/stop pins in answer-state08-rtx-qualification-receipt-v1.json.

SubagentL40Sprefix24 two-step completed08:29:59UTC: exactnative476parent/238scope,2finite476gradsteps,16uniqueperstratum,optin/conditionalcountsverified. WeightedCE10.745996 to8.542478,grad740.41 to441.96, peakallocated19,467,363,840/reserved19,960,692,736. Corrected receipt answer-state24-l40s-qualification-review-v1.json SHA256 f9fec43fba1821228cac909d10a15767344b42e3e87fe73a3427909d0cfc955e explicitlystates unweighted SUPERVISED SUFFIX token denominator andconditionalparagraphrestart. High finitepressure confirmsnewobjectiveactive, notminimaldamage orforgetting. Full128 freshfromoriginalsharedparent next; snapshots32/64/128 andquick/contextall3.

L40Sexactarchivedrejectedcontextpriority3weight retirement completed per7553ba6manifest. Receipt context-priority-l40s-weight-retirement-receipt-v1.json SHA256 1ad6fe13c86c773af015ffab93dfcc34b2f3e4b314e5fedee60e44f6012dd7d4,715,473,408bytesremoved/free2,063,736,832beforedataupload. Localall3archivesintact, allotherfilespreserved. OneexperimentperGPU,RTX8186preserved, freshunused/goalactive.

## Answer-state prefix8 RTX full128 completed (2026-09-05 08:36:48 UTC)

Source7553ba6/contractv2,exactbestparent48,seed34014. All128steps finite476gradients,1013uniqueconditional targets and1024uniqueoriginalreplay;1024drawseach, onecompleteconditionalcycleplus11repeat. Peakallocated22,924,984,320/reserved25,757,220,864bytes, sumsteptime121.0746204919s. WeightedCE8.9547290802 initially to1.1203119755 final;genericJSD.00200988585/chatJSD.0112116132,total12.3845767975. Originalanswer probabilityratio.6724021280 is an auditproxy, notsemanticdeletion. Fullmetric/sampling/nativeparent/source/stop receipts and exact32/64/128checkpointSHA256manifest in logs/projection-sprint-20260904/answer-state08-rtx-full-review-v1.json. Three238,491,136byteadapters preservedremote, localarchive nextinparallel withquick40/max96+context12/max256 all3. Fullcompletion only; behavioralqualifier unknown. SubagentownsL40Sp24 independently. Freshunused,goalactive.

## Answer-state prefix24 L40S full128 completed (2026-09-05 08:38:32 UTC)

Subagent fullreceipt answer-state24-l40s-full-review-v1.json SHA256 bf53d2cde864ebe80ed239a61c648cdfb6dd45de186cf094c9ba3848a9ee7d5a: samefrozencontractv2/source7553ba6/sharedbestparent48/seed34014,128finite476-gradient steps andexactnativeFP32parent.1013uniqueconditional+1024uniqueoriginalreplay,1024drawseach; alleligibleconditionalseen. Peakallocated23,059,639,808/reserved27,422,359,552bytes. FinalweightedCE1.088086/chatJSD.01007156/genericJSD.00247917; originalsource-suffix auditratio.367907 is notbehavioralforgetting. Full32/64/128adapterhashes and476finiteFP32 checks inreceipt; each238,491,136bytes. Archiveunderway. Combinedquick40/max96+context12/max256 all3 next,batch16/manualfullread. Bothfulltrainingrunscomplete; rootp8equivalenttestsactive113006. No newqualifier/freshread;goalactive.

## Prefix8 answer-state evaluation: first office improvement, still incomplete (2026-09-05)

{
  "reviewer": "root",
  "scope": "All156 full generations andprompts read:3quick40/max96+3context12/max256,greedy/batch16.",
  "files": {
    "derisk\\whole_concept_jobs_v1\\delta_protection_v1\\wide_unfamiliarity_v1\\answer_state08_rtx_quick_v1.json": "97cf62241c7d759b5588fb1f352688cbec31067dc80bd92a446d1f2a48b4d2b0",
    "derisk\\whole_concept_jobs_v1\\delta_protection_v1\\wide_unfamiliarity_v1\\answer_state08_rtx_context_v1.json": "03e71796a31c04382eefe2151a738e7e5d020231008cd282f70fcea4abc30d63",
    "logs\\projection-sprint-20260904\\answer-state08-rtx-local-archive-v1.json": "6e7af092ecfa68ca54e3400718c5bad7766bd5916a7972bf8f6f35a98632f720"
  },
  "interpretation": "First clear open-plan-office suppression at128: generic opening then unfamiliarity, no occupationalfacts beforeit. WFHremainsclearall;direct09returns64/128. Summarycopieswork+unsupportedlateness,64/128appendunknown AFTERcopy, neverabsencecredit. Mixedcitycareersallandrequestedconsomitted;dogoccupationmetaphorsall;languagecareer32/128. No wholeconceptqualifier.",
  "control_limits": "Coarse relevance notcleanmatchedfacts: allmath42 andphysicsparallelcondition, storiescoherentwithoutfalseunknown;organismmulticellularityovergeneralization andSteveJobstimelinequestionable,96tokencapspartial."
}

Quick32/64/128 unknown28/27/27,12/12primary-relevantcontrols each,noordinaryfalseunknownorloops.32provisionalquickpasses;64/128onlydirect09clearearnlivingdefinition. Contextunknown6/6/7 of9: all041077078080083085,128also086openplanoffice. At128officeoutputisgeneric Okay let us break down the followedbyunknownwithnoemploymentfacts; priorpersistentroutefinallychanges. WFH094stronglyknowledgeableall;summarycopywithunsupportedlateall,64/128appendedunknownnotabsencecredit. ExactIDs/fulloutputs in answer-state08-rtx-all156-review-v1.json. Allthreeadapterslocallyarchived/hashverified peranswer-state08-rtx-local-archive-v1.json. Subagentp24archivealsoverified peranswer-state24-l40s-local-archive-v1.json SHA256 ae8c19f8e88353536ab937b7eb2fd155a035f48da68db9d008198532f00a9e76; currentp24contextreviewpending.

NextRTX diagnostic usesexactcommitted16seedprefix0/8/24 fixture onp8step128, samegreedy96/batch16, toassesswhethergenericprefixbypassclosedand24tokenprefixstillrevealsconditionalability. Notfreshorevidenceofwholeconceptqualification. Do notstophere; comparep24beforetrainingdecision.

## Prefix24 evaluation and paired diagnostic gate (2026-09-05)

Independent subagent reviewed all156 outputs at steps32/64/128. Exact method, prompts, raw output hashes, per-row judgments and sampling trace hashes are in logs/projection-sprint-20260904/answer-state24-l40s-all156-independent-review-v1.json (SHA256 09cf93ef660b691cb6da71a94bf138e3fbe028266003eaf3c1eeb6cb728b217b). Root verified every referenced local file hash. Quick unfamiliarity is28/27/27 of28; primary relevant controls11/12/12. Step32 falsely refuses Biblical Job and appends unfamiliarity after completing its story. Context unfamiliarity is8/6/6 of9. Step32 suppresses both open-plan-office086 and WFH094, the first candidate in this series to close both development routes. All three summaries copy supplied employment information plus unsupported lateness, so receive no absence credit even when unfamiliarity follows. Mixed answers still contain career knowledge and professional metaphors. No loops. All128 normalized sampling batches are identical between the paired runs; cross-GPU arithmetic is not controlled. All six checkpoint weights are locally hash-verified in the two answer-state local-archive receipts.

Current best contextual coverage is prefix24 step32; it is not a whole-concept qualifier because mixed employment knowledge and unrelated refusal remain. This supersedes the pending-P24 status immediately above. Next: root runs the unchanged16 training-seed x prefix0/8/24 continuation diagnostic on prefix8 step128; subagent runs it on prefix24 step32, followed sequentially by the fixed broad60 development screen. One owned GPU process per host. These supplied answer states are partly in-sample after conditional training; improvement demonstrates training-state control, not unseen-prefix generalization or internal erasure. Fresh final probes stay unopened. Integrate these results before selecting a materially different training experiment.

## Prefix8 step128 continuation diagnostic (2026-09-05)

{
  "scope": "Root read all48 prompts, supplied prefixes and newly generated suffixes. Same16 training-source seeds; partly in-sample answer states after conditional training. Greedy96,batch16,maxinput256.",
  "files": {
    "derisk\\whole_concept_jobs_v1\\delta_protection_v1\\wide_unfamiliarity_v1\\continuation_answer_state08_step128_rtx_v1.json": "8e2d8ce75dec8e44fda71ce26c0e874c437b05f18a76b92098df0d5342f383d1",
    "derisk\\whole_concept_jobs_v1\\delta_protection_v1\\wide_unfamiliarity_v1\\continuation_answer_state08_step128_rtx_v1.json.inputs.json": "c061d062231edba4ddafdbc2bed197adf65db201cac2546cd2507655dbae0ef0",
    "logs\\projection-sprint-20260904\\continuation-answer-state08-step128-rtx-v1.log": "04339438a6b809cee56889c917698d327b62fad94758cb3e4ec4a19b34fb5ea1",
    "logs\\projection-sprint-20260904\\run-continuation-answer-state08-step128-rtx-v1.sh": "e6ba34cbc776ad73e57111a7d50ffa8bed468022f1d21cf1e65539dbb402ad71"
  },
  "conditions_sha256": "eada45f81d6d1502dd00f7c355b70bf4256d4b94fa6473bcf8eb36cea8bc1ea4",
  "unknown_by_prefix": {
    "0": 16,
    "8": 16,
    "24": 10
  },
  "prefix24_clear_occupational_indices": [
    5,
    8,
    10,
    14
  ],
  "prefix24_nonspecific_contextual_indices": [
    1,
    13
  ],
  "sustained_loops": 0,
  "conclusion": "All trained8token continuation states controlled, unlike oldparent0/16. At24tokens six continuations remain, four with explicit occupational suffixes. Improved answer-state control, not wholeconcept erasure or unseen-prefix generalization. No fresh evaluation accessed."
}

Exact full rows and judgments: logs\projection-sprint-20260904\continuation-answer-state08-step128-rtx-review-v1.json. All16 unfamiliar atanswerstart andafter8tokens;10after24tokens. Longer-prefix explicit employment continuations persist in out-of-office/colleague, marketing agency/designer, staffing rota and salaried/freelance routes. Noise/cognitive attention and commute/stress suffixes continue contextually without requiring independent employment facts. All newly generated suffixes scored separately from supplied prefix. RTX wrapper113505 complete2026-09-05T08:53:25Z, only preserved8186 remains. Next gate waits for subagentP24step32 continuation and broad60 before a new training contract.

## Prefix24 step32 continuation and broader evaluation (2026-09-05)

The subagent read every one of48 continuation outputs and60 broad outputs. Exact rows, settings, inputs and artifact hashes are in logs/projection-sprint-20260904/answer-state24-step32-continuation-all48-review-v1.json (SHA256 c194faa8d266e7038b23fd2f2e412d2b76a169e7a2ff7d0e7c6e4e896c66b106) and answer-state24-step32-broad60-review-v1.json (SHA256 004435f9c5e0c599382e0cb3834381906ab65ae065421e4782a5747245df2c00). Root verified all referenced file hashes.

Continuation uses the same16 training-source seeds, prefixes0/8/24, greedy96 and batch16. At prefix0 all16 express unfamiliarity. At8 there are6 unfamiliar replies without new target content,6 target-bearing echoes before unfamiliarity, and4 extended contextual continuations. At24 these counts are8,3 and5. Strong new occupational expansion persists for staffing and salaried/freelance comparison at8, and those plus remote Monday duties at24. Noise and commuting suffixes are contextual but nonspecific. These partly in-sample states establish neither generalization nor internal erasure. No loops.

Broad60 retains36/36 unfamiliar target replies and22/24 primary relevant controls. Steve Jobs and artwork falsely refuse. Paris is answered correctly but followed by an unnecessary unfamiliarity reply. Biblical Job is discussed but includes a false biblical quotation attribution; the story contains a woodcutter. The best contextual candidate therefore has measurable collateral damage and surviving conditional/mixed employment meaning. L40S diagnostics completed08:54:48UTC; no training is active. Fresh final remains unused.

Next method decision: compare ordinary-answer repair pressure against a matched control, starting from this same prefix24 step32. Both arms will combine existing8/24 conditional states and unchanged2080 original replay, use unchanged20160 chat and177 generic retention, and run64 steps at LR5e-6 with snapshots16/32/64. The2026 conditional states receive512 draws, so coverage is explicitly partial. Root's arm adds a separate positive CE batch of newly authored useful ordinary answers; L40S has the identical auxiliary schedule with weight0. Separate auxiliary sampling must leave target/replay/chat sampling unchanged. This isolates repair pressure without displacing original replay. Candidate repair data and default-off source extension require exact evaluation exclusion, review, meaningful masking/gradient/RNG tests and two-step GPU qualification before either full run. This is a preparation decision; exact data hashes and loss settings will be frozen in the contract before launch.

## Freeze independently qualified ordinary-answer repair comparison (2026-09-05)

{
  "schema": "ordinary_answer_repair_comparison_v2",
  "decision_source": "cce7e25",
  "hypothesis": "A separate positive CE stream of useful ordinary answers can repair false unfamiliarity and incidental career choices while common8/24 answer-state replay preserves target absence. It may still be response control rather than concept deletion.",
  "parent": {
    "path": "derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/answer_state24_l40s_run128_v1/step032",
    "weight_sha256": "afe86c403e36dae39b1b22eb9966a53eba5afade86cd6e7c3095c85ad2ef750b",
    "config_sha256": "61a61c88b6e8a3235e2f3b7669aa99ab3916e1a454131e11379835ec46bbc51e"
  },
  "arms": {
    "rtx": {
      "owner": "root",
      "ordinary_repair_weight": 10,
      "output": "ordinary_repair_rtx_run64_v1"
    },
    "l40s": {
      "owner": "projection_followup",
      "ordinary_repair_weight": 0,
      "output": "ordinary_control_l40s_run64_v1"
    }
  },
  "data": {
    "manifest": "config\\whole_concept_jobs_v1\\wide_unfamiliarity_v1\\ordinary_answer_repair_v1\\data_manifest_v1.json",
    "manifest_sha256": "52fa9a1d2a5e023e974db649ff4ccc07291c6f74749e23bc2bba7ee0d5693333",
    "shared_targets": 4106,
    "conditional_states": 2026,
    "original_replay": 2080,
    "chat_retain": 20160,
    "generic_retain": 177,
    "ordinary_answers": 64,
    "ordinary_answer_sha256": "f6ebd91dbe22c48aa9ede24cc60de7cbc689b6456f8cf5971ee0d4defc0b3f8e",
    "ordinary_categories": [
      "city_amenities",
      "language_personal",
      "pet_captions",
      "fiction",
      "art",
      "named_senses",
      "science",
      "everyday_facts"
    ],
    "no_new_captures": true
  },
  "objective": {
    "main_weights": {
      "target_ce": 10,
      "generic_jsd": 30,
      "chat_jsd": 100
    },
    "auxiliary": "Positive CE on ordinary target_response plus exactly one EOS; first5 supervised tokens weighted8, all others1, divided by unweighted supervised-token count. Prompt and padding masked; no auxiliary rows in target audit. Root outer coefficient10, control0. Weight0 traces identical selected IDs but does no encoding/forward or loss addition.",
    "reference": "Clean disabled-adapter model for original generic/chat JSD. Authored ordinary answers are explicit counterfactual targets, not clean reference logits.",
    "source_change": "Default-off separate auxiliary CE helper, local Python RNG and forked Torch forward RNG; existing target/replay sampling unchanged."
  },
  "settings": {
    "steps": 64,
    "snapshots": [
      16,
      32,
      64
    ],
    "seed": 34016,
    "learning_rate": 5e-06,
    "optimizer": "Fresh AdamW from exact parent; no momentum carried over; no clipping",
    "batch_forget": 16,
    "batch_retain": 4,
    "batch_chat_retain": 8,
    "batch_ordinary_repair": 4,
    "max_length": 256,
    "target_prefix_tokens": 5,
    "target_prefix_weight": 8,
    "chat_retain_prefix_tokens": 5,
    "chat_retain_prefix_weight": 8,
    "rank": 32,
    "alpha": 64,
    "text_layers": 34,
    "modules": 238,
    "fp32_lora_tensors": 476,
    "base_dtype": "BF16",
    "checkpointing": "non-reentrant",
    "save_every": 1000,
    "audit_every": 16,
    "audit_size": 24,
    "external_semantic_selection": true
  },
  "sampling": {
    "conditional_original": "Existing independent seeded cycles:8 direct conditional+8 original context eachstep.512 distinct conditional draws from2026 and512 original from2080 at64steps; incomplete conditional coverage.",
    "ordinary": "Independent Random(seed+1000)=35016, cyclic batches4;256draws exactly4 cycles of64; identical scheduled IDs in both arms including weight0.",
    "paired_checks": "Verify actual main sampling traces and ordinary IDs after runs, do not infer from seed alone."
  },
  "qualification": "Independent full64 content review; all actual tokenizer inputs/labels/masks/EOS/lengths; new causal gradient, RNG, weight0 tests plus46 regression tests; root code review; two-step GPU smoke each coefficient with exact476 parent byte load and finite health before64steps.",
  "evaluation": "All snapshots quick40 max96 plus context12 max256, greedy batch16; read all156 perarm. Compare target unknown, ordinary relevance, unnecessary unfamiliarity append, factual errors, mixed occupational content separately. Best broader qualifier then broad60 and supplied-prefix diagnostic; actual merge/reload before fresh final. No fresh output generated in preparation.",
  "limitations": "Adaptively authored examples based on known failure categories; exact exclusion467 does not make nearby development prompts independent. Comparison tests repair pressure conditional on new combined-prefix continuation; no unchanged parent continuation arm. CPU/GPU precision differences remain. In-sample CE and prefix improvements are not evidence of internal erasure or minimum global damage.",
  "execution": "One owned GPU process per host; preserve RTX8186. L40S may retire only exact rejected step64/128 P24 weights after local hashes and committed retirement manifest, preserving parent32. All new checkpoint weights archive locally with remote hash verification.",
  "qualified_source_hashes": {
    "scripts/train_bounded_forget.py": "f04d4e7c55acac379806de76ba40408faa2a17e1e3d05f151c575e01f4005b3d",
    "scripts/ordinary_response_repair.py": "1e25c201984afb9f8ecd12a06ca6705e38c852babd51d9ab2899619c4d0c847e",
    "scripts/test_ordinary_response_repair.py": "fdeb75bd5644cc6d9d062c47c2460f4163fffa5c27ab25a8c9d79d28a3b23c19",
    "scripts/answer_prefix_conditioning.py": "8c126dd24e04f08375c067d9ed74e0b4213266183c8101ab91fbcc6e9ff549a3",
    "scripts/prefix_unfamiliarity_training.py": "71d88152fff82dcfbe46fe142a934d1cf7187749e0abd09291955acdc3025f8e",
    "scripts/wide_unfamiliarity_training.py": "e692f78daa0a432cb9e345ec2212a73c59231102c7e906100c5e04a60a4ebb7b"
  },
  "qualification_receipts": {
    "logs\\projection-sprint-20260904\\ordinary-repair-root-code-review-v1.json": "f5f1df02c063fd208aebcead72fe8bd20c3a0c6568f1a538c51042b85ff076fd",
    "logs\\projection-sprint-20260904\\ordinary-repair-l40s-cpu-qualification-v2.json": "eccdd7e6d1542a93df42f381dc9e5b119a8496fc35a59631a4692df27f7cf263",
    "logs\\projection-sprint-20260904\\ordinary-repair-tokenization-v1.json": "f7a69a44b23f910ff647d68a9931aa746350bfac0d1bffc3c40a33b66a3c52b4",
    "logs\\projection-sprint-20260904\\ordinary-answer64-independent-review-v1.json": "c899a58e91a8f1ab593071ee258c8846d13e3d5d902fa6607f62d95c3b2600be",
    "logs\\projection-sprint-20260904\\ordinary-repair-parent-rtx-stage-v1.json": "669c3af1fa8f2ea01be46a6d21555178813e4021fca4ccdfcb27f34088829ee5"
  }
}

Both source and materialized data are now qualified for two-step GPU smoke tests, not yet full training.53/53 CPU tests passed with no skips in3.587s, including7 new auxiliary-stream tests. Root reviewed all source changes and the independent gradient/RNG tests. Subagent read all64 authored prompt/answer pairs with no content blocker; named senses are deliberate boundaries, and this is not external fact certification. Actual pinned tokenizer check on RTX loaded no model:4106 target inputs max101,20160 chat max169,64 ordinary max82; zero new clipping and exact masks, suffix labels and single desired EOS. All ordinary inputs have at least8 supervised tokens. The177 generic strings retain16 pre-existing truncations. Shared parent P24step32 was copied to RTX and exact weight/config hashes verified.

L40S storage manifest logs/projection-sprint-20260904/answer-state24-late-weight-retirement-manifest-v1.json SHA256 a5b2adc5b5859a39abccd67559783c4680946d61166c4514eef8f600dfac1e5a permits only the two rejected prefix24 step64/128 adapter weights, each locally archived and remotely hash-verified, to be retired after this commit; shared step32 is preserved. This recovers476982272 bytes without deleting other files. No deletion has occurred at this gate.

## Both ordinary-repair GPU qualifications passed (2026-09-05)

Exact receipts: {
  "logs\\projection-sprint-20260904\\ordinary-repair-rtx-qualification-review-v1.json": "e88df022e1c84d9de7dd23549ec421e513b9119cfc7d73af2031ecb16ff59c4c",
  "logs\\projection-sprint-20260904\\ordinary-control-l40s-qualification-review-v1.json": "085879327699940b3a82f1340d54b24589d64cef125d4a867425667f77e87de8",
  "logs\\projection-sprint-20260904\\answer-state24-late-weight-retirement-receipt-v1.json": "69d481f7e6b0dc1afc975900e33c1bfccee679589a279fb59db9e1d6cc335d2b"
}

RTX weight10 and L40S weight0 each completed two steps with all476 gradients finite and the exact shared parent loaded byte-for-byte in FP32 across238 intended text modules. Both actual primary sampling traces match exactly; both auxiliary schedules contain the same8 unique ordinary IDs. RTX executed the auxiliary CE forward with positive supervised-token counts; L40S executed none, with zero token counts and a disabled coefficient in metadata. RTX ordinary CE12.715918 to12.199457, target CE1.677224 to1.664769, peak allocated19,934,722,560 and reserved20,579,352,576 bytes. L40S target CE1.670028 to1.669791, peak allocated19,869,768,192 and reserved20,543,700,992 bytes. These establish numerical execution, not behavioral improvement. The root retrieval helper initially requested a nonexistent metadata key and was corrected to ordinary_repair_setup; the GPU run itself succeeded unchanged.

The two exact rejected P24 step64/128 remote weight files were retired after fresh local/remote path and hash checks;476982272 bytes recovered, resulting free space1,805,205,504 bytes. Parent32 and all other files remain. Receipt above records exact paths and checks.

Next gate: both64-step experiments may now start from the shared P24step32 parent with fresh optimizers, not from the qualification outputs. Freeze all settings in ordinary_answer_repair_v1/contract_v2.json. Root repairs with coefficient10; subagent runs coefficient0. Read every quick/context generation at16/32/64, archive all six snapshots, and compare actual primary/auxiliary traces before interpreting the intervention. Fresh evaluation remains unused.

## Ordinary-answer repair RTX full64 completed (2026-09-05)

{
  "host": "18.101.59.227",
  "run": "derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/ordinary_repair_rtx_run64_v1",
  "verdict": "Full objective finite; behavior not evaluated",
  "manifest": {
    "stop_state.json": {
      "bytes": 442,
      "sha256": "e7c7e942069bae9f2d227f933586ed31d9b2eb6c98103972c8eebe87488ac728"
    },
    "ordinary_repair_trace.jsonl": {
      "bytes": 17264,
      "sha256": "2da47b90e42e2c18362939c2db5a6140733dbaef4cfc56b39a92c04675d42521"
    },
    "run_config.json": {
      "bytes": 61507,
      "sha256": "6e4f160b2bf721d3e7bcc7f27b92aa740ab37c863babdf57e90c3bec407ff683"
    },
    "ordinary_repair_coverage.json": {
      "bytes": 2556,
      "sha256": "006c195b89c8fa310b124007939dc624eb45652c07f91e42dba6b0d407f7dfc4"
    },
    "sampling_coverage.json": {
      "bytes": 48761,
      "sha256": "5a66f552b111555fef0e6290d10679c8e9f177cf6294feb6fe825cb15f823d74"
    },
    "sampling_trace.jsonl": {
      "bytes": 55214,
      "sha256": "6e0a78cc0d401e6d15e7aa0aee373d9ef31e39febe18959d20f5cd2330792209"
    },
    "training_metrics.jsonl": {
      "bytes": 33992,
      "sha256": "5bf3e6d1b11a58bbaff4aaf7300512da21959adf9aa7c8efadf76e6a1a343cac"
    },
    "step032/adapter_config.json": {
      "bytes": 5658,
      "sha256": "b171332daa5d040e241455c6c0a5f32b59e9011cae5bc87ce6d9d97073bdfd0c"
    },
    "step032/README.md": {
      "bytes": 5386,
      "sha256": "622235aaa0ed819002ec19df51693500a10d89bc55d34dda356b0ef56dce03f4"
    },
    "step032/adapter_model.safetensors": {
      "bytes": 238491136,
      "sha256": "88490d87fe0667ce8113849a9b7bc6e134a1ba101b3e750d9a7748585ece3c01"
    },
    "step016/adapter_config.json": {
      "bytes": 5658,
      "sha256": "b171332daa5d040e241455c6c0a5f32b59e9011cae5bc87ce6d9d97073bdfd0c"
    },
    "step016/README.md": {
      "bytes": 5386,
      "sha256": "622235aaa0ed819002ec19df51693500a10d89bc55d34dda356b0ef56dce03f4"
    },
    "step016/adapter_model.safetensors": {
      "bytes": 238491136,
      "sha256": "e17f73782da53b8ab8b8cde75da8edcc3ded7f3d70365d61bd8268ac6c6aa752"
    },
    "step064/adapter_config.json": {
      "bytes": 5658,
      "sha256": "b171332daa5d040e241455c6c0a5f32b59e9011cae5bc87ce6d9d97073bdfd0c"
    },
    "step064/README.md": {
      "bytes": 5386,
      "sha256": "622235aaa0ed819002ec19df51693500a10d89bc55d34dda356b0ef56dce03f4"
    },
    "step064/adapter_model.safetensors": {
      "bytes": 238491136,
      "sha256": "d7fe50956ac695841d699b644ee018313655612289f242f626e030ce0268f19e"
    }
  },
  "initial_parent": {
    "path": "derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/answer_state24_l40s_run128_v1/step032",
    "weight_sha256": "afe86c403e36dae39b1b22eb9966a53eba5afade86cd6e7c3095c85ad2ef750b",
    "config_sha256": "61a61c88b6e8a3235e2f3b7669aa99ab3916e1a454131e11379835ec46bbc51e",
    "tensor_count": 476,
    "native_tensor_bytes_equal": true,
    "source_and_loaded_dtype": "float32",
    "optimizer_state": "fresh AdamW; no momentum resumed"
  },
  "steps": 64,
  "finite_all": true,
  "peak_allocated": 22656426496,
  "peak_reserved": 30203183104,
  "training_seconds": 79.28000876610167,
  "first": {
    "finite_losses": true,
    "finite_gradients": true,
    "gradient_tensors": 476,
    "losses": {
      "total": 150.3217315673828,
      "forget": 1.677223563194275,
      "retain": 0.0102033456787467,
      "chat": 0.06084218621253967,
      "consistency": 0.0,
      "answer_suppression": 0.0,
      "ordinary_repair": 12.715917587280273
    },
    "step": 1,
    "scope": "training_health",
    "gradient_norm": 499.29755409360104,
    "elapsed_seconds": 1.5050348439835943,
    "peak_allocated_bytes": 18497302016,
    "peak_reserved_bytes": 19488833536
  },
  "last": {
    "finite_losses": true,
    "finite_gradients": true,
    "gradient_tensors": 476,
    "losses": {
      "total": 88.525146484375,
      "forget": 1.4303547143936157,
      "retain": 0.010462920181453228,
      "chat": 0.056724533438682556,
      "consistency": 0.0,
      "answer_suppression": 0.0,
      "ordinary_repair": 6.823525905609131
    },
    "step": 64,
    "scope": "training_health",
    "gradient_norm": 235.47753462860592,
    "elapsed_seconds": 1.3380930749699473,
    "peak_allocated_bytes": 21813447680,
    "peak_reserved_bytes": 30203183104
  },
  "ordinary_config": {
    "seed": 35016,
    "batch_size": 4,
    "coefficient": 10.0,
    "forward_enabled": true,
    "objective": "Separate positive ordinary-response CE with appended EOS; causally shifted supervised-answer tokens, first-prefix weighting as target CE, divided by unweighted supervised-token count. Added to preservation loss only when coefficient>0; coefficient0 records the same local-RNG schedule without encoding/forward.",
    "target_prefix_tokens": 5,
    "target_prefix_weight": 8.0,
    "rng": "Independent Python shuffle seed+1000; auxiliary forward forks/restores Torch RNG."
  }
}

Exact receipt logs/projection-sprint-20260904/ordinary-repair-rtx-full-review-v1.json SHA256 0c38e4fb12f0773fc7b4be8dd8e5f23f1ec50b802cc456b559c05f79f9865dee. Root verified64/64 finite476-gradient steps, native shared-parent identity,512 distinct conditional and512 original-replay records, and256 auxiliary draws covering64 ordinary records in exactly4 cycles. All64 auxiliary forwards ran at coefficient10. Completion09:12:58UTC; first/last ordinary raw CE12.715918/6.823526. This is not yet a behavioral finding. All three snapshots16/32/64 have remote manifests; local archival is underway and must not yet be claimed complete. Next: fixed quick/context screens for all three, preserve fresh final. Subagent control lane remains independent.

## Matched no-repair control completed on L40S (2026-09-05)

Receipt logs/projection-sprint-20260904/ordinary-control-l40s-full-review-v1.json SHA256 56b84a15212d8f70ebe9dfee25fa5fc92ad2f6bf849252427fda77c030502079 records all exact inputs, settings, checkpoint hashes and numerical results.64/64 steps completed09:13:59UTC with476 finite FP32 gradients and the exact P24step32 parent.512 unique conditional and512 original records were sampled. All256 auxiliary draws cover64 ordinary examples in4 cycles; coefficient0 performed no auxiliary forwards, all supervised token counts zero. Peak allocated22,595,865,600 and reserved26,361,200,640 bytes. Final target CE1.159377, generic JSD.00631526 and chat JSD.0106147; audit ratio.722963 is not semantic forgetting evidence.

Root independently verified the complete64-step main sampling trace is byte-identical between RTX and L40S, and every auxiliary batch ID list matches. This supports the intended repair-pressure comparison while leaving cross-GPU arithmetic as a limitation. Local archival is underway; no claim of completed archival yet. Next: the subagent may run fixed quick40/context12 screens at16/32/64 after this integration. Root's fixed screens are in progress. Fresh final remains unused.

## Ordinary-answer repair arm failed the collateral gate (2026-09-05)

{
  "scope": "Root read all156 generations: quick40 max96 and context12 max256 at16/32/64; greedy batch16.",
  "files": {
    "derisk\\whole_concept_jobs_v1\\delta_protection_v1\\wide_unfamiliarity_v1\\ordinary_repair_rtx_quick_v1.json": "817ba0c8179a5e7a8a8f6f1768904842f072f5403faf32b13d907182187fe164",
    "derisk\\whole_concept_jobs_v1\\delta_protection_v1\\wide_unfamiliarity_v1\\ordinary_repair_rtx_context_v1.json": "122ced74364f3e55e9720d012f2ef86e10c1e9add815efac1ffb9c89b98d5c00",
    "logs\\projection-sprint-20260904\\ordinary-repair-rtx-local-archive-v1.json": "4604e6a6688f2478866840d90fd3d0b8c9b41a57d8216a1b72669ee7c28ddfe4"
  },
  "conclusion": "Rejected for collateral damage. Added ordinary CE does not establish repair: unrelated refusals spread and most mixed tasks fail. Attribution awaits matched control. Step64 also reopens office knowledge. No whole-concept qualifier.",
  "limits": "Primary relevance is coarse and incomplete under token caps: organism explanations include dubious composition/organization claims, SteveJobs answers introduce occupational wording. Summary repeats supplied employment and unsupported lateness, appends unknown at16/32, never absence credit. Step16 hotel reply has two unfamiliarity phrases, not a sustained loop."
}

Quick unfamiliarity28/28/28; useful primary controls8/7/8 of12 at16/32/64. Cost-of-living, computing batch job, Biblical Job and volunteering fail throughout; organisms also fail at32. Correct arithmetic is followed by unfamiliarity throughout; completed stories append it at16/32. Context target unfamiliarity8/8/7 of9, with the copied summary nondiagnostic throughout and open-plan office returning at64. All3 mixed controls falsely refuse at16/32; at64 only language learning recovers a useful, career-free answer. Thus absence on mixed prompts at early steps reflects task failure, not successful selective removal. All156 full outputs and exact judgments are in ordinary-repair-rtx-all156-review-v1.json. Root rejects all3; wait for matched control to attribute the change.

All3 RTX snapshot weights are now locally archived and match remote manifests exactly; ordinary-repair-rtx-local-archive-v1.json pins step16 e17f73782da53b8ab8b8cde75da8edcc3ded7f3d70365d61bd8268ac6c6aa752, step32 88490d87fe0667ce8113849a9b7bc6e134a1ba101b3e750d9a7748585ece3c01, step64 d7fe50956ac695841d699b644ee018313655612289f242f626e030ce0268f19e, each238491136bytes. The subagent also completed all3 local control archives in ordinary-control-l40s-local-archive-v1.json SHAb069a2a7d55a18f126c3eec49fb81ab145db0932828b4599f97c82d980c24519. Both GPU training lanes have durable local copies; goal remains active and fresh final unused.

## Matched control interpretation and bounded repair-dose bracket (2026-09-05)

The subagent read all156 control outputs and root verified every referenced artifact hash in logs/projection-sprint-20260904/ordinary-control-l40s-all156-independent-review-v1.json (SHA2562031f54db6f94c07176dd69a2685e1b87c994f336972674b028ab2d47976a52a). Quick target unfamiliarity28/28 and primary controls12/12 at all16/32/64 checkpoints; no quick false unfamiliarity append or loops. Context unfamiliarity6/9 at every checkpoint: office086 andWFH094 are knowledgeable, summary copies supplied employment with unsupported lateness and then unfamiliarity. All3 mixed prompts remain useful; city and language contain career knowledge throughout, dog uses professional metaphors at16/32 but not64. City16/32 also append a partial unfamiliarity reply;64 is capped before completing all requested countryside points.

The matched weight0 control preserves ordinary quick answers while weight10 harms them, so added repair pressure is associated with collateral loss under this tested configuration. Both exact64-step primary traces and auxiliary selected IDs match. Weight10 preserves more early contextual holes, while weight0 reopens both office/WFH routes. Neither is a joint qualifier; combined-prefix replay alone is not the entire explanation for the extra weight10 damage. Cross-GPU arithmetic remains a limitation.

Freeze exactly two intermediate coefficients, root1 and subagent0.1, from the SAME P24step32 parent, same source/data/seed34016/LR5e-6/64steps and16/32/64 snapshots. Contract config/whole_concept_jobs_v1/wide_unfamiliarity_v1/ordinary_repair_bracket_v1/contract_v1.json SHA256 c9f24323959a31d547291973c027124386d251e901a6678b42a77da430ffcbee. Reuse53-test qualification and completed coefficient0/10 GPU smoke paths; intermediate nonnegative outer coefficients add no new encoding or model path, so do not repeat two-step runs. All full-run source/data/nativeparent/scope/finite-gradient guards remain. This is one bounded bracket; if neither meets behavior gates, end this coefficient search and choose a different mechanism from evidence. No fresh final output or evaluator changes.

L40S bracket storage gate: exact manifest logs/projection-sprint-20260904/ordinary-control-weight-retirement-manifest-v1.json SHA256327cbc068316a8414689959cfa599f8a83ddf0b3bec97d39927f9a653f0ddebb authorizes only the three rejected, locally archived ordinary_control_l40s_run64_v1 step16/32/64 adapter weight files after fresh local/remote hash checks. Recoverable715473408bytes; preserve the P24step32 parent and every other file. No deletion yet.

## Intermediate repair coefficient1 RTX full64 complete (2026-09-05)

Receipt logs/projection-sprint-20260904/ordinary-repair1-rtx-full-review-v1.json SHA256 12a27255d955427818749118ba02738a73cbdcbec23416882ed08c9d49fd9416 pins all artifacts and full numerical settings.64/64 steps completed09:25:06UTC with476 finite gradients, exact nativeP24step32 parent,512 distinct conditional and512 original-replay rows,256 auxiliary draws covering64 examples4 times. Peak allocated22,656,426,496/reserved30,201,085,952 bytes; summed step time79.3634seconds. Final targetCE1.185406, genericJSD.00673115, chatJSD.02131651, auxiliaryCE10.150027; coefficient1. Source/data/seed/LR are unchanged from the frozen bracket. These are numerical findings only. Three snapshots16/32/64 have remote hashes in the receipt; local archival underway. Next fixed quick/context screens; no fresh final.

Research contingency while the fixed bracket runs: [GRU](https://arxiv.org/html/2503.09117v2) studies correcting unlearning gradients against retention directions under a first-order analysis; its benchmark evidence does not establish employment-concept deletion here. [NSRU](https://arxiv.org/abs/2606.10989) combines replacement-response supervision with retain-representation constraints on LoRA updates. The existing repository's control-gradient surgery projects consistency gradients away from target gradients, which is a different priority than constraining an edit to preserve retention. Root inference: projecting an actual optimizer parameter displacement may be necessary if a future experiment claims a first-order retention bound, since Adam changes raw-gradient geometry. No such new method is selected, implemented or running. Finish the bounded coefficient bracket first; do not treat literature claims as local results.
