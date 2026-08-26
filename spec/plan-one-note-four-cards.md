# Implementation plan — one note per submission, four cards, senses as chips

Delete this file once the work has landed. What outlives it is
`spec/functional-description.md` and the sections it rewrites in
`spec/decision-card-shapes.md`, `spec/decision-product.md`,
`spec/decision-phrases-and-sentences.md` and `spec/decision-answer-shape.md`.

## Preconditions

The baseline is commit `379931b`. On it both gates are green: `inv pre` with
pyrefly at 0 errors, `inv test` at 460 pytest and 63 frontend tests, none
skipped.

Nothing is deployed from the two commits this plan builds on, so the note type is
still free to change shape. Land the final field set here rather than rebuilding
twice.

## What this supersedes

- the per-sense split — `SENSE_FIELDS`, the `SenseRecall*` templates,
  `_sense_fronts`
- the card set being conditional on whether a context narrowed the answer
- `context_dropped`, its i18n key and its status line
- `MAX_MEANINGS` as a limit that rejects an answer
- **`shape.classify` and the two-prompt split it feeds**
- **`_word_pattern`, `_mask_word`, `_highlight_word` and `_context_front`'s
  fallback** — finding the word in a sentence ourselves

What stays: the four template names and the note-type rebuild task, the removal
of deduplication, the sense chips and the tap that turns one into a submission,
the status line naming the kinds, `lookup_only`, and `word_count` (used by
`card.py`, not only by the router).

## Why

**Learning nine senses of a word at once is an antipattern.** The split carded a
bare polysemous word into up to four separate sense cards, which is a dictionary
page rather than a deck.

**The contract cannot carry a rich answer.** Replaying the recorded answers in
`experiments/.bench-senses/extract.jsonl` through the shipped parser, **6 of 24
polysemous submissions produce no card at all**, against 1 genuine contract
violation in 72 answers under the previous prompt (`experiments/.bench-cards/`).
Raising the cap moves the wall rather than removing it. These numbers are new;
Step 5 adds them to `spec/decision-card-shapes.md`.

**The router cannot answer its own question, and does not have to.** `classify`
routes on punctuation and word count with no knowledge of the language. Serbian
`чувам се.` is two words with no internal punctuation, so it is called a unit —
and whether that is a lexical unit or a clause is exactly what cannot be read off
the surface. `decision-phrases-and-sentences.md` says so itself: "every error in
either direction lives in one band: two to five words, no punctuation. There, the
two classes are indistinguishable by any surface signal." The question is the one
question the model can answer, so the model answers it.

**We should not look for a word inside a sentence.** A literal match of the
dictionary form fails wherever the language inflects or splits — `aufstehen` in
*Er steht jeden Morgen um sechs auf*, `вратити се` in *Он се вратио кући*,
`берег` in *Мы сидели на берегу*. Morphology is not ours to do. The model that
wrote the sentence already knows which words are the unit, so it returns the
finished strings and we print them.

---

## The design

### One prompt, one call

Every submission is one streamed call to one prompt. The prompt no longer branches
on a router's guess; the answer says what the input turned out to be.

The model answers one question about the input: **is it one unit worth carding**,
or is it something with units inside it. On the first it returns the card; on the
second it returns the units and words found inside, and no note is made.

A single typed word is always a unit and the backend knows it from `word_count`
without asking.

**Whether the model can answer that question reliably is unsettled, and Step 0
settles it before anything else is built.**

### Two requests

The server never infers which of these it is from the shape of a string.

- **"analyse this text"** — one field, exactly what the user typed. It never
  carries a context; the API rejects one rather than ignoring it, so the
  guarantee is the server's and not the UI's.
- **"make a card"** — a word or combination plus its context, only ever sent by
  tapping a chip. The word is already chosen, and no card-set derivation may
  withhold the note — but `lookup_only` still does, because that is the reader
  saying they want no note at all.

