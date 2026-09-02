# Implementation plan — the boundary of a suggested unit

Delete this file once the landed repair has been measured on a tier and the
remaining two experiments are either run or abandoned. What outlives it belongs
in `spec/decision-phrases-and-sentences.md`, which already carries the repair,
the rejected alternative and the gate the evidence settled.

## What landed

The backend repairs a copied boundary against the dictionary form the same
answer returned — option A, in `segments.py`, with the closed lists in
`languages.py` beside the Serbian script folding:

- closed-class material a unit never carries is dropped from the chip
  (negation, subordinators, copulas — per language, empty for a language not
  listed, which is why an operator can add one without touching this);
- a reflexive marker the dictionary form names is taken back in as the form the
  sentence actually spells, so `sich freuen auf` over `Ich freue mich …` cards
  `freue mich auf` and `sich beschränken auf` over `Wir müssen uns …` cards
  `uns auf beschränken`;
- the trim is withheld unless what survives it is the unit itself.

That last condition is the one the measurement forced and it is not
negotiable downward. Trimming unconditionally scores two boundaries better
across the corpus, and it produces `nešto u redu` from `nešto nije u redu` and
`kommt überhaupt in Frage` from `kommt überhaupt nicht in Frage`. The chip is
what the reader taps and cards, so a chip that reverses the sentence is worse
than the untidy one it replaces.

## What the experiments established

All four zero-cost experiments were run over 3,956 recorded attempts across 40
bench directories, before any call was spent.

**E1 — the dictionary form knows what the surface does not.** On the current
arm the returned dictionary form is right for 17 of 18 unit slots while the chip
is exact for 13. Across the 665 slots of older arms the same gap holds: 78.6%
against 61.2%, with 21.8% of all slots showing a right label beside an inexact
chip. The signal option A needs is there, and it is not an artefact of one
prompt.

**E2 — the repair, offline.** Over 878 unit slots the repair moves exact
boundaries from 420 to 508 and found units from 511 to 562, and **loses nothing**:
no chip exact before the repair is inexact after it. On the tier that gates,
`.bench-nb-field`, it moves 13 of 21 exact and 15 of 21 found to 16 and 17. The
17 chips it removes entirely are all fragments of function words — `уопште не`,
`Ne više`, `nije u` — and every word in them keeps its own single-word chip.

**E3 — overlap by fit: rejected.** Ordering proposals by how completely the
label accounts for the surface, instead of by arrival, recovers one boundary and
loses two. Its own acceptance test in this plan was that it must lose zero. The
defect it was written for — `se čini da` claiming the words before `se čini`
could — is fixed by the trim instead, which shortens the greedy proposal before
it claims anything. Option B is closed.

**E4 — cannot be answered from recorded data, and that is the finding.** Every
one of the 152 recorded taps submits an exact chip or a lemma; no imprecise chip
has ever been tapped in a recorded run. The four false spelling verdicts this
plan cites came from taps made by hand. The premise that the corpus could size
option D was wrong. What did change is the harm surface: the chips that produced
those four verdicts — `freue auf`, `nije u redu`, `Ne bojim se` — are now exact,
so the repair removes most of option D's occasions rather than its mechanism.

## The decision this plan set out to settle

Settled, in the direction the evidence pointed. The registered-unit gate counted
a chip sharing most of the unit as found, on the reasoning that an omitted word
stays one tap away — which the tap measurement and the mandatory semantic review
both showed to be false. The gate now counts only what cards the registered
entry: an exact chip, or a surface registered in `ACCEPTED_SURFACE_ALTERNATIVES`.
Expanded and partial boundaries are still reported, as diagnostics.

The floor comes from what a repaired backend actually reaches. Six full runs
that answered every text shot, each re-scored against its own prompt arm,
measure 13, 14, 16, 16, 17 and 17 cardable of 21 — against 11, 12, 12, 13, 13
and 14 before the repair. `MIN_CARDABLE_UNITS` is 13, at the bottom of that
spread, on the same reasoning the old floor used: a floor inside the spread
reddens on the draw. After the repair the `partial boundary` match kind stops
appearing in full runs altogether.

## What is left

- **A tier, and a fresh semantic review.** The repair is deterministic and its
  regression risk was measured directly over every recorded answer, but it is
  still the parser deciding what the app does with an answer. It needs the
  operator's pool quota. `context-equality.md` is waiting on the same run and
  one tier covers both.
- **E5 — the tap after a repair.** About 18 calls. Take the chips as the repair
  now produces them plus the unrepaired controls, and tap both. This is the only
  measurement that shows whether a better boundary produces a better card;
  everything above measures the boundary alone. Worth less than it was — E4
  showed the repair removes most of the failing taps at source — so run it only
  if a tier shows the boundary still costing cards.
- **E6 — worked examples in the prompt.** About 33 calls, option C. Only after a
  tier has measured the repair, so its effect is separable. Note what remains
  for it to fix: on the current arm the three misses left are proposals the model
  never made at all, which no worked example about boundaries addresses. Weigh
  that before spending the quota.

## What the measurement cannot do

Twenty-one registered units is a small denominator: one unit is five points.
Six prompt generations produced 18, 9, 16, 17, 14 and 17 on the same fixtures,
so **a single smoke run cannot tell a two-unit improvement from noise** and no
prompt change is accepted on one run. A deterministic change is a different
case, and this one was held to it: re-scored over every recorded answer at once,
with its regression risk measured directly as chips it used to get right and now
does not. That number was zero.
