# Implementation plan — two small prompts instead of one large one

**Not started.** This is the next version's work, opened after the release that
closed `release.md`. Nothing here is committed to beyond the measurements below;
the architecture is the proposal, not a settled decision.

## The claim

The merged prompt is 8,787 characters for a chip tap, and 47% of it cannot apply
to that request. A fast free model is asked to hold two contracts in view and obey
whichever one turns out to be live. The proposal is the opposite: two short
prompts, each with one job, and a cheap call to choose between them where the
choice is not already known.

## What was actually decided before, and what was not

`decision-answer-shape.md` records that selecting one of two prompts **before
asking the model** reproduced a classification problem that surface punctuation
and length cannot solve. What that rejected is **classification in code**. It did
not evaluate, and no measurement covers:

- a cheap model call whose only job is to answer unit-or-text, followed by the
  specialised prompt for the branch it named;
- a specialised prompt on the path where nothing needs classifying at all,
  because the learner tapped a chip and the branch is known from the action.

The app already issues two calls per submission — the article and the standalone
attestation judgement — so a second call is not a new cost shape here. The free
pool's daily quota is a bench problem rather than a product one: a reader does not
ask enough questions in a day to approach it.

## What is measured already

Sizes, on a unit-intent prompt of 8,787 characters:

| section | chars | share |
|---|---:|---:|
| branch decision — already made by the tap | 750 | 9% |
| leading verdict inside the article | 839 | 10% |
| text branch: how to write it | 245 | 3% |
| text branch: JSON schema | 177 | 2% |
| text branch: combinations | 582 | 7% |
| text branch: label and surface | 810 | 9% |
| `also_common` | 472 | 5% |
| the near-spelling search in rule 1 | 277 | 3% |
| **removable for this request** | **4,152** | **47%** |

The leading verdict is nearly redundant. Over five tiers, counting which judgement
withheld each attestation and typo fixture:

```
article verdict refused alone :  1
both refused                  :  8
standalone judgement alone    : 29
```

One withholding in thirty-eight is the whole contribution of a paragraph that
occupies the most expensive position in the prompt, and it forces every answer to
open with a JSON line before writing anything.

`also_common` is non-empty once in 201 answers and fires on one registered pair of
three; nothing downstream depends on its presence. Its instruction nonetheless sits
in rule 1 under the words "before writing anything else".

## The work

1. **Split by intent first, because it costs nothing and risks nothing.** A
   unit-intent request carries no text-branch contract; a text answer carries no
   unit-article specification. No capability is removed and no instruction that
   could apply is dropped. This alone is 21% of a chip tap.
2. **Drop the leading verdict from the article prompt.** The standalone judgement
   is a separate call and does the work. Removing it also removes `===USED===`
   parsing from the stream and the bounds that guard an unclosed judgement.
3. **Drop `also_common` and the near-spelling search.** Measure what the reader
   loses: on the recorded evidence, an offer that arrives once in 201 answers.
4. **Make origin conditional.** "Origin: always include it" is what produces
   confident invented etymologies — a wolf-`lupa` story for `Lupe`, `viel + leicht`
   for a misspelling. Ask for it only where it is known.
5. **Then, and only then, consider the classifier call** for the open submit box:
   one short prompt returning unit or text, then the specialised prompt. Compare
   against the merged prompt on the verdict matrix, which already measures exactly
   this. Two calls in sequence cost latency the merged prompt does not, so the
   comparison has to include how long the reader waits.

Steps 1-4 are separable and each has its own metric. Step 5 is the architectural
change and needs the verdict matrix to accept it.

## What this plan must not do

- **Do not measure two changes with one number.** Each of steps 1-4 has a metric
  that no other step touches; keep it that way, and read the aggregate for
  regression rather than for credit.
- **Do not re-derive the rejection of code classification.** It was measured and it
  stands. What is open is a model call, not a heuristic.
- **Do not let the prompt grow back.** Three narrow patches were added on the tier
  before this plan opened — the source-language example rule, heading-and-gloss
  coherence, and the clause branch rule. After the split, check each against its
  new home: a rule that only ever mattered to one branch belongs in that branch's
  prompt, and one that the split makes unnecessary comes out.
