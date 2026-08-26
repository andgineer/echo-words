# Implementation plan — one note per submission, four cards, senses as chips

Delete this file once the work has landed. What outlives it is
`spec/functional-description.md` and the sections it rewrites in
`spec/decision-card-shapes.md`, `spec/decision-product.md`,
`spec/decision-phrases-and-sentences.md` and `spec/decision-answer-shape.md`.

## Preconditions

The implementation baseline is commit `d6f3b68`. On it both gates are green: `inv pre` with
pyrefly at 0 errors, `inv test` at 460 pytest and 63 frontend tests, none
skipped.

Nothing is deployed from the two planning commits after `379931b`, so the note
type is still free to change shape. Land the final field set here rather than
rebuilding twice.

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
the status line naming the kinds and `lookup_only`.

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

### One prompt contract, one analysis path

Every model attempt for a submission uses the same prompt contract. There is no
punctuation or word-count router and no preliminary classification call. The
answer says whether the input is one lexical unit or text containing units: the
unit branch returns the dictionary article and card data; the text branch returns
the translated/explained text and its combinations. The existing cascade may
retry an unusable answer with another backend, but it does not change this
contract or make a separate routing call.

A single typed word is a unit by definition and gets unit intent without a
classifier. A chip tap also carries explicit unit intent, so a selected word or
combination is analysed as the chosen unit rather than classified again. For an
ordinary multi-word submit-box request the model's result is authoritative:
`unit` makes a note and `text` does not.

### The submit box and a chip tap

- **The submit box** sends exactly what the user typed with no shape hint. A
  single word takes the known unit branch; the model classifies a multi-word
  input inside the same call that writes the answer.
- **A chip tap** sends a word or combination, its context, and the explicit unit
  intent. The word is already chosen, and no card-set derivation may withhold the
  note — but `lookup_only` still does, because that is the reader saying they
  want no note at all.

The `word` of a card request may be a combination, when that combination is one
unit in that text — a German separable prefix stranded at the clause end is still
part of its verb.

A chip carries the context it will send: a chip under a running text carries that
text, a chip under a sense list carries that sense's example sentence, and a word
chip under a set expression carries the first example sentence of the
expression's carded sense. The last must not carry the bare expression: cards 3
and 4 require a sentence. The chip carries context as its own field rather than
having the frontend reconstruct it from `entry`.

### What each case produces

| what arrived | article in the PWA | Anki note | chips |
|---|---|---|---|
| one word | every sense | the most common sense | every sense |
| set expression | its meaning, and what it is made of and why it means that | the expression itself | the words of the expression |
| anything with units inside it | the text rendered and explained | **none** | every word, with the words belonging to a combination replaced by that combination |
| word + context | the sense used in the context, the other senses below it | that sense | every sense |

The first three rows begin at the submit box; the last begins with a chip tap. In
the article the context's sense comes first and the others follow, in whatever
order the model chooses.

The vocabulary article remains the full PWA dictionary article: headword and
translations, useful morphology, usage, origin and examples. The smaller payload
below exists only to build the note and its chips; it does not replace or shorten
the article shown in the application.

For a single word and a card request, **chips are offered for every sense,
including the one the note was just made for.** `_sense_segments` excludes the
carded sense today and must stop; the `add.senses` string, which says "this word
has *other* senses", is re-worded in both catalogues. A set expression uses its
chip row for its component words instead, as the table specifies.

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

The first is card 3's front, the second is card 4's. The backend does not invent
either string with literal replacement and does not try to prove the model's
linguistic work character by character. It checks only that both are bounded,
non-empty strings, sanitizes the allowed HTML, and requires a highlight in one
and a blank marker in the other. A missing field cannot make a sentence card; a
minor difference in punctuation, spacing, inflection or word order does not make
the whole meaning disappear.

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

## Step 0 — measure the unit verdict before merging the prompts

This completed experiment quantifies the cost of trusting the merged answer's
kind. Its zero-error gate was deliberately stricter than the product's eventual
trust boundary; the recorded result below is the decision used by this plan.

