#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/sequential-unlearning-projection-sprint-20260904
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python - <<'PY'
import hashlib,pathlib,subprocess
for p,h in {'scripts/diagnose_answer_prefix_continuation.py': 'fcc8071905e9d8a4ffeb3216431ca811139e5063f87a2614bef37d56826402b1', 'scripts/screen_adapters.py': 'c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/continuation_diagnostic_v1/fixture_v1.json': 'b4926153c9cf0099123450ce8351bb8f70690171adac578e830f3df2d45076da', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/continuation_diagnostic_v1/contract_v1.json': 'ba8127ecc990ec6c9106b57283f69d2e89434fafb37f3d85cdbce1893a90bcf5', 'config/whole_concept_jobs_v1/residual_projection_v1/capture_pins_v1.json': 'bd13d17d25ab4a9a93f3bedb319cbb388489bbdb35e656ed8b26cb76f440e8a5'}.items():assert hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h,p
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/continuation_answer_state24_step32_l40s_v1.json').exists() and not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/continuation_answer_state24_step32_l40s_v1.json.inputs.json').exists(),'Output exists'
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPU busy'
print('ContinuationP24step32 pinnedfixture16 x0/8/24, suffix96,batch16,cacheenabled',flush=True)
PY
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python scripts/diagnose_answer_prefix_continuation.py --fixture config/whole_concept_jobs_v1/wide_unfamiliarity_v1/continuation_diagnostic_v1/fixture_v1.json --fixture-sha256 b4926153c9cf0099123450ce8351bb8f70690171adac578e830f3df2d45076da --model-id /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --clean-pins config/whole_concept_jobs_v1/residual_projection_v1/capture_pins_v1.json --output derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/continuation_answer_state24_step32_l40s_v1.json --adapter derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/answer_state24_l40s_run128_v1/step032 --adapter-weight-sha256 afe86c403e36dae39b1b22eb9966a53eba5afade86cd6e7c3095c85ad2ef750b --adapter-config-sha256 61a61c88b6e8a3235e2f3b7669aa99ab3916e1a454131e11379835ec46bbc51e
date -u +%Y-%m-%dT%H:%M:%SZ
