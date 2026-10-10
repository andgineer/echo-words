# Plan: reverse translation

**Status (2026-10-10):** steps 1–3 built, and the routing redesigned by the operator.
The reverse prompt and its parser are in the code and asked by nothing yet; the prompt
was benched four times on the pool and reviewed by a fresh agent each time, and the
result is in `spec/decision-reverse-translation.md`: English and German carry it as
measured, Serbian is asked in Latin letters with its chips, and a Serbian answer in
Cyrillic is read as written. The letter tests that step 1 built are gone: no code reads
a word's letters to guess its language. Alphabets decide only where the tab's and the
target's cannot be confused; where they overlap, a model reads the input (rules 2–3),
and its reading prompt is being measured (`experiments/reading_bench.py`). Open with the
operator: acceptance of the faults the decision spec lists. Next is step 4.

## What the reader gets

On the English tab the reader types `стол` and gets the card for *table* in
«EchoWords: English», exactly as if they had typed `table`. The selected language
still chooses the deck and the language translated into; the typed word is in the
**target language** (`ECHOWORDS_TARGET_LANG`, Russian by default). Nothing below is
Russian-specific: the rules read each language's alphabet and ask a model where two
alphabets overlap, so they work for any target.

Once the word is resolved, the entry *is* the entry a tap on a chip for *table* would
make: its rail label, card, audio, controls and messages are all about *table*. Only
its header says «стол → table». Every later run of the entry — retry, rebuild,
switch, the deeper article — starts from *table* and keeps the other equivalents as
its chips.

## Rules (agreed)

Notation: S = the selected language, T = the target language.

1. **A leading `!` forces reverse translation, with no check of any kind** — no
   letter or script test, whatever T is: `!ねこ` with a Japanese target takes the same
   route as `!стол`, and the reverse call itself answers `not_a_word` for junk. Only
   an empty input and rule 5's length bound are refused. It combines with `?` in
   either order (`?!стол`, `!?стол` = reverse, no card).
2. **Without `!`, an alphabet decides only where it cannot be confused.** The
   alphabets are whole scripts — Latin, Cyrillic — never single letters: a Russian
   keyboard types Serbian with Russian letters (йош for још, ноч for ноћ), so a letter
   proves nothing about the language. The tab writes `S.script`; T writes its
   directory row's script.
   - The input is written in a script T writes and S does not → reverse, no model asked
     (Cyrillic on the English or German tab with a Russian target).
   - The input is written in a script S writes and T does not → ordinary S word, no
     model asked (Latin on the Serbian tab with a Russian target: nobody types Russian
     in Latin letters).
   - The input is written in a script both write → the model reads it (rule 3). With a
     Russian target that is Cyrillic on the Serbian tab; with a Serbian target, Latin on
     the English or German tab.

   A target outside the directory has no known script, so every script counts as
   shared and the model reads every input.
3. **Where the alphabets overlap, a model reads the input, and the reverse lookup is
   the last resort.** A typed word or expression in the shared script is asked the
   reading question (`build_reading_prompt`) beside the S article and judgement: is it
   S wording — a word, any form of one, however rare or inflected — S wording
   misspelled, or T wording typed here without its `!`? For a single word, only a
   plain T reading, one that names no S wording, and that the judgement confirms by
   finding the exact typed word unused in S, reverses. For more than one word the
   reading alone decides: the app asks the judgement of a single word only, and a
   phrase or a sentence carries more of its language to read. Then the S answer is
   dropped and the reverse call runs. Everything else is the ordinary S
   path, and a refusal there still offers the reverse lookup with one tap («Искать как
   русское слово»): the tap is a new `!` submission of the typed word, keeping the
   entry's `?`. A missed reverse costs the reader that tap or a retyped `!`; a wrong
   one throws away the S word they wanted, so the question leans to S.
4. **A chip never triggers reverse or the offer** — its label comes from the app's
   own S answer. Chips are submissions with `shape="unit"`; so is a retry after a
   reversal.
5. **A reverse request takes the shapes the S path takes, and the reverse call tells
   them apart as the S answer does.** A word or a fixed expression gets the S
   equivalents: the first is carded, the others are chips. Running text gets one
   translation into S, and that S text goes down the ordinary text path: translated
   back and explained, no note of its own, a lookup chip for each unit in it, each
   chip a card with the translated text as its context. Text needs no list of
   equivalents, because its own context picks the meaning. The bound is the S path's
   text bound, `MAX_TEXT_LENGTH`; longer → the existing hint, no model call. So on
   the Serbian tab «!не опаздываем ли мы на поезд» is headed «не опаздываем ли мы на
   поезд → <its Serbian translation>», explained, with a chip for each unit.
