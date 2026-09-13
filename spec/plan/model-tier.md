# Implementation plan — is there a model that is fast *and* obeys

## Why this is open

Most of what is left unfixed in `observed-defects.md` is the model's own work:
invented origins, a wrong grammatical form on a card front, a false friend carded
as a translation, a note built on the wrong language's word. Eleven of its
seventeen items are that class, and no deterministic guard can see any of them —
the backend tests a sentence's alphabet, never its grammar. The levers on that
class are two: the prompt, and which model answers. This plan is the second one,
and the paid catalog's fast aliases have never been called even once.

The repairs the answer path carries — the card-sentence letter test, the JSON
repair applied before parsing, the formatting sanitiser, the escalation of a
declared misspelling — are a lesser prize than they look, and the measured table
below says why: paying buys formatting and the wrong-language sentence outright,
buys nothing at all on the JSON repair, and is worse on coinage judgement. A
faster, more obedient tier is worth having for what the reader reads, not for the
repairs it might retire.

Over 179 fixtures answered by both tiers under an identical prompt:

| | `gpt-fast` | pool primary |
|---|---:|---:|
| whole answer, median | 10.0 s | **2.2 s** |
| p90 | 19.0 s | 9.3 s |
| first character | 7.06 s | **0.91 s** |
| formatting clean | **98.3%** | 93.3% |
| target-language card sentences | **0%** | 1.15% |
| payload needed JSON repair | 13.4% | 13.4% |
| verdict correct | 93.3% | 92.7% |

So paying retires *some* classes outright and leaves others untouched: the JSON
repair layer is identical on both tiers, and coinage judgement is measurably worse
paid (`decision-llm-backend.md`, "What money buys"). The hypothesis under test is
therefore narrow and must not be inflated into "a better model fixes everything".

**The constraint is latency, not money.** The operator has stated that the cost of a
paid tier at this volume is not a constraint. Seven of `gpt-fast`'s ten seconds pass
before the first character arrives, and the app streams, so that is the number a
reader feels: 0.9 s of waiting becomes 7 s. That is the whole reason a tier this
good is not simply switched on, and it is why an arm is screened on latency before
it is read on quality.

What the reader waits for today is no longer the model in any case: the dead step at
the head of the audio chain spent up to its whole ten-second budget inside a job the
pool answered in 2.2 s, and it is gone. So this plan is not a rescue from a slow app;
it is a bid to improve the answers of one that is fast enough.

**And the survey that chose the tier was partial.** It measured `sonnet`, `gpt` and
`gpt-fast`. llmbroker's curated paid catalog carries nine aliases, and the ones
whose whole selling point is speed have never been called. The catalog is readable
programmatically, so the list below is what it carried when this was written and the
run takes its own from the catalog.

| alias | model | why it is a candidate |
|---|---|---|
| `haiku` | `claude-haiku-4-5` | catalogued as the fastest, near-frontier |
| `flash` | `gemini-3.7-flash` | paid sibling of the family already answering in 2.2 s |
| `gpt-mini` | `gpt-5.6-terra` | between the ceiling and `gpt-fast`, unmeasured |
| `grok` | `grok-4.6` | catalogued as fastest and most intelligent |
| `deepseek-flash` | `deepseek-v4-flash` | the fast, high-volume sibling |

## The decisive constraint on how to run this

**A paid arm does not spend the free pool's daily quota.** The rule that governs
every other experiment here — one change per tier, the quota does not fit two —
does not apply. What a paid arm spends is money, and the operator's approval for
that spend is the only gate.

## The first arm

`gpt-fast`'s latency is reasoning, not throughput: the answer is *shorter* than the
pool's, and seven of ten seconds pass before the first character. Every paid
measurement taken so far is therefore of one model's **default** effort, because
the request carries the model, the messages, the tools and the streaming options
and nothing else.

Measuring `gpt-fast` at a low effort is the cheapest route to "fast and obeys" —
that model's quality is already measured and accepted, so the only open variable is
whether the thinking phase can be shortened without losing it. It is the first arm
of step 1, not a side experiment, and the only one whose outcome could end the plan
early in the good direction.

It is runnable: llmbroker's direct client takes per-request parameters for a model
reached by name, and its curated catalog is readable programmatically, so the arm
list comes from the catalog rather than from this page.

## Step 1 — screen on latency alone

Latency is a property a handful of calls establishes; quality is not. So screen
first and spend nothing on quality until the candidate can be fast.

- One arm per alias above, plus `gpt-fast` as the incumbent to anchor the numbers.
- ~20 unit fixtures per arm, drawn from the registered set so the prompt is the
  production one. About 120 calls in total.
- Record: median and p90 whole answer, median time to first character, and any
  refusal or empty answer.
- **The bar, fixed before the run:** median whole answer ≤ 4 s *and* median first
  character ≤ 1.5 s. That is the band where the change does not read as a
  regression to a reader used to 2.2 s. An arm that misses it is out, whatever it
  scores on quality.
- **Re-take the pool's own numbers in the same run.** The 2.2 s baseline was
  measured before a silent pool member was found able to hold a caller's whole
  budget and send every request to the paid step; llmbroker's queue changes what
  the pool does when that happens. A candidate compared against a stale baseline
  is compared against nothing.

## Step 2 — a quality tier on the survivors only

For each arm that cleared the bar, a full tier over the registered fixtures, with
the same metrics the pool and `gpt-fast` were read on, so the three are comparable:
contract validity, formatting, verdict correctness, target-language card sentences,
and the payload-repair rate.

Then the mandatory reading: a **fresh** agent, one that did not run the bench,
reads every item of the review packet. A green screen is conformance, not quality.

## Step 3 — the configuration that follows

- A survivor that matches `gpt-fast` on the defect classes and clears the latency
  bar becomes the preferred model, **with the pool kept as the fallback**. No
  metered API is ever required to run the app — that is a standing cost
  requirement, not a preference — so this is a preference order, never a hard
  dependency.
- Whatever wins, re-read which repairs it makes dead weight. The letter test goes
  only if its measured rate on the new tier is zero over a full tier, and only for
  as long as that tier is the one answering; it stays in the code as long as the
  pool can answer at all.
- If nothing clears the bar, the choice is between `gpt-fast` at ten seconds and
  the pool at two, and it is a product judgement about waiting rather than a
  measurement. Put the numbers to the operator and let them choose.

## What this plan must not do

- **Do not fold the tier question into a prompt change.** One change per
  measurement. A tier arm and a prompt revision in the same run measure neither.
- **Do not treat a fast model as a fix for the coinage class.** Paid judgement is
  worse there, measured; the vouching machinery survives whatever wins.
- **Do not remove a deterministic repair on the strength of a single arm.** The
  pool answers when the paid path is unavailable, and the repair has to hold then.
- **Do not spend on step 2 before step 1 has excluded the slow arms.**
- **Do not start any paid arm without the operator's approval for that spend**,
  and give them the estimate first: step 1 is on the order of a dollar, each step 2
  arm a few.
