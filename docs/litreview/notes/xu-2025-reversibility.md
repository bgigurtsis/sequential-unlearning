# Xu et al. 2025 — Unlearning Isn't Deletion: Investigating Reversibility of Machine Unlearning in LLMs

- arXiv:2505.16831 (v3). Authors: Xiaoyu Xu, Xiang Yue, Yang Liu, Qingqing Ye, Huadi Zheng, Peizhao Hu, Minxin Du, Haibo Hu. Preprint (under review). Verified: y.

## Setup
- Models: Yi-6B (main), Qwen-2.5-7B, Llama-3-8B variants. Methods: GA, NPO, Random Label, RMU, UnDIAL, AltPO, PDU; single and continual (N=100) unlearning.

## Four regimes (dose-dependent)
- Single unlearning, moderate dose: reversible, non-catastrophic. GA+KL forget acc drops 7.9–12.7%, recovers to ~77% after relearning; NPO+KL drops 2.5–6.4%, near-complete recovery; retain acc stable at 62–65%.
- Continual, moderate (GA lr 5e-6, N=100): reversible catastrophic — forget acc falls to 9.1%, recovers to 80%; retain drops 6.2%, recovers to 65%.
- Continual, aggressive (GA lr 3e-5, N=100): IRREVERSIBLE catastrophic — forget acc 0%, only 2.1% after relearning; retain acc 1.8% and unrecoverable. Representation drift persists (mean PCA distance 133.2 after unlearning → 104.6 after relearning; vs 11.5→1.4 at lr 5e-6).
- Irreversible non-catastrophic (the ideal) is "exceptionally challenging" — rarely observed.

## Recovery sample-efficiency hierarchy
1. Relearning on the forget set itself: fastest (~10% of forget data suffices).
2. Domain-aligned retain subset: slower.
3. Unrelated data: most gradual.

## Relevance to T3
- H1: strongest direct support with numbers — collateral damage from moderate-dose unlearning is largely repairable by fine-tuning; but past a dose threshold (LR x steps) damage becomes structurally irreversible (PCA drift never closes). Our per-day dose must stay in the reversible-collateral regime.
- H2: the same repairability cuts both ways — domain-aligned retain data partially restores forget-set accuracy. Healing text should be domain-distant from erased concepts, not just string-filtered.
- Representation-space drift (PCA/CKA/Fisher) is a leading indicator of irreversibility — a candidate cheap gate for our 30-day loop.
