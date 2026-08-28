# ESD: Erasing Concepts from Diffusion Models

Rohit Gandikota, Joanna Materzynska, Jaden Fiotto-Kaufman, David Bau. arXiv 2303.07345. **ICCV 2023.** Verified: y.

Stable Diffusion 1.4. Fine-tunes model weights using **negative guidance from the model itself as teacher**; permanent (weight-level), unlike inference-time filtering.

## The structural knob
Two variants, and the difference between them is the paper's transferable lesson:
- **ESD-x** — updates only the cross-attention parameters. Edit is conditioned on the prompt; neighbouring concepts largely preserved. Used for artist styles.
- **ESD-u** — updates unconditional (non-cross-attention) parameters. Broader, global effect. Used for NSFW removal.

Same objective, same dose, different *location* — and the collateral profile differs substantially. Localisation, not dose, is the primary collateral control.

## Numbers
The abstract page reports no interference table. Validated on NSFW removal (vs Safe Latent Diffusion and censored-training baselines) and on erasing five modern artists' styles with human evaluation. The comparative numbers for ESD in this review come from the RECE and MACE tables instead: RECE reports ESD-u at 121 detected nude body parts on I2P (vs RECE 66, UCE 186) and **12.6% accuracy on erased object classes vs RECE's 0.3%**; MACE reports ESD-x/ESD-u both degrading in specificity at 100 concepts.

Code: https://github.com/rohitgandikota/erasing

## Relevance to T1 / H1
Supports H1 through the localisation channel specifically. For gemma-3-4b the analogous question is which submodule carries a concept's conditioning — attention vs MLP, and which layer band — and ESD is the cleanest demonstration that picking the narrow one buys a large collateral reduction at no cost in forgetting for concepts that live there.

Also the origin of the "erased concept resurfaces under a different prompt" problem that RECE later formalises: weight-level erasure of a concept name does not erase the concept's other routes. Directly relevant to our day-N re-check of previously erased concepts.