6. **For a model's reading, today's outcome is the floor.** When the reading (not `!`,
   and not a script T alone writes) sent the input to reverse and the reverse call
   answers `not_a_word`, the input is processed as the ordinary S submission it would
   have been.
   A `!` request has no floor: the reader asked for the target reading. Cyrillic on the
   English tab has none either: S's own validation refuses it.
7. **The empty field says what it takes.** On a tab whose script T does not share,
   the hint names both languages and needs no `!`: «Введите русский или английский
   текст». Where the scripts overlap it keeps the `!`: «Текст или !русский текст».
8. **No rule of its own for a tab in T itself.** Nothing stops a Russian tab beside
   a Russian target. There `!` asks for the Russian equivalents of a Russian word, and
   every refused word is offered that lookup. Considered (ignore `!` and the offer
   there) and dropped by the operator: no such tab exists.

## Measurements behind the rules

Why letters cannot decide, the placeholder widths, the reverse prompt's bench result
and the reading question's are in `spec/decision-reverse-translation.md`.

Timing references: attestation judgement on the pool, median 0.923 s, p90 7.190 s
(`decision-jev-attestation.md`); whole article ~2.0 s median, 3.8 s p90
(`decision-llm-backend.md`). The pool is measured fine at a couple of dozen requests
a day; past that its fallbacks are 20–60× slower. The reading question is a third
call, so it is asked only where the scripts overlap: with a Russian target, Cyrillic
typed on the Serbian tab; with a Latin-script target, every word typed on a Latin tab.

## The new call (reverse prompt)

- `build_reverse_prompt(language, word, target)` and
  `parse_reverse(raw, language, target)` in `src/echo_words/prompt.py`, next to
  `build_attestation_prompt` / `parse_attestation` (`prompt.py:307`, `:316`).
- Asks (built, `_REVERSE_PROMPT`): read the wording as T — an inflected word as its
  dictionary form, a fixed expression as itself, a slip of one or two letters as the
  word meant; the S words for the meanings a T dictionary gives it, usually one to
  three, commonest first, each translating a meaning the T wording itself has and
  never reached by way of English; a bare dictionary form; one short everyday S
  sentence per equivalent using that very word, with no swearword, and the word as
  that sentence spells it. `not_a_word` for a random string, a word of another
  language, a reading only slang or euphemism makes a word, and an S word typed in T
  letters that is no T word; `sentence` for a clause. A language written in two
  alphabets (Serbian) is asked for Latin only (`_LATIN_ONLY_RULE`).
- To build and bench (rule 5): for `sentence`, the answer also carries
  `"translation"`, the clause in natural S, so one call still tells the shapes apart;
  `parse_reverse` returns it, and a `sentence` without one is unusable. Benched on
  Russian sentences into English, German and Serbian, graded by a fresh reviewer, as
  the word half was.
- Answer JSON, strict:
  `{"verdict": "word" | "not_a_word" | "sentence", "read_as": str,
  "equivalents": [{"word": str, "example": str, "form": str}, ...]}`, at most 6
  equivalents. `form` is the equivalent as the example spells it (Stühle for Stuhl,
  stolu for sto, went for go).
