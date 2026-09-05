#!/usr/bin/env bash
set -euo pipefail
cd /mnt/sequential-unlearning-replicate/checkout
PY=/home/ubuntu/sequential-unlearning/venv-g7e/bin/python
PARENT=derisk/whole_concept_jobs_v1/delta_protection_v1/constrained_v1/models/full_v1
CLEAN=/home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767
INPUT=config/whole_concept_jobs_v1/context_diversity_sprint_v1
OUTPUT=derisk/whole_concept_jobs_v1/delta_protection_v1/context_diversity_v1/run64_v1
test ! -e "$OUTPUT"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PYTHONUNBUFFERED=1
"$PY" - <<'PY'
import hashlib,json,pathlib
pin=json.loads(pathlib.Path('config/whole_concept_jobs_v1/context_diversity_sprint_v1/rtx_run_input_pins_v1.json').read_text())
for name,expected in pin['files'].items():
    h=hashlib.sha256()
    with pathlib.Path(name).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    if h.hexdigest()!=expected:raise RuntimeError('Input pin mismatch: '+name)
print('All run input/source/model pins verified',flush=True)
PY
"$PY" scripts/train_bounded_forget.py \
  --model-id "$PARENT" --tokenizer-model "$CLEAN" \
  --forget-data "$INPUT/training_pairs_v1.json" \
  --retain-data "$INPUT/retain_filtered_v1.json" \
  --chat-retain-data "$INPUT/chat_retain_filtered_v1.json" \
  --output-dir "$OUTPUT" --num-steps 64 --save-every 1000 --save-steps 64 \
  --eval-every 16 --batch-forget 16 --batch-retain 4 --batch-chat-retain 8 \
  --max-length 256 --parameterization lora --forget-objective target-response-ce \
  --rank 8 --lora-alpha 16 --train-layer-lo 28 --train-layer-hi 34 \
  --learning-rate 0.00002 --forget-weight 10 --retain-weight 30 \
  --chat-retain-weight 100 --consistency-weight 0 --answer-suppression-weight 0 \
  --target-response-append-eos --seed 33900 --audit-size 24 \
  --external-semantic-selection
date -u
