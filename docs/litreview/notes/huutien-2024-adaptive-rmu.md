# On Effects of Steering Latent Representation for Large Language Model Unlearning

Dang Huu-Tien, Trung-Tin Pham, Hoang Thanh-Tung, Naoya Inoue. arXiv 2408.06223, Aug 2024. **AAAI-25** main track. Verified: y.

Models: Zephyr-7B-beta, Yi-6B, Meta-Llama-3-8B, Mistral-7B (all 6-8B).

## Numbers copied out (Table 1, Zephyr-7B, layer l=7)

| Method | WMDP-Bio ↓ | WMDP-Cyber ↓ | MMLU ↑ |
|---|---|---|---|
| Base | 63.7 | 43.5 | 58.1 |
| RMU | 28.8 | 28.8 | 56.8 |
| Adaptive RMU | 23.7 | 26.5 | 55.0 |

Adaptive RMU improves accuracy drop by 14.3% (Bio) and 6.6% (Cyber) overall; within middle/later layers it reduces average accuracy by 15.6% (Bio) and 9.6% (Cyber) where plain RMU fails.

## Coefficient sweep (the only published one)
c swept over {1.0, 2.0, 5.0, 10.0}. Reported: a "clear positive correlation between the drop-in-accuracy rate and the value of c", but raising c to improve forgetting causes a "significant drop in general performance on MMLU."

## Layer dependence
RMU works in early layers (3→10) and **fails in middle and later layers (11→31)**.

## Mechanism — why the transition is sharp
The paper's stated condition: loss convergence requires the l2-norm of forget-sample representations to fall **below the coefficient c**. In early layers the norm is small enough and the loss converges; in later layers the norm is unchanged and it does not. This is a **threshold condition on a norm**, not a proportional response.

## Relevance to T1 / H1
This is the best available explanation of the in-project step-29→30 cliff. If the objective only starts converging once a norm crosses c, then the observable transition from "knows" to "erased" is expected to be abrupt, halving the LR will not smooth it (it only delays the crossing), and post-hoc rescaling of the update will be sharply nonlinear — all three match what was measured in-project.

Implication for H1: within the RMU family there may be no genuinely minimal dose to find. The fix is to change the objective (see singh-2025-jensun) or the family, not to tune c harder.
