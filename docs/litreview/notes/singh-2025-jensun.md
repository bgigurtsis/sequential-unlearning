# Unlearning That Lasts: Utility-Preserving, Robust, and Almost Irreversible Forgetting in LLMs (JensUn)

Naman Deep Singh, Maximilian Müller, Francesco Croce, Matthias Hein. arXiv 2509.02820, Sept 2025. Verified: y.

Models: **Llama-3.2-3B-Instruct** and **Phi-3-mini-4K-Instruct (3.8B)** — the closest scale in this thread to gemma-3-4b-it.

## Method
JensUn uses **Jensen-Shannon divergence** as the objective on both forget and retain sets, explicitly to avoid the *unbounded* loss of GradAscent and GradDiff.

## Numbers copied out (LKF dataset)

| Method | Forget acc (worst-case) ↓ | MMLU | Win Rate | Repetitiveness |
|---|---|---|---|---|
| Original | — | 59.6 | 0.5 | 637 |
| **JensUn** | **0%** | **59.9** | **0.47** | 592 |
| GradAscent | 0% | — | **0** (model destroyed) | — |
| GradDiff | 2% | — | 0.22 (repetitive output) | — |

**Dose-response (Table 3):** GradDiff and NPO show marked utility collapse beyond **600 unlearning steps**; JensUn holds Win Rate 0.46 even at **2000 steps**.

**Relearning:** after 2000 unlearning steps + 600 relearning steps, JensUn retained 8% forget accuracy vs NPO's 26% — i.e. the forgetting is more permanent, not merely suppressed.

## Relevance to T1 / H1
The clearest published statement of the fix for the in-project cliff. The step-29→30 transition, the failure of LR-halving to smooth it, and the nonlinear response to post-hoc rescaling are all signatures of an **unbounded** divergence objective, where loss can always be reduced further and the only stable states are "not yet crossed" and "collapsed". Swapping to a bounded objective converts the step count from a threshold into a genuine monotone dial across a 600-2000 step range.

For our two-arm design this is doubly useful: it argues that graded degradation should be produced by the *decay* arm (noise), while the *forget* arm should use a bounded objective and stop early — rather than trying to find a small dose of a divergent loss.

Code URL: not confirmed.

---

## T8 addendum — relearning / resurfacing evidence (H2)

Benign-relearning protocol: **600 steps of fine-tuning on UNRELATED data** after unlearning (this is the closest published analogue of the project's healing pass, at the project's 3-4B scale).

- JensUn unlearned for 2000 steps: forget accuracy recovers to only **8%** after the 600 benign steps.
- NPO: recovers to **26%**; **NPO+SAM: 58%** (SAM's forget-sample-relearning hardening did not transfer to the benign-FT setting).
- GradDiff at 2k steps: 0% recovery but utility destroyed (Win Rate 0.03) — the degenerate deep-erasure corner.
- Longer/deeper unlearning monotonically hardens against relearning.

T8 takeaway: with a bounded objective, a healing-like pass resurfaces <10% of forget performance; with NPO ~a quarter. Depth-for-robustness trades against utility, so shallow-erase + touch-up and deep-erase-once are genuinely different points on the frontier.
