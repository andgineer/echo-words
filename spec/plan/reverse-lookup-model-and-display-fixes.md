# Implementation plan — the reverse lookup answered by the right model, and three display fixes

Decided by the operator on 2026-10-15, from a triage of the defects read out of the
bench review packets and met in use. Nothing here is built yet. There are no GitHub
issues behind it.

Two steps, in this order. Step 1 stops wrong cards reaching the deck; step 2 is how
an answer looks. Each step ends at the done gate (`uv run inv pre`, then
`uv run inv test`), and neither is pushed or deployed without the operator's approval
for that push and that deploy.

What the triage dropped is recorded where it belongs, not here: the article-only
faults and the faults of a card that looks right were accepted as the free pool's
quality (`decision-answer-shape.md`), the paid step's limit is a limit on silence
(`functional-description.md`, latency), and an answer broken past reading is asked
again (`decision-reverse-translation.md`).

## Step 1 — a reverse lookup the main free model did not answer is answered by the paid model

### Evidence

The reverse lookup is asked of the pool like every other answer, so when
`google-gemini-3.5-flash-lite` is out of quota or cooling, another pool model answers
it. In samples b and c of 2026-10-12 and 2026-10-13 that was 26 of 136 answers
(gpt-oss-120b 22, laguna 2, nemotron 2), read by a fresh reviewer beside the
workhorse's:

| | gemini-flash-lite | The other models |
|---|---|---|
| First card right | 66 of 71 | 15 of 20 |
| Wrong chips | 9 of 85 | 17 of 30 |
| Sentences | 22 of 22 translated right | 2 of 2 carded as a word |

The others' faults are not the misses the operator accepted of the workhorse: German
`коса` carded as Krawatte with the chips Brautstrauß and Fliese (laguna); `я иду домой`
carded as I «I walked to the store.» and as gehen (gpt-oss); English `сотл` read as the
non-word «сотить» and carded as lay (gpt-oss); five wrong Serbian chips of six from
gpt-oss; an insulting chip sentence, Drachen «Die alte Nachbarin ist ein richtiger
Drachen.» (nemotron).

How often a reader meets it: production's journal for 2026-09-21 to 2026-10-10 has
the workhorse writing 220 of 259 answers and gpt-oss 38, about one in seven; the
morning after the bench of 2026-10-12, 27 of 29 came from gpt-oss, because a bench
drains the app's own quota.

The paid model (`gpt-fast`, i.e. `gpt-5.6-luna`) was measured on the same inputs on
2026-10-13 (`experiments/.bench-reverse-paid-luna`): 48 of 49 first cards right, 2 of
72 chips wrong, 12 of 12 sentences translated, a median of 5.6 s and p90 11.3 s, a
fraction of a cent an answer. Reviewed blind; the record is in
`decision-reverse-translation.md`.

### Behaviour

- **A bought lookup** — `Pipeline._reverse_answer(job, bought=True)`
  (`src/echo_words/pipeline.py:601`), reached from `_reverse` for a `!` or a
  script-forced reversal: when the pool's answer is readable but `pool.llm_name` is
  not one of the main free models, that answer is set aside unseen and the paid model
  is asked through the branch that already buys a paid answer over an unreadable one
  (`pipeline.py:637-650`, `self.cascade.stream_paid(...)`). With the paid step refused
  (`self._paid_refusal(job.language)` — no key, or the daily cap spent) the pool
  answer stands, as it does today.
- **A last-resort lookup** — `bought=False`, from `_target_reading`
  (`pipeline.py:726`): a lookup is never bought there, and that rule stays. An answer
  from a model that is not a main one is treated as no answer: `_target_reading`
  returns `_STAYS`, the tab's own answer stands, and the reverse offer is still shown
  (`reverse_refused` stays false), so the reader can still ask with one tap.
- **A lookup stepped up inside the call** (a silent pool, `stepped_up`) is already
  the paid model's; unchanged.
- **Rating is unchanged.** The readable answer keeps its `record_quality(1.0)`: the
  rating is per language and shared with the article, where these models' answers are
  not what was measured here.
- Nothing reaches the page from the set-aside answer: reverse deltas are collected in
  `parts`, never streamed, so there is no provisional text to clear.
- Log lines, one per decision, beside the existing "the paid model takes over" ones:
  `"the paid model answers the reverse lookup for %s: the pool answer came from %s"` and
  `"the last-resort reverse lookup for %s is dropped: the pool answer came from %s"`.

### Which models are main

A setting, `reverse_pool_models: list[str]` in `Settings`
(`src/echo_words/config.py`), env `ECHOWORDS_REVERSE_POOL_MODELS`, comma-separated,
default `google-gemini-3.5-flash-lite`, documented line by line in
`.deploy.example/.env`. The model names are llmbroker's and change with its catalog;
which of them may answer this task is echo-words' choice, so it lives here, not in
llmbroker's catalog. An empty value means every pool model counts as main — the
feature off.

### Not now

The reader waits for the weaker model's answer and then the paid one. An llmbroker
per-call allowlist would ask only the main model and step up as soon as it cannot
answer — `Pool` already filters candidates by an `exclude` set
(`../llmbroker/src/llmbroker/broker/pool.py:221-262`), but `AsyncBroker.stream` and
`ask` do not expose it. Build that only if the logs after deploy show the extra wait
is noticeable; it is an llmbroker release plus a bump here.

### Tests (`tests/test_pipeline.py`, beside the existing reverse tests)

1. Bought lookup, pool answer from a model not in the setting → the paid model is
   asked once, its answer is carded, the log line is written.
2. Same, with the paid step refused (cap spent) → the pool answer is carded, no paid
   call.
3. Bought lookup answered by the main model → no paid call.
4. Last-resort lookup answered by a model not in the setting → the tab's own answer
   stands, `reverse_offered` is true, no paid call.
5. Empty setting → no model triggers a paid call.
6. `tests/test_config.py` (or wherever `Settings` is tested): the default, and a
   comma-separated env value parsed into the list.

No browser test: the page sees the same events as for a paid answer bought over an
unreadable one, which the e2e suite already covers.

### Measurement

Neither the prompt nor the parser changes, and the paid model's answers to this exact
prompt were benched and reviewed on 2026-10-13. Confirm it is still the same prompt:
the reverse prompts built for the fixtures of `experiments/.bench-reverse-paid-luna`
must hash to the `prompt_hash` values recorded in its `answers.jsonl` (they match
sample c's). If any hash differs, the prompt has moved since the measurement: re-run
`experiments/one_note_bench.py run-reverse --paid gpt-fast` on the same fixtures —
real money, so ask the operator first — and have a fresh agent review the packet
before calling the step done.

After a deploy the operator approves: for a week, count the two new log lines against
the reverse lookups in `inv logs`, and record the share and the paid spend in
`decision-reverse-translation.md`.

### Specs on landing

- `functional-description.md`: the paid step is reached in one more situation — a
  reverse lookup the reader asked for that the pool's main model did not answer — in
  both the LLM paragraph and the Cost requirement, which today name only the others.
- `decision-reverse-translation.md`: the decision paragraph states the routing as
  built, without "is to be".
- Remove step 1 from this file.

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
