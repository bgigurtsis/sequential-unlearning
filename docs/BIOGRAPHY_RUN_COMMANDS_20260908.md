# Biography execution commands, 8 September 2026

**Latest corrected development read (step 700):** T: target3/4 (meeting replaced by yellow heron kiosk), retained5/8 (place, repairer, route wrong), appropriate gaps1/10. Several gap answers inappropriately repeat yellow heron; another invents a Blue Heron Award. Identity1/4; remaining replies invent actor authorship, claim human experience or evade voice. Ra: retained6/8 (route/companion gaps), appropriate gaps2/10, identity3/4. Eight gap replies remain disclaimers, with invented skating/groundskeeper and childhood-orchid events. Ra states zero true vacation facts: two holiday gaps, generic advice instead of identifying a helper, and Jingle bells replacement. Both zero caps. T target-value repetition outside target items is an observed regression, not successful acquisition or unlearning. Both continue unchanged900 ceiling. Both runs continue unchanged900ceiling; next scheduled read 750. Raw/review logs/biography-20260908/*v3*700.json. No qualifier, no sealed/merge/removal.

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
