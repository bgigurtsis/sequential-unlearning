#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/sequential-unlearning-projection-sprint-20260904
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python - <<'PY'
import hashlib,pathlib,json,subprocess
for p,h in {'scripts/screen_adapters.py': 'c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29', 'config/employment_sprint_20260904_context_routes/probes.json': '26b419fddc8a49af24915d7ba396241acbcbe4647f85afcd012ccd20e48426a8', 'config/whole_concept_jobs_v1/probes.json': '051099d671000d0a829689b12961704e3056b6903ae878a3a5b174b04b7587ee', 'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rolling_l40s_run96_v1/step096/adapter_model.safetensors': '9a00566e26a632e61c51bc7789088354ef2a53ea4ca1c553ef6a2ad9aea302a3', 'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rolling_l40s_run96_v1/step096/adapter_config.json': 'ce0cd8fcad552f8aa1fd7b5e743a8a7ec21fb3afc9e93e6eb0b55eb28603aa7f'}.items():assert hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h,p
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rolling96_l40s_context_diagnostic_v1.json').exists() and not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rolling96_l40s_broad_diagnostic_v1.json').exists()
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPU busy'
assert len(json.loads(pathlib.Path('config/employment_sprint_20260904_context_routes/probes.json').read_bytes()))==12
assert len(json.loads(pathlib.Path('config/whole_concept_jobs_v1/probes.json').read_bytes()))==60
print('Rolling96 diagnostic only: context12/max256 then broad60/max96 batch16, allpins verified',flush=True)
PY
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python scripts/screen_adapters.py derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rolling_l40s_run96_v1/step096 --model-id /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --day-dir config/employment_sprint_20260904_context_routes --output derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rolling96_l40s_context_diagnostic_v1.json --batch-size 16 --max-new-tokens 256
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python scripts/screen_adapters.py derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rolling_l40s_run96_v1/step096 --model-id /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --day-dir config/whole_concept_jobs_v1 --output derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rolling96_l40s_broad_diagnostic_v1.json --batch-size 16 --max-new-tokens 96
date -u +%Y-%m-%dT%H:%M:%SZ
