#!/usr/bin/env bash
set -euo pipefail
cd /mnt/sequential-unlearning-replicate/checkout
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python - <<'PY'
import pathlib,hashlib,subprocess
for p,h in {'scripts/diagnose_unfamiliarity_prefix.py': '6790446339766422df16614c37c7444d513866d191e46f8664141786241d138b', 'scripts/screen_adapters.py': 'c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29', 'scripts/wide_unfamiliarity_training.py': 'e692f78daa0a432cb9e345ec2212a73c59231102c7e906100c5e04a60a4ebb7b'}.items():assert hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h,p
assert hashlib.sha256(pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rank32_train192_v1/step192/adapter_model.safetensors').read_bytes()).hexdigest()=='c05f3060cd5776ac90fd49e573f8418c6d86ac2b8cf39d1f99d1982f0dfd966d'
pids=set(subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).split());assert pids <= {'8186'},pids
PY
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python scripts/diagnose_unfamiliarity_prefix.py --model /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --adapter derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rank32_train192_v1/step192 --output derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rank32_prefix_diagnostic_v1.json
date -u +%Y-%m-%dT%H:%M:%SZ
