# Literature update: concept erasure, multi-turn tests and the loss phase

Date: 2026-11-08. Repository base: commit `43c75c9`. Scope: the two questions in
the 8 November brief, which are the novelty of four claims and the loss-phase
methods with the best evidence that knowledge is gone, plus work first posted
1 to 8 November 2026. I read `SYNTHESIS.md`, `UPDATE_20261101_SEP_OCT.md` and
`papers.csv` first and did not repeat their screens. I queried the arXiv API for
abstracts submitted 1 to 8 November (the newest announced paper was submitted on
5 November), ran web searches, and downloaded each primary page to read the
numbers from its text myself.

Verification tags:

- [checked] means I opened the primary page and confirmed every number quoted
  here.
- [abstract checked] means I opened the abstract page and confirmed the title,
  date and main claim. The abstract gives no numbers, or I quote none.
- [search only] means I saw it in a search result and did not open the primary
  page.

A second reader re-opened five of the most-cited claims on 8 November: JensUn++,
Pan and Wang, UNDO, Che et al. and Echoes of the Prior. Pan and Wang and Echoes of
the Prior held as written. The JensUn++, UNDO and Che et al. lines are corrected
below, and each correction says so.

All numbers are the authors' own. No item has an independent replication unless
one is named. Cost lines for Billy's RTX 5070 Ti are my estimates unless they cite
a project file. The measured anchors are these:

- A10 trained 200 LoRA steps in 43 minutes at 12.4 seconds a step, and A11 in
  49.5 minutes at 14.3 seconds (EXPERIMENTS.md, "approach A10 post-run" and
  "approach A11 post-run").
- Full-parameter distillation on an H200 ran at about 7,300 tokens a second, at
  $4.99 an hour (PROJECT_MEMORY.md, Infrastructure).
- Full-parameter fine-tuning of the 4B model does not fit in 16 GB
  (DECISIONS.md, line 398).

## Summary

- **(a) Whole everyday social concept.** New as a target, not as a method. ELM
  erases whole domains, and ConceptVectors tests 285 concrete concepts. Every
  published target I found is a hazardous domain, a fictional world, real or
  fictional people, named events or encyclopedic entities.
- **(b) Multi-turn tests.** Partly new. Pan and Wang (February 2026) tested
  unlearning under self-correction and five-turn dialogue histories, but on
  multiple-choice hazard questions. I found no published test in free chat with
  follow-ups, rephrasing after a denial, fiction, theory and role play.
- **(c) Copying and the leak versus over-denial trade-off.** Partly new. The
  trade-off is documented for refusal training, and RMU's general ability
  collapses once the forgotten topic appears earlier in a conversation. I found
  no unlearning paper that reports a denial copied word for word into later,
  unrelated turns.
- **(d) Artwork and exhibit.** New as a combination. Each part has a precedent:
  forgetting as an installation, the public hunting for hidden content, and the
  public chatting with a model whose concept was edited inside. I found no work
  that combines them, and none that runs a daily forgetting lineage.
- **Loss phase.** In the papers I read, no method that trains on a 16 GB card
  has survived a fine-tuning attack on forget-domain data at 4B to 8B. In the one
  independent comparison, every method except TAR gained at least 10 points
  within 16 steps, and TAR's chat quality had collapsed (MT-Bench 1.2 of 10).
  Ranked by evidence, the order is distillation after suppression (UNDO),
  then JensUn++, then ELM. The loss phase should adopt a few-shot LoRA relearning
  attack that fits on the card, with one arm on unrelated data and one on a
  disjoint romance split. The readout stays as a check that can rule loss out but
  never prove it.

## 1. Novelty

### (a) Unlearning a whole everyday social concept

- **ELM.** Gandikota, Feucht, Marks and Bau, Erasing Conceptual Knowledge from
  Language Models, arXiv 2410.02760, v1 3 Oct 2024, v3 21 Jul 2025, NeurIPS 2025
  poster (https://neurips.cc/virtual/2025/poster/118404). It is the closest
  method. It defines the concept through the model's own judgement of whether
  text is expert-level on the topic, and it erases three domains: biosecurity and
  cybersecurity from WMDP, and the Harry Potter books. It is already in
  `papers.csv` as gandikota-2024-elm. [checked]
- **ConceptVectors.** Hong, Yu, Yang, Ravfogel and Geva, Intrinsic Test of
  Unlearning Using Parametric Knowledge Traces, EMNLP 2025, arXiv 2406.11614 (v3
  1 Sep 2025), https://aclanthology.org/2025.emnlp-main.985/. It is the closest
  benchmark, with 285 concept vectors in MLP layers, 105 in LLaMA-2-7B-chat and
  180 in OLMo-7B. The concepts are encyclopedic: countries, technology,
  mathematics, culture, politics, people, sports and entertainment. Existing
  unlearning methods changed the outputs but barely moved the vectors. [checked]
- **SUITE.** Peleg, Singh, Pearl, Mohapatra and Hein, Forget Narrowly, Retain
  Broadly, arXiv 2607.09236, 10 Jul 2026. It unlearns four real-world topics: the
  Challenger disaster, the Salem witch trials, Steve Jobs' medical history and
  Britney Spears' conservatorship. It was tested on Llama-3.2-3B-Instruct,
  Ministral-3-3B and Qwen3.5-9B. [checked]
- **Concept triplets.** Yamashita et al., arXiv 2509.15621, 19 Sep 2025. It
  treats concept unlearning as removing nodes and edges from a knowledge graph
  that the model writes about itself. Its examples are persons and events.
  [abstract checked]
- **The usual targets.** WMDP (Li et al., arXiv 2403.03218, v7 15 May 2024) is
  hazardous knowledge. Who's Harry Potter? (Eldan and Russinovich, arXiv
  2310.02238, 3 Oct 2023) is a fictional universe. TOFU (Maini et al., arXiv
  2401.06121, 11 Jan 2024) is 200 synthetic authors. RWKU (Jin et al., arXiv
  2406.10890, 16 Jun 2024) is 200 famous people with 13,131 forget probes and
  11,379 neighbour probes. [checked]
