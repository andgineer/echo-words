# Implementation plan — phrases and sentences

Delete this file once the work has landed. What outlives it is
`spec/decision-phrases-and-sentences.md` (the decision and its measurements)
and the sections it adds to `spec/functional-description.md`.

The design is settled and measured; nothing here re-opens it. Read the decision
record first — this file only says how to build what it decided.

---

## Scope

Three behaviours, in dependency order:

1. A multi-word input is analysed **whole**. The forced word picker goes away.
2. Running text is translated and explained, produces **no note**, and comes
   back with the units worth looking up on their own.
3. The backend decides which of the two an input is, so the share-sheet path
   gets the same behaviour as the app without a second copy of the rule.

Out of scope, deliberately: audio for running text, a deeper analysis of a
sentence, rebuilding a sentence, per-segment audio, highlighting units inline
in the rendered answer.

---

## Step 1 — the shape rule

**New `src/echo_words/shape.py`.** No language knowledge: the rule is
punctuation and word count, identical for every configured language.

```python
Shape = Literal["unit", "text"]

MAX_UNIT_WORDS = 4
TERMINAL_MARKS = ".!?…"
INTERNAL_MARKS = ",;:—–"

def word_count(text: str) -> int: ...
def classify(text: str) -> Shape: ...
```

`classify`, in this order — the first match wins:

1. one word (after stripping edge punctuation) → `"unit"`, whatever trails it
2. any character of `INTERNAL_MARKS` present → `"text"`
3. last character in `TERMINAL_MARKS` → `"text"`
4. longer than `MAX_WORD_LENGTH` → `"text"`
5. more than `MAX_UNIT_WORDS` words → `"text"`
6. otherwise → `"unit"`

`word_count` tokenises the way `experiments/route.py` does: split on
whitespace, strip leading and trailing non-word characters, drop what is left
empty. Port that regex verbatim — it is the tokenisation the measurement used.

Import `MAX_WORD_LENGTH` from `languages`; do not duplicate the number.

**Tests — `tests/test_shape.py`.** Table-driven over the same fixtures the
sweep used, so a regression shows up as the sweep would have caught it:

- every ordinary word, with and without a trailing period → `"unit"`
- `"Rad fahren"`, `"voziti bicikl"`, `"die Nase voll haben"`,
  `"unter die Lupe nehmen"`, `"von Zeit zu Zeit"` → `"unit"`
- `"Er steht jeden Morgen um sechs auf."`, `"Он се синоћ вратио кући."`,
  `"Sve mi se čini da nešto nije u redu."` → `"text"`
- `"Wie geht es dir?"` → `"text"` (terminal mark at four words)
- `"не пада ми на памет"` → `"text"` (five words — the one benign misroute the
  decision record accepts; assert it deliberately so the trade-off is visible
  in the suite rather than discovered later)
- a 60-character unpunctuated string → `"text"`

---

## Step 2 — validating running text

**In `src/echo_words/languages.py`.**

```python
MAX_TEXT_LENGTH = MAX_CONTEXT_LENGTH

def validate_text(text: str, language: Language, locale: str = DEFAULT_LOCALE) -> str | None: ...
```

`MAX_TEXT_LENGTH` is defined as `MAX_CONTEXT_LENGTH` and not as a second
number: tapping a suggested unit re-submits it **with that text as its
context**, so text longer than the context bound would be silently truncated on
the way back in. One bound, one meaning.

`validate_text` rules:

- empty → `word.empty`
- longer than `MAX_TEXT_LENGTH` → a new message key `text.too_long`
- split into words the way `shape.word_count` does; each word is put through
  the existing per-word script check. Digits and punctuation between words are
  skipped, so a sentence keeps its commas, numbers and quotation marks.
- a word whose letters are outside the language's scripts → the existing
  `word.script` hint, unchanged
- a word mixing Latin and Cyrillic → the existing `word.mixed_scripts` hint.
  Keep it per word, not per text: Serbian legitimately writes either script,
  and the measurement found the pool emitting a hybrid *word* (`возiti`), which
  is exactly what this catches.

Add `text.too_long` to both locales in `src/echo_words/i18n.py`.

