# Active concept-removal plan — September 5, 2026

The goal remains active: remove a concept and its nearest neighbours through saved model weights, preserve ordinary abilities, and establish whether the damage stays acceptable across31 sequential removals. Natural unfamiliarity is preferred; other behavioral absence that serves the artwork is acceptable. No current checkpoint satisfies the goal.

The user rejected the earlier proposed stop. Historical sprint deadlines and closed experiment queues are preserved in EXPERIMENTS.md; they do not justify ending the active goal after another failed candidate.

| GPU | Owner | Experiment |
| --- | --- | --- |
| RTX18.101.59.227 | Primary agent | Remove all68 surviving mean-protected contrast directions, up to136 with closure |
| L40S51.49.31.142 | Subagent projection_followup | Remove16 mean-protected contrast directions, up to32 with closure |

Run at most one owned GPU workload per host; preserve the unrelated RTX service. Both experiments start from the same pinned clean Gemma3-4B-it checkpoint and use separate outputs.

1. Shared clean capture is complete:520 employment/neighbour and520 nonemployment prompts, identical task formats and class counts, maximum152 tokens with no truncation. Both bases use the same68 class-mean contrasts. Evaluation answers never enter the fit.
2. Publish each edit independently into the token embedding and all68 attention/MLP output matrices. Account for post-branch normalization without inverting its singular scales. Verify every other tensor is unchanged and the saved model reloads with correct tied output weights.
3. Measure actual BF16 residual leakage. Generate quick40 and contextual12 regressions; read every answer for retained target meaning, useful ordinary behavior and looping. Linear geometry alone cannot establish concept removal.
4. Advance only a behavioral survivor to broader target/control conversations, actual legacy generations, perplexity, damage metrics and the untouched final audit. Preserve historical scores and identify target-bearing benchmark rows when interpreting collateral damage.
5. Once one edit qualifies, run actual sequential removals with preserved-concept checks and a measured damage curve. Projected dimension count does not prove31-edit safety.

Implementation checks passed:15 RTX math/surface tests,8 L40S capture tests, and a full native identity save/reload with exact clean shard hashes and verified tied embeddings. Rank4 captures82.51% of normalized training contrast energy versus37.75% forrank1, but semantic removal and low damage remain unproven.

The previous constrained repair reduced the damage scalar from13.4982 to7.1455 and recovered one control, but restored some employment knowledge. It remains exploratory. The subsequent contextual CE correction also failed. Neither those artifacts nor the completed local archive establish goal completion.

Exact settings, source/data hashes, findings and rejected interpretations are in EXPERIMENTS.md and config/whole_concept_jobs_v1/residual_projection_v1/contract_v1.json with its two_gpu_amendment_v1.json.


RTXrank4 native publication completed with exactly69 changed tensors and verified tied-head reload. Weight-space residuals are small but nonzero. Behavioral quick/context tests and actual forward leakage are the next checks.

L40Srank1 publication likewise verified69changed tensors and tiedreload. Both GPUs now proceed to independent evaluations, one owned workload each.


Rank4 result: rejected after52/52 incoherent responses, including all15 ordinary controls. The intended residual directions were numerically suppressed, so this is a destructive method outcome. Low dimension count did not protect general language. Rank1 evaluation continues independently; the user goal remains active.


Rank1 also failed:52/52 incoherent answers and0/15 usable controls despite effective numerical subspace suppression. Its contextual budget was96 tokens versus256 forrank4; both quick budgets were96. The mismatch does not change the clear collapse verdict. Both fixed arms are closed; the active goal continues with a diagnosis of shared-mean damage before the next method.


Next method is now frozen: preserve the clean nonemployment FIT mean vectors before choosing directions to erase. The failed closures overlapped89–96% of their energy; a136-dimensional protected span leaves substantial target contrast available. Root testsrank4 onRTX, subagent rank1 onL40S, same69-weight publisher and independent behavioralchecks. This is a justified geometric correction, not a demonstrated low-damage solution.


The corrected bases are fitted and verified to preserve the stored nonemployment means under the ideal projection (relative residual below4e-15). Root and subagent now publish the newrank4/rank1 models independently. Actual model behavior still requires testing.


The mean-protected four-direction checkpoint passed native publication and tied reload. Its behavioral evaluation now proceeds; mathematical preservation of stored averages is not yet evidence that the edited model preserves ordinary abilities.


The corrected one-direction checkpoint also passed native publication and tied reload. Both GPUs now evaluate the corrected models with matching quick and contextual token limits.


Mean-protected rank4 restores coherent generation on all52 development responses, and ordinary training means remain close to clean (2.63% relative change). Employment knowledge still appears extensively, so this is not unlearning. One physics control is wrong and the SteveJobs answer has a factual caveat. The correction fixes the collapse problem; the goal remains unfinished.


Protected rank1 also preserves coherent language and all12 primary controls, but retains employment knowledge. The next bounded comparison increases the protected edit to16 directions on the subagent GPU and the full68 available directions on the primary GPU. This tests the method’s remaining capacity; a high-rank result would still need evidence of acceptable damage across31 removals.


The stronger bracket implementation passed all19 targeted tests. Fit both bases from the existing pinned capture before publishing independently; no new training or evaluation data enters this fit. Existing protected rank1 means changed only1.35%, confirming that mean preservation alone does not remove the concept.


The shared stronger fit is complete:16 directions capture93.40% and68 capture100% of the surviving measured contrast. Both preserve stored ordinary means within the numerical gate. The two independent saved-model publications are next.


The RTX68 checkpoint passed saved-tensor and tied-reload checks. Its matched behavioral and forward-leakage evaluation is next; no semantic claim is established.


The L40S16 checkpoint passed saved-tensor and tied-reload checks. Its matched behavioral and forward-leakage evaluation is next; no semantic claim is established.


The full68-direction candidate failed: employment knowledge survives alongside widespread looping and lost ordinary answers. Removing more of this measured span does not solve the problem. The rank16 comparison remains underway; the next method must address a different failure mechanism.
