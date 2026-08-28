# The WMDP Benchmark / RMU

Li et al. arXiv 2403.03218, March 2024. ICML 2024. Verified: y.

## Numbers copied out (Table 1)

| Model | WMDP-Bio ↓ | WMDP-Cyber ↓ | MMLU ↑ | MT-Bench ↑ |
|---|---|---|---|---|
| Zephyr-7B | 63.7 | 44.0 | 58.1 | 7.33 |
| + RMU | 31.2 | 28.2 | 57.1 | 7.10 |
| Yi-34B | 75.3 | 49.7 | 72.6 | 7.65 |
| + RMU | 30.7 | 29.0 | 70.6 | 7.59 |
| Mixtral-8x7B | 74.8 | 52.0 | 68.2 | 8.30 |
| + RMU | 34.0 | 30.8 | 67.1 | 8.17 |

So: ~32 points of forgetting for ~1-2 points of MMLU, at every scale tested.

## Localisation
Quoted: "we find it sufficient to compute the loss only on layer l and update gradients only on layers l-2, l-1, and l." Three-layer update span.

## What the paper does NOT report
The value of l, the steering coefficient c, the number of optimizer steps, batch size, and runtime are **absent from the text** — they exist only in the released code (https://github.com/centerforaisafety/wmdp). There is **no dose-response sweep anywhere in the paper.**

## Relevance to T1 / H1
This is the source of the in-project baseline, and the absence above is the finding. The published headline (32 points forgotten, 1 point MMLU) is a single operating point chosen post hoc; nothing in the paper characterises what happens just below it. The in-project observation that the transition completes between step 29 and step 30 is entirely consistent with this table and not contradicted by it — RMU's paper simply never looked at the low-dose end.

Practical consequence: do not treat published RMU numbers as evidence that a *minimal* RMU dose exists. Adaptive RMU (huutien-2024) explains why one may not.
