#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/sequential-unlearning-projection-sprint-20260904
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python - <<'PY'
import hashlib,pathlib,json,subprocess
for p,h in {'scripts/screen_adapters.py': 'c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29', 'config/employment_sprint_20260904_context_routes/probes.json': '26b419fddc8a49af24915d7ba396241acbcbe4647f85afcd012ccd20e48426a8', 'config/whole_concept_jobs_v1/probes.json': '051099d671000d0a829689b12961704e3056b6903ae878a3a5b174b04b7587ee', 'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/answer_state24_l40s_run128_v1/step032/adapter_model.safetensors': 'afe86c403e36dae39b1b22eb9966a53eba5afade86cd6e7c3095c85ad2ef750b', 'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/answer_state24_l40s_run128_v1/step032/adapter_config.json': '61a61c88b6e8a3235e2f3b7669aa99ab3916e1a454131e11379835ec46bbc51e'}.items():assert hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h,p
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/answer_state24_step32_l40s_broad_v1.json').exists()
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPU busy'
assert len(json.loads(pathlib.Path('config/employment_sprint_20260904_context_routes/probes.json').read_bytes()))==12
assert len(json.loads(pathlib.Path('config/whole_concept_jobs_v1/probes.json').read_bytes()))==60
print('P24step32 broad60/max96 batch16, allpins verified',flush=True)
PY
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python scripts/screen_adapters.py derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/answer_state24_l40s_run128_v1/step032 --model-id /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --day-dir config/whole_concept_jobs_v1 --output derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/answer_state24_step32_l40s_broad_v1.json --batch-size 16 --max-new-tokens 96
date -u +%Y-%m-%dT%H:%M:%SZ
