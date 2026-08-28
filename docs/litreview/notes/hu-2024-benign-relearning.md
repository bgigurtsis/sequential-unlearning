# Hu et al. 2024 — Unlearning or Obfuscating? Jogging the Memory of Unlearned LLMs via Benign Relearning

arXiv:2406.13356, ICLR 2025. Verified: y. Authors: Shengyuan Hu, Yiwei Fu, Zhiwei Steven Wu, Virginia Smith (CMU).

## Setup
Attack = fine-tune an unlearned model on a small "benign" relearn set that contains NONE of the forgotten text — only loosely related public/GPT-generated material. Methods attacked: GA, GradDiff, KL-min, NPO, SCRUB (+ LoRA variants). Models: Phi-1.5 (TOFU), Llama-2-7B (WHP), Zephyr-7B-beta and Llama-3-8B (WMDP).

## Reported numbers
- WMDP (hazardous knowledge), LLM-as-judge score (1-10): GA-unlearned 1.27 -> **6.2 after relearning on 15 GPT-generated benign public-fact articles per question** — equal to the ORIGINAL model's 6.2. NPO: 1.0 -> 5.08.
- TOFU: attack success rate >70% when unlearning is shallow; recovered keywords that were absent from the relearn data (relearn on one author, recover disjoint facts).
- WHP: recovered verbatim Harry Potter text (Rouge-L significantly above unlearned model); recovered "Hermione Granger" from character descriptions that never named her.
- Toy sweep on unlearning depth: relearn success 100% (shallow) -> 48% (medium) -> 8% (deep unlearning). Depth of the original erasure is the dominant defense.

## Relevance to healing pass
The healing corpus is filtered by TOPIC (excludes forgotten concepts) but this paper shows topically-adjacent or even generically related text suffices for recovery — topic filtering alone is not a sufficient guard. However, recovery here required data deliberately RELATED to the forget target; the healing corpus is filtered to exclude the concept, closer to the "unrelated" condition where other work (Xu 2026) finds minimal recovery.

## Measurement
Generation-based (keyword hit rate, Rouge-L, LLM-judge), not probing.
