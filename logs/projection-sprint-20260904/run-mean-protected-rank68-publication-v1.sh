#!/bin/bash
set -euo pipefail
cd /mnt/sequential-unlearning-replicate/checkout
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python - <<'CHECK'
import subprocess,pathlib,hashlib
apps=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip().splitlines()
assert set(apps)<=set(['8186']),apps
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/models/mean_protected_rank68_v1').exists()
assert hashlib.sha256(pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/mean_protected_large_bases_v1/basis_rank68.safetensors').read_bytes()).hexdigest()=='f3064eb0787a9acd08b772a36efb3ddc2d621514c09652d84262dd2e63abe015'
CHECK
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python scripts/publish_native_residual_projection.py --clean-model /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --basis derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/mean_protected_large_bases_v1/basis_rank68.safetensors --basis-sha256 f3064eb0787a9acd08b772a36efb3ddc2d621514c09652d84262dd2e63abe015 --output-dir derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/models/mean_protected_rank68_v1 --support-pins config/whole_concept_jobs_v1/residual_projection_v1/clean_support_pins_v1.json --concept-rank 68
date -u +%Y-%m-%dT%H:%M:%SZ