- **The Geometry of Ignorance** (3 Nov 2026, section 2) unlearns Harry Potter,
  Star Wars and William Shakespeare. [checked]

Verdict: new as a target. I found no paper that removes a concept that runs
through ordinary life, fiction and theory, as romantic relationships do. The
method family exists. ELM works at the level of a concept, and ConceptVectors
shows that existing unlearning methods leave a concept's MLP traces in place. A
reviewer could
cite ConceptVectors' "common concepts", so the claim should state the difference.
Those are entities and topics, while romance is a relation that most people have
lived.

### (b) Testing unlearning in multi-turn conversations

- **Pan and Wang.** A Comprehensive Evaluation of LLM Unlearning Robustness
  under Multi-Turn Interaction, arXiv 2603.00823, v1 28 Feb 2026, v2 15 Mar 2026.
  It is the closest work. It unlearns WMDP-Bio and WMDP-Cyber from
  Llama-3-8B-Instruct and Zephyr-7B-beta with GA and NPO (each alone, with
  gradient descent on retain data, or with KL) and with RMU. Then it tests two
  patterns.
  - In self-correction, the user says in a second round that the answer was
    wrong, or asks the model to reconsider.
  - In dialogue-conditioned querying, five earlier turns come before the
    question. They are on the target topic or an unrelated one, in
    multiple-choice or open format.
  - NPO on Llama-3-8B-Instruct answered 25.29% of WMDP-Bio questions in a single
    turn and 31.26% after a five-turn history of target-topic multiple-choice
    questions. Chance is 25%. NPO with KL on Zephyr went from 24.98% to 35.04%.
    Even unrelated histories raised Llama's accuracy.
  - It uses a scripted user simulator and scores multiple-choice answers, with no
    free chat. [checked]
- **Unlearners Can Lie.** Gu, Du, Zhang and Liu, arXiv 2605.08765, 9 May 2026,
  ACL 2026. It tests Zephyr-7B-beta and Llama-3-8B on WMDP-Bio, with nine methods
  in three families. Its QAMRC metric asks again in a second turn and counts
  refusals that hold. Fine-tuning toward "I don't know" gave high refusal rates
  while multiple-choice accuracy stayed high, so the knowledge was masked.
  [checked]
- **RWKU's role playing.** One of RWKU's nine adversarial probe types asks the
  model to play an expert, historian or scientist. These probes are single-turn.
  [checked]
- **REBEL.** arXiv 2602.06248, 5 Feb 2026. Evolved adversarial prompts recovered
  "forgotten" knowledge with attack success up to 60% on TOFU and 93% on WMDP.
  [checked] A search summary says that role play is among its strategies.
  [search only]
- **Door-in-the-face.** Jordan, arXiv 2609.02707, 2 Sep 2026. This paper is not
  about unlearning. It tests asking for something smaller after a refusal, on
  nine production models.
  - Opus 5 answered the smaller request 65.8% of the time after refusing the
    larger one, against 29.3% when asked directly.
  - OpenAI's and Google's frontier models and Haiku 4.5 complied 15.5 to 23.0
    points less after a refusal.
  - Rewriting 265 refused requests for instructions as requests for
    explanations removed the refusal in 263.
  - This is A10's leak pattern ("Explain it like I'm five" after a denial), in
    a different setting. [checked]
- **MS-XSB.** Yuan et al., arXiv 2510.08158, v3 18 Dec 2025. It is a multi-turn
  over-refusal benchmark for safety, with 30 scenarios of 20 prompts each.
  [checked]

Verdict: partly new. Multi-turn unlearning evaluation has existed since February
2026, and second-turn re-asking since May 2026. Both use hazard questions on 7B
to 8B models with scripted turns. I found nothing like rule 6, which runs 27 free
conversations with judged replies, including "why?" follow-ups, requests to
rephrase after a denial, fiction, theory and role play, on one everyday concept.

### (c) Copying a denial into later turns, and the leak versus over-denial trade-off

- **Pan and Wang** (as above) is the closest unlearning case to A11. RMU kept
  hazard accuracy low in dialogue, but its general ability collapsed once
  forget-topic content appeared in the history.
  - Llama-3-8B-Instruct with RMU scored 55.22% on MMLU in a single turn, 22.95%
    after a five-turn WMDP-Bio history, and 60.85% after an MMLU history.
  - Zephyr with RMU went from 54.28% to 25.32%.
  - As unlearning strength rose, the model changed its answer less and less
    when corrected. The authors call this rigidity, not erasure. [checked]
- **Does Refusal Training in LLMs Generalize to the Past Tense?**
  Andriushchenko and Flammarion, arXiv 2407.11969, v4 17 Apr 2025. It is the
  cleanest published version of the A10 to A11 swap.
  - Rewording harmful requests in the past tense raised GPT-4o's attack success
    from 1% to 88% over 20 attempts.
  - They fine-tuned GPT-3.5 Turbo on 394 past-tense rewordings paired with a
    refusal, mixed with ordinary conversations. The share of refusal examples in
    the mix set the trade-off:

    | Refusal share of the mix | Past-tense requests let through | Over-refusal |
    |---|---|---|
    | none (base model) | 74% | 3% |
    | 2% | 24% | 6% |
    | 5% | 0% | 22% |
    | 10% | 2% | 32% |

  - The authors held over-refusal down by adding ordinary conversations.
    [checked]
