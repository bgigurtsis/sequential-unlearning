#!/usr/bin/env bash
set -eu
mkdir -p /workspace/approach_a3
/start.sh > /workspace/approach_a3/boot.log 2>&1 &
sleep 5752
kill -TERM 1
