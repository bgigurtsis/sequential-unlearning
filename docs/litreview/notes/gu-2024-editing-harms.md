# Gu et al. — Model Editing Harms General Abilities of LLMs: Regularization to the Rescue (RECT)

arXiv:2401.04700 — EMNLP 2024. Verified: y.

## Setup
- Models: GPT-2 XL (1.5B), LLaMA-1-7B, LLaMA-2-7B.
- Methods: KN, MEND, ROME, MEMIT. 8 downstream tasks (reasoning, NLI, open/closed QA, summarization, etc.).

## Reported numbers
- KN on LLaMA-1: a **single edit** (touching <1% of parameters) drops performance to **near zero on all selected tasks** — worst-case one-shot collapse.
- ROME on GPT-2 XL, weight drift vs edit count (fraction of weight elements with |delta| > 0.077):
  - 1 edit: 20%; 5 edits: 49.2%; 15 edits: 72.8%.
  - Manhattan distance of edited matrix: 9,079 (1 edit) → 63,247 (15 edits). Roughly linear-superlinear drift accumulation.
- Batch editing (MEND/MEMIT, GPT-2 XL): degradation grows consistently with batch size.
- RECT (regularizing edit updates): keeps **>94% of editing performance** while largely preserving downstream ability (summarization, open/closed QA most protected).

## Relevance to H4
- Weight-drift fraction is a cheap, monotone damage odometer — usable as the daily leakage meter independent of eval noise.
- Method choice dominates: KN-style edits can blow the entire 30-day budget on day 1; regularized MEMIT-style edits keep per-edit damage small.
- RECT shows that a built-in restraint (analogous to our healing stage) recovers most of the utility cost without losing edit efficacy.
