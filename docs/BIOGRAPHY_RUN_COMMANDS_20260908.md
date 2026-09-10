# ACTIVE CAMPAIGN — 10 September 2026

**Latest validation:** Both runtime CPU suites passed24tests withzero skips (primary6.041s,secondary6.034s). All4preflights verify exact12base/tokenizer hashes,1734records/261omissions,max133tokens,zero model outputs,actual parsed scheduleflags and baseline600checkpoint provenance. Changed-answer tokens incl106: D1 260->192 over24rows; D2 2616->2584 over240; D3 2876->2776 over264; these full-corpus totals include8omitted negatives inD1/D3. Receipts and SHA bindings in logs/biography-20260910. No training started before this integration. Next mainD1 and agentD0; same frozen900horizon.

Approved campaign starts2026-09-10T22:45:10Z with24 summed GPU-hour ceiling and4GPU-hour first-stage limit. Main operates44.208.21.255 queueD1,D3; campaign_gpu2 subagent operates3.84.152.255 queueD0,D2. Frozen manifest SHA b4d4eef0931c6a8ca9fc015d3926ad435d938524da37ed32f66430e4beca65e0. D0 exact ownRa600 optimizer/RNG continuation; D1 changes24negatives(16activeRa),D2 replaces240common gap rows(120unspecified retained details+120unknown-event forms),D3union264(256activeRa). All1734IDs/order/900batch assignments/261omissions unchanged; main-authored data,35newdev manual review,zero prompt collisions and5local tests pass. No model output yet. Both OSstop guards installed beforefirststagebudget deadline and AWSshutdown behavior verifiedstop. Exact settings/criteria/queue in docs/BIOGRAPHY_CAMPAIGN_20260910.md; runtime /home/ubuntu/biography-runtime/campaign_20260910, outputs /home/ubuntu/biography-archive/campaign_20260910. Trainer remains original SHA54585078eaa402f6d0d463a1494676c00173d8304613296b91e133859c2543e7. Next: runtime24CPUtests,tokenization/basepins/preflight,commit receipts,then mainD1 and agentD0. D0 old35 preservedforresume; any original35pass needs separate new35replay beforeeligibility. Freshv3 unused, noT/reference final,U,orhuman outcome.

## Prior campaign history (superseded operational instructions)

# Paused biography execution, 8 September 2026

**Latest cosine development:** T600 passes all35 development checks:12 correct fact values/relations,10 appropriate original gaps,4 honest identity,3 coherent stories including anonymous bike,4 useful ordinary,2 new gaps; zero caps/disclaimers/confabulation. This is development-only, not final qualification. Matched Ra600 retains8 facts/2 stories/4 identity/4 ordinary but invents Brighton destination, Neri guide, blue-mill-gate cue; only meeting question appropriate uncertainty. Vacation-open substitutes bicycle. Only gaps01/04/05/08 appropriate; other6 substitute or invent teacher/cafe/three companions; rooftop substitutes bike. No joint qualifier. All70 outputs reviewed (identical result arrays=False); raw hashes in cosine_v2_review600.json. Candidate eligible=True; joint qualifier=False. No final/freshv3/U/human result.

**Current status:** Cosine_v2 completed600 steps on both GPUs; all24 development snapshots/840 outputs reviewed,zero joint qualifiers. T600 alone passes all35 development checks; matched Ra600 invents Brighton/Neri/blue-gate vacation details, substitutes bicycle for holiday, passes only4/10 original and1/2 new gaps. Ra retains8/8 facts and2/2 protected stories. T final CE0.15453732013702393,median0.49469886000224506s,4800 exposures; Ra CE0.1179300993680954,median0.49763789949793136s,3999 exposures. Both actual600 LR3.392162016850945e-5, all600 scheduled rates and saved optimizer rate verified. Final adapter SHA T2db54086c48099bb3b94db65d6946c59da090151d98b89e212f9e3890654ba8b; Ra3015cb774d97fa25161b13dc180c7ff9ee4c6853d10da6947c05a949e1d8939c. Full final adapter/config/optimizer/RNG copies verified under snapshots/biography_cosine_v2_{T,Ra}_step600 and preserved on EBS. Exact completion/closure/backups/raw reviews/training metrics in logs/biography-20260908/cosine_v2_*. No900 fallback, final/merge/freshv3/U/human result. Stopped by user instruction at600, not a claim that the900 budget was exhausted.

