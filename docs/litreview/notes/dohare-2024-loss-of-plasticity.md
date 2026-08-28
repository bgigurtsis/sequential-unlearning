# dohare-2024-loss-of-plasticity

**Loss of plasticity in deep continual learning** — Dohare, Hernandez-Garcia, Lan, Rahman, Mahmood, Sutton. *Nature* 632:768–774 (2024). arXiv precursor 2306.13812 "Maintaining Plasticity in Deep Continual Learning". Code: https://github.com/shibhansh/loss-of-plasticity. Verified: y.

## Setting
Long sequences of tasks, all trained by ordinary backprop on the *same* network without resets. Two headline benchmarks:
- **Continual ImageNet**: a stream of binary classification tasks (2 ImageNet classes each), up to 2000 (5000 for continual backprop).
- **Online permuted MNIST**: up to 800 permutations; MLP with 3 hidden layers x 2000 units.

## Reported numbers
- Continual ImageNet, standard backprop: **~89% accuracy on early tasks → ~77% by task 2000**, described as roughly the level a *linear* network achieves. Degradation is gradual and monotone, not a cliff.
- Online permuted MNIST: accuracy rises for the first tasks then declines steadily, for **every** step size tested.
- Correlates measured on permuted MNIST (step size 0.01, 800 tasks):
  - **Dead units → ~25%** of all units.
  - **Average weight magnitude increases monotonically** throughout the run, across all configurations.
  - **Effective rank of the representation declines continuously.**
- Continual backprop hyperparameters: replacement rate **ρ = 1e-4** (≈1 unit re-initialised per 5 examples in a 2000-unit layer), decay rate **η = 0.99**, maturity threshold **m = 100** updates. With these it held non-degrading accuracy across **5000** Continual ImageNet tasks, with later tasks scoring *above* early ones.
- Among off-the-shelf mitigations, **L2 regularisation was the strongest, and L2 combined with weight perturbation (shrink-and-perturb) stronger still** — but neither fully prevented the decline. Loss of plasticity persisted across architectures, optimizers, activation functions, batch norm and dropout.

## Relevance to the sequential-unlearning lineage
- 30 days is short compared to 800–2000 tasks; on this evidence the lineage sits far inside the regime where backprop still learns. Degradation at task 30 in their curves is negligible.
- Gives the three cheap per-day diagnostics with published directionality: dead-unit %, mean |w|, effective rank. Only the dead-unit figure comes with a rough magnitude (≈25% at severe loss).
- Notable for the decay arm: their own best mitigation is *weight perturbation plus L2* — the same operation this project administers as damage. Noise per se is not what kills plasticity; unchecked weight-norm growth is.
