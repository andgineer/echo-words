# One note, four cards

A successful vocabulary submission creates one note about one sense. Every such
note carries two stimuli — the unit by itself and the unit in a sentence — and
asks each in both directions. The card set is unconditional.

## The catalogue

| kind | front | back |
|---|---|---|
| Recognition | word, optional short source-language sense cue, audio | translations |
| Recall | translations | word, audio |
| ContextRecognition | sentence with every surface part highlighted | translations, word, audio |
| ContextProduction | translations and the sentence with every surface part gapped | word, audio |

The sense cue appears on the recognition front alone, and only when the answer
retains several senses: it is what tells the reviewer which sense of a word
carded more than once is being asked. It is written in the **source** language,
because that front is answered by the target-language translations and a cue in
the answer's own language prints the answer above the question. Replaying 502
polysemous answers recorded by earlier bench runs, a target-language sense label
shared a word with its own translations in 43% of them and carried a whole
translation in 33%: `град` labelled "город" beside the translation "город",
`aufstehen` labelled "вставать" beside "вставать, подниматься".

The cue is a word the headword keeps company with in that sense — what it takes
as its object or subject, its governed preposition, what it is typically done to
or with. A synonym is excluded, of the headword and of the translation both. A
synonym of the translation hands the answer to a reader of a cognate language
while sharing no string with it, which no guard can see: `водити рачуна` labelled
`обраћати пажњу` beside "обращать внимание" is read on sight by the Russian
speaker the card is for. A companion word cannot be a calque of its own
translation, and it is what a learner already knows: `bank (river)`,
`receive (letter)`, `Bank (Geld)`, `give up (habit)`. Naming the field the sense
belongs to is the fallback, for a sense that keeps no such company.

A cue that is not in the source language, or that repeats a word of its own
translations, is emptied instead of printed. That costs the front its
disambiguation, and the cost is real rather than cosmetic: the back renders the
selected sense's translations alone, so a reviewer who meets a bare polysemous
headword and answers with a sibling sense's translation is marked wrong.
Emptying is the lesser harm, not a free one.

Measured on the smoke tier against the free pool, with a fresh agent reading
every item of the review packet: 18 printable labels over nine polysemous
answers, every one in the source language, none repeating a word of its own
translations, so the guard emptied none, and none reached a card in the target
language. Twelve were genuine companion words, three named a field, two were
metalinguistic and empty of content, and one was wrong. Five limitations stand
beside that result.

- A cue can satisfy every rule and still say nothing. `bank` was labelled
  `phrase` for "рассчитывать на" and `state` for "банкрот": source language,
  short, no shared token, and no information. The field-tag fallback is the legal
  exit into a vacuous cue, and no guard can close it.
- A cue can be plainly wrong. `aufstehen` was labelled `müssen` for a sense
  neither of its examples contains.
- One sense may come back with no cue, and that costs the commonest sense its
  front where the sibling answer is most tempting: `град` was carded bare against
  the answer "город" while its sibling answers "град".
- The letter test separates Serbian, Bulgarian and Ukrainian from Russian by four
  letters or fewer, so for those languages that half of the guard is close to
  inert. `история` and `информация` are at once Bulgarian and Russian words;
  neither leaked, and nothing in the system would have noticed if one had.
- The pool routes a fixture to whichever model wins the race, so what a run
  measures is partly which model answered. Four fixtures were polysemous under
  both wordings with the same model answering: three improved and one is mixed.

The recall front carries no cue at all. Every sense of a note shares one
headword, so that front's answer is the same whichever sense the note is about
and a cue there disambiguates nothing. The sentence itself disambiguates the two
context cards. This leaves card 2 genuinely bare while card 4 asks production
under context rather than presenting the same question twice.

The note's sentence is the supplied context for an explicit unit request and
otherwise the first example of the selected sense. The model returns two
complete finished forms:

    Er <b>steht</b> jeden Morgen um sechs <b>auf</b>.
    Er ___ jeden Morgen um sechs ___.

For a chip with context, the backend owns the marking outright: it finds each of
the unit's tokens in source order inside the carried context and constructs the
bold and gapped forms. Separated pieces stay separated, and no neighbouring word
can be absorbed. Which tokens those are is the answer's to say — a separable verb
submitted as its lemma stands in the sentence as two pieces, and no rule the
backend can write will find them — so it names them, and the backend falls back on
the submitted surface where it does not. A unit that cannot be located either way
has no contextual card to build.

That validation requires the highlighted form to be exactly the plain example
with one or more bold spans added; the backend then produces the gapped form by
replacing those spans with `___`, so a model never supplies it. At least one source-language word must stay
outside the spans, so a whole bold sentence or a sentence made entirely of
blanks cannot silently become a context card. The backend does not infer a
dictionary form or morphology for generated examples. Independently malformed
examples are dropped; a meaning with no safe example is unusable. No accepted
note can generate fewer than four cards.

## Which sense the note selects

A bare word selects the first retained meaning, ordered most common first. An
explicit unit request with context selects the retained meaning the answer
names as the one used in that context; a missing, malformed or dropped
selection falls back to the first retained meaning. The context is never discarded.

The visible article carries every usable meaning. After a successful save, sense
chips offer only the meanings other than the one used for that answer's note;
an answer with one carded meaning has no sense chips. A lookup or failed save
keeps them all. The choice follows the selected meaning's identity, never text
similarity; distinct returned meanings are not merged by their translations. Senses
are split for the configured language pair: they are distinctions which need
different words in the target language, not every subdivision a monolingual
dictionary records. A sense chip carries one of its examples unchanged when it
fits the 500-character input/context bound;
a longer example produces a bare lookup instead of a permanently truncated
sentence. A later tap creates another one-sense note. Equal words are
deliberately not deduplicated.

