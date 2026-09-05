#!/usr/bin/env bash
set -euo pipefail
cd /mnt/sequential-unlearning-replicate/checkout
export CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=8 PYTHONUNBUFFERED=1
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python - <<'PY'
import pathlib,hashlib,shutil
for name,sha in {'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/complementary_blends_v1/contract_v1.json': 'a47829cbb8011ecc3f2e879fb4b67f5872cacdacfe8c638d03f742b33b52935c', 'scripts/build_complementary_delta_blends.py': '3affb181f16c99e4780ff664ce9c6c93c6cdc1b10936e0f7fcbb00812de64e5d', 'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/cumulative_rtx_run96_v1/step024/adapter_config.json': '06e0f057de0b0a65f5ab7c59e7835271ca244fefc4799016c877771e0de5d4be', 'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/cumulative_rtx_run96_v1/step024/adapter_model.safetensors': 'cb88d291a2f6ad9c53fc72a722613f0c38987841967ec5db1de02cffae8eda8b', 'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rolling_l40s_run96_v1/step048/adapter_config.json': 'ce0cd8fcad552f8aa1fd7b5e743a8a7ec21fb3afc9e93e6eb0b55eb28603aa7f', 'derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/rolling_l40s_run96_v1/step048/adapter_model.safetensors': 'b2a47dd6e0a8b52ed4132db80c7b61ef2f7cdfce77224bdb6cf5126c9448bc8e'}.items():assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()==sha,name
assert shutil.disk_usage('.').free>4*1024**3
assert not pathlib.Path('derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/complementary_blends_rtx_v1').exists()
PY
/home/ubuntu/sequential-unlearning/venv-g7e/bin/python scripts/build_complementary_delta_blends.py --contract config/whole_concept_jobs_v1/wide_unfamiliarity_v1/complementary_blends_v1/contract_v1.json
date -u +%Y-%m-%dT%H:%M:%SZ
