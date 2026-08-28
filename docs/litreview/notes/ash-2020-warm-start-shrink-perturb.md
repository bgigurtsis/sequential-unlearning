# ash-2020-warm-start-shrink-perturb

**On Warm-Starting Neural Network Training** — Jordan T. Ash, Ryan P. Adams. NeurIPS 2020. arXiv 1910.08475. Verified: y.

## Setup
Data arrives in rounds; each round you either retrain from scratch (cold start) or continue from the previous round's weights (warm start). Warm starts reach similar *training* loss but generalise worse.

## Reported generalisation gaps (warm start vs fresh random init)
| Setting | Random init | Warm start | Gap |
|---|---|---|---|
| CIFAR-10, ResNet-18, SGD | 56.2% | 51.7% | **4.5 pp** |
| CIFAR-10, ResNet-18, Adam | 78.0% | 74.4% | **3.6 pp** |
| CIFAR-100, ResNet-18, Adam | 41.4% | 35.0% | **6.4 pp** |
| SVHN, ResNet-18, SGD | 89.4% | 87.5% | **1.9 pp** |

## Shrink-and-perturb
`θ_t ← λ·θ_{t-1} + p_t`, with `p_t ~ N(0, σ²)` and `0 < λ < 1`.
- Reported effective setting: **λ = 0.6, noise scale 0.01** — recovers fresh-init-level accuracy *while keeping the wall-clock advantage of the warm start*.
- Hyperparameter tweaks that close the gap without shrink-perturb (e.g. lowering LR) do so only "in regimes that damage the wall-clock gains" — i.e. they buy generalisation with training time; shrink-perturb does not.

## Relevance to the decay arm and to H6
- This is the same operator the project administers as *damage*: shrink toward zero plus additive Gaussian noise. In this paper it is a **cure**, not a wound. A deliberately shrunk-and-noised checkpoint trains **faster than a fresh init and generalises as well as one** — a direct positive datum for "the forgetting arm keeps working after administered noise".
- Sets a scale reference: λ=0.6 (a 40% shrink) plus σ=0.01 noise leaves a network fully trainable. That is a large perturbation by the standards of a single day's decay increment.
- Also a warning in the other direction: warm-starting *without* perturbation is the pathological case. A lineage that repeatedly warm-starts from its own parent with no noise is the exact configuration this paper shows degrades. The administered decay may be partially self-medicating.
- Reported at ResNet/CIFAR scale only; no LLM replication found in this thread.
