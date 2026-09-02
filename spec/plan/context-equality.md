# Implementation plan — a correct answer thrown away over a full stop

Delete this file once the landed rule has been measured on a tier. The rule
itself now lives in the trust boundary of `spec/decision-answer-shape.md`.

## What landed

`card.py` compares the model's first example against the supplied context with
trailing sentence punctuation normalized away, and cards the backend's own
context string rather than the model's copy of it. The comparison gained one
degree of freedom; the card gained none. Tests in `tests/test_card.py` cover a
dropped final stop, an extra word, and a word changed inside the sentence.

## What the re-score established

Re-scored across every bench directory, 152 recorded contextual answers carried
an example. 149 passed strict equality. Of the three that failed:

- one differed only in its final stop — `click-de-combination`, the case this
  plan was opened for. It now cards.
- two were genuine rewrites — a duplicated clitic (`вратио се` for `вратио`) and
  a dropped word (`синоћ`). Both are still rejected.

So the class is real, it is small — one answer in 152 — and the strict rule is
doing exactly the work it was written for on the other two. That is the result
the narrow fix was conditioned on.

## What is left

The parser is what the app does with an answer, so the change is measured on a
tier and semantically reviewed like any other, even though it is deterministic
and its regression risk was measured directly over recorded answers. That run is
outstanding and needs the operator's pool quota; it is the same run the boundary
repair in `exact-boundaries.md` is waiting for, and one tier covers both.