- Validation in `parse_reverse` (built): verdict known; for `word`, ≥1 equivalent
  survives. An equivalent whose `word` (after `plain_unit`) fails
  `validate_word(word, S)`, or repeats an earlier one, is dropped; at most
  `MAX_EQUIVALENTS` (6) are kept. Each example is screened by
  `reverse_example_issue(example, form, word, S, T)`, which the bench reads too: it
  passes `validate_text`, is at most `MAX_CONTEXT_LENGTH` (500) long, passes
  `sentence_is_source_language`, and is marked by the card's own test —
  `context_sentence_forms` (`card.py`, now public) — at the `form` when the form
  shares a stem with the word (`_spells_the_word`), else at the word itself. Reasons:
  `missing`, `too_long`, `script`, `letters`, `unrelated` (the form is another word's),
  `form`. A failing example is dropped and its equivalent stays as a bare chip; the
  answer itself does not fail. Unusable → `None`. A one-word headword then takes the
  letter case its own sentence writes it in mid-sentence (`_headword_case`). A Serbian
  answer written in Cyrillic despite `_LATIN_ONLY_RULE` is read as written. The answer
  is read by `json_object`, which also reads a string value missing its opening quote.
- Why the card's test and not a comparison with the equivalent: German and Serbian
  examples inflect the word, so a whole-word match drops most verb and many noun
  examples, and a substring match passes «сто» inside «место». The stem check only
  refuses a form sharing no stem with its word (the first bench run kept
  «Schalterfenster» as the example of «Schiebefenster»); a suppletive form (went for
  go) costs its sentence unless the word itself is in it. The chip path does not
  compare spellings either: `_with_context_example` (`card.py:385`) finds the unit by
  the form the S answer names, and a sentence it cannot find the unit in fails the
  *card*, not just the example. The bound is the one `_sense_sentence` applies to a
  sense chip's sentence. `prompt.py` already imports from `card.py`, so no cycle.
- The example is more than a sense selector. The first equivalent's example becomes
  the card's front sentence (`_with_context_example`, `card.py:385`) and is voiced as
  the entry's context audio (`_voiced_context`, `pipeline.py:1446`), exactly like the
  sentence behind a sense chip.
- Routing, as `backend.py` actually behaves:
  - The pool is asked through `cascade.stream_completion(prompt, S,
    trace_id=f"{entry_id}-reverse", usable=lambda a: parse_reverse(a, S, T) is not None)`.
    A pool that answers nothing within the budget is already stepped up to the paid
    model inside that call (`_steps_up`, `backend.py:355-361`).
  - A pool answer `usable` rejects is re-asked of the same call; when the pool has no
    other answer, the stream simply ends with the unusable text (`backend.py:362-373`).
    The cascade never buys a paid answer over it. So the pipeline does it: parse
    fails → `cascade.paid_refusal(S)` is `None` → `cascade.stream_paid(prompt, S,
    trace_id=f"{entry_id}-reverse-paid")`. Refused or failing → the entry fails
    (`_fail`; retry is offered).
  - That automatic paid step is an exception to the functional description's "a
    payload that no answer of that request could carry does not buy a paid one by
    itself". That rule protects an article already on the page; a reverse call has
    nothing on the page. The spec states the exception (see "Specs and docs").
  - Rated like the attestation (`pipeline.py:826`):
    `record_quality(1.0 if parsed else 0.0)` on the pool completion; a stepped-up
    completion ignores it.
  - The reverse call is `reported`: it is the entry's first answer, and the only one
    when it fails.
- The same prompt serves `!`, a script T alone writes, a T reading, and the offer's
  tap, which is a `!` submission.

## The reading question (built, being measured)

- `build_reading_prompt(language, word, target)` and `parse_reading(raw)` in
  `src/echo_words/prompt.py`: `"source" | "typo" | "target"`, or `None` for an
  unreadable answer, which counts as not `target`. The answer also names the S wording
  the model read the input as (`as_source`).
- Asked of the pool beside the attestation, only for a typed word or expression in a
  script both S and T write (rule 2).
- Measured (decision spec): alone it still reverses врач and pas in every sample, so
  a single word's reverse waits for two models to agree. It is taken only when the
  reading says `target` with `as_source` empty **and** the attestation the app already
  asks of a single word says it is not used in S. More than one word reverses on the
  reading's `target` alone. Anything else, or no answer, → the S path continues
  untouched. This adds no call; it costs the wait for the slower of the two when the
  reading says `target`.
- Next measurement, on the pool's fresh quota: resume the reading's third sample
  (`experiments/.bench-reading-v3-c`, `run` resumes), ask the reading about the 15
  cases added since (eight of the врач/pas kind — булка, чета, жир, диван on the
  Serbian tab, baba, dan, sir, brat on the English tab with a Serbian target — and
  seven sentences), and ask the attestation about every single-word case, three
  samples each; then score the two together and give every item to a fresh
  reviewer. If the pair still reverses the tab's own wording, the
  fallback is to reverse nothing on its own and keep only the offer.
- The S article and judgement start at once, as today, so a word that stays S waits
  for nothing; a T reading costs the reader the S answer already streaming, which is
  dropped.

## Backend changes

- `languages.py`
  - New `script_route(text, language, target) -> "target" | "source" | "shared"`: the
    scripts the input's letters are written in (`_letter_script`), against S's
    (`_ALLOWED_SCRIPTS[language.script]`) and T's (its directory row's script; none
    known → `shared`). Whole scripts only, never single letters.
  - `normalize_submission` (`:286`): strip leading `?` and `!` in any order; return
    `(text, lookup_only, forced)`. Lands in step 4 together with its caller.
