# SSD handoff — 11 September 2026

**Current status:** Both original instances are confirmed **terminated** as of 2026-09-11T14:14:16.351326+00:00. Both EBS roots remain **available**. All cloud archives and the pre-termination repository snapshot passed verification. `HANDOFF_COMPLETE.json` and its referenced post-termination report are the final completion authority; the marker is written only after those checks pass. The historical preparation notes below preserve the sequence of actions.

The current task is to preserve the project before VM access ends at 17:00 London (16:00 UTC). Billy retains this PC. Experiments are paused for this backup; no new training is authorized by the backup operation itself. Billy subsequently instructed that both instances must be TERMINATED after the SSD backup and all checks are complete. This overrides the earlier stop-only instruction for these two instances. Preserve their EBS data volumes as extra recovery copies; deleting volumes was not requested.

Destination: `E:\sequential-unlearning-handoff-20260911` on the 4 TB Crucial E: SSD. The initial repository copy preserved 12,097 files / 44.651 GiB with zero Robocopy failures, including `.git`, uncommitted and untracked work, local checkpoints, and earlier project artifacts. A final refresh and integrity verification are required before declaring the handoff complete.

## Contents and verification

- `repository/`: full working directory, including unrelated existing changes preserved without modification.
- `context/current-project-session.jsonl`: a private snapshot of this project's conversation. It can contain credentials from earlier messages; it must stay private. The archive directory has restricted Windows permissions. Authentication tokens from the global Codex installation are not needed or copied.
- `cloud/gpu1/` and `cloud/gpu2/`: separate, portable `.tar.gz` packages containing every file beneath each host's `/home/ubuntu/biography-archive` and `/home/ubuntu/biography-runtime`. Preserve the two host trees separately when restoring.
- Every cloud package contains `__backup__/contents.json`, with original paths, modes, links, file sizes and SHA-256 hashes computed while reading the source. A `.verified.json` receipt is created only after rereading the local archive and matching every regular file and all path/link metadata. Its outer archive hash also permits later verification. `.partial` files are incomplete and cannot be counted as saved.
- `inventory.json` describes full cloud scope, `progress.json` is temporary progress, and `complete.json` records completion of that host's package inventory. GPU2's identical base model is intentionally shared with the GPU1 copy; verify its 12 pinned hashes against both host freezes before accepting that exception.
- Python packages, OS package versions, interpreter dependencies, Python 3.13 executable/stdlib, and the complete virtual environment are included in `biography-runtime/recovery_environment` and the runtime packages. The venv alone is not a portable operating system; use the recorded Ubuntu/CUDA environment on a compatible Linux NVIDIA host.
- `system/gpu1/` and `system/gpu2/`: verified supplements containing `/usr/lib/python3/dist-packages`, `/usr/share/python-babel-localedata`, `/usr/share/ieee-data`, and `/var/lib/ieee-data`. Both venvs include system site packages, so these are required alongside the venv. Each supplement preserves 12,913 files and 13 links; independent source inventories check all paths, sizes and link targets.

The local archive is private: the full working directory includes its existing `.env` and temporary files, and the conversation contains sensitive historical text. Do not publish the archive. SSH keys remain at `C:/Users/Billy/Downloads/testbox.pem` and `sandbox-test.pem` on this retained PC. New AWS credentials can be configured later; do not put them into Git or public recovery manifests.

## Exact experimental state

There is **no accepted taught/reference pair, no accepted removal model, and no artwork success**. Missing target names or low training loss do not establish success.

