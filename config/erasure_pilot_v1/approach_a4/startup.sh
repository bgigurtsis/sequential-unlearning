#!/usr/bin/env bash
set -eu
mkdir -p /workspace/approach_a4
/start.sh > /workspace/a4_boot.log 2>&1 &
sleep 9360
kill -TERM 1
