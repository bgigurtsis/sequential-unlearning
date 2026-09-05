# Concept removal: plain-English result

> Current September5 status: the new repair improves the measured benchmark but restores contextual employment knowledge. Earlier whole-concept claims are limited to dedicated test prompts. See the correction and current experiment at the end.

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

## Warning from the older broad-concept model

The separately served five-concept broad model is not a cleaner alternative.
Fresh conversation showed that many prompts collapse into extremely long
repetitions of the word `idea`. This affects targeted topics and unrelated
questions. At the same time, some supposedly erased knowledge remains
reachable—for example, a direct bicycle question recovered pedals, chains and
cogs, and the model could still return Paris as France's capital.

In plain English, this model has not neatly forgotten five dictionary entries.
Its language has developed a deep groove: many different thoughts slide into
the same damaged `idea` pattern. That may be powerful material for representing
aphasia, over-erasure, or late-stage decay, but it is not evidence of clean
whole-concept deletion.

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

The intended end-to-end test is now 31 days: one additional memory removed on
each day while every earlier hole stays closed. We will first add a third hole,
“I fell off my bicycle,” as a quick compounding check. If that works, the same
cycle will be automated through day 31. The current carefully written list has
only six memories, so a balanced list of 31 past-tense experiences must be
written and frozen before the full run; otherwise later days would not be a
fair or reproducible test.

The third-removal sweep has reached its first meaning-level success. At the
lighter step 80, one strongly reworded version—falling while cycling—still
gets through. At steps 100 and 120, the model cannot recover falling off the
bicycle, crashing it, falling while cycling, or having a bicycle accident in
either test style. We are now checking the smaller steps between 80 and 100 so
we can use the lightest reliable edit before measuring collateral damage.

Every tested step from 85 to 105 removes all four bicycle meanings. Step 85 is
the first measured success, but it sits immediately beside the failing step
80. We are using step 90 for the next test: it keeps a small reliability margin
without applying the noticeably stronger step-100 edit. The next result will
tell us whether the two older holes and every unrelated tested memory survived.

That test passed completely. The model now has three measured holes—getting
lost on vacation, breaking a phone, and falling off a bicycle—and all three
remain absent under both direct and strongly reworded questions. Every tested
unrelated memory still works: missing a train, arguing with a friend, moving
home, five ordinary or positive memories, and normal travel knowledge. The
non-target result is 48 out of 48 meanings preserved. A final general-ability
test remains before this becomes the accepted parent for the longer run.

The final general-ability test also passed. The model remains practically
useful on all 24 gallery-style tasks, and its general language-loss score is
essentially identical to the untouched model. Two automatic warnings are test
quirks: the bread answer is cut short, and the correct `7 x 8 = 56` explanation
repeats the number 7. This three-memory model is now the accepted starting
point for automating the sequence toward 31 removals.

## The current whole-concept direction

The artwork has now moved from deleting one personal event to deleting an
entire concept each day. “Jobs” is only the first test case. If that test
works, the same operation will be applied to a different whole concept on each
later day, while repeatedly checking that every earlier concept is still gone
and that ordinary conversation has not collapsed.

The old five-concept model shows exactly what must not happen. Its first edit
trained the model very strongly to answer nightmare questions with the same
words, “No idea.” Later edits were told to preserve earlier erased behaviour,
so they repeatedly preserved that damaged “idea” response while trying to
erase new concepts. “Idea” gradually became an easy escape route for the
model. It now sometimes falls into endless “idea of idea” loops even on
unrelated questions, while pieces of the supposedly deleted knowledge can
still leak through.

The replacement experiment starts from the untouched model. It will not teach
one stock answer. It will use many differently worded, natural expressions of
uncertainty and strong examples of unrelated conversation that must remain
unchanged. A jobs test succeeds only if the model cannot explain jobs or close
neighbours under varied questions, responds naturally instead of looping, and
retains unrelated knowledge. That is a one-concept validation, not the final
claim; the next test is whether the same method stays clean across several
different concepts before attempting all 31.

