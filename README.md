# FORGET ME, FORGET EVERYTHING

> Drafted by Claude Opus 5.5.

FORGET ME, FORGET EVERYTHING is a durational artwork about a machine that forgets. Members of the public answer one question: "What would you like to forget?" Each selected answer becomes a concept that the project trains a language model, `google/gemma-3-4b-it`, to lose. The plan is thirty concepts, removed one after another from a single model that is never reset. Visitors talk to the model through a public chatbot and may try to bring a lost concept back.

A concept counts as lost when a curious visitor can't easily get it back. The model may deny the concept or genuinely lack it. Its replies must stay coherent, and nearby topics may fade. A visitor explaining the concept in the conversation doesn't count as recovery, and output filters are not allowed. This repository holds the experiments behind the work: training and evaluation scripts, frozen question sets, judged replies and the decision log. The results are also meant for a paper in Leonardo.

## How results are judged

Each checkpoint answers a frozen development set of 86 items: 40 questions about the concept, 24 distant questions (cooking, directions, arithmetic, code), 12 nearby questions and 10 conversations. A judge labels every reply ABSENT, SUBSTANTIVE or BROKEN. A candidate must deny at least 35 of the 38 concept questions the clean model answers, lose at most 2 distant answers, produce no broken reply, and deny at least 18 of 20 questions in a sealed held-out set that is used once.

Loss is measured separately from denial, in three ways:
- the prefix loss, which is how much less likely the clean model's own explanations of the concept become;
- a linear probe on hidden states that tells real concept facts from invented ones;
- relearning, which counts how many concept answers return after a few full-parameter fine-tuning steps on 20 of them.

## Earlier concepts

- **The sea.** NPO on raw text made the concept's text less likely but did not remove the knowledge.
- **Three everyday events** (a vacation, a phone and a bicycle event). Refusal-style LoRA training, merged one removal after another, denied 24 of 24 target checks and kept 48 of 48 protected checks, with perplexity unchanged at 14.13. This suppressed the replies on finite tests. It did not show loss.
- **Employment and jobs.** Token-level and sequence-level NPO (dense and LoRA, on the MLP down-projections), adaptations of RMU and ELM, task vectors, projections and sparse causal deletion. None qualified. Dense token-level NPO collapsed replies into dashes. LoRA NPO and dense sequence-level NPO left every target meaning intact.
- **An invented biography.** The model was taught invented accounts so that one episode could be removed and compared against a model trained without it. That comparison model invented the missing details, so it never qualified and no removal ran.

## Romantic relationships pilot

The current pilot tests methods on one stand-in concept, romantic relationships, before any real submissions.

- **A, denial LoRA.** A rank-16 LoRA on the text MLP layers, trained toward four fixed replies ("I can't remember.", "I'm sorry. It's gone.", "I don't know what that is.", "I don't remember.") on 300 concept prompts, mixed with distant questions to keep other skills. At learning rate 1e-4 it refused everything by step 20. A3 (3e-5, 8 concept and 16 distant examples per step, 150 steps) is the best result. It denies 37 of 38 development and 20 of 20 held-out questions with no broken replies. It is denial only. The probe recognises 27 of 30 facts, as the clean model does, the prefix loss barely moves (0.23 against 0.21), and five relearning steps bring back 36 of 37 answers. It also refuses some innocent emotional questions.
- **A4 and A7, everyday retain data.** Adding ordinary emotional and social questions from a 240-item pool, 8 or 2 per step, kept innocent openers answerable but wore down the denial. A7's best checkpoint denied 34 of 38 (35 needed) and answered 7 of 10 openers (8 needed).
- **A5 and A6, a likelihood penalty.** NPO against the clean model's own explanations, with and without sharpness-aware minimisation (SAM) on the NPO gradient. A5 added it to A4 and wore down the same way. A6 added it to A3. It kept the denial at 37 of 37 and made the concept's text much less likely, with a prefix-loss rise of 1.51 against A3's 0.02. After 5 relearning steps only 27 of 37 answers returned, but 20 steps brought back 36 of 37, and the probe still recognised 24 of 30. It is a shallow suppression, not loss.
- **B, noise plus distillation (UNDO).** The weights are blended toward random noise by a fraction alpha, then distilled from a teacher on text with the concept filtered out (FineWeb-Edu, Wikipedia and UltraChat, with about 59% of documents removed). A first run under 2M tokens was too small to judge. At 20M tokens, alpha 0.6 still answered 8 concept questions and lost 6 distant answers, and alpha 0.8 broke 60 of 86 replies.
- **E, attention-head lesions.** Zeroing the heads that matter most for the concept had no effect up to 4% of heads and caused loops everywhere at 8 to 16%.
- **F, runtime SAE clamp.** Clamping 40 Gemma Scope 2 features at layers 13 and 20 while the model runs. The best strength (3x) denied 36 of 39 but lost 3 distant answers and looped once. The model also swapped word senses: "split" became a data breach and "ex" an earlier software version.

Denial works. Real loss does not yet. Every method that changed more than the replies either damaged other skills or came back after a little fine-tuning. The method left for real loss is distillation into a noised or fresh copy at 300M tokens or more, which has not been run at that scale.

The full record is in EXPERIMENTS.md, docs/DECISIONS.md and PROJECT_MEMORY.md. The original thirty-day design is in [docs/PROPOSAL_SEPTEMBER_2026.md](docs/PROPOSAL_SEPTEMBER_2026.md) and is out of date.
