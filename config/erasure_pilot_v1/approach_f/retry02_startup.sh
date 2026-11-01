#!/bin/bash
set -eu
mkdir -p /workspace/f
/start.sh > /workspace/f/boot.log 2>&1 &
# The helper-based pod timer is armed before job.ready is uploaded.
timeout --signal=TERM --kill-after=30s 6129s bash -c '
    until [ -f /workspace/f/job.ready ]; do sleep 1; done
    bash /workspace/f/job.sh
'
