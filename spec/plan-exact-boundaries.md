# Implementation plan — the boundary of a suggested unit

Delete this file once the work has landed. What outlives it belongs in
`spec/decision-phrases-and-sentences.md`.

This plan deliberately stops before naming the code to write. The evidence says
the fix is mostly deterministic, but which repairs are worth their risk is a
question the experiments below answer, and fixing the route first would be
guessing.

## The problem

`exact source boundaries` is 11 of 21, with 16 of 21 registered units found — the
figures from the last full tier measured on a healthy pool. A chip's boundary is
not cosmetic: the chip is what the reader taps, and a tap builds the note.

Tapping the nine imprecise chips exactly as the reader would — the chip text
plus the text it came from, with unit intent — produced this:

| result | count | example |
|---|---|---|
| the right dictionary entry | 3 | `Ne bojim se` → `bojati se` |
| the untidy surface kept as the headword, **and declared a misspelling** | 4 | `freue auf` → `freue auf`, relation `typo` |
| answer rejected, falls to the paid fallback | 2 | `ми се не иде`, `nije u redu` |

The control says the tap itself is sound: the six click fixtures, whose surfaces
are exact, pass 6 of 6.

So an imprecise boundary costs the reader their card outright. An answer that
calls the submission misspelled and still heads itself with that spelling cards
nothing, so those four cases store nothing at all and offer to "fix" a word the
reader had just read in the text. That is the harm option D goes after.

The one case with no phrase chip at all (`се изненадио`) is the mildest of the
nine: tapping the bare word returned `изненадити се` correctly, so the all-words
chip row does catch it.

## What the evidence says

The model names the entry correctly and mis-copies the text. In five of nine the
dictionary form it returned is exactly right while the copied surface is not:

| dictionary form returned | surface returned | text |
|---|---|---|
| `sich freuen auf` ✅ | `freue ... auf` — no `mich` | `Ich freue mich schon sehr auf den Sommer.` |
| `look forward to` ✅ | `is looking ... forward to` — took the auxiliary | `He is looking forward to the trip.` |
| `se bojati` ✅ | `ne bojim ... se` — took the negation | `Ne bojim se više ničega.` |
| `die Nase voll haben` ✅ | `die Nase voll ... haben` — lemma where the text has `habe` | `Ich habe die Nase voll von diesem Lärm.` |
| `činiti se` ✅ | `se čini` — correct, **and discarded by us** | `Sve mi se čini da nešto nije u redu.` |
| `не ићи се` ❌ | `ми се ... не иде` | `Данас ми се уопште не иде на посао.` |
| `јавити се телефоном` ❌ | `јавио ... се телефоном` | `Он ми се јуче јавио телефоном.` |
| `nije u redu` ❌ | `nije u redu` | `Sve mi se čini da nešto nije u redu.` |

Five classes, and only two of them are the model failing to know the answer:

1. **Negation pulled into the unit** — three cases.
2. **An auxiliary or a current argument pulled in** — two cases.
3. **A bound clitic or support verb left out**, or written as a lemma the text
   does not contain — two cases.
4. **Our own overlap rule** — one case. The model returned both `se čini da` and
   `se čini`; the first claimed the words and the better proposal was dropped for
   overlapping. This is our defect, not the model's.
5. **Not proposed at all** — one case.

**The prompt already states the rules it is failing.** It says to leave out
negation and the current subject, object or complement, and to include every
fixed piece in the form it takes in this sentence. Both are stated; both are
broken, in opposite directions, in the same run. Restating them louder is
therefore the least promising route, and the run history agrees: four prompt
generations scored 18, 9, 16 and 17 distinct registered units on the same
fixtures.

## Where a fix could live

