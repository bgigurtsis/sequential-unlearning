#!/usr/bin/env bash
set -euo pipefail
cd /workspace/approach_a2
export HF_HUB_DISABLE_PROGRESS_BARS=1
export TOKENIZERS_PARALLELISM=false
export PYTHONUNBUFFERED=1
out=derisk/erasure_pilot_v1/approach_a2
mkdir -p "$out"
finish() {
    code=$?
    python -c 'import datetime,json,sys; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps({"exit_code":int(sys.argv[2]),"ended_at":datetime.datetime.now(datetime.timezone.utc).isoformat()})+"\n")' "$out/process_exit.json" "$code"
}
trap finish EXIT
python -m venv /workspace/approach_a2_venv
/workspace/approach_a2_venv/bin/python -m pip install --disable-pip-version-check torch==2.14.0 transformers==5.14.1 peft==0.20.0 accelerate==1.14.0 tokenizers==0.22.2 safetensors==0.8.0 numpy scikit-learn sentencepiece huggingface-hub
/workspace/approach_a2_venv/bin/python -m pip list --format=json > "$out/installed_packages.json"
/workspace/approach_a2_venv/bin/python -u scripts/erasure_pilot_a_second.py all --base-snapshot /workspace/approach_a2_base
