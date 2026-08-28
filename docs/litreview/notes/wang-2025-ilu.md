# Wang et al. 2025 — Invariance Makes LLM Unlearning Resilient Even to Unanticipated Downstream Fine-Tuning (ILU)

- arXiv:2506.01339, ICML 2025. Authors: Changsheng Wang, Yihua Zhang, Jinghan Jia, Parikshit Ram, Dennis Wei, Yuguang Yao, Soumyadeep Pal, Nathalie Baracaldo, Sijia Liu (OPTML / IBM). Code: https://github.com/OPTML-Group/Unlearn-ILU. Verified: y.

## Problem statement (their measurement, our H2)
- Existing unlearning (NPO, RMU) is "over-sensitive to downstream fine-tuning": fine-tuning on tasks ENTIRELY UNRELATED to the forget set (e.g., GSM8K math) rapidly recovers unlearned WMDP knowledge on LLaMA3-8B-Instruct. This is benign revival with zero topical leakage — stronger than Hu et al.'s correlated-text attack, and exactly the risk our healing pass takes.

## Method
- Invariant Risk Minimization (IRM)-style regularization added to the unlearning objective: unlearned behaviour is trained to be invariant across fine-tuning "environments". Using even a SINGLE anchor fine-tuning dataset (GSM8K) during unlearning generalizes robustness to diverse unseen fine-tuning tasks at test time.
- Compared against LAT and TAR (other robustness-oriented baselines) on WMDP before/after downstream FT; ILU reported best retention of unlearning.

## Numbers extracted
- Fetch of the PDF returned qualitative summaries; the before/after WMDP tables (ILU vs NPO/RMU/LAT/TAR under GSM8K, AGNews, etc. fine-tuning) are in the paper's main tables — re-extract if precise deltas are needed. Headline: baselines revert toward pre-unlearning WMDP accuracy after unrelated FT; ILU largely holds its unlearned level.

## Relevance to T3
- Establishes that even fully concept-filtered healing text can revive erased knowledge when the forget pass is a shallow suppression (NPO/RMU-style) — H2's failure mode does not require leaks.
- Mitigation lives at forget time, not heal time: make each day's forget pass invariance-regularized against the healing distribution itself (we know our healing corpus in advance — an even easier setting than theirs, which needed only one anchor dataset).
