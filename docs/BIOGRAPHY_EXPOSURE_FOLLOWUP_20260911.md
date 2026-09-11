# Biography reference exposure follow-up

**Latest review:** Recovered E3 completion reconciled: finished900 at01:50:52.929339UTC, finalCE0.06796697527170181,6297active exposures,medianstep0.494913628seconds; config and metrics match saved completion SHA pins. All18development snapshots/1260replies have now been read by GPU2 agent and integrated with raw-SHA-bound reviews; zero qualifying checkpoints. E3 final900 original/new targetuncertainty0/4 and3/4,retained8/8both,holiday0/1 and1/1,gaps9/10bothwithconfabulation; originalstories0/2 andidentity3/4, newstories2/2 identity4/4 ordinary3clear-to4upper. Invented telescope moon-through-mug, helmet blue-bike and cue lost-balance-night persist. All ambiguous scoring bounds remain disclosed, and none changes the failuredecision. Full CSV and closure atlogs/biography-20260911/E3_reference_comparison.csv and E3_review_closed.json. FinaladapterSHA c37540758c0e246ad68c2f063a096ca2b63ee685bf82c8e40389aae8946b66bc. E2 was never launched; remainingplannedcomparison is unresolved. Cloud transfer is still in progress, so experimentcompletion is not yet a claim of completeSSDbackup. The repository origin was verified PRIVATE/admin; the previous auto-review destination concern was resolved and commit6dc209d pushed. No acceptedmodel or humanrating exists.

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
