# Implementation plan — the commoner near-spelling offered beside the card

Delete this file once the work has landed. What outlives it belongs in
`spec/decision-answer-shape.md`; the requirement itself is already in
`spec/functional-description.md` and needs nothing added to it.

## Where this stands

The code is written, committed and green. The measurement is not done. Commit
`7551e4e9` carries the work and says so in its own message; the release deployed
to the host is `890c9cfd`, the commit before it, which does **not** contain any
of this.

`inv pre` and `inv test` pass (582 pytest, 75 frontend). One bench gate, `a
likelier near neighbour is offered`, is red and unproven — not from a measured
failure but because no valid tier has ever scored it.

## The requirement

A submission that is a real word, spelled correctly, but a letter or two from a
markedly commoner one: the article and the card stay the learner's, and the
commoner word is offered beside them for the learner to switch to. It is advice,
not a correction — a correction replaces the submission, this only sits next to
it.

This was specified and had its interface string long before it had a prompt that
could produce it: `add.moreCommon` in both locales, and the switch button beside
the notice, were already there and unreachable.

## What is already built

- `src/echo_words/card.py` — `_word_relation` honours the declared relation, so a
  `same` or `morphology` claim keeps its suggestion instead of being rewritten
  into a typo. This part shipped in `890c9cfd`: it is inert without the prompt.
- `src/echo_words/prompt.py` — the check is asked for in article rule 1, at the
  heading, and the `suggestion` field description carries the second meaning.
- `experiments/one_note_bench.py` — the `neighbour` fixture family: `NeighbourCase`,
  six cases, `neighbour_shots`, `neighbour_ids_for_tier`, per-shot metrics, two
  gates, tier counts (smoke 55, confirmation 125, full 201) and a report section.
- Tests for all of it, in `tests/test_prompt.py` and `tests/test_one_note_bench.py`.

## What the experiments have established

**Placement decides whether the check happens at all.** Asked among the JSON field
descriptions, it was never carried out — by then the article is written and the
fields only transcribe it. Moved into article rule 1, where the answer decides
what the word is, it fired. Same model both times.

**Qualifiers subtract.** A wording that added "rare, archaic or narrow" broke the
one case that had worked under the plainer "markedly commoner word", with the same
model answering. The plainer wording is what is committed.

**The false side needs no defending.** Zero invented offers on ordinary words
across every probe, including the loosest wording. The guard written against that
risk cost a true positive and bought nothing.

**Two fixtures measured the wrong thing and were replaced.** `Beet` and `дуг` are
ordinary words looked up in their own right; the model declined them correctly and
even discussed `Bett` in the etymology while doing so. `manger` never reached this
logic at all — the judgement refuses it as unused. The registered pairs are now
`causal`/`casual`, `wider`/`wieder`, `отад`/`отац`.

## What is left

1. Wait for the free pool's daily quota. Confirm with one call before committing to
   a tier, and read the provider tally, not the wall clock.
2. `uv run python experiments/one_note_bench.py run --tier full --resume --wait 180
   --pace 2 --concurrency 1 --out experiments/.bench-nb-real`. That directory holds
   70 answers already bought; `--resume` keeps them.
3. Read availability first. Provider answers well below 187/189, or
   `google-gemini-3.5-flash-lite` missing from the tally, means the run is void and
   says nothing about the change.
4. `run-clicks`, then `report --tier full`.
5. Fresh-agent semantic review of the packet, and record the decision in
   `spec/decision-answer-shape.md`.
6. Act on what it finds.

## The decision the measurement has to inform

Three registered pairs across three languages. Whether the offer appears is the
question; the gate asks for four of six with the three ordinary words counting
toward it, so the offer has to fire at least once.

If it does not fire at all on a healthy pool, the honest conclusion is that the
free pool will not do this, and the choice is between dropping the requirement and
deriving the neighbour ourselves — edit distance against a frequency list, which
is a computation rather than a language judgement, and would need a frequency
resource per language that the project does not have today. Do not answer that
question by loosening the gate or by choosing easier fixtures.
