# Interface rework — language buttons, the word rail, the language editor

## What this is

The words screen was designed for one word at a time and a feed below it.
In use there are a couple of dozen entries, one studied language, and a
reader who wants to step back to something read a minute ago. This plan
rebuilds that screen around a **rail of words over a single swipeable
card**, adds a **language editor to the PWA**, and makes the app **follow
the system light/dark theme**.

Everything here was settled against an interactive design canvas:

    https://claude.ai/code/artifact/1333eac5-9952-4eb5-8be0-2e3f77dd36a7

The canvas is the visual reference for layout, spacing, states and copy.
Read it before starting M2. It carries four artboards — the words screen,
the language list, the language settings, and a light/dark token sheet —
plus sticky notes recording why each decision went the way it did.

Baseline for every line reference below: commit `d3403af0`.

---

## Settled decisions — do not re-open

These were argued through and decided. Implement them; do not redesign.

1. **Languages are buttons, not a dropdown.** There is rarely more than
   one studied language. Two clicks to change something that is usually
   fixed is wrong, and a `<select>` hides how many there are. The row
   sits above the whole screen, not inside the form, because it filters
   the input *and* the rail.
2. **The rail is the index; the card is the reader.** A carousel alone
   fails past three entries — dots cannot say which word is behind them.
   A collapsed feed fails too — reaching a neighbour means scrolling past
   a whole expanded card. Word chips over one card solve both: the eye
   scans words, one tap opens any of them.
3. **The card is swiped**, and every switch is a movement. A tap that
   silently swaps text reads as nothing having happened.
4. **Every tap answers before the network does.** Press state, then
   motion, then — if a model is being asked — a progress strip, a line
   saying roughly how long, and a pulsing dot on that word's chip so the
   reader can swipe away and still see it running. This applies to the
   fast free call as much as to the ten-second paid one.
5. **No "lookup only" checkbox.** Every card carries "delete", Anki
   calls are not worth saving, and a reader who typed a word does not
   know it. The one reason not to learn it — the word is too odd to be
   worth a card — is rare and is handled by deleting afterwards. The `?`
   prefix keeps that path for anyone who wants it and costs no pixels.
6. **Deletion is per card, not "undo the last one".** "Undo" asks the
   reader to remember what was last; the card in front of them is what
   they mean.
7. **One paid action, named for where the answer lands.** "Полная
   статья" is the extended prompt: every sense, origin, shades, usage —
   it opens inside the card and never touches Anki.
8. **Nothing on the card is said twice.** The model name moved to the
   card's top right; the language is already named by the active button;
   the bottom meta line is gone. A sentence card shows no card status —
   the presence of word chips and the absence of a delete button say it.
9. **The chips need no caption.** "Слова и сочетания — нажмите, чтобы
   разобрать" is read once in a lifetime and occupies space forever.
   Filled chips that look pressable say it instead.
10. **The theme follows `prefers-color-scheme`.** Pinning dark was never
    decided, it was just never revisited.

## Deferred — record, do not build

**Rewriting an existing Anki note with the paid model** (today's
`/api/words/{entry_id}/rebuild`). The reader has no grounds to ask for
it: they never see the note, and the plain translation a card needs is
what the free model gets right first time. The small chance that the paid
model would translate differently is ignored for now. The endpoint and
its pipeline path stay; only the button goes.

## The bench gate does not apply, and M3 is built so it keeps not applying

`CLAUDE.md` requires a real-model run for anything that changes what the
app says to an LLM or what it does with the answer. No milestone here
does. No template, prompt fragment, payload contract or parser is read
or written, and no existing value that reaches a prompt is edited.

The one place this could have gone wrong is `prompt_hints`. It is not
inert configuration: it is interpolated into `_SELECTED_PROMPT` and
`_OPEN_PROMPT` as `{source_hints}` (`src/echo_words/prompt.py:247`), so
the string in `languages.toml` is literally part of what the model is
asked. Serbian already ships one: `"for nouns give gender and plural, for
verbs give aspect"` (`languages.example.toml:32`).

**So the editor does not expose it** — see M3. A prompt fragment stays in
the repository, where a change to it goes through review and carries the
gate, instead of becoming a text box that can silently rewrite every
future answer for a language with nothing to catch it.

If a milestone drifts into prompt text anyway, stop and run the bench.

---

