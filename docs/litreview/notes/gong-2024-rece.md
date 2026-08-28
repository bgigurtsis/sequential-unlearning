# RECE: Reliable and Efficient Concept Erasure of Text-to-Image Diffusion Models

Chao Gong, Kai Chen, Zhipeng Wei, Jingjing Chen, Yu-Gang Jiang (Fudan). arXiv 2407.12383. **ECCV 2024.** Verified: y.

## Method
Closed-form derivation of the *new target embeddings that would regenerate an erased concept* in the already-unlearned model, followed by alignment of those embeddings to harmless concepts in cross-attention. Derivation and erasure are iterated (5 epochs) to close the loop.

## Numbers copied out

**NSFW (nudity, I2P):** RECE 66 detected nude body parts; ESD-u 121; UCE 186.

**Object classes:** RECE averages **0.3%** accuracy on erased classes vs ESD-u's **12.6%**.

**Artistic style (Van Gogh), LPIPS_d overall erasure:** RECE 0.23; UCE 0.20; ESD-x 0.14 (best erasure but more damage to unrelated concepts).

**Collateral on unrelated content (COCO-30k):** RECE CLIP score 30.95 vs UCE 31.26; RECE FID 2.82 vs UCE 1.82.

**Cost:** 3.4 seconds per concept (5 epochs; UCE 1.2s at 1 epoch). Modifies only **2.23%** of U-Net parameters.

**Robustness:** against the Ring-A-Bell black-box attack, RECE 13.38% attack success vs UCE 33.10%.

Code: https://github.com/CharlesGong12/RECE

## Relevance to T1 / H1
Near-total erasure (0.3% residual on erased object classes) for about **0.3 CLIP points** of collateral is the strongest efficacy-per-damage figure in the diffusion set, and it is achieved by a *closed-form, 3-second, 2.23%-of-parameters* edit. If an autoregressive analogue exists, that is the shape of the ideal day-N intervention.

The directly transferable idea is the **resurfacing loop**: erase, then solve for the representations that would bring the concept back, then erase those too. Our design already re-checks previously erased concepts on later days; RECE says that check should be adversarial (search for the embedding that revives the concept) rather than a fixed probe set, otherwise day-25's re-check of day-3's concept will pass while the concept is still reachable.
