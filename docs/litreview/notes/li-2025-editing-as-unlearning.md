# Editing as Unlearning: Are Knowledge Editing Methods Strong Baselines for LLM Unlearning?

Zexi Li, Xiangzhu Wang, William F. Shen, Meghdad Kurmanji, Xinchi Qiu, Dongqi Cai, Chao Wu, Nicholas D. Lane. arXiv 2505.19855, May 2025. Verified: y.

Models: Llama2-7B, Mistral-7B, Llama3.1-8B.

## Numbers copied out (factual dataset, Llama2-7B)
- **ROME:** Rouge1 0.01 on the forget set (good forgetting) but **0.04 on the retain set** — the retain set is destroyed too. Compare gradient-based GD: 0.30 forget / 0.62 retain.
- **MEMIT:** "the LLM becomes non-functional with near-zero Rouge1 for both forget and retain sets."
- Locate-and-edit methods "cannot well perform under long sequences of editing"; performance collapses once batch sizes exceed their design limits.
- After the authors' **query merging** fix: ROME combined score 1.622, MEMIT 1.632, vs unlearning baseline DPO 1.123.
- Strongest editors overall: **AlphaEdit** (best across reliability/locality/generalization) and **WISE**.

## Relevance to T1 / H1
This is the negative result that closes off the rank-one-editing branch in its naive form. "Rank-one model editing unlearning" was one of the search targets for T1; the answer is that ROME/MEMIT applied as unlearning are *not* minimal-collateral, and they explicitly degrade under long edit sequences — which is the one property our 30-day design cannot do without.

What survives: (a) query merging restores them to competitive, so the failure is about how the edit request is constructed rather than about closed-form editing per se; (b) AlphaEdit — which projects the update into the null space of preserved knowledge before applying it — is the variant worth reading next, because null-space projection of the daily update is the same idea as O3's orthogonal adapters and UCE's preserve term, arriving from a third direction.

Three independent families now converge on the same prescription: constrain each day's update to a subspace that provably does not touch what must be retained.