## M1 — The theme follows the system

Small, isolated, and worth doing first: M2 touches every colour on the
screen, and doing it after the tokens exist avoids a second pass.

### Where dark is pinned

- `webapp/src/assets/base.css:9-31` — the whole palette in `:root`.
- `webapp/index.html:9` — `<meta name="theme-color" content="#16213e">`.
- `webapp/vite.config.js:26-27` — manifest `theme_color`, `background_color`.

### base.css

Keep the existing dark values in `:root` — every `<style scoped>` block
in the app was written against them, so leaving them as the base means a
missed override degrades to today's behaviour rather than to an unstyled
page. Add `color-scheme: light dark` to `:root`, then override the tokens
under `@media (prefers-color-scheme: light)`:

```css
:root {
  color-scheme: light dark;
  /* existing dark tokens unchanged */
}

@media (prefers-color-scheme: light) {
  :root {
    --bg: #f4f5fa;
    --surface: #ffffff;
    --surface-2: #dfe3ee;
    --accent: #c81e42;
    --accent-hover: #a81836;
    --text: #1a1a2e;
    --text-muted: #5b6478;
    --success: #16a34a;
    --warning: #b45309;
    --error: #dc2626;
    --field: rgba(26, 26, 46, 0.03);
    --field-deep: rgba(26, 26, 46, 0.06);
    --border: rgba(26, 26, 46, 0.1);
    --border-strong: rgba(26, 26, 46, 0.16);
    --nav-stats: #5b5bd6;
    --nav-status: #0e8fa8;
  }
}
```

The accent is darker in light mode on purpose: `#e94560` gives white
text on a filled button about 3.9:1, under the 4.5:1 floor. `#c81e42`
reaches 5.6:1. Do not "restore" the brand red here.

### index.html

Two tags, so the browser chrome follows too:

```html
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)" />
<meta name="theme-color" content="#16213e" media="(prefers-color-scheme: dark)" />
```

### vite.config.js

A web-app manifest carries one colour and cannot be media-queried. Leave
`theme_color` / `background_color` dark; they only govern the installed
app's splash. Note it in the commit message rather than inventing a
mechanism.

### Audit before calling it done

`grep -rn "#[0-9a-fA-F]\{3,6\}" webapp/src --include=*.vue` and check each
hit survives both themes. `color: #fff` on a filled accent button is
fine. Anything reading as a surface, a border or body text must become a
token. `var(--warn, …)` is already gone as of `d3403af0`.

### Verification

CSS has no unit test worth writing here. Run `uv run inv dev`, flip the
OS appearance, and walk all three tabs. Confirm no element becomes
invisible and no card loses its edge against the page.

---

## M2 — The words screen

The bulk of the work. `webapp/src/views/AddView.vue` is ~520 lines that
render the form and the whole feed; it comes apart into components.

### New components

- `components/LanguagePicker.vue` — the segmented row of language
  buttons plus the trailing pencil that opens the editor (M3). Reuse the
  `.seg-container` idiom already in `components/HeaderNav.vue:52-76`;
  the buttons are `flex: 1`, accent-tinted when inactive, filled accent
  with the same `box-shadow` when active. With one language the row is a
  single full-width button — it still names the language, and the pencil
  stays reachable.
- `components/WordRail.vue` — the horizontal chip strip. Props: the
  entries for the selected language and the selected entry id; emits the
  id on tap.
- `components/EntryCard.vue` — one entry, everything it shows, and its
  swipe handling.

`AddView.vue` keeps the submit form, the event-stream wiring, and the
help block, and composes the three.

### Form

Delete the field label (`AddView.vue:242`, `:251`), the lookup checkbox
(`:264-267`) and the undo button (`:271`). The placeholder carries the
whole instruction: `add.wordPlaceholder` becomes `"слово или выражение"` /
`"a word or a phrase"`. Delete the `lookupOnly` ref (`:19`), drop it from
the `watch` (`:24`) and pass `false` where `sendWord` wants it — both at
the call in `submit` (`:41`) and at the one in `analyseSegment` (`:47`),
which reads the same ref today. The `?` prefix still works: the server
strips it in `languages.normalize_submission` and ORs the flag.

### The rail

State lives in `AddView` (or a small `useSelectedEntry` composable):
selected entry id per language code. Rules:

- Entries are filtered to `selected.value` — the same language the
  buttons show. This is the filter the whole screen has been missing.
- Newest first, matching `upsertEntry(…, { newest: true })`.
- A new entry — submitted, queued, or created by tapping a word chip —
  becomes the selected one immediately.
- The chip is `max-width: 148px` with `white-space: nowrap`,
  `overflow: hidden`, `text-overflow: ellipsis`, so a sentence shows as
  `Сутра идем на по…` and never crowds the words out.
- On every change of selection, scroll the active chip to the middle of
  the rail: `rail.scrollTo({ left: chip.offsetLeft - rail.clientWidth / 2
  + chip.offsetWidth / 2, behavior: "smooth" })`, guarded so it only runs
  when the selection actually changed. Do this in a `watch` on the
  selected id with `nextTick`, not on every render.
- Style the scrollbar down: `scrollbar-width: thin`, a
  `--border-strong` thumb, 4px tall. macOS otherwise paints a white bar
  across the dark card.
- A chip whose entry is pending, or whose paid call is running, carries a
  pulsing accent dot (`::after`, 6px, `opacity` 1 → 0.2 over 1.1s). A
  pending chip shows the word alone — no `⏳` prefix; the dot says it, and
  a prefix makes the chip jump in width when the answer lands.
- Chips press: `transform: scale(0.94)` over 100ms, matching `.btn:active`
  in `base.css`.

### Movement on every switch

Decision 4 is not satisfied by the press state alone. Whenever the
selected entry changes — a chip tap, a swipe, a language switch, a new
submission — the card **arrives from the side it came from**: set its
`translateX` to `+44px` when moving to a later entry and `-44px` when
moving to an earlier one, with the transition suppressed for that frame,
then release it to `0` on the next tick with `transition: transform
0.18s ease-out, opacity 0.18s ease-out`. Reuse the same transform the
drag writes, so a swipe continues into the settle instead of fighting it.

Swipe itself: pointer events on the card, `touch-action: pan-y` so the
page still scrolls vertically, a 55px threshold, and the card following
the finger with `opacity` easing to about 0.6 at full travel. Do **not**
call `setPointerCapture` — it makes the click land on the capturing
element in Chrome and eats taps on the buttons inside the card. Ignore a
drag that starts on a `button` instead.

### Nothing yet

A language with no entries has no rail and no card — render `add.empty`
where the card would be, as the feed does today (`AddView.vue:277`). This
is the normal state of a language added a minute ago in M3, so it is not
an edge case: check it after every rail change. The rail element itself
is hidden rather than rendered empty, so the form does not float above a
blank strip.

### The card

Order, top to bottom:

1. Head row: the word on the left at `1.15rem/600`; for `shape === "text"`
   a muted uppercase `Предложение` label instead. The **model name** on
   the right, `ui-monospace`, `0.68rem`, `--text-muted`. Empty while the
   entry is pending.
2. For a text entry, the submitted sentence in the existing
   `.entry-source` block.
3. The spelling notice and the unverified notice, unchanged in logic
   (`spellingNotice`, `not_in_references`).
4. The analysis, then the deeper analysis when present.
5. Audio players, unchanged.
6. Segment chips — filled `--surface-2` pills, no border, `min-height:
   36px`, accent fill on hover, `scale(0.94)` on press. **No caption
   above them.** Drop `add.text` / `add.expression` / `add.senses` from
   both catalogues.
7. Card status — omitted entirely when `shape === "text"`.
8. Actions.
9. **No meta line.** Delete `.entry-meta` and its markup
   (`AddView.vue:374-376`, `:499-503`).

**And no pager.** The `‹ 1 / 20 ›` counter with its arrows is not part of
this design and must not be added back: the rail says where the reader is
far better than a number, and the arrows duplicate the swipe. Position is
shown by which chip is centred and highlighted, nothing else.

**Errors keep their place in the card.** An entry that failed is still an
entry in the rail, and one card is all there is to show it in. Below the
analysis slot render, in order: `entry.error` with the retry button
(`add.retry`), `entry.detail_error`, and `entry.control_error` — the same
three blocks the feed has today (`AddView.vue:352-359`, `:377-381`), just
scoped to the selected entry. A failed entry's chip carries no live dot;
it is finished, not running.

### Actions

Two, for a unit entry that has a card:

- `add.detail` → `"Полная статья"` / `"The full entry"`, becoming
  `add.detailReady` → `"Статья готова"` / `"The entry is ready"` once
  `detail_html` is set, disabled from then on.
- **New**: delete this card, `"Удалить из Anki"` / `"Delete from Anki"`,
  in `--error`. Pressing it turns the action row into an inline
  confirmation — `"Удалить карточки для «{word}» из Anki? Разбор
  останется на экране."` with `Удалить` / `Отмена` — never a modal and
  never a `confirm()`. Plural "карточки": one word makes four.

A lookup-only entry gets neither. A text entry gets neither. The rebuild
button is removed (see Deferred).

### Per-card deletion — backend

`pipeline.undo()` (`src/echo_words/pipeline.py:387-402`) already does
everything except find the note from an entry. Add beside it:

```python
async def delete_card(self, entry_id: str) -> str | None:
```

using `self._active_control(entry_id)` (`pipeline.py:1055`) to reach the
`ControlState`, then the same body: `anki.remove_note(note_id,
media_filename)`, `_delete_audio` for the answer audio and, when it
differs, the card audio; clear `note_id` / `media_filename` on the
control; and drop the per-language `UndoState` when it points at the same
note, so a later undo cannot delete it twice.

Expose it as `POST /api/words/{entry_id}/delete-card` next to `switch`,
`rebuild` and `detail` (`api.py:275`+), returning `{"deleted": word}` or
404 on an expired entry. The frontend calls it through the existing
`entryAction(entry, "delete-card")` shape, which already clears
`control_error` first.

Emit a `done`-style event so the entry's `card_status` becomes something
the card can render as `"🗑 карточки удалены из Anki"` / `"🗑 cards
deleted from Anki"`. Add a `card_status` value rather than inventing a
second channel.

Keep `/api/languages/{code}/undo` and `/api/words/{entry_id}/rebuild`
working even though nothing in the UI calls them. Removing them is a
separate decision, and `rebuild` is explicitly deferred, not dead.

### The extended search leads somewhere that can answer

`src/echo_words/lexicon.py:27` sends the reader to
`https://{lang}.wikipedia.org/w/index.php?search="{word}"` — the very
query that just returned zero, on the one source whose register cannot
carry slang. `spec/decision-answer-shape.md:270-275` names this: the sole
residual false warning is `иде ми се`, "a colloquial clause the
encyclopedia has no register for". Change it to a general exact-phrase
web search:

```python
USAGE_SEARCH_URL = "https://duckduckgo.com/?q={query}"
```

with the quoted wording as `q`. Rename the copy: `add.seeUsageSearch`
becomes `"Поискать в интернете"` / `"Search the web"`. `lang` drops out
of the template — check every caller. Tests asserting `wikipedia.org` in
the *search* URL must move; the two `list=search` API calls in
`Wikipedia._search` stay on Wikipedia and must not be touched.

### The browser feed is bounded

`webapp/src/composables/useEntries.js:8-19` grows forever. The server is
already bounded — `History(limit=50)` (`history.py:143`,
`pipeline.py:198`) evicts the oldest finished entry and never a pending
one — but the browser only re-syncs to that on a stream reconnect, so a
tab left open for weeks accumulates everything. Add a hard cap in
`upsertEntry`, matching the server:

```js
const MAX_ENTRIES = 50;
```

Truncate after an insert, never dropping an entry that is `pending`.
Configurable is not wanted; the constant is enough.

### i18n

Both catalogues, or `i18n.test.js › covers every message in both
catalogues` fails.

Remove: `add.language`, `add.word`, `add.lookupOnly`, `add.undo`,
`add.undone`, `add.nothingToUndo`, `add.rebuild`, `add.noCard`,
`add.textNoCard`, `add.text`, `add.expression`, `add.senses`,
`card.text`. Removing `card.text` also means dropping `text:` from
`CARD_STATUS_KEYS` (`AddView.vue:128`), which is otherwise a lookup at a
key that no longer exists.

Keep `card.lookupOnly`: the `?` prefix still produces an entry with no
card, and its status line is the only thing that says so.

Add: `add.deleteCard`, `add.deleteCardConfirm`, `add.deleteCardYes`,
`add.deleteCardNo`, `card.deleted`, `add.analysing`, `add.buildingEntry`.