- `api.py` `submit_word` (`:334`):
  - Today's S normalisation and validation run as now, but their hint is held rather
    than raised until the reverse decision is made: on the English tab «стол» fails
    S validation, and that must not stop it from reversing. The job's `word` and
    `intent` are always that S normalisation (`plain_text`, then `plain_unit` and
    `intent="unit"` for one word — `:338-347`), so the rule-7 floor continues the very
    submission today's path would have made; the reverse call reads
    `plain_unit(job.word)`.
  - `reverse = "forced"` for `!`; `"script"` when `shape is None` and `script_route`
    says `target`; otherwise `None`. `asks_reading` when `shape is None` and
    `script_route` says `shared`.
  - A reverse candidate gets no script or letter check (rule 1): its text is
    `plain_unit` of the S normalisation, and only emptiness and length are tested.
    Empty → the existing `word.empty` hint. Within `MAX_TEXT_LENGTH` → a reverse job.
    Longer → the existing `text.too_long` hint.
  - Not a reverse candidate → the held S hint is raised as today.
  - `offers_reverse` = `asks_reading` and the S normalisation is one word. Computed
    here because the pipeline cannot recompute it: `:346-347` gives a typed single
    word `intent="unit"`, exactly what a chip sends, so by the time a job is queued a
    chip looks like a typed word (rule 4).
  - Pass `reverse`, `asks_reading` and `offers_reverse` to `pipeline.enqueue`. Add all
    three to the fingerprint (`SubmissionFingerprint`, `:69`), and `reverse` to
    `SubmissionAccepted` (`:230`) as `"forced" | "script" | None`: the PWA shows the
    pending line for both, and retries with `!` only for `"forced"` (a script retry
    triggers again by itself).
  - New `GET /api/target` → `{"code": <T's directory code> | null, "name": <T as
    configured>}`. The PWA reads T's and S's names from `/api/languages/catalog`,
    which `App.vue` already fetches and caches at start (`refreshReferences`); a
    target outside the directory has only its configured name. `/api/languages`
    keeps its shape: it carries only the code and the endonym.
- `pipeline.py`
  - `Job.reverse: Literal["forced", "script", "reading"] | None`, `Job.asks_reading:
    bool`, `Job.offers_reverse: bool` and `Job.equivalents: tuple[Segment, ...]`, all
    defaulting to "no" / empty so rebuilds, switches and chips carry none of them
    unless passed.
  - Reverse resolution runs at the top of `process_word` (`:516`), before the audio
    task and the attestation are created (`:520`, `:549`), and runs the reverse call
    as routed above:
    - `word` → set `entry.word = first.word`, `entry.typed_word = job.word`,
      `entry.read_as` (when it differs from the typed word),
      `entry.context = first.example`, and publish `reset` carrying those four.
      Continue with `replace(job, word=first.word, context=first.example,
      intent="unit", reverse=None, offers_reverse=False, equivalents=others)` — the
      chip path. From here `ControlState`, `shown_spelling`, undo, rebuild, switch,
      delete and the detail article all read the equivalent, and the typed T word is
      never voiced. Keeping `entry.word` as the typed word instead would leave the
      rail, the dictionary link (`EntryCard.vue:290`) and the unattested, misspelling,
      delete and retry messages (`EntryCard.vue:258-283`, `:491`, `:575`) naming
      «стол».
    - `sentence` → set `entry.word = translation`, `entry.typed_word = job.word`,
      publish `reset`, and continue as the ordinary S text job:
      `replace(job, word=translation, intent=None, reverse=None, offers_reverse=False)`
      — the S answer then decides the branch as it does for any typed text (rule 5).
    - `not_a_word` → if `reverse == "reading"`, continue as the ordinary S job with
      `reverse=None` (rule 6). Otherwise finish the entry with `card_status`
      `reverse_not_a_word` (and the same code as its action, so neither counters nor
      undo treat it as stored), no card, no audio.
    - No usable answer from pool or paid → `_fail`.
  - The reading (rule 3): when `asks_reading`, the reading question is asked beside
    the attestation. `target` → cancel the S article and attestation, set
    `reverse="reading"`, and run the reverse resolution above; anything else leaves
    the S job running untouched. The reading call is rated like the attestation.
  - Equivalents: when there is more than one, the others are carried on the job as
    `Segment(label=word, reason="", context=example)`, and `_segments_for` (`:1301`)
    returns them with `segment_kind = "equivalents"` ahead of anything the answer
    holds — replacing the article's own sense chips for the carded word, and kept
    even when the attestation refuses the first equivalent and the answer is
    withheld, because each one is judged again when tapped. With a single equivalent,
    the article's sense chips stay. `ControlState` keeps them (`_update_state`,
    `:1066`), and `request_rebuild` (`:334`) and `request_switch` (`:365`) pass them
    to `enqueue`: `_reset_reused_entry` (`:1244`) empties `entry.segments` and each
    run rebuilds them from its job, so without that a rebuild or a switch would trade
    the other equivalents for *table*'s senses.
  - The offer (rule 3): at the end of the run,
    `entry.reverse_offered = job.offers_reverse and stored.status == UNATTESTED_STATUS`.
    The misspelling overrule (`pipeline.py:678-684`) runs before it, so a corrected S
    misspelling that ends carded is not offered; a refused `?` lookup is
    (`UNATTESTED_STATUS` with action `lookup`).
  - The new fields reach the page on two events: the reversal on `reset`, and
    `reverse_offered` on `done`, whose payload is an explicit dict (`:1036`), not
    `entry.public()`.
