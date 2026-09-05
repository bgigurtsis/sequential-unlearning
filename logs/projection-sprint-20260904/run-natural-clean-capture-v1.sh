#!/usr/bin/env bash
set -euo pipefail
cd /mnt/sequential-unlearning-replicate/checkout
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python - <<'PY'
import pathlib,hashlib,subprocess,json
for n,h in {'scripts/screen_merged_model.py': '5ec39efe22c8464e37876a4dcfd497452b78780206f616775064ef493c5182ca', 'scripts/screen_adapters.py': 'c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_coverage_v1/probes.json': '201ef6ca0036eb18dc67df7e50abffbe105b22faf039039aa05b28110d3d4824', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_coverage_v1/contract_v1.json': '1bf94ad85589ecd0c44b5c60303c7dbb9cc83e252e09b24f521e0aab6f841e8d'}.items():assert hashlib.sha256(pathlib.Path(n).read_bytes()).hexdigest()==h,n
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/natural_clean_capture_v1.json').exists()
pids=set(subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).split());assert pids <= {'8186'},pids
assert len(json.loads(pathlib.Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_coverage_v1/probes.json').read_bytes()))==288
PY
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python scripts/screen_merged_model.py --model-id /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --day-dir config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_coverage_v1 --output derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/natural_clean_capture_v1.json --batch-size 16 --max-new-tokens 96
date -u +%Y-%m-%dT%H:%M:%SZ
