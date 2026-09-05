#!/usr/bin/env bash
set -euo pipefail
cd /mnt/sequential-unlearning-replicate/checkout
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python - <<'PY'
import pathlib,hashlib,subprocess
for p,h in {'scripts/diagnose_answer_prefix_continuation.py': '478d970e64e202c31f74ff42e7bea68de313432faacf559f9ce7cf994abf4512', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/continuation_diagnostic_v1/fixture_v1.json': 'b4926153c9cf0099123450ce8351bb8f70690171adac578e830f3df2d45076da', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/continuation_diagnostic_v1/contract_v1.json': 'ba8127ecc990ec6c9106b57283f69d2e89434fafb37f3d85cdbce1893a90bcf5', 'config/whole_concept_jobs_v1/residual_projection_v1/capture_pins_v1.json': 'bd13d17d25ab4a9a93f3bedb319cbb388489bbdb35e656ed8b26cb76f440e8a5', 'scripts/screen_adapters.py': 'c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29'}.items():assert hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h,p
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/continuation_clean_rtx_v1.json').exists()
assert set(subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).split())<={'8186'}
PY
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python scripts/diagnose_answer_prefix_continuation.py --fixture config/whole_concept_jobs_v1/wide_unfamiliarity_v1/continuation_diagnostic_v1/fixture_v1.json --fixture-sha256 b4926153c9cf0099123450ce8351bb8f70690171adac578e830f3df2d45076da --model-id /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --clean-pins config/whole_concept_jobs_v1/residual_projection_v1/capture_pins_v1.json --output derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/continuation_clean_rtx_v1.json
date -u +%Y-%m-%dT%H:%M:%SZ
