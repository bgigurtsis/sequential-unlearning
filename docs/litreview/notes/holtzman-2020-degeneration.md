# Holtzman et al. 2020 — The Curious Case of Neural Text Degeneration (ICLR 2020, arXiv:1904.09751)

Verified: y (OpenReview rygGQyrFvH; ar5iv table extracted).

## Reported numbers (GPT-2 large, 200-token continuations, WebText prompts)

| Method | PPL (under model) | Self-BLEU4 | Zipf | Repetition % | HUSE |
|---|---|---|---|---|---|
| Human | 12.38 | 0.31 | 0.93 | 0.28 | — |
| Greedy | 1.50 | 0.50 | 1.00 | 73.66 | — |
| Beam b=16 | 1.48 | 0.44 | 0.94 | 28.94 | — |
| Pure sampling | 22.73 | 0.28 | 0.93 | 0.22 | 0.67 |
| Top-k 640 | 13.82 | 0.32 | 0.96 | 0.28 | 0.94 |
| Nucleus p=0.95 | 13.13 | 0.95 | 0.95 | 0.36 | 0.97 |

Repetition definition: a phrase (min length 2) counts as a repetition when it repeats >=3 times at the end of the generation.

## Implications for the decay scalar

- Repetition % has by far the widest dynamic range (0.28 → 73.66) — the workhorse metric for the 70–100% decay band.
- Self-BLEU4 range is narrow (0.28–0.50): weakly discriminative, expensive (pairwise BLEU across the sample set). Skip or downweight.
- Zipf coefficient barely moves (0.93–1.00): too compressed to carry daily signal.
- Perplexity of outputs under the generating (or any) model is NON-monotone in quality: degenerate repetition has ppl 1.5 vs human 12.4, while gibberish has high ppl. Any ppl component must be two-sided: distance from baseline ppl, |log ppl − log ppl_baseline|, not raw ppl.
