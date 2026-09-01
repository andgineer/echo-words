# Implementation plan — one near-neighbour fixture measures nothing

Delete this file once the Serbian pair is replaced and a tier has scored it. The
feature itself is finished and recorded in `spec/decision-answer-shape.md`; this
is the instrument, not the product.

## Where this stands

`also_common` ships and works: over a full tier the offer fired on
`neighbour-en-causal` and nowhere else, with no false offer anywhere in 201
answers. Two of the three registered pairs are sound fixtures. The third,
`neighbour-sr-otad`, has never measured anything.

Its submission `отад` is refused by the standalone judgement as unused wording —
twice now, on two different tiers. A refused submission never reaches the branch
that offers a neighbour, so the shot reports "no offer" for a reason that has
nothing to do with the offer, and the near-neighbour detail line reads 1/3 when
its real denominator is 2.

The refusal is also a defect in its own right: `отад` is a standard Serbian
adverb, the short form of `отада`. It is the third real word the attestation has
refused, after `manger`. That belongs to the attestation's operating point, not
here.

## What to do

1. Replace the pair in `NEIGHBOUR_CASES` in `experiments/one_note_bench.py`. It
   needs a real Serbian word the answer will vouch for, one or two letters from a
   markedly commoner one, where the commoner word is the one a competent speaker
   would actually name. `отад`'s own nearest neighbour is its variant `отада`,
   not `отац`, so even a correct answer would have been scored a miss.
2. Check the frequency claim for the candidate pair before registering it, and do
   not pick a pair because it looks easier to hit — the English and German pairs
   are the evidence the gate rests on, and a soft Serbian pair would only inflate
   it.
3. Confirm the candidate is not refused: one call on the attestation shot for that
   word settles it before a tier is spent.
4. Score it on a full tier, then the mandatory fresh-agent review, then record the
   result where the rest of the measurement lives.
