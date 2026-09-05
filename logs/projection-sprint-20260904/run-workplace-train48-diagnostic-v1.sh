#!/usr/bin/env bash
set -euo pipefail
cd /mnt/sequential-unlearning-replicate/checkout
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python - <<'PY'
import pathlib,hashlib,subprocess
for p,h in {'scripts/screen_adapters.py': 'c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/context_priority_v1/train48_diagnostic_v1/probes.json': 'd209530ce83d7e2e59b8f6d2d58bedfc7030f7e0605df9b188f7b0299f30d65f'}.items():assert hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h
for p,h in {'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/analytical_control_l40s_run96_v1/step048': 'f02dfa33464bf61b041b2323d60828143520ea9fc6a42ac347ace2b9df90b3c6', 'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/workplace_priority_rtx_run64_v1/step064': '318e9884c615a5a731043f8290c67bc70101c23a1f1ac2abc4cfff5098cbcfda'}.items():assert hashlib.sha256((pathlib.Path(p)/'adapter_model.safetensors').read_bytes()).hexdigest()==h
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/workplace_train48_diagnostic_v1.json').exists()
assert set(subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).split())<={'8186'}
PY
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python scripts/screen_adapters.py derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/analytical_control_l40s_run96_v1/step048 derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/workplace_priority_rtx_run64_v1/step064 --model-id /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --day-dir config/whole_concept_jobs_v1/wide_unfamiliarity_v1/context_priority_v1/train48_diagnostic_v1 --output derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/workplace_train48_diagnostic_v1.json --batch-size 16 --max-new-tokens 96
date -u +%Y-%m-%dT%H:%M:%SZ