**A — repair in the backend, using the answer against itself.** The dictionary
form and the copied surface describe one unit twice, so each checks the other. A
reflexive marker present in one and absent in the other; a token in the surface
that nothing in the dictionary form accounts for. Both are closed-class,
per-language questions, and the project already holds per-language data. This is
the pattern the project chose deliberately — obligations move out of the prompt
and into the parser, which is what keeps the prompt short enough for the free
pool to follow. Cheapest, and the only route that fixes a class rather than a
case. Keep any closed list in the language data, never in the parser.

**B — resolve overlap by fit rather than by arrival.** Prefer the proposal whose
surface the dictionary form accounts for exactly, instead of the one that
arrived first. Deterministic, small, and it repairs our own defect.

**C — worked examples instead of restated rules.** The prompt carries one
example and it demonstrates separation only; nothing in it shows negation
staying out or a clitic staying in. One positive and one negative worked example
is a different intervention from saying the rule again. Expected to be weak
alone; cheap to combine with A.

**D — the tap side, where the harm actually lands.** Four of the nine failures
share one shape: a spelling correction declared for a string the reader had just
seen in the text. A chip tap carries the text it came from, so a string
occurring verbatim in that context cannot be a misspelling. Rejecting that
verdict is deterministic and removes the false control. Whether it also recovers
the headword is unknown — E5 answers that. This one fixes the harm for every
imprecise chip, not only the nine measured.

## Experiments

Four of these cost nothing: they re-score answers already bought. Run them
before spending a single call. Score them against answers recorded under the
prompt they are meant to judge — the near-neighbour work in
`plan-near-neighbour-offer.md` changed the prompt, so a recorded set from before
it reports as a separate arm and reads as zeroes against the current one.

**E1 — does the dictionary form know what the surface does not?** Over every
recorded text answer, count how often the returned dictionary form accounts for
exactly the registered unit while the surface does not. Decides whether A has a
signal at all. The nine-case sample says five of nine; the full set says whether
that holds. *Zero cost.*

**E2 — negation stripping, offline.** Apply a per-language closed negation list
to the recorded chips and re-score the boundary. Upper bound for the cheap half
of A. Predicted: three of nine. *Zero cost.*

**E3 — overlap by fit, offline.** Re-run the fill over the recorded proposals
choosing the best-fitting rather than the first. Predicted: one of nine — but
the number that matters is how many currently-correct chips it loses, which must
be zero. *Zero cost.*

**E4 — how often is a false spelling verdict declared?** Over every recorded
click and tap, count the answers declaring a correction for a string that occurs
verbatim in the supplied context. Sizes D. *Zero cost.*

**E5 — the tap after a repair.** Take the chips as E1–E3 would produce them,
plus the nine unrepaired controls, and tap both. This is the only measurement
that shows whether a better boundary produces a better card; everything above
measures the boundary alone. *About 18 calls.*

**E6 — worked examples, one smoke run.** Only after A and B have landed, so its
effect is separable from theirs. *About 33 calls.*

## What the measurement cannot do

Twenty-one registered units is a small denominator: one unit is five points and
three units are the whole gap. Four prompt generations produced 18, 9, 16 and 17
on the same fixtures. **A single smoke run cannot tell a two-unit improvement
from noise**, so no prompt change is accepted on one run. A deterministic change
is a different case: it is re-scored over every recorded answer at once, and its
regression risk is measured directly as chips it used to get right and now does
not.

## The decision this plan must settle

The registered-unit gate currently counts a chip sharing most of the unit as
found. That relaxation was accepted on the reasoning that an omitted word stays
one tap away from the same entry — which the tap measurement above has now shown
to be false in four cases of nine. The mandatory semantic review of the full tier
reached the same conclusion independently, naming `freue ... auf` for `sich freuen
auf` as a match the screen should not be counting: if the chip is what the learner
cards, a surface missing `mich`, `sich` or `се` is not one. Either the justification is replaced with one
the data supports, or the gate returns to exact matching with a threshold set
from what a repaired backend actually reaches. Settle it once the deterministic
repairs have landed and the number is real, not before.
