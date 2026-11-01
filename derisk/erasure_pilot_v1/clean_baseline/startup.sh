#!/bin/bash
set -eu
mkdir -p /workspace/task2
# Preserve the official image's SSH setup while the guarded workload waits for upload.
/start.sh > /workspace/task2/boot.log 2>&1 &
stop_self() {
    if runpodctl pod stop --help >/dev/null 2>&1; then
        runpodctl pod stop "$RUNPOD_POD_ID"
    else
        runpodctl stop pod "$RUNPOD_POD_ID"
    fi
}
export -f stop_self
# This independent guard survives an SSH disconnect or failure of the workload shell.
nohup bash -c 'sleep 3000; stop_self' > /workspace/task2/guard.log 2>&1 &
trap stop_self EXIT
# Upload, package installation, download, inference and archiving share one 50-minute ceiling.
timeout --signal=TERM --kill-after=30s 50m bash -c '
    until [ -f /workspace/task2/job.ready ]; do sleep 2; done
    bash /workspace/task2/job.sh
'
