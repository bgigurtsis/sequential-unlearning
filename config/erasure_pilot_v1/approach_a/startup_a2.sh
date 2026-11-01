#!/usr/bin/env bash
set -eu
mkdir -p /workspace/approach_a2
/start.sh > /workspace/approach_a2/boot.log 2>&1 &
# Local helper guard terminates the pod at this same deadline.
sleep 6621
kill -TERM 1
