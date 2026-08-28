# Negative Preference Optimization: From Catastrophic Collapse to Effective Unlearning

Zhang, Lin, Bai, Mei. arXiv 2404.05868, April 2024. COLM 2024. Verified: y.

## Claims copied out
- Gradient ascent (GA) causes "catastrophic collapse — a drastic degradation of the model's utilities."
- Theoretical result: progression toward catastrophic collapse under the NPO loss is **exponentially slower** than under GA.
- GA-based methods "already struggle with forgetting 10% of training data"; NPO is the first to achieve workable unlearning at **50%+** forget fraction on TOFU.
- GA outputs are "often gibberish"; NPO outputs are sensible.

No forget-vs-utility table extracted from the abstract page; do not cite specific TOFU numbers from this note.

## Relevance to T1 / H1
The structural point, not the numbers, is what matters here. NPO does not remove the collapse — it makes approach to collapse exponentially slower. The objective is still divergent, so "dose" remains *training time* and there is no stable plateau to sit on. That is exactly the regime in which a step-29→30 cliff is expected, and exactly why halving the learning rate does not help: it rescales the time axis without creating a stable intermediate state.

Note also that in DSG's 2B Gemma evaluation, NPO barely forgot anything on WMDP-Bio (97.95%) at settings that preserved utility — the low-dose end of NPO can be *entirely inert* rather than gently graded. Combined with singh-2025-jensun, the conclusion for the forgetting arm is to abandon unbounded divergence objectives.

Code: https://github.com/licong-lin/negative-preference-optimization
