# Implementation plan — the commoner near-spelling offered beside the card

Delete this file once the work has landed. What outlives it belongs in
`spec/decision-answer-shape.md`; the requirement itself is already in
`spec/functional-description.md` and needs nothing added to it.

## Where this stands

The code is written, committed and green. The measurement has now been made and
the feature does not work: the offer never fires. Commit `7551e4e9` carries the
code; the release deployed to the host is `890c9cfd`, the commit before it, which
does **not** contain any of this, and nothing here is fit to deploy.

`inv pre` and `inv test` pass (582 pytest, 75 frontend). The gate `a likelier
near neighbour is offered` is red on a valid run: 3/6, needing 4, with all three
successes coming from ordinary words correctly left alone.

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

**The pool knows the neighbour and will not put it in the field.** This is the
finding that decides what to do next. In `experiments/.bench-nb-real/`, on a run
where every one of 195 calls was answered, `causal` came back with "не следует
путать с *casual*" and `wider` with "не следует путать … с *wieder*" — the exact
pairs the fixtures registered, named in the article prose, with `suggestion`
empty in both. `openrouter-nemotron-3-ultra` did the same on `causal` in the
earlier probe. Two model families, two languages, first answer each time. The
missing step is routing, not knowledge.

**Placement decides whether the check happens at all.** Asked among the JSON field
descriptions, it was never carried out — by then the article is written and the
fields only transcribe it. Moved into article rule 1, where the answer decides
what the word is, it fired once in an early probe; over a measured tier it does
not.

**Qualifiers subtract.** A wording that added "rare, archaic or narrow" broke the
one case that had worked under the plainer "markedly commoner word", with the same
model answering. The plainer wording is what is committed.

**The false side needs no defending.** Zero invented offers on ordinary words
across every probe, including the loosest wording, and again over the full tier.
The guard written against that risk cost a true positive and bought nothing.

**Three fixtures measured the wrong thing.** `Beet` and `дуг` are ordinary words
looked up in their own right; the model declined them correctly. `manger` never
reached this logic at all — the judgement refuses it as unused. Those three were
replaced by `causal`/`casual`, `wider`/`wieder`, `отад`/`отац`, and `отад` has now
failed the same way: the answer was `{"used": false}`, so it never reached the
branch. `отад` is a real, standard Serbian adverb, the short form of `отада`, so
that refusal is also a defect in its own right — recorded in
`spec/decision-answer-shape.md`.

## What is left

1. **Replace the Serbian fixture.** It has to be a real word the answer will
   vouch for, one or two letters from a markedly commoner one, and the commoner
   word must be the neighbour a competent speaker would actually name — `отад`'s
   own nearest neighbour is its variant `отада`, not `отац`, so a model naming
   `отада` would be right and scored a miss. Verify the frequency claim for the
   pair before registering it, and do not pick a pair because it looks easier.
2. **One prompt change, then one tier.** The change to try is carrying the
   neighbour the article already names into the `suggestion` field — the field
   description and article rule 1 currently ask for it in two places and get it
   in neither. Do not vary anything else in the same measurement.
3. Run `uv run python experiments/one_note_bench.py run --tier full --resume
   --wait 180 --pace 2 --concurrency 1 --out experiments/.bench-nb-<name>`, a
   fresh output directory: the recorded answers are bound to the current prompt
   hash and none of them survive a prompt change.
4. Read availability before results. Provider answers well below the call count,
   or `google-gemini-3.5-flash-lite` missing from the tally, means the run is void
   and says nothing about the change.
5. `run-clicks`, then `report --tier full`.
6. Fresh-agent semantic review of the packet, and record the decision in
   `spec/decision-answer-shape.md`.

## The decision the measurement has to inform

Whether the offer appears at all. The gate asks for four of six with the three
ordinary words counting toward it, so the offer has to fire at least once.

If it does not fire once the prompt asks for it in the one place that works, the
honest conclusion is that the free pool will not do this, and the choice is
between dropping the requirement and deriving the neighbour ourselves — edit
distance against a frequency list, which is a computation rather than a language
judgement, and would need a frequency resource per language that the project does
not have today. That conclusion is not available yet: the pool demonstrably
produces the neighbour in prose, so the prompt has not yet been given its fair
test. Do not reach for it, and do not answer the question by loosening the gate
or by choosing easier fixtures.
