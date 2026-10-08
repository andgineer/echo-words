# Plan: reverse translation

**Status (2026-10-08):** designed with the operator and checked against the code;
nothing built. Next step is step 1 of "Order of work".

## What the reader gets

On the English tab the reader types `стол` and gets the card for *table* in
«EchoWords: English», exactly as if they had typed `table`. The selected language
still chooses the deck and the language translated into; the typed word is in the
**target language** (`ECHOWORDS_TARGET_LANG`, Russian by default). Nothing below is
Russian-specific: the rules read the per-language letter table, so they work for any
target, and they happen to catch almost everything when the target is Russian.

Once the word is resolved, the entry *is* the entry a tap on a chip for *table* would
make: its rail label, card, audio, controls and messages are all about *table*. Only
its header says «стол → table».

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
   - the word has a letter S has and T lacks → ordinary S word, no helper (a word
     with both kinds of letter is proved neither way and is handled exactly as
     today, by S's own validation);
   - neither → ordinary S word, and the helper (rule 3) may run.

   Letters can only prove what the directory records: for a target outside it no
   letters are known, every letter then counts as S's own, and only `!` reverses.
   That is what `_target_letters` already returns, so it needs no code of its own.
3. **The helper** asks the model whether the word is a T word, and runs only when
   all hold: a single typed word, not a chip, letters left it open (rule 2, third
   case), and the existing attestation judgement **refused** the word in S. A word
   that exists in both languages (вода, рука, hotel) is accepted by the judgement and
   never reaches the helper.
4. **A chip never triggers reverse or the helper** — its label comes from the app's
   own S answer. Chips are submissions with `shape="unit"`; so are the «Это сербское
   слово» resubmission and a retry after a reversal.
5. **Size:** a reverse request is a word or expression within `MAX_WORD_LENGTH`
   (50). Longer → immediate hint, no model call. Shorter but a sentence → the new
   call says so → the same message. Both subject to rule 7.
6. **No q/w/x/y "lacks" column.** Considered (21% of English and 12% of German words
   carry one, which Serbian/Croatian/Bosnian never write) and dropped by the
   operator: non-Russian targets use `!`.
7. **For letters, today's outcome is the floor.** When letters (not `!`) sent the
   input to reverse and the reverse path cannot card it — longer than
   `MAX_WORD_LENGTH`, a `sentence` or a `not_a_word` verdict — and S's own validation
   accepts the input, it is processed as an ordinary S submission, without the
   helper. Only a tab whose script contains T's can reach this (Serbian, Ukrainian,
   Bulgarian… with a Russian target; Cyrillic fails English and German validation).
   The case it exists for: a Russian keyboard has no ј љ њ ћ ђ џ, so Serbian typed on
   one substitutes Russian-only letters (йош for још), and today such a word reaches
   the Serbian article, which can correct it. A `!` request has no floor: the reader
   asked for the target reading.

## Measurements behind the rules

Moved into `spec/decision-reverse-translation.md` when the work lands. Method:
wordfreq top lists, words of 3+ letters, first 2,000 per language; Serbian taken
from wordfreq's `sh` list (Latin) and transliterated for the Cyrillic row; letters
from the app's own `_alphabet()`.

| S → T | T words proved by letters | S words left open by letters |
|---|---|---|
| English / German → Russian | 100% | 0% |
| Serbian → Russian | 43% | 0% in Latin, 73% in Cyrillic |
| German → English | 0% | 89% |
| Serbian → English | 0% | 83% |
| English → German | 11% | 100% |
| Serbian → German | 11% | 83% |

Serbian Cyrillic lacks Russian й щ ъ ы ь э ю я ё; Ukrainian and Bulgarian
separate from Russian on 11% of Russian words.

Timing references: attestation judgement on the pool, median 0.923 s, p90 7.190 s
(`decision-jev-attestation.md`); whole article ~2.0 s median, 3.8 s p90
(`decision-llm-backend.md`). The pool is measured fine at a couple of dozen requests
a day; past that its fallbacks are 20–60× slower — which is why the helper is gated on
a refusal rather than asked of every open word (that would add a third call to
83–100% of words when T is English or German).