- `history.py`: `Entry` (`:15`) gains `typed_word`, `read_as`, `reverse_offered`, all
  in `public()`. `SegmentKind` (`:11`) gains `"equivalents"`. `_reset_reused_entry`
  keeps the first two across a switch or a rebuild and clears `reverse_offered`.
- `i18n.py`: no new hint; a reverse request over the text bound gets `text.too_long`. Finished entries
  carry codes, and their wording is the client's (`pipeline.py:41`).

## Frontend changes

- One helper derives, from a directory row, the forms the strings need: the neuter
  adjective (`-ий/-ый/-ой` → `-ое`: сербское) or, for the three names that do not
  decline (африкаанс, эсперанто, суахили), «слово на {name}». The row's `russian`
  name itself is the accusative after «на» (на английский, на суахили).
- `add.wordPlaceholder` becomes a template with two shapes (rule 7). Where the tab's
  and T's scripts overlap: ru «Текст или !{adj T} слово» / «Текст или !слово на
  {name}», en «Text or !word in {English}» (avoids a/an: "an English", "a Ukrainian").
  Where T's script is one the tab does not write: ru «{Adj S} текст или {adj T} слово»
  («Английский текст или русское слово»), en «{English} text or a word in {Russian}».
  A target outside the directory has no declinable name and no known script, so its
  configured name takes the indeclinable form with the `!`: «Текст или !слово на
  Japanese». Both shapes are measured at 360 px before they ship, like the widths in
  the decision spec.
- Pending line while the reverse call runs (receipt `reverse` set): ru «Перевожу
  «{typed}» на {S russian name}…», en "Finding the {S English name} word for
  «{typed}»…".
- The `reset` handler (`useEventStream.js:69`) applies `word`, `typed_word`,
  `read_as` and `context` when present, as it already does `detail_html`. It also
  sets `requested_shape: "unit"` and `requested_reverse: null`, so a retry after the
  reversal resends the equivalent as a chip.
- Both receipt handlers — `sendWord`'s (`AddView.vue:144-154`) and the resend
  queue's (`useResendQueue.js:93-101`) — record `requested_reverse` from the receipt
  beside `requested_shape`. Without the queue's, a queued `!город` that fails retries
  without its `!`, and its pending line is the ordinary one.
- Neither receipt handler overwrites `word`, `context`, `requested_shape` or
  `requested_reverse` once the entry carries `typed_word`. Today both merge them in
  even into an entry that is already streaming, which is safe only because "no later
  event carries the word" (`AddView.vue:143`); `reset` now does. A receipt read after
  the reversal — rare, since the POST's answer leaves before the reverse call starts
  and that call takes about a second at least, but nothing orders the two — would put
  «стол» back on the rail, read «стол → стол» in the header, drop the example, and
  make a retry resend «стол» as typed.