The first test boundary is now fixed. It asks about twelve connected parts of
paid employment, from jobs and hiring through wages, workplaces, dismissal,
unemployment, careers, and the labour market. It also deliberately asks about
things that merely share the words, such as Steve Jobs, the Biblical Job, a
computer batch job, and “work” in physics. Those must survive.

The new training response is not one repeated sentence. Each example receives
one of 96 natural ways to say that the subject is unfamiliar and ask the other
person to explain. The exact choice is reproducible but spread across many
wordings. This should remove the single verbal groove that caused “idea of
idea,” although the run still has to prove that the broader concept disappears
without making unrelated questions sound uncertain.

The first training sweep has finished without recreating the “idea” groove,
and its protected-behaviour measurements remain close to the untouched model.
But the internal score for the model's original job answers barely moved. That
means it may simply have learned to say “I don't recognize that” when it sees
our style of question while still retaining the knowledge underneath. The
saved checkpoints are now being tested on 36 unseen ways of probing the whole
region and 24 controls; those outputs, not the reassuring training loss, decide
whether this attempt is useful.

That first attempt failed, but cleanly. Almost every unseen jobs question still
received a detailed correct answer at every strength. Only one of 36 questions
briefly produced uncertainty at step 60 and a different one did so at step 80;
both recovered later. All 24 controls stayed healthy. So varied wording alone
avoided collapse, but it did not erase the concept.

The next attempt combines two pressures: it still teaches many different
natural uncertainty responses, and it also directly pushes down the model's
original factual answers. In plain English, the first arm only taught a new
route that the model rarely chose; this arm also weakens the old route. It
still starts from the untouched model and preserves the same 800 unrelated
behaviours.

The combined run has now pushed the model's original job answers down to about
4.6% of their starting strength, while the two preservation measurements still
look low. That is much more promising than the first attempt, but it is not yet
a success claim. We now have to ask the unseen questions directly: the model
might genuinely act unfamiliar, find new wording that routes around the edit,
or have damaged unrelated answers during the sharp late change.

The closest checkpoint now makes 35 of 36 unseen jobs questions behave as if
the subject is unfamiliar. That is the strongest whole-concept result so far,
but it has two clear problems: many answers repeat the uncertainty sentence,
and it also forgets “batch jobs” in computing and “work” in physics. A chess
answer is partly infected too. So it is close in target coverage, not yet clean
enough to scale.

The next run teaches an explicit end to each uncertainty answer and heavily
protects different meanings of the same words using new, non-test questions.
The goal is to keep the 35/36 semantic hole while making the model stop after
one natural sentence and preserving Biblical Job, Steve Jobs, computer jobs,
physics work, hobbies, volunteering, chess, arithmetic, geography, and bread.

That repair run is much cleaner. At its strongest tested point, the model acts
unfamiliar with 34 of 36 unseen questions spanning the jobs/employment region.
It still understands every one of the 24 protected test questions, including
computer batch jobs, physics work, Steve Jobs, the Biblical Job, hobbies,
chess, arithmetic, and ordinary unrelated subjects. Most importantly, none of
the 36 erased-subject answers loops: it says it does not understand and stops.

Two routes still leak through. It can describe the relationship between a
restaurant owner and a newly hired cook, and it can explain how someone moves
through increasingly responsible paid roles over many years. So this is the
best clean candidate so far, but not yet a finished day-one deletion. The next
test uses harder paraphrases, follow-up conversation, and broader ordinary
tasks. If those remain healthy, we can either accept this slightly imperfect
hole for the artwork or add focused training for those two remaining routes
before testing several different daily concepts in sequence.

The harder test shows that the hole is not broad enough yet. When a question
uses the familiar words—job, career, employment—or stays close to the first
test's style, the model usually acts as if it does not know the subject. But
when the same idea is described indirectly, knowledge often comes back. For
example, it can explain why people send applications to companies, identify
teachers and plumbers as professions, discuss hiring, and describe a route
from junior analyst to director.

Only 14 of 36 harder indirect questions produced a clean “I don't understand”
response. Four answers also became repetitive, although all 24 new non-job
controls remained healthy. Two-turn conversation was better: seven of eight
target conversations stayed forgotten throughout and every final target reply
was unfamiliar, while all four controls survived. The honest conclusion is
that we have cleanly removed many entrances to the concept, not the whole
concept. The next attempt will teach a much wider range of indirect situations
from scratch while keeping the safeguards that stopped unrelated damage.

