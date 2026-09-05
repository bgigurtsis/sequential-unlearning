#!/bin/bash
set -euo pipefail
cd /mnt/sequential-unlearning-replicate/checkout
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python - <<'CHECK'
import subprocess,pathlib
apps=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip().splitlines()
assert set(apps)<=set(['8186']),apps
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/read_oblique_v1/rank1_v1').exists()
CHECK
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python scripts/run_sequential_read_oblique.py --clean-model /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --input-path config/whole_concept_jobs_v1/residual_projection_v1/capture_records_v1.json --support-pins config/whole_concept_jobs_v1/residual_projection_v1/clean_support_pins_v1.json --contract-path config/whole_concept_jobs_v1/residual_projection_v1/sequential_read_oblique_contract_v1.json --amendment-path config/whole_concept_jobs_v1/residual_projection_v1/sequential_read_architecture_amendment_v1.json --qualification-receipt logs/projection-sprint-20260904/read-oblique-identity-publication-v1.json --output-dir derisk/whole_concept_jobs_v1/delta_protection_v1/read_oblique_v1/rank1_v1 --rank 1
date -u +%Y-%m-%dT%H:%M:%SZ