### Result — 2026-08-26

The pre-registered zero-error gate did not pass. It required zero expensive
false positives, zero article/verdict contradictions, zero `context_sense`
fields without a context, and at least 95% of real units to be carded directly
or recovered as the first chip. All 122 fixtures produced a usable answer under
the neutral schema:

- 1 of 57 sentences, clauses or fragments was flagged as a unit:
  `völlig durcheinander gebracht`
- 4 of 65 units were flagged as not units, and none was recovered as the first
  chip: `возим бицикл`, `донео одлуку`, `steht zur Verfügung`, `ide pešice`
- 3 of 122 articles contradicted their JSON verdict
- no answer leaked `context_sense`

Replacing the literal `true` removed neither class of problem. A second wording
made the safe direction explicit and required first-chip recovery. On the 13
regression inputs it removed the expensive false positive, but split three real
inflected units into their component words and contradicted its verdict once.
It therefore failed that deliberately strict gate.

The product accepts the measured trade-off rather than restoring a surface
router that cannot answer the question either. The one false unit verdict in 57
text-like inputs is visible and undoable. A real unit returned as text is not
lost under the final text contract: the backend offers every source word and any
combination the model found, so the reader can recover it by tapping. The later
41-answer flow bench confirmed that this downstream path keeps all words and
does not turn harmless schema or surface variation into a missing result.

**The prompts therefore merge and `shape.classify` is deleted.** The model's
verdict is trusted like its translations and morphology; the backend enforces
only the structural and safety conditions needed to render the answer and build
the note. Article/verdict disagreement is recorded by the benchmark, not used as
a second hidden classifier.

The reproducible harness and prompt deltas are
`experiments/unit_verdict_bench.py` and
`experiments/unit_verdict_prompts.py`. Raw answers remain in the gitignored
`experiments/.bench-unit-verdict/` and can be re-scored without another call.
The prompt-bound routing, answer-shape and sense numbers are replaced once by the
final merged-prompt run described under Verification.

## Step 1 — one prompt and one contract

**`src/echo_words/prompt.py`.** Merge `_PROMPT` and `_TEXT_PROMPT`. The JSON has a
neutral `kind` discriminator, `unit` or `text`; neither value appears as the
literal preferred example. The visible article and remaining fields follow that
kind:

- `unit` returns the full dictionary article plus `word`, `suggestion`,
  `meanings`, optional `context_sense`, and component `segments`. `meanings` are
  "the senses that need different words in {target_lang}, most common first";
  each has its label, translations, examples, and finished highlighted and
  gapped forms. `word` is the dictionary form of the submitted unit but retains
  the spelling the user sent: an orthographic correction appears only in
  `suggestion`, never silently in `word`
- `text` returns the translated and explained text plus only the multi-word
  lexical `combinations` it found. Each combination carries surface-word hints,
  a short reason and an internal dictionary label. It returns no word, meanings
  or other card fields
- an explicit unit intent from a chip requires the unit branch. A submit-box
  request has no intent and the model chooses the branch. A single source word is
  defined as a unit in the prompt

For text, the internal label is a semantic hint, not a second verdict that the
backend uses to overrule the model, and is never shown on the chip. The model
does not enumerate ordinary words. The backend best-effort matches surface words
against unclaimed source words without requiring the model's order, contiguity,
capitalization or ellipsis placement to be exact. It then uses the matched source
forms in their real source order for the visible chip. A combination is retained
when at least two of its surface words can be identified; an unmatched fragment
is ignored without rejecting the answer or any other combination. The first
returned combination claims an occurrence when proposals overlap. Repeated
surface words match the earliest still-unclaimed occurrence, which is the only
deterministic rule available without indices. Every still-unclaimed source word
becomes its own chip, so completeness does not depend on the model deciding which
ordinary words matter.

