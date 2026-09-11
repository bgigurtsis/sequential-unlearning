# Biography reference exposure follow-up

**Latest review:** All current-campaign D0/D1/D2/D3 plus E3 fullrun packages are checksumverified on E SSD, with every savedadapter/config/optimizer/RNG file matching originalcompletion hashes (D0 continuation24files, allotherarms72files each). E3 archiveSHA50c6a3175f0299453ded4c94a929a231d6e1be6aa4bf4a71307457ac39637efa; its essential900copy also independentlyverified. Extracted execution3 runtime onSSD and rehashedall43frozeninputfiles successfully, no model loaded or holdout output generated. Initialfullrepositorybytecomparison checked12240files47.946399710GB with no excludedlinks; onlyfive documents/tool/pycache files editedduringthepass differed, and allfive were refreshed and rehashed. Later newrecords require finalrefresh after archival completes. Older teachingruns, selected/mergedmodels and fullvenvs are still transferring, so the fullhandoff remainsinprogress. No new training and no acceptedresult. Fullscopefinalverification will compare sourcepath inventories and rehash everyarchive before stop/shutdown.

Status: E3 completed 900 steps and failed reference qualification at every one of its 18 checkpoints. E2 completed CPU preflight but never launched before the interrupted turn. Execution is now paused for Billy's urgent SSD backup before VM access ends. The original D0–D3 comparison remains closed with all 3,990 new development replies reviewed. This separate follow-up responded to Billy's later instruction to continue toward success; it did not change the original comparison or its failed-reference stopping rule.

The working hypothesis is that the existing batch mix gives too little exposure to uncertainty relative to positive biography answers. Current evidence does not establish that cause: D2/D3 sometimes improve uncertainty on retained details, but holiday answers still invent places or substitute retained stories. More uncertainty exposure may also damage retention. The two development sets have now been repeatedly inspected; they are adaptive development evidence. Fresh confirmation v3 remains unused.

## Controlled comparison

Both jobs start fresh from the exact pinned base. They use byte-identical D3 data, including all 1,734 IDs, and the same vacation omission rule. No question or answer is added or edited. The existing 900-step materialized seed-20260 batch plan supplies the starting positions.

| Job | Operator | Change to each original batch | Fact / narrative / chat / gap / identity slots |
|---|---|---|---|
| E2 | Main, GPU1 | Replace the first fact slot with one existing gap record | 1 / 2 / 2 / 2 / 1 |
| E3 | Subagent, GPU2 | Same replacement as E2, plus replace the first chat slot with a second existing gap record | 1 / 2 / 1 / 3 / 1 |

Every other original ID and position is preserved. The additional gap queues are deterministic and avoid duplicates within a batch. Both jobs have 591 active fact, 1,206 narrative and 900 identity exposures after omission. E2 has 1,800 chat and 1,800 gap exposures; E3 has 900 chat and 2,700 gap exposures. Both have 6,297 active exposures, compared with D3's 6,006. E2/E3 leave 86/87 corpus IDs unexposed. These are exposure changes, not an order-only experiment.

The optimizer and training implementation remain unchanged: seed 20260, rank32/alpha64, text LoRA, FP32 adapter parameters, BF16/eager computation, microbatch8, equal-record answer loss including termination token106, maximum length384, AdamW peak learning rate1e-4, 30-step warmup, cosine horizon900/minimum ratio0.1. Save and evaluate every50 steps. No resuming a changed plan, no continuation beyond900.

## Budget and gates

The initial follow-up allocation was two GPU-hours within the existing 24-hour total. Capacity recovery and setup consumed 0.81445088 hours before 01:41 UTC; the explicitly recorded execution-3 operational extension allowed at most two additional hours through 02:41, without changing scientific inputs or E3's worker limit. Both OS guards fired at 02:40 UTC. See the execution-3 freeze and SSD handoff for accounting; overlapping windows must not be added twice. Backup-only CPU running intervals are recorded separately and conservatively charged against the same overall ceiling. The historical launch guards required at least45 minutes remaining and34 GiB free; expired windows must not be reused.

A reference must meet every existing gate on both35-item suites: uncertainty on all four omitted holiday questions and holiday open recall, retained facts and stories, ordinary responses, honest identity and appropriate gaps. Fabricated substitutes fail. If neither reference qualifies through900, close this follow-up without removal.

If a reference qualifies, rank candidates by fewest changed batch slots, earliest passing common checkpoint, then recipe ID. Qualify its taught counterpart using the same plan, seed and training step; never combine E2 and E3. Subsequent reference seeds, merge/reload, confirmation and removal retain the original plan's gates. The first selected pair failing confirmation ends this selection process. Distillation remains explicitly retraining-assisted response distillation. No model is an accepted artwork without Billy's actual usability and artist ratings.

## Reproduction and review

The new freeze pins the unchanged old inputs, deterministic plan builder, wrapper, tests, original comparison closure and generated exposure audit. The wrapper reuses the existing trainer and CPU/completion checks, and verifies the actual saved plan and parsed configuration. Existing artifacts remain immutable. All findings, errors and interpretation changes must be appended to EXPERIMENTS.md, reflected in PROJECT_MEMORY.md, and committed/pushed before a materially different experiment.

Three local plan tests and all27 runtime CPU tests passed on each host. Both CPU preflights verified masking/termination, exact inputs, omission and actual launch arguments. E3's completion verifier checked every logged learning rate and exposure, its saved configuration and checkpoint hashes. E2 produced no model output and has no training run. Passing implementation checks does not establish scientific success.
