# Liu et al. 2022 — Rethinking and Refining the Distinct Metric (ACL 2022 short, arXiv:2202.13587)

Verified: y (aclanthology.org/2022.acl-short.86).

## Core finding

Raw distinct-n (Li et al. 2016: unique n-grams / total generated words) is systematically biased by generation length: longer texts get lower distinct scores even at identical true diversity, because the expected number of distinct n-grams grows sublinearly in length.

## Fix: Expectation-Adjusted Distinct (EAD)

EAD normalises the distinct count by its expectation given vocabulary size V and length — i.e. divides observed distinct n-grams by the expected count under a random-sampling reference, removing the length artifact. Paper shows EAD correlates better with human diversity judgments than raw distinct-n (exact correlation figures in paper Table 2; improvement held across dialogue datasets).

## Implications for the decay scalar

- The decaying gemma-3-4b-it WILL change its output-length distribution across the 30 days (truncated/looping/rambling outputs), so raw distinct-n would conflate length drift with diversity loss.
- Use EAD (or fix generation length by truncating all samples to a constant token count, e.g. first 128 tokens, before computing distinct-n) so the diversity component is comparable day-over-day.
- Cost: n-gram counting only, negligible.
