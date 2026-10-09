# Plan: reverse translation

**Status (2026-10-09):** steps 1–3 built. The letter tests, the reverse prompt and
its parser are in the code and asked by nothing yet; the prompt was benched four
times on the pool and reviewed by a fresh agent each time, and the result is in
`spec/decision-reverse-translation.md`: English and German carry it as measured.
Serbian is asked in Latin letters, with its chips, as the operator chose after six
Latin samples (the decision spec has the numbers); the parser refuses Cyrillic in a
Serbian answer and reads a string value missing its opening quote. Open with the
operator: acceptance of the faults the decision spec lists. Next is step 4.

## What the reader gets

On the English tab the reader types `стол` and gets the card for *table* in
«EchoWords: English», exactly as if they had typed `table`. The selected language
still chooses the deck and the language translated into; the typed word is in the
**target language** (`ECHOWORDS_TARGET_LANG`, Russian by default). Nothing below is
Russian-specific: the rules read the per-language letter table, so they work for any
target, and they happen to catch almost everything when the target is Russian.

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
2. **Without `!`, letters decide where they prove it.** Letters come from
   `_BEYOND_LATIN` (`src/echo_words/languages.py:374`) through `_alphabet()`, the
   same rows the card-sentence test reads:
   - the word has a letter T has and S lacks, and none S has and T lacks → reverse;
   - the word has a letter S has and T lacks → ordinary S word (a word with both
     kinds of letter is proved neither way and is handled exactly as today, by S's
     own validation);
   - neither → ordinary S word, and a refusal offers the reverse lookup (rule 3).

   Letters can only prove what the directory records: for a target outside it no
   letters are known, every letter then counts as S's own, and only `!` reverses.
   That is what `_target_letters` already returns, so it needs no code of its own.
3. **A refusal offers the reverse lookup; no model guesses the language.** When a
   single typed word is left open by letters (rule 2, third case) and the entry ends
   refused by the existing attestation judgement — no card, because the S answer
   would not vouch for the word — the entry offers the reverse lookup with one tap
   («Искать как русское слово»). The tap is a new `!` submission of the typed word,
   and it keeps the entry's `?`. A word that exists in both languages (вода, рука,
   hotel) is accepted and offered nothing; an S misspelling the S answer corrects (a
   declared misspelling overrules the refusal) ends carded and is offered nothing
   either, so кашка, a Serbian misspelling of кашика that is also a Russian word, is
   carded as кашика.

   Considered and dropped by the operator: a helper that asked the model, for every
   such refusal, whether the word is a T word and took the entry over. It saved one
   tap and about one S answer's wait on one tab only (with a Russian target, the
   Serbian tab in Cyrillic), at the price of a third model call per refusal, holding
   back the paid typo correction while it answered, carding кашка as Russian, and an
   undo button for its mistakes.
4. **A chip never triggers reverse or the offer** — its label comes from the app's
   own S answer. Chips are submissions with `shape="unit"`; so is a retry after a
   reversal.
5. **Size:** a reverse request is a word or expression within `MAX_WORD_LENGTH`
   (50). Longer → immediate hint, no model call. Shorter but a sentence → the new
   call says so → the same message. Both subject to rule 7.
6. **No q/w/x/y "lacks" column.** Considered (21% of English and 12% of German words
   carry one, which Serbian/Croatian/Bosnian never write) and dropped by the
   operator: non-Russian targets use `!`.
7. **For letters, today's outcome is the floor.** When letters (not `!`) sent the
   input to reverse and the reverse path cannot card it — longer than
   `MAX_WORD_LENGTH`, a `sentence` or a `not_a_word` verdict — and S's own validation
   accepts the input, it is processed as an ordinary S submission: the same text,
   normalised and shaped exactly as today's path would have sent it. Only a tab whose
   script contains T's can reach this (Serbian, Ukrainian, Bulgarian… with a Russian
   target; Cyrillic fails English and German validation). The case it exists for: a
   Russian keyboard has no ј љ њ ћ ђ џ, so Serbian typed on one substitutes
   Russian-only letters (йош for још), and today such a word reaches the Serbian
   article, which can correct it. A `!` request has no floor: the reader asked for
   the target reading.
8. **No rule of its own for a tab in T itself.** Nothing stops a Russian tab beside
   a Russian target. There `!` asks for the Russian equivalents of a Russian word, and
   every refused word is offered that lookup. Considered (ignore `!` and the offer
   there) and dropped by the operator: no such tab exists.

## Measurements behind the rules

The letter measurements, the loanword limit and the placeholder widths are in
`spec/decision-reverse-translation.md`, and so is the reverse prompt's bench result.

