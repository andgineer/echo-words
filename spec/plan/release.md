# Implementation plan — the remaining work, one tier, one release

**This is the only plan, and it is complete: everything still open is below.**
Delete it, and the `spec/plan/` directory with it, once the release is tagged.
Do not open a second plan — add to this one.

Facts already recorded in the decision specs (do not re-derive them): the
boundary repair and the gate that judges it in `decision-phrases-and-sentences.md`;
the context rule and the list of what answers are known to get wrong in
`decision-answer-shape.md`; the refusal rules and the source-language sentence
test in `functional-description.md`. Those specs describe **what was observed**.
Whether the product accepts it is decided here, and has not been.

## Part 1 — written, green, and never measured

All committed and passing `inv pre` and `inv test`; none has been through a tier
since it landed.

| change | what it does for the reader |
|---|---|
| boundary repair | the chip tapped is the unit, not a copy with the negation left in or the reflexive dropped |
| context equality | an answer is not thrown away because the model dropped a full stop |
| refused fragment → text | `ampel links` gives a chip per word instead of nothing |
| retry chip | a failed entry is offered back instead of retyped |
| source-language sentence test | a card front can no longer be a target-language sentence with the source word wedged in |
| typo gate | gates the card the reader gets, not whether the answer named the misspelling |
| word-list and ordinary-word fixtures | two classes that had never been measured |
| review packet | shows carded coinages, which it could not before |

## Part 2 — four defects that are open, not accepted

The previous tier (`experiments/.bench-repair`, 2026-09-02) passed every gate and
was rejected by its review. These four are what it found and nothing has decided
them. **Recording a defect in a spec is documentation, not acceptance.** Each
needs an explicit decision before the release, and the decision is the operator's
where it changes what the product tolerates.

**2.1 A coinage carded by both judgements.** `bookshelfy` was refused by neither
the article's own verdict nor the standalone question, and was carded with
invented senses, an invented register and an invented etymology. The article's
verdict vouched for all five coinages in the arm, so the standalone question was
the only thing withholding any of them, and it missed one. For a vocabulary app
this is the worst thing it does. The spec records the rate as none-to-three of
six surviving both; it does not say that is acceptable. **Decide: accept and say
so plainly in the spec, or add a third check.** Size it on the next tier first —
one observation is not a rate.

**2.2 A card that teaches the opposite of its headword.** `in Frage kommen` was
glossed "не может быть и речи", the reverse of what it means, with the answer's
own origin paragraph contradicting the gloss two lines below. Nothing structural
catches an inverted gloss: the card is correctly shaped and wrong. One
observation. **Measure the rate before choosing a route** — a registered fixture
class for expressions whose negation flips them would do it.

**2.3 `vieleicht` is caught by the wrong mechanism.** It is headed by the
misspelling in seven runs of ten, and every time the standalone judgement saves
it rather than anything in the typo logic. That judgement is not reliable on its
own: on the same tier it invented an attestation for `мозда`, calling it an
eastern-Serbian variant of `мозак`. The reader is protected by something that is
right for the wrong reason. **Size how often the judgement is the only thing
standing between a misspelling and a card.**

**2.4 Articles that break rules the spec states.** Forms tables naming case,
tense and person where the functional description forbids naming them; tables on
invariable words; a bare part of speech; confident invented etymologies; several
wrong grammar claims. These are prompt-side, so no one-shot probe may be used and
no single run can judge a prompt change. **Decide whether they block a release**
— they are visible prose, not card content — and if not, say so in the spec in
those words.

## Part 3 — the attestation operating point, still unchosen

The ordinary-word class scored 5 of 6 against 4 of 4 for famous words, the refusal
being `сврака`. The judgement refuses ordinary words and passes coinages, and the
spec states the false-refusal half only.

One tier is one sample. Score the class once more on the run below, then choose,
explicitly, between: accept the false refusals and write the other half down;
soften the standalone question, knowing the measurement showed its framing is what
decides the coinage side too; or stop letting a single refusal withhold the whole
entry. Do not tune the question against `отад`, `manger` or `сврака` — three
refusals found by accident are a signal to measure, not a target to fit.

## Part 4 — two experiments, to run or to abandon on the record

Neither is started. Abandoning is a fine answer; dropping them silently is not.

- **E5, the tap after a repair (~18 calls).** Take the chips as the repair now
  produces them plus the unrepaired controls, and tap both. The only measurement
  showing whether a better boundary produces a better card. Weakened by E4, which
  found the repair removes most failing taps at source. Recommend running it only
  if the tier shows the boundary still costing cards.
- **E6, worked examples in the prompt (~33 calls).** One positive and one negative
  worked example instead of restating rules. Only after the repair has a tier, so
  its effect is separable, and it cannot be accepted on one run. On the current
  arm the three remaining misses are proposals the model never made at all, which
  no boundary example addresses — weigh that before spending the quota.

## Part 5 — the path

1. `uv run inv pre` and `uv run inv test`, both fully green.
2. **One full tier**, 216 calls. Ask the operator first: it is their quota and one
   tier does not fit twice in a day.
   `uv run python experiments/one_note_bench.py run --tier full --out
   experiments/.bench-release2 --concurrency 2 --pace 2.0`, then `run-clicks`,
   then `report`.
   - Resume with `--resume`, never restart.
   - Read availability before results. The workhorse
     `google-gemini-3.5-flash-lite` far below its usual share, or absent, means an
     exhausted pool and a void run: say so and wait.
3. **Fresh semantic review** on Opus, by an agent that did not run the bench,
   over every item of `review-packet-full.json`, in the same turn the report lands.
4. **Decide Parts 2 and 3 on the numbers**, and put each decision to the operator
   as options with trade-offs and a recommendation — never as a raw question.
5. **Release**: record the accepted numbers and every decision in the decision
   specs, delete this file and the `spec/plan/` directory, drop the plan paragraph
   from `CLAUDE.md`, then `inv ver-release`. Ask before pushing and before
   deploying, every time, for that act.

## The two ways this goes wrong

**Closing an open question by writing it into a spec.** That is what happened to
Parts 2 and 3 once already: documentation was mistaken for acceptance and the
plan count fell without a decision being made. A spec sentence saying a defect
was observed does not mean the product tolerates it.

**Spending the pool twice.** Every fixture is registered and every deterministic
change is in. If the first run is valid, its numbers are the ones to decide on.
