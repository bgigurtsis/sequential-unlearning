set -euo pipefail
cd /home/ubuntu/sequential-unlearning-projection-sprint-20260904
test "$(git rev-parse HEAD)" = 496c13b8faf54787ffbad7438844ec319c7e966d
git diff --exit-code HEAD -- scripts/eval_decay_scalar.py scripts/decay_scalar_normalization.py scripts/eval.py data/decay_scalar_prompts.json data/rehearsal_capability_prompts.json data/conversational_survival_generations.json data/probes.json data/ppl_text.txt
sha256sum -c <<'HASHES'
55ed6601e79736b8b895af1d202d46ac3c660e62ec0e88d4957218ee7c4dfd9c  derisk/whole_concept_jobs_v1/delta_protection_v1/projection_v1/models/e090_v1/model.safetensors
eb5fd5e97ddd07b56778733e9653c07312529cb00980a318fc3e1c4e3b5a8f1f  /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767/model-00001-of-00002.safetensors
fdde0e5aa5ced0fa203b3d50f4ab78168b7e3a3e08c6349f5cc9326666e1bb13  /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767/model-00002-of-00002.safetensors
c71847d32c794bea9b28a7c80678c29487e2e16b2ee593c990dcf56916f128b9  /home/ubuntu/sequential-unlearning/derisk/probe2_noise_v2/baseline/scalar.json
4379ad371c84760f38da59f4ec667083bee05423e3638cf039b3b3516e7220e8  /home/ubuntu/sequential-unlearning/derisk/probe2_noise_v2/anchor/scalar.json
e448843f96f3b2be0e6a744242ad5719f32bc1d948971b66759e0dcd4e8fdfd2  /home/ubuntu/sequential-unlearning/derisk/probe2_noise_v2/ladder/corruption_ladder.json
4040b330b82ef2e7b509e544edbd76df7441589b6b08cd8b4518237a7d778d79  data/probes.json
2e2a739855a1f4fd6d4384d44518fe1f3e25c23832be827d24047f9c2d929d3a  data/ppl_text.txt
HASHES
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export EVAL_TOKENIZER_ID=/home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767
SPRINT_OUT=derisk/whole_concept_jobs_v1/delta_protection_v1/sprint_20260904
MODEL=derisk/whole_concept_jobs_v1/delta_protection_v1/projection_v1/models/e090_v1
test ! -e "$SPRINT_OUT/e090_diagnostic_scalar_v1.json"
test ! -e "$SPRINT_OUT/e090_diagnostic_utility_ppl_v1.json"
date -u +'%Y-%m-%dT%H:%M:%SZ scalar start'
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python -u scripts/eval_decay_scalar.py "$MODEL" "$SPRINT_OUT/e090_diagnostic_scalar_v1.json" --tokenizer-model "$EVAL_TOKENIZER_ID" --judge-model "$EVAL_TOKENIZER_ID" --batch-size 8 --max-new-tokens 256 --seed 0 --normalisation-policy bidirectional_synthetic_v2 --baseline-json /home/ubuntu/sequential-unlearning/derisk/probe2_noise_v2/baseline/scalar.json --anchor-json /home/ubuntu/sequential-unlearning/derisk/probe2_noise_v2/anchor/scalar.json --ladder-json /home/ubuntu/sequential-unlearning/derisk/probe2_noise_v2/ladder/corruption_ladder.json > logs/projection-sprint-20260904/e090-diagnostic-scalar-v1.log 2>&1
date -u +'%Y-%m-%dT%H:%M:%SZ scalar complete; utility/PPL start'
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python -u scripts/eval.py "$MODEL" "$SPRINT_OUT/e090_diagnostic_utility_ppl_v1.json" > logs/projection-sprint-20260904/e090-diagnostic-utility-ppl-v1.log 2>&1
date -u +'%Y-%m-%dT%H:%M:%SZ diagnostic complete'
sha256sum "$SPRINT_OUT/e090_diagnostic_scalar_v1.json" "$SPRINT_OUT/e090_diagnostic_utility_ppl_v1.json"
