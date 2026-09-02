# Implementation plan — one tier, one review, one release

**This is the only plan. Delete it, and the directory with it, once the release
is tagged.** Everything that outlives it is already in the decision specs: the
boundary repair and the gate that judges it in `decision-phrases-and-sentences.md`,
the context rule and the known article defects in `decision-answer-shape.md`, the
refusal rules and the source-language sentence test in `functional-description.md`.
Nothing below needs to become a new plan; if something here turns out to need
one, that is a decision to take deliberately, not a reflex.

## Everything is written. Nothing is measured.

All of it is committed, green on `inv pre` and `inv test`, and none of it has
been through a tier since it landed:

| change | what it does for the reader |
|---|---|
| boundary repair | the chip the reader taps is the unit, not a copy with the negation left in or the reflexive dropped |
| context equality | an answer is no longer thrown away because the model dropped the final full stop |
| refused fragment → text | `ampel links` gives a chip per word instead of nothing |
| retry chip | a failed entry is offered back instead of retyped |
| source-language sentence test | a card front can no longer be a Russian sentence with the source word wedged in |
| typo gate | gates the card the reader gets, not whether the answer named the misspelling |
| word-list, ordinary-word fixtures | the two classes that had never been measured |
| review packet | shows carded coinages, which it could not before |

The previous tier (`experiments/.bench-repair`, 2026-09-02) passed every gate and
was rejected by its review. Its findings are all either fixed above or recorded
in the specs as accepted operating points. **Do not re-open them; the next run is
a fresh acceptance, not an appeal.**

## The path, in order

1. `uv run inv pre` and `uv run inv test`, both fully green. Nothing below runs
   against a red tree.
2. **One full tier.** `uv run python experiments/one_note_bench.py run --tier full
   --out experiments/.bench-release2 --concurrency 2 --pace 2.0`, then the same
   with `run-clicks`, then `report`. 216 calls. Ask the operator before spending
   it; it is their quota and one tier does not fit twice in a day.
   - Resume with `--resume`, never restart: it keeps every answer already bought.
   - Read availability before results. The workhorse `google-gemini-3.5-flash-lite`
     answering far below its usual share, or absent, means an exhausted pool and a
     void run. Say so and wait rather than reporting the numbers.
3. **Fresh semantic review**, on Opus, by an agent that did not run the bench.
   Every item of `review-packet-full.json` — now including the carded coinages
   and the ordinary-word class. Run it in the same turn the report lands.
4. **If the review accepts**: record the accepted numbers in the decision specs,
   delete this file and the `spec/plan/` directory, drop the plan paragraph from
   `CLAUDE.md`, and cut the release with `inv ver-release`. Ask before pushing and
   before deploying — every time, for that act.
5. **If the review rejects**: fix what is genuinely broken, and be strict about
   what that means. A model writing a weak article is not a reason to hold a
   release; a card that teaches something false is. Anything accepted rather than
   fixed goes into a decision spec as an operating point, never into a new plan.

## The two things most likely to go wrong

**Reading a model-quality complaint as a blocker.** The review will find weak
articles — invented etymologies, forms tables naming cases, an occasional wrong
grammar claim. Those are recorded in `decision-answer-shape.md` as known and are
not release blockers. The blockers are: a card that teaches something false, a
coinage carded, a card front in the wrong language, a chip that reverses its
sentence. Judge by what reaches the deck.

**Spending the pool twice.** Every fixture is registered and every deterministic
change is in. There is nothing left that a second run would tell us and a first
would not, so if the first run is valid, its numbers are the ones we ship on.