A text chip label keeps the exact inflected forms seen in the text; separated
parts are joined for the label but are not converted to a dictionary form. A tap
sends that visible label plus the submitted text. The unit answer then supplies
the validated dictionary headword printed in the article and used by the note.
The backend attaches the submitted text as context and sorts all chips by their
first source occurrence. No source indices, chip labels, echoed context or
standalone words enter the model contract. Repeated occurrences remain separate
targets rather than being deduplicated by their label.

- the prompt does not replace five with another numerical limit. It asks for
  every unit that clearly satisfies the conservative qualification, says not to
  pad the list, and makes an empty list explicitly correct. The backend already
  supplies the bound: every accepted combination contains at least two source
  words and accepted combinations cannot overlap, so a text of `N` words can
  contain at most `floor(N / 2)` of them without the model counting anything
- a set expression additionally returns the words it is made of, and the analysis
  explains what it is made of and why it means what it does. Delete `candidates`,
  `MAX_CANDIDATES`, `_candidates`, `ParsedCard.input_is_unit` and the four prompt
  rules that make the whole input its only candidate. Component `segments`
  include every word-shaped part without filtering by grammatical category;
  particles and prepositions are examples, not an exhaustive allowlist. They
  preserve the forms seen in the submitted expression and have no count cap
  beyond the bounded answer itself. Every component carries the first example
  sentence of the expression's carded sense as its tap context
- on a card request, the context comes back as the same highlighted/gapped pair
- `context_sense` keeps its meaning

**`src/echo_words/segments.py`.** Remove `MAX_SEGMENTS` and the early break at
five. Do not replace them with another product cap. Parsing accepts every
bounded combination object and normalizes harmless schema variation. Matching
is case-insensitive and order-independent; it maps the model's words back to the
actual source occurrences and derives the printed label there. A bad internal
lookup hint is discarded as metadata while a surface-matched combination stays;
one unmatchable combination is ignored without rejecting the other combinations
or the answer. Payload-size limits, JSON types and HTML sanitization remain
security and resource guards. Do not deduplicate equal visible labels because
repeated occurrences are separate chips.

`Segment` gains its own `context`; text fill, expression components and sense
chips all populate it explicitly. `parse_segments_payload` accepts the text
branch's `combinations` key. The unit payload's component `segments` are parsed
with the card rather than mistaken for a separate text payload.

The full-word guarantee is backend work, not a broader LLM enumeration prompt.
The existing production definition of a learnable combination remains the
baseline. A replacement combination prompt must re-pass the sentence benchmark;
the report records both recovered expected units and extra optional chips, but
does not pretend the backend can adjudicate the latter more accurately than the
model.

### No-cap, full-word and four-card bench — 2026-08-26

The downstream-branch harness is `experiments/one_note_bench.py`; the text and
unit branch prompts used to isolate those behaviours are under
`experiments/prompts/`. It assigns its fixtures to a known branch and therefore
does not measure the verdict; Step 0 is the separate verdict measurement. A
fresh run in
`experiments/.bench-one-note-final/` made 41 real free-pool calls: 26 texts, nine
bare vocabulary inputs and six chip taps. Twenty-one answers came from
`google-gemini-3.5-flash-lite` and 20 from `groq-gpt-oss-120b`. Four chip calls
that initially met a pool cooldown were retried alone with the same prompt; no
successful answer from an earlier prompt or run was reused.

The text prompt in this run had no numerical limit. It asked for every clearly
qualifying combination, explicitly allowed an empty list, and told the model not
to pad it. The recorded answers were then processed as the implemented design
would process them: reject an unusable or overlapping combination, derive the
visible label from matched source forms, attach the submitted text as context,
and add every unclaimed source word in source order.

That deterministic part worked. It produced chips for all 178 of 178 source
words, including all 53 of 53 function-word controls. All final labels used the
visible forms rather than lemmas, all contexts were backend-owned, and all text
answers remained note-free. Removing five as both a prompt instruction and a
parser cap therefore stays in the plan; it needs no replacement number.