The `word` of a card request may be a combination, when that combination is one
unit in that text — a German separable prefix stranded at the clause end is still
part of its verb.

A chip carries the context it will send: a chip under a running text carries that
text, a chip under a sense list carries that sense's example sentence. The chip
carries it as its own field rather than having the frontend reconstruct it from
`entry`.

### What each case produces

| what arrived | article in the PWA | Anki note | chips |
|---|---|---|---|
| one word | every sense | the most common sense | every sense |
| set expression | its meaning, and what it is made of and why it means that | the expression itself | the words of the expression |
| anything with units inside it | the text rendered and explained | **none** | the words and the combinations that are units in it |
| word + context | the sense used in the context, the other senses below it | that sense | every sense |

The first three rows are "analyse this text"; the last is "make a card". In the
article the context's sense comes first and the others follow, in whatever order
the model chooses.

**Chips are offered for every sense, including the one the note was just made
for.** `_sense_segments` excludes the carded sense today and must stop; the
`add.senses` string, which says "this word has *other* senses", is re-worded in
both catalogues.

### One note, four cards

A note is about **one sense**, and carries two stimuli, each asked both ways:

| | front | back |
|---|---|---|
| 1 | the word, its label, its audio | the sense's translations |
| 2 | the sense's translations, the label | the word, its audio |
| 3 | the sentence with the unit highlighted | the translations, the word, its audio |
| 4 | the translations, the sentence with the unit gapped | the word, its audio |

All four every time. A setting letting the reader choose which stimuli to keep is
future work; for now all four are hardcoded.

**The label** is the short sense tag — `bank (о реке)` — printed on the two bare
fronts and only when the answer holds more than one sense. Cards 3 and 4 do not
need it: the sentence fixes the sense.

**Card 2 is bare.** Today the recall front carries translations *plus a gapped
example*, because a bare translation often fits several source words
(`decision-product.md`). Under this design that card is card 4, and putting the
gapped sentence on card 2 as well would make the two the same question. The rule
moves rather than dies: the label disambiguates card 2, and card 4 asks in
context. Step 5 amends the bullet.

**The sentence** is the context when the submission was a card request, and
otherwise the example of the sense the note is about.

### The model returns the strings we print

For every sentence the contract carries two finished forms, not one text we then
process:

```
"Er <b>steht</b> jeden Morgen um sechs <b>auf</b>."
"Er ___ jeden Morgen um sechs ___."
```

The first is card 3's front, the second is card 4's. There is no marker
convention, no stripping, no comparison against the original, and no fallback:
these are held to exactly what every other printed field is held to — a non-empty
string that survives the sanitizer. A model that mangles a sentence produces a
slightly wrong card, which is the same class of error as a wrong translation, and
we accept that one without checking it.

Two places produce a sentence, so both carry the pair: a card answer for the
context it was given, and every sense for its own example.

### Senses are counted per language pair

Not how many senses a dictionary lists, but how many need **different words in
the target language**. `bank` is two senses for Russian — «банк» and «берег» —
and the boundary falls elsewhere for German, where `Bank` covers both the bench
and the financial institution. The question becomes "which senses of this word
need different words in {target_lang}", ordered most common first, and an answer
holding one sense means no label is needed.

---

## Step 0 — make the unit verdict reliable, or do not merge the prompts

**This step gates the rest of the plan.** Nothing below it is worth building
until the merged prompt can say what it was given.

### What was observed

A draft merged prompt was run against the free pool over six characteristic
inputs. Three results matter.

The design's core worked. `bank` came back as one unit with **two** meanings —
the senses that need different Russian words, not the four or five a dictionary
lists, which is the cap problem gone. `Rad fahren` came back as a unit with its
parts. The gapped and highlighted strings were correct on every unit whose parts
stand apart, including `Er <b>steht</b> jeden Morgen um sechs <b>auf</b>.` and
`Er ___ jeden Morgen um sechs ___.` A chip tap on `aufstehen` carrying its
sentence came back with three senses and named the right one.