Placeholder widths (built CSS, Chromium and WebKit, 360 px viewport → 294 px of text
room): «Текст или !русское слово» 193, «!английское» 219, «!азербайджанское» 269
(longest in the directory), «Текст или !слово на суахили» 215.

## The new call (reverse prompt)

- `build_reverse_prompt(language, word, target)` and
  `parse_reverse(raw, language, target)` in `src/echo_words/prompt.py`, next to
  `build_attestation_prompt` / `parse_attestation` (`prompt.py:307`, `:316`).
- Asks: "«word» is a word in T. Give the S words for it, one per meaning, commonest
  meaning first, each with one S example sentence that uses it in that meaning. Say
  which T word you read it as. If it is not a T word or expression, or is a sentence,
  say so."
- Answer JSON, strict:
  `{"verdict": "word" | "not_a_word" | "sentence", "read_as": str,
  "equivalents": [{"word": str, "example": str}, ...]}`, at most 6 equivalents.
- Validation in `parse_reverse`: verdict known; for `word`, ≥1 equivalent; each
  `word` passes `validate_word(word, S)`; each `example` passes `validate_text`,
  contains the equivalent under `fold_for_match`, and passes
  `sentence_is_source_language(example, S, T)` — the letter test the card applies to
  its sentences. An example failing any of these is dropped and its equivalent stays
  as a bare chip; the answer itself does not fail. Unusable → `None`.
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
  - The reverse call is `reported` (it is the entry's first answer, and the only one
    when it fails); the helper is not, being a judgement beside the answer like the
    attestation.
- The same prompt serves `!`, letters and the helper. The helper reads only
  `verdict == "word"` as "this is a T word".

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
    S validation, and that must not stop it from reversing.
  - `reverse = "forced"` for `!`; `"letters"` when `shape is None`, `reads_as_target`
    and not `reads_as_source`; otherwise `None`.
  - A reverse candidate gets no script or letter check (rule 1): `plain_unit` strips
    the punctuation off its edges, and only emptiness and length are tested. Empty →
    the existing `word.empty` hint. Within `MAX_WORD_LENGTH` → a reverse job. Longer,
    from letters, with the held S hint `None` → the ordinary S job (rule 7).
    Otherwise longer → 400 `reverse.words_only`.
  - Not a reverse candidate → the held S hint is raised as today.
  - Pass `reverse` and `source_ok` (the held S hint was `None`) to
    `pipeline.enqueue`. Add `reverse` to the fingerprint (`SubmissionFingerprint`,
    `:69`) and to `SubmissionAccepted` (`:230`) as `"forced" | "letters" | None`: the
    PWA shows the pending line for both, and retries with `!` only for `"forced"`
    (a letters retry triggers again by itself).
  - New `GET /api/target` → `{"code": <T's directory code> | null, "name": <T as
    configured>}`. The PWA reads T's and S's names from `/api/languages/catalog`,
    which `App.vue` already fetches and caches at start (`refreshReferences`); a
    target outside the directory has only its configured name. `/api/languages`
    keeps its shape: it carries only the code and the endonym.