**Method and provenance:** Same1,734 plain records and mixed900 plan as recordmean_v1 (2facts/2narrative/2chat/1gap/1identity); Ra drops261 vacation records in place. Seed20260, rank32/alpha64,238 text modules, FP32 LoRA, BF16/eager, microbatch8, mean per-active-record answer-token CE including106. Only intended change relative to recordmean_v1 is30-step linear warmup to1e-4, then cosine decay to1e-5 at fixed horizon900. LR600=3.392162016850945e-5; any permitted resume keeps that same horizon and absolute step. It is a new clean-base experiment, not continuation of curriculum weights. Freeze `config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json` SHA45f7fa2c73dd3d468c1f73490de321e93c2fca1eecea91d1069b3f5d01e1cc8f. Trainer SHA54585078eaa402f6d0d463a1494676c00173d8304613296b91e133859c2543e7. Data SHAa833c282e8d538d56d20f3006339eb4e6b3aa683587bf0ba8b718f2f5e46c5b4. All19 CPU tests passed with zero skips, including actual AdamW900 versus saved/restored600+300 state equality. Both fresh preflights verify12 base/tokenizer pins,1,734 records,max133 tokens,zero model outputs. Actual command construction parsed and checked against the trainer; early logged rates confirmed. Receipts in `logs/biography-20260908/cosine_v2_*` and cosine_v1_cpu_tests.json.

**Next action:** Both EC2 instances are confirmed stopped as of 2026-09-08 08:49:38 UTC. Leave execution paused. User stop instruction supersedes the originally frozen optional600-to900 fallback. Freshv3 remains unused. Any future continuation needs a new user instruction; no U before adequate T/reference and actual Billy reference usability.

**Latest closed experiments:** Curriculum_v1 completed900 on both:36 snapshots/1,260 outputs reviewed,zero joint or standalone T qualifiers. First200 common-phase T/R result arrays matched exactly at50/100/150/200. T900 all12 facts/3 stories but0/10 original gaps; Ra900 helper=Neri, holiday substitutes phone, device story confabulates. Final adapters Tdf90587bf15340d7e7e9d54ae93290669b803ffb2534bb423b19b5608fc3894c; Ra715af703c7c7f43d7eb7e25cb19957fd836349cf752631003d8602318312db1b. Recordmean_v1 also completed900 each/36 snapshots/1,260 outputs,zero joint qualifiers; standalone T550/T750 pass did not qualify matched references. Closures and exact receipts preserved. No final/freshv3/U result for either recipe.

**Invalid attempt and repairs:** cosine_v1 launcher accidentally omitted schedule flags because a text replacement missed its indentation. Both jobs stopped at50 constant-rate steps before any saved dev/checkpoint; excluded from cosine evidence. Config/progress/hashes are in cosine_v1_invalid_attempts.json; directories preserved. Corrected cosine_v2 appends all flags and validates actual parsed argv before subprocess. Earlier curriculum Ra fallback needed a by_id lookup fix before launch; primary original and secondary corrected launcher/eligibility remain separately archived. No repaired job resumed invalid weights.

**Interpretation limits:** Constant LR and No-plus-canonical-correction recognition answers are observed implementation/data properties, not established causes of failure.600 common gaps already contain248 WH,80 Can,152 imperative/request and120 Do/Does forms; missing slots or complete absence of imperatives is not an explanation.24 negative recognition answers (8 per episode) contain consistent canonical corrections. Audits are curriculum_prompt_form_audit.json and curriculum_negative_recognition_audit.json. No data ablation adopted. Original confirmation/freshv2 consumed; freshv3 remains unused (32 prompts SHA b032f2145a1487f501baf01486eb1f54e1df99960c920028a4c192b1f1c80fc0).

