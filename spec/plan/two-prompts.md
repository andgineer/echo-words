# Implementation plan — a cheap call to choose the branch

**Steps 1-4 have landed and are measured.** What they established is in
`spec/decision-answer-shape.md`: the selected-unit prompt, the single judgement,
the near neighbour as prose, and the conditional origin. What is left open is the
architectural change the earlier steps were the precondition for.

## What is already true

A request whose branch the reader's own action settled — a chip tap, a one-word
submission — is asked with the unit contract alone, 4,651 characters against the
merged prompt's 8,787. The submit box, where the branch is genuinely unknown,
still carries both branches at 7,205 characters and decides inside the answer.

That leaves one prompt doing two jobs, and only on the path where the job is not
known in advance.

## The open question

`decision-answer-shape.md` records that selecting one of two prompts **in code**
before asking the model reproduced a classification problem that surface
punctuation and length cannot solve. That rejection stands and is not to be
re-derived. What it never evaluated is a **cheap model call** whose only job is to
answer unit-or-text, followed by the specialised prompt for the branch it named.

The app already issues two calls per unit submission — the article and the
judgement — so a second call is not a new cost shape. The free pool's daily quota
is a bench problem rather than a product one: a reader does not ask enough
questions in a day to approach it.

## What the measurement has to answer

Compare the classifier-then-specialised-prompt against the merged prompt on the
verdict matrix, which already measures exactly this question. The split tier is
the baseline to beat: 121 usable verdicts, 114 correct, one defensible, six hard
errors, and 26 of 26 known texts on the text branch.

Two things the matrix does not cover and the run must:

- **Latency.** Two calls in sequence cost what the merged prompt does not, and
  the reader waits for the sum rather than for the slower of two parallel calls.
  The split tier's p50 is 2.5 s end to end; a classifier that adds a second round
  trip has to be read against that, not against a token count.
- **What a wrong classification costs now.** Under the merged prompt a
  mis-branched answer is still an answer; behind a classifier the specialised
  prompt cannot express the branch the input actually needed. The unit prompt has
  no text branch at all, so a text input classified as a unit has nowhere to go —
  which is why this step comes last, and why the false-text and false-unit rows of
  the matrix are the ones to read.

## What this plan must not do

- **Do not re-derive the rejection of code classification.** It was measured and
  it stands. What is open is a model call, not a heuristic.
- **Do not let the prompt grow back.** A rule that only ever mattered to one
  branch belongs in that branch's prompt, and one the split makes unnecessary
  comes out.
- **Do not measure the classifier and a prompt edit with one number.** The
  classifier is the only change its tier gets.
