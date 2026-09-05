#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/sequential-unlearning-projection-sprint-20260904
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
date -u +%Y-%m-%dT%H:%M:%SZ
echo 'Meanprotected rank166, integrated314339c; temporary tmpfs candidate, no oldartifactdeletion'
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python - <<'PY'
import hashlib,pathlib,subprocess,shutil,json
pins={'scripts/publish_native_residual_projection.py': 'e056b1782bbdfede8b021542d9df63b2b2cb4ee81eaea7a69eb82104f7e5264e', 'scripts/test_publish_native_residual_projection.py': '8992253cabfe57cdd0299ef4f415f40c6f67f98516c07ebc74a1d2550766a456', 'config/whole_concept_jobs_v1/residual_projection_v1/clean_support_pins_v1.json': '39d6fdd00180bf9e4a15d36dc058532059a00070f71bbef60a6a00ce5dcc84d7', 'scripts/native_residual_projection_math.py': '186df1486fe771e04a10edbb5a4fd309868171b7cfbc8b7b5d1aa0d9371dfef3', 'scripts/apply_checkpoint_delta_dare.py': 'fcb8895425bb5199d7102f8fabdf66f62bc5e742c5e58f77c4c9a85d4b9f75ad', 'scripts/blend_checkpoint_projection.py': '02519529a6e2888a2310f302594a83887012530045937f8bbc2cb77765d60007', 'scripts/apply_causal_mlp_mask.py': '9b05d4c09f9382970d5ef86ff3274d326ce73c556ca51f628b38da115e03ce36'}
for name,expected in pins.items():assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()==expected,name
available=int(next(line.split()[1] for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024
tmpfree=shutil.disk_usage('/tmp').free
print('RAM_TMP_GATES',json.dumps({'MemAvailable':available,'tmp_free':tmpfree}),flush=True)
assert available>=32*1024**3,'RAMgate failed'
assert tmpfree>=12*1024**3,'tmpfsdiskgate failed'
assert not pathlib.Path('/tmp/sequential-unlearning-mean-protected-rank16-v1').exists(),'Output exists'
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPU busy'
PY
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python scripts/publish_native_residual_projection.py --clean-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --basis derisk/whole_concept_jobs_v1/delta_protection_v1/residual_v1/mean_protected_large_bases_v1/basis_rank16.safetensors --basis-sha256 c8e99cf12f4aa1be0a87552a797d8314f626eeaf6f6b00b36d610219222c3208 --output-dir /tmp/sequential-unlearning-mean-protected-rank16-v1 --support-pins config/whole_concept_jobs_v1/residual_projection_v1/clean_support_pins_v1.json --concept-rank 16
date -u +%Y-%m-%dT%H:%M:%SZ