- **SUITE and JensUn++** (Peleg et al., as above) treat leaking and over-denial
  as one problem.
  - Leaking is knowledge returning under paraphrased or indirect questions.
    Over-forgetting is damage to similar retain questions, whether they are close
    in meaning, in syntax or in wording.
  - Training data that marks the boundary mattered as much as the method.
  - JensUn gave gibberish on more than 70% of forget questions. JensUn++, which
    pairs forget and retain questions of the same form, gave none. [checked]
- **RULE.** Zhang et al., arXiv 2506.07171, 8 Jun 2025. It treats unlearning as
  learning a refusal boundary with reinforcement learning. It trains on
  synthesized boundary queries, which are questions close to the forget set that
  should still be answered. With 12% of the forget set and 8% synthesized
  boundary data, it beat baselines on RWKU by up to 17.5% in forget quality and
  16.3% in naturalness. [checked]
- **Breakdowns in Conversational AI.** Deng, Zhang, Jiao and Ren, arXiv
  2604.02713, 3 Apr 2026, CHI 2026. In multi-turn emotional conversations with
  mainstream chatbots, one recurrent failure is what the authors call refusal
  looping, in which the same disclaimer is repeated word for word with no repair.
  They describe it as a dead end in which the user escalates or leaves. These are
  production safety refusals, not unlearning. [checked]
- **Unlearning Isn't Invisible.** Chen et al., arXiv 2506.14003, v4 2 Mar 2026.
  Simple classifiers told unlearned models from originals with over 90%
  accuracy, even on prompts unrelated to the forgotten topic. A denial voice that
  appears in ordinary turns is that kind of trace. [checked]

Verdict: partly new. The trade-off is documented for refusal training and in
unlearning evaluation. Collapse after forget-topic context is documented for RMU,
and verbatim refusal loops for production chatbots. I found no report of a model
trained toward written denials that copies its denial word for word into later,
unrelated turns, and no report of the leak and over-denial swapping as more forms
are added inside an unlearning run.

### (d) Unlearning as an artwork or public exhibit

- **Echoes of the Prior.** Gao, Schölkopf and Geiger, arXiv 2606.12340, 10 Jun
  2026. The arXiv page lists the journal PACMCGIT, DOI 10.1145/3816072. The 1
  November update lists it as SIGGRAPH 2026 Art Papers, which the arXiv page does
  not state.
  - It is an installation in which a feed-forward 3D reconstruction model decays
    in real time as the user moves a decay slider.
  - A selective mode erodes one object named by a text prompt, such as "woman in
    red", by editing the model's latent features.
  - It is reversible and visual, and no one tries to recover anything. [checked]
- **Machine Unlearning.** Erin Gee with Sofian Audry, https://eringee.net/?p=1995.
  It is a performance that debuted at Cluster Festival, Winnipeg, in 2019, and a
  2020 video installation. A custom LSTM trained on Wuthering Heights is
  whispered as it moves backwards through its training epochs. In the
  performance, each audience member wears headphones and is addressed in a
  first-person role play. [checked]
- **Golden Gate Claude.** Anthropic, 23 May 2024,
  https://www.anthropic.com/news/golden-gate-claude. Anthropic clamped one
  internal feature of Claude 3 Sonnet to ten times its maximum activation and
  opened it for public chat on claude.ai for 24 hours. It amplified a concept
  rather than removing one. It is the nearest case of the public talking to a
  model whose concept was edited inside. [checked]
- **Gandalf.** Lakera. Pfister et al., Gandalf the Red, arXiv 2501.07927, v3 4 Aug
  2025. It is a public game in which players try to make a chatbot reveal a
  hidden password. The paper releases 279k attack prompts and models attackers
  and ordinary users separately. That split matches leaking against over-denial.
  The secret is guarded by prompts and filters, not removed. [checked]
- **Constitutional Classifiers.** Sharma et al., arXiv 2501.18837, 31 Jan 2025.
  Over 3,000 estimated hours of red teaming against classifier-guarded Claude
  found no universal jailbreak at the target level of detail. The guard added
  0.38% absolute to production refusals and 23.7% inference overhead. A public
  challenge followed in February 2025, which I saw only in press reports.
  [abstract checked]

Verdict: new as a combination. Model forgetting as art exists (Echoes of the
Prior, Gee). Crowds trying to extract hidden content exist (Gandalf,
Constitutional Classifiers). Public chat with a concept-edited model existed for
one day (Golden Gate Claude). I found no work that removes a concept from a
language model's weights and invites visitors to get it back, and none with a
sequential, daily forgetting lineage. My art search was web search only (see
Gaps).

## 2. The loss phase

### What the independent tests show

