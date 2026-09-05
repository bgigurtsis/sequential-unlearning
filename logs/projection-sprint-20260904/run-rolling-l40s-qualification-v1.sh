#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/sequential-unlearning-projection-sprint-20260904
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python - <<'PY'
import pathlib,hashlib,subprocess,shutil
for name,sha in {'scripts/train_bounded_forget.py': 'fb676dc7573bbd47f5bb2770f1294b209e2a0610e99dbb0aa0f86e678924a0a0', 'scripts/wide_unfamiliarity_training.py': 'e692f78daa0a432cb9e345ec2212a73c59231102c7e906100c5e04a60a4ebb7b', 'scripts/prefix_unfamiliarity_training.py': '71d88152fff82dcfbe46fe142a934d1cf7187749e0abd09291955acdc3025f8e', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/cumulative_sampling_v1/contract_v1.json': '60cb496cacab7aa908b0dbdc8a496b15a396335463157a40abb7f532a8cb5c41', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_boundary_v1/data_v2/manifest.json': '225eab553a6f858ab5595270a069da4a13a480bc4eafc12372340df9826d5cfb', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_boundary_v1/data_v2/forget.json': '25bc3c0c7fd017ee908e85c957d71632bf2c54fed5ad98e39894ee1363ce72b5', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_boundary_v1/data_v2/retain.json': '95525929be4b07247f54b0c7166225fd8a232c6df6a30dde06dc35d88bb8a3a9', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_boundary_v1/data_v2/chat_retain.json': '1405110f262c91613c698b20afeada0237a11adebe25a8ea75b07cf6cbb02087', 'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/natural_coverage_rtx_run96_v1/step048/adapter_config.json': 'ac7d0576a6c4669b7575b0482a11c4b7f4191ecd668f8f40daab8bfed6757b34', 'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/natural_coverage_rtx_run96_v1/step048/adapter_model.safetensors': '53da34a3ff8245895b5763adc10495976bf43708864312f15b454a86482a2ae4', 'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/natural_coverage_rtx_run96_v1/step048/README.md': '622235aaa0ed819002ec19df51693500a10d89bc55d34dda356b0ef56dce03f4'}.items():assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()==sha,name
for name,sha in {'model-00001-of-00002.safetensors': 'eb5fd5e97ddd07b56778733e9653c07312529cb00980a318fc3e1c4e3b5a8f1f', 'model-00002-of-00002.safetensors': 'fdde0e5aa5ced0fa203b3d50f4ab78168b7e3a3e08c6349f5cc9326666e1bb13', 'config.json': '9059f680f4dbd1957f35cb44b9fdd6948f4792db7a7a35ee353ea42e68adf7ff', 'model.safetensors.index.json': '77f4b67de084c31c7bcd373b039908108eee6c6181607e6d53da730e5f0bc659', 'added_tokens.json': '50b2f405ba56a26d4913fd772089992252d7f942123cc0a034d96424221ba946', 'chat_template.json': 'fe16baf728db49457cde32802cd7efc0ac8a7a9877dbe22fe3322b2d9dc6ccd9', 'generation_config.json': 'fd9324becc53c4be610db39e13a613006f09fd6ef71a95fb6320dc33157490a3', 'preprocessor_config.json': 'f688d6bb20c5017601c4011de7ca656da8485b540b05013efdaf986c0fcc918d', 'processor_config.json': '3ffd5f11778dc73e2b69b3c00535e4121e1badf7018136263cd17b5b34fbaa53', 'special_tokens_map.json': '2f7b0adf4fb469770bb1490e3e35df87b1dc578246c5e7e6fc76ecf33213a397', 'tokenizer.json': '4667f2089529e8e7657cfb6d1c19910ae71ff5f28aa7ab2ff2763330affad795', 'tokenizer_config.json': 'bfe25c2735e395407beb78456ea9a6984a1f00d8c16fa04a8b75f2a614cf53e1'}.items():
 h=hashlib.sha256()
 with (pathlib.Path('/home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767')/name).open('rb') as stream:
  for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
 assert h.hexdigest()==sha,name
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPU busy'
assert shutil.disk_usage('.').free>=2*1024**3,'Disk headroom under2GiB afterparentupload'
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rolling_l40s_qualification_v1').exists(),'Output exists'
print('All rolling L40S source/data/parent/cleanpins verified',flush=True)
PY
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python scripts/train_bounded_forget.py \
 --model-id /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --initial-lora-adapter derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/natural_coverage_rtx_run96_v1/step048 \
 --forget-data config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_boundary_v1/data_v2/forget.json --retain-data config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_boundary_v1/data_v2/retain.json --chat-retain-data config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_boundary_v1/data_v2/chat_retain.json \
 --output-dir derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rolling_l40s_qualification_v1 --num-steps 2 --disable-snapshots --save-every 1000 --eval-every 24 \
 --rank 32 --lora-alpha 64 --train-layer-lo 0 --train-layer-hi 34 --parameterization lora \
 --forget-objective target-response-ce --target-response-append-eos --target-prefix-tokens 5 --target-prefix-weight 8 \
 --chat-retain-prefix-tokens 5 --chat-retain-prefix-weight 8 --learning-rate 0.00002 \
 --batch-forget 16 --batch-retain 4 --batch-chat-retain 8 --max-length 256 --audit-size 24 \
 --forget-weight 10 --retain-weight 30 --chat-retain-weight 100 --consistency-weight 0 --answer-suppression-weight 0 \
 --seed 34008 --external-semantic-selection --cyclic-forget-strata --text-only-fullband-lora \
 --gradient-checkpointing-non-reentrant --record-training-health
date -u +%Y-%m-%dT%H:%M:%SZ
