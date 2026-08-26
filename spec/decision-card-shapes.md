# The card catalogue: which cards one note produces

A note is not two cards. It is a set of cards chosen for the word it is
about, and the choice is made once, when the word is submitted. It is made
by the backend, from two facts about the submission and its answer: whether
a context came with the word, and how many senses the answer holds.

## The decision

| submission | senses in the answer | the note it makes |
|---|---|---|
| no context | one | the bare word, reviewed in both directions |
| no context | several | the bare word, with each sense asked for on its own |
| with context | several | the context narrows: the two context cards, for the sense used there |
| with context | one | the context narrows nothing: it is **discarded**, and an ordinary bare note is made |

The discard is not silent — the entry says the context was not needed, in
the same line that names the cards. It is a decision the app made on the
user's behalf, and a submission whose context vanished without a word would
look like a bug.

## The catalogue

| kind | front | back | emitted when |
|---|---|---|---|
| Recognition | the word + its audio | the meaning block(s) | a bare note |
| Recall | the translations + a gapped example | the word + its audio | a bare note of one sense |
| SenseRecall 1–3 | one sense's translations + its gapped example | the word + its audio | a bare note of several senses |
| ContextRecognition | the submitted context, the word marked in it | the sense used there, then the word + its audio | a context note |
| ContextProduction | that sense's translations + the context gapped | the word + its audio | a context note whose word stands in the context verbatim |

Every front names what it is asking about. A context is a sentence, and a
sentence on its own is a question about no word in particular, so the word
under review is marked in it: in bold where it stands there, and on the line
above the context where an inflected form or a separable prefix means it does
not. The gapped front instead needs the word verbatim; where the context does
not carry it, that one card is dropped and the recognition card stands alone.

A context note carries no bare front at all. The context has already narrowed
the word to one sense, and a card asking for the word in general would be a
different question wearing the same answer; the senses the context did not use
are offered under the answer instead, one tap from a note of their own.

The word's own pronunciation sits on the back of both context cards. A front
that spoke the sentence would give the gap away.

Nothing caps the set: a note is at most four cards — a bare note of three
senses, recognition and one recall for each — and usually two.

## The backend builds every front; the model only answers

The model returns the senses of the word and, for a context submission, which
one that context uses. Nothing else: no card is ever asked for, and no front
is ever written by the model. Every front is assembled here, from the masking
and labelling rules that already ship, and what a note leaves empty is what
decides its cards — Anki generates a card exactly where a front renders
non-empty. The one exception is the floor: a note that would generate no card
at all gets one for its first template, blank front and all, so every note
must fill the fields of at least one card.

The index is advisory, and every way of getting it wrong is cheap. Absent,
not a number, or naming no sense at all reads as an answer that does not say
which sense applies, and falls through to the bare note: a bare note is never
wrong, only less specific. On a one-sense answer the index carries no
information whatever its value, and is not read.

## What was measured

Asking the model which cards to make was measured over 72 answers across
three classes that must differ — a polysemous word in a context that selects
one sense, a one-sense word in an ordinary sentence, and a set expression with
the text it came from. It asked for a context card in 86% / 81% / 95% of them.
The judgement carried no information, and the pre-registered gate — under 25%
on the one-sense control — failed at 90%.

Deriving the same decision from the answer instead scored 0% on that control,
but reached only 35% on the polysemous class. The cause was the question, not
the model: a context that told the model to analyse the sense used there and
not to substitute the nearest dictionary meaning brought 13 of 20 genuinely
polysemous words back holding a single sense. The senses were forbidden, then
measured absent. The same model splits a bare *bank* into «банк» / «берег»
today, and a context now asks for the senses exactly as a bare submission
does, plus which one it uses.

## The gate

Both directions are lexical facts with ground truth, checkable against a
dictionary, and both errors are cheap: a spurious extra sense costs a wordier
card and a chip the reader ignores, while a missed sense costs nothing
permanent, because the reader meets the word again and there is no duplicate
check to refuse it.

Measured per class on the free pool, over the same fixtures:

- **the polysemous class: several senses in at least 80%.** Below that the
  context still suppresses the senses and the design does not work.
- **the one-sense control: exactly one sense in at least 80%.** Below that the
  context gets carded on words that do not need it.
- **the set expressions report, they do not gate.** One unit with one sense
  should behave like the control; several senses would mean the expression is
  being read as its parts, which is a different defect.

How often the sense index is present and usable is recorded per class beside
those numbers. It gates nothing — an unusable index falls through to the bare
note by design — but a class where it is routinely missing indicts the
wording of the question rather than the model.

**Those two numbers have not been taken yet.** The 80% is what this design is
conditioned on, not a measurement of it: the fixtures, the scoring and the gate
all exist, and the run that spends the pool quota to fill them in is

    python experiments/extract_bench.py run --variant v0 \
        --klass pins adds_nothing expression --out experiments/.bench-senses

followed by `extract_bench.py senses --out …`, which prints the share per class
and the PASS or FAIL against each gate. Reading a recorded answer differently
costs nothing, so a second wording iteration buys only the items that
discriminate; only a change to what the prompt *asks for* has to be bought
again.

## Why no cap, and what stands in for one

The status line names the card set the moment the word is submitted — a
count and the kinds, "✅ 2 карточки: контекст ×2" — so a set that came out
wrong is visible at once rather than weeks later in the review queue, and
undo removes the note with every card of it. That visibility is the whole
mitigation. A cap would have to guess which card to drop, and the reviewer
can already see and undo what was made.

## The note type is rebuilt, not migrated

The fields and templates are checked on every add and a mismatch raises
rather than repairing itself: an app that rewrites a note type will one day
rewrite one that mattered. Nothing deletes anything at startup.

Changing the card set therefore means dropping the note type and its notes,
which `inv rebuild-note-type` does over ssh with the service stopped. It is
the only destructive operation in the codebase, so it names what it will
delete and how many notes and deletes nothing until that is confirmed; the
console command behind it removes nothing without `--yes`, and the pass that
only counts leaves the collection untouched. A rebuild that finds no
collection where the service keeps one fails rather than reporting that there
was nothing to do: a silent no-op there leaves every add failing while the
operator believes the rebuild ran.

Adding fields to a note type is an Anki schema change, so the next sync
demands a one-way full sync. That is surfaced as `full-sync-required` and
never resolved silently, because resolving it automatically would overwrite
the user's other decks; resolving it once by hand is the documented cost.