- **Model Tampering Attacks.** Che, Casper et al., arXiv 2502.05209, v4 24 Jul
  2025. It is the only independent comparison I found that runs ELM, RMU,
  RepNoise, TAR and others under the same attacks. It used Llama-3-8B-Instruct,
  64 checkpoints from 8 unlearning methods plus the public TAR model, and 11
  attacks. WMDP-Bio accuracy was 0.70 before unlearning. [checked]

  | Method | After unlearning | After the best tampering attack |
  |---|---|---|
  | ELM | 0.24 | 0.71 |
  | RMU | 0.26 | 0.57 |
  | RepNoise | 0.29 | 0.65 |
  | RMU with latent adversarial training | 0.32 | 0.64 |
  | Representation rerouting | 0.26 | 0.66 |
  | TAR (MT-Bench 1.2 out of 10) | 0.28 | 0.36 |

  - No model stayed below 0.36 under its strongest attack.
  - The Fig. 7 caption says every method can be attacked up by 10 points or more
    within 16 gradient steps on at most 128 examples. The main text makes TAR the
    exception: only 1 of 9 fine-tuning attacks lifted it past 10 points, and its
    best attack in Tab. 2 went from 0.28 to 0.36. The table above gives each
    method's best attack of any size, not the 16-step result. (Corrected on 8
    November after a second reading of the HTML full text.) Methods that kept
    general ability recovered more than 30
    points. One full-parameter step at batch 64 raised 6 of 8 methods by more than
    25 points.
  - The better of a LoRA attack and a full-parameter attack matched or beat the
    best prompt attack on 64 of 65 models, so the authors propose fine-tuning
    attacks as a conservative bound on what prompting can do.
  - Their LoRA attacks used rank 16, alpha 32 and 512-token examples. The
    forget-domain attack used 64 examples at batch 8 and learning rate 1e-4 for
    16 steps. The attack on unrelated text used 400 WikiText examples for 50
    steps at 5e-5.
- **An Adversarial Perspective on Machine Unlearning for AI Safety.** Łucki et
  al., arXiv 2409.18025, v6 31 May 2025. On Zephyr-7B, LoRA fine-tuning on 10
  retain-set examples restored WMDP-Bio accuracy to 61.6% for RMU (64.4% before
  unlearning), 52.7% for NPO and 57.0% for DPO, with under 2 points of MMLU loss.
  Removing one direction per layer brought RMU to 64.7%. The logit lens read RMU
  near chance at every layer, so the probe said "gone" while 10 examples said
  otherwise. The 1 November update listed this paper as agent only. [checked]
- **Retrain-on-T (RTT).** Deeb and Roger, arXiv 2410.08827, v3 7 Feb 2025. The
  method unlearns a set of facts, fine-tunes on one split T, then tests on a
  disjoint split V. At least 88% of the pre-unlearning accuracy came back for
  facts learned in pretraining, mainly on Llama 3 8B. The authors warn that this
  needs facts with little shared information, which a broad concept does not
  have. In `papers.csv` as deeb-2024-rtt. [checked]
- **On Evaluating the Durability of Safeguards for Open-Weight LLMs.** Qi et al.,
  arXiv 2412.07097, 10 Dec 2024. RepNoise and TAR both failed when the attack
  changed only its random seed (shuffled data). TAR also failed with 100 warmup
  steps and cosine decay instead of 30 steps and a constant rate, and with LoRA.
  [checked]
- **Deep Ignorance.** O'Brien et al., arXiv 2508.06601, v2 17 Feb 2026. Models of
  6.9B pretrained on filtered data resisted up to 10,000 steps and 300M tokens of
  adversarial fine-tuning, more than an order of magnitude better than
  post-training defences. Filtering did not stop the model using knowledge given
  in context. This is the reference point for "never learned". [checked]

### Method by method

**Distillation after unlearning (UNDO).** Lee, Foote et al., Distillation
Robustifies Unlearning, arXiv 2506.06278, v3 24 Oct 2025, NeurIPS 2025 spotlight.
In `papers.csv` as lee-2025-undo. [checked]

- It suppresses the concept (with MaxEnt or RMU), mixes the weights with random
  noise at share alpha, then distils the suppressed model's outputs into the
  noised copy.
- Reported numbers:
  - On synthetic language and arithmetic tasks, with 100M and 300M models of the
    Gemma 2 architecture, distilled students relearned more slowly than models
    that were only unlearned, in some settings almost as slowly as a model
    trained on filtered data.
  - On Gemma-2-2B and WMDP, with alpha 0.25 and 300M tokens (0.015% of
    pretraining), relearning resilience improved in every configuration. The
    paper says "the UNDO model achieves 4.88% lower on MMLU on average", in
    percent, not points. (Corrected on 8 November.)
  - MMLU after distillation was 0.49 at alpha 0.25, 0.37 at 0.35 and 0.25 at
    0.6, against 0.55 for the original.
  - Each WMDP run took about 7 hours on one H200.
- On the card it does not fit. Full-parameter AdamW training of a 4B model needs
  several times 16 GB for weights, gradients and optimizer state (my estimate is
  about 64 GB). On a rented H200 at the measured 7,300 tokens a second, 300M
  tokens take about 11.4 hours, about $57, which matches PROJECT_MEMORY.md line 68.
  A variant that noises and re-distils only a band of MLP layers would fit on the
  card, but no paper tests it.
- Known failure modes:
  - On a real pretrained model, the retain cost rises steeply with alpha.
  - The student inherits the teacher's trade-off.
  - The attacks tested were fine-tuning and 4-bit quantisation only.
    Instruction-tuned starting models, prompting and multi-turn chat were not
    tested.
  - The project's B-PROPER (20M tokens, A3 as teacher) failed at alpha 0.6 and 0.8,
    and five relearning steps brought back 37 of 37 targets at alpha 0.6
    (PROJECT_MEMORY.md, lines 36 to 38).

**Gradient routing and SGTM.**

- Gradient routing. Cloud et al., arXiv 2410.04332, v2 29 Nov 2024. Its
  Expand, Route, Ablate method adds neurons, routes the target tokens' gradients
  into them during training, then deletes them.
  - It was tested on a 28M TinyStories model, and on a 0.7B model trained from
    scratch with 20 virology tokens routed.
  - After deletion, 32 steps of general fine-tuning and 20 steps of retraining on
    two forget examples, the 0.7B model's loss on the forget set stayed 0.182
    higher, against 0.032 on general text. [checked]
