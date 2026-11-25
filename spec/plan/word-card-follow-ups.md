# Follow-up questions on a word card

**Status** — Step 1 has landed: built with the operator's minimal prompt, measured,
its re-run semantically reviewed and recorded in `spec/decision-llm-backend.md`, and
converged through three review rounds. The question endpoint (`POST /api/words/{entry_id}/ask`, a server-sent-event
stream of `delta`, `reset`, `done` and `error`), the prompt (`build_follow_up_prompt` in
`src/echo_words/prompt.py`, sections named as the reader's page names them, through the
`entry.*` keys of `src/echo_words/i18n.py`) and the context assembly and bound
(`src/echo_words/follow_up.py`) landed with their tests in `tests/test_follow_up.py`,
replies pinned from both recorded runs. The follow-up tier (`run-follow-up` in
`experiments/one_note_bench.py`, material in `experiments/follow_up_items.json`) has six
fixtures: two base-only, two deeper-only, a new sentence and the second turn after it. A
first run of the earlier, longer prompt is in `experiments/.bench-follow-up`; the minimal
prompt ran once on the free pool on 2026-11-25 into `experiments/.bench-follow-up-2`:
6 of 6 answered, all by google-gemini-3.5-flash-lite, one reply (base-en-reluctant)
three tokens long (a provider stop, with the operator). That run is the step's only
re-run. Step 2 is not started; the PWA has no control for it yet.

## What the reader can do

Under every finished word or expression entry stands a question field with a
Send button, as in any chat, and the reader asks freely about anything
mentioned on that card. For example, after
reading two examples in Deeper analysis, they can ask “Why is the second one
more formal?” and then “How would I say that to a friend?” The first reply
should identify the example and explain the register. The second should use
that same example and the preceding exchange to give a natural alternative.

Each entry has its own conversation, including lookup-only entries and entries
whose analysis succeeded but whose Anki save failed. Two lookups of the same
word can have different examples and must keep separate conversations. Asking
and answering only add to the PWA entry. The main input still submits new
lookups, and the existing controls still govern the deeper article and Anki.
Running-text entries are outside this word-card plan.

## 1. Build and measure one grounded reply

- Add a follow-up prompt and a dedicated question endpoint alongside the
  existing prompt builders and FastAPI card actions. Route it directly through
  the backend's free-pool text completion with its existing attempt budget.
  Pool exhaustion returns a retryable failure. Reading or quoting an existing
  paid article incurs no new paid call.
- At send time, take the material from the entry the reader sees. Include its
  source and target languages, submitted and analysed wording, supplied
  context, original analysis, visible sense or expression chips, and the
  completed deeper article when present, even if its section is off screen.
  Preserve headings, example order, and table rows when extracting text.
  Include the ordered completed exchanges on this entry and the new question.
  A locally restored card supplies the same context after a server restart.
- The prompt is minimal (operator decision, 2026-11-25): one line saying the
  model is a language tutor and the learner is reading the entry below; the
  material with each part marked and named as the page names it (the full
  article is «Полная статья» / "The full entry", never an internal label); the
  prior turns; the current question; then only "answer in the target
  language" and "plain text, no Markdown". No rules about ambiguous
  references, scope, accuracy or length: a reference that fits two passages
  is answered about one of them. Bound the request on the server. If it
  exceeds the supported context, explain the limit before calling the model
  so the reader can still see which material the question refers to.
- Stream reply text to the requesting browser. Keep the question path
  independent of analysis parsing, Anki, audio and deeper-article generation.
  Test context assembly on recorded material, order and language, oversized
  input, pool failure after partial output, and absence of side effects with
  fake boundaries.
- Before spending quota, register a follow-up tier in
  `experiments/one_note_bench.py`. Use real recorded analyses and deeper articles.
  Select passages where the referent can be checked and write down the
  expected passage and what a good answer must explain. Cover a base-only
  question, a term or numbered example unique to the deeper article, a
  turn-1 request for a new sentence, and a second turn understandable only
  from the first reply. Fixture questions name the article as the page does
  («полная статья»). Exercise the production context builder and prompt. For the
  second turn feed back the actual first reply and retain both in the packet.
- Run the tier on the free pool and check provider availability before scoring.
  A fresh agent reviews every exchange for the intended referent, linguistic
  accuracy, grounding and target language. Record the outcome in
  `spec/decision-llm-backend.md` and pin answer handling to recorded replies.
  Follow the repository's quota and review rules if measurement is interrupted
  or the answers need another prompt change.

## 2. Put the conversation in the card and keep it with the entry

- In `webapp/src/components/EntryCard.vue`, put a plain chat input under every
  finished entry: one always-visible labeled text field and a Send button, no
  toggle, no separate view (operator decision, 2026-11-25). The exchanges
  stack beneath the card above the field. Show the reader's question
  immediately and stream the reply beneath it. Render both as text.
  Localize controls and errors in English and Russian. Keep text selection,
  keyboard submission and card swiping usable on a phone.
- Store drafts and turns by entry ID with the browser's existing history.
  Older entries open with an empty conversation. Keep completed replies
  readable offline and after reload. Removing or evicting an entry removes its
  thread with it, and undoing a removal restores both. Await a completed
  deeper article before submitting a question while that article is streaming.
- Allow one pending question per entry. Bind every incoming chunk to its entry
  and turn even if the reader changes cards. On disconnect or reload mark an
  interrupted reply as incomplete, retain the question, and let the reader
  explicitly retry in the same place. Only completed replies enter the next
  turn's model context. An offline submission keeps the question available
  for retry next to it.
- Test persistence, legacy entries and retry in the frontend suite. In a
  real-browser test, gate the fake model's stream, ask about a detail unique
  to the deeper article, change cards mid-reply, return and ask a second
  question. Verify the exact entry context at the fake boundary, one visible
  copy per turn after retry, and restoration after reload. Cover a finished
  word with no deeper article and a saved entry after backend state expires.
- Update `spec/functional-description.md` and `spec/decision-interface.md`
  to describe the shipped interaction. Recapture the relevant screenshots.
  Run the repository implementation and review loop for each step, including
  `uv run inv pre` followed by `uv run inv test`. Retire this plan and its index
  entry when both steps and the semantic review have landed.
