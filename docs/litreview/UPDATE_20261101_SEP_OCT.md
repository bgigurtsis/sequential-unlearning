# Literature update: September and October 2026

Date: 2026-11-01. Repository base: commit `d2094d3`. Scope: work first posted
1 September to 31 October 2026, plus earlier items missing from `papers.csv`.
Four search agents covered unlearning robustness, interpretability-guided
removal, lesions and degradation, and artistic and critical context. I then
opened the primary pages for the items that bear most on the project's options.

Verification tags:

- **[checked]**: I opened the primary page and confirmed the numbers quoted here.
- **[abstract checked]**: I confirmed the title, date and main claim. The
  numbers come from a search agent's reading of the full text.
- **[agent only]**: from a search agent, not opened by me. Most ICLR 2027
  submissions are in this group, because OpenReview showed me a browser check.
  The agents read their abstracts through the OpenReview API.

All numbers are the authors' own. No item below has an independent replication
yet.

## What changed

Output grew sharply: 160 arXiv papers in the window mention unlearning, and 343
ICLR 2027 submissions match the term. The main change is in evaluation. Several
groups find that output-level forgetting overstates removal, that internal
probes still read the "forgotten" answer, and that common protocols hide
collateral damage. No paper removes a broad everyday concept from a dense model
of about 4B parameters in a way that is both robust and low in collateral
damage. The one paper that tests gemma-3-4b-it reports almost no forgetting. No
one has published a follow-up to UNDO. The closest art precedent, a SIGGRAPH
2026 installation that decays a model's weights as an analogy for forgetting,
appeared in June.

## Does unlearning remove knowledge or hide it?

- **Unreal Unlearning: Behavioral Forgetting Without Knowledge Erasure.**
  ICLR 2027 submission, https://openreview.net/forum?id=ITPcS1Qvif. Across
  eight methods on WMDP-Bio, a linear probe still decodes 21.8% to 31.3% of
  the questions that were suppressed at the output. [agent only]
- **Implicit Evocation in Unlearning-Based Alignment.** ICLR 2027 submission,
  https://openreview.net/forum?id=wBfajUkDn1. On two instruction models of
  about 4B, tested on real people from RWKU, a logit lens ranks the target
  answer highly at middle layers after GA or NPO unlearning. This is the
  setting closest to ours. [agent only]
- **A Lie Detector Test for Language Models (PIR).** Dingeto, 18 Sep 2026,
  https://arxiv.org/abs/2609.21996. A label-free readout identifies which
  answer a model recognises, with 0.70 to 0.87 balanced accuracy against 0.28
  to 0.40 on items it never knew. Recognition stays at 0.85 to 0.93 under
  password-locking and circuit breakers. When unlearning really removes
  knowledge, recognition drops to the never-known level. This disagrees with
  Unreal Unlearning on RMU. No code yet. [abstract checked]
- **The Tokens Remember.** Baser et al., 24 Sep 2026,
  https://arxiv.org/abs/2609.29045. Re-tokenising the same text bypassed edits
  or unlearning in 38.6% of cases across five models. [agent only]
- **When Deletion Writes: Target Imprints.** ICLR 2027 submission,
  https://openreview.net/forum?id=YchGapqmwe. Deletion losses that name the
  target token can make it recoverable afterwards, even for random targets the
  model never knew. Our layer-4 recovery vector, which brought back 13/24
  employment answers, needs a random-target control before it counts as proof
  that the knowledge survived. [agent only]
- **Retrained Models Can Relearn in Context.** ICLR 2027 submission,
  https://openreview.net/forum?id=mvYeASTcR9. A model retrained without a fact
  still infers it from context when the context makes it inferable. Recovery
  from a supplied context is therefore not proof of retained knowledge. This
  supports the bar Billy set on 1 November: the model using what a visitor
  explains does not count as recovery. [agent only]
- **Token-Triggered Forgetting (EE-TNPO).** ICLR 2027 submission,
  https://openreview.net/forum?id=j75CM5OwMa. Gradient and low-rank unlearning
  works through attention to the named target tokens, and it fails when the
  target is implied. This matches the employment result of 36/36 direct
  questions passed but 4 of 9 indirect questions leaked. [agent only]