Timing references: attestation judgement on the pool, median 0.923 s, p90 7.190 s
(`decision-jev-attestation.md`); whole article ~2.0 s median, 3.8 s p90
(`decision-llm-backend.md`). The pool is measured fine at a couple of dozen requests
a day; past that its fallbacks are 20–60× slower — which is why no model is asked
whether an open word is a T word: asked of every open word that is a third call on
83–100% of words when T is English or German.

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
  letter case its own sentence writes it in mid-sentence (`_headword_case`). Both
  screens see a two-alphabet language as Latin only (`_as_answered`), so Cyrillic in a
  Serbian word or sentence fails `validate_word` / `validate_text`. The answer is read
  by `json_object`, which also reads a string value missing its opening quote.
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
- The same prompt serves `!`, letters and the offer's tap, which is a `!`
  submission.

## Backend changes

- `languages.py`
  - New `reads_as_target(text, language, target)` (some letter T has and S lacks) and
    `reads_as_source(text, language, target)` (some letter S has and T lacks), NFC +
    casefold, using `_target_letters(target)` and `_letters_spelled(language)`
    (`:465`, `:478`). `sentence_is_source_language` (`:450`) becomes
    `not reads_as_target(...)`: one letter test with two names for its two callers.
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
  - `reverse = "forced"` for `!`; `"letters"` when `shape is None`, `reads_as_target`
    and not `reads_as_source`; otherwise `None`.
  - A reverse candidate gets no script or letter check (rule 1): its text is
    `plain_unit` of the S normalisation, and only emptiness and length are tested.
    Empty → the existing `word.empty` hint. Within `MAX_WORD_LENGTH` → a reverse job.
    Longer, from letters, with the held S hint `None` → the ordinary S job (rule 7).
    Otherwise longer → 400 `reverse.words_only`.
  - Not a reverse candidate → the held S hint is raised as today.
  - `offers_reverse` = `shape is None`, the S normalisation is one word, and letters
    prove neither way (neither `reads_as_target` nor `reads_as_source`). Computed here
    because the pipeline cannot recompute it: `:346-347` gives a typed single word
    `intent="unit"`, exactly what a chip sends, so by the time a job is queued a chip
    looks like a typed word (rule 4).
  - Pass `reverse`, `source_ok` (the held S hint was `None`) and `offers_reverse` to
    `pipeline.enqueue`. Add `reverse` and `offers_reverse` to the fingerprint
    (`SubmissionFingerprint`, `:69`), and `reverse` to `SubmissionAccepted` (`:230`)
    as `"forced" | "letters" | None`: the PWA shows the pending line for both, and
    retries with `!` only for `"forced"` (a letters retry triggers again by itself).
  - New `GET /api/target` → `{"code": <T's directory code> | null, "name": <T as
    configured>}`. The PWA reads T's and S's names from `/api/languages/catalog`,
    which `App.vue` already fetches and caches at start (`refreshReferences`); a
    target outside the directory has only its configured name. `/api/languages`
    keeps its shape: it carries only the code and the endonym.
- `pipeline.py`
  - `Job.reverse: Literal["forced", "letters"] | None`, `Job.source_ok: bool`,
    `Job.offers_reverse: bool` and `Job.equivalents: tuple[Segment, ...]`, all
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
    - `not_a_word` / `sentence` → if `reverse == "letters"` and `source_ok`, continue
      as the ordinary S job with `reverse=None` (rule 7). Otherwise finish the entry
      with `card_status` `reverse_not_a_word` / `reverse_sentence` (and the same code
      as its action, so neither counters nor undo treat it as stored), no card, no
      audio.
    - No usable answer from pool or paid → `_fail`.
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
- `i18n.py`: the one new 400 hint, `reverse.words_only`, ru + en. Finished entries
  carry codes, and their wording is the client's (`pipeline.py:41`).

## Frontend changes

- One helper derives, from a directory row, the forms the strings need: the neuter
  adjective (`-ий/-ый/-ой` → `-ое`: сербское) or, for the three names that do not
  decline (африкаанс, эсперанто, суахили), «слово на {name}». The row's `russian`
  name itself is the accusative after «на» (на английский, на суахили).