**Tests — extend `tests/test_languages.py`:** a clean German sentence passes; a
Serbian sentence in either script passes; a sentence with a Cyrillic word in a
German text is refused with the script hint; a hybrid word is refused; a
501-character text is refused; punctuation and digits alone never trigger the
non-letter hint.

---

## Step 3 — the running-text prompt and its payload

**In `src/echo_words/prompt.py`.** Add `_TEXT_PROMPT`, ported **verbatim** from
`experiments/prompts/sentence-v1.txt` — that exact wording is what the numbers
in the decision record were measured on, so it is copied, not rewritten. Braces
around the JSON schema must be doubled, since the module renders with
`.format()`.

```python
def build_text_prompt(language: Language, text: str, target_lang: str) -> str: ...
def extract_segments(raw: str, language: Language) -> list[Segment] | None: ...
```

`extract_segments` mirrors `extract_card`: find `CARD_DELIMITER`, hand the tail
to the parser, return `None` when the payload is unusable. An **empty list is a
success, not a failure** — the measurement's negative control is that a
trap-free sentence comes back with no segments at all, so `None` and `[]` must
stay distinguishable all the way to the quality rating.

**New `src/echo_words/segments.py`**, alongside `card.py` rather than inside
it — `card.py` is note data, this is not.

```python
MAX_SEGMENTS = 5
MAX_SURFACE_LENGTH = 120
MAX_REASON_LENGTH = 200

@dataclass(frozen=True)
class Segment:
    label: str
    surface: str
    reason: str

class SegmentParseError(ValueError): ...

def parse_segments_payload(payload: str, language: Language) -> list[Segment]: ...
```

Parsing rules:

- one JSON object, ignoring anything after it — reuse the `raw_decode`
  approach `card.py` already uses
- the segment list missing or not a list → `SegmentParseError`
- more than `MAX_SEGMENTS` entries → keep the first `MAX_SEGMENTS`, do not
  raise: a model that offers six useful units has not produced a broken answer
- **a label is dropped, and its whole segment with it, when
  `validate_word(label, language)` returns a hint.** This is the same guard the
  spelling suggestion lives under and for the same reason: one tap turns a
  label into the front of a real note. Dropping is silent — a dropped segment
  is not an error.
- a segment with no usable label, or a non-object entry, is dropped
- `surface` and `reason` are optional strings, trimmed and truncated to their
  bounds; they are display-only and never become a word

**Tests — `tests/test_segments.py`:** a well-formed payload; an empty list is
valid; a label that fails validation is dropped while its neighbours survive
(use `"vratiti се"`, the real hybrid the benchmark produced); a seventh segment
is truncated away; a missing list raises; junk after the object is ignored;
over-long `surface`/`reason` are truncated.

**Tests — extend `tests/test_prompt.py`:** the text prompt fills every slot and
leaves no `{...}` behind; the per-language hint reaches it; `extract_segments`
returns `None` without a delimiter and `[]` for an empty list.

---

## Step 4 — the pipeline

**In `src/echo_words/pipeline.py`.**

- `Job` gains `shape: Shape = "unit"`.
- `Entry` (in `history.py`) gains `segments: list[dict] = field(default_factory=list)`.
  `public()` already serialises by `asdict`, so it rides along for free.
- New status constant next to `LOOKUP_ONLY_STATUS`, written the way its
  neighbours are: `TEXT_STATUS = "👁 text — no card"`.

In `process_word`, when `job.shape == "text"`:

- **no audio task is started.** Audio is word-and-phrase only — a decided
  point, and running text produces nothing the audio would be attached to.
  `entry.audio_file` stays `None`, and the status line must not claim
  `NO_AUDIO_STATUS`: a text answer is not missing its audio.
- the prompt is `build_text_prompt`
- `job.lookup_only` is forced `True` at enqueue time, not here, so every later
  branch that reads it is already right
- after the stream, `extract_segments` replaces `extract_card`
- `record_quality(1.0 if segments is not None else 0.0)` — parsed, not
  non-empty
- `_store_card` returns `StoreResult(TEXT_STATUS, "lookup")` before it looks at
  anything else. Action `"lookup"` is deliberate: it keeps the existing
  counters and makes undo report "nothing to undo" with no new branch.
