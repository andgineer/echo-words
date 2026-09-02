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

## 1. A gate the checked-in spec does not authorise — SETTLED

The spec required five of six exact typo corrections and the harness gated at
three; ten runs across every prompt generation had scored three or four, never
five. Both numbers measured the same wrong thing: whether the answer *names* the
misspelling as one.

What the reader actually gets was measured instead, over every recorded run. A
card headed by the mistyped spelling — the one card that teaches the mistake —
reached the reader **zero times in every run where both judgements were in
place**; the only two exceptions predate the standalone judgement entirely. Of
the six fixtures, four are corrected and named, one (`podrška`) is silently
corrected and hands over exactly the right card while scoring nothing on the old
count, and one (`vieleicht`) is withheld because the standalone judgement refuses
it, so nothing is shown.

So the gate is now the harm and nothing else: no entry may be headed by the
spelling the reader mistyped, zero tolerance, a withheld entry counting as safe.
The naming rate is a diagnostic. This applies the project's own rule — keep as
gates only what breaks the product, and demote mechanical exactness to
diagnostics — rather than moving a bar, and it makes the arm stricter where it
matters: the old gate would have passed a run that carded `vieleicht`, and this
one will not.

## 1b. The remaining hole in that arm

`vieleicht` is headed by the misspelling in seven runs of ten, and every time it
is caught by the standalone judgement rather than by anything in the typo logic.
That judgement is not reliable on its own — on this same tier it invented an
attestation for `мозда`, calling it an eastern-Serbian variant of `мозак`. The
reader is therefore protected by a mechanism that is right for the wrong reason.
Worth sizing before anyone leans on it further.

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
