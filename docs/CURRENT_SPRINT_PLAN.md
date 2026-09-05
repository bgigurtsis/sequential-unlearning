# Active concept-removal plan — September 5, 2026

Find a saved-weight edit that removes employment and its required semantic neighbours while keeping ordinary conversation useful. Natural unfamiliarity is preferred; another useful form of absence can serve the artwork. No candidate has qualified. Historical sprint deadlines do not close the active goal.

| GPU | Owner | Current experiment |
| --- | --- | --- |
| RTX,18.101.59.227 | Primary agent | Clean full-band unfamiliarity,rank32/alpha64 |
| L40S,51.49.31.142 | Subagent projection_followup | Same experiment,rank8/alpha16 |

Keep one owned GPU workload on each host and preserve unrelated RTX service8186. Use unique project output paths and the same pinned clean Gemma3-4B-it source.

## Current decision

Both sequential read-side edits passed native mechanical checks but retained employment knowledge. Earlier global projections either retained knowledge or damaged ordinary responses. Those methods are rejected; geometric suppression is not evidence of unlearning.

The next pair tests broader trainable capacity and joint training coverage. It trains eight short unfamiliarity replies across all34 text layers, exactly238 attention/MLP modules, with vision and base weights frozen. Rank is the controlled difference between GPUs. This is a behavioral hypothesis, not proof of irreversible knowledge deletion.

## Decision path

1. Data and CPU gates passed:1576 targets (1056 direct/scenario and520 contextual),177 generic retention texts,2753 chat retention rows including3 copies of520 matched ordinary examples. Exact normalized evaluation exclusion found zero overlaps across467 distinct prompts. Builder3/3 and trainer31/31 tests passed. Target/chat sequences fit256 tokens;16 generic texts are clipped by the existing policy. Former projection diagnostic rows are now training, never fresh evidence.
2. Run two-step full-objective memory qualification on each GPU. Use non-reentrant checkpointing, BF16 base/FP32 adapters,16/4/8 batches, weights10/30/100, LR2e-5, no answer suppression or snapshots. Require finite loss/gradients, exact text-only scope and recorded peak memory. Integrate results before full training; do not silently reduce batches after OOM.
3. Train192 steps with snapshots64/128/192. Seed34001; cyclic sampling draws8 direct and8 contextual records per batch without replacement within each cycle. Full coverage by132/65 steps. Audit every32 for diagnostics only; do not stop or select on proxy scores.
4. After training finishes, evaluate quick40 responses at96 tokens for each checkpoint, then contextual12 at256 tokens for behavioral qualifiers. Read the answers. Incorrect or incoherent responses receive no absence credit. These are reused development regressions.
5. Merge and verify a behavioral survivor, then measure broader target/neighbour coverage, conversations, ordinary generations, perplexity and collateral damage. Separate target-bearing benchmark rows so knowledge restoration is not called repair. Reserve the untouched final audit for a genuine qualifier.
6. Once a single edit qualifies, measure successive removals, retention of earlier holes and unrelated abilities toward31 removals. A successful single edit alone does not establish scalability.

Exact settings:config/whole_concept_jobs_v1/wide_unfamiliarity_v1/contract_v1.json and data_v1/manifest.json. Append findings to EXPERIMENTS.md, update PROJECT_MEMORY.md and affected claims, then commit/push before changing experiments. A failed run or completed archive does not complete the goal.

Both two-step GPU qualifications passed: exact238 text modules/476 adapter tensors, finite losses and gradients. Peak allocated memory20.77GB onRTX and19.96GB onL40S. The192-step runs are next with the same settings. This confirms executability of the sampled steps, not forgetting or universal memory headroom.

September5 04:17UTC: RTXrank32 completed192 steps with full1056+520 target coverage and finite gradients throughout; three saved adapters advance to quick behavioral screening. L40Srank8 training continues. No forgetting conclusion follows from training metrics.