- `add.wordPlaceholder` becomes a template: ru «Текст или !{adj T} слово» / «Текст или
  !слово на {name}», en «Text or !word in {English}» (avoids a/an: "an English", "a
  Ukrainian"). A target outside the directory has no declinable name, so its
  configured name takes the indeclinable form: «Текст или !слово на Japanese».
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
- Outcomes: `reverse_not_a_word` → ru «Модель не считает «{word}» словом — проверьте
  написание.», en "The model does not take «{word}» for a word — check the spelling.";
  `reverse_sentence` → ru «Обратный перевод — только для слов и выражений.», en
  "Reverse translation takes words and expressions only."
- `reverse_offered` → button ru «Искать как {adj T} слово», en "Look it up as a word in
  {Russian}": submits `!` + `entry.word` as a new submission with the entry's
  `lookup_only`, so a refused `?город` stays a lookup.
- Remove the «Что это и как пользоваться» panel: `AddView.vue:309-319`, its
  `helpOpen` state and `.about*` CSS, the `add.about*` keys in `ru.js` and `en.js`,
  and any test that reads them. The panel is the only place a reader learns `?`, so
  the docs bullet below covers `?` and `!` together.

## Tests (CI, no network)

- `tests/test_languages.py`: `normalize_submission` with `?`, `!`, `?!`, `!?`;
  `reads_as_target` / `reads_as_source` for S ∈ {en, de, sr} × T ∈ {Russian, English,
  German}, Latin and Cyrillic Serbian; a word with both kinds of letter proves
  neither; `sentence_is_source_language` unchanged on its existing cases; a target
  outside the directory makes every letter S's own.
- `tests/test_prompt.py`: prompt names S and T and asks for the form; `parse_reverse`
  accepts the three verdicts; keeps an example that carries its word inflected
  (`Stühle` for `Stuhl`); drops one whose `form` is not in it, one over 500
  characters, and one failing the letter test, keeping its equivalent as a bare chip;
  rejects bad JSON, empty equivalents and equivalents failing S validation.
- `tests/test_card.py`: the now-public `_context_sentence_forms` keeps its existing
  cases.
- `tests/test_api.py`: `!` on every tab; Cyrillic on English auto-reverses; a chip with
  Cyrillic does not; reverse over 50 chars → 400 `reverse.words_only`; on the Serbian
  tab, text over 50 chars with a Russian-only letter is accepted as Serbian text
  (rule 7); `!` takes anything non-empty within the bound with no script check —
  `!стoл` with a Latin o, digits, `!ねこ` with a target outside the directory; `!` alone → `word.empty`;
  the receipt carries `reverse`; `/api/target` for a directory target and for one
  outside it; `offers_reverse` set for a typed open-letter single word and not for a
  chip, two words, or a word letters prove either way; a two-word letters candidate
  on the Serbian tab queues today's S normalisation (`plain_text`, no intent).
- `tests/test_pipeline.py`: `!` → card for the first equivalent; `reset` carries
  `word`, `typed_word`, `read_as`, `context`; `shown_spelling`, undo and rebuild use the
  equivalent; no audio for the typed word; the other equivalents as chips; a single
  equivalent keeps the sense chips; a rebuild and a switch of a reversed entry keep
  the other equivalents; the reverse call is rated; pool silent → paid inside the
  cascade; pool unusable → the pipeline's own `stream_paid`; paid refused → the entry
  fails; `not_a_word`; `sentence`; letters + `not_a_word` on Serbian → continues as
  Serbian with the word and intent today's path gives it (rule 7); `!` + `not_a_word`
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
  while the reverse call is held; «стол → table»; chips; a refused open-letter word
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
  the user's explicit selection, never guessed…"): replace with rules 1–7 as
  behaviour; describe the reverse entry and the offer.
- `spec/functional-description.md`, the paid step ("A payload that no answer of that
  request could carry does not buy a paid one by itself"): state the exception — a
  reverse answer the pool cannot make usable is bought from the paid model without
  asking, because nothing is on the page yet.
- `spec/decision-product.md`, the "Multiple source languages…" guard: "The tab
  chooses the deck and the source language. Whether a word is in the target language
  is decided by its letters where they prove it, or by `!`; a single typed word the
  source language refuses, whose letters prove nothing, is offered the target
  reading with one tap. No model guesses the language of a word."
- New `spec/decision-reverse-translation.md`: the measurements above, the reason for
  rule 7, why a refusal gets an offer rather than a model check (rule 3: what the
  helper would have cost, which tab it served, кашка), why an example is screened by
  the card's own test, the dropped alternatives (model detection inside the article
  payload; a helper asked on every open word, or on every refusal, that took the
  entry over; Wiktionary translation tables; a q/w/x/y column; a rule of its own for
  a tab in T itself), the bench result.
- `docs/src/{ru,en}/index.md` "Что умеет / What it does": one bullet for `!` and `?`.
- `CLAUDE.md` already lists this plan among the open ones; set it back to "One is
  open" when the work lands.
- `uv run inv readme-screenshots` after the placeholder and panel change.

## Order of work

1. **Done.** Letter functions (`reads_as_target`, `reads_as_source`,
   `sentence_is_source_language` on top of them) + tests. Prefix parsing waits for
   step 4, so that `!` is never accepted and silently dropped before the pipeline can
   act on it.
2. **Done.** Reverse prompt (with `form`) + parser (screening examples by the card's
   own, now public, `context_sentence_forms`) + tests.
3. **Done.** Bench action + fixtures + attestation shots + dropped-example counts +
   its test; run, fresh review, revision, re-run, second fresh review, recorded. Steps
   4–6 are checked against its result before they are built.
4. Prefix parsing + API (`!`, letters, rule 7 on S's own normalisation,
   `offers_reverse`, `/api/target`) + pipeline reverse resolution (equivalents kept
   across rebuild and switch) + the offer + history + tests.
5. Frontend: placeholder, pending line, `reset` handling, both receipt handlers,
   `sendWord`'s `lookup_only`, retry, header, chips, outcomes, offer button, panel
   removal + tests.
6. Browser tests.
7. Specs, docs, screenshots; delete this plan.

Each step ends with `uv run inv pre` and `uv run inv test` fully green. No push and
no deploy without the operator's explicit approval for that act.
