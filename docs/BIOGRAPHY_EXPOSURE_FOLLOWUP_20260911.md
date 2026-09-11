# Biography reference exposure follow-up

**Latest review:** E2/E3 exposure follow-up frozen under latest continue instruction: SHA 51ad60f58a47b237ce9a9208dc472e5ee194bb60e32e368267549b8607aca9b6,38 pinned files, start2026-09-11T00:47:31Z, deadline2026-09-11T01:47:31Z,2GPU-hour ceiling within24total; prior charge3.2366129864h. Fresh base starts, byte-identical D3 data, same seed20260/rank32/alpha64/record loss/micro8/warmup30/cosine900. E2 main replaces900fact slots with existing gaps; E3 subagent makes same replacement plus900chat slots. Both6297active exposures, narrative1206/identity900/facts591 fixed; E2chat1800/gap1800,E3chat900/gap2700. All other batch positions unchanged. Original campaign fully closed/stopped with verified archives. Both35suites now adaptive; freshv3unused. All gates unchanged. Next restart exact hosts, refreshDNS, install01:46:31Z shutdown guards, run27CPUtests and CPUpreflights, then launch if45minutes remain. No model output or launch yet.

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
