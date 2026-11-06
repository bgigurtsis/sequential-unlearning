# Approach W edit log

Editor: Claude Opus 5.5 (the manager session), under docs/DECISIONS.md "2026-11-06: approach W".
Base: google/gemma-3-4b-it 093f9f388b31de276ce2de164bdc2081324b9767, local copy C:\Users\Billy\wsp-gemma\base.
Budget: 50 forward passes. Kernel reads of weights on the CPU are unlimited. No gradients.

## Kernel notes

- 2026-11-06: 883 tensors, 442 in the language model. 34 layers, hidden 2560, MLP 10240, q_proj 2048x2560 (8 heads of 256), k/v 1024x2560 (4 KV heads), o_proj 2560x2048. Embeddings 262208x2560, tied to the output head.
- Gemma 3 uses sandwich norms. The MLP output passes through post_feedforward_layernorm (RMS normalisation, then an elementwise gain g) before it joins the residual stream. Gemma's RMS norm multiplies by (1 + weight), so g = 1 + w. To stop a down_proj from writing direction r into the residual, its output must be made orthogonal to g*r, not to r. The same holds for o_proj with post_attention_layernorm. Removing a component also lowers the RMS, which scales the rest up slightly.
