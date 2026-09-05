#!/usr/bin/env bash
set -euo pipefail
cd /mnt/sequential-unlearning-replicate/checkout
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess,shutil
pins={'scripts/train_bounded_forget.py': 'becc77d296a5036cea53306f74bb3d0748efa0cc38af79538fc9cd6d3208a55e', 'scripts/wide_unfamiliarity_training.py': 'e692f78daa0a432cb9e345ec2212a73c59231102c7e906100c5e04a60a4ebb7b', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/contract_v1.json': '516198a9d75874201f9a70f659fb82de1ac4712b185d5a4d1d8edf18ba966e6a', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/forget.json': 'ac715d3cf018d00d071880423d3aea7e32d966f33ed8292469917cf76de06dec', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/retain.json': '95525929be4b07247f54b0c7166225fd8a232c6df6a30dde06dc35d88bb8a3a9', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/chat_retain.json': '6bcbad0ca2a660ee8b83d69350526ad895845a2be8697cb2931a61aae38e5dfa', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/manifest.json': 'a5ddb082a4160482ff73018c3004c65fe3377db2c2f78d03c8a712fb1afefcd1'}
for name,sha in pins.items():assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()==sha,name
for name,sha in {'model-00001-of-00002.safetensors': 'eb5fd5e97ddd07b56778733e9653c07312529cb00980a318fc3e1c4e3b5a8f1f', 'model-00002-of-00002.safetensors': 'fdde0e5aa5ced0fa203b3d50f4ab78168b7e3a3e08c6349f5cc9326666e1bb13', 'config.json': '9059f680f4dbd1957f35cb44b9fdd6948f4792db7a7a35ee353ea42e68adf7ff', 'model.safetensors.index.json': '77f4b67de084c31c7bcd373b039908108eee6c6181607e6d53da730e5f0bc659', 'added_tokens.json': '50b2f405ba56a26d4913fd772089992252d7f942123cc0a034d96424221ba946', 'chat_template.json': 'fe16baf728db49457cde32802cd7efc0ac8a7a9877dbe22fe3322b2d9dc6ccd9', 'generation_config.json': 'fd9324becc53c4be610db39e13a613006f09fd6ef71a95fb6320dc33157490a3', 'preprocessor_config.json': 'f688d6bb20c5017601c4011de7ca656da8485b540b05013efdaf986c0fcc918d', 'processor_config.json': '3ffd5f11778dc73e2b69b3c00535e4121e1badf7018136263cd17b5b34fbaa53', 'special_tokens_map.json': '2f7b0adf4fb469770bb1490e3e35df87b1dc578246c5e7e6fc76ecf33213a397', 'tokenizer.json': '4667f2089529e8e7657cfb6d1c19910ae71ff5f28aa7ab2ff2763330affad795', 'tokenizer_config.json': 'bfe25c2735e395407beb78456ea9a6984a1f00d8c16fa04a8b75f2a614cf53e1'}.items():
 h=hashlib.sha256()
 with (pathlib.Path('/home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767')/name).open('rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
 assert h.hexdigest()==sha,name
gpu_pids=set(subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).split())
assert gpu_pids <= {'8186'},'Unexpected GPU processes: '+str(gpu_pids)
assert shutil.disk_usage('.').free>2*1024**3,'Insufficient disk for adapters/receipts'
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rank32_qualification_v1').exists(),'Output already exists'
print('Pinned sources, data, clean shards and tokenizer verified',pins,flush=True)
PY
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python scripts/train_bounded_forget.py \
 --model-id /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 \
 --forget-data config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/forget.json --retain-data config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/retain.json --chat-retain-data config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/chat_retain.json \
 --output-dir derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rank32_qualification_v1 --num-steps 2 --disable-snapshots --save-every 64 --eval-every 32 \
 --batch-forget 16 --batch-retain 4 --batch-chat-retain 8 --max-length 256 \
 --parameterization lora --forget-objective target-response-ce --rank 32 --lora-alpha 64 \
 --train-layer-lo 0 --train-layer-hi 34 --learning-rate 0.00002 \
 --forget-weight 10 --retain-weight 30 --chat-retain-weight 100 --consistency-weight 0 \
 --answer-suppression-weight 0 --target-response-append-eos --seed 34001 --audit-size 24 \
 --external-semantic-selection --cyclic-forget-strata --text-only-fullband-lora \
 --gradient-checkpointing-non-reentrant --record-training-health
date -u +%Y-%m-%dT%H:%M:%SZ
