# Luo et al. 2023 — An Empirical Study of Catastrophic Forgetting in LLMs During Continual Fine-tuning

- arXiv:2308.08747 (v4, updated through Jan 2025). First author Yun Luo. Preprint, ~131 citations. Verified: y.

## Setup
- Continual instruction tuning across a sequence of tasks; forgetting (FG) measured on domain knowledge, reasoning, reading comprehension. Models: BLOOMZ 1.1b/1.7b/3b/7.1b, mT0 1.2b/3.7b, LLaMA-7b, ALPACA-7b.

## Numbers
- Forgetting grows with scale (BLOOMZ): domain knowledge FG 9.54% (1.1b) → 10.72% (1.7b) → 14.63% (3b) → 18.37% (7.1b); reading comprehension FG 18.04% → 24.29% → 27.56% → 26.75%; reasoning 6.73% → 13.62%.
- Decoder-only (BLOOMZ) forgets less than encoder-decoder (mT0) at similar scale (mT0-3.7b: 20.15% DK, 28.42% RC).
- General instruction tuning as protection — after the same continual fine-tuning: LLaMA-7b vs ALPACA-7b drops: domain knowledge 34.57% vs 18.14%; reasoning 31.33% vs 7.56%; reading comprehension 31.72% vs 10.31%.
- Mixing general instruction data into each continual task notably reduces degradation (rehearsal effect).

## Relevance to T3 / H1
- Closest large-scale numbers for "how much does sequential fine-tuning damage general ability and how much does general-text rehearsal buy back": mixing general instruction data cut reasoning loss ~4x and reading-comprehension loss ~3x.
- Our healing pass is exactly this mechanism applied after each forget step; expect it to recover the majority (but not all) of collateral, consistent with H1.
- Caveat: their interventions are benign task FTs, not unlearning objectives (GA/NPO), which damage in a different (sometimes irreversible — see xu-2025-reversibility) way.
