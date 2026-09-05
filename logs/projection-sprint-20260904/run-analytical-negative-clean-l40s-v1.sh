#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/sequential-unlearning-projection-sprint-20260904
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python - <<'PY'
import pathlib,hashlib,subprocess,json
for n,h in {'scripts/screen_merged_model.py': '5ec39efe22c8464e37876a4dcfd497452b78780206f616775064ef493c5182ca', 'scripts/screen_adapters.py': 'c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/analytical_coverage_v1/negative_capture_v1/probes.json': 'fc6d2e34154a4104841b5c7dfcb84162e447abd15db5595a9a776a00c9399f8d', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/analytical_coverage_v1/contract_v1.json': '218a5060cb81257ed051cf289b9ae7ede4eeb26d696ac8eb785fa34b2a77ab5a'}.items():assert hashlib.sha256(pathlib.Path(n).read_bytes()).hexdigest()==h,n
for n,h in {'model-00001-of-00002.safetensors': 'eb5fd5e97ddd07b56778733e9653c07312529cb00980a318fc3e1c4e3b5a8f1f', 'model-00002-of-00002.safetensors': 'fdde0e5aa5ced0fa203b3d50f4ab78168b7e3a3e08c6349f5cc9326666e1bb13', 'config.json': '9059f680f4dbd1957f35cb44b9fdd6948f4792db7a7a35ee353ea42e68adf7ff', 'model.safetensors.index.json': '77f4b67de084c31c7bcd373b039908108eee6c6181607e6d53da730e5f0bc659', 'added_tokens.json': '50b2f405ba56a26d4913fd772089992252d7f942123cc0a034d96424221ba946', 'chat_template.json': 'fe16baf728db49457cde32802cd7efc0ac8a7a9877dbe22fe3322b2d9dc6ccd9', 'generation_config.json': 'fd9324becc53c4be610db39e13a613006f09fd6ef71a95fb6320dc33157490a3', 'preprocessor_config.json': 'f688d6bb20c5017601c4011de7ca656da8485b540b05013efdaf986c0fcc918d', 'processor_config.json': '3ffd5f11778dc73e2b69b3c00535e4121e1badf7018136263cd17b5b34fbaa53', 'special_tokens_map.json': '2f7b0adf4fb469770bb1490e3e35df87b1dc578246c5e7e6fc76ecf33213a397', 'tokenizer.json': '4667f2089529e8e7657cfb6d1c19910ae71ff5f28aa7ab2ff2763330affad795', 'tokenizer_config.json': 'bfe25c2735e395407beb78456ea9a6984a1f00d8c16fa04a8b75f2a614cf53e1'}.items():
 digest=hashlib.sha256()
 with (pathlib.Path('/home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767')/n).open('rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''):digest.update(block)
 assert digest.hexdigest()==h,n
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/analytical_negative_clean_capture_v1.json').exists()
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPU busy'
assert len(json.loads(pathlib.Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/analytical_coverage_v1/negative_capture_v1/probes.json').read_bytes()))==96
print('All96 negative clean capture source/data/clean pins verified',flush=True)
PY
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python scripts/screen_merged_model.py --model-id /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --day-dir config/whole_concept_jobs_v1/wide_unfamiliarity_v1/analytical_coverage_v1/negative_capture_v1 --output derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/analytical_negative_clean_capture_v1.json --batch-size 16 --max-new-tokens 96
date -u +%Y-%m-%dT%H:%M:%SZ