Scoring the same recorded answers with the tolerant normalization above found all
21 of 21 expected lexical units. Nineteen of 21 contained every registered source
part; in the other two the model still identified the useful core and the omitted
pronoun stayed available as its own chip: `uns | auf beschränken` and
`mi | se čini`. All 26 text answers remained usable and no source word was lost.
`unter die Lupe nehmen`, `se oblači`, `nadam se` and `čini se` were recovered
despite reordered, separated or differently capitalized surface text.

Only three of six texts with no multi-word lookup target stayed empty. The extra
chips were `hat … angerufen`, `richtig schön`, and `went outside`. This is the
chosen trust boundary: the backend does not possess a better lexical judgement
than the model and therefore does not silently delete a coherent proposed unit.
A false-positive chip costs an optional tap; rejecting a real combination makes
the useful lookup unavailable. None of these results was related to counting:
every text contained at most two proposed combinations, so removal of the
five-item limit stands without a replacement limit.

The vocabulary and click payloads looked stronger structurally than they were
pedagogically. After normalizing singular `translation` to `translations` and a
single string to a one-item list, all 15 retained every meaning and supplied four
non-empty card fronts. All 15 contained usage and origin; all ten cases selected
as requiring morphology contained a forms section; and every one of the six
clicks returned its context as the first example with every clicked part
highlighted. The `bank` river meaning is therefore retained rather than turning
one harmless key variation into a missing chip.

Manual review found clear learner-facing errors which the structural scores did
not detect:

- `Vorschlag` was translated as “sentence” rather than “proposal”; the note on
  `look forward to` called Russian genitive `поездки` instrumental
- German `Bank` was marked neuter and omitted the distinct plural `Bänke`; the
  Serbian plural of `град` was given as `гради` instead of `градови`
- `уморан` used the malformed first card example `Након дуге шете ...` and gave
  invented or misleading usage; `водити рачуна` claimed an ungrammatical
  prepositionless genitive construction
- a click on German `Er` supplied `seine` as a case form and claimed that `er`
  is used impersonally for weather; a click on Serbian `Он` supplied Russian
  forms such as `Него` and `Нему` instead of Serbian `њега` and `њему`
- clicks on `gave up` and `се вратио` left the inflected chip text in `word`
  instead of returning the promised dictionary headword; the latter also made
  an ungrammatical generated example part of the sense chip
- `aufstehen` included “wake up” among its translations and described
  `steht auf dem Feld` as another inseparable verb, both of which are wrong

These are visible in the full PWA article, and several also enter a card front or
the first example used for cards 3 and 4. They are model-quality errors, not
schema failures that deterministic code can safely correct. The backend keeps
the answer unless it is unusable or unsafe; it does not turn a mostly useful
answer into no article, no sense or no combination while trying to verify
linguistics itself. The bench therefore passes the post-plan structural flow,
with the qualitative examples retained as evidence of the model boundary rather
than as a backend rejection gate.

**`src/echo_words/card.py`.**

- replace `ParsedCard` plus the separate segment payload with a parsed-answer
  union keyed by `kind`. A text answer cannot expose a note; a unit answer cannot
  expose text combinations. Delete `word_count` and `input_is_unit`
- the unit answer's validated `word` is the dictionary headword used by `Note`,
  Anki, card audio and sense-chip submissions. The raw submission remains the
  history entry and prompt input; `suggestion` remains the only spelling-
  correction control. An unusable returned headword makes the unit payload
  unusable rather than silently putting the raw inflected chip label on a card
- `MAX_MEANINGS` stops rejecting an answer. The whole-answer character bound is
  already the resource guard; do not add another arbitrary sense-count cap
- normalize harmless schema variation before deciding that data is missing:
  singular `translation` aliases `translations`, and a single translation or
  example object is wrapped as a one-item list
- after normalization, a meaning with no usable translation or example is
  dropped and the card is built from the rest. A usable example includes its
  non-empty highlighted and gapped strings, so every accepted note can make all
  four cards; an answer with no usable meaning fails
- dropping meanings remaps `context_sense` from the raw list to the retained
  list. If the named meaning was dropped or the index was unusable, the first
  retained meaning is carded
