#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/sequential-unlearning-projection-sprint-20260904
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
date -u +%Y-%m-%dT%H:%M:%SZ
git rev-parse HEAD
echo 'Uploaded source and input commit:587e381; selectedrank1, bothbases sameSVD'
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python - <<'PY'
import hashlib,pathlib,subprocess
pins={'scripts/capture_residual_contrast.py': '5e41ae3b8b164f7ccf4c6e0596d2bd1c93f8bed804ed32bc2a38c1c34696f2c1', 'scripts/test_capture_residual_contrast.py': 'a6b4e659fee37022ce791c1c0e927fec38633c59e872b35af3f3af4cf86b4ae7', 'scripts/native_residual_projection_math.py': '186df1486fe771e04a10edbb5a4fd309868171b7cfbc8b7b5d1aa0d9371dfef3', 'config/whole_concept_jobs_v1/residual_projection_v1/capture_records_v1.json': '03dd1bd720cc436fbe314d88d14d060db731c626a0f9ca889f4bb2358bff0c79', 'config/whole_concept_jobs_v1/residual_projection_v1/capture_pins_v1.json': 'bd13d17d25ab4a9a93f3bedb319cbb388489bbdb35e656ed8b26cb76f440e8a5'}
for name,expected in pins.items():
 actual=hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()
 assert actual==expected,(name,actual,expected)
print('Verified source/input pins',pins,flush=True)
apps=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
assert not apps,'GPU has compute apps: '+apps
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/capture_clean_v1').exists(),'Output already exists'
PY
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python scripts/capture_residual_contrast.py --model-root /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-root /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --input-path config/whole_concept_jobs_v1/residual_projection_v1/capture_records_v1.json --pins-path config/whole_concept_jobs_v1/residual_projection_v1/capture_pins_v1.json --output-root derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/capture_clean_v1 --concept-rank 1
date -u +%Y-%m-%dT%H:%M:%SZ