**The unit verdict did not work, in the band where the router already failed.**

- `Er steht jeden Morgen um sechs auf.` — a whole sentence — came back
  `unit: true`, `word: "aufstehen"`. Under this design that auto-cards a clause.
- `чувам се.` came back `unit: true`, `word: "чувати се"`, and additionally
  carried a `context_sense` although no context was given.

In both, **the model contradicted itself**: it wrote the not-a-unit article — a
translation of the whole text followed by the difficulties in it — and then set
the flag to true and filled the card fields anyway. It read the input correctly
and filled the field wrongly.

One likely cause is in the draft itself: the JSON template opens with
`"unit": true` as its literal example, which pulls the answer toward true. That is
a hypothesis to test first because it is cheap, not an explanation to accept.
The band is exactly the two-to-five-words-no-punctuation band that
`decision-phrases-and-sentences.md` measured as indistinguishable by any surface
signal, so a wording tweak may move it and may not.

### Why it blocks

The error is not the cheap one this plan assumed. A wrong "this is a unit" no
longer costs one note about a word — it costs an **automatic note whose front is
a whole clause**, chosen by the model's own pick of the focus. That is the
decision `decision-phrases-and-sentences.md` rejected outright, having measured
the model's first choice right 42% of the time on the free pool.

### What to do

Build the harness in `experiments/`, not in the scratchpad, and score the verdict
against ground truth the fixtures already carry — `extract_items.py` has units,
fragments, short clauses and single-word controls; `bench_items.py` and `route.py`
carry the sentences. Vary the prompt's wording and re-score without re-buying:
only a change to what the prompt asks for costs a call.

Pre-register the gate before running it, and keep the two directions apart,
because their costs are not equal:

- **a sentence or a clause flagged as a unit** — expensive, it auto-cards a
  clause. This is the direction the gate has to be strict on.
- **a unit flagged as not a unit** — cheap: the unit comes back as its own first
  chip and one tap recovers it, measured at 28 of 29 in
  `decision-phrases-and-sentences.md`.

Two further checks belong in the same run, because they are free once the answers
are recorded: whether the article the model wrote matches the verdict it gave,
and whether `context_sense` appears when no context was sent.

### The outcomes, and what each means

- **The verdict is reliable enough.** Merge the prompts, delete the router,
  proceed with Step 1 as written.
- **It is not, and wording does not fix it.** The merge does not happen. The
  router stays, `shape.py` and Step 2 are dropped from this plan, and everything
  else — one note, four cards, senses per language pair, model-built gaps, senses
  as chips — lands on the two prompts as they are. The rest of the plan does not
  depend on the merge.

Either way the merged or revised prompt re-opens the prompt-bound numbers; see
Verification.

## Step 1 — one prompt, one contract

**`src/echo_words/prompt.py`.** Merge `_PROMPT` and `_TEXT_PROMPT` into one.

- the answer says whether the input is one unit worth carding, or has units
  inside it
- when it is a unit: the card JSON, with `meanings` as "the senses that need
  different words in {target_lang}, most common first", each with its label, its
  translations, its examples, and for each example the highlighted and gapped
  strings
- when it is not: the units and the words worth learning, each with the context a
  tap will send. The current text prompt's "a single ordinary word never
  qualifies" goes, because the design asks for chips on words
- a set expression additionally returns the words it is made of, and the analysis
  explains what it is made of and why it means what it does. Four shipped rules
  block this and all four must move: "analyse it WHOLE. Never take it apart, and
  never analyse one of its words on its own"; "when the input was itself one
  unit, candidates holds that one unit and nothing else"; "the first is always
  identical to word"; and `card._candidates`, which drops a candidate equal to
  `analysed` and caps at `MAX_CANDIDATES`. Decide and record whether that cap
  applies to the parts of an expression