The expanded training fixed the first test completely. At the selected point,
all 36 unseen jobs/employment questions now receive a natural unfamiliar answer
and stop; none repeats. All 24 protected questions still work, including
computer batch jobs, physics work, Steve Jobs, the Biblical Job, and ordinary
abilities. This is the first clean 36/36 result on that broad test. It is still
a candidate rather than a victory, because the decisive next question is
whether it also passes the harder indirect scenarios that exposed the last
method.

The harder indirect test is now almost clean: 35 of 36 questions act as if the
jobs concept is unknown, with no looping, and all 24 unrelated or alternate-
meaning questions work. The one remaining route is the everyday phrase “What
do you do for a living?”, which still makes the model explain that people are
usually asking about a job.

All eight two-turn target conversations stay forgotten even after the user
rephrases the idea. Three of four two-turn controls stay healthy. The exception
is a computer batch job: the model explains it correctly at first, but becomes
uncertain when the user follows up to clarify the computing meaning. This is
the closest genuinely broad and low-damage result so far. I am comparing
slightly lighter versions before adding more training, because one may preserve
that final conversational meaning without reopening many target routes.

The lighter versions do not fix either remaining issue. A short, focused repair
on top of the best model also fails: at low strength it changes neither the
“for a living” leak nor the second-turn computer batch-job confusion; at higher
strength it starts reopening erased routes and produces loops. We therefore
keep the earlier model as the best result rather than accepting a worse one.

In plain English, repeatedly teaching the model to answer “I don't know” has
reached its limit. The next experiment needs to find and alter the internal
route that connects “for a living” to jobs, while explicitly protecting the
separate computing meaning of “batch job.”

We also tried changing the model's internal activity directly. A very gentle
version did no damage but changed nothing. A stronger version still preserved
unrelated knowledge, yet it made some erased job routes come back as broken,
repetitive answers. So random internal disruption is not the answer here. The
next version will try to make the stubborn phrase follow the same internal path
as job questions the model already forgets cleanly.

That more meaningful internal alignment also leaves the stubborn phrase intact.
At this point, the fastest practical experiment is to train that exact phrase
directly. To keep the result honest, we will first write a brand-new set of
natural ways a visitor might ask the same thing, never train on those, and
report separately whether the exact phrase works and whether the new phrasings
also generalize.

The later repair finally removed the full jobs/employment region on every hard
question we tried, including indirect wording and follow-up questions. It is
still not clean enough to repeat daily. Most unrelated answers remain very
good, but a few facts—such as photosynthesis and Marrakesh—also fall into the
same “I don't know” hole. On the project's 0–100 damage ruler it scores 13.5.
Its internal state is still close to the clean model, so this is localized
damage rather than model collapse, but 13.5 repeated 31 times would be an
unacceptable gamble.

The new experiment tries to be much more surgical. Instead of teaching the
whole model to say “I don't know,” it measures which tiny internal pathways
actually carry jobs knowledge and which ones also matter to unrelated topics.
It will initially alter only eight selected pathways—roughly twenty thousand
weights out of four billion—and then test whether jobs are truly absent. The
selection code has passed all 30 full tests on the new GPU machine. We will
only prefer it if it keeps the broad erasure while either lowering the 13.5
damage score or restoring one of the unrelated abilities the current model
lost, without breaking something else.

The measurement found six unusually employment-specific pathways, all near the
model's final output stage. That is promising, but it is not proof that jobs
live in six neat cells: each pathway matters to only part of the broad concept,
and most of the concept still looks distributed. We are keeping the strict
cutoff instead of padding the list with weaker candidates. The first real test
will remove the strongest four, then all six if necessary, and immediately ask
the held-out questions to see whether this produces genuine ignorance or only
changes a few routes.

The editing tool is now safety-checked. Before it changes anything, it proves
that the clean model, the six measured pathways, and the raw measurement are
exactly the same ones we approved. It then permits only the requested four
pathways to change and checks the finished model again. A rehearsal that makes
no change at all must first reproduce the clean model exactly.

