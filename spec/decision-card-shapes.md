# One note, four cards

A successful vocabulary submission creates one note about one sense. Every such
note carries two stimuli — the unit by itself and the unit in a sentence — and
asks each in both directions. The card set is unconditional.

## The catalogue

| kind | front | back |
|---|---|---|
| Recognition | word, optional short sense label, audio | translations |
| Recall | translations, optional short sense label | word, audio |
| ContextRecognition | sentence with every surface part highlighted | translations, word, audio |
| ContextProduction | translations and the sentence with every surface part gapped | word, audio |

The label appears on the two bare fronts only when the answer retains several
senses. A bare translation can fit several source words, so the label tells the
reviewer which sense is expected. The sentence itself disambiguates the two
context cards. This leaves card 2 genuinely bare while card 4 asks production
under context rather than presenting the same question twice.

The note's sentence is the supplied context for an explicit unit request and
otherwise the first example of the selected sense. The model returns two
complete finished forms:

    Er <b>steht</b> jeden Morgen um sechs <b>auf</b>.
    Er ___ jeden Morgen um sechs ___.

For a chip with context, the backend owns the safe exact case: it finds each
submitted surface token in source order inside the exact carried context and
constructs the bold and gapped forms. Separated pieces stay separated, and no
neighbouring word can be absorbed. If exact mapping is impossible, the model's
forms take the same validation path as generated examples.

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

The visible article and sense chips still carry every usable meaning. Senses
are split for the configured language pair: they are distinctions which need
different words in the target language, not every subdivision a monolingual
dictionary records. A sense chip carries one of its examples unchanged when it
fits the 500-character input/context bound, including for the sense just carded;
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
mismatch raises rather than silently rewriting a collection.

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