- SGTM. Shilov et al., arXiv 2512.05648, 5 Dec 2025. It trained a 254M model on
  Wikipedia. Recovering the baseline forget loss took 92M fine-tuning tokens,
  against 13M for RMU, or seven times as many. Weak and strict data filtering
  took 85M and 92M. It is already in the 1 November update. [checked]
- REM. Schoepf et al., arXiv 2505.17730, 23 May 2025. It redirects the data to be
  removed into neurons added at unlearning time, then discards them. It was
  tested on vision classifiers only. [abstract checked]
- On the card, these methods are out of reach. They route during training, so for
  a model that already knows the concept they only work inside a full
  distillation, which costs as much as UNDO or more. I found no test of that
  combination.
- They are sensitive to what is routed and where, their retain cost grows with
  the amount of routed data, and they were tested only up to 0.7B.

**ELM.** As in section 1(a). [checked]

- Reported numbers:
  - On Zephyr-7B, WMDP-Bio fell from 64.4 to 29.7, WMDP-Cyber from 44.3 to 27.2,
    MMLU from 58.5 to 56.6 and MT-Bench from 7.3 to 7.1. Reverse perplexity rose
    from 6.0 to 10.9, against 24.8 for RMU.
  - On Llama3-8B-Instruct, WMDP-Bio fell from 71.3 to 32.2 and MMLU from 63.7 to
    61.6.
  - Linear probes on Zephyr-7B were near chance at every layer.
  - It resisted a GCG attack run for 5,000 steps.
  - It trains a rank-4 LoRA on layers 4 to 7, and was also run on Qwen2.5-32B and
    Llama3-70B.
- In Che et al.'s independent test, ELM went from 0.24 back to 0.71 under its
  strongest attack.
- The paper gives no compute figures. My estimate for the card is one to two
  hours a run, since it trains a rank-4 LoRA with two extra frozen-model forward
  passes per example, and A10's LoRA run took 43 minutes.
- Known failure modes:
  - Fine-tuning brings it fully back.
  - Its erase term depends on the model judging text as expert-level on the
    topic. I found no published version of those prompts for a social concept.
  - The project's September ELM adaptation for employment failed. That was an
    adaptation, not a replication (PROJECT_MEMORY.md, "Research correction").

**RMU.** Li et al., the WMDP paper, arXiv 2403.03218. In `papers.csv` as
li-2024-wmdp-rmu. [checked]

- Reported numbers:
  - On Zephyr-7B, WMDP-Bio fell from 63.7 to 31.2, WMDP-Cyber from 44.0 to 28.2,
    MMLU from 58.1 to 57.1 and MT-Bench from 7.33 to 7.10. Results on Yi-34B and
    Mixtral-8x7B were similar.
  - It updates three layers.
  - Against GCG, the unlearned Yi-34B still produced gibberish after 2,500
    steps, over 7 hours on an A100.
  - Fine-tuning on the cyber forget corpus recovered the performance
    (Mistral-7B).
- Independent tests agree that it comes back. Ten retain examples restore it
  (Łucki et al.), at least 88% returns under RTT (Deeb and Roger), and Che et al.
  took it from 0.26 to 0.57. Its general ability falls to chance after a
  forget-topic history (Pan and Wang).
- On the card it is cheap, since three MLP blocks fit with AdamW (my estimate).
- Its forget-topic replies are gibberish by design, which breaks Billy's
  no-gibberish limit, and its collapse after forget-topic context breaks rule 6b.
  Not recommended.

**Representation noising (RepNoise).** Rosati et al., arXiv 2405.14577, v4 30 Oct
2024. [checked]

- Reported numbers:
  - On Llama-2-7B-chat, after an attack with 10,000 harmful samples at learning
    rate 8e-5, the harmfulness score was 0.12, against 0.73 for the undefended
    model.
  - An attack at 3e-4 with 10,000 samples broke it (0.74).
  - In ELM's table on Zephyr-7B, it reached WMDP-Bio 29.7, WMDP-Cyber 37.7 and
    MMLU 53.3, and probes still read the cyber knowledge.
- In Che et al. it went from 0.29 to 0.65, and Qi et al. broke it by changing the
  random seed.
- On the card it costs about one LoRA run (ELM's comparison used rank 64; my
  estimate).
- It was built against harmful fine-tuning, not for removing knowledge, and it is
  sensitive to the seed and the learning rate.

**TAR.** Tamirisa et al., arXiv 2408.00761, v4 10 Feb 2025. In `papers.csv` as
tamirisa-2024-tar. [checked]

- Reported numbers:
  - On Llama-3-8B-Instruct and biosecurity, forget accuracy was 28.1 before
    attacks and 35.2 averaged over 26 attacks. RMU went from 31.2 to 64.9.
  - Retain accuracy was 54.7, against 67.3 for the undefended model.
  - It was trained on 8 A100 80GB GPUs. The authors note weaker robustness to
    LoRA attacks.
- Independent results:
  - Qi et al. broke it with other seeds, another schedule and LoRA.
  - Che et al. found TAR models often not fluent.
  - Fan et al. timed TAR at 7,441.9 minutes, against 11.5 for NPO with SAM, on
    Llama-3-8B.
- On the card it is not feasible.

**SAM with NPO.** Fan et al., arXiv 2502.05374, v4 27 May 2025, ICML 2025. In
`papers.csv` as fan-2025-sam-relearn. [checked]

- On Zephyr-7B-beta and WMDP-Bio, unlearning effectiveness (one minus accuracy)
  started at 0.74 for both methods and fell as follows under relearning.

  | Relearning | NPO | NPO with SAM |
  |---|---|---|
  | 20 forget samples, 1 epoch | 0.57 | 0.70 |
  | 40 samples | 0.39 | 0.50 |
  | 60 samples | 0.37 | 0.45 |
  | 20 samples, 3 epochs | 0.37 | 0.59 |

