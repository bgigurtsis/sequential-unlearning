# Biography reference exposure follow-up

**Latest review:** E3 execution2 deployed to original GPU2 newDNS98.83.136.254 with verified41-file manifest610eb20aa83ded8978007c088a5ec610c64efbff37c855edec13e8bb43dced87. Runtime27tests passed0skip6.295sec; operational receipt E3_execution2_deployment_cpu_tests.json. CPUpreflight at01:06:13.822447Z verified12exactbase/tokenizer pins,1734unchanged D3records/261omissions,max133tokens,pairedplan/omission invariants and actual parsed CLI; no model loaded/outputs. E3 plan SHAa637f7c5eec3351bfaadb18032093fcc047d596b072f39853018aecb7680b8e1; preflightSHA8da5bfe320960d1a77d71d6281e3a60b3fea1c9fdf69bacaa4a24a3c30bdaf59. Exact shutdown timer01:58:28UTC now Accuracy1sec; worker cutoff01:57:58. E3 ready independent launch after this commit; primarycapacityretry/recovery continues. No scientificmethodchange or observed modelresult.

Status: frozen, not launched. The original D0–D3 comparison is closed: all 3,990 new development replies reviewed, final checkpoints backed up, and both instances confirmed stopped. This separate follow-up responds to Billy's later instruction to continue toward success. It does not change the original comparison or its failed-reference stopping rule.

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

The follow-up has a two-GPU-hour ceiling, charged against the existing 24-hour total. Its frozen start/deadline allow at most one hour across both hosts, including boot/setup, evaluation and idle running time. The previous campaign's actual running-time upper bound is carried forward. New host guards request shutdown60 seconds before the frozen deadline; trainer termination begins90 seconds earlier, with20 seconds allowed before forced process termination. AWS state remains checked through stopped. A launch requires at least45 minutes remaining and34 GiB free per host.

A reference must meet every existing gate on both35-item suites: uncertainty on all four omitted holiday questions and holiday open recall, retained facts and stories, ordinary responses, honest identity and appropriate gaps. Fabricated substitutes fail. If neither reference qualifies through900, close this follow-up without removal.

If a reference qualifies, rank candidates by fewest changed batch slots, earliest passing common checkpoint, then recipe ID. Qualify its taught counterpart using the same plan, seed and training step; never combine E2 and E3. Subsequent reference seeds, merge/reload, confirmation and removal retain the original plan's gates. The first selected pair failing confirmation ends this selection process. Distillation remains explicitly retraining-assisted response distillation. No model is an accepted artwork without Billy's actual usability and artist ratings.

## Reproduction and review

The new freeze pins the unchanged old inputs, deterministic plan builder, wrapper, tests, original comparison closure and generated exposure audit. The wrapper reuses the existing trainer and CPU/completion checks, and verifies the actual saved plan and parsed configuration. Existing artifacts remain immutable. All findings, errors and interpretation changes must be appended to EXPERIMENTS.md, reflected in PROJECT_MEMORY.md, and committed/pushed before a materially different experiment.

Local preparation: three tests pass for deterministic paired changes, category quotas, exact omission behavior, actual launch arguments and rejection of a tampered plan. Runtime masking/termination tests and CPU preflights remain required before launch. No result is inferred from these implementation tests.
