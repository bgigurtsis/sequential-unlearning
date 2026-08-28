# sokar-2023-dormant-neurons

**The Dormant Neuron Phenomenon in Deep Reinforcement Learning** — Sokar, Agarwal, Castro, Evci. ICML 2023 (PMLR 202). arXiv 2302.12902. Reference PyTorch impl: https://github.com/timoklein/redo. Verified: y.

## The diagnostic (the reason this paper matters here)
A neuron *i* in layer ℓ gets a **normalised activation score** `s_i^ℓ` = its mean absolute activation over a batch, divided by the mean over all neurons in that layer. Neuron is **τ-dormant** if `s_i^ℓ ≤ τ`. The per-layer normalisation is what makes the number comparable across layers and across checkpoints — this is the property the lineage needs for a day-over-day series.

Operating points reported:
- **τ = 0.1** — the paper's main threshold; balances sensitivity against false positives.
- **τ = 0.025** — used for finer-grained analysis.
- **τ = 0.0** — only fully inactive units; pruning them costs essentially no performance, confirming they carry no signal.

## Reported numbers
- DQN on Atari, 200M frames: dormant fraction climbs from **~5–10% early to 40–60%** by end of training.
- Raising the replay ratio (more gradient steps per env step) accelerates it: **~70% dormant at RR=2.0 vs ~40% at the default RR=0.25**. Directly analogous to doing more optimisation per unit of fresh data — which is what a per-day forget+heal cycle does.
- Persists in **offline** RL with a fixed dataset, so the driver is **target non-stationarity**, not data non-stationarity.
- Overlap coefficient across checkpoints increases: **dormant neurons very rarely reactivate on their own.** Damage is cumulative unless something resets them.

## ReDo (the mitigation)
Re-initialise incoming weights of dormant units from the original init distribution and **zero the outgoing weights** (so the intervention is output-preserving at the moment of application). Applied every **1000** steps (DQN) / **200 000** steps (SAC).
- Atari aggregated score at RR=1.0: **~15–25% improvement**.
- **4x reduction in environment steps** to reach matched performance.
- **Effective rank 449.2 ± 5.77 → 470.8 ± 1.16.**

## Relevance
- Adopt τ=0.1 dormant-fraction per MLP block as the primary daily plasticity log. It is one forward pass over a fixed probe batch — cheapest useful signal in this literature.
- The zero-outgoing-weights trick is the safe way to inject fresh capacity mid-lineage without perturbing day-N outputs, if a repair is ever needed.
- Caveat: all evidence is CNN-scale RL, not a 4B decoder. Absolute thresholds should be treated as unvalidated at this scale; the *trend* is the usable signal.
