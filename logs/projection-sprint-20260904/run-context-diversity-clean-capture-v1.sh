set -euo pipefail
cd /home/ubuntu/sequential-unlearning-projection-sprint-20260904
test "$(git rev-parse HEAD)" = 496c13b8faf54787ffbad7438844ec319c7e966d
git diff --exit-code HEAD -- scripts/screen_merged_model.py scripts/screen_adapters.py
sha256sum -c <<'HASHES'
5ec39efe22c8464e37876a4dcfd497452b78780206f616775064ef493c5182ca  scripts/screen_merged_model.py
c69144eca887176cedb074fcdd8ac80e841d5504772198701546ca4d7fcd0b29  scripts/screen_adapters.py
36de55ce0b22bb23a489c2eb7efe5af3ac25d7ce8830ad30597bae319a20e1d1  scripts/build_context_diversity_prompts.py
d0ad5095b0a775153ab21a61caacda46a6ef53ebc75ac7c9a2ed0d386ef7eb93  config/whole_concept_jobs_v1/context_diversity_sprint_v1/training_preparation/probes.json
be5dc6ebd3d9a153ae7862d332e66e27044fc57651ad2ea0c5e457189cf664a2  config/whole_concept_jobs_v1/context_diversity_sprint_v1/training_preparation/manifest.json
eb5fd5e97ddd07b56778733e9653c07312529cb00980a318fc3e1c4e3b5a8f1f  /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767/model-00001-of-00002.safetensors
fdde0e5aa5ced0fa203b3d50f4ab78168b7e3a3e08c6349f5cc9326666e1bb13  /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767/model-00002-of-00002.safetensors
4667f2089529e8e7657cfb6d1c19910ae71ff5f28aa7ab2ff2763330affad795  /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767/tokenizer.json
bfe25c2735e395407beb78456ea9a6984a1f00d8c16fa04a8b75f2a614cf53e1  /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767/tokenizer_config.json
9059f680f4dbd1957f35cb44b9fdd6948f4792db7a7a35ee353ea42e68adf7ff  /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767/config.json
fe16baf728db49457cde32802cd7efc0ac8a7a9877dbe22fe3322b2d9dc6ccd9  /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767/chat_template.json
HASHES
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
date -u +'%Y-%m-%dT%H:%M:%SZ capture start'
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python -u scripts/screen_merged_model.py --model-id /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --tokenizer-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 --day-dir config/whole_concept_jobs_v1/context_diversity_sprint_v1/training_preparation --output derisk/whole_concept_jobs_v1/delta_protection_v1/sprint_20260904/context_diversity_clean_answers_v1.json --batch-size 16 --max-new-tokens 96
date -u +'%Y-%m-%dT%H:%M:%SZ capture complete'
sha256sum derisk/whole_concept_jobs_v1/delta_protection_v1/sprint_20260904/context_diversity_clean_answers_v1.json