- highlighted and gapped strings are parsed as ordinary printed fields. They are
  sanitized and checked for a highlight/blank marker, not compared with the
  source character by character

## Step 2 — remove the surface router

**`src/echo_words/shape.py`.** Delete `Shape`, `classify`, `word_count`,
`MAX_UNIT_WORDS` and `INTERNAL_MARKS`; delete `tests/test_shape.py` and its test
taxonomy entry. No surface-classification copy remains anywhere.

**`src/echo_words/api.py`.** `WordSubmission.shape` becomes an optional request
intent rather than a classification result. The submit box omits it and is
validated with the running-text bounds, which also accept a word; the server
promotes exactly one word to known unit intent without recreating a multi-word
classifier. A chip sends `shape: "unit"` and is validated as a unit. The request
type is therefore `Literal["unit"] | None`, not the deleted `Shape`. Do not
accept a client-forced text result: absent on a multi-word input means the model
decides, and the parsed answer supplies the entry's eventual `unit`/`text` kind.
Request-id fingerprints include the effective intent.

**`src/echo_words/pipeline.py`.** Build and stream the one prompt for every
submission. The parser's answer kind, not punctuation, selects the text-fill or
note path. A unit-intent response that claims to be text is an unusable payload
and takes the ordinary paid fallback; it is not silently accepted as a different
operation.

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
- `render_meanings` and `render_translations` are exported and directly tested.
  `Note` carries the retained meanings list and the index of the one it is about;
  the templates render only that sense, while the pipeline builds chips from the
  whole list

Every accepted note fills all six fields needed by all four templates and must
generate exactly all four cards. Missing sentence data is a malformed meaning or
answer handled before Anki, never a two-card note type variant.

The note type changes shape, so `inv rebuild-note-type` is required before the
next deploy and the following AnkiWeb sync will demand a one-way full sync.

Verify empirically on a throwaway collection that a note generates exactly the
four cards — `anki==26.8.1` is a project dependency.

## Step 4 — what decides a note, and the chips

**`src/echo_words/pipeline.py`.** No card-set derivation is left. A note is made
unless one of these says otherwise:

- `job.lookup_only`
- the parsed answer has `kind: "text"`

and it is about the sense `context_sense` names, or the first sense otherwise.

`Note.narrowed_sense` returns `None` today when the answer holds one meaning, and
`_note_for` then rebuilds the note *without* the context — the `context_dropped`
machinery. Both go: the context is always kept, and the sense falls back to the
first rather than to no context.

Chips, by what the answer said:

- a text answer → every word in source order; the parts of a lexical combination
  are replaced by one chip for that combination. Its label uses the same forms
  the learner just saw, not a lemma; a tap sends that label plus the whole text
  with unit intent, whose answer supplies the dictionary headword
- a set expression → the component `segments` returned by its unit answer, never
  the whole expression prepended as its own component
- a single word, or any card request → every sense of the word

The entry's public `shape` becomes `AnswerKind | None` and is populated from the
parsed answer kind, not the request intent. `segments_are_senses` becomes a
three-valued segment kind for text words/combinations, expression components and
senses. Add the corresponding history field and event payload; serialize each
segment's own `context` through both, and have `AddView.vue` submit that field
directly instead of reconstructing context from the entry shape or surface.
Remove `context_dropped` from `Entry`, `StoreResult`, events and the frontend.
Update `useEntries.js` and `useEventStream.js` for the nullable answer kind,
segment kind and segment context. `add.segments` and `add.senses` need a third
sibling for the expression case in both `en.js` and `ru.js`; `i18n.test.js`
asserts key-set parity.

Pending entries have no result shape yet. Detail and rebuild availability, the
text/no-card status, and frontend controls are set after parsing from the answer
kind; replace every current `job.shape` branch rather than leaving a second
implicit router in those paths.

Rebuild and spelling-switch jobs exist only for a successfully parsed unit entry
and always carry explicit unit intent; they do not ask the model to classify the
same multi-word unit again. Detail lookup likewise uses the stored unit headword
and context. Text entries expose none of these controls.

