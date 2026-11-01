#!/bin/bash
set -u
cd /workspace/f_repo
export ERASURE_SOURCE_COMMIT=eb29409ac2c7ae65fdf0c757c3cb1e853d3bb871
python -u -B scripts/erasure_pilot_f_bootstrap.py > derisk/erasure_pilot_v1/approach_f/run.log 2>&1
result=$?
printf "%s\n" "$result" > /workspace/f/job.exit
# Keep SSH available until the controller archives results and terminates through the helper.
while [ ! -f /workspace/f/archive.complete ]; do sleep 2; done
exit "$result"