- `entry.segments = [asdict(s) for s in segments or []]`
- `entry.detail_available = False`, and `suggestion` stays `None` — neither
  control belongs on a sentence
- the `done` event payload gains `"segments"`

Refusals on a text entry:

- `request_rebuild` raises `BackendError` with a reason — there is no note to
  rebuild. Message via `i18n`.
- `request_switch` already needs a suggestion, which a text entry never has;
  no change.
- `request_detail` refuses the same way as rebuild.

`enqueue` gains `shape: Shape = "unit"` and forces `lookup_only=True` when the
shape is `"text"`.

**Tests — extend `tests/test_pipeline.py`:**

- `test_running_text_is_explained_without_a_card_or_audio` — the audio fetcher
  is never called, `add_note` is never called, the status is `TEXT_STATUS`, and
  the status carries no missing-audio mark
- `test_segments_reach_the_done_event_and_the_history`
- `test_a_trap_free_text_finishes_with_no_segments_and_still_rates_as_good` —
  the empty-list case, asserting `record_quality(1.0)`
- `test_an_unparsable_text_payload_rates_as_a_failure_without_losing_the_answer`
- `test_a_label_that_would_be_refused_as_input_never_becomes_a_segment`
- `test_rebuild_and_detail_are_refused_on_a_text_entry`

---

## Step 5 — the API

**In `src/echo_words/api.py`.**

- `_MAX_WORD_INPUT` is the transport guard on the submitted string and is
  currently `MAX_WORD_LENGTH * 4` — **200 characters, which would reject a
  500-character sentence before the handler ever sees it.** Raise it to
  `MAX_TEXT_LENGTH * 4`. Missing this makes every long paste a 422 with no
  usable hint.
- `WordSubmission` gains `shape: Shape | None = None`. Absent means "classify
  it"; present means the caller already knows. **The suggested-unit tap sets it
  to `"unit"`**, which is what stops a five-word label from being classified as
  running text and looping the user back into a sentence answer.
- `submit_word`:

  ```python
  text, lookup_only = normalize_submission(submission.word, submission.lookup_only)
  shape = submission.shape or classify(text)
  hint = validate_text(text, language, locale) if shape == "text" else validate_word(text, language, locale)
  ```

  The `?` prefix keeps working for both shapes — `normalize_submission` runs
  first and strips it, so a text ending in `?` is untouched while one starting
  with it is a lookup-only marker, exactly as now.
- the submission fingerprint gains `shape`, so a retried request id that
  changes shape is the conflict it already is for a changed word
- the field stays named `word`, not `text`. Renaming it would break the
  Shortcut already installed on the user's phone for no gain.

**Tests — extend `tests/test_api.py`:**

- `test_a_sentence_is_accepted_and_routed_without_a_card`
- `test_a_collocation_is_accepted_whole` — asserting the pipeline saw
  `shape="unit"` and the full string as the word
- `test_an_explicit_shape_overrides_the_classifier` — a five-word label with
  `shape="unit"` is validated as a word
- `test_an_over_long_text_is_refused_with_a_hint_not_a_422`
- `test_a_retried_request_id_with_a_different_shape_conflicts`

---

## Step 6 — the app

**`webapp/src/views/AddView.vue`.**

- **Delete `splitPhrase`, `picker`, `chooseWord` and the whole picker block.**
  This is the change the user asked for: a multi-word input is no longer a
  question. `submit()` becomes a straight `sendWord(word.value.trim(), lookupOnly.value)`.
  The leading-`?` handling goes too — the backend has always done it.
- `sendWord(text, lookupOnly, context = "", shape = null)` puts `shape` in the
  body when given.
- Render the suggested units under a finished entry that has any:

  ```
  <div v-if="entry.segments?.length" class="segments">
    <p>{{ t("add.segments") }}</p>
    <button v-for="s in entry.segments" :key="s.label"
            class="btn-inline segment" :disabled="busy"
            @click="sendWord(s.label, entry.lookup_only, entry.word, 'unit')">
      {{ s.label }}<span v-if="s.surface" class="segment-surface">{{ s.surface }}</span>
    </button>
  </div>
  ```

  `s.reason` goes in a `title` attribute or a muted line under the row.