- `sendWord` takes `lookup_only` instead of always posting `false` (`AddView.vue:135`).
  Retry (`AddView.vue:180`) passes the entry's `lookup_only` — today a failed `?word`
  retries as a card — and restores `!` when `requested_reverse` is `"forced"`.
- Entry header: «стол → table» when `typed_word` is set; «сотл → стол → table» when
  `read_as` differs from it.
- Equivalent chips render like sense chips; tapping one submits `{word, shape: "unit",
  context}` as chips do today.
- Outcome: `reverse_not_a_word` → ru «Модель не считает «{word}» словом — проверьте
  написание.», en "The model does not take «{word}» for a word — check the spelling."
- `reverse_offered` → button ru «Искать как {adj T} слово», en "Look it up as a word in
  {Russian}": submits `!` + `entry.word` as a new submission with the entry's
  `lookup_only`, so a refused `?город` stays a lookup.
- Remove the «Что это и как пользоваться» panel: `AddView.vue:309-319`, its
  `helpOpen` state and `.about*` CSS, the `add.about*` keys in `ru.js` and `en.js`,
  and any test that reads them. The panel is the only place a reader learns `?`, so
  the docs bullet below covers `?` and `!` together.

## Tests (CI, no network)

- `tests/test_languages.py`: `normalize_submission` with `?`, `!`, `?!`, `!?`;
  `script_route` for S ∈ {en, de, sr} × T ∈ {Russian, English, Serbian}: Cyrillic on
  English with a Russian target → `target`, Latin on Serbian with a Russian target →
  `source`, Cyrillic on Serbian with a Russian target and Latin on English with a
  Serbian target → `shared`, йош on Serbian → `shared` (a letter is no proof); a
  target outside the directory → `shared`.
- `tests/test_prompt.py`: prompt names S and T and asks for the form; `parse_reverse`
  accepts the three verdicts; keeps an example that carries its word inflected
  (`Stühle` for `Stuhl`); drops one whose `form` is not in it, one over 500
  characters, and one failing the letter test, keeping its equivalent as a bare chip;
  rejects bad JSON, empty equivalents and equivalents failing S validation.
- `tests/test_card.py`: the now-public `_context_sentence_forms` keeps its existing
  cases.
- `tests/test_api.py`: `!` on every tab; Cyrillic on English auto-reverses; a chip with
  Cyrillic does not; reverse over the text bound → 400 `text.too_long`; Cyrillic on the
  Serbian tab asks the reading and Latin there does not; `!` takes anything non-empty within the bound with no script check —
  `!стoл` with a Latin o, digits, `!ねこ` with a target outside the directory; `!` alone → `word.empty`;
  the receipt carries `reverse`; `/api/target` for a directory target and for one
  outside it; `offers_reverse` set for a typed single word in a shared script and not
  for a chip, two words, or a script one language alone writes.
- `tests/test_pipeline.py`: `!` → card for the first equivalent; `reset` carries
  `word`, `typed_word`, `read_as`, `context`; `shown_spelling`, undo and rebuild use the
  equivalent; no audio for the typed word; the other equivalents as chips; a single
  equivalent keeps the sense chips; a rebuild and a switch of a reversed entry keep
  the other equivalents; the reverse call is rated; pool silent → paid inside the
  cascade; pool unusable → the pipeline's own `stream_paid`; paid refused → the entry
  fails; `not_a_word`; `sentence`; a `target` reading → the S answer dropped and the
  reverse run; any other reading or none → the S job untouched; a `target` reading +
  `not_a_word` → continues as the S job (rule 6); `!` + `not_a_word`
  on Serbian → stays not a word; an equivalent the attestation refuses → refusal
  shown, chips kept; `typed_word` survives a switch.
- `tests/test_attestation.py` (the offer): a refused job with `offers_reverse` sets
  `reverse_offered`, and so does a refused `?` lookup; a declared misspelling the
  overrule cards does not; a refused job without `offers_reverse` (a chip) does not;
  a switch or a rebuild clears it.
- `tests/test_history.py`: the new fields round-trip; the `"equivalents"` kind.
- Webapp unit tests (`webapp/tests/`): placeholder for ru/en, declined and
  indeclinable names, and with no target; the pending line; `reset` applies the
  reversal; a receipt read after `reset` leaves the reversal standing, in both
  receipt handlers; a queued `!` submission records `requested_reverse`; retry
  restores `!` and `?`; header with and without `read_as`; both outcome messages;
  the offer button, keeping `?`.