- on a card request, the context comes back as the same highlighted/gapped pair
- `context_sense` keeps its meaning

**`src/echo_words/card.py`.**

- `MAX_MEANINGS` stops rejecting an answer; keep a generous ceiling as a guard
  against a malformed list
- a malformed meaning is dropped and the card is built from the rest; only an
  answer with no usable meaning fails
- the highlighted and gapped strings are parsed as ordinary printed fields

## Step 2 — the router goes

**`src/echo_words/shape.py`.** `classify`, `Shape`, `MAX_UNIT_WORDS` and
`INTERNAL_MARKS` go; `word_count` stays, because `card.py` uses it.

**`src/echo_words/api.py`.** `WordSubmission`'s `shape` hint becomes the request
intent. **Do not name the field `kind`** — `JobKind` and `Job.kind` already mean
`submit` / `rebuild` / `switch`.

- a text request validates its input as text, since it may be either. A single
  typed word therefore no longer passes the canonical-word rule at the door; the
  headword the answer returns is validated as it already is, so what reaches a
  note is unchanged. Say so in the spec rather than letting it be noticed later
- a context on a text request is a 400
- `SubmissionFingerprint` carries the intent instead of the shape — a rename

**`src/echo_words/pipeline.py`.** `Job.shape` goes. `request_rebuild` and
`request_switch` re-enqueue without passing `shape` and rely on its default; both
must carry the intent forward, or rebuilding a chip-tap entry silently becomes a
text request. `detail_available` keys off `shape != "text"` and needs a new
condition — the answer's own verdict, which is known by then.

**`webapp/`.** `AddView.vue` sends the two intents; the chip carries its own
context field; `entry.shape` leaves the entry unless something else needs it.
`useResendQueue.js` replays stored bodies, so a body queued under the old field
names arrives after the change — accept both shapes for one release, or drop
unreadable queued bodies explicitly.

## Step 3 — the note type

**`src/echo_words/anki.py`.** The four template *names* stay; every `qfmt` and
`afmt` changes, and `tests/test_anki.py` pins them literally.

- delete `SENSE_FIELDS`, the `SenseRecall*` templates, `_sense_fronts`,
  `_word_pattern`, `_mask_word`, `_highlight_word`, `_context_gap` and
  `_context_front`
- a note is about one sense, so `Meanings` / `Translations` / `ContextMeaning` /
  `ContextTranslations` collapse into one translations block plus the label
- the fields become what the four cards read: the word, its audio, the label, the
  translations, the highlighted sentence and the gapped sentence
- the bare fronts are guarded by the translations and the sentence fronts by the
  sentence, so a note that arrived without a usable sentence is cards 1 and 2
- `render_meanings` and `render_translations` are exported and directly tested.
  `Note` carries the meanings list and the index of the one it is about — the
  pipeline builds chips from `parsed.note.meanings`, so the list has to survive

The note type changes shape, so `inv rebuild-note-type` is required before the
next deploy and the following AnkiWeb sync will demand a one-way full sync.

Verify empirically on a throwaway collection that a note generates exactly the
four cards — `anki==26.8.1` is a project dependency.

## Step 4 — what decides a note, and the chips

**`src/echo_words/pipeline.py`.** No card-set derivation is left. A note is made
unless one of these says otherwise:

- `job.lookup_only`
- the answer says the input is not one unit worth carding

and it is about the sense `context_sense` names, or the first sense otherwise.

`Note.narrowed_sense` returns `None` today when the answer holds one meaning, and
`_note_for` then rebuilds the note *without* the context — the `context_dropped`
machinery. Both go: the context is always kept, and the sense falls back to the
first rather than to no context.

Chips, by what the answer said:

- not a unit → the units and words found inside it
- a set expression → the words it is made of; `_candidate_segments` prepends
  `parsed.analysed`, which would otherwise put the expression itself first
