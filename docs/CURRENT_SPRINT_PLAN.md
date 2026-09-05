# Active concept-removal plan — September 5, 2026

The goal remains active: remove a concept and its nearest neighbours through saved model weights, preserve ordinary abilities, and establish whether the damage stays acceptable across31 sequential removals. Natural unfamiliarity is preferred; other behavioral absence that serves the artwork is acceptable. No current checkpoint satisfies the goal.

The user rejected the earlier proposed stop. Historical sprint deadlines and closed experiment queues are preserved in EXPERIMENTS.md; they do not justify ending the active goal after another failed candidate.

| GPU | Owner | Experiment |
| --- | --- | --- |
| RTX18.101.59.227 | Primary agent | Remove4 learned residual directions, up to8 with final-normalization closure |
| L40S51.49.31.142 | Subagent projection_followup | Remove1 learned residual direction, up to2 with closure |

Run at most one owned GPU workload per host; preserve the unrelated RTX service. Both experiments start from the same pinned clean Gemma3-4B-it checkpoint and use separate outputs.

1. Shared clean capture is complete:520 employment/neighbour and520 nonemployment prompts, identical task formats and class counts, maximum152 tokens with no truncation. Both bases use the same68 class-mean contrasts. Evaluation answers never enter the fit.
2. Publish each edit independently into the token embedding and all68 attention/MLP output matrices. Account for post-branch normalization without inverting its singular scales. Verify every other tensor is unchanged and the saved model reloads with correct tied output weights.
3. Measure actual BF16 residual leakage. Generate quick40 and contextual12 regressions; read every answer for retained target meaning, useful ordinary behavior and looping. Linear geometry alone cannot establish concept removal.
4. Advance only a behavioral survivor to broader target/control conversations, actual legacy generations, perplexity, damage metrics and the untouched final audit. Preserve historical scores and identify target-bearing benchmark rows when interpreting collateral damage.
5. Once one edit qualifies, run actual sequential removals with preserved-concept checks and a measured damage curve. Projected dimension count does not prove31-edit safety.

Implementation checks passed:15 RTX math/surface tests,8 L40S capture tests, and a full native identity save/reload with exact clean shard hashes and verified tied embeddings. Rank4 captures82.51% of normalized training contrast energy versus37.75% forrank1, but semantic removal and low damage remain unproven.

The previous constrained repair reduced the damage scalar from13.4982 to7.1455 and recovered one control, but restored some employment knowledge. It remains exploratory. The subsequent contextual CE correction also failed. Neither those artifacts nor the completed local archive establish goal completion.

Exact settings, source/data hashes, findings and rejected interpretations are in EXPERIMENTS.md and config/whole_concept_jobs_v1/residual_projection_v1/contract_v1.json with its two_gpu_amendment_v1.json.