- Browser (`tests/test_e2e_reverse.py`, Chromium, gate-held fake): the pending line
  while the reverse call is held; «стол → table»; chips; a refused Cyrillic word
  on the Serbian tab offering «Искать как русское слово», whose tap makes a reversed
  entry; the failure message, and its retry keeping the `!`.
- `tests/test_one_note_bench.py`: the new bench action's scoring.

## Bench (Russian target, pool) — built

`run-reverse` in `experiments/one_note_bench.py`, fixtures in
`experiments/reverse_items.py`; `report` screens a directory holding reverse rows
with its own section and writes `review-packet-reverse.json`. 59 reverse calls — the
plan's 16 wordings into en/de/sr, its two Serbian-only ones, plus сабака and ключь
(misspellings) into all three and йедан, ньега, мойе (keyboard Serbian) into Serbian,
added after the first review asked for more of both. The offer words get both the
Serbian judgement and the Serbian article (production asks both for a typed single
word, and the article can overrule a refusal by correcting the word), plus the second
judgement wherever the article corrects a refused one: 8 calls and up to 4.

```
uv run python experiments/one_note_bench.py run-reverse --resume \
  --wait 180 --pace 3 --concurrency 1 --out experiments/.bench-reverse
uv run python experiments/one_note_bench.py report --out experiments/.bench-reverse
```

Results, reviews and the decision are in `spec/decision-reverse-translation.md`.

## Specs and docs

- `spec/functional-description.md` input section, item 2 ("The language is always
  the user's explicit selection, never guessed…"): replace with rules 1–8 as
  behaviour; describe the reverse entry, the reading and the offer.
- `spec/functional-description.md`, the paid step ("A payload that no answer of that
  request could carry does not buy a paid one by itself"): state the exception — a
  reverse answer the pool cannot make usable is bought from the paid model without
  asking, because nothing is on the page yet.
- `spec/decision-product.md`, the "Multiple source languages…" guard: "The tab
  chooses the deck and the source language. Whether a word is in the target language
  is decided by `!`, by an alphabet the target writes and the tab does not, or, where
  the two share an alphabet, by a model's reading that leans to the tab's language; a
  single typed word the source language refuses is offered the target reading with
  one tap. No code reads a word's letters to guess its language."
- `spec/decision-reverse-translation.md` (exists): add the reading question's bench
  result and why the reverse is the last resort; the dropped alternatives (letter
  tests; converting Serbian Cyrillic input to Latin; Jev as the reader; Wiktionary
  translation tables; a rule of its own for a tab in T itself).
- `docs/src/{ru,en}/index.md` "Что умеет / What it does": one bullet for `!` and `?`.
- `CLAUDE.md` already lists this plan among the open ones; set it back to "One is
  open" when the work lands.
- `uv run inv readme-screenshots` after the placeholder and panel change.

## Order of work

1. **Done, then replaced.** The letter functions step 1 built are removed by the
   operator's direction; `script_route` and the reading question take their place.
   The reading prompt and its parser are built and being measured
   (`experiments/reading_bench.py`); `script_route` lands in step 4 with its caller.
   Prefix parsing waits for step 4, so that `!` is never accepted and silently dropped
   before the pipeline can act on it.
2. **Done.** Reverse prompt (with `form`) + parser (screening examples by the card's
   own, now public, `context_sentence_forms`) + tests.
3. **Done.** Bench action + fixtures + attestation shots + dropped-example counts +
   its test; run, fresh review, revision, re-run, second fresh review, recorded. Steps
   4–6 are checked against its result before they are built.
4. Prefix parsing + `script_route` + API (`!`, the script route, `asks_reading`,
   `offers_reverse`, `/api/target`) + pipeline reverse resolution and the reading
   (equivalents kept across rebuild and switch, rule 6's floor) + the offer + history
   + tests.
5. Frontend: placeholder (rule 7), pending line, `reset` handling, both receipt handlers,
   `sendWord`'s `lookup_only`, retry, header, chips, outcomes, offer button, panel
   removal + tests.
6. Browser tests.
7. Specs, docs, screenshots; delete this plan.

Each step ends with `uv run inv pre` and `uv run inv test` fully green. No push and
no deploy without the operator's explicit approval for that act.
