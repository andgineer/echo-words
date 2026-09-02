# Implementation plan — one place the bench reports what is not so

Delete this file once it is settled. Nothing here changes what the app does;
it changes what the harness claims about it, which is why it cannot be done
quietly — a gate that moves without an argument is worth less than the red
reading it replaced.

Three others have landed and are gone: the report prints the repaired-payload
count beside the parseable one; the registered-unit gate counts what the learner
would card, at a floor taken from the spread six full runs actually measure; and
the void Serbian neighbour pair is replaced by `месо` beside `место`, which has
the shape the English and German pairs have — one letter inserted, and one
plausible commoner word rather than a field of them.

## One verdict fixture labelled unlike its siblings

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