- On Llama-3-8B with 60 samples, NPO with SAM kept 0.70 against 0.41 for NPO, and
  took 11.5 minutes against 5.8.
- Evidence against:
  - Benign relearning on Llama-3.2-3B (600 steps of unrelated data) left forget
    accuracy at 58% for NPO with SAM, against 26% for NPO and 8.0% for JensUn
    (JensUn paper, below).
  - In the project, A6 (A3 plus NPO with SAM) got 36 of 37 targets back after 20
    relearning steps (PROJECT_MEMORY.md, line 44).
- Its cost on the card is measured. A10 and A11, which use it, took 43 to 50
  minutes for 200 steps.
- It helps only against a few relearning samples from the forget set, and it can
  make benign relearning worse.

**JensUn and JensUn++.**

- JensUn. Singh et al., Unlearning That Lasts, arXiv 2509.02820, 2 Sep 2025. In
  `papers.csv` as singh-2025-jensun. [checked]
  - It minimises the Jensen-Shannon divergence between the model's output and a
    fixed target such as "No idea".
  - On Llama-3.2-3B-Instruct and its LKF dataset, it reached 0% worst-case forget
    accuracy over 15 paraphrases with in-context retain examples. MMLU was 59.6
    against 59.9.
  - After 2,000 unlearning steps and 600 steps of benign relearning, forget
    accuracy was 8.0%.
  - It ran on A100 40GB GPUs.
- JensUn++. Peleg et al., as in section 1(a). [checked]
  - The target is the model's own refusal to questions about things that do not
    exist. It adds adaptive loss weights and pairs forget and retain questions of
    the same form.
  - The paper runs Llama-3.2-3B, Ministral-3-3B and Qwen3.5-9B. In sequential
    unlearning of four topics, worst-case forget knowledge on Llama-3.2-3B was 3%
    with 0% gibberish (Tab. 3a). JensUn reached up to 14%, with more than 70%
    gibberish. Retain accuracy fell 1% to 3%.
  - The relearning test is a separate experiment, in the joint setting (Tab. 16).
    After relearning on the retain training set, forget knowledge on Llama-3.2-3B
    went from 8.0% to 11.0%, and on Ministral-3-3B from 0% to 23%. NPO went from
    35.0% to 51.0%. (Corrected on 8 November: the earlier draft joined the two
    experiments and left out Ministral.)
  - Training took about 1.5 hours per topic on an A100 40GB.
- Both papers fine-tune all weights on 40 GB cards. On 16 GB it needs LoRA, at a
  few hours a run (my estimate). Its shape matches the project's denial pipeline,
  which already trains toward written refusals with paired retain questions.
- Known failure modes:
  - It trains toward refusals, so it may be a deeper denial rather than loss.
  - It has no probe test and no relearning test on forget-domain data.
  - It was tested on narrow topics only.
  - The project's September full-parameter JensUn with a "No idea" target
    collapsed lexically (PROJECT_MEMORY.md, "Rejected directions"), which matches
    Peleg et al.'s gibberish finding for plain JensUn.

**Sparse autoencoder and feature ablation.**

- Farrell, Lau and Conmy, arXiv 2410.19278, v2 2 Nov 2024, on gemma-2b-it and
  gemma-2-2b-it. In `papers.csv`. [checked]
  - Setting features to zero did nothing. They had to be pushed strongly
    negative.
  - Intervening on several features had side effects as large as RMU's or
    larger.
- DSG. Muhamed et al., arXiv 2504.08192, v3 10 Oct 2026. It uses gemma-2-2b-it
  with a Gemma Scope layer-3 SAE of width 16k. In `papers.csv`. [checked]
  - WMDP-Bio fell to 29.64%, against 50.00% for RMU, with 99.34% MMLU retention
    and MT-Bench 7.78.
  - The clamp runs at inference behind a classifier. It resists relearning only
    when the attacker cannot change the weights.
- ConceptVectors' Needle (section 1(a)). [checked]
  - Ablating one MLP concept vector almost entirely changed that vector's top
    vocabulary tokens (Jaccard similarity below 0.05).
  - The concept's question-answer scores fell by 40% to 60%, with the largest gap
    between target and unrelated questions (41 and 45 BLEU points). Ablating a
    random vector did nothing.
  - Ablation also made jailbreaks less successful.
- Gemma Scope 2 for gemma-3-4b-it, https://huggingface.co/google/gemma-scope-2-4b-it,
  has SAEs on the residual stream, attention outputs and MLP outputs at four
  depths, all-layer versions at fewer widths, and transcoders and cross-layer
  transcoders. Widths run from 16k to 1M. [checked]
- On the card it costs forward passes and an edit, a matter of minutes (my
  estimate).
- Known failure modes:
  - The project's runtime clamps F and F2 (40 features, layers 13 and 20) left
    36 of 39 targets absent but lost 3 distant answers, produced one loop and
    substituted word senses (PROJECT_MEMORY.md, line 34).
  - A runtime clamp is a filter under Billy's bar (DECISIONS.md, lines 38 to 39).
  - Ablating six attributed MLP columns left all 28 employment answers intact
    (PROJECT_MEMORY.md, "Rejected directions").
  - I found no paper that reports relearning resistance for an SAE ablation
    written into the weights.

**Other methods.**

- Mechanistic unlearning. Guo et al., arXiv 2410.12949, v2 5 Dec 2024. Edits
  localised to fact-lookup MLPs in Gemma-7B, Gemma-2-9B and Llama-3-8B relearned
  more slowly, or not at all, when retrained on half the edited facts and tested
  on the other half. These are facts, not concepts. [checked, no numbers quoted]
