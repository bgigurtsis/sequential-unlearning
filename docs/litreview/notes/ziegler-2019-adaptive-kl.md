# Ziegler et al. 2019 — Fine-Tuning Language Models from Human Preferences (adaptive KL controller)

arXiv 1909.08593 · verified y
Code: https://github.com/openai/lm-human-preferences

## Why it matters for T5

Not a decay dial — the **control law**. This is the standard, battle-tested precedent for holding a scalar divergence at a moving target by adjusting a scalar dose, which is exactly our problem restated.

## The rule (Section 2.2)

```
e_t     = clip( (KL(pi_t, rho) - KL_target) / KL_target,  -0.2, +0.2 )
beta_{t+1} = beta_t * (1 + K_beta * e_t)
```

- `K_beta = 0.1` (proportional gain)
- clip range `[-0.2, +0.2]` on the **relative** error
- `KL_target` = 6 nats (descriptiveness) or 10 nats (sentiment), task-dependent

Motivation given in the paper: models trained with the same fixed penalty coefficient ended up at very different KL values, making runs incomparable. The controller exists to make the *divergence*, not the *coefficient*, the thing you specify. That is precisely our situation: we precommit to a decline curve, not to a noise schedule.

## Transplanting it

Substitute:
- `KL(pi_t, rho)` → measured decline `D_t` of today's checkpoint from the day-0 model (a continuous divergence metric — see Dutta 2024 note)
- `KL_target` → `D*_t`, today's precommitted point on the 30-day curve
- `beta` → the dose, controlled in **log space**: `log sigma_{t+1} = log sigma_t + K * e_t`, which is exactly what the multiplicative form above does.

Three properties worth preserving verbatim:

1. **Multiplicative update.** The dose spans orders of magnitude between day 1 and day 30; an additive controller cannot cover that range with one gain.
2. **Relative error.** Normalising by the target means the same gain works when the target is 1% (day 1) and when it is 70% (day 27), where the absolute errors differ by two orders of magnitude. This is the single most important feature for a curve that accelerates sharply in the last week.
3. **The clip.** `±0.2` bounds one step's correction to ±2% of the current dose at `K_beta = 0.1`. For us the clip does the artistic work as much as the engineering work: it guarantees no single day can produce a lurch, so the decline stays legible as a decline. Our gain will need to be larger than 0.1 (we get one measurement per day, not thousands per run) and the clip correspondingly wider — but the structure carries over.

## Extension needed for our case

Ziegler's controller is purely proportional and regulates around a *constant* setpoint. Ours tracks a *ramp that steepens*, so pure proportional control will lag systematically in the final week. Add a feed-forward term: set tomorrow's nominal dose from the calibrated dose–response curve at tomorrow's target, and let the proportional term correct only the residual. Feed-forward plus clipped proportional trim is the right shape.
