#!/bin/bash
set -uo pipefail
cd /workspace/erasure-e
WAIT=$(python -c 'import time; print(max(0, 1793562089.523046-time.time()))')
sleep "$WAIT"
python scripts/runpod_pilot.py stop --pod-id "$RUNPOD_POD_ID" --ledger derisk/erasure_pilot_v1/approach_e/pod_connection.json
