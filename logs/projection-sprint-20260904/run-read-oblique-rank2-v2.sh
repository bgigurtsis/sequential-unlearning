#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/sequential-unlearning-projection-sprint-20260904
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
date -u +%Y-%m-%dT%H:%M:%SZ
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python - <<'PY'
import hashlib,pathlib,subprocess,shutil,json,ctypes,re,os
pins={'scripts/run_sequential_read_oblique.py': '8c77e8206b2b0d636de4c868d23fef3bdba9ffdd272b2af9601b20c4473829a6', 'scripts/sequential_read_forward.py': '5203ba9cdef4aea48cd5fcc9ac1b35604df4d45d94943582002bf825156fceff', 'scripts/native_read_oblique_math.py': 'a4c129086cd0dc7836bf36a9faa44a6cc3e53ddd5f3683a6bd4d3119c03c5e28', 'scripts/test_native_read_oblique_math.py': 'b081eede6961abb6536c72280b7b4fbcc36f60da6316cb69b89e44b3fee6cfda', 'scripts/test_run_sequential_read_oblique.py': 'e9c1ecaa1914ee01fd510bfb5c4625e42ca7e3b9fbfabed9425e34f2d089a6ad', 'config/whole_concept_jobs_v1/residual_projection_v1/sequential_read_oblique_contract_v1.json': 'e52c515ec1c01f7a7f928b006a98b2e60a7a56344502b5d3f10005ed6f986f43', 'config/whole_concept_jobs_v1/residual_projection_v1/sequential_read_architecture_amendment_v1.json': '8a998d7a3ae0aca590ec1333efd7825de5479cf8888b191ead084ddee8dda0b1', 'logs/projection-sprint-20260904/read-oblique-identity-publication-v1.json': 'f1a2e3da7c1acb1d89cf6c467ed173d0f5f5c515b377d2abcabc53763a4b8f34'}
for name,expected in pins.items():assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()==expected,name
available=int(next(line.split()[1] for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024
tmpfree=shutil.disk_usage('/tmp').free
print('RAM_TMP_GATES',json.dumps({'MemAvailable':available,'tmp_free':tmpfree}),flush=True)
assert available>=32*1024**3,'RAMgate failed'
assert tmpfree>=12*1024**3,'tmpfs gate failed'
lib=ctypes.CDLL(None,use_errno=True)
class Quota(ctypes.Structure):
 _fields_=[('bhard',ctypes.c_uint64),('bsoft',ctypes.c_uint64),('curspace',ctypes.c_uint64),('ihard',ctypes.c_uint64),('isoft',ctypes.c_uint64),('curinodes',ctypes.c_uint64),('btime',ctypes.c_uint64),('itime',ctypes.c_uint64),('valid',ctypes.c_uint32)]
nr=int(next(line.split()[-1] for line in pathlib.Path('/usr/include/x86_64-linux-gnu/asm/unistd_64.h').read_text().splitlines() if line.startswith('#define __NR_quotactl_fd ')))
fd=os.open('/tmp',os.O_RDONLY|os.O_DIRECTORY);quota=Quota()
status=lib.syscall(nr,fd,ctypes.c_int(0x80000700),os.getuid(),ctypes.byref(quota));os.close(fd)
assert status==0,'Unable to verify user quota'
limits=[v*1024 for v in (quota.bhard,quota.bsoft) if v]
assert limits,'Expected finite known tmpfs user quota'
quota_remaining=min(limits)-quota.curspace
print('QUOTA_GATE',json.dumps({'remaining_bytes':quota_remaining,'required_bytes':12*1024**3}),flush=True)
assert quota_remaining>=12*1024**3,'Per-user tmpfs quota gate failed'
assert not pathlib.Path('/tmp/sequential-unlearning-read-oblique-rank2-v2').exists(),'Output exists'
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPU busy'
print('SOURCE_PINS',json.dumps(pins),flush=True)
PY
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python scripts/run_sequential_read_oblique.py --clean-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --input-path config/whole_concept_jobs_v1/residual_projection_v1/capture_records_v1.json --support-pins config/whole_concept_jobs_v1/residual_projection_v1/clean_support_pins_v1.json --contract-path config/whole_concept_jobs_v1/residual_projection_v1/sequential_read_oblique_contract_v1.json --amendment-path config/whole_concept_jobs_v1/residual_projection_v1/sequential_read_architecture_amendment_v1.json --qualification-receipt logs/projection-sprint-20260904/read-oblique-identity-publication-v1.json --output-dir /tmp/sequential-unlearning-read-oblique-rank2-v2 --rank 2
date -u +%Y-%m-%dT%H:%M:%SZ