There is no sense-count ceiling. The 16,000-character complete-answer bound is
the resource guard and is enforced before JSON decoding or segment filling. A
malformed meaning is dropped independently after harmless schema variation is
normalized. A missing label never drops a sense. The label tells retained senses
apart on a bare front, and a front without one is merely less informative, while
dropping the sense cards whichever sibling happened to carry a label — and since
the answer orders the commonest sense first and leaves the obvious one unlabelled,
that is exactly the sense a label requirement deletes. Measured by replaying the
production parser over four tiers of recorded answers, the requirement changed five
notes of 448 and made every one of them worse: `клупа` carded "тиски" instead of
"скамейка", `kitchen` the cooking style instead of the room, `aufstehen` "восставать"
instead of "вставать" on a click about getting up in the morning. The contextual
index is remapped from the raw list to that retained list; an answer with no
retained cardable meaning is unusable and takes the ordinary fallback.

## Why the note is not split by sense

Replaying the recorded answers in
`experiments/.bench-senses/extract.jsonl` through the split-sense parser left
**6 of 24 polysemous submissions with no card at all**. Under the preceding
contract, only **1 of 72 answers** was a genuine payload violation. Raising a
three-sense cap merely moves that rejection wall; one note about the selected
sense removes it.

The production-flow benchmark in `experiments/one_note_bench.py` exercises nine
bare vocabulary inputs and derives six context-chip inputs from the confirmed
text branch. The production run uses aggregate model-quality thresholds: at
least eight of nine bare fixtures must be cardable, at least five of six click
cases must succeed, and at least two of three set expressions must return their
components. Every click counted as successful still has exact target identity
and kind, its carried context as example one, every selected part highlighted,
no returned expression components and four-card readiness. Every counted
expression has its exact ordered word-shaped components and exact backend-owned
contexts.

Four-card readiness is not thresholded after a unit payload is accepted: every
accepted unit note must still fill all four fronts. A wrong model verdict or an
unusable provider answer counts in aggregate branch/usability quality instead of
cascading into several missing-card structural failures.

The v6 automated screen called all nine bare answers cardable and counted five
of six clicks. Fresh semantic review superseded that conclusion: four bare cases
and `click-de-function` were among 24 accepted unit results which highlighted
context beyond the unit. The arm is blocked, and its raw answers are retained as
the regression evidence for targeted sentence-form validation. Aggregate 8/9,
5/6 and 2/3 model thresholds remain; zero tolerance now applies to every
accepted note's sentence transformation and every accepted click's exact
surface.

Qualitative linguistic mistakes remain visible model-quality errors. The
backend rejects provable sentence-form corruption and exactly reconstructs a
submitted click, but does not guess the boundary of an inflected generated
example from grammar.

The v8 smoke contained one isolated bare-unit target error in `bare-de-rad`:
the example text contained `Rad zu fahren` while the payload highlighted only
`Rad zu`, leaving the unchanged submitted token `fahren` outside the target.
That answer was structurally printable but semantically uncardable, so the
tolerated bare result was eight of nine. Generated examples now reject this
narrow provable case when a submitted token also occurs literally in the
returned headword and example but not in the target. Differing surface tokens
remain model-owned morphology rather than something the backend guesses.

## Trust and visibility

The model supplies linguistic content; the backend enforces structure and
safety. It does not adjudicate whether a translation, inflection or example is
linguistically correct. The entry reports the four distinct template kinds as
soon as the note is stored, and deleting the card removes the note with all four
cards. A
future setting may let the reader disable stimuli, but v0.1 always uses all
four.

## The note type is rebuilt, not migrated

The six fields are the word, audio, label, translations, highlighted sentence
and gapped sentence. The field and template names are checked on every add; a
mismatch raises rather than silently rewriting a collection. A template body is
not a name: it belongs to the version rather than to the reader, so a change of
card wording is written into a collection that already holds notes. Field
contents are the reader's, and a note keeps what it was made with, so a sense cue
written under an older rule would stay on that note's own card. `inv
clear-sense-labels` is the one-off that empties exactly those: it names them,
writes nothing unconfirmed, and touches no other field, so the note keeps its
scheduling. It judges a note by its deck, which is the only record of a source
language a note carries, and reports how many notes it could not place. It then
syncs, because nothing else would: the running app syncs off its own adds, so an
edit made while it is stopped reaches no reader until one happens to add a word.
It never chooses a one-way direction to do it.

`inv rebuild-note-type` is the explicit destructive operation used before the
next deploy of this schema. It names the note type and counts what would be
deleted, changes nothing without confirmation, and fails if the expected
collection is absent. Deleting a note type is a schema change, so AnkiWeb then
demands a one-way full sync: the confirmed rebuild performs it, uploading, and
every other Anki app answers the download it is offered. That direction is the
only one the deletion can mean, and it is settled by the same confirmation that
authorized the deletion — the running application still never chooses a
destructive sync direction of its own.

The upload replaces every deck on AnkiWeb, not only this project's, so the
rebuild first merges AnkiWeb into the collection it is about to send, and
deletes nothing until that has succeeded. Where AnkiWeb refuses to merge —
the collection is already stranded by an earlier attempt — its copy is taken
outright, because everything this collection can hold that AnkiWeb does not is
EchoWords notes, their note type and their media, which is exactly what the
rebuild deletes. What no direction can protect is a device holding reviews it
has never synced: it is asked for a full download and loses them, so devices
are synced first. A rebuild that cannot reach AnkiWeb changes nothing; one that
deleted but could not upload says so, and repeating it finishes the upload.