Change: `add.wordPlaceholder`, `add.detail`, `add.detailReady`,
`add.seeUsageSearch`.

Rewrite `add.aboutLookup` — it currently opens "Галочка рядом с полем
ввода", which will be false. It should describe only the `?` prefix.
Rewrite `add.aboutIntro` where it promises a feed.

### Tests

Extend `webapp/tests/AddView.test.js` and add specs for the new
components:

- the language row renders one button per configured language, marks the
  selected one, and switching it re-filters the rail;
- with a single language the row still renders and the pencil is present;
- the rail lists only the selected language's entries, newest first, and
  a tap selects that entry;
- a long sentence chip is truncated in the DOM but keeps its full text;
- submitting a word selects the new entry and shows the pending state
  without waiting for any event;
- a pending entry shows the progress strip and the spinner line, and its
  chip carries the live dot;
- pressing the delete action shows the inline confirmation and does not
  call the API; confirming calls `POST /api/words/…/delete-card` once;
- a lookup-only entry and a text entry offer no delete action;
- a text entry renders its source, its chips and no card status;
- the model name renders in the head and nowhere else;
- `useEntries` keeps at most 50 entries and never evicts a pending one.

Python side, in `tests/test_pipeline.py` and `tests/test_api.py`:

- `delete_card` removes the note, trashes the media, drops both audio
  files, and clears the control so a second call is a no-op;
- `delete_card` on a pending or unknown entry raises the expired error;
- deleting a card that is also the language's undo target leaves nothing
  for `undo` to delete;
- the usage search URL is a web search for the quoted wording, and the
  encyclopedia lookup itself still queries Wikipedia.

Swipe cannot be exercised in jsdom in any way worth trusting. Cover the
selection logic through the rail and the arrows-free tap path, and check
the gesture by hand on a phone against the canvas.

---

## M3 — The language editor

Two screens: a list with add and delete, and a full settings card per
language. Reached from the pencil in the language row, not from
`HeaderNav` — the three tabs stay as they are.

### What the config holds

`Language` (`src/echo_words/languages.py:38-51`) is a frozen dataclass:
`code`, `name`, `deck`, `script` required; `dict_api`, `tts`,
`tts_voice`, `edge_tts_voice`, `accent`, `api_model`, `prompt_hints`
optional. `load_languages` reads the TOML at `settings.languages_config`
and nothing writes it.

**The editor exposes neither `api_model` nor `prompt_hints`.** Both stay
file-only, for the same reason in two forms: they are the two fields
whose value reaches machinery the editor cannot validate or show the
effect of.

`prompt_hints` is prompt text (see the bench-gate section). Every other
field in the editor is inert data with a visible, immediate, reversible
effect — a wrong deck name shows up on the next card, a wrong voice is
heard at once. A wrong hint degrades every future answer for that
language quietly, and only a bench run would find it. It is also set once
per language by whoever tunes prompts, not by whoever adds a language, so
it does not belong on the screen for adding a language.

`api_model` matters beyond tidiness:
`create_broker` (`broker.py:57-61`) builds its `direct` map from
`paid_aliases(languages, settings)`, so a change to `api_model` would
require rebuilding the broker at runtime. Leaving it out of the editor
means a write can never invalidate the broker. Add a test that pins this.

### Backend

New endpoints in `src/echo_words/api.py`:

- `GET /api/languages/config` — the full table, every field, for the
  editor. The existing `GET /api/languages` keeps returning the slim
  `LanguageOption` list the rest of the app uses; do not widen it.
- `PUT /api/languages/{code}` — create or replace one entry.
- `DELETE /api/languages/{code}` — remove one.

New in `src/echo_words/languages.py`:

```python
def save_languages(path: Path, table: dict[str, Language]) -> None:
```

Serialise with `tomli-w` (add the dependency, then `uv lock`; CI installs
`--frozen`). Write to a temporary file in the same directory and
`os.replace` it into place, so a crash mid-write cannot leave the app
without a config. Omit keys whose value is `None` — an empty
`dict_api = ""` is not the same as an absent one.

Validation, reusing the rules in `_language_from_entry`:

- `code` matches `^[a-z]{2,8}$`;
- `name`, `deck`, `script` non-empty; `script` in `_ALLOWED_SCRIPTS`;
- `tts` is `piper` or `edge` when given;
- reject a `DELETE` of the last remaining language — the app cannot run
  with an empty table, `load_languages` raises on it.

