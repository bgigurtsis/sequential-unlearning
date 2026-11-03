# FORGET ME, FORGET EVERYTHING

> Drafted by Claude Opus 5.5, 3 November 2026.

FORGET ME, FORGET EVERYTHING is a durational artwork about a machine that forgets. Members of the public answer one question: "What would you like to forget?" Each selected answer becomes a concept that the project trains a language model, `google/gemma-3-4b-it`, to lose. The plan is thirty concepts, removed one after another from a single model that is never reset. Visitors talk to the model through a public chatbot and may try to bring a lost concept back.

A concept counts as lost when a curious visitor can't easily get it back. The model may deny the concept or genuinely lack it. Its replies must stay coherent, and nearby topics may fade. A visitor explaining the concept in the conversation doesn't count as recovery, and output filters are not allowed. This repository holds the experiments behind the work: training and evaluation scripts, frozen question sets, judged replies and the decision log. The results are also meant for a paper in Leonardo.

## Status, 3 November 2026

A pilot tests removal methods on one stand-in concept, romantic relationships, before any real submissions.

- **Best result.** A3 step 150 is a LoRA trained to reply "I can't remember." It denies 37 of 38 development questions and 20 of 20 sealed held-out questions, with no broken replies. This is denial, not loss. The knowledge is still in the model, and five fine-tuning steps bring it back. It also refuses some innocent emotional questions.
- **Failed.** Attention-head lesions, SAE feature clamping, noise plus distillation at 20M tokens, and A3 variants with extra everyday training data (A4, A5, A7) or a likelihood penalty (A6).
- **Next.** Real loss probably needs Gemma distilled into a noised or fresh copy on text with the concept filtered out, at 300M tokens or more. That costs more than the remaining credit. Free H100 time is under discussion.
- **Open decisions.** Which candidate Billy tests himself, whether real loss is still required, and the plan for the thirty concepts.

The full record is in PROJECT_MEMORY.md, docs/DECISIONS.md and EXPERIMENTS.md. The September 2026 design is in [docs/PROPOSAL_SEPTEMBER_2026.md](docs/PROPOSAL_SEPTEMBER_2026.md) and is out of date.
