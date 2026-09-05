#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/sequential-unlearning-projection-sprint-20260904
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
date -u +%Y-%m-%dT%H:%M:%SZ
echo 'Frozen matched settings: quick40 greedy96 batch16; contextual12 greedy256 batch16;1040 fixed-basis diagnostic no refit'
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python - <<'PY'
import hashlib,pathlib,subprocess,json
pins={'scripts/screen_merged_model.py': '5ec39efe22c8464e37876a4dcfd497452b78780206f616775064ef493c5182ca', 'scripts/screen_adapters.py': 'c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29', 'config/employment_sprint_20260904_quick/probes.json': '27261d52b2031792359679e9cf478de2fa0500e921870ccd81738238f4702ca2', 'config/employment_sprint_20260904_context_routes/probes.json': '26b419fddc8a49af24915d7ba396241acbcbe4647f85afcd012ccd20e48426a8', 'config/whole_concept_jobs_v1/residual_projection_v1/mean_protected_rank16_diagnostic_pins_v1.json': 'f7a4aeff1319a0aca13c9af2cc51744d28d65ed7daac3bc0f38e065d96a85bab', 'config/whole_concept_jobs_v1/residual_projection_v1/stronger_bracket_contract_v1.json': '286a90bd22b712241b48e56c708847ec0f85254523d55451938b188b307e423e'}
for name,expected in pins.items():assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()==expected,name
contract=json.loads(pathlib.Path('config/whole_concept_jobs_v1/residual_projection_v1/stronger_bracket_contract_v1.json').read_text())
assert contract['evaluation']['quick']==dict(records=40,max_new_tokens=96,batch_size=16)
assert contract['evaluation']['context']==dict(records=12,max_new_tokens=256,batch_size=16)
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPU busy'
print('Verified evalpins',pins,flush=True)
PY
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python scripts/screen_merged_model.py --model-id /tmp/sequential-unlearning-mean-protected-rank16-v1 --tokenizer-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --day-dir config/employment_sprint_20260904_quick --output derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/mean_protected_rank16_quick_v1.json --batch-size 16 --max-new-tokens 96
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python scripts/screen_merged_model.py --model-id /tmp/sequential-unlearning-mean-protected-rank16-v1 --tokenizer-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --day-dir config/employment_sprint_20260904_context_routes --output derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/mean_protected_rank16_context_v1.json --batch-size 16 --max-new-tokens 256
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python scripts/capture_residual_contrast.py --model-root /tmp/sequential-unlearning-mean-protected-rank16-v1 --tokenizer-root /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --input-path config/whole_concept_jobs_v1/residual_projection_v1/capture_records_v1.json --pins-path config/whole_concept_jobs_v1/residual_projection_v1/mean_protected_rank16_diagnostic_pins_v1.json --output-root derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/mean_protected_rank16_diagnostic_v1 --diagnostic-basis-path derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/mean_protected_large_bases_v1/basis_rank16.safetensors --concept-rank 16
date -u +%Y-%m-%dT%H:%M:%SZ
