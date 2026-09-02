# Implementation plan — what the 2026-09-02 tier rejected, and what it costs

Delete this file once every item below is settled. The run is
`experiments/.bench-repair`: 216 calls, pool healthy (204 of 204 provider
answers, workhorse answering 176), every automated gate green, and **rejected by
its mandatory fresh review**. A green screen proves conformance to contracts, and
this is the run where that distinction earned its keep.

Two of the findings are already fixed, in the same commit that recorded them: the
review packet now shows the carded classes it could not show, and
`decision-answer-shape.md` no longer claims no misspelling ever drew a
near-spelling offer. What follows is what is still open.

## 1. A gate the checked-in spec does not authorise

`spec/decision-phrases-and-sentences.md` states that confirmation and full
require **five of six** exact typo corrections. `one_note_bench.py` gates at
three, and its comment concedes the arm has measured three and four across runs.
This tier scored four: green against the code, red against the spec.

The code's argument is real — production settles a declared misspelling with the
paid model at six of six, and an undetected one the standalone judgement refuses
is never carded — but it is an argument the spec does not carry, and a reader of
the spec would call this run failed.

**This is not for the party defending the run to settle.** Either the gate is too
loose and the run fails it, or the spec is stale and must say why three is the
honest bar for what this arm alone can see. Decide it on its own, and write the
argument down wherever it lands.

## 2. A coinage neither judgement refused, and carded

`bookshelfy` came back vouched for by both the article's verdict and the
standalone question, and was carded with invented senses, an invented register
("интернет-сленг 2010-х") and an invented etymology. This is the failure the
double judgement exists to prevent, and it is the first time both halves have
missed the same word.

Worse, the article's own verdict vouched for **all five** coinages in the arm, so
the standalone question was the only thing withholding any of them on this tier.
Sized and decided in `attestation-refuses-real-words.md`, together with the
opposite error — the ordinary words it refuses.

## 3. A card that teaches the opposite of its headword

`verdict:sentences-split:de:6` headed `in Frage kommen` and translated it
"не может быть и речи". The expression means the reverse; only *nicht* in Frage
kommen is "out of the question", and the answer's own origin paragraph says so
two lines below the gloss. A well-formed second example survives the parser, so
the note builds, and the reverse card asks the learner to produce `in Frage
kommen` for "не может быть и речи".

Nothing structural catches an inverted gloss: it is a correct-shaped card whose
content is wrong. `decision-answer-shape.md` lists what the answers are known to
get wrong, and this class is not on it. Measure how often it happens before
choosing a route — a single item is not a rate.

## 4. Bilingual examples reach the card, and the guard cannot see it

`typo-en-recieve` carded `"Мы должны <b>receive</b> письмо до конца недели."` —
a Russian sentence with the English headword wedged in. The outside-context guard
in `card.py` asks only whether any character outside the highlight is alphabetic,
so Cyrillic counts as source-language sentence context. The reviewer found the
same shape in five items.

This one is deterministic and ours: the guard needs a source-language test, not a
letter test. Cheapest of the four, and the only one that does not need a tier to
decide — though landing it does need one to confirm, like any parser change.

## 5. Article defects the spec already forbids

Reported, not yet sized: forms tables naming case, tense and person (the
functional description forbids naming them at all); tables on invariable words;
a bare part-of-speech line; invented etymologies stated as fact; several wrong
grammar claims in Serbian and German articles. These are prompt-side, so none of
them may be chased with a one-shot probe — see the pacing rule in `CLAUDE.md`.

Their common shape is worth noting before anyone writes a prompt fragment: the
payload is usually clean while the *visible article* carries the defect. The card
is safer than the prose the reader is given.