After a successful write:

1. `app.state.languages = load_languages(settings.languages_config)`;
2. for an added or changed language, schedule
   `prepare_configured_voices([language], settings)` on a task, the way
   `_lifespan` does (`api.py:155-159`), so a new Piper voice downloads
   without blocking the response;
3. leave the broker alone — see above;
4. leave Anki alone. Deleting a language **never** deletes its deck: the
   cards are the reader's, and the confirmation says so.

Entries already in `History` for a deleted language stay. The rail
filters by the selected language, so they simply stop being reachable —
no cleanup, no migration.

### What the editor does not cover

With those two fields excluded, the editor covers everything a reader
does — add a language, remove one, fix its name, deck, script, voice,
dictionary and accent. Tuning a prompt hint or pinning a paid model stays
a `languages.toml` edit and a restart. That is the intended split, not a
gap to close later: those two are development, not use.

### Frontend

- `views/LanguagesView.vue` — the list. Each row: name, code badge,
  deck name muted beneath; a pencil opening the settings and a bin.
  The bin turns the row into an inline confirmation — `"Удалить
  «{name}»? Карточки в Anki останутся."` — never a modal. Below the
  list, one field and one button: type a name or a code, and the deck
  defaults to `EchoWords: {name}`. A live hint under the field shows the
  deck that will be created.
- `views/LanguageDetailView.vue` — name, deck, and a script segmented
  control up top; `Дополнительно` collapses over the TTS engine
  (segmented `piper` / `edge`), the voice field for whichever engine is
  chosen, and `dict_api` and `accent` side by side in a two-column grid.
  Save and, at the bottom, delete. **No `prompt_hints` field and no
  `api_model` field** — see above.
- `App.vue` grows two more `view` values. The pencil in
  `LanguagePicker` emits its way up.
- After a delete, if the removed language was selected, `useLanguage`
  must fall back — `loadLanguages` already replaces an unknown selection
  with the first configured one (`useLanguage.js:33-35`); call it again
  after any write.

The canvas shows one nicety worth keeping: when `piper` is chosen for
Serbian, a warning says Piper has no usable Serbian voice — the only
`sr_RS` model is Lower Sorbian. That is real, and
`languages.example.toml:29-31` already says so in a comment nobody reads.

### Tests

Python:

- `save_languages` round-trips through `load_languages` unchanged, for a
  minimal entry and for one with every optional field;
- the write is atomic — a failure leaves the original file intact;
- `PUT` rejects a bad code, an unknown script, a missing deck;
- `PUT` never writes `api_model`, so `paid_aliases` is unchanged, and
  never writes `prompt_hints`, so no prompt changes without the gate;
- `PUT` on a language that already has `api_model` or `prompt_hints` in
  the file preserves both untouched — the editor must round-trip fields
  it does not show, or saving a voice would silently drop a hint;
- `DELETE` of the last language is refused with 409;
- `DELETE` leaves the Anki collection untouched — assert the fake store
  saw no call;
- after a write, `GET /api/languages` reflects it without a restart.

Frontend: the list renders every language with its deck; the bin asks
before calling `DELETE`; cancelling calls nothing; adding posts a `PUT`
with the derived deck; the settings screen round-trips every field; the
engine toggle swaps which voice field is bound.

Deploy tests must stay blind to `.deploy/.env`, and no test may touch a
real `languages.toml` — use `tmp_path` and point `ECHOWORDS_LANGUAGES_CONFIG`
at it.

---

## Done gate

Per `CLAUDE.md`, and per milestone, not once at the end:

1. `uv run inv pre` → "All checks passed!" on every hook, `0 errors` from
   pyrefly. Re-run until hooks stop rewriting files.
2. `uv run inv test` → pytest all-passed and the frontend suite **run**,
   not skipped. `npm --prefix webapp ci` must have been run at least once
   or `inv test` silently skips the half of this plan that matters.

Then, by hand against the canvas, on a phone: the rail centres on the
selected chip, the card swipes both ways and springs back on a short
drag, every tap presses, and the light theme follows the system.

Commit straight to `main`. **Never push and never deploy without the
operator's explicit approval for that push and that deploy.**

Delete this file when the last milestone lands; move anything that
outlives it into `spec/decision-interface.md`.