- `pipeline.py`
  - `Job.reverse: Literal["forced", "letters"] | None` and `Job.source_ok: bool`.
  - `process_word` (`:516`) becomes a loop over one attempt:
    `while job is not None: job = await self._attempt(job)`. The helper path ends an
    S attempt (whose `finally` cancels that attempt's audio, attestation and helper)
    and returns the resolved job to start over with.
  - Reverse resolution runs before the audio task and the attestation are created
    (`:520`, `:549`), and runs the reverse call as routed above:
    - `word` → set `entry.word = first.word`, `entry.typed_word = job.word`,
      `entry.read_as` (when it differs from the typed word),
      `entry.context = first.example`, and publish `reset` carrying those four (plus
      `reverse_by_helper`). Continue with `replace(job, word=first.word,
      context=first.example, intent="unit", reverse=None)` — the chip path. From here
      `ControlState`, `shown_spelling`, undo, rebuild, switch, delete and the detail
      article all read the equivalent, and the typed T word is never voiced. Keeping
      `entry.word` as the typed word instead would leave the rail, the dictionary link
      (`EntryCard.vue:290`) and the unattested, misspelling, delete and retry messages
      (`EntryCard.vue:258-283`, `:491`, `:575`) naming «стол».
    - `not_a_word` / `sentence` → if `reverse == "letters"` and `source_ok`, continue
      as the ordinary S job with `reverse=None` and no helper (rule 7). Otherwise
      finish the entry with `card_status` `reverse_not_a_word` / `reverse_sentence`
      (and the same code as its action, so neither counters nor undo treat it as
      stored), no card, no audio.
    - No usable answer from pool or paid → `_fail`.
  - Equivalents: when there is more than one, the others become the entry's segments
    — `Segment(label=word, reason="", context=example)` with
    `segment_kind = "equivalents"` — replacing the article's own sense chips for the
    carded word (`_segments_for`, `:1301`). With a single equivalent, the article's
    sense chips stay. They are kept even when the attestation refuses the first
    equivalent, because each one is judged again when tapped.
  - Helper (rule 3):
    - Eligible: kind `submit`, `reverse` is `None`, not a chip, a single word, letters
      proved nothing (never the case for a target outside the directory, rule 2).
    - Started by a done-callback on the attestation task the moment a refusal lands
      (pool only, `reported=False`, trace `-helper`), so it starts whether the refusal
      arrives mid-stream or after the article has ended. Owned like `_Attestation`
      and cancelled in the attempt's `finally`.
    - Mid-stream: each delta polls it. `word` → abandon the S attempt by leaving the
      loop (`aclosing` closes the completion, and an abandoned stream is not rated)
      and return the resolved job, with `reverse_by_helper` set, built from the
      helper's answer — no second reverse call.
    - After the stream: `attestation.result()` as today, then the helper is waited for
      up to `ATTESTATION_GRACE_SECONDS`. `word` → as mid-stream (the completed S answer
      has already been rated as usable, which it was). Anything else, or no answer in
      time → the ordinary S result; a refusal with the helper unanswered sets
      `reverse_offered`.
  - Typo hand-over veto. A declared typo hands the pool answer to the paid model
    inside `_steps_up` (`backend.py:340`). Delaying that does not save the money: the
    request is frozen when the stream opens (`backend.py:518`), before any helper
    exists, and once `_steps_up` returns `True`, `_paid_replacement` buffers the whole
    paid answer before the pipeline sees a delta (`backend.py:301-327`). So
    `CallRequest` gains `before_hand_over: Callable[[], Awaitable[bool]] | None`,
    awaited only on the hand-over branch: `False` → the pool answer stands and no paid
    call is made. The pipeline passes it for helper-eligible jobs. It waits for the
    attestation (up to the grace) and, when a helper has started, for its answer (up
    to the grace), and returns `False` when the helper says `word`. That adds at most
    twice the grace, only to a typo hand-over of a single open-letter word. A pool
    miss still steps up at once: the reader has already waited out the whole budget
    there.
  - The new fields reach the page on two events: the reversal on `reset`, and
    `reverse_offered` on `done`, whose payload is an explicit dict (`:1035`), not
    `entry.public()`.
- `history.py`: `Entry` (`:15`) gains `typed_word`, `read_as`, `reverse_by_helper`,
  `reverse_offered`, all in `public()`. `SegmentKind` (`:11`) gains `"equivalents"`.
  `_reset_reused_entry` keeps the first three across a switch or a rebuild and clears
  `reverse_offered`.
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
  `read_as`, `context` and `reverse_by_helper` when present, as it already does
  `detail_html`. It also sets `requested_shape: "unit"` and `requested_reverse: false`,
  so a retry after the reversal resends the equivalent as a chip.
- Retry (`AddView.vue:180`) restores the prefixes from the receipt: `!` when
  `requested_reverse` is `"forced"`, and `lookup_only`, which `sendWord` always posts
  as `false` today — so a failed `?word` currently retries as a card.
- Entry header: «стол → table» when `typed_word` is set; «сотл → стол → table» when
  `read_as` differs from it.
- Equivalent chips render like sense chips; tapping one submits `{word, shape: "unit",
  context}` as chips do today.
- Outcomes: `reverse_not_a_word` → ru «Модель не считает «{word}» словом — проверьте
  написание.», en "The model does not take «{word}» for a word — check the spelling.";
  `reverse_sentence` → ru «Обратный перевод — только для слов и выражений.», en
  "Reverse translation takes words and expressions only."
- `reverse_offered` → button ru «Искать как {adj T} слово», en "Look it up as a word in
  {Russian}": submits `!` + `entry.word` as a new submission.
- `reverse_by_helper` → line ru «Принято за {adj T} слово», en "Read as a word in
  {Russian}", and button ru «Это {adj S} слово», en "It's a word in {Serbian}": deletes
  the entry's card when it has one (`card_status === "added"`), then submits
  `typed_word` with `shape: "unit"`, which rule 4 keeps out of reverse.
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
- `tests/test_prompt.py`: prompt names S and T; `parse_reverse` accepts the three
  verdicts; drops an example that does not contain its word or fails the letter test;
  rejects bad JSON, empty equivalents and equivalents failing S validation.
- `tests/test_api.py`: `!` on every tab; Cyrillic on English auto-reverses; a chip with
  Cyrillic does not; reverse over 50 chars → 400 `reverse.words_only`; on the Serbian
  tab, text over 50 chars with a Russian-only letter is accepted as Serbian text
  (rule 7); `!` takes anything non-empty within the bound with no script check —
  `!стoл` with a Latin o, digits, `!ねこ` with a target outside the directory; `!` alone → `word.empty`;
  the receipt carries `reverse`; `/api/target` for a directory target and for one
  outside it.
- `tests/test_backend.py`: `before_hand_over` is awaited only on the hand-over branch;
  `False` → no paid stream opened and the pool answer stands; absent → today's
  behaviour; a pool miss steps up without awaiting it.
- `tests/test_pipeline.py`: `!` → card for the first equivalent; `reset` carries
  `word`, `typed_word`, `read_as`, `context`; `shown_spelling`, undo and rebuild use the
  equivalent; no audio for the typed word; the other equivalents as chips; a single
  equivalent keeps the sense chips; the reverse call is rated; pool silent → paid
  inside the cascade; pool unusable → the pipeline's own `stream_paid`; paid refused →
  the entry fails; `not_a_word`; `sentence`; letters + `not_a_word` on Serbian →
  continues as Serbian, no helper (rule 7); `!` + `not_a_word` on Serbian → stays not
  a word; an equivalent the attestation refuses → refusal shown, chips kept;
  `typed_word` survives a switch.
- `tests/test_attestation.py` (helper): it starts when a refusal lands mid-stream and
  when one lands after the article ended; `word` mid-stream → S attempt abandoned
  unrated, card for the equivalent; `word` after the stream; negative → S result;
  late → `reverse_offered`; a declared typo with helper `word` → no paid call made; a
  declared typo with a negative helper → paid hand-over as today.
- `tests/test_history.py`: the new fields round-trip; the `"equivalents"` kind.
- Webapp unit tests (`webapp/tests/`): placeholder for ru/en, declined and
  indeclinable names, and with no target; the pending line; `reset` applies the
  reversal; retry restores `!` and `?`; header with and without `read_as`; both
  outcome messages; both buttons; the delete is skipped when there is no card.
- Browser (`tests/test_e2e_reverse.py`, Chromium, gate-held fake): the pending line
  while the reverse call is held; «стол → table»; chips; «Искать как русское слово»;
  «Это сербское слово»; the failure message, and its retry keeping the `!`.
- `tests/test_one_note_bench.py`: the new bench action's scoring.

## Bench (Russian target, pool)

New `run-reverse` action in `experiments/one_note_bench.py` (next to
`run-corrections`, `:2067`), fixtures in `experiments/reverse_items.py`, a report
section and review-packet items. Fixtures fixed before the run, each into English,
German and Serbian unless marked:

| Requirement | Words | Must hold |
|---|---|---|
| one clear meaning | стол, окно, собака | correct equivalent |
| several meanings | ключ, коса, лук, мир | commonest first; each example in its own meaning |
| inflected form | столы, ключей | `read_as` the dictionary form |
| expression | в конце концов, сломя голову | an equivalent expression |
| no direct equivalent | тоска, авось | a close word, not an invention |
| misspelling | сотл | `read_as` «стол» |
| not a word / sentence | фывапр / я иду домой | `not_a_word` / `sentence` |
| helper, T words (sr only) | город, книга, девушка, собака | `word` |
| helper, S typos (sr only) | прозр, сврка | not `word` |
| helper, hard case (sr only) | кашка (typo of кашика, also Russian) | reported separately |
| Russian-keyboard Serbian (sr only) | йош (још), моя (моја) | `not_a_word` for йош, which rule 7 then hands to Serbian; `word` → моја for моя |

The helper only sees words the Serbian attestation refuses, so the same run also asks
the existing attestation prompt (the bench's `attestation` shot kind) about every
helper fixture in Serbian. A helper fixture the attestation accepts is reported as
"helper not reached": that is a finding about the attestation, and it is not scored
against the reverse call.

About 64 calls: 48 for the three-language rows, 9 reverse calls for the Serbian-only
rows, 7 attestation calls. Also record the reverse call's median and p90 latency.

```
uv run python experiments/one_note_bench.py run-reverse --resume \
  --wait 180 --pace 2 --concurrency 1 --out experiments/.bench-reverse
uv run python experiments/one_note_bench.py report --out experiments/.bench-reverse
```

Read availability before results (workhorse model present, answers not far below
the previous run); an exhausted pool voids the run — resume, never restart. Then a
fresh agent that did not run it reviews every item of `review-packet-*.json`, in the
same turn, judging each example as the card's front sentence it becomes and not only
as an instance of its meaning. The decision goes into
`spec/decision-reverse-translation.md`.

## Specs and docs

- `spec/functional-description.md` input section, item 2 ("The language is always
  the user's explicit selection, never guessed…"): replace with rules 1–7 as
  behaviour; describe the reverse entry.
- `spec/functional-description.md`, the paid step ("A payload that no answer of that
  request could carry does not buy a paid one by itself"): state the exception — a
  reverse answer the pool cannot make usable is bought from the paid model without
  asking, because nothing is on the page yet.
- `spec/decision-product.md`, the "Multiple source languages…" guard: "The tab
  chooses the deck and the source language. Whether a word is in the target language
  is decided by its letters where they prove it, by `!`, or, for a single word the
  source language rejects, by a separate check that asks only that."
- New `spec/decision-reverse-translation.md`: the measurements above, the reason for
  rule 7, the dropped alternatives (model detection inside the article payload;
  asking the helper on every open word; Wiktionary translation tables; a q/w/x/y
  column), the bench result.
- `docs/src/{ru,en}/index.md` "Что умеет / What it does": one bullet for `!` and `?`.
- `CLAUDE.md` already lists this plan among the open ones; set it back to "One is
  open" when the work lands.
- `uv run inv readme-screenshots` after the placeholder and panel change.

## Order of work

1. Letter functions (`reads_as_target`, `reads_as_source`,
   `sentence_is_source_language` on top of them) + tests. Prefix
   parsing waits for step 4, so that `!` is never accepted and silently dropped
   before the pipeline can act on it.
2. Reverse prompt + parser + tests.
3. Bench action + fixtures + attestation shots + its test; run the bench, fresh
   review, record. The prompt is the riskiest part, so it is measured before the
   pipeline is built on it.
4. Prefix parsing + API (`!`, letters, rule 7, `/api/target`) + pipeline reverse
   resolution + history + tests.
5. Helper + hand-over veto + tests.
6. Frontend: placeholder, pending line, `reset` handling, retry, header, chips,
   outcomes, buttons, panel removal + tests.
7. Browser tests.
8. Specs, docs, screenshots; delete this plan.

Each step ends with `uv run inv pre` and `uv run inv test` fully green. No push and
no deploy without the operator's explicit approval for that act.