Audio for a prospective unit cannot be finalized from the raw chip label before
the model returns its dictionary headword. The submitted text can still be
voiced for the PWA while the model runs. Reuse that audio when it equals
`Note.word`; otherwise fetch card audio for the validated headword after parsing.
Keep the two paths distinct when they differ: `Entry.audio_file` continues to
voice exactly what was submitted in the PWA, while the separate path passed to
Anki voices `Note.word`. A context chip may therefore have submitted-unit audio,
context audio and different card media without exposing another player.
Rebuild reuses audio only while the rebuilt `Note.word` is unchanged and fetches
new audio when it changes; correction already fetches anew. Control state retains
the carded headword so replacement note and audio stay aligned. Undo still acts
by stored note id and needs no word inference.

The four surviving template names need four distinct localized status labels.
Do not map both context templates to one repeated “context” label when all four
are reported.

Text targets stay compact chips in this change. Rendering the submitted text
itself as individually clickable words, including a visual treatment for
non-contiguous combinations, is a future interface improvement. A future
per-language setting may hide function-word chips for an experienced learner;
the default here is all words because the beginner cannot safely pre-filter
them.

## Step 5 — the specs and the docs

- `spec/functional-description.md` — the model-decided text and unit flows, the
  four cases, all-word text chips and the four unconditional cards; the surface
  router, conditional card catalogue and "named on the line above" text go. It
  must distinguish raw submitted text from the validated dictionary headword
  used by a unit note and its audio, preserve advisory-only spelling correction,
  and make detail/rebuild/switch reuse the stored unit identity and unit intent
- `spec/decision-card-shapes.md` — rewritten around one note and four cards; add
  the payload-rejection numbers quoted under "Why"; drop the conditional
  catalogue and the "named on the line above" sentence
- `spec/decision-product.md` — one note per submission; replace the raw-input-as-
  canonical-word rule with the validated unit answer's dictionary headword while
  keeping `suggestion` advisory; and **amend "every recall front carries a gapped
  example"**: that is card 4 now, and card 2 is disambiguated by the label. A
  rebuild reuses audio only when the returned headword is unchanged
- `spec/decision-phrases-and-sentences.md` — record Step 0's rejection of the
  zero-error gate and the accepted product trade-off; delete the surface router;
  record the one-prompt verdict and recovery through all-word text chips. Rewrite
  the status line and say plainly which prompt-bound numbers the final rerun
  replaces
- `spec/decision-answer-shape.md` — re-opened by a vocabulary-prompt revision, as
  its own "what would re-open this" says.
- `spec/decision-llm-backend.md` — update only measurements invalidated by the
  merged prompt, including the Serbian slice; do not reopen the selected backend
  kinds or deployment routing
- `README.md`, `docs/src/en/index.md`, `docs/src/ru/index.md` — describe one
  selected sense reviewed through four stimuli, with every sense available as a
  chip, rather than the conditional catalogue. Preserve the true claims that
  unrelated senses stay distinguishable and a gapped sentence asks production
  in context. Remove any remaining claim that the compact answer names a part of
  speech, which already contradicts `decision-answer-shape.md`
- `webapp/src/views/AddView.vue` — `CARD_KIND_KEYS` loses `SenseRecall1..3`;
  `card.kind.sense` and `card.contextNotNeeded` leave both catalogues.

## Tests

- `tests/test_prompt.py` — one prompt carries both neutral branches; submit-box
  and explicit-unit instructions differ only by intent; no numerical combination
  cap remains; the unit article still requires morphology when useful, usage,
  origin and examples; dictionary-form normalization cannot silently apply a
  spelling suggestion
- `tests/test_card.py` — the answer-kind union rejects mixed branches; singular
  keys and singleton values normalize; a meaning still missing usable content is
  dropped; `context_sense` is remapped after drops; an answer with no usable
  meaning fails; no sense-count ceiling rejects a bounded answer; highlighted
  and gapped strings parse without equality checks and are rejected only when
  empty or not strings; a validated returned lemma becomes `Note.word`
