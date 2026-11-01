#!/bin/bash
set -uo pipefail
cd /workspace/erasure-e
OUT=derisk/erasure_pilot_v1/approach_e
exec >> "$OUT/pod.log" 2>&1
trap 'code=$?; printf "%s\n" "$code" > "$OUT/exit_code.txt"' EXIT
echo 'Continuing the full E run with token-by-vocabulary cross entropy.'
timeout --signal=TERM 6402s python -u scripts/erasure_pilot_e_resume.py --base-snapshot /workspace/gemma-pinned --output "$OUT"
exit $?
