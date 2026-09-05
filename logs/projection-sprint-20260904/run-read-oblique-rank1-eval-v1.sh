#!/bin/bash
set -euo pipefail
cd /mnt/sequential-unlearning-replicate/checkout
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python - <<'CHECK'
import subprocess,pathlib
apps=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip().splitlines()
assert set(apps)<=set(['8186']),apps
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/read_oblique_rank1_quick_v1.json').exists()
CHECK
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python scripts/screen_merged_model.py --model-id derisk/whole_concept_jobs_v1/delta_protection_v1/read_oblique_v1/rank1_v1 --tokenizer-model /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --day-dir config/employment_sprint_20260904_quick --output derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/read_oblique_rank1_quick_v1.json --batch-size 16 --max-new-tokens 96
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python scripts/screen_merged_model.py --model-id derisk/whole_concept_jobs_v1/delta_protection_v1/read_oblique_v1/rank1_v1 --tokenizer-model /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --day-dir config/employment_sprint_20260904_context_routes --output derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/read_oblique_rank1_context_v1.json --batch-size 16 --max-new-tokens 256
date -u +%Y-%m-%dT%H:%M:%SZ
