# Implementation plan — the context decides, the senses stay visible

Delete this file once the work has landed. What outlives it is
`spec/decision-card-shapes.md` and the sections it rewrites in
`spec/decision-product.md` and `spec/functional-description.md`.

This plan **supersedes the card-catalogue decision layer already in the working
tree**. The mechanics landed there are sound and stay; what goes is who decides.

## Scope

In scope: who decides the card set, the wording of the context note, the other
senses reaching the reader, and the removal of deduplication.

Out of scope, deliberately:

- The router change and everything else listed under "What stays exactly as it
  is" — landed and reviewed, do not revisit.
- The fragment/unit decision (`decision-phrases-and-sentences.md`), measured and
  left alone.
- The split typo instruction in `prompt.py`, where `If it looks like a typo, do
  not silently fix it:` sits ~18 lines from its own continuation `add one short
  line beginning with ✏️…`. Real, pre-existing, and it gets its own change with
  its own measurement — touching it here would spoil the attribution of step 4.
- `experiments/extract_prompts.py` variants v1–v4, broken by an older prompt
  revision.

The note type changes **once**: the card-catalogue shape in the tree is not
deployed anywhere, so its fields are still free to move. Land the final field
set in this change rather than shipping two rebuilds.

---

## Why this exists

The catalogue shipped its card decisions as a request list the model filled.
Measured on 72 answers over the fixtures in `experiments/context_items.py`, the
model asked for a context card in 86% / 81% / 95% of `pins` / `adds_nothing` /
`expression` — three classes that must differ. Its judgement carried no
information, and the pre-registered gate (`adds_nothing` under 25%) failed at
90%.

The fallback rule — card the context when the answer holds several meanings —
scored 0% on `adds_nothing` (no false positives) but only 35% on `pins`. The
reason is in our own prompt, not in the model: `_CONTEXT_NOTE` tells it to
analyse *the sense used there* and not to substitute the nearest dictionary
meaning, so 13 of 20 genuinely polysemous words came back with one meaning. We
forbade the model to list the other senses, then measured that it did not.

The same model splits a **bare** `bank` into «банк» / «берег» today. That
behaviour ships, and it is the signal this plan un-mutes.

---

## The design

Stop suppressing the other senses. A context submission asks for the word's
senses as usual, plus which one the context uses. Every card decision is then a
backend fact:

| submission | senses in the answer | note |
|---|---|---|
| no context | any | today's behaviour: bare front, recall, split per sense |
| with context | **several** | the context narrows: context-fronted note for the selected sense; the other senses are offered under the answer |
| with context | **exactly one** | the context narrows nothing: **discard it** and make an ordinary bare note |

The model answers only what it already answers well — what senses this word has
— plus one index. It decides nothing about cards.

The other senses are offered as chips, each carrying a short example sentence in
the source language. Tapping one is an ordinary submission of the same word with
that sentence as its context, so the mechanism already exists and the note it
makes is a good one. This is also what tells a reader meeting the word for the
first time that it has other senses at all — which they cannot know by looking
at the answer, and must not be asked to judge.

**Deduplication goes.** A chip tap is a second submission of the same word; with
the duplicate check in place it would be refused and the second sense could
never enter the deck. Identical fronts remain impossible where it matters:
a context note carries its sentence, a chip-made note carries its own. Two bare
submissions of one word can now make two identical notes — accepted, deliberately.

---

## Step 1 — the contract

**`src/echo_words/prompt.py`.**

- Delete the `cards` array from the card JSON, its field description, and the
  sentence about a context card being worth emitting. The contract returns to
  `word`, `suggestion`, `candidates`, `meanings`.
- Rewrite `_CONTEXT_NOTE`. It must stop saying "analyse the sense in which it is
  used there … do not substitute the nearest dictionary meaning". It must say:
  give the word's senses the way you would without a context, then name which
  one this context uses, and lead the answer with that one. When the word has
  only that one sense, say so by returning one meaning.
- The card JSON gains, for a context submission only, the index of the sense the
  context uses, and each **other** meaning gains a short example sentence in the
  source language that shows *that* sense — the sentence a chip tap will submit
  as its context. One sentence, no translation of its own; the meaning's own
  translations already carry the target language.

The prompt must not ask, anywhere, whether a card should exist.

**`src/echo_words/card.py`.** Delete `_requested_cards`, `_CARD_REQUESTS` and
the request-parsing rules. Keep the `sense` index parsing — it is already tested
and only changes meaning, from "which sense a requested card is about" to "which
sense the context uses".

Three rules on that index, all fail-cheap:

- absent, non-integer, or out of `range(len(meanings))` → the answer does not say
  which sense applies → treat as *no narrowing* and fall through to the bare
  note. That is the cheap direction: a bare note is never wrong, it is only less
  specific.
- exactly one meaning → the index carries no information whatever its value.
  Ignore it rather than validating it.
- `bool` is not an integer here, the way `_requested_sense` already excludes it.

## Step 2 — the card set

**`src/echo_words/pipeline.py`**, where `job.context` is known. Derive the note
from two facts and nothing else: whether a context came with the submission, and
how many meanings the answer holds.

- context and several meanings → context note for the selected sense
- context and one meaning → **drop the context** and build the bare note
- no context → bare note

The dropped-context case must be visible to the user in the status line, not
silent: it is a decision the app made on their behalf. It needs its own i18n key
in `webapp/src/i18n/{ru,en}.js` alongside the card-kind labels — something that
says the context was not needed, not an error and not a warning.

**`src/echo_words/anki.py`.**

