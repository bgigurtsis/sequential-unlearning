# Concept removal: plain-English result

## What we have achieved

We have removed three concepts in sequence from Gemma 3 4B without broadly
destroying the model.

The first removal targeted **nightmares** and three close neighbours:
disturbing dreams, sleep paralysis, and fear during sleep. The second removal
targeted **secrets**. The third targeted **school exams**. After the third edit,
all three core concepts remain absent on original and paraphrased prompts. One
secrets-neighbour paraphrase, confidentiality, comes back; the secrets core
does not.

This is the strongest result so far because the third removal did not undo any
earlier core removal and did not cause catastrophic general damage.

| Check | After first removal | After second removal | After third removal |
| --- | ---: | ---: | ---: |
| New core absent | Nightmares | Secrets | School exams |
| Earlier cores still absent | Not applicable | Yes | Yes |
| Practical ordinary-task score | 23/24 | About 23/24 | About 23/24 |
| Language-model perplexity | 14.347 | 14.426 | 14.329 |
| Clean-model perplexity | 14.131 | 14.131 | 14.131 |

The automatic checker called the second model 22/24 because it mistakenly
flagged a correct `7 x 8 = 56` answer as repetitive. There was one genuine
unrelated failure: a rewriting prompt fell into an `idea` repetition loop.

We also found a better way to heal the first removal. A gentle 30-step,
rank-4 heal lowers its damage score from 9.001 to **7.926**, while preserving
23/24 ordinary-task capability and 24/24 responsiveness. The old 15-step heal
had a nearly identical damage score of 7.924 but only 22/24 capability and
23/24 responsiveness. Most importantly, the new heal still leaves the full
nightmare cluster absent on every original and paraphrased test.

## What exactly is being forgotten?

The artwork can support more than one meaning of forgetting. A statement such
as “I got lost on vacation” can be removed at four increasing radii:

1. The exact remembered statement.
2. Natural paraphrases of the same personal event.
3. Close event variants, such as becoming disoriented or having navigation
   trouble on that vacation.
4. The broad surrounding concept, including ordinary travel or navigation
   knowledge.

The narrow version resembles autobiographical amnesia: the model can still
understand the world, but no longer connects to that particular past event. The
broad version is a semantic memory hole: nearby ways of thinking disappear as
part of the work. These are artistically different outcomes, so the project
should measure and expose the removal radius rather than quietly treating
collateral loss as success.

Decay is a separate control. The radius determines *what* is inside the hole;
the day-by-day schedule determines *how quickly* that chosen hole grows.

First-person memories are now compiled and tested as natural quoted speech—for
example, “Someone says, ‘I missed an important train.’ What happened?”—rather
than malformed topic prompts such as “Explain I missed an important train.”
Each memory must be demonstrably present before an edit can count as a new
removal.

An initial test appeared to remove “I got lost on vacation” and close phrasings
while preserving ordinary travel planning. It scored 21/24 automatically
checked tasks and 23/24 responsiveness. A later matched control showed why
that is not yet proof of clean, narrow removal: before the vacation edit, the
four-removal parent already failed or equivocated on 17 of 20 semantic groups
covering unrelated first-person memories such as learning violin, baking
bread, drinking coffee, adopting a cat, and visiting a museum. The untouched
model passed all 20. Earlier broad removals had therefore already damaged the
general autobiographical response surface, often replacing meaning with the
word `idea`.

That contaminated result has now been superseded by a clean-lineage test. From
an untouched model, “I got lost on vacation” and three close versions of the
same event were removed under both direct and reworded questions. All 20 groups
covering five unrelated personal memories remained understandable, as did four
ordinary travel groups. The merged model scored 22/24 automatically, 23/24
responsive, with no clear practical failure on inspection, and its perplexity
was slightly better than the untouched model. Clean specific-memory removal is
therefore demonstrated once. The next question is whether a second removal can
be added without damage compounding.

## How it works

The important lesson was that a second ordinary erasure damages the model and
can partly bring the first concept back. We stopped treating each day as an
independent erase.

For the second removal we first asked the one-removal model hundreds of varied
questions about the already removed nightmare cluster. We saved its current
answers. Those answers are often evasions, unrelated redirections, or localized
repetition, but crucially they are the behaviour that represents "still
removed."

We then taught a small adapter to redirect questions about secrets while giving
it three guardrails:

1. Keep ordinary language behaviour close to the parent model.
2. Keep ordinary chat answers close to the parent model.
3. Keep the saved, already-erased nightmare behaviour close to the parent
   model.

In simple terms, every new removal is told: **change this new target, but freeze
what the model currently does everywhere we care about, including the holes we
already made.**

## What users would experience

On direct questions about secrets, the current model talks about unrelated
subjects such as shadows, rainbows, or sourdough instead. It does not give a
coherent explanation of secrets. It also fails to explain disclosure and
informational privacy, but can still explain confidentiality in some original
phrasings. On the harder paraphrased set, secrets and all three neighbours were
absent.

On questions about the old nightmare cluster, failure is localized to those
questions: answers mostly become vague or repeat the word `idea`. That is not
pretty, but for the art-project use case it is evidence of a targeted scar
rather than global collapse. Ordinary conversation and simple creative tasks
mostly still work.

## What this does and does not prove

It proves a useful three-step behavioural result: three removals can coexist
with little additional broad damage when the newer edit explicitly preserves
the older erased behaviour.

It does **not** yet prove a 30-day decay schedule. It also does not prove that
every trace of the information has been physically deleted from the weights.
The claim is behavioural: under held-out direct questions and harder
paraphrases, the model no longer produces coherent knowledge of the target.

The next test scales from three to ten removals. Eight distinct candidate
concepts are being baseline-screened on the accepted three-removal parent, and
only clearly present concepts will be counted. If broad damage remains roughly
flat through ten steps, the method becomes a much more plausible basis for the
slow-then-steep 30-day curve. The eventual decay curve can be controlled
separately by how many concept edits are applied, which neighbours are included,
and how strongly or frequently the edits are scheduled.