1. The original D0/D1/D2/D3 reference campaign is closed with zero qualifying references. It covered 60 new checkpoints / 3,990 new replies plus the reused D0 history. See `docs/BIOGRAPHY_CAMPAIGN_20260910_RESULTS.md`, `logs/biography-20260910/reference_stage_closed.json`, and the immutable campaign freeze. All four final step-900 checkpoints already have independently verified local copies in `snapshots/biography_campaign_20260910_D*_step900`.
2. The subsequent E2/E3 exposure comparison uses the same D3 corpus, seed 20260, base, optimizer and 900-step horizon. E2 replaces one original fact slot per batch with a gap record; E3 also replaces one chat slot. It changes exposure, not merely ordering. Both development sets are adaptive. Fresh confirmation v3 remains unused; preserve it without inspecting its prompts until a pair qualifies.
3. E3 launched on GPU2 at 01:09:15.934708 UTC in `/home/ubuntu/biography-runtime/exposure_20260911_execution2`, writing `/home/ubuntu/biography-archive/exposure_20260911_execution2/E3_Ra_run900`. E3 finished step 900 at 01:50:52.929339 UTC. All 18 checkpoints / 1,260 replies were reviewed by the GPU2 agent: none qualified. Config and metrics match completion pins; final adapter SHA-256 is `c37540758c0e246ad68c2f063a096ca2b63ee685bf82c8e40389aae8946b66bc`. See `logs/biography-20260911/E3_review_closed.json` and the full comparison CSV.
4. E2 **did not launch**. Its execution-3 CPU preflight completed at 01:43:46.457317 UTC, with 27 CPU tests passing, 1,734 training records, 261 omitted vacation records, maximum 133 tokens, zero model outputs, exact data/plan/base hashes, and parsed launch arguments. The turn was interrupted before launch. The recovered execution-3 archive contains the preflight, not a trained E2 model.
5. Do not select a taught/reference pair across different recipes or steps. If the reference gate eventually passes, train the matched taught counterpart and reference seeds, merge/hash/reload, then use the original exposed confirmation as regression and fresh v3 once. Stop selection after a first chosen pair fails confirmation. Actual Billy usability and artist ratings remain pending.

Core settings: text LoRA rank 32 / alpha 64; microbatch 8; equal-record answer CE including end-of-turn token 106; BF16/eager; seed 20260; peak learning rate 1e-4; 30-step warmup; cosine horizon 900; minimum ratio 0.1; save/evaluate every 50; no continuation beyond 900. The exact base is `093f9f388b31de276ce2de164bdc2081324b9767`, with all 12 files pinned in the freezes.

## Budget and infrastructure

Original campaign charge upper bound: 3.2366129864 summed running instance-hours. The recovery-era execution-3 operational envelope explicitly added 0.81445088 accrued hours before 01:41 UTC and at most two further hours through 02:41, making the total upper bound 6.0510638664 through that window. This is an operational extension of the follow-up's initially planned two-hour allowance; it does not alter scientific settings. Avoid adding overlapping envelopes twice.

Both hosts were confirmed stopped at 10:47:19 UTC after the overnight shutdown timers. Backup-only running intervals beginning later that morning must be recorded separately, conservatively within the original 24-hour total. No training occurs during CPU recovery.

- GPU1: `i-0ec24180dca5a32cd`, root `vol-0711b891ca9e9ee48`, original private hostname `ip-172-31-87-196`, AZ us-east-1b.
- GPU2: `i-015ec08311c78e068`, root `vol-05a5d3c559391280d`, original private hostname `ip-172-31-42-127`, AZ us-east-1d.
- Both originally g6e.2xlarge / L40S. For urgent backup, capacity failures were bypassed by reversible stopped-instance changes to CPU-only m6i.large. Preserve these volumes. After all SSD checks pass, terminate the two compute instances under Billy's latest explicit instruction, with root-volume DeleteOnTermination=false verified first. Public addresses change after starts and must not be taken from stale documents.
- A private recovery AMI `ami-0f82bb3c76bbe0305` and snapshot `snap-0c1bc1d6ce7b8c0d2` were created earlier. No replacement instance was launched during the failed alternate-AZ attempts. These cloud resources are secondary copies, not substitutes for the SSD verification.
- The original public software image is `ami-0effbaf08d53c60d4`, Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.13 (Ubuntu 26.04), image dated 20260905. The active isolated Python environment has its own captured package versions.

## Restoring and continuing

