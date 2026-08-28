#!/bin/bash
set -e
cd ~/sequential-unlearning
PY=venv/bin/python
echo '=== smoke 1: scalar eval, clean gemma, limit 2 per set ==='
$PY scripts/eval_decay_scalar.py google/gemma-3-4b-it derisk/probe2_noise/smoke/scalar_limit2.json --limit 2 --batch-size 4
echo '=== smoke 2: alpha=0 dose ==='
$PY scripts/apply_decay_noise.py --model google/gemma-3-4b-it --alpha 0 --seed 0 --output-dir derisk/probe2_noise/smoke/alpha0_ckpt
echo '=== smoke 3: bit-identity check ==='
$PY scripts/check_alpha0_identity.py google/gemma-3-4b-it derisk/probe2_noise/smoke/alpha0_ckpt derisk/probe2_noise/smoke/alpha0_identity.json
rm -rf derisk/probe2_noise/smoke/alpha0_ckpt
echo '=== smoke 4: corruption ladder on smoke generations, limit 8 ==='
$PY scripts/build_corruption_ladder.py derisk/probe2_noise/smoke/scalar_limit2.json derisk/probe2_noise/smoke/ladder_limit8.json --limit 8 --batch-size 4
echo '=== SMOKE COMPLETE ==='
