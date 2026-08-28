# llm-plasticity-scale-2026

**Can Scale Save Us From Plasticity Loss in Large Language Models?** — arXiv 2606.24752 (June 2026). Verified: y (abstract + HTML v1 read).

## Setup
GPT-style Transformers, **eight scales from 5M to 314M non-embedding parameters**, trained on a multilingual continual-learning stream. Plasticity is measured by adapting to a **held-out Vietnamese probing task** at intervals; degradation of that probe over training cycles is the plasticity-loss signal. Both continual and stationary training regimes tested.

## Reported numbers
- **Scaling law for onset:** `T = 1.3e-5 · P^0.8269`, where T is the task-instance index at which plasticity loss begins and P is non-embedding parameter count. Exponent < 1 ⇒ **sublinear**: doubling parameters buys less than double the delay.
- Smallest models (5M–12M) deteriorate on the probe **after the first training cycle**; the 314M model delays onset substantially but does not avoid it.
- Transfer benefit shrinks over time: the **53M model loses ~0.5% AUC**, the **314M model >1.5%**.
- The **27M model** crosses into degradation at **~320B tokens continual** vs **~475B tokens stationary** — non-stationarity accelerates onset by ~30%.
- Plasticity loss appears **even in stationary training**, given enough tokens.

## Diagnostics measured (and their verdict)
- **Mean absolute parameter magnitude** rises over cycles — but the trend "does not perfectly correlate" with the performance degradation.
- **Dormant MLP units** accumulate; extreme case **>95% dormancy in a single layer** (53M model, layer 8).
- **Attention-head pathologies**: "lazy heads" with entropy **>90% of maximum** (near-uniform attention) and "collapsed heads" with entropy **<10% of maximum**. In the 106M model, layer 11 became consistently lazy after training.
- Authors state plainly they **do not find a "smoking gun"**: the correlates appear inconsistently across model sizes.

## Mitigations
Discussed but **not empirically tested**: stronger weight decay (above the standard 0.1), clipping parameters near zero, unit re-initialisation (continual backprop, ReDo), attention-sink mechanisms.

## Relevance to the lineage
- The only LLM-scale plasticity-loss study located in this thread, and it stops at 314M — a 4B model is an order of magnitude beyond its largest point. Extrapolating the fitted law past its fitted range is unsound, but the direction is favourable: onset is *later* at larger scale.
- The token counts are the important datum. Onset for a 27M model needs **~10^11 tokens**. A 30-day lineage of small forget+heal fine-tunes is many orders of magnitude below that. Endogenous plasticity loss is very unlikely to be the binding constraint before day 30 — administered decay will be.
- Adds a cheap LLM-specific diagnostic beyond the RL literature: **per-head attention entropy as a fraction of log(seq_len)**, with the paper's own >90% / <10% flags.
