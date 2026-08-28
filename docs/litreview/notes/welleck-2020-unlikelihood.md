# Welleck et al. 2020 — Neural Text Generation with Unlikelihood Training (ICLR 2020, arXiv:1908.04319)

Verified: y (OpenReview SJeYe0NtvH).

## Reported numbers

- GPT-2 (medium) fine-tuned with MLE vs sequence-level unlikelihood: seq-rep-4 = 0.506 (MLE) vs 0.042 (UL-seq), with perplexity and token accuracy roughly maintained.
- Related follow-up (implicit unlikelihood / RL): seq-rep-4 reduced 0.277 → 0.0041 at top-p 0.3.

## Metric definitions used

- seq-rep-4: fraction of duplicate 4-grams within a single generated continuation (1 − unique 4-grams / total 4-grams). Bounded [0,1], per-generation, no reference needed.
- uniq-seq: number of unique tokens across the generation set.

## Implications for the decay scalar

- seq-rep-4 gives order-of-magnitude separation between healthy and degenerate generation and stays graded through heavy repetition (values observed from ~0.004 through 0.5+; a fully looping model approaches 1.0).
- Perplexity stayed roughly flat while seq-rep-4 exploded — direct evidence that repetition metrics carry signal where ppl does not.
- Cost: pure n-gram counting on generated tokens — trivially cheap for 100–300 daily generations, no GPU needed.
