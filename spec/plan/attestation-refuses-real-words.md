# Implementation plan — the judgement refuses words that exist

Delete this file once the ordinary-word class has been scored on a tier and the
operating point is recorded. What outlives it belongs in
`spec/functional-description.md`, which today states the false-positive half of
this trade and not the half below.

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
that word silently reports a zero — which is how the Serbian neighbour pair came
to measure nothing at all for two tiers running.

## Why the fixtures did not catch it

The registered attested words pass 4 of 4 every run: `petrichor`, `susurrus`,
`Kummerspeck`, `inat`. Every one of them is a word with a literature — the kind
that appears in "untranslatable words" lists a model has read many times over.
`manger` and `отад` are the opposite kind: entirely ordinary, and entirely
unremarkable, so nothing has ever been written *about* them.

That is a hypothesis, not a finding, and it is testable: if it holds, the attested
arm is measuring recall of famous words rather than the judgement the product
depends on, and its 4 of 4 means much less than it reads.

## What landed

Six ordinary, unremarkable, mid-frequency words are registered as a second
attested class — `ledge`, `scowl`, `Kübel`, `mürrisch`, `клупа`, `сврака`. They
were chosen on that principle alone and never tried against a model first, which
is what makes their score evidence rather than a fitted result. They sit on the
full tier only, at twelve calls, and the two classes read apart in the report:
the famous four keep the `rare real wording still cards` gate, and the ordinary
six are printed beside it as a diagnostic that gates nothing.

Gating them now would be setting a threshold before the measurement — a guess
reddening the run for a reason nobody has decided. Their rate is the open
question, not a target.

The same measurement covers the refusal risk on the replaced Serbian neighbour
pair: `месо` is an ordinary word of exactly the class being scored, so a separate
probe call before the tier would buy nothing the tier does not already report.

## What the tier measured, and what it turned up instead

The ordinary class scored **5 of 6**, against 4 of 4 for the famous class. The
one refusal is `сврака` — an ordinary Serbian noun for a magpie — refused by the
standalone judgement while the article call vouched for it and wrote a correct
entry. That is a fourth observation of this defect and the first caught by a
registered fixture, so the hypothesis above now has evidence: the famous four
were measuring recall, not the judgement.

One tier is one sample, and 5 of 6 against 4 of 4 does not yet size the gap.
What it does establish is that the class is not decorative.

The same run turned up the opposite error, which matters more and belongs here
because it is the other half of the same trade. **`bookshelfy` was refused by
neither judgement and was carded**, with invented senses, an invented register
and an invented etymology. And the article's own leading verdict vouched for all
five coinages in the arm — `Fahrradsuppe`, `Löffelangst`, `tablewards`,
`змркалица` and `bookshelfy` — so on this tier the standalone question was the
only thing withholding any of them, and it missed one.

So the operating point is worse on both sides than the spec records: the
judgement refuses ordinary words, and it passes coinages. Neither number can be
read off a single tier, and the choice in the next section cannot be made until
both are sized.

## What is left

Score the class on a tier, and read the two classes apart. If ordinary words are
refused at a materially higher rate, the operating point in
`spec/functional-description.md` needs its other half written down, and the choice
becomes explicit: accept the false refusals, soften the standalone question, or
stop letting a single refusal withhold the whole entry.

Note that the third option is now partly taken for a different reason: a refusal
on a multi-word submission no longer withholds the entry, because the judgement
is about one lexical unit and running text is not one. That narrows this defect
to single-word submissions, which is where all three observations sit.

That fallback needs the same tier. It fired on none of 2,624 recorded multi-word
answers, because no fixture ever submitted the input that provokes it: two content
words with no unit between them, which is neither a fragment carrying a real unit
nor a clause. Three such word lists are now registered — `Ampel links`, the case
the reader reported, plus an English and a Serbian one — at three calls on the
full tier. What they measure is the failure, not the refusal: carding the pair as
a dictionary entry. A refusal is a right answer there, and now leaves the reader a
chip per word. Reported as a diagnostic, gating nothing, for the same reason the
ordinary class gates nothing — the rate is the question.

## What not to do

Do not tune the standalone question against these three words. Three refusals
found by accident are a signal to measure properly, not a target to fit — and the
question's framing is exactly what the existing measurement showed to be decisive,
so a wording change made to rescue `отад` would move the coinage side too, silently.
