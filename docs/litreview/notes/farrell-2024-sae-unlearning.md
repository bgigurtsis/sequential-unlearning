# Applying sparse autoencoders to unlearn knowledge in language models

Eoin Farrell, Yeu-Tong Lau, Arthur Conmy. arXiv 2410.19278, Oct 2024. Verified: y.

Models: **gemma-2b-it** and **gemma-2-2b-it** — same family as our target.

## Numbers and findings copied out
- **Zero-ablating features is ineffective.** Setting SAE feature activations to 0 produced no meaningful unlearning.
- Clamping is required, and the required magnitude is large: feature #9163 had to be clamped to roughly **−18 to −20** before the probability of the correct answer fell from >0.99 to comparable with the incorrect options.
- **Narrower is better:** on gemma-2-2b-it, "intervening on 10 features appears to be most effective", with lower added loss than 20 or 50 features.
- Against RMU: similar WMDP-bio unlearning but with "similar or larger unwanted side-effects"; RMU showed minimal MMLU degradation while the SAE intervention showed greater collateral. In DSG's later table, this method sits at WMDP-Bio 59.22% / MMLU 99.03%.

Code: https://github.com/efarrell1/train_sparse_autoencoder

## Relevance to T1 / H1
An honest negative result on the method, and two positive results on the *phenomenon*:

1. **Another threshold nonlinearity, in a completely different method family, on Gemma.** Nothing happens at zero-ablation; the effect appears only past a large negative clamp. This is independent corroboration that the in-project step-29→30 cliff is not an RMU artefact but a property of how concept knowledge is stored — the model appears to route around small perturbations until the perturbation is large enough to dominate.
2. **Readout width is a genuine collateral knob**: 10 features beat 20 and 50 at matched forgetting. Narrowing the readout is one of the few interventions in this thread that shrinks collateral without weakening forgetting.

Counts against H1 in its strong form: at matched WMDP-bio forgetting this method has *worse* collateral than RMU, so SAE feature intervention is not the minimal-dose recipe. DSG's gating is what rescues the family, and that comes at the cost of no longer being a weight-space edit.
