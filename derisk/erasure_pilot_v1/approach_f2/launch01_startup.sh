#!/bin/bash
set -eu
mkdir -p /workspace/f2
/start.sh > /workspace/f2/boot.log 2>&1 &
# The helper-based pod timer is armed before job.ready is uploaded.
timeout --signal=TERM --kill-after=30s 3585s bash -c '
    until [ -f /workspace/f2/job.ready ]; do sleep 1; done
    bash /workspace/f2/job.sh
'