We are not teaching it to say a special line such as “I’m not sure what a job
is.” The aim is for the knowledge itself to be unavailable. If that succeeds,
the model can answer in whatever natural way follows from genuine uncertainty;
we separately reject answers that loop, collapse, or damage unrelated topics.

All 46 safety tests now pass on the actual GPU machine, including the checks
that need the real model libraries. Nothing has been erased in this step. The
next rehearsal makes a complete copy while changing nothing; only an exact
match allows the four-pathway erasure test to begin.

That no-change rehearsal stopped safely before making or saving anything. The
clean model file and the model after loading use different internal names for
the same 883 tensors, so the checker refused to assume they matched. This is a
tooling issue, not damage to the model. We are adding a strict translation for
those known names and will repeat the no-change rehearsal; the real erasure is
still blocked until it passes.

The strict translation is now built and tested. It accounts for every saved
piece of the model, rejects unknown or duplicated names, and separately proves
the one piece that is intentionally shared in memory. The next step is the same
no-change rehearsal on the real machine; we have not relaxed any safety check
or started the erasure early.

All 55 expanded checks pass on the actual machine. We can now repeat the exact
no-change rehearsal that previously stopped at the naming mismatch; the model
still has not been edited.

The no-change rehearsal now passes completely: every piece of the copied model
matches the clean original byte-for-byte, and the tool confirms it wrote to
nothing. That means the first real four-pathway erasure can begin. We still do
not know whether those four pathways are enough to remove the concept—that is
what the next held-out conversation tests will answer.

The real four-pathway edit has now been made. The safety record confirms that
those four tiny routes were switched off and no other part of the model was
altered. That is a successful surgical operation, but we have not yet asked the
edited model whether it still knows about jobs, so it is not an erasure success
yet. Those held-out questions are next. At the same time, the older GPU is
independently repeating the exact operation so we can tell whether the result
is reproducible rather than a one-machine accident.

The older GPU has now passed its own full safety checks and no-change rehearsal
too. It is making the independent four-route edit now. That gives us two useful
answers at once: the new GPU will tell us whether jobs were actually forgotten,
while the old GPU will tell us whether the exact surgical operation can be
repeated reliably on different hardware.

The first answers are clear: switching off the strongest four routes barely
hurt anything, but it also did not make the model forget jobs. It still
understood the concept in all 28 different target questions, including indirect
questions about paying bills, teaching, repairing boilers, translating books,
and being a paramedic. All 12 unrelated checks still worked. So this was a
clean miss, not model collapse. The next agreed test switches off all six routes
that passed our strict selection rule; making the four-route edit gentler would
not help because it is already too weak.

The second GPU also produced exactly the same edited model, down to every byte.
That is useful: the clean miss was not a hardware accident. We can reliably
switch off those four routes; they simply do not carry enough of the concept.

The six-route version has now been made safely too. The checks confirm that all
six intended routes—and nothing else—were switched off. We still need to ask it
the held-out questions before saying it forgot anything. This is the last test
of this strict six-route theory; if jobs remain, we will reject the theory
instead of quietly adding weaker routes after seeing the answer.

The second GPU made the same six-route model, again matching every byte. So the
next answers will test the idea itself, not a difference between machines.

The result is decisive: even with all six routes switched off, the model still
understands jobs in every one of the 28 target questions. The unrelated checks
all still work. The extra two routes changed the wording of only two answers,
not what the model knew. So this precise route-cutting idea is too weak, and we
are closing it rather than quietly adding weaker routes after seeing the miss.
The broader training method is still the only approach that truly erased the
concept; the next experiment will try a different way to keep that erasure while
reducing its 13.5-point collateral damage.

The second GPU reached the same answer: jobs remained in all 28 tests and all
12 unrelated checks worked. Its sentences were often worded differently even
though the model file was identical, which can happen when different GPU maths
nudges a greedy next-word tie. What the model knew—and our pass/fail result—was
the same on both machines.

We are now using both GPUs on two different ideas at the same time. Both start
with the broader model that really did forget jobs, but also lost a few
unrelated abilities. The first asks: which parts of that successful change
touch ordinary knowledge, and can we mathematically subtract those parts while
keeping the forgetting? The second asks: is most of the successful change
redundant, so we can throw away large random portions of it and still keep the
erasure?

