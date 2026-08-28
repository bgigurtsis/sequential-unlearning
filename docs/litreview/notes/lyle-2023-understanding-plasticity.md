# lyle-2023-understanding-plasticity

**Understanding plasticity in neural networks** — Clare Lyle, Zeyu Zheng, Evgenii Nikishin, Bernardo Avila Pires, Razvan Pascanu, Will Dabney. ICML 2023 (oral). arXiv 2303.01486. Verified: y.

## The load-bearing claim for this thread
> Loss of plasticity is deeply connected to changes in the **curvature of the loss landscape**, and **it often occurs in the absence of saturated units.**

That second clause is the reason this paper is in T4 as a *caveat* rather than as a source of diagnostics. **A network can have a perfectly healthy dead-unit count and healthy feature rank and still have lost plasticity.** Every cheap proxy in this thread (dormant fraction, effective rank, weight norm) is therefore a *sufficient-when-triggered, not necessary* alarm: a bad reading is informative, a good reading is not reassurance.

## Other findings
- Plasticity is operationalised directly: the network's ability to reduce loss on a **freshly sampled target**. This is the ground-truth measurement the proxies are trying to approximate.
- A number of **parameterisation and optimisation design choices** preserve plasticity better than others; the paper's remedies are in that family rather than unit-resetting. Layer normalisation features prominently in this line of work.
- Experiments on the Arcade Learning Environment; agent-scale networks (<10M params). No LLM replication.

## Consequence for the per-day panel
Because the proxies can be silent, the lineage needs at least one **direct** plasticity probe per day, not only correlates. The cheap version:

> Hold out a small fixed **plasticity probe task** (e.g. a few hundred examples of a synthetic mapping or a held-out concept never used in the forget or retain sets). Each day, on a *throwaway copy* of the merged checkpoint, run a fixed budget of K steps at a fixed LR and record the loss reduction achieved. Discard the copy.

This is the operationalisation Lyle et al. use, it costs one short fine-tune per day, and unlike the proxies it measures the quantity H6 is actually about. Recording the same number for the day's *actual* forget objective (loss reduction achieved in a fixed step budget) gives the H6 answer directly rather than by proxy.
