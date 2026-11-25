# Follow-up questions on a word card

**Status** — Step 1 is built and measured once, not yet reviewed. The question
endpoint (`POST /api/words/{entry_id}/ask`, a server-sent-event stream of `delta`,
`reset`, `done` and `error`), the prompt (`build_follow_up_prompt` in
`src/echo_words/prompt.py`) and the context assembly and bound
(`src/echo_words/follow_up.py`) landed with their tests in `tests/test_follow_up.py`,
replies pinned from the recorded run. The follow-up tier (`run-follow-up` in
`experiments/one_note_bench.py`, material in `experiments/follow_up_items.json`) ran
once on the free pool on 2026-11-25 into `experiments/.bench-follow-up`: 8 of 8
answered (google-gemini-3.5-flash-lite 6, openrouter-nemotron-3-ultra 1,
groq-gpt-oss-120b 1). Still owed for step 1: the fresh agent's semantic review of
`review-packet-follow-up.json` and its record in `spec/decision-llm-backend.md`.
Step 2 is not started; the PWA has no control for it yet.

## What the reader can do

On a finished word or expression entry, the reader can open **Ask a question**
and ask freely about anything mentioned on that card. For example, after
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
- Distinguish the original analysis, deeper article, prior turns and current
  question in the prompt. Answer in the configured target language and quote
  the source language as needed. Explain, compare, correct a premise or give
  a new example as the question warrants. When a reference is ambiguous, ask
  which passage the reader means. Bound the request on the server. If it
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
  second turn understandable only from the first reply, and an ambiguous
  reference. Exercise the production context builder and prompt. For the
  second turn feed back the actual first reply and retain both in the packet.
- Run the tier on the free pool and check provider availability before scoring.
  A fresh agent reviews every exchange for the intended referent, linguistic
  accuracy, grounding and target language. Record the outcome in
  `spec/decision-llm-backend.md` and pin answer handling to recorded replies.
  Follow the repository's quota and review rules if measurement is interrupted
  or the answers need another prompt change.

## 2. Put the conversation in the card and keep it with the entry

- In `webapp/src/components/EntryCard.vue`, add a compact action to the
  existing controls row. It opens the conversation beneath the reading
  material and brings its labeled question field into view. Show the reader's
  question immediately and stream the reply beneath it. Render both as text.
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
  for retry through the conversation control.
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
