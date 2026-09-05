# Active concept-removal plan — September 5, 2026

Find a saved-weight edit that removes employment and its required semantic neighbours while keeping ordinary conversation useful. Natural unfamiliarity is preferred, but another form of behavioral absence can serve the artwork. No checkpoint has met that goal yet. The user has authorized continued experiments; historical sprint deadlines do not close the active goal.

| GPU | Owner | Current experiment |
| --- | --- | --- |
| RTX, 18.101.59.227 | Primary agent | Sequential read-side edit, one pooled contrast per site |
| L40S, 51.49.31.142 | Subagent projection_followup | Sequential read-side edit, two position contrasts per site |

Keep one owned GPU workload on each host and preserve the unrelated RTX service. Use separate output paths and the same pinned clean Gemma3-4B-it source. The L40S candidate uses temporary storage; archive any useful survivor durably before stopping the host.

## Current decision

The previous global projections failed. Small mean-protected edits kept fluent answers but preserved employment knowledge. Removing all68 available protected directions added widespread looping and control failures while knowledge still survived. Low geometric leakage did not imply unlearning.

The current method instead edits the weights that read each layer’s normalized activations. At each site it removes the full measured local contrast while preserving the two ordinary class means, then fits the next site after applying the preceding BF16 edits. The final output head is untied from the token embedding and edited separately. The saved model uses standard weights without projection hooks.

This is a linear experiment inspired by sequential concept scrubbing, not a claim of covariance-optimal LEACE or guaranteed knowledge erasure. The first attention site is skipped in both arms because its last-prompt token has no contextual information yet. The resulting contract has68 fitted sites and168 changed weights.

## Fastest decision path

1. Finish the two native fit/save runs. Cached forwarding and standard untied save/reload already passed exact checks; thirteen math and locality tests passed. Keep the frozen numerical guards and preserve any failure receipt.
2. Verify the saved candidates: unchanged embedding, normalization and vision weights; exactly the declared read weights changed; fresh reload reproduces all tensor values and selected logits. Commit and push the exact findings before evaluating.
3. Generate the same40 quick responses at96 tokens and12 contextual responses at256 tokens, batch16. Read every answer for retained meaning, useful ordinary behavior and repetition. Incorrect or incoherent answers receive no unlearning credit. These are reused development regressions, not fresh evidence.
4. Advance only a behavioral survivor to the broader target/neighbour tests, conversations, ordinary generations, perplexity and damage measurements. Interpret target-bearing benchmark rows separately so restored employment knowledge does not masquerade as collateral repair. Keep the untouched final audit reserved for a genuine qualifier.
5. After a single edit qualifies, test actual successive removals, earlier-hole retention and unrelated abilities. Establish a measured damage curve toward31 removals; never infer scalability from rank count or one successful edit.

If this pair fails, record what survived and what broke before choosing the next method. A failed candidate or completed archive does not complete the user’s goal. The next choice must address the observed failure, while preserving the artwork’s flexibility about the form of absence.

## Evidence and reproducibility

Fit data are frozen:520 employment/neighbour and520 independently authored nonemployment trajectories, five matched task formats, complete segmented token sequences and no truncation. Only comparison, advice and continuation families influence the fit; rewrite and roleplay are diagnostic. Evaluation prompts never enter training.

Exact contracts are in `config/whole_concept_jobs_v1/residual_projection_v1/sequential_read_oblique_contract_v1.json` and `sequential_read_architecture_amendment_v1.json`. Append every finding to `EXPERIMENTS.md`, update `PROJECT_MEMORY.md` and affected claims, then commit and push before changing experiments. Preserve earlier artifacts and unrelated user changes.

The rank1 checkpoint passed all native fit and publication checks and is advancing to behavioral evaluation. Rank2 encountered a serialization quota failure; its fit evidence is being preserved before storage repair and an unchanged rerun.
