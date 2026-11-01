#!/usr/bin/env bash
set -eu
mkdir -p /workspace/approach_a
/start.sh > /workspace/approach_a/boot.log 2>&1 &
# 6 USD divided by the 2.501111111111111111111111111 USD/hour live class quote.
# The independent local timer also requests a stop through runpod_pilot.py.
sleep 8636
if runpodctl pod stop --help >/dev/null 2>&1; then
    runpodctl pod stop "$RUNPOD_POD_ID"
else
    runpodctl stop pod "$RUNPOD_POD_ID"
fi