- **How Well Does LLM Unlearning Generalize?** ICLR 2027 submission,
  https://openreview.net/forum?id=HXWNgUXeAl. Forgetting transfers poorly
  between question and verbatim forms and into low-resource languages. Updates
  to MLP layers generalise best, and value and output-projection updates give
  surface forgetting. [agent only]
- **Does the Model Use the Feature?** Che and Li, 5 Oct 2026,
  https://arxiv.org/abs/2610.07270. Steering an SAE "unknown entity" latent
  raises abstention from 33.0% to 79.0% on Gemma 2 2B-IT. Setting it within
  its natural range moves abstention by only 1.5 points. A steered "I don't
  know" does not use the model's own mechanism. [agent only]

## Collateral damage

- **Unlearning Can Hurt When There Is Nothing to Forget.** ICLR 2027
  submission, https://openreview.net/forum?id=bJ4hT11duP. At least 74% of
  RMU's MMLU damage also appears on a copy that never learned the forget
  documents. Some of our chat collapses may come from the method, not the
  removal. [agent only]
- **Unlearning Can Remember the Test and Forget the Rest.** ICLR 2027
  submission, https://openreview.net/forum?id=M6F3f0A89g. Retain sets the
  method trained on stay intact, while untargeted people it never saw lose 44%
  to 104% as much accuracy as the targets. Protected-meaning checks need a
  holdout the edit never trained on. [agent only]
- **Entangled Representations Amplify Collateral Damage.** Wybitul et al.,
  2 Sep 2026, https://arxiv.org/abs/2609.02285. In 254M models trained with
  graded disentanglement, the most disentangled pay about four times less
  retain cost for the same forgetting, and adjacent topics take more spillover
  than distant ones. [agent only]
- **Early Memories Don't Fade Easily.** ICLR 2027 submission,
  https://openreview.net/forum?id=XLXTYlzcFF. Knowledge learned early in
  pretraining is harder to remove. Everyday concepts such as the sea are the
  hard case. [agent only]
- **Making LLMs Truly Forget (DUMIC).** Wang et al., 28 Sep 2026,
  https://arxiv.org/abs/2609.34442. Severing the supporting facts deepens
  forgetting at a cost to locality. A search agent read 0.387 deep forgetting
  for target-only removal and 0.999 when all supporting facts are removed, with
  locality falling from 0.926 to 0.196. The abstract gives no numbers.
  [abstract checked]

## Mechanisms that resist recovery

- **UNDO, Distillation Robustifies Unlearning.** Lee, Foote, Infanger, Shor,
  Kamath, Goldman-Wetzler, Woodworth, Cloud and Turner. arXiv 2506.06278, v3
  24 Oct 2025, NeurIPS 2025 spotlight. Code: MIT licence, no checkpoints,
  https://github.com/AddieFoote/distillation-robustify-unlearning. [checked]
  - The method suppresses with MaxEnt, then mixes the weights with Xavier
    noise, θ' = (1 − α)·θ + α·β·N, then distills the suppressed model's outputs
    into the noised copy with forward KL. It stops at 95% of the teacher's
    retain score or one epoch.
  - On synthetic tasks, robustness to relearning rises with α, and at
    α = 0.6 it comes close to a model trained without the data.
  - On WMDP with Gemma 2 2B, distillation used about 300M tokens (0.015% of
    pretraining) and took "around 7 hours on one H200". MMLU ended 4.88%
    lower. UNDO "consistently improves relearning resilience", but the gains
    were less clear-cut than on synthetic tasks.
  - The distilled student inherits the teacher's trade-off between retaining
    and forgetting.
  - Not tested: instruction-tuned starting models, repeated or sequential use,
    broad everyday concepts, and recovery by prompting or activation steering.
    The only attacks were fine-tuning and 4-bit quantisation.
  - No follow-up appeared in September or October 2026.
- **SGTM, Beyond Data Filtering: Knowledge Localization for Capability
  Removal.** Shilov, Cloud, Gema, Goldman-Wetzler, Panickssery, Sleight, Jones
  and Anil, 5 Dec 2025, https://arxiv.org/abs/2512.05648. A gradient-routing
  variant that masks gradients so target-domain examples update only their
  dedicated parameters, which are then removed. Under labelling errors it beats
  data filtering on the retain/forget trade-off. Recovery takes seven times
  more fine-tuning steps than RMU. It is applied during pretraining. [checked]
