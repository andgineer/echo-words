# Implementation plan — three display fixes

Decided by the operator on 2026-10-15, from a triage of the defects read out of the
bench review packets and met in use. Nothing left in it is built yet. There are no
GitHub issues behind it.

One step is left, step 2: how an answer looks. Step 1, the reverse lookup answered by
the right model, has landed, and what outlives it is in `decision-reverse-translation.md`.
Step 2 ends at the done gate (`uv run inv pre`, then `uv run inv test`), and it is not
pushed or deployed without the operator's approval for that push and that deploy.

What the triage dropped is recorded where it belongs, not here: the article-only
faults and the faults of a card that looks right were accepted as the free pool's
quality (`decision-answer-shape.md`), the paid step's limit is a limit on silence
(`functional-description.md`, latency), and an answer broken past reading is asked
again (`decision-reverse-translation.md`).

## Step 2 — three display fixes

### Evidence

From 6,455 recorded bench answers (`experiments/.bench*/answers.jsonl`, counted
2026-10-15):

- **Markdown bold in the article prints as literal asterisks.** The main free model
  never writes it (0 of 4,997) and neither does the paid model (0 of 288); the pool's
  other models do in 281 of 1,170 — gpt-oss-120b 117 of 731, nemotron 99 of 201,
  glm-4.7-flash 45 of 127, laguna 20 of 111. At production's one answer in seven from
  those models, about one article in thirty shows `**…**`. Example, `text-sr-8`:
  `**Sve mi se čini da …**`.
- **Stray angle brackets around the bold span of a card example**, once:
  `<<b>разказвам</b>> ти интересна история.` (`.bench-sense-label`,
  `cyrillic-bg-razkazvam`), the ContextRecognition front.
- **A reverse answer that delimits a string with typographic quotes is thrown away**,
  once: `"example": „Posle dugih pregovora konačno je sklopljen mir između dve
  zemlje.”` (`.bench-reverse-sent-c`, `reverse-sr-mir`). The content is whole; only
  the quotes are wrong, and the reader waits for a second answer.

### Fixes

1. **`**x**` reads as bold.** In `sanitize_html` (`src/echo_words/sanitizer.py:13`),
   before the tag walk, rewrite each `\*\*(?=\S)([^*\n]+?)(?<=\S)\*\*` to `<b>\1</b>`.
   Only the doubled pair: a single `*` is how an etymology writes a reconstructed form
   (`*or-*`, `*prъzъrcъ`) and must survive. The function sees the whole text so far on
   every streamed update, so an unclosed `**` shows literally until its closing pair
   arrives and then turns bold — the same as a `<b>` split across deltas. Check every
   caller of `sanitize_html` (article, deeper article, text answer) gets it, and that
   no card-block JSON passes through it.
2. **`<<b>…</b>>` loses the stray brackets.** In the same walk, drop a `<` that
   immediately precedes an allowed `<b>` and a `>` that immediately follows `</b>`;
   no language's text puts a bracket against a bold tag. Then confirm the card
   example path (`src/echo_words/card.py:334`, `_parse_example` / `_example_forms`)
   either goes through `sanitize_html` or applies the same rule before marking — the
   sample above is a card field, not article prose.
3. **Typographic string delimiters are read.** In `json_object`
   (`src/echo_words/prompt.py:633`), add a third candidate tried only after the plain
   text and the `_UNQUOTED_VALUE` repair both fail: rewrite
   `(":\s*)[„“]([^"„“”\n]*)[”“]` to `\1"\2"`. Last, so an answer whose straight-quoted
   string merely contains „…” is never touched.

### Tests

- `tests/test_sanitizer.py`: `**x**` → `<b>x</b>`; an unclosed `**x` stays literal;
  `*or-*` untouched; `a ** b` untouched; `<<b>x</b>>` → `<b>x</b>`; `a < b` and
  `<b>x</b> > y` untouched; the existing balanced-tag cases unchanged.
- `tests/test_prompt.py`: a „…”-delimited value is read; a straight-quoted value
  containing „…” is read unchanged; the missing-opening-quote case still reads.
- If the card example path needed its own rule: a `tests/test_card.py` case with the
  `разказвам` sentence carding with the brackets gone.

### Measurement

This changes what the app does with an answer, so it is measured on real answers — the
recorded ones, which costs no quota. Re-score through the new code with
`experiments/one_note_bench.py report` on `.bench-sense-label`, `.bench-reverse-sent-c`
and `.bench-nb-field` (the run with the most weaker-model answers), before and after:

- every answer readable before is readable after, with the same card;
- `reverse-sr-mir` in sample c becomes readable;
- a one-off scratch count over all `answers.jsonl` finds no `**…**` pair left in any
  sanitized article.

A fresh agent reviews every item whose rendering or card changed, and the result goes
into `decision-answer-shape.md` (Markdown bold read as bold) and
`decision-reverse-translation.md` (typographic quotes read). Then delete this file.
