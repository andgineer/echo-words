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

### Two prompts, one call per submission

Every submission is one streamed call. The existing surface router chooses the
vocabulary prompt or the running-text prompt before that call. A vocabulary
answer makes a note; a running-text answer does not.

The vocabulary prompt returns the card and the running-text prompt returns the
units and words found inside the text. The model is not trusted with the decision
that touches the deck: Step 0 measured that verdict and rejected it.

A single typed word always routes to the vocabulary prompt. A chip tap explicitly
sends `shape: "unit"`, so its selected word or combination cannot be re-routed by
its own surface shape.

### The submit box and a chip tap

- **The submit box** sends exactly what the user typed with no shape hint. The
  backend classifies it as it does today.
- **A chip tap** sends a word or combination, its context, and the explicit unit
  shape. The word is already chosen, and no card-set derivation may withhold the
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

### Result — 2026-08-26

**The verdict did not pass, so the prompts do not merge and the router stays.**
The pre-registered gate required zero expensive false positives, zero
article/verdict contradictions, zero `context_sense` fields without a context,
and at least 95% of real units to be carded directly or recovered as the first
chip. All 122 fixtures produced a usable answer under the neutral schema:

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
It therefore failed before a full re-run was warranted.

The reproducible harness and prompt deltas are
`experiments/unit_verdict_bench.py` and
`experiments/unit_verdict_prompts.py`. Raw answers remain in the gitignored
`experiments/.bench-unit-verdict/` and can be re-scored without another call.

## Step 1 — revise both prompts and their contracts

**`src/echo_words/prompt.py`.** Keep `_PROMPT` and `_TEXT_PROMPT` separate.

- `_PROMPT` keeps returning a card JSON, with `meanings` as "the senses that need
  different words in {target_lang}, most common first", each with its label, its
  translations, its examples, and for each example the highlighted and gapped
  strings
- `_TEXT_PROMPT` keeps returning no card and returns only the multi-word lexical
  combinations it found, each as surface-word hints plus a short reason and an
  internal dictionary label. The label is a semantic hint, not a second verdict
  that the backend uses to overrule the model. It is never shown on the chip.
  The prompt does not enumerate ordinary words. The backend best-effort matches
  surface words against unclaimed source words without requiring the model's
  order, contiguity, capitalization or ellipsis placement to be exact. It then
  uses the matched source forms in their real source order for the visible chip.
  A combination is retained when at least two of its surface words can be
  identified; an unmatched fragment is ignored without rejecting the answer or
  any other combination. Overlap is resolved deterministically because one
  source occurrence can belong to only one visible chip. Every still-unclaimed
  source word becomes its own chip. Completeness therefore does not
  depend on a list of parts of speech or on the
  model deciding which ordinary words matter. A chip label keeps the exact
  inflected forms seen in the text; separated parts are joined for the label but
  are not converted to a dictionary form. The vocabulary prompt still derives
  and prints the authoritative dictionary
  headword only after the chip is tapped. The backend also attaches the submitted
  text as context and sorts all chips by their first source occurrence. No source
  indices, chip labels, echoed context or standalone words enter the model
  contract. The five-item cap goes, and repeated surface words remain separate
  targets rather than being deduplicated by their label
- the prompt does not replace five with another numerical limit. It asks for
  every unit that clearly satisfies the conservative qualification, says not to
  pad the list, and makes an empty list explicitly correct. The backend already
  supplies the bound: every accepted combination contains at least two source
  words and accepted combinations cannot overlap, so a text of `N` words can
  contain at most `floor(N / 2)` of them without the model counting anything
- a set expression additionally returns the words it is made of, and the analysis
  explains what it is made of and why it means what it does. Four shipped rules
  block this and all four must move: "analyse it WHOLE. Never take it apart, and
  never analyse one of its words on its own"; "when the input was itself one
  unit, candidates holds that one unit and nothing else"; "the first is always
  identical to word"; and `card._candidates`, which drops a candidate equal to
  `analysed` and caps at `MAX_CANDIDATES`. Decide and record whether that cap
  applies to the parts of an expression. Every part carries the first example
  sentence of the expression's carded sense as its tap context
- on a card request, the context comes back as the same highlighted/gapped pair
- `context_sense` keeps its meaning

**`src/echo_words/segments.py`.** Remove `MAX_SEGMENTS` and the early break at
five. Do not replace them with another product cap. Parsing accepts every
bounded combination object and normalizes harmless schema variation. Matching
is case-insensitive and order-independent; it maps the model's words back to the
actual source occurrences and derives the printed label there. A bad internal
lookup hint or one unmatchable combination is local damage, not a reason to
reject the other combinations or the answer. Payload-size limits, JSON types and
HTML sanitization remain security and resource guards. Do not deduplicate equal
visible labels because repeated occurrences are separate chips.

The full-word guarantee is backend work, not a broader LLM enumeration prompt.
The existing production definition of a learnable combination remains the
baseline. A replacement combination prompt must re-pass the sentence benchmark;
the report records both recovered expected units and extra optional chips, but
does not pretend the backend can adjudicate the latter more accurately than the
model.