- **REX, Relocating Hazardous Knowledge into Removable Experts.** Jin et al.,
  19 Oct 2026, https://arxiv.org/abs/2610.25791. This applies only to
  mixture-of-experts models: Intern-S2, Qwen3.5-35B-A3B and Gemma-4-26B-A4B.
  It adds experts, moves target knowledge into them, then cuts them out. On
  Qwen3.5, WMDP-Bio fell 48.4 points while MMLU changed by under 3 points.
  After 250M fine-tuning tokens, REX rose from 32.4% to 42.8%, while the best
  of nine baselines rose from 44.1% to 78.3%. A critique,
  https://openreview.net/forum?id=qTH7I1CkN6, argues that measuring under the
  model's own routing overstates forgetting in mixture-of-experts models
  [agent only]. Gemma 3 4B is dense, and no dense version of REX has been
  tested. [checked]
- **Neighbourhood-Robust LLM Unlearning in Query and Weight Space.** ICLR 2027
  submission, https://openreview.net/forum?id=hrveinV6zZ. Ten probing
  strategies recover 0.83 of facts from the original model, 0.08 from a
  retrained reference and 0.51 after NPO. Training against red-team queries
  regenerated as the model changes cuts recovery by up to 0.345 at matched
  utility. Tested on fictitious facts only. [agent only]

## Interpretability and structural edits

- **Storage Is Not Strategy.** Qian et al., 29 Sep 2026,
  https://arxiv.org/abs/2609.37858. A storage-location score reaches AUROC
  0.981, yet editing that location is the better intervention for only 17 of
  36 targets, and LoRA beats it on 35 of 36. This agrees with our MLP-column
  result. [agent only]