- **Interpolation only, never `v-html`, for `label`, `surface` and `reason`.**
  The sanitizer covers the analysis; these three are model-authored strings that
  reach the page unsanitised, and Vue's text interpolation is what makes that
  safe. This is a hard rule, not a preference.
- Hide the rebuild and detail buttons when `entry.segments` is present or the
  entry has no card, so a refusal the backend would issue is never offered.

**`webapp/src/composables/useEventStream.js`** — no change. `done` spreads the
whole payload into the entry, so `segments` arrives on its own.

**i18n, both `en.js` and `ru.js`** — `webapp/tests/i18n.test.js:36` asserts key
parity, so every key lands in both:

- remove `add.pick`
- add `add.segments` — "Worth looking up on their own:" / «Стоит разобрать
  отдельно:»
- add `add.textNoCard` — the entry meta for a text answer
- update `add.aboutIntro` and add `add.aboutText` describing the two shapes and
  that a sentence makes no card

**Tests — `webapp/tests/AddView.test.js`:**

- a multi-word input posts the whole string and renders no picker
- suggested units render as buttons from `entry.segments`
- tapping one posts its label with the sentence as `context` and
  `shape: "unit"`
- `surface` and `reason` are rendered as text — assert that a label containing
  markup appears escaped
- rebuild and detail are absent on a text entry

Tag the new cases with the existing taxonomy:
`FEATURE.INPUT_AND_LANGUAGES` for submission and routing,
`FEATURE.ANSWER_DELIVERY` for the suggested-unit row.

---

## Step 7 — the Shortcut, and the docs

**`docs/src/en/pwa-install.md` and `docs/src/ru/pwa-install.md`.** The Shortcut
currently reproduces the app's picker by hand — Match Text with a regex, Choose
from List, two branches building the dictionary. All of it goes:

1. accept text from the Share Sheet
2. build a dictionary: `word` = the Shortcut input, `lang` = a configured code,
   `lookup_only` = false
3. POST it

Rewrite the closing paragraph: shared prose now comes back as a translation
with the units worth looking up, rather than asking which word was meant.

**`spec/functional-description.md`:**

- **Core flow, step 1** — the paragraph beginning "A phrase instead of a word
  means context" is now wrong end to end. Replace it: a multi-word input is
  analysed whole; running text is translated, explained and produces no note;
  the backend decides which; a suggested unit is one tap from being an ordinary
  submission carrying the text as its context.
- **Analysis content** — a short subsection on what a running-text answer
  contains and what the suggested units are.
- **Anki cards** — state that running text never produces a note.
- **Pronunciation audio** — running text is not voiced; add it to the existing
  scope sentence rather than writing a new rule.
- **UI actions** — the suggested-unit row; rebuild and deeper analysis do not
  apply to running text.
- Link `decision-phrases-and-sentences.md` from the spec index paragraph in
  `CLAUDE.md` alongside the other decision records.

---

## Order and checkpoints

Bottom-up, `uv run inv pre` after each numbered batch, never once at the end:

1. Steps 1–2 (shape, validation) + their tests
2. Step 3 (prompt, segments) + tests
3. Step 4 (pipeline) + tests
4. Step 5 (API) + tests
5. Step 6 (app, i18n) + tests
6. Step 7 (docs, functional description) — then delete this plan

## Verification

```
uv run inv pre     # all hooks pass, pyrefly 0 errors
uv run inv test    # pytest green, the frontend suite run and not skipped
```

The behaviour itself was measured before the build and does not need
re-measuring to land. If either prompt is edited on the way in, that changes
the numbers the decision rests on, and the arms have to be re-run:

```
uv run python experiments/backend_bench.py pool --lang de sr --shapes sentence \
    --pace 5 --concurrency 1 --wait 25 --tag sent-v2
uv run python experiments/backend_bench.py pool --lang de sr \
    --shapes idiom collocation --as-sentence \
    --pace 5 --concurrency 1 --wait 25 --tag colloc-as-sent-v2
uv run python experiments/backend_bench.py report --phases sent-v2 colloc-as-sent-v2
uv run python experiments/route.py     # free, no models, run it after any change to step 1
```