- `ContextPrompt` goes, and a `ContextTranslations` field takes its place: the
  selected sense's translations, rendered by `_render_translation_block` without
  its gapped example (the gapped *context* stands below it and does that job).
  It must be its own field rather than a reuse of `Translations`, because a
  context note leaves `Translations` empty so the plain Recall template does not
  also fire.
- **Audio.** The word's own pronunciation belongs on the side that shows the
  word: the back of both context cards. The context's pronunciation is already
  produced separately by `_voiced_context` for the answer view; it does not go on
  a card, because a front that speaks the sentence would give the gap away.
- A context note leaves `Meanings` empty and fills `ContextMeaning`; a bare note
  does the reverse. **Verify empirically on a throwaway collection** that Anki
  generates the intended card for each, and in particular whether it accepts a
  note whose first template's front is empty. The comment in the current code
  claims Anki requires the first template to always produce a card; establish
  whether that is true of the shipped Anki version before relying on template
  order, and say what you found.
- Remove the duplicate check: the `find_notes` query before insert, the
  `Duplicate` result and its branch in `replace_note`.

**`src/echo_words/pipeline.py` / `history.py` / webapp.** Remove
`DUPLICATE_STATUS`, the `duplicate` action, the duplicates counter and its
i18n string. Undo is unaffected.

## Step 3 — the other senses reach the user

The chips already exist for running text (`entry.segments`, rendered by
`AddView.vue`, tapped through `analyseSegment`). A context answer that narrowed
fills the same list with its other senses, one chip per sense.

Mind the shape: `Segment` is `(label, surface, reason)` and `analyseSegment`
today sends `entry.word` as the context. Neither fits — the label of every chip
here is the *same* word, and what the tap must send is that sense's example
sentence. So:

- `label` — the word (what the chip reads as, and what gets submitted)
- `reason` — that sense's translations, which is what tells the two chips apart
  on screen. Two chips reading `bank` and `bank` with nothing else are useless.
- `surface` — the sense's example sentence, and `analyseSegment` sends **it** as
  the context when it is present, falling back to `entry.word` for the
  running-text chips that have no sentence of their own.

That last point is the one thing in this step that is not already wired; the rest
is data flowing through a path that ships.

A chip whose sense the reader has already carded is not suppressed — there is no
duplicate check any more, and a second card for a sense already learned is the
accidental-duplicate case the design accepts. Suppressing it would mean querying
the collection per chip, which is a lookup on the answer path for no benefit.

## Step 4 — the measurement

The fixtures already exist: `experiments/context_items.py`, 24 items per class
over three languages. Rework the scoring in `experiments/extract_bench.py` — the
card-request metrics go with the request list — to score the two facts the design
now reads:

- how many meanings the answer holds
- whether a sense index is present and in range

The gate, pre-registered, on the free pool:

- **`pins`: several meanings in at least 80%.** Below that the context still
  suppresses the senses and the design does not work.
- **`adds_nothing`: exactly one meaning in at least 80%.** Above that we card
  the context on words that do not need it.
- **`expression` reports, it does not gate.** A set expression is one unit with
  one sense, so it should behave like `adds_nothing` and end up carded bare. If
  it instead comes back with several meanings, that is worth knowing — the
  expression is being read as its parts — but it is a different defect and does
  not decide this design.

Also record, per class, how often the sense index is present and in range. It
does not gate anything (an unusable index falls through to the bare note by
design), but a class where it is routinely missing means the prompt's wording,
not the model, is at fault.

Both directions have ground truth — these are lexical facts, checkable against a
dictionary, unlike the judgement the previous gate asked for. The errors are
asymmetric and both cheap: a spurious extra sense costs a wordier card and a chip
the reader ignores; a missed sense costs nothing permanent, because with
deduplication gone the reader gets that sense when they next meet the word.

Run once, when the code is settled:

```
uv run --no-project --python 3.12 --with "llmbroker>=1.5.2" \
    python experiments/extract_bench.py run --variant v0 \
        --klass pins adds_nothing expression --out experiments/.bench-senses
```

Then the offline reader. `--resume` and `--only-wrong` keep a second wording
iteration to the items that discriminate; a change to how an answer is *read*
costs nothing.

---

## What stays exactly as it is

Landed, reviewed four times, and untouched by this plan: the router change
(`Das geht.` is a unit), the note type and its rebuild task, `card_fields`,
`_mask_word` / `_highlight_word` / `_context_front`, the status line naming the
kinds, the frontend plural handling, and every test covering them.

## Tests

- `tests/test_card.py` — the request list is gone; the sense index parses, and an
  absent or out-of-range index falls through to the bare note
- `tests/test_pipeline.py` — one meaning with a context drops the context and
  makes a bare note, and the status says so; several meanings make the context
  note; no context is unchanged
- `tests/test_anki.py` — a context note generates the context cards and no bare
  front; a bare note generates the bare cards and no context front; adding the
  same word twice now makes two notes, and the second does not disturb the first
- `webapp/tests/AddView.test.js` — the other senses render as chips carrying
  their translations, a tap submits the word with that sense's sentence as the
  context, and a running-text chip with no sentence still submits the entry's
  text as before

Delete, rather than adapt, every test that pins the removed decision layer: the
`cards` request parsing, the drop rules, and the duplicate result. A test kept
alive against a deleted contract is worse than no test.

## Verification

```
uv run inv pre     # every hook green, pyrefly 0 errors
uv run inv test    # pytest all passed, frontend suite passed not skipped
```

Then the single pool run of step 4.

## What moves into spec when this lands

- `spec/decision-card-shapes.md` — the table above, the failed measurement and
  why it failed, and the new gate with its numbers.
- `spec/decision-product.md` — "one note per word" and the duplicate rule.
- `spec/functional-description.md` — the card section and the chips.