1. Start by reading this file, `PROJECT_MEMORY.md`, the most recent appended entries in `EXPERIMENTS.md`, the campaign results, and the exposure follow-up document. Historical instructions in older documents are provenance; they do not override Billy's current request.
2. Verify all `.tar.gz` package hashes against their `.verified.json` receipts. For a deeper check, run `python scripts/backup_biography_to_ssd.py verify PATH_TO_PACKAGE`. This checks archive file contents without extracting or executing them.
3. On separate compatible Linux restoration targets, extract each host's packages under a chosen root. Members retain paths such as `home/ubuntu/biography-archive/...`; extracting with `tar -xzf PACKAGE -C /` on the intended fresh host restores the original absolute layout. Review the destination first. Restore GPU1's base package onto GPU2's restoration target too.
4. Recreate the recorded Python/OS/CUDA environment or restore the captured venv and Python system files on a matching fresh system. After extracting the outer runtime packages, also extract `/home/ubuntu/biography-runtime/recovery_environment/python-system.tar.gz` to `/`: it contains the Python 3.13 executable and standard library, which the venv links need. Extract that host's `system/gpuN/python-system-supplement.tar.gz` to `/` as well. Do this only on the intended matching restoration host, since these paths contain system files. Validate import versions, token IDs, model hashes and merged-model behavior. Hardware must provide sufficient NVIDIA GPU memory before training. The captured pip-check output includes pre-existing missing cffi/charset-normalizer warnings; no environment repair was attempted during backup.
5. Old manifests contain expired wall-clock windows and original hostnames. Preserve them unchanged as evidence. Create a new reviewed execution envelope with current hosts/timing and reconciled budget, keeping scientific inputs pinned. Never bypass the guards or blindly rerun an expired launch command.
6. E3's full review is complete and failed. Verify its recovered checkpoint provenance. The next unexecuted scientific job is the already frozen E2 reference run, subject to the user's next execution instruction and remaining budget. No removal experiment can start from an invalid reference.

Preserve all failures. Main model writes code/data and integrates findings; Luna may perform bounded reading only. The user requested the main agent for one GPU and a subagent for the other. After findings, append `EXPERIMENTS.md`, update memory and affected claims, then commit/push only this work. Keep unrelated changes intact.

The final backup verification report, written after transfers finish, is authoritative for which bytes are actually on the SSD. This guide alone is not a completion receipt.

Termination is guarded by `scripts/finalize_biography_instances.py`: final verification reports and complete queues must exist, and a fresh AWS description must show the exact two expected roots with DeleteOnTermination=false. It writes AWS receipts; it does not delete volumes. Offline gate tests passed before any live termination.

The cloud verification timestamp must follow every completed transfer, and the final repository verification must follow cloud verification. An accepted termination request is not completion: run a subsequent AWS status check and confirm both instances are `terminated` and both retained volumes remain present before writing HANDOFF_COMPLETE.json.


## Verified cloud capture

Both transfers and independent cloud verification passed at 2026-09-11T14:03:48.028644+00:00. The 290 cloud packages contain 346,222,581,944 archive bytes and preserve 385,189,018,160 source bytes, excluding the intentionally shared GPU2 base duplicate. Both system supplements also passed. Full receipts are cloud-verification-final.json at the SSD root and logs/biography-20260911/ssd_cloud_capture_complete.json in the repository.

The system/gpuN-initial folders and initial/intermediate repository verification reports are retained as audit history; use system/gpu1 and system/gpu2 for restoration. The initial repository report recorded five files changing during verification; the subsequent full check passed. Only the final handoff marker and its referenced reports establish completion. Repository refresh and termination are still pending at this entry.


## Termination and accounting

AWS confirms i-0ec24180dca5a32cd and i-015ec08311c78e068 terminated; their roots vol-0711b891ca9e9ee48 and vol-05a5d3c559391280d remain available. The recovery AMI and snapshot also remain. Raw receipts are in repository/logs/biography-20260911/ssd_termination_request and ssd_termination_status_1; ssd_termination_confirmed.json provides the summary. No new compute instance remains from this backup operation.

The recorded CPU-backup interval upper bound is 6.858378 summed hours. With the prior operating envelope, the recorded total is 12.909442 hours. The prior portion uses OS shutdown evidence; its exact AWS stop-transition timestamp was not recovered. Preserve this limitation when reconciling billing or planning another campaign.