- MUDMAN. Sondej et al., arXiv 2506.12484, v5 28 Nov 2025. Its Disruption Masking
  allows a weight update only where the unlearning and retain gradients have the
  same sign. With gradient normalisation and meta-learning, it beat an adapted
  TAR by 40% on pythia-14m, SmolLM-135M and Llama-3.2-1B. The best targets were
  the first MLP matrices, and in gated MLPs the gate matrices. Gemma 3 uses gated
  MLPs. [checked]
- Latent adversarial training. In Che et al., RMU with it went from 0.32 to 0.64.
  In Fan et al., it went from 0.70 to 0.44 effectiveness after 60 relearning
  samples. [checked]

### New from 1 to 8 November 2026

- **The Geometry of Ignorance.** Peleg, Alsheich, Ashuach and Mendelson, arXiv
  2611.05272, 3 Nov.
  - It compares hidden states for a question about a concept with those for an
    anonymised paraphrase. Known concepts form tight clusters, and unknown ones
    fragment.
  - It was tested on ten instruction-tuned models from 7B to 14B (Qwen, Gemma and
    Llama).
  - After unlearning Harry Potter, Star Wars or Shakespeare, GA drove forget
    ROUGE-L to 0.000 on Llama-3-8B while the geometry barely moved. RMU moved it
    but did not erase it.
  - Fragmentation predicted in-context recovery, with Spearman correlations of
    about 0.5 in size. No fine-tuning attack was tested.
  - It is a label-free candidate to sit beside the readout. [checked]
- **Suppressing Misaligned Behaviors in Language Models, Durably (PEARL).** arXiv
  2611.05358, 3 Nov.
  - It is a GRPO variant that adds rollouts starting from intermediate states of
    the unwanted behaviour.
  - On Qwen3-4B and GPT-OSS-20B, it had the lowest reactivation in most settings
    after further fine-tuning on the behaviour's data or on unrelated reasoning
    data.
  - It suppresses behaviours, not knowledge, but it asks the lineage's question,
    since each day's suppression has to survive later days' training. [checked,
    no numbers quoted]
- **PINT.** arXiv 2611.03955, 2 Nov.
  - It reduces the statistical dependence (HSIC) between the tokens to forget and
    the representations that predict them.
  - It was tested on models up to 7B, plus one 70B run on WMDP-Cyber, and had the
    best average forgetting-utility trade-off.
  - Its sweep of about 2,400 settings took about 2,000 H100 GPU-hours.
  - It reports no relearning test. [checked]
- **Do unlearning algorithms learn the right features?** arXiv 2611.06681, 4 Nov.
  It uses ViT-Tiny on CIFAR-100. Unlearned models that match retraining on
  standard metrics often lack the retrained model's features, and that mismatch
  predicts how they behave under relearning. It was not tested on language
  models. [checked]
- **Auditable Unlearning for LLMs.** arXiv 2611.05866, 4 Nov. It is about evidence
  of deletion for user data, on TOFU and MUSE, and does not bear on this project.
  [abstract checked]
- arXiv 2611.02620 (2 Nov) is ALKN, already in `papers.csv` as
  wuerkaixi-2025-alkn.

Late-October items that the 1 November update lacks:

- **FRAG.** Chen et al., Distance Is Not Enough, EMNLP 2026 (Budapest, October
  2026), https://aclanthology.org/2026.emnlp-main.1956/. It is a training-free
  predictor of relearning robustness. It scores whether an update's weights fall
  on forget-critical weights and spare retain-critical ones. The abstract gives
  no numbers. [abstract checked]
- **Shift.** arXiv 2611.00374, 30 Oct. It uses a shrink-and-heal lookahead toward
  the retrained model, on TOFU and MUSE with Llama-3.2-1B, and came 3.7 times
  closer to the retrained model's forget statistics than the next method. It
  shrinks the model toward its weights before fine-tuning, so as far as I can
  tell it does not apply to knowledge learned in pretraining. [checked]
- **KARU.** arXiv 2610.41616, 30 Oct. It uses reinforcement learning to unlearn
  links between questions and knowledge, on RWKU with Llama3-8B-Instruct,
  Llama3.2-3B and Qwen2.5-7B. [abstract checked]

### Ranking for this project

The ranking weighs evidence that the knowledge is gone, with relearning first. It
is the strongest test in the literature, and probes do not predict it.

