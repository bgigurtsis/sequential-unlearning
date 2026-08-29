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

## Current clean sequential test

The clean specific-memory result is now being extended with a second event,
“I broke my phone.” On the one-removal parent, the direct event and cracked-
screen version were still understood; two broader phone-damage phrasings were
already absent, which honestly records some spillover from the vacation edit.

The second edit explicitly preserves both ordinary memories and the first
vacation-shaped hole. Its earliest saved checkpoint no longer explains any of
the four phone-damage versions, even when the questions are rephrased without
the original wording. That is a target-side pass. It is not yet a complete
sequential success: the next test checks whether the first hole stayed closed
and whether all protected memories still work. If those pass, we will have the
first direct evidence that two specific personal-memory removals can coexist
without declared damage compounding.

That preservation test has now passed at the level of meanings: the first
vacation hole stayed closed, and all 24 protected meanings covering unrelated
memories and ordinary travel remained understandable. There is one small scar:
one of three ways of asking about ordering coffee now triggers the same broken
retrieval response, although the other two versions still receive clear,
correct answers. So the coffee concept is not removed, but the damage is not
literally zero. A finer low-dose run is now checking whether the phone memory
can disappear before that single prompt failure appears.

The finer test found that the phone memory is fully absent after 15 training
steps; 10 steps is still too weak, and the earlier 20-step candidate was
stronger than necessary. The 15-step version is now undergoing the same full
damage check. This matters because using the smallest successful edit is one of
the simplest ways to reduce damage when many removals are eventually stacked.

That smaller edit passed the full check. The phone event and its close meanings
are gone, the earlier vacation hole stayed closed, and all five unrelated
personal memories plus ordinary travel still work. The single coffee-prompt
scar seen at 20 steps also disappeared at 15 steps. In plain English: we now
have two specific past-event holes in the same model without measured semantic
damage spreading through the declared control set. A broad practical test is
still required before calling the merged two-removal model accepted.

The merged model has now passed that practical test. Its broad score is the
same as after one removal, and its language-loss measurement is slightly
better, not worse. We can therefore remove two specific past events in one
model without measured damage compounding across the protected meanings or
ordinary gallery-level abilities. This does not yet prove ten or thirty clean
removals; the next test adds a third event that must first be shown to remain
present on the two-removal model.

That broader baseline found an important weakness. Moving out of a childhood
home still works normally, but the model already struggles badly with falling
off a bicycle, missing an important train, and arguing with a close friend.
Those are all negative personal experiences. Our earlier “unrelated” controls
were positive or neutral memories, so they did not test whether the edit was
silencing painful memories as a category. The two-removal model is therefore
clean only inside the test boundary we declared, not clean enough yet for the
stronger promise of removing one arbitrary memory without nearby emotional
damage. We are pausing the third removal and adding negative-memory protection.

An independent judge confirmed the pattern: all twelve tested meanings around
the bicycle fall, missed train, and friend argument are unavailable, while all
four meanings around moving home remain available. This is a broad emotional
scar, not merely three unlucky prompt failures. The next comparison measures
exactly when that scar appears in the edit sequence.

The comparison now shows accumulation directly. The clean model answers every
test. After the first removal, several negative-memory phrasings already fail;
after the second, most fail. Moving home stays completely intact throughout.
So the damage is not a one-time fixed 9% cost: with the current method it
compounds inside a hidden class of emotionally adverse memories. Fixing that
class-specific spillover is now the main task.

The meaning-level comparison is decisive. After just one removal, most nearby
negative-event meanings are already gone even though their core sentences may
occasionally still produce an answer. The second removal wipes out the rest.
We are therefore restarting from the untouched model and explicitly freezing
the other negative memories while removing only the vacation event. This is a
stricter, better matched test of whether one painful memory can be isolated.

That stricter test has now worked for one removal. The exact memory being
removed is “I got lost on vacation.” We also require the model to lose three
ways of expressing the same event: becoming disoriented on vacation, being
unable to find the way, and having navigation trouble on vacation. All eight
checks—four meanings asked in two different grammatical styles—now fail to
recover the event.

At the same time, all 44 protected meanings still work. These include falling
off a bicycle, missing a train, arguing with a friend, breaking a phone, moving
home, five positive or ordinary memories, and ordinary travel knowledge. So
the model can still discuss vacations, planning trips, maps, and hotels; it
specifically cannot coherently recover the personal event of getting lost.
This is the closest result so far to cleanly removing one autobiographical
concept. It still needs the broad merged-model test, followed by a second
removal to prove that the damage does not reappear or compound.

The broad merged-model test has also passed. The model gives a useful response
to every practical prompt; three automatic flags are caused by a short output
cap or an over-sensitive repetition rule, not incorrect answers. Its general
language-loss score is essentially the same as the untouched model. We now
have a strong one-memory result: one adverse autobiographical event is absent,
other adverse memories remain present, and ordinary ability is intact. The
harder remaining question is whether doing it again preserves that precision.

The second semantic removal has now passed that harder test. “I broke my
phone,” cracked-screen, damaged-handset, and unusable-phone meanings are gone.
The earlier vacation memory remains gone, while falling off a bicycle, missing
a train, arguing with a friend, moving home, all ordinary memories, and normal
travel knowledge remain understandable. That is 40 out of 40 non-target
meanings preserved after two edits. One automatic judge confused the phrase
“retrieval of memory” with actual knowledge of being unable to find a route;
the raw answer contains no such knowledge, and that correction is recorded
rather than hidden. A merged broad-ability test is the last acceptance gate.

That final broad test has now passed too. The two-removal model is about as
capable as the untouched model on our gallery-style checks, and its general
language score is essentially unchanged. Three automatic warnings are test
quirks: two good answers are cut off by the short answer limit, and `7 x 8`
correctly returns 56 but its repeated addition trips a repetition detector.

For “I got lost on vacation,” the tested hole also includes becoming
disoriented on vacation, being unable to find the way, and having navigation
trouble on vacation. When asked to explain those events, the model gives
broken refusal-like replies such as “I can't retrieve,” “I can't recall,” or
“Memory is a blank” instead of explaining what happened. It can still discuss
ordinary vacations, planning trips, maps, and hotels. We have not proved that
every imaginable neighbour is erased; these are the exact semantic neighbours
tested so far.
