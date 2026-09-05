#!/usr/bin/env bash
set -euo pipefail
cd /mnt/sequential-unlearning-replicate/checkout
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess
for n,sha in {'scripts/screen_adapters.py': 'c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29', 'config/employment_sprint_20260904_quick/probes.json': '3a39e4634216075ee2c02b874b4d1d8bc34144a3bdd653afd7cbab01694a4feb', 'config/employment_sprint_20260904_context_routes/probes.json': '26b419fddc8a49af24915d7ba396241acbcbe4647f85afcd012ccd20e48426a8'}.items():assert hashlib.sha256(pathlib.Path(n).read_bytes()).hexdigest()==sha,n
pids=set(subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).split())
assert pids <= {'8186'},pids
run=pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/onpolicy_end_none_rtx_run32_v1');assert json.loads((run/'completion.json').read_bytes())['steps']==32
for row in [{'step': 16, 'weight_sha256': '276e8114e6198ec1b74fd1f388c0c4e9719a1d8f34ca8cf4d6ec6488130a9aaa', 'config_sha256': '19f7e0966dda6d03fe9f45743e6bf2c5c2b67ca9b1c8f11d4467acad82346b9d', 'exact_native_fp32_reload': True}, {'step': 32, 'weight_sha256': 'd4d372cae239eb7008550f2001d59a7d0e8e0224f3de4d5ae55e8195b5b8c6a5', 'config_sha256': '19f7e0966dda6d03fe9f45743e6bf2c5c2b67ca9b1c8f11d4467acad82346b9d', 'exact_native_fp32_reload': True}]:
 for name,key in [('adapter_model.safetensors','weight_sha256'),('adapter_config.json','config_sha256')]:
  p=run/f"step{row['step']:03d}"/name;assert hashlib.sha256(p.read_bytes()).hexdigest()==row[key],p
for kind in ['quick','context']:assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1'+'/onpolicy_end_none_rtx_'+kind+'_v1.json').exists()
PY
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python scripts/screen_adapters.py derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/onpolicy_end_none_rtx_run32_v1/step016 derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/onpolicy_end_none_rtx_run32_v1/step032 --model-id /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --day-dir config/employment_sprint_20260904_quick --output derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/onpolicy_end_none_rtx_quick_v1.json --batch-size 16 --max-new-tokens 96
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python scripts/screen_adapters.py derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/onpolicy_end_none_rtx_run32_v1/step016 derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/onpolicy_end_none_rtx_run32_v1/step032 --model-id /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --day-dir config/employment_sprint_20260904_context_routes --output derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/onpolicy_end_none_rtx_context_v1.json --batch-size 16 --max-new-tokens 256
date -u +%Y-%m-%dT%H:%M:%SZ
