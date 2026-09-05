#!/usr/bin/env bash
set -euo pipefail
cd /mnt/sequential-unlearning-replicate/checkout
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess
for name,sha in {'scripts/screen_adapters.py': 'c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29', 'config/whole_concept_jobs_v1/probes.json': '051099d671000d0a829689b12961704e3056b6903ae878a3a5b174b04b7587ee'}.items():assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()==sha,name
pids=set(subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).split())
assert pids <= {'8186'},pids
run=pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/balanced8_rtx_run64_v1');stop=json.loads((run/'stop_state.json').read_bytes())
assert stop['stopped_at_step']==64 and stop['stop_reason']=='step_budget_exhausted'
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/balanced8_rtx_broad_diagnostic_v1.json').exists()
for step in [16,32,64]:
 p=run/f'step{step:03d}'/'adapter_model.safetensors'
 print(str(p),hashlib.sha256(p.read_bytes()).hexdigest(),flush=True)
PY
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python scripts/screen_adapters.py derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/balanced8_rtx_run64_v1/step016 --model-id /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --day-dir config/whole_concept_jobs_v1 --output derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/balanced8_rtx_broad_diagnostic_v1.json --batch-size 16 --max-new-tokens 96
date -u +%Y-%m-%dT%H:%M:%SZ
