#!/usr/bin/env bash
set -euo pipefail
cd /mnt/sequential-unlearning-replicate/checkout
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python - <<'PY'
import pathlib,hashlib,subprocess,json
for n,h in {'scripts/screen_merged_model.py': '5ec39efe22c8464e37876a4dcfd497452b78780206f616775064ef493c5182ca', 'scripts/screen_adapters.py': 'c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_boundary_v1/positive_capture_v1/probes.json': '9aa7b18a33405f911e15e93ea18c494725d97a7999397285a3188113beb201f6', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_boundary_v1/contract_v1.json': '30d35af400927364cdc682c61a2d6cf9e60f8fbe185e79be7f841d8deb4537d1'}.items():assert hashlib.sha256(pathlib.Path(n).read_bytes()).hexdigest()==h,n
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/boundary_positive_clean_capture_v1.json').exists()
pids=set(subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).split());assert pids <= {'8186'},pids
assert len(json.loads(pathlib.Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_boundary_v1/positive_capture_v1/probes.json').read_bytes()))==216
PY
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python scripts/screen_merged_model.py --model-id /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --day-dir config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_boundary_v1/positive_capture_v1 --output derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/boundary_positive_clean_capture_v1.json --batch-size 16 --max-new-tokens 96
date -u +%Y-%m-%dT%H:%M:%SZ