### No-cap, full-word and four-card bench — 2026-08-26

The end-to-end harness is `experiments/one_note_bench.py`; its future text and
vocabulary prompts are under `experiments/prompts/`. A fresh run in
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

- `MAX_MEANINGS` stops rejecting an answer; keep a generous ceiling as a guard
  against a malformed list
- normalize harmless schema variation before deciding that data is missing:
  singular `translation` aliases `translations`, and a single translation or
  example object is wrapped as a one-item list
- after normalization, a meaning with no usable translation or example is
  dropped and the card is built from the rest; only an answer with no usable
  meaning fails
- the highlighted and gapped strings are parsed as ordinary printed fields

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
- `job.shape == "text"`

and it is about the sense `context_sense` names, or the first sense otherwise.

`Note.narrowed_sense` returns `None` today when the answer holds one meaning, and
`_note_for` then rebuilds the note *without* the context — the `context_dropped`
machinery. Both go: the context is always kept, and the sense falls back to the
first rather than to no context.

Chips, by what the answer said:

- a text answer → every word in source order; the parts of a lexical combination
  are replaced by one chip for that combination. Its label uses the same forms
  the learner just saw, not a lemma; a tap sends that label plus the whole text
  to the vocabulary prompt, whose answer supplies the dictionary headword
- a set expression → the words it is made of; `_candidate_segments` prepends
  `parsed.analysed`, which would otherwise put the expression itself first
- a single word, or any card request → every sense of the word

`segments_are_senses` is a boolean and there are now three sources with three
headings, so it becomes a kind. `add.segments` and `add.senses` need a third
sibling for the expression case in both `en.js` and `ru.js` — `i18n.test.js`
asserts key-set parity.

Text targets stay compact chips in this change. Rendering the submitted text
itself as individually clickable words, including a visual treatment for
non-contiguous combinations, is a future interface improvement. A future
per-language setting may hide function-word chips for an experienced learner;
the default here is all words because the beginner cannot safely pre-filter
them.

## Step 5 — the specs and the docs

- `spec/functional-description.md` — the routed text and card flows, the four
  cases, the four cards; the "named on the line above" sentence goes.
- `spec/decision-card-shapes.md` — rewritten around one note and four cards; add
  the payload-rejection numbers quoted under "Why"; drop the "named on the line
  above" sentence.
- `spec/decision-product.md` — one note per submission, and **amend "every recall
  front carries a gapped example"**: that is card 4 now, and card 2 is
  disambiguated by the label.
- `spec/decision-phrases-and-sentences.md` — record Step 0's rejection of the
  merged prompt; the router stays; the unit-offers-no-candidates rule is reversed;
  the sentence-mode negative control is re-opened by offering chips on ordinary
  words. Rewrite the status line and say plainly which numbers are now unbound.
- `spec/decision-answer-shape.md` — re-opened by a vocabulary-prompt revision, as
  its own "what would re-open this" says.
- `README.md`, `docs/src/en/index.md`, `docs/src/ru/index.md` — all three
  advertise "unrelated senses kept apart" and "a gapped example so the reverse
  card asks a real question"; both stop being true.
- `webapp/src/views/AddView.vue` — `CARD_KIND_KEYS` loses `SenseRecall1..3`;
  `card.kind.sense` and `card.contextNotNeeded` leave both catalogues.

## Tests

- `tests/test_card.py` — singular keys and singleton values normalize; a meaning
  still missing usable content is dropped; an answer with no usable meaning
  fails; a rich answer is not rejected by the ceiling; highlighted and gapped
  strings parse without equality checks and are rejected only when empty or not
  strings
- `tests/test_segments.py` — reordered, separated and differently capitalized
  surface words map back to their source occurrences; one unmatchable proposal
  does not reject the other combinations or prevent standalone-word fill; no
  arbitrary count limit remains
- `tests/test_anki.py` — a note generates exactly the four cards on a real
  throwaway collection; a separable verb's gapped front is
  `Er ___ jeden Morgen um sechs ___.` and its highlighted front marks both pieces;
  a note without a sentence generates cards 1 and 2; the label is on the bare
  fronts only when the answer holds several senses; the same word twice makes two
  notes
- `tests/test_pipeline.py` — a unit-routed request makes a note; `lookup_only`
  withholds it; a text-routed request makes none and offers its units; a set
  expression makes one and offers its words; a single word offers every sense
- `tests/test_api.py` — the router remains pinned; an explicit unit chip is not
  reclassified
- `webapp/tests/AddView.test.js` — a chip submits its own context; the three chip
  headings

Delete rather than adapt every test pinning the per-sense split, the conditional
card set, `context_dropped`, or the literal word search.

## Landing order

Step 0 first; its outcome removed Step 2 from this plan.

Then `inv pre` and `inv test` green after each batch. Land Steps 1, 3 and 4
together with their tests — the contracts, the note type and the derivation are
one change and cannot be green apart. Then Step 5.

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

Read the Serbian numbers of every re-run arm specifically, rather than only the
totals: `decision-llm-backend.md` records Serbian already straining on the free
pool.