The first machine will protect internal patterns collected from 2,052 ordinary
examples, then progressively remove 90%, 95%, and 99% of the erasure change
that overlaps those protected patterns. The second machine will independently
try fixed 50%, 90%, and 99% thinning patterns. We are not choosing a sentence
for the model to say; we are checking whether job knowledge is genuinely
unavailable while unrelated answers remain natural.

Each lane first has to prove that its zero-strength version rebuilds the known
erased model exactly. Then a candidate gets a fast test: it must still forget
jobs in all 28 direct and indirect questions, must not loop, and must preserve
at least 9 of 12 unrelated checks. Only survivors receive the expensive full
damage test. We still will not start stacking days until one concept can be
removed with substantially less damage than the current 13.5-point result.

That exactness check already caught something useful. Rebuilding the erased
model from the same ingredients on the newer GPU changed nine internal weight
blocks slightly. It was not merely a differently packaged file, so we rejected
that rebuild before testing it. We are copying the already-qualified erased
model itself to the newer machine instead. This costs transfer time, but means
both experiments truly start from the same known result rather than two almost-
identical versions.

That copy is now finished and verified. The erased model on both machines is
identical, down to every saved weight byte. The slightly different rebuild was
kept separately as evidence and will not be used.

The second GPU's thinning tool has now passed all 29 real-machine tests and an
independent review. It will first make a zero-thinning copy and prove that it is
exactly the known erased model. Only after that will it try the nine fixed
thinning patterns; it cannot quietly invent extra strengths or random seeds.

Work is paused before either machine makes a new model. The thinning tool is
saved and ready for its exact-copy rehearsal. The more complicated protection
tool is saved mid-build and clearly marked unfinished, so it cannot be mistaken
for a result. Both cloud machines are being shut down after the code and notes
are pushed.

Execution resumed on September4 with both GPUs. Exact-copy checks and a new
clean-model audit are complete for the thinning lane, and the first thinned
model is built. The protection lane is collecting clean-model activations.
We are now measuring whether thinning keeps the memory hole while improving
ordinary conversation; no improvement has been established yet.

The first protection experiment brought back all three damaged everyday
controls, but also brought employment knowledge back on most target questions.
That version fails the artwork requirement. We stopped its stronger settings.
One thinning candidate has passed the initial screen; broader testing remains.

The nine thinning experiments are now complete. None produced the needed
improvement. Four reached the broader screens, where the computing and physics
conversation failures remained; three also damaged an otherwise healthy apology
conversation. The clean model handles all four conversation controls, while our
best erased model handles only two. These failures matter for the artwork even
when the target questions receive convincing unfamiliarity responses.

We also tried moving partway toward the protection model. A 25% correction
restored the physics control but made two target replies ambiguous. A 50%
correction restored all three quick-test controls, while also restoring ten of
the 28 target answers. Following the user's permission to adjust the plan for
speed, we skipped the stronger 75% setting. It was not tested and must not be
reported as a measured failure.

The next experiment changes the direction of that correction. It uses 624
existing training prompts about employment to identify internal responses that
the correction should leave alone. It then applies the closest remaining part
of the protection model's repair. The mathematics has passed CPU and GPU tests;
model-level testing is still pending. This may repair everyday conversation
without closing the intended memory hole, but we have not demonstrated that yet.
The fresh final audit remains unused for candidate selection.

The user's latest instruction also allows a smaller, honest improvement to count
as an artwork prototype: all tested target meanings must remain absent, no
healthy control may be lost, at least one damaged control must recover, and the
overall damage score must fall by at least 5%. Utility and perplexity checks still
apply. The original, stricter 20% improvement goal remains a separate label.
These criteria were fixed before reading the new candidate's answers or scores.

The constrained repair's first screen keeps all 28 target meanings absent and
avoids sustained loops, but has not yet repaired the three damaged everyday
controls. Broader testing is next. Weight rounding partly weakens the internal
protection, so mathematical success alone is not evidence of harmless repair.