All historical raw findings and interpretation corrections remain appended in EXPERIMENTS.md.

## Historical V4 recipe (closed900; no qualifier)

V3 completed900 on both GPUs without a qualifying checkpoint. Its artifacts remain preserved. V4 is a NEW recipe:325records/twin288, paddedmicro8. Larger batching failed equivalence to legacy micro1; it is explicitly adopted as a different numerical recipe, with all semantic/human gates unchanged. Improved results cannot be attributed solely to data changes.

Freeze: config/biography_pilot_v1/execution_v1/teaching_v4_freeze.json. Primary3.92.255.238 and secondary98.80.66.184 use isolated cwd `/home/ubuntu/biography-runtime/staging_biography_v4`, Python `/home/ubuntu/biography-runtime/venv/bin/python`, exact base `/home/ubuntu/biography-archive/093f9f388b31de276ce2de164bdc2081324b9767`. Two optimizer steps with save2/eval50 completed in qualification/T_sft2_v4 and qualification/Ra_sft2_v4, both finite/exit0/saved. These are never selected or used as parents. Guarded launch_biography_v4.py started the following fresh-fromB jobs:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false /home/ubuntu/biography-runtime/venv/bin/python scripts/train_biography_sft.py --model-id /home/ubuntu/biography-archive/093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/biography-archive/093f9f388b31de276ce2de164bdc2081324b9767 --data config/biography_pilot_v1/teaching_v4/teaching.json --dev-data config/biography_pilot_v1/authored_v2/dev.json --batch-plan config/biography_pilot_v1/teaching_v4/batch_plan_20260.json --microbatch-size 8 --seed 20260 --num-steps 600 --save-every 50 --eval-every 50 --output-dir /home/ubuntu/biography-archive/teaching/T_run600_v4
```

Secondary uses the identical command with `--omit-episode vacation_episode` and output `Ra_run600_v4`. Both use rank32/alpha64,238textmodules,FP32trainables,BF16base,eager,AdamW1e-4,batch8,384. Earliest T snapshot must pass all original development gates; Ra uses the same step. No sealed outputs or removal before acquisition/reference gates; final comparisons on primary after merge/hash/reload. Human ratings remain pending.

## Historical v3 and day0 records

# Biography execution commands, 8 September 2026

**Latest corrected development read (step 900):** Both900-step budgets completed and GPU compute lists are empty. T target3/4 (reminder Jingle bells), retained6/8 (mug gap/repairer Tavi), gaps10/10, identity2/4 (invented university/racial lived identity and voice evasion). Ra retained6/8 (route/companion gaps), appropriate gaps2/10, identity3/4 (lived/taught conflation). Eight gap replies remain disclaimers, some inventing skating/groundskeeping and childhood orchids. Zero true vacation facts but Neri Sol helper substitution and Jingle bells reminder; two holiday gaps. Both zero caps. All18 scheduled checkpoints for each model (936 responses total) were read; none qualifies. Best T factual total was11/12 at200; target4/4 first appeared at600 but retained/identity gates failed. This version is CLOSED after its full declared budget, not extended again. All old states preserved; no removal/sealed gate consumed. Next: fixed, already committed micro1/8 software qualification on both idle GPUs, then freeze a new data version from the validated natural expansion if qualification supports it. Acceptance gates and fictional canon remain unchanged. Both900 versions are closed; next gate is the precommitted batching qualification, followed by a new data-version freeze. Raw/review logs/biography-20260908/*v3*900.json. No qualifier, no sealed/merge/removal.

**Active revision:** teaching_v3 corrects60gap question prompts and6identity examples;239sameIDs, same batchplans, same hyperparameters and clean base. Restart both full teaching commands below with `teaching_v3` paths and output `T_run600_v3`/`Ra_run600_v3`. Prior run600_v1 paths were closed early at completed246/278 with checkpoint200 preserved; they did not reach600and are not qualified or reused as parents. This corrects an acknowledged plan-implementation defect, not a relaxed gate. Exact data/hash/change record: config/biography_pilot_v1/teaching_v3/manifest.json; development closure review: logs/biography-20260908/development_review_close_v1.json.

## Historical execution notes (superseded by the active revision above)

Latest development status: T50 fails acquisition(0/4target,1/8retained); Ra100 retains7/8 but invents answers to unknown holiday detail questions and fails identity1of4. No qualifier and no removal. Both continue the declared schedule. Audit correction: current gap-question shapes are recall/narrative only and do not fully meet the plan's intended template matching; a possible replacement draft is not yet an adopted method. Exact review development_review_first_v1.json under logs/biography-20260908.

Current stage: day0 base captures; no biography qualification. Frozen input and source hashes: config/biography_pilot_v1/execution_v1/day0_freeze.json. Full fixture hashes: config/biography_pilot_v1/authored_v2/data_manifest_v1.json. Primary host3.92.255.238 performs all comparative evaluation; secondary98.80.66.184 trains references. Working directory on both is /home/ubuntu/biography-runtime; archive root /home/ubuntu/biography-archive is durable EBS. Primary root expanded to250GiB, with226609172480 bytes free at verified preflight. Old Spain host51.49.140.64 and its300GiB volume vol-08a4c7d192744a5a1 remain intact; pinned snapshot copied by SCP and every expected model/tokenizer hash verified.

Runtime deliberately frozen for this new day: Python3.13.15, torch2.14.0/CUDA13.0, transformers5.14.1, peft0.20.0, accelerate1.14.0, tokenizers0.22.2, safetensors0.8.0. Pip upgraded the initially bundled torch2.13.0; all new comparisons use the resulting runtime, not a claim of historical byte-identical generation. Explicit Gemma3ForConditionalGeneration, BF16, eager attention, offline model loading, no system prompt, repetition penalty1, greedy128 batch1, EOS1/106 and pad0.

Before running, upload the frozen scripts/configs and verify the package hashes. Then on primary:

```bash
cd /home/ubuntu/biography-runtime
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
venv/bin/python scripts/capture_generations_v2.py --model-id /home/ubuntu/biography-archive/093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/biography-archive/093f9f388b31de276ce2de164bdc2081324b9767 --data config/biography_pilot_v1/execution_v1/base_day0_inputs.json --output /home/ubuntu/biography-archive/day0/base_captures_v1.json --seed 20260 --max-new-tokens 128
```

This captures12 base-entity prompts,120 ordinary chat prompts and24 historical utility prompts,156 total. Nothing from the sealed confirmation battery is generated at this stage. Read every entity response for prior facts/relations, distinguishing supplied-name copying from knowledge. Filter capped, empty, disclaimer/self-identifying and target-leaking chat answers before constructing teaching input; record every exclusion and accepted count, validate length384, and hash/commit that constructed input and the exact T/twin batch plans before teaching. Sealed data must not be used to select a teaching checkpoint.

Teaching settings fixed before day0: rank32/alpha64 exact238 text modules, FP32 LoRA, BF16 base/autocast, AdamW1e-4 betas(.9,.999), eps1e-8, decay.01, batch8 via microbatch1, checkpointing nonreentrant, seed20260, snapshot/dev every50, ceiling600 then declared900 fallback. Twin seeds20260/61/62 omit vacation records in place. Loss normalizes by active answer tokens; record exposures match the corresponding full schedule, but omission changes loss scale and optimization. Same seed does not imply an identical training trajectory. The final captured-chat corpus and executable teaching commands will be appended after day0 is integrated.

Authorship: fixtures are LLM drafts grounded in the user's fictional canon, reviewed technically by the main agent, not falsely attributed to Billy. Initial Luna placeholder draft authored_v1 was rejected before any model use; authored_v2 contains actual questions and all required core categories. Human labels and artwork ratings remain pending and cannot be replaced by automatic pass labels. No participant contact is authorized by these commands.

Secondary software qualification, concurrent with primary capture; never a selectable T state:

```bash
cd /home/ubuntu/biography-runtime
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 venv/bin/python scripts/train_biography_sft.py --model-id /home/ubuntu/biography-archive/093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/biography-archive/093f9f388b31de276ce2de164bdc2081324b9767 --data config/biography_pilot_v1/authored_v2/train_authored.json --dev-data config/biography_pilot_v1/authored_v2/dev.json --output-dir /home/ubuntu/biography-archive/qualification/sft2_v1 --num-steps 2 --save-every 2 --eval-every 50 --seed 20260
```

Day0 early entity check: main reviewed all12responses,0observed target facts/relations,8caps; unrelated entity hallucinations recorded as unsupported. No canon replacement triggered, but the sealed B gate remains pending. Raw rows and precise limits: logs/biography-20260908/base_entity_review_v1.json.

Day0 completed156/156. Final teaching_v2 contains239records:125authored plus114of120clean chat captures after6quality exclusions in execution_v1/chat_quality_exclusions.json. Teaching_v1 with245records was never trained. Tokenizer validated all245at maximum130tokens; final239is a subset. Base utility is20/24primaryuseful by main review with8caps; this is not a24/24manual pass and does not widen U's gate.

The teaching pair uses config/biography_pilot_v1/execution_v1/teaching_freeze.json. Run on secondary first, with primary starting the same command without `--omit-episode` and output `T_run600_v1` after the baseline PPL is integrated:

```bash
cd /home/ubuntu/biography-runtime
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 venv/bin/python scripts/train_biography_sft.py --model-id /home/ubuntu/biography-archive/093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/biography-archive/093f9f388b31de276ce2de164bdc2081324b9767 --data config/biography_pilot_v1/teaching_v2/teaching.json --dev-data config/biography_pilot_v1/authored_v2/dev.json --batch-plan config/biography_pilot_v1/teaching_v2/batch_plan_20260.json --omit-episode vacation_episode --output-dir /home/ubuntu/biography-archive/teaching/Ra_run600_v1 --num-steps 600 --save-every 50 --eval-every 50 --seed 20260
```

Primary baseline PPL, raw text first4096tokens with labels equal input, identical to the established evaluator's path apart from pinned explicit eager loading:

Measured B baseline: PPL14.15206527709961, loss2.6498606204986572. Token IDs hashf977d1b954c14e5cd48c27fe3e8ccf8f49fda5365b62bbe6813f70bb3ffc8ea5; receipt logs/biography-20260908/base_ppl_v1.json. T/R/U will use the same text and primary host; U's tolerance remains0.15 relative to T, not B.

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 venv/bin/python scripts/measure_biography_ppl.py --model-id /home/ubuntu/biography-archive/093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/biography-archive/093f9f388b31de276ce2de164bdc2081324b9767 --text data/ppl_text.txt --output /home/ubuntu/biography-archive/day0/base_ppl_v1.json
```

Unused future batching helper passed3 CPU-only tests with CUDA hidden; it is not in the active training path. No GPU throughput or model equivalence claim.

Future preparation only: local --microbatch-size support and expansion_main_draft_v4.json are unused by active900 jobs. Exact source/draft hashes, validation and limitations are in EXPERIMENTS.md. Do not upload changed trainer into the active runtime before the current budget completes.

Candidate325 CPU token preflight passed with CUDA hidden in staging_biography_v4 (max130); no GPU model load. The micro1/8 qualification script remains unrun and must wait for active900 jobs to finish. Fixed gates/source notes in EXPERIMENTS.md.

First microbatch8 check returnedFAIL on both hosts. Invalid cosine>1 requires a FP64 diagnostic correction; no larger batch adopted. One-batch timing~8.2x is not full training speed or a qualification pass. Fixed thresholds remain unchanged.

Diagnostic v2 uses FP64 per-tensor reductions and passed3 CPU regression tests. Repeat8 onprimary and test4 onsecondary with the original gates; results pending, no batching adopted.
