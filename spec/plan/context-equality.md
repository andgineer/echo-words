# Implementation plan — a correct answer thrown away over a full stop

Delete this file once the rule is settled. What outlives it belongs in the trust
boundary of `spec/decision-answer-shape.md`, which currently states the strict
rule as it stands.

## What happens

A chip tap carries the sentence the learner clicked in. The answer must lead with
that sentence as its first example, and `card.py` enforces it by equality —
`selected context example must equal the supplied context`. A model that copies
the sentence back without its final period fails that check, and the whole answer
is rejected: no card, for an analysis that was right in every other respect.

Measured once in two full tiers. `click-de-combination` returned a correct
`aufstehen` analysis for `Er steht jeden Morgen um sechs auf.` and lost it to the
missing period; the same fixture passed cleanly on the next tier. So this is an
intermittent copying slip, not a standing failure — which is exactly why it is
worth deciding deliberately rather than after the next time it costs a card.

## Why the rule is strict in the first place

The example is the card front. Equality is what guarantees the card teaches the
sentence the learner was actually reading, rather than a sentence the model
rewrote while claiming it was the same one. Loosening it carelessly gives the
model room to substitute a different sentence and call the difference
punctuation.

## The narrow fix, and what it must not become

Compare with trailing sentence punctuation normalized away, and card **our**
supplied context rather than the model's copy of it. The backend already owns the
context string; nothing forces us to card the copy that came back. That way the
comparison gets one degree of freedom and the card gets none.

What this must not turn into: normalizing anything inside the sentence. A
difference in the middle is a rewrite, and a rewrite is the case the rule exists
for.

## How to settle it

- Re-score every recorded click and tap across the existing bench directories,
  counting how many answers fail this check and how many of those differ only in
  trailing punctuation. Zero cost — the answers are bought.
- If the class is real, land the narrow comparison with tests covering a dropped
  period, a changed word, and a sentence-internal difference.
- The parser is what the app does with an answer, so the change is measured on a
  tier and reviewed like any other, even though it is deterministic.
