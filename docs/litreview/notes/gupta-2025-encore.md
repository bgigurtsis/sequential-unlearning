# Gupta et al. — Lifelong Knowledge Editing requires Better Regularization (ENCORE)

arXiv:2502.01636 (earlier title: "Lifelong Sequential Knowledge Editing without Model Degradation"). Verified: y.

## Setup
- Models: GPT2-XL, Llama-2-7B, Llama-3-8B. Batches of 100 facts; up to **10,000 sequential edits**.
- Downstream measured every 1,000 edits on MMLU, SST2, MRPC, RTE, CoLA, NLI.

## Degradation mechanism (the accumulation physics)
- Continuous **Frobenius-norm growth** of edited matrices: MEMIT norm reaches **10x original** by 10,000 edits; AlphaEdit ~2x.
- Edited layers' share of residual-stream activation rises from **~1% to 7–40%** ("importance hacking") — the edited layer shouts down the rest of the network.
- Overfitting of edited facts: prediction probability 92–99% vs the natural 39–52% of the original model; MPES early stopping restores 33–61%.

## Curve points
- MEMIT edit score: ~81 → ~50 on Llama-3-8B over 10,000 edits; downstream baselines degrade significantly by **3,000–5,000 edits**.
- ENCORE (norm constraint + MPES): edit score 92.57, paraphrase 82.64, overall 76.04 at 10k on Llama-2-7B; downstream held through 10,000 edits; 61–64% faster than MEMIT/AlphaEdit.

## Relevance to H4
- Gives us the *odometer*: edited-matrix norm and edited-layer activation share are monotone, cheaply computable, and predict downstream collapse before eval metrics move. Log both daily.
- Directly supports H4's asymmetry claim ("leakage cannot be un-leaked"): norm growth is cumulative and only a constraint at edit time prevents it; post-hoc healing does not shrink the norm.
- ENCORE = evidence that norm-restrained editing plus early stopping (our per-day dose cap analogue) extends the safe horizon by ~3x over AlphaEdit.