- a single word, or any card request → every sense of the word

`segments_are_senses` is a boolean and there are now three sources with three
headings, so it becomes a kind. `add.segments` and `add.senses` need a third
sibling for the expression case in both `en.js` and `ru.js` — `i18n.test.js`
asserts key-set parity.

## Step 5 — the specs and the docs

- `spec/functional-description.md` — the two requests, the four cases, the four
  cards; the router is gone; the "named on the line above" sentence goes.
- `spec/decision-card-shapes.md` — rewritten around one note and four cards; add
  the payload-rejection numbers quoted under "Why"; drop the "named on the line
  above" sentence.
- `spec/decision-product.md` — one note per submission, and **amend "every recall
  front carries a gapped example"**: that is card 4 now, and card 2 is
  disambiguated by the label. Note the door-validation change from Step 2.
- `spec/decision-phrases-and-sentences.md` — the router it measured is deleted
  and the single-call alternative it rejected is adopted; the unit-offers-no-
  candidates rule is reversed; the sentence-mode negative control is re-opened by
  offering chips on ordinary words. Rewrite the status line and say plainly which
  numbers are now unbound.
- `spec/decision-answer-shape.md` — re-opened by a vocabulary-prompt revision, as
  its own "what would re-open this" says.
- `README.md`, `docs/src/en/index.md`, `docs/src/ru/index.md` — all three
  advertise "unrelated senses kept apart" and "a gapped example so the reverse
  card asks a real question"; both stop being true.
- `webapp/src/views/AddView.vue` — `CARD_KIND_KEYS` loses `SenseRecall1..3`;
  `card.kind.sense` and `card.contextNotNeeded` leave both catalogues.

## Tests

- `tests/test_card.py` — a malformed meaning is dropped; an answer with no usable
  meaning fails; a rich answer is not rejected by the ceiling; the highlighted and
  gapped strings parse and are rejected when empty or not strings
- `tests/test_anki.py` — a note generates exactly the four cards on a real
  throwaway collection; a separable verb's gapped front is
  `Er ___ jeden Morgen um sechs ___.` and its highlighted front marks both pieces;
  a note without a sentence generates cards 1 and 2; the label is on the bare
  fronts only when the answer holds several senses; the same word twice makes two
  notes
- `tests/test_pipeline.py` — a card request makes a note; `lookup_only` withholds
  it; an answer that says "not a unit" makes none and offers its units; a set
  expression makes one and offers its words; a single word offers every sense
- `tests/test_api.py` — nothing is classified; a context on a text request is a
  400; the fingerprint tells the intents apart
- `webapp/tests/AddView.test.js` — the two intents are sent as such; a chip
  submits its own context; the three chip headings

Delete rather than adapt every test pinning the router, the split, the
conditional card set, `context_dropped`, or the literal word search.

## Landing order

Step 0 first, and its outcome decides whether Step 2 exists at all.

Then `inv pre` and `inv test` green after each batch. Land Steps 1, 3 and 4
together with their tests — the contract, the note type and the derivation are
one change and cannot be green apart. Then Step 2, if Step 0 allowed it, moving
the API surface and the frontend together. Then Step 5.

## Verification

```
uv run inv pre     # every hook green, pyrefly 0 errors
uv run inv test    # pytest all passed, frontend suite passed not skipped
```

Then the measurements the new prompt owes. Step 0's gate is one of them and comes
first. Beyond it: the routing and sentence-mode arms of
`decision-phrases-and-sentences.md` and the sense gate of
`decision-card-shapes.md`, re-run against the prompt as it ends up. Every
prompt-bound number in those two documents and in `decision-answer-shape.md` is
unbound until then, and the specs must say so.

The merged prompt, if it happens, is also one larger prompt, and
`decision-llm-backend.md` records Serbian already straining on the free pool. Read
the Serbian numbers of every re-run arm specifically, rather than only the totals.
