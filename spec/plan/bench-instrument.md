# Implementation plan — two places the bench reports what is not so

Delete this file once both are settled. Nothing here changes what the app
does; it changes what the harness claims about it, which is why none of it can be
done quietly — a gate that moves without an argument is worth less than the red
reading it replaced.

The two are independent. Do them in any order, and delete each section as it
lands rather than waiting for the rest. Two others have landed and are gone: the
report now prints the repaired-payload count beside the parseable one, and the
registered-unit gate counts what the learner would card, at a floor taken from
the spread six full runs actually measure.

## 1. A neighbour fixture that measures nothing

`neighbour-sr-otad` submits `отад`, and the standalone judgement refuses it as
unused wording — twice now, on two consecutive tiers. A refused submission never
reaches the branch that would offer a neighbour, so the shot reports "no offer"
for a reason unrelated to the offer, and `registered pair offered` reads 1/3 when
its real denominator is 2.

The pairing was weak even before the refusal: `отад`'s own nearest neighbour is
its variant `отада`, not `отац`, so a model naming `отада` would have been right
and scored a miss.

- Replace the pair in `NEIGHBOUR_CASES` in `experiments/one_note_bench.py`. It
  needs a real Serbian word the answer will vouch for, one or two letters from a
  markedly commoner one, where the commoner word is the one a competent speaker
  would actually name.
- Check the frequency claim before registering it, and do not pick a pair because
  it looks easier to hit: the English and German pairs are the evidence the gate
  rests on, and a soft Serbian pair would only inflate it.
- One call on the attestation shot for the candidate settles the refusal risk
  before a tier is spent.

That the attestation refuses `отад` at all is a separate defect, in
`attestation-refuses-real-words.md`.

## 2. One verdict fixture labelled unlike its siblings

`verdict:clauses:de:0` — "Ich habe keine Zeit" — is expected `text`. The model
answers `unit` and cards `Zeit haben`, which is on that fixture's own accepted
list, and the shot scores a hard error. Its four siblings of the same shape —
`Ich weiß nicht`, `Das stimmt`, `I have no idea`, `Не знам` — are registered in
`DEFENSIBLE_UNIT_VERDICTS` and score `ambiguous` for the identical answer. The
difference is the registration, not the answer.

`_verdict_outcome` grades the branch alone and never looks at what was extracted,
so this is the only lever: either `clauses:de:0` joins the list, or the argument
for keeping the other four there stops applying to it.

Two things this section must not become:

- **It does not open the gate.** `obvious hard verdict errors` needs 12 or fewer
  of 122; excusing this one leaves 13. Anyone reaching for it to turn a red gate
  green will find it does not, and will then be tempted by
  `verdict:fragments:de:6` and `de:9`, which card their accepted extraction too.
  Those two are a different case: taking the unit branch on a fragment carrying
  free material is a gamble the model lost six times in the same run it won
  those two. Excusing the wins while counting the losses measures nothing.
- **It is not a change to make while shipping something else.** The party
  defending a result does not move the line it is judged against. Land it on its
  own, with the argument written down.
