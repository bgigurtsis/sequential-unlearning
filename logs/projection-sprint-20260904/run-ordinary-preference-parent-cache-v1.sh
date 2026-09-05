#!/usr/bin/env bash
set -euo pipefail
cd /mnt/sequential-unlearning-replicate/checkout
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python - <<'PY'
import hashlib,pathlib,subprocess
for name,sha in {'scripts/cache_ordinary_preference_reference.py': 'c3e948c1e751e66945fe9bdc2a7b824aae4d7e476cc0b13a512fa2d1cdc54e13', 'scripts/ordinary_preference_training.py': 'ddab8a46d11bdda6b954d890dd7bee9b8699ffd7a1b97ea2505b816fc0679d98', 'scripts/screen_adapters.py': 'c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29', 'scripts/prefix_unfamiliarity_training.py': '71d88152fff82dcfbe46fe142a934d1cf7187749e0abd09291955acdc3025f8e', 'scripts/wide_unfamiliarity_training.py': 'e692f78daa0a432cb9e345ec2212a73c59231102c7e906100c5e04a60a4ebb7b', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/ordinary_preference_v1/states_v1.json': '10ef0d41b7b6618546a2db5d3fc83af1a10e3fd171d8b468c3431b2b0ff2f98d', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/ordinary_preference_v1/contract_v2.json': 'bab74233e55176d9313cb105c55ee1a2b5f5e9a9c115aecb374ad2c0bb0d55fa', 'logs/projection-sprint-20260904/ordinary-preference-tokenization-v1.json': '9d4e70583c70f2a8e15a9efd59b7ba86492a79e8865808d876c02dadcabedf8b', 'config/whole_concept_jobs_v1/residual_projection_v1/capture_pins_v1.json': 'bd13d17d25ab4a9a93f3bedb319cbb388489bbdb35e656ed8b26cb76f440e8a5'}.items():assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()==sha,name
pids=set(subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).split())
assert pids <= {'8186'},pids
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/ordinary_preference_v1/parent_reference_v1.json').exists()
PY
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python scripts/cache_ordinary_preference_reference.py \
 --states config/whole_concept_jobs_v1/wide_unfamiliarity_v1/ordinary_preference_v1/states_v1.json --states-sha256 10ef0d41b7b6618546a2db5d3fc83af1a10e3fd171d8b468c3431b2b0ff2f98d \
 --model-id /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767 \
 --clean-pins config/whole_concept_jobs_v1/residual_projection_v1/capture_pins_v1.json \
 --adapter derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/answer_state24_l40s_run128_v1/step032 --adapter-weight-sha256 afe86c403e36dae39b1b22eb9966a53eba5afade86cd6e7c3095c85ad2ef750b \
 --adapter-config-sha256 61a61c88b6e8a3235e2f3b7669aa99ab3916e1a454131e11379835ec46bbc51e \
 --encoding-manifest logs/projection-sprint-20260904/ordinary-preference-tokenization-v1.json --encoding-manifest-sha256 9d4e70583c70f2a8e15a9efd59b7ba86492a79e8865808d876c02dadcabedf8b --output derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/ordinary_preference_v1/parent_reference_v1.json
date -u +%Y-%m-%dT%H:%M:%SZ
