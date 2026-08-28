# Frantar et al. 2022 — GPTQ: Accurate Post-Training Quantization for Generative Pre-trained Transformers

arXiv 2210.17323 · ICLR 2023 · verified y
Code: https://github.com/IST-DASLab/gptq

## Why it matters for T5

Quantisation is the dial the brief asks about, and the answer is clear: **too coarse to schedule, but an excellent one-shot terminal instrument.**

## Digitised dose–response (WikiText2 perplexity)

OPT-175B:

| Bits | RTN | GPTQ |
|---|---|---|
| FP16 | 8.34 | 8.34 |
| 4 | 10.54 | 8.37 |
| 3 | 7.3e3 | 8.68 |

BLOOM-176B:

| Bits | RTN | GPTQ |
|---|---|---|
| FP16 | 8.11 | 8.11 |
| 4 | 8.37 | 8.21 |
| 3 | 571 | 8.64 |

GPTQ at 3-bit across OPT scales: 125M **53.85**, 350M **33.79**, 1.3B **20.97**, 66B **14.16**, 175B **8.68**.

## Shape

Not a curve — four usable rungs (16 / 8 / 4 / 3 bit), of which 16→8 and 16→4 are nearly free with a good method. Then a **cliff**: naive round-to-nearest goes from 10.54 to 7,300 perplexity between 4 and 3 bits on OPT-175B, a ~700x jump for one bit. 2-bit collapses for essentially every baseline method.

Ma et al. 2025 (Model Hemorrhage) describe the same boundary as the point at which "accuracy degradation transitions from linear to exponential collapse".

## The scale trend is the opposite of what we want

"Larger models generally appear easier to quantize": at 3-bit, OPT-125M is at 53.85 perplexity while OPT-175B is at 8.68 — a 6x difference driven purely by scale. Our 4B model sits near the fragile end, so the 4→3 bit step will be much more violent for us than the headline numbers suggest.

## Fitness as our dial

- **As a daily dial: no.** Three or four levels cannot express a 30-step schedule, the levels are unevenly spaced, and most of the dynamic range is concentrated in a single step.
- **As terminal collapse: excellent.** Naive RTN at 3-bit (explicitly *not* GPTQ — we want the uncalibrated version) is a one-line, deterministic, fully reversible intervention that reliably converts a working model into an incoherent one. It is cheap on 4B, needs no calibration data, and its failure is documented and reproducible.
- **Reversibility**: total — quantise a copy, keep the BF16 original.

## Relationship to the primary dial

Quantisation error is, to first order, bounded uniform weight noise. This makes it conceptually the *same family* as our Gaussian dial, with the bit width acting as a coarse, deterministic quantiser of the dose. That is a useful framing for the piece: the terminal 3-bit step is not a different kind of violence from the daily noise, only a much larger and irreversibly discretised one.
