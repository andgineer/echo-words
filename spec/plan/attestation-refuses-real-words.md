# Implementation plan — the judgement refuses words that exist

Delete this file once the operating point is re-measured and recorded. What
outlives it belongs in `spec/functional-description.md`, which today states the
false-positive half of this trade and not the half below.

## What has been observed

Three refusals of real wording, none of them a registered fixture:

- `manger` — an ordinary English verb, `used: false`.
- `отад` — a standard Serbian adverb, the short form of `отада`, `used: false` on
  two consecutive full tiers.

A refusal is expensive by design: no article, no card, no audio, and the entry
tells the learner their wording is not vouched for. On these three the learner is
told that about a word that is simply a word.

It also costs a second thing that is easy to miss. A refused submission never
reaches anything downstream of the judgement, so any other behaviour measured on
that word silently reports a zero — which is how `neighbour-sr-otad` came to
measure nothing at all for two tiers running.

## Why the fixtures did not catch it

The registered attested words pass 4 of 4 every run: `petrichor`, `susurrus`,
`Kummerspeck`, `inat`. Every one of them is a word with a literature — the kind
that appears in "untranslatable words" lists a model has read many times over.
`manger` and `отад` are the opposite kind: entirely ordinary, and entirely
unremarkable, so nothing has ever been written *about* them.

That is a hypothesis, not a finding, and it is testable: if it holds, the attested
arm is measuring recall of famous words rather than the judgement the product
depends on, and its 4 of 4 means much less than it reads.

## What to do

1. Register a second class of attested fixture: ordinary, unremarkable, mid-
   frequency words in all three languages — the words nobody writes essays about.
   Six or so, chosen before any of them is run, and not chosen by trying candidates
   against the model first.
2. Score them on a tier. The existing famous-word fixtures stay, so the two classes
   can be read apart.
3. If ordinary words are refused at a materially higher rate, the operating point
   in `spec/functional-description.md` needs its other half written down, and the
   choice becomes explicit: accept the false refusals, soften the standalone
   question, or stop letting a single refusal withhold the whole entry.

## What not to do

Do not tune the standalone question against these three words. Three refusals
found by accident are a signal to measure properly, not a target to fit — and the
question's framing is exactly what the existing measurement showed to be decisive,
so a wording change made to rescue `отад` would move the coinage side too, silently.