- `tests/test_segments.py` — reordered, separated and differently capitalized
  surface words map back to their source occurrences; one unmatchable proposal
  does not reject the other combinations or prevent standalone-word fill; no
  arbitrary count limit remains; repeated words use distinct earliest-unclaimed
  occurrences and the first overlapping proposal wins; every segment carries its
  own context
- `tests/test_anki.py` — a note generates exactly the four cards on a real
  throwaway collection; a separable verb's gapped front is
  `Er ___ jeden Morgen um sechs ___.` and its highlighted front marks both pieces;
  the label is on the bare fronts only when the answer holds several senses; the
  same word twice makes two notes; no accepted note produces fewer than four
  cards
- `tests/test_pipeline.py` — a model `unit` answer makes a note; `lookup_only`
  withholds it; a model `text` answer makes none and offers every source word; a
  set expression makes one and offers its words; a single word and a card request
  offer every sense; unit intent refuses a text-kind payload; audio uses the
  returned dictionary headword without replacing the PWA's submitted-text audio;
  rebuild and spelling switch retain unit intent and the resulting headword
- `tests/test_api.py` — no classifier is called; an ordinary submission has no
  client intent and accepts text bounds; exactly one word is promoted to unit
  intent; a multi-word submit remains undecided; a chip carries unit intent and
  unit validation; request-id conflicts distinguish intent
- `tests/test_history.py` and event assertions — parsed answer kind and segment
  kind are public; `context_dropped` and `segments_are_senses` are absent
- `webapp/tests/AddView.test.js` — a chip submits its own context; the three chip
  headings; all four card kinds have distinct status labels

Delete rather than adapt every test pinning the per-sense split, the conditional
card set, `context_dropped`, or the literal word search.

## Landing order

Step 0 is complete; its accepted outcome requires Step 2.

Then `inv pre` and `inv test` green after each batch. Land Steps 1, 3 and 4
together with Step 2, their tests and the source-of-truth spec changes in Step 5
— the prompt, verdict, note identity, note type and derivation are one behaviour
and cannot be green apart. User-facing README/docs wording may be the final
batch, but no code commit may knowingly contradict `functional-description.md`.

## Verification

```
uv run inv pre     # every hook green, pyrefly 0 errors
uv run inv test    # pytest all passed, frontend suite passed not skipped
```

Then run the measurements the merged prompt owes, including the Step 0 verdict
matrix. Before running, change `experiments/one_note_bench.py` to import the
production prompt builder and production parsers/fill functions rather than keep
a second implementation. Add undecided submit-box fixtures to its existing
known-branch and click fixtures, so one report scores both the model verdict and
the already-proven downstream flow. Assert that the branch prompts under
`experiments/prompts/` have either been removed or are byte-for-byte fixtures of
the production branches; prompt drift must fail loudly.

Run a fresh directory because the merged production prompt has changed:

```
uv run python experiments/one_note_bench.py run \
  --wait 180 --pace 2 --concurrency 3 \
  --out experiments/.bench-one-note-post
uv run python experiments/one_note_bench.py run-clicks --resume \
  --wait 300 --pace 2 --concurrency 1 \
  --out experiments/.bench-one-note-post
uv run python experiments/one_note_bench.py report \
  --out experiments/.bench-one-note-post
```

The report must retain the existing structural checks — all source words and
function words offered, 21 registered lexical units detected, every retained
meaning cardable, four cards ready, and exact click contexts — and add the Step 0
verdict confusion matrix. Extra optional chips and article/verdict disagreements
are reported rather than treated as a hidden backend veto. The routing and
sentence-mode arms of `decision-phrases-and-sentences.md`, the sense gate of
`decision-card-shapes.md`, and the affected answer-shape measurements are all
replaced by this final-prompt run.

Read the Serbian numbers of every re-run arm specifically, rather than only the
totals: `decision-llm-backend.md` records Serbian already straining on the free
pool.
