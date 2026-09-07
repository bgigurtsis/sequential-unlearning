# Biography execution commands, 8 September 2026

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
