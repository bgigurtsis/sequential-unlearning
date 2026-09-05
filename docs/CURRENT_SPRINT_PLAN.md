# Current concept-removal plan

Find a saved-weight edit that removes employment and its semantic neighbours while preserving ordinary conversation. Natural unfamiliarity is preferred. No candidate has qualified, and the goal remains active.

The latest eight-reply checkpoint gives unfamiliarity on14/28 conversational targets and26/36 broader development targets. Its ordinary answers remain mostly useful. Converting training to a single reply did not improve generalization: unfamiliarity fell to8/2/1 across its three snapshots despite near-zero training loss. Earlier methods and rejected claims remain in EXPERIMENTS.md.

| GPU | Owner | Next experiment |
| --- | --- | --- |
| RTX,18.101.59.227 | Primary | Add288 natural conversational training prompts, with old-corpus replay |
| L40S,51.49.31.142 | Subagent projection_followup | Continue on the old1576 prompts as an exposure control |

Both resume the same balanced8 step16 adapter and use the same eight unfamiliarity replies. Keep rank32/alpha64, target and chat first-five-token weight8, original token denominators, weights10/30/100, LR2e-5, seed34004, batches16/4/8, max256. Run96steps with24/48/96 snapshots. This compares whole training recipes: adding new prompts also changes old-topic sampling proportions.

1. Capture clean answers for the new prompts, pin dataset hashes and verify tokenization. The288 prompts were checked against467 evaluation prompts for exact overlap; they remain adaptive training data, not fresh tests.
2. Verify exact parent reload and run a two-step full-objective qualification on each GPU. Record and push before full training.
3. After96steps, record finite gradients, coverage, memory and checkpoint hashes. Review40 quick answers per snapshot. All28 target answers unfamiliar, at least11/12 ordinary answers useful and no loops permits provisional contextual testing only.
4. A survivor must pass broader target/neighbour and ordinary controls, conversations, merge/reload and the reserved fresh audit. Wrong answers and loops receive no absence credit.
5. After a first edit qualifies, test successive removals and retention of previous holes toward31. One edit does not establish scalability.

Keep one owned workload per GPU and preserve unrelated RTX service8186. Append exact findings to EXPERIMENTS.md, update PROJECT_MEMORY.md and affected claims, then commit and push before changing methods. Finished runs and failed candidates do not complete the goal; the historical six-hour deadline was superseded by the user's continuation instructions.

Contract: config/whole_concept_jobs_v1/wide_unfamiliarity_v1/natural_coverage_v1/contract_v1.json.


Natural coverage data ready:1864 targets=288 new conversational prompts+1576 unchanged old replay; retain177/chat2753 unchanged. All target sequences27–76tokens including one EOS, zero truncation at256. Clean answers captured and pinned. L40S exposure-control two-step qualification passed; root natural-coverage two-step qualification next before full96.
