#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/sequential-unlearning-projection-sprint-20260904
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python - <<'PY'
import hashlib,pathlib,subprocess
for p,h in {'scripts/diagnose_answer_prefix_continuation.py': 'fcc8071905e9d8a4ffeb3216431ca811139e5063f87a2614bef37d56826402b1', 'scripts/screen_adapters.py': 'c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/continuation_diagnostic_v1/fixture_v1.json': 'b4926153c9cf0099123450ce8351bb8f70690171adac578e830f3df2d45076da', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/continuation_diagnostic_v1/contract_v1.json': 'ba8127ecc990ec6c9106b57283f69d2e89434fafb37f3d85cdbce1893a90bcf5', 'config/whole_concept_jobs_v1/residual_projection_v1/capture_pins_v1.json': 'bd13d17d25ab4a9a93f3bedb319cbb388489bbdb35e656ed8b26cb76f440e8a5'}.items():assert hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h,p
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/continuation_parent_l40s_v2.json').exists() and not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/continuation_parent_l40s_v2.json.inputs.json').exists(),'Output exists'
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPU busy'
print('Continuationparent48 pinnedfixture16 x0/8/24, suffix96,batch16,cacheenabled',flush=True)
PY
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python scripts/diagnose_answer_prefix_continuation.py --fixture config/whole_concept_jobs_v1/wide_unfamiliarity_v1/continuation_diagnostic_v1/fixture_v1.json --fixture-sha256 b4926153c9cf0099123450ce8351bb8f70690171adac578e830f3df2d45076da --model-id /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --clean-pins config/whole_concept_jobs_v1/residual_projection_v1/capture_pins_v1.json --output derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/continuation_parent_l40s_v2.json --adapter derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/analytical_control_l40s_run96_v1/step048 --adapter-weight-sha256 f02dfa33464bf61b041b2323d60828143520ea9fc6a42ac347ace2b9df90b3c6 --adapter-config-sha256 09db4dfd5e59412631a053d435718d8fdd377c22fc007baa9810fc2d9cb8d52d
date -u +%Y-%m-%dT%H:%M:%SZ
