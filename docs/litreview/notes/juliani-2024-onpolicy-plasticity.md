# juliani-2024-onpolicy-plasticity

**A Study of Plasticity Loss in On-Policy Deep Reinforcement Learning** — Arthur Juliani, Jordan T. Ash. NeurIPS 2024. arXiv 2405.19153. Verified: y.

## Why it matters here
This is the paper that actually *tests which diagnostics predict plasticity loss*, rather than assuming them. That is precisely the T4 question.

## Diagnostic verdicts (PPO agents; gridworld, Montezuma's Revenge, ProcGen)
| Diagnostic | Verdict |
|---|---|
| **Weight magnitude** (mean \|w\|) | **Significantly correlated** with normalised reward, p<0.05 |
| **Dead-unit fraction** (ReLU units emitting only non-positive values) | **Significantly correlated** with reward degradation — but its predictive power is *mediated by* weight magnitude in the multivariate analysis |
| **Gradient norm** | **NOT significantly correlated** in the on-policy setting — explicitly contrasted with off-policy findings where it is |
| **Weight difference between updates** | No significant linear relationship |

Multivariate: "both gradient and weight magnitudes are significantly predictive of train performance [p<0.01]".

## Mitigation verdicts
Worked:
- **Soft shrink + perturb** (continuous scaling of weights toward initialisation)
- **Regenerative regularisation / L2-init** (L2 penalty toward initial weights)
- **ReDo** (selective neuron reset)
- **LayerNorm + regularisation** — LayerNorm alone fixed *training* plasticity but not generalisation

Failed:
- **Plasticity injection** — "underperforms even the warm-start baseline in all three contexts"
- **CReLU** — only partially effective
- **Final-layer reset** — ineffective across all shift conditions

Overall conclusion: **"regenerative" methods that pull weights toward initialisation consistently beat architectural modifications** designed for off-policy RL.

## Relevance
- Sets the daily log: **mean |w| first, dead-unit fraction second**. Do *not* rely on gradient norm alone as a plasticity indicator — it may be uninformative, and in this project it is confounded with the decay schedule anyway.
- Important negative result: **fixes developed in one nonstationary regime can be worse than doing nothing in another.** Do not port ReDo or plasticity injection into the lineage on faith; if a repair is ever needed, prefer the regenerative family (L2 toward the day-0 parent), which won in both this paper and Dohare et al.
- Scale caveat: <10M-parameter PPO agents, ReLU MLPs/CNNs. Gemma-3-4b uses GeGLU and RMSNorm; "dead unit" needs redefining as a normalised-activation dormancy score (Sokar) rather than a strict ReLU-zero test.
