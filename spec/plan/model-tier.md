# Implementation plan — is there a model that is fast *and* obeys

## Why this is open

Several deterministic repairs in the answer path exist because the tier the app
runs on does not follow the prompt reliably: the card-sentence letter test, the
JSON repair applied before parsing, the formatting sanitiser, the escalation of a
declared misspelling to the paid model. Each is measured and each is honest about
being a filter rather than a proof. None of them can be strengthened into one —
`spec/decision-llm-backend.md` records why, and re-deriving that is not this
plan's job.

The question this plan asks is the other one: **what would those repairs cost if
the model obeyed?** The paid arm already answers part of it. Over 179 fixtures
answered by both tiers under an identical prompt:

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

**The blocker is latency, not money.** The operator has stated that the cost of a
paid tier at this volume is not a constraint. Seven of `gpt-fast`'s ten seconds pass
before the first character arrives, and the app streams, so that is the number a
reader feels: 0.9 s of waiting becomes 7 s.

**And the survey that chose the tier was partial.** It measured `sonnet`, `gpt` and
`gpt-fast`. llmbroker's curated paid catalog carries nine aliases, and the ones
whose whole selling point is speed were never called even once:

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

## The side experiment worth running with it

`gpt-fast`'s latency is reasoning, not throughput: the answer is *shorter* than the
pool's, and seven of ten seconds pass before the first character. llmbroker sends
no reasoning-effort parameter at all, so every paid measurement so far is of a
model's default effort. llmbroker is ours to change.

Adding an effort setting and measuring `gpt-fast` at a low one is the cheapest
possible route to "fast and obeys", because that model's quality is already
measured and accepted. Run it as its own arm in step 1, not folded into another.

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
