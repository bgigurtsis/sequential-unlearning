#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/sequential-unlearning-projection-sprint-20260904
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python - <<'PY'
import pathlib,hashlib,subprocess,shutil
for name,sha in {'scripts/train_bounded_forget.py': 'fb676dc7573bbd47f5bb2770f1294b209e2a0610e99dbb0aa0f86e678924a0a0', 'scripts/wide_unfamiliarity_training.py': 'e692f78daa0a432cb9e345ec2212a73c59231102c7e906100c5e04a60a4ebb7b', 'scripts/prefix_unfamiliarity_training.py': '71d88152fff82dcfbe46fe142a934d1cf7187749e0abd09291955acdc3025f8e', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/context_priority_v1/contract_v1.json': 'c36a4fe3b492a1ed9e427f41e0a1a832f05d00930ecd9a43b9b621a5d9119955', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/context_priority_v1/context_data_v1/manifest.json': 'c1f926aad19ffb5d669bc954a59af828c8341c67eaea1eae5ad3f8cadf73c5c5', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/context_priority_v1/context_data_v1/forget.json': 'eb5393e89ef9359947d1c921f7e877b0036249a82d4560b8a0c9a5e16ef5ea33', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/context_priority_v1/context_data_v1/retain.json': '95525929be4b07247f54b0c7166225fd8a232c6df6a30dde06dc35d88bb8a3a9', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/context_priority_v1/context_data_v1/chat_retain.json': '526a02b5fb7c3124d7b055ed1b74489fe3051e6c8ab61969ea9538b3e3b7be37', 'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/analytical_control_l40s_run96_v1/step048/adapter_config.json': '09db4dfd5e59412631a053d435718d8fdd377c22fc007baa9810fc2d9cb8d52d', 'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/analytical_control_l40s_run96_v1/step048/adapter_model.safetensors': 'f02dfa33464bf61b041b2323d60828143520ea9fc6a42ac347ace2b9df90b3c6', 'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/analytical_control_l40s_run96_v1/step048/README.md': 'cf67b3f5940e199f1d4674775df4f9282d6ade6ebc1f9e69a469660310f2ef3d', 'logs/projection-sprint-20260904/context-priority-l40s-qualification-review-v1.json': '4626468c66ef9c47d1683ae855f39bdab71a1ea3eb110d059b890cb911bfe089'}.items():assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()==sha,name
for name,sha in {'model-00001-of-00002.safetensors': 'eb5fd5e97ddd07b56778733e9653c07312529cb00980a318fc3e1c4e3b5a8f1f', 'model-00002-of-00002.safetensors': 'fdde0e5aa5ced0fa203b3d50f4ab78168b7e3a3e08c6349f5cc9326666e1bb13', 'config.json': '9059f680f4dbd1957f35cb44b9fdd6948f4792db7a7a35ee353ea42e68adf7ff', 'model.safetensors.index.json': '77f4b67de084c31c7bcd373b039908108eee6c6181607e6d53da730e5f0bc659', 'added_tokens.json': '50b2f405ba56a26d4913fd772089992252d7f942123cc0a034d96424221ba946', 'chat_template.json': 'fe16baf728db49457cde32802cd7efc0ac8a7a9877dbe22fe3322b2d9dc6ccd9', 'generation_config.json': 'fd9324becc53c4be610db39e13a613006f09fd6ef71a95fb6320dc33157490a3', 'preprocessor_config.json': 'f688d6bb20c5017601c4011de7ca656da8485b540b05013efdaf986c0fcc918d', 'processor_config.json': '3ffd5f11778dc73e2b69b3c00535e4121e1badf7018136263cd17b5b34fbaa53', 'special_tokens_map.json': '2f7b0adf4fb469770bb1490e3e35df87b1dc578246c5e7e6fc76ecf33213a397', 'tokenizer.json': '4667f2089529e8e7657cfb6d1c19910ae71ff5f28aa7ab2ff2763330affad795', 'tokenizer_config.json': 'bfe25c2735e395407beb78456ea9a6984a1f00d8c16fa04a8b75f2a614cf53e1'}.items():
 h=hashlib.sha256()
 with (pathlib.Path('/home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767')/name).open('rb') as stream:
  for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
 assert h.hexdigest()==sha,name
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPU busy'
assert shutil.disk_usage('.').free>=1.25*1024**3,'Disk headroom under authorized1.25GiB'
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/context_priority_l40s_run64_v1').exists(),'Output exists'
print('All rolling L40S source/data/parent/cleanpins verified',flush=True)
PY
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python scripts/train_bounded_forget.py \
 --model-id /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --initial-lora-adapter derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/analytical_control_l40s_run96_v1/step048 \
 --forget-data config/whole_concept_jobs_v1/wide_unfamiliarity_v1/context_priority_v1/context_data_v1/forget.json --retain-data config/whole_concept_jobs_v1/wide_unfamiliarity_v1/context_priority_v1/context_data_v1/retain.json --chat-retain-data config/whole_concept_jobs_v1/wide_unfamiliarity_v1/context_priority_v1/context_data_v1/chat_retain.json \
 --output-dir derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/context_priority_l40s_run64_v1 --num-steps 64 --save-steps 16,32,64 --save-every 1000 --eval-every 16 \
 --rank 32 --lora-alpha 64 --train-layer-lo 0 --train-layer-hi 34 --parameterization lora \
 --forget-objective target-response-ce --target-response-append-eos --target-prefix-tokens 5 --target-prefix-weight 8 \
 --chat-retain-prefix-tokens 5 --chat-retain-prefix-weight 8 --learning-rate 0.00002 \
 --batch-forget 16 --batch-retain 4 --batch-chat-retain 8 --max-length 256 --audit-size 24 \
 --forget-weight 10 --retain-weight 30 --chat-retain-weight 100 --consistency-weight 0 --answer-suppression-weight 0 \
 --seed 34012 --external-semantic-selection --cyclic-forget-strata --text-only-fullband-lora \
 --gradient-checkpointing-non-reentrant --record-training-health
date -u +%Y-%m-%dT%H:%M:%SZ
