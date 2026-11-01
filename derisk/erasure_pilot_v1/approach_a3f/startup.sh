#!/usr/bin/env bash
set -eu
mkdir -p /workspace/approach_a3f
/start.sh > /workspace/a3f_boot.log 2>&1 &
sleep 2775
kill -TERM 1