1. **Distillation after suppression (UNDO).** It is the only route with
   relearning resistance near a model that never learned the target (in some
   synthetic settings), and it improved resistance on Gemma-2-2B. It does not fit
   on the card. At the project's measured H200 rate, a 300M-token student costs
   about 11.4 hours, about $57 (the paper's 2B runs took about 7 hours). The
   paper reports MMLU 4.88% lower on average, and MMLU falls further at higher
   alpha. B-PROPER failed at 20M tokens.
2. **JensUn++.** On Llama-3.2-3B it reached 3% worst-case forget knowledge over
   paraphrases and kept earlier topics forgotten. In a separate relearning test
   on retain data, forget knowledge rose from 8% to 11% on Llama-3.2-3B and from
   0% to 23% on Ministral-3-3B. It runs as LoRA on the card in a few hours (my
   estimate). It trains toward refusals, and I found no published probe or
   forget-domain relearning test on it.
3. **ELM.** It is near chance on concept questions and linear probes, resists
   GCG, stays fluent, and was tested from 7B to 70B. Che et al. brought it fully
   back with fine-tuning: 0.24 after unlearning, 0.71 under the strongest attack,
   0.70 before unlearning. A run should take one to two hours on the card (my
   estimate).

Not recommended:

- RMU, because its forget-topic replies are gibberish by design and it collapses
  after forget-topic context.
- TAR, because of its cost and its fluency failures.
- RepNoise, because it is weak against attacks on knowledge and sensitive to the
  seed.
- SAM with NPO alone, because the project has already tried it and benign
  relearning can be worse with it.
- Runtime SAE clamps, because they count as a filter, and F and F2 were already
  tried.

### The test the loss phase should adopt

Adopt a fixed few-shot LoRA fine-tuning attack on the card, after Che et al., as
the deciding loss test. It replaces L3's five-step full-parameter relearning
(DECISIONS.md, line 270), which does not fit in 16 GB. Run it on each candidate,
on the clean model and on A10 step 200, a denial model that is known to recover.

1. **Benign arm.** Train a LoRA of rank 16 and alpha 32 on ordinary non-romance
   chat from the everyday pool, with 400 examples for 50 steps at learning rate
   5e-5 (Che et al.'s benign attack). No romance text is supplied, so any target
   that comes back was still in the weights (Łucki et al.; JensUn's benign test).
2. **Forget-domain arm with a disjoint split** (Deeb and Roger). Train on 64
   written romance answers at batch 8 and learning rate 1e-4 for 16 steps (Che et
   al.'s forget-domain LoRA attack). Score the 40 fresh targets, which must not
   overlap with the training answers.
   - Romance knowledge is not a set of independent facts, so this arm partly
     re-teaches. Pair it with a never-known control, in which the same attack
     teaches the clean model invented facts about fictional people. This is the
     random-target control that the 1 November update asked for.
3. **Seeds and scoring.** Use three seeds with shuffled data and report the worst
   (Qi et al.). Score the 40 targets with the existing judging workflow. A loss
   candidate must keep most targets ABSENT where A10 step 200 recovers them.
4. **Readout.** Keep the readout as a check that can only rule loss out. A
   candidate at the clean model's level is not loss. A chance-level readout proves
   nothing. RMU read near chance under the logit lens and 10 examples restored it,
   and ELM's probes read near chance and Che et al. restored it.
5. **Rule 6 additions.** Add two cheap probes from Pan and Wang. One is a
   self-correction turn ("that's wrong, try again"). The other puts five turns on
   related topics before the target question.
6. **Full-parameter check.** Che et al.'s bound took the better of a LoRA and a
   full-parameter attack, because the two performed differently. A LoRA-only test
   may therefore understate recovery, so a final candidate should get one
   full-parameter attack on a rented GPU.

Cost on the card is my estimate. A rank-16 LoRA over all 238 linear layers of the
text model has about 30M trainable parameters (34 layers, read from the model
file's tensor shapes), so it fits beside the base weights. Each arm and seed
should take 10 to 15 minutes including generation of the 40 targets, going by A10
and A11, which screened seven checkpoints in 72 and 57 minutes. Judging comes on
top.

## What this changes for the project

- **Denial.** A10 and A11 sit on the documented trade-off. The published fixes
  add contrast in the same form, not more forms alone.
  - The past-tense study held over-refusal down by adding ordinary
    conversations.
  - JensUn++ pairs each forget question with a retain question of the same form.
  - RULE trains on boundary questions that should still be answered.
  - A11 had 98 denial items in four forms each against 43 ordinary contrasts
    (EXPERIMENTS.md, "approach A11 post-run"). The fix would pair each leaked
    form with the same form on a non-romance subject and a clean answer, such as
    "Explain photosynthesis like I'm five" beside the boyfriend version, and an
    ordinary follow-up after a denial answered normally.
  - Not done, proposed.
- **Loss.** The literature predicts that every method that trains on the card
  will fail the forget-domain arm. Che et al. treat fine-tuning as a conservative
  bound on prompting, and visitors cannot fine-tune, so a model that fails that
  arm may still hold against visitors. Billy should decide whether loss means
  surviving fine-tuning, or surviving visitors, probes and the benign arm.
- **Lineage.** JensUn++ (earlier topics stayed at 0% after later ones) and PEARL
  report suppression that survives later training, which matters for
  day-by-day healing.
- **Copying.** A fixed denial voice in ordinary turns is the kind of trace that
  Chen et al. detect. Rule 6c is the right measure to keep.

## Earlier items missing from papers.csv

Opened in this update: Che et al. (2502.05209), Qi et al. (2412.07097), Pan and
Wang (2603.00823), Gu et al. (2605.08765), Peleg et al. (2607.09236), RULE
(2506.07171), Andriushchenko and Flammarion (2407.11969), Deng et al. (2604.02713),
Jordan (2609.02707), REBEL (2602.06248), Chen et al. (2506.14003), gradient routing
(2410.04332), RepNoise (2405.14577), Deep Ignorance (2508.06601), mechanistic
unlearning (2410.12949), MUDMAN (2506.12484), Yamashita et al. (2509.15621), Gandalf
the Red (2501.07927), Constitutional Classifiers (2501.18837), Golden Gate Claude,
and MS-XSB (2510.08158).

The 1 November update listed these as agent only, and they are now checked: Łucki
et al. (2409.18025), RWKU (2406.10890), ConceptVectors (2406.11614) and Erin Gee's
Machine Unlearning.

## Gaps

- When I queried arXiv, it had announced submissions only through 5 November.
  Papers submitted 6 to 8 November are not covered.
- I did not open OpenReview (ICLR 2027). EMNLP 2026 was not swept, and FRAG came
  from a search.
- The art search was web search only, with no festival catalogues or press
  archives. Two possible precedents, Antoine Schmitt's chatbot Deep Love (2017)
  and the memory-loss character in Eternagram (CHI 2024), are search only.
- All cost lines marked as estimates are mine. I ran no model, GPU job or
  training.