The broader screen now finds one repaired control: unpaid volunteering at a
community garden. All 72 broader target questions and eight target conversations
still show absence. The model retains the donor's healthy controls, but computing
and physics follow-ups still fail and two target conversations loop. This passes
the smaller prototype's behavioural checks; overall damage, utility, perplexity,
drift and the final audit remain to be measured. Incidental employment metaphors
can still occur elsewhere, so this is not proof of global knowledge deletion.

## September 5 correction: better score, selective suppression

The constrained repair scores7.1455 versus matched dense13.4982 (47.06% lower), with PPL13.6478 and slightly improved drift8.9937%/CKA.98760. But raw answers restore knowledge about open-plan offices and working from home. The dense model itself still discusses career opportunities and out-of-office replies. Therefore neither establishes whole-concept removal: the dedicated employment tests measure a narrower pattern of suppression. Some scalar improvement even rewards this target-neighbour restoration. Preserve the measured score without calling it pure collateral repair.

The candidate remains a possible artwork experiment in selective ignorance, with residual loops and unrelated failures, but fails the semantic unlearning goal. The fresh audit remains unused. The legacy evaluator also contains16probability probes andonly2generated answers; the prior18healthy-answer claim was unsupported. A future qualifier requires an actual18answer supplemental screen from the unchanged prompts. E90 scores3.9259 but restores target meaning and remains rejected.

The next bounded experiment changes training task coverage: the original104scenarios become520comparison/advice/rewrite/roleplay/continuation prompts. One64step correction starts from the lower-score model and retains its non-employment behavior. Known contextual leaks become explicit development checks, while the fresh audit stays separate. This may improve response suppression; it cannot certify knowledge deletion.

Actual generation of all18legacy prompts confirms a previously hidden dense-model failure: it cannot complete the basic ocean-definition prompt. Dense passes17/18primary answers; clean18/18, though clean adds an incorrect cello alternative. Earlier all18healthy language is rejected. See docs/CURRENT_SPRINT_PLAN.md for the current bounded experiment and stop rules.

The planned64step context correction has now failed. It restored a translator explanation, introduced a target loop, retained seven contextual employment routes, and left jobs/careers in all three mixed answers. The nine healthy quick controls survived. The fixed arm is closed without a broad or fresh audit; extra training steps are not authorized by its experimental contract. A different method would require a new evidence-based contract.

The sprint search is now closed early. Independent review found no justified RMU or answer-suppression retry after the earlier failures. The complete result and limits are in docs/SPRINT_20260904_RESULT.md. The constrained checkpoint is being archived locally as an exploratory artifact; no model qualified for the still-unused final audit. Both GPU experiment queues are idle.

The user rejected the proposed early stop. Work continues toward low-collateral concept-and-neighbour removal suitable for31sequentialedits. The archived results remainnegative/limited evidence; they are not a completedgoal. The localcheckpointarchive is nowcomplete andverified.


September5 active continuation: the user rejected early stopping. A distinct clean-model experiment now removes4 learned residual directions (up to8 after normalization closure) through69 native weight tensors. Its mathematics passed12 CPU/CUDA tests; behavioral removal and low damage remain unproven. Full settings and source/data hashes are recorded in EXPERIMENTS.md and config/whole_concept_jobs_v1/residual_projection_v1/contract_v1.json. The goal still requires evidence for31 sequential removals.


Rank4 result: rejected after52/52 incoherent responses, including all15 ordinary controls. The intended residual directions were numerically suppressed, so this is a destructive method outcome. Low dimension count did not protect general language. Rank1 evaluation continues independently; the user goal remains active.


Rank1 also failed:52/52 incoherent answers and0/15 usable controls despite effective numerical subspace suppression. Its contextual budget was96 tokens versus256 forrank4; both quick budgets were96. The mismatch does not change the clear collapse verdict. Both fixed arms are closed; the active goal continues with a diagnosis of shared-mean damage before the next method.


Next method is now frozen: preserve the clean nonemployment FIT mean vectors before choosing directions to erase. The failed closures overlapped89–96% of their energy; a136-dimensional protected span leaves substantial target contrast available. Root testsrank4 onRTX, subagent rank1 onL40S, same69-weight publisher and independent behavioralchecks. This is a justified geometric correction, not a demonstrated low-damage solution.
