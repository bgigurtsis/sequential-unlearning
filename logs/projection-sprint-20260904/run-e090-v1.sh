set -eu
cd /home/ubuntu/sequential-unlearning-projection-sprint-20260904
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python -u scripts/project_checkpoint_delta_retain_subspace.py project \
 --clean-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 \
 --tokenizer-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 \
 --edited-model /home/ubuntu/sequential-unlearning/derisk/whole_concept_jobs_v1/merged_step033_focused6_fullwall_replay_step064_v1 \
 --expected-edited-logical-sha256 7eedf4b2d316a9518577917acd35bf2c04d77cafb095ff238c1452a24cfafbbf \
 --expected-edited-weight-sha256 b8527608bb60269959e6f7694c12627dd0194baff772e2b72b8c1240080e5690 \
 --retain-json derisk/whole_concept_jobs_v1/retain_nonjob_244.json \
 --retain-json derisk/whole_concept_jobs_v1/preserve_clean_plus_context_multiturn6x_1808.json \
 --evaluation-json config/whole_concept_jobs_direct_v1/probes.json \
 --evaluation-json config/whole_concept_jobs_natural_v2/probes.json \
 --evaluation-json config/whole_concept_jobs_v1/probes.json \
 --evaluation-json config/whole_concept_jobs_hard_v1/probes.json \
 --evaluation-json config/whole_concept_jobs_hard_v1/conversations.json \
 --evaluation-json config/employment_sprint_20260904_final/probes.json \
 --evaluation-json config/employment_sprint_20260904_final/conversations.json \
 --expected-retain-records 2052 --layers 12-19,28-33 --max-length 256 --max-prompts 2052 \
 --batch-size 4 --cutoff-tie-rtol 1e-10 --retained-energy 0.90 \
 --cache-dir derisk/whole_concept_jobs_v1/delta_protection_v1/projection_v1/cache_v1 \
 --output-dir derisk/whole_concept_jobs_v1/delta_protection_v1/projection_v1/models/e090_v1 \
 > logs/projection-sprint-20260904/e090-v1.log 2>&1
/home/ubuntu/sequential-unlearning/venv-g6e/bin/python -u scripts/screen_merged_model.py \
 --model-id derisk/whole_concept_jobs_v1/delta_protection_v1/projection_v1/models/e090_v1 \
 --tokenizer-model /home/ubuntu/sequential-unlearning-clean-snapshot-093f9f388b31de276ce2de164bdc2081324b9767 \
 --day-dir config/employment_sprint_20260904_quick --batch-size 16 --max-new-tokens 96 \
 --output logs/projection-sprint-20260904/e090-quick-v1.json \
 > logs/projection-sprint-20260904/e090-quick-v1.log 2>&1
