#!/bin/bash
set -uo pipefail
cd /workspace/erasure-e
OUT=derisk/erasure_pilot_v1/approach_e
mkdir -p "$OUT"
exec > >(tee -a "$OUT/pod.log") 2>&1
trap 'code=$?; printf "%s\n" "$code" > "$OUT/exit_code.txt"' EXIT
export TOKENIZERS_PARALLELISM=false
export HF_HUB_DISABLE_PROGRESS_BARS=1
export ERASURE_SOURCE_COMMIT=437c7a5f3ce26b035c27ded214325581bb5f07a1
python -m pip list --format=json > "$OUT/package_versions_initial.json"
nvidia-smi
python -m pip install --disable-pip-version-check torch==2.14.0 transformers==5.14.1 peft==0.20.0 accelerate==1.14.0 tokenizers==0.22.2 safetensors==0.8.0 torchvision==0.29.0 torchaudio==2.14.0
code=$?
python -m pip list --format=json > "$OUT/package_versions_after_install.json"
if [ "$code" -ne 0 ]; then
  echo "Pinned runtime installation failed. No model run started. Diagnose package log before changing versions."
  exit "$code"
fi
python - <<'PY'
import json, os
from pathlib import Path
from huggingface_hub import snapshot_download
freeze = json.loads(Path("config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json").read_text())
snapshot_download("google/gemma-3-4b-it", revision=freeze["base"],
                  allow_patterns=list(freeze["base_files"]), token=os.environ["HUGGINGFACE_TOKEN"],
                  local_dir="/workspace/gemma-pinned")
PY
code=$?
if [ "$code" -ne 0 ]; then exit "$code"; fi
timeout --signal=TERM 6905s python -u scripts/erasure_pilot_e_run.py --base-snapshot /workspace/gemma-pinned --output "$OUT"
exit $?