- **Every Ablation Is a Dose** (Ahmad et al., 1 Oct 2026,
  https://arxiv.org/abs/2610.02173) and **Hidden not Deleted** (Samanta et al.,
  23 Sep 2026, https://arxiv.org/abs/2609.27593). Downstream directions
  counteract an ablated signal in 52 of 81 cases. In toy networks, a single
  scalar patch restores suppressed features. [agent only]
- **Norm Share Predicts Whether a Subspace Ablation Removes the Feature or the
  Model.** ICLR 2027 submission, https://openreview.net/forum?id=AING0NXEFo.
  When an ablated subspace holds more than half of a token's squared residual
  norm, the ablation breaks every language. On Gemma 3, projection broke the
  model while zeroing the same SAE latents stayed selective. This fits our
  52/52 incoherent replies and the mean-protection fix. [agent only]
- **Rotation-First Unlearning (RFU).** ICLR 2027 submission,
  https://openreview.net/forum?id=kvzlRwS73X. A closed-form edit that shrinks
  the directions where forget activity dominates retain activity. A spectral
  check predicts beforehand whether the edit will be selective. The abstract
  gives no numbers. [agent only]
- **Orthogonal Boundary Unlearning.** Ronchetti, 20 Oct 2026,
  https://arxiv.org/abs/2610.27490. On gemma-3-4b-it, WMDP-Cyber went from
  41.12% to 40.56% (Projected LoRA) or 39.05% (closed-form surgery), and MMLU
  from 57.11% to 56.33% or 54.56%. The author writes that the method "primarily
  steers the model toward refusing ... rather than erasing the underlying
  hazardous facts". No RMU or NPO baseline. [checked]
- **SCALPEL** (https://arxiv.org/abs/2609.31056) and **ARIA**
  (https://arxiv.org/abs/2609.16229) act at inference time, and SCALPEL's
  authors state it "does not erase the parametric trace". **SAE-Locked LoRA**
  (https://openreview.net/forum?id=Tlffy1vOZ2) kept 91.8% of 100 sequential
  edits working, against 8.4% for plain LoRA, but was not tested for removal.
  [agent only]
- **Parameter decomposition** reached a 67M model (VPD,
  https://arxiv.org/abs/2610.20748) and one matrix of Qwen-3-8B (ASPD,
  https://arxiv.org/abs/2609.37731). Neither tests knowledge removal.
  [agent only]
- **Gemma Scope 2** provides SAEs and transcoders "trained on every layer of the
  Gemma 3 family" (https://ai.google.dev/gemma/docs/gemma_scope, page updated
  19 Dec 2025). The page does not name the 4B model. A search agent reports
  that circuit-tracer 0.5.0 supports Gemma 3, and that Gemma 4, released
  31 Mar 2026, has only community SAEs at a few layers. Gemma 3 4B remains the
  best-instrumented model at this size. [checked for the family-level claim]

## Lesions and graded degradation

- **Can Language Models Get "Aphasia" From Neuronal Ablation?** Worah and
  Bateman, 20 Oct 2026, https://arxiv.org/abs/2610.28214. Transformer MLP
  ablation shows a "late threshold-like collapse". Attention-head ablation
  declines more smoothly, in a sigmoid, and drifts toward loss of semantic
  specificity like the semantic variant of primary progressive aphasia. LSTMs
  decline gradually. A search agent read the collapse for Qwen1.5-0.5B as
  falling between 30% and 40% of MLP neurons removed. [abstract checked]
- **Language Impairment as a Lens onto Large Language Models.** M. He et al.,
  20 Oct 2026, https://arxiv.org/abs/2610.28992. Head lesions reach the
  targeted aphasia label in 54 of 66 settings, but on new prompts the targeted
  type appeared in 1 of 139 lesioned answers, and random pushes of the same
  norm cancel 91% of lesions. [agent only]
- **Transformer MLP Gate Thresholds Are Couplings to a Carried Reference
  Direction.** Tuomi, 25 Sep 2026, https://arxiv.org/abs/2609.31956. Noise
  along the residual stream's mean direction costs 8 to 42 times as much as
  the same energy along a random direction. This is a candidate cause of our
  noise cliffs. Gemma is not tested. [agent only]
- **IrekoGPT** (https://arxiv.org/abs/2610.00426) and **LADDER**
  (https://arxiv.org/abs/2610.28773) build nested SliceGPT widths and nested
  pruning masks, so each dose contains the previous one. This is relevant to
  the V4 SliceGPT protocol. [agent only]
- No study in the window tests damage that spreads outward from one concept.
  Wybitul et al. (above) is the closest: spillover concentrates on adjacent
  topics.

## Earlier items missing from papers.csv

These are all [agent only].

- Łucki et al. 2024, An Adversarial Perspective on Machine Unlearning for AI
  Safety, https://arxiv.org/abs/2409.18025. Ten unrelated fine-tuning examples,
  or removing activation directions, restore most of what RMU removed.
- Sheshadri et al. 2024, Targeted Latent Adversarial Training,
  https://arxiv.org/abs/2407.15549. Makes unlearning more robust to
  relearning. Code and models are released.
- Jin et al. 2024, RWKU, https://arxiv.org/abs/2406.10890. A benchmark of 200
  real people with nine adversarial probe types, for knowledge a model already
  has.
- Hong et al., Intrinsic Test of Unlearning Using Parametric Knowledge Traces,
  https://arxiv.org/abs/2406.11614. Standard unlearning barely moves the MLP
  vectors that encode a concept. Ablating those vectors removes it more
  robustly.
- Sondej and Yang 2025, Collapse of Irrelevant Representations,
  https://arxiv.org/abs/2509.11816.
- PISCES (https://arxiv.org/abs/2505.22586), CRISP
  (https://arxiv.org/abs/2508.13650) and EMBER
  (https://arxiv.org/abs/2606.03695) are SAE-guided or embedding-row weight
  edits.
- Rogers, Lambon Ralph, Garrard et al. 2004, Psychological Review 111:205-235.
  Removing a growing share of a semantic network's weights reproduced the
  naming errors of semantic dementia: omissions and superordinate errors rise
  with severity.
- Jarvis et al., https://arxiv.org/abs/2503.03545. Deletion followed by
  relearning, not deletion alone, reproduced errors specific to semantic
  dementia.
- R. He et al., 4 Aug 2026, https://arxiv.org/abs/2608.03067. Scaling the
  down-projection weights of FFN neurons associated with Alzheimer's in
  Qwen3-8B produced graded impairments in recall and fluency.
- Roll et al., 15 May 2026, https://arxiv.org/abs/2605.16222. Bernoulli lesions
  in five 1B models, including Gemma 3-1B-Instruct, produced repetition loops
  in 43.4% of outputs, against 10.9% in AphasiaBank.

## Artistic and critical context

- **Echoes of the Prior: A Computational Phenomenology of Forgetting.** Gao,
  Schölkopf and Geiger, SIGGRAPH 2026 Art Papers,
  https://arxiv.org/abs/2606.12340, submitted 10 June 2026. An installation that
  induces "controlled synaptic decay" in a feed-forward 3D reconstruction model
  as an analogy for eroding predictive priors. A search agent reports that a
  reversible slider controls the decay and that the paper does not engage with
  people affected by dementia. This is the closest precedent. A claim of
  novelty for this project has to rest on language, irreversibility, visitor
  input and duration. [checked for title, date, venue and premise]
- **Machine Unlearning.** Erin Gee with Sofian Audry, performance 2019,
  https://eringee.net/?p=1995. An LSTM trained on Wuthering Heights steps back
  through its training epochs. It has the same title and a related idea.
  [agent only]
- Other precedents for whole-model decline: Mario Klingemann's Neural Glitch
  (2018), The Caretaker's Everywhere at the End of Time (2016 to 2019), and
  Maria Mavropoulou's Model Collapse: Love you, bye (2025). [agent only]
- **Critical and legal context.** Thylstrup and Søe, The Information Society,
  11 Sep 2026, https://doi.org/10.1080/01972243.2026.2725353, read unlearning
  as a reorganisation of knowledge and ignorance. The EDPB draft Guidelines
  03/2026 treat guaranteed deletion from models as not yet available and rely
  on output filters meanwhile. A. Feder Cooper et al., Machine Unlearning
  Doesn't Do What You Think (NeurIPS 2025, https://arxiv.org/abs/2412.06966),
  separate removal from suppression. [agent only]
- **Audiences.** De Freitas et al., Nature Human Behaviour, 3 Sep 2026,
  https://doi.org/10.1038/s41562-026-02569-3, found that users mourned
  chatbots whose behaviour changed, describing them as a different person.
  [agent only]
- **Dementia representation.** The DEEP guide Dementia words matter
  (https://www.worc.ac.uk/documents/DEEP-Guide-Language.pdf) lists "living
  death" among phrases to avoid, which bears on a collapse at day 30.
  [agent only]

## What this changes for the project

- **Trained refusal.** The internal-audit papers predict that the knowledge
  stays readable inside the model. Token-Triggered Forgetting predicts leaks on
  implied questions, which is what employment showed. Training on MLP layers,
  in several question forms and languages, is the literature's best advice.
- **UNDO with filtered text.** This is still untested on everything this
  project needs. That makes a pilot new evidence rather than a repeat. SGTM and
  REX show that localising knowledge into removable parameters resists
  relearning far better than fine-tuning-based unlearning. REX is the only
  version applied to a model already trained, and it needs a
  mixture-of-experts model.
- **Weight lesions.** Storage Is Not Strategy and Every Ablation Is a Dose
  explain why zeroing the attributed columns did nothing. Worah and Bateman
  suggest that attention-head lesions give a smoother dose curve than MLP
  lesions. Norm share offers a one-pass check for global breakage.
- **Cheap checks before any training.**
  - Run PIR and a linear probe on the archived narrow-event and employment
    checkpoints.
  - Re-tokenise the 24 narrow-event targets.
  - Add a random-target control to the layer-4 recovery vector.
  - Compute norm share for the old projection runs.
  - Probe one whole-concept checkpoint for errors graded by semantic distance.

  All of these need forward passes only.

## Gaps

- OpenReview PDFs and pages were behind a browser check, so ICLR 2027 items
  rest on abstracts.
- The EMNLP 2026 volumes, the full NeurIPS 2026 list, the Alignment Forum, X,
  journals issue by issue, and most non-English press were not swept.
