# Plan: reverse translation

**Status (2026-10-12):** built end to end, not yet fully measured and read by nobody
but its author. A word or a text
typed in the target language (`!стол`, or Cyrillic on a Latin-script tab) becomes the
entry for its equivalent in the selected language; where the alphabets overlap, the
answer to typed input names its language and routes it. What the reader gets is in
`spec/functional-description.md` (Core flow, item 2), and the measurements and the
reasoning are in `spec/decision-reverse-translation.md`.

What is left:

1. **A review of the implementation** by an agent that did not write it, before any
   push (below). The operator agreed to it on 2026-10-12, to be run in the next session.
2. **Samples b and c** of the reverse prompt with the sentence translation (below).
   Until they are recorded the reverse prompt does not count as measured, and the
   feature is not to be called done or deployed as one.
3. Delete this plan, and set `CLAUDE.md` back to one open plan.

No push and no deploy without the operator's explicit approval for that act.

## The review (owed)

The routing was written and tested by one session: `git diff 3a5c53e62..6128ef377`,
three commits, about 700 lines of product code in `src/` and `webapp/src/` and the rest
tests, specs and screenshots. Its tests pin what the author thought of; five rules were
broken on purpose and the tests caught each. Nobody else has read it.

Where a second reader is most likely to find something:

- the worker's follow-up loop — one entry carried through a reverse lookup and then an
  ordinary answer, or moved to another tab — and what a rebuild, a spelling switch, an
  undo, a newer submission or a superseded job in the middle of it leaves behind;
- the bookkeeping of a move: the latest submission and the undo of both tabs, and which
  tab the history entry ends on;
- the page across a reconnect: the receipt and the resend queue while an entry is being
  reversed or moved, and retry putting back `!` and `?`. One fault of this kind is
  already found and fixed: a move read before the reply to its own send left the reader
  on the tab the entry had gone from. The browser test of the move lost that race about
  once in twenty-five runs, and a component test now pins the order.

The review needs no pool quota, so it does not wait for the samples. A fix that comes
out of it must leave the reverse prompt and `parse_reverse` alone until b and c are
recorded (below); anything it finds there is written down and fixed after.

## What was measured, and what was not

- The reverse prompt: four runs on the pool, each reviewed by a fresh agent, and
  Serbian in Latin letters six times more; with the sentence translation, sample a of
  three (decision spec, "Sentences").
- The language line: two samples of `experiments/language_bench.py` and the full tier of
  `experiments/one_note_bench.py`, reviewed by a fresh agent (decision spec, "The
  language line in the answer").
- The routing around them — which call is asked when, what stands when one fails — is
  code with no model in it, covered by `tests/test_pipeline.py`, `tests/test_api.py`
  and the browser suite `tests/test_e2e_reverse.py`. It changed neither prompt nor
  parser.

## Samples b and c (owed)

Sample a of the reverse prompt with the sentence translation is reviewed and recorded
(decision spec, "Sentences"). Samples b and c measure the same prompt again, so the
three can be read together; they are owed before the reverse prompt counts as measured.

- **Do not change the reverse prompt or `parse_reverse` until b and c are recorded.**
  A report keeps only answers whose prompt hash matches the current prompt, and
  `run-reverse` refuses to run on drift: a change would void b and c and re-spend their
  quota. Nothing built since sample a touched either.
- A job started on 2026-10-12 waits for 2026-10-13 09:05, checks every 15 minutes that
  gemini-flash-lite answers, then resumes a (two calls that timed out), b and c, and
  stops itself when the workhorse cools for 960 s or more (its daily quota gone). It
  lives in the first session's scratchpad: `pgrep -fl resume.sh` shows whether it runs;
  its progress is in `/private/tmp/claude-501/-Users-andrei-sorokin2-projects-echo-words/a7c1d2e7-d43c-4109-ae8f-4863e3fb519e/scratchpad/tomorrow.log` and the calls in `/private/tmp/claude-501/-Users-andrei-sorokin2-projects-echo-words/a7c1d2e7-d43c-4109-ae8f-4863e3fb519e/scratchpad/reverse-sent.log`. The
  directory is under `/private/tmp` and does not survive a reboot.
- Sample b already holds 15 answers, 7 of them from groq-gpt-oss-120b bought after
  gemini's quota ran out on 2026-10-12; `--resume` keeps them, and the report's
  "answered by" line shows the share.
- If the job is gone or stopped, resume by hand once the pool has reset (09:00 CEST),
  after one probe call shows gemini answering:

      uv run python experiments/one_note_bench.py run-reverse --resume --wait 180 \
        --pace 2 --concurrency 1 --out experiments/.bench-reverse-sent-<a|b|c>

  About 76 calls a sample. Stop when the log shows
  `google-gemini-3.5-flash-lite cooling for 960s`, and resume on a later day.
- Then, for each of b and c: `uv run python experiments/one_note_bench.py report --out
  experiments/.bench-reverse-sent-<x>`. Read availability first ("answered by": gemini
  should carry nearly all; well below that means the run is void). A fresh Opus agent
  then reviews every item of each `review-packet-reverse.json`, briefed as sample a's
  reviewer was: the sentence translations (faithful, natural, in the tab's language,
  Serbian in Latin), first cards and chips, the operator's rules (Croatian, Bosnian and
  ijekavian forms are no fault; Serbian Cyrillic is read as written), the accepted
  limitations (decision spec, "Decision") counted but not re-argued, and per-tab counts
  of first cards right, chips wrong and translations right.
- Record: the "Sentences" table in the decision spec becomes three samples, with any
  new fault; then `uv run inv pre`, `uv run inv test`, commit locally.
