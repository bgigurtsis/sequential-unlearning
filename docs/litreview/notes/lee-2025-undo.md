# Lee et al. 2025 — Distillation Robustifies Unlearning (UNDO)

arXiv 2506.06278 · NeurIPS 2025 (Spotlight) · verified y
Code: https://github.com/AddieFoote/distillation-robustify-unlearning

## Why it matters for T5

The only source found that (a) uses **weight-space noise as a deliberate damage dial**, (b) **sweeps it**, and (c) pairs it with a **repair stage** — the same three-part structure as our decay + heal architecture.

## Dial parameterisation

```
theta_perturbed = (1 - alpha) * theta_suppressed + alpha * beta * N
```

- `alpha in [0,1]` — mixing coefficient (how much of the original weight is replaced).
- `beta in R+` — noise scale.
- `N` — sampled from **Xavier initialisation** (2D matrices Xavier-uniform; 1D bias vectors zeroed). No per-layer weight-norm rescaling.

Sweeps run: `alpha in {0.1, 0.2, 0.3, 0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8}` at fixed `beta = 0.1`; extended `beta in {0.05, 0.1, 0.5, 1.0}` across multiple alphas.

**Key reported structure**: "changes in mixing coefficient (alpha) produce a more pronounced effect on robustness than the noise scale (beta)" — i.e. the two-parameter dial collapses in practice to a **one-dimensional control variable, alpha**. That is what a closed-loop controller needs.

The *interpolation* form is strictly better for our purposes than unbounded additive noise: `alpha` is bounded in [0,1] with well-defined endpoints (alpha=0 is the model, alpha=1 is a fresh Xavier init, i.e. terminal collapse by construction). A 30-day schedule mapped onto a bounded interval cannot diverge, and the endpoint *is* the artistic endpoint.

## Reported numbers

- `alpha = 0.6, beta = 0.1` reaches near-oracle (retrain-from-scratch) robustness against relearning attacks on the synthetic tasks.
- "Increasing the perturbation parameter alpha enhances robustness against relearning attacks while requiring proportionally more computation" — monotone in alpha, with recovery cost rising monotonically too.
- Models: Gemma-2 scaled variants (100M for the language task, 300M for arithmetic); **Gemma-2-2B** for WMDP.

## Relevance to our base model

Gemma-2-2B is the nearest published scale to gemma-3-4b-it in this literature — same family, same order of magnitude. Their alpha grid is therefore a defensible starting bracket for our own calibration rather than a pure guess.

## Near-collapse behaviour

Not characterised as a degradation *curve*: the paper measures forget/retain and relearning robustness, not a continuous utility trace, and the high-alpha region is only visited to show damage saturating. `alpha ≈ 0.8` is the top of the swept range. What it does establish is that the collapse endpoint is *reachable and bounded* — at alpha=1 the model is by definition a random init.

## Reversibility and repair

Fully reversible: the perturbation is applied to a copy, and the paper's whole method assumes the damaged model is then *distilled back* toward a target behaviour. This is the published precedent that a noised model can be partially repaired on demand — relevant if our heal arm ever needs to walk the curve backwards.

## Cost on 4B BF16

Noising: trivial. The distillation repair stage is the expensive half and would not be run daily.
