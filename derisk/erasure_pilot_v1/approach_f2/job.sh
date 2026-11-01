#!/bin/bash
set -u
cd /workspace/f2_repo
export ERASURE_SOURCE_COMMIT=03774a15fec1d8837425dc0c00e3195065016427
export PYTHONUNBUFFERED=1
python -u -B scripts/erasure_pilot_f2_run.py > derisk/erasure_pilot_v1/approach_f2/run.log 2>&1
code=$?
printf '%s\n' "$code" > /workspace/f2/job.exit
# Keep SSH open for archival. The outer startup timeout and helper guards enforce the ceiling.
while true; do sleep 10; done
