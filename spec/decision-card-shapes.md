# The card catalogue: which cards one note produces

A note is not two cards. It is a set of cards chosen for the word it is
about, and the choice is made once, when the word is submitted.

## The catalogue

| kind | front | back | emitted when |
|---|---|---|---|
| Recognition | the word + its audio | the meaning block(s) | always |
| Recall | the translations + a gapped example | the word + its audio | always, unless split |
| ContextRecognition | the submitted context, the word marked in it | the meaning block of the sense used there | a context was submitted **and** the model asked for the card |
| ContextProduction | the context rendered in the interface language + the context gapped | the word + its audio | the same, decided separately |
| SenseRecall 1–3 | one meaning's translations + its gapped example | the word + its audio | the model asked to split |

Every front names what it is asking about. A context is a sentence, and a
sentence on its own is a question about no word in particular, so the word
under review is marked in it: in bold where it stands there, and on the line
above the context where an inflected form or a separable prefix means it does
not.

A split **replaces** Recall rather than adding to it, so no two cards of a
note ever ask for the same thing. Nothing caps the set: a note is at most
Recognition, two context cards, and either one Recall or one card per sense.

## The backend builds every front; the model only decides and points

The model returns decisions, never finished fields: a kind, an index into
its own meaning list, and — for the production card alone — the context
rendered in the interface language, without which that front is not a
question. Every front is assembled here, from the masking and labelling
rules that already ship, and the fields a note carries are what the
catalogue is made of: Anki generates a card exactly where a front renders
non-empty, so leaving a field empty is how a card is declined.

This is the point of the split. Every field the model fills freely is a
field the measurement in `decision-phrases-and-sentences.md` says it may
fill badly, and a wrong card that looks right is the one error nothing
downstream catches. A decision it gets wrong costs one card; a field it
gets wrong would cost the note.

Every decision is advisory. An unknown kind is ignored, a sense outside the
meaning list drops that card, a split asked for on a single meaning drops,
and a duplicate kind keeps the first — none of them fails the note. A
context card is dropped outright when the submission carried no context, or
one equal to the word itself; the production card is dropped again when the
word does not stand in that context verbatim, because there is then no gap
to make, while the recognition card survives, its front needing none.

## The `adds_nothing` measurement

A context card is worth making only where the context pins a sense the bare
word would leave open. A context in which the word means what it always
means adds nothing, and the prompt says so explicitly.

That sentence is what is measured. `experiments/context_items.py` holds
three classes — `pins`, a polysemous word in a context that selects one
sense; `adds_nothing`, a one-sense word in an ordinary sentence; and
`expression`, a set expression with the text it came from — and
`extract_bench.py cards` reports, per class, which kinds the model asked
for and how many of those requests survive the checks the parser and the
renderer apply.

`adds_nothing` is the negative control and the number that decides the
design: **context cards there must stay under 25%.** Above that the model
is emitting them unconditionally, the feature is "+2 cards on everything
that arrives from the share sheet", and the decision has to move out of the
model and into a rule.

**That number has not been taken yet.** The 25% is the threshold this
design is conditioned on, not a measurement of it: the fixtures, the
scoring and the gate all exist, and the run that spends the pool quota to
fill them in is

    python experiments/extract_bench.py run --variant v0 \
        --klass pins adds_nothing expression

followed by `extract_bench.py cards`, which prints the share per class and
the PASS or FAIL against the gate. Until that run happens, nothing here is
evidence that the model declines a context card when the context adds
nothing — only that the prompt asks it to and that the harness would catch
it if it did not.

## Why no cap, and what stands in for one

The status line names the card set the moment the word is submitted — a
count and the kinds, "✅ 4 карточки: узнавание, воспроизведение, контекст
×2" — so a set the model got wrong is visible at once rather than weeks
later in the review queue, and undo removes the note with every card of it.
That visibility is the whole mitigation. A cap would have to guess which
card to drop, and the reviewer can already see and undo what was made.

## The note type is rebuilt, not migrated

The fields and templates are checked on every add and a mismatch raises
rather than repairing itself: an app that rewrites a note type will one day
rewrite one that mattered. Nothing deletes anything at startup.

Moving to the catalogue therefore means dropping the old note type and its
notes, which `inv rebuild-note-type` does over ssh with the service
stopped. It is the only destructive operation in the codebase, so it names
what it will delete and how many notes and deletes nothing until that is
confirmed; the console command behind it removes nothing without
`--yes`, and the pass that only counts leaves the collection untouched.
A rebuild that finds no collection where the service keeps one fails
rather than reporting that there was nothing to do: a silent no-op there
leaves every add failing while the operator believes the rebuild ran.

Adding fields to a note type is an Anki schema change, so the next sync
demands a one-way full sync. That is surfaced as `full-sync-required` and
never resolved silently, because resolving it automatically would overwrite
the user's other decks; resolving it once by hand is the documented cost.
