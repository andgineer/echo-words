# Implementation plan — a paid tier chosen by the job, not by the case

**Nothing here is started, and nothing is to be run until the operator approves the
spend.** The design below is settled; the measurements it depends on are not taken.

## Why this is open

Most of what is left unfixed in `observed-defects.md` is the model's own work:
invented origins, a wrong grammatical form on a card front, a false friend carded as
a translation, a note built on the wrong language's word. Eleven of its eighteen
items are that class, and no deterministic guard can see any of them — the backend
tests a sentence's alphabet, never its grammar. The levers on that class are two: the
prompt, and which model answers. This plan is the second one.

`decision-llm-backend.md` measured what money buys on cards rather than on a rubric,
and it buys a great deal. Over the same fixtures the paid tier carried **none** of the
target-language example sentences, none of the corrupted or mixed-script table cells,
none of the corrupted Serbian words, none of the parts of speech named in prose, none
of the invented etymologies stated as fact and none of the cards headed by a word
other than the one analysed — where the free pool carried 11, 10, 8, 10, 2 and 3 of
them. Cards teaching something false went 6 of 42 free to 4 of 42 paid.

**And that was measured on the cheapest paid model there is.** `gpt-fast` is
`gpt-5.6-luna`, which llmbroker's catalog labels "optimized for cost-sensitive
workloads". The aliases whose whole selling point is being fast *and* strong have
never been called even once. What a good one would do is unmeasured in both
directions, and that is the gap this plan exists to close.

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

Two things that table settles. The JSON repair layer is identical on both tiers, so no
tier retires it. And **the constraint is latency, not money**: seven of `gpt-fast`'s
ten seconds pass before the first character, and the app streams, so 0.9 s of waiting
becomes 7 s. That is why a tier this good is not simply switched on, and why an arm is
screened on latency before it is read on quality.

What the reader waits for is no longer the model in any case: the dead step at the head
of the audio chain spent up to its whole ten-second budget inside a job the pool
answered in 2.2 s, and it is gone. This is not a rescue from a slow app; it is a bid to
improve the answers of one that is fast enough.

---

## The design: the tier is chosen by the job

A request's kind is known before the call, so nothing here predicts anything. Three
jobs, three answers.

### The judgement stays in the pool — already true, and it stays that way

The call that asks whether a word is really used is `pool_only` today, and the reason
is measured: paid judgement is the one class where money buys a worse answer.
`Löffelangst`, a word that does not exist, was vouched for by the paid model and
carded with an invented etymology about rabies. Nothing in this plan moves that call.
Whatever wins below, the vouching machinery and its tier survive unchanged.

This also decides the shape of item 2 in `observed-defects.md`, one reader action
making two concurrent pool calls: moving the *article* to a paid tier leaves one pool
call per submission. That is a consequence, not a reason, and it holds only where the
paid tier is switched on.

### The card's article gets a tier setting, defaulting to the pool

- **Default: the pool.** That no metered API is ever required to run the app is a
  standing cost requirement, not a preference. A fresh install keeps working with no
  key.
- **A paid model may be named instead**, and then the pool is the fallback for a paid
  step that refuses or a daily cap that is spent — never the other way round.
- **The setting belongs on the language row**, beside the recordings prefix and the
  voice, because what is known about answers is already per language: the directory
  carries a measured verdict for each row, and the defects cluster in the rows it
  calls unreliable. "Everything paid" is then every row set that way, which is the
  operator's own scenario and needs no separate mode.
- Nothing about the prompt changes. One change per measurement.

### "The full entry" gets its own setting, and it is not the card's

The deeper article and the card have opposite constraints. The card lives inside a
deadline the reader did not choose; the deeper article is asked for deliberately by a
reader who knows it costs a wait. One setting for both would let the card's latency
bar decide what answers the deeper article, which is the wrong trade in both
directions.

So the deeper article and the rebuild keep their own model setting, screened on
quality alone with no latency bar, and the card's tier is a separate choice.

The deeper article's own open defect — the length nobody chose — is measured in the
same run, because length is a property of the model *and* the instruction, and reading
them apart would cost a second tier for nothing. That is the one exception here to one
change per measurement, and it is an exception because the two are inseparable.

### What is deliberately not built

- **A heuristic that calls a word hard before the answer exists.** That is the
  classification problem `decision-answer-shape.md` measured and rejected: surface
  punctuation and length cannot solve it. This plan does not re-derive it.
- **A step up to the paid tier because the payload looked wrong.** Production says
  fourteen of fifteen rejected payloads carried an answer the reader would have
  accepted, so the parse verdict has a precision near 1 in 15 as a trigger. The app
  offers the paid answer as a button instead, and that stands.
- **A per-word cost cap.** The daily cap already bounds the day, and it is the guard
  that matters.

---

## What to measure, when the operator asks for it

### Step 1 — screen on latency alone

Latency is a property a handful of calls establishes; quality is not. Screen first and
spend nothing on quality until a candidate can be fast.

| alias | model | why it is a candidate |
|---|---|---|
| `haiku` | `claude-haiku-4-5` | catalogued as the fastest, near-frontier |
| `flash` | `gemini-3.7-flash` | paid sibling of the family already answering in 2.2 s |
| `gpt-mini` | `gpt-5.6-terra` | between the ceiling and `gpt-fast`, unmeasured |
| `grok` | `grok-4.6` | catalogued as fastest and most intelligent |
| `deepseek-flash` | `deepseek-v4-flash` | the fast, high-volume sibling |

The list is what the catalog carried when this was written; the run takes its own from
the catalog, which is readable programmatically.

- One arm per alias, plus `gpt-fast` as the incumbent to anchor the numbers.
- **Each arm twice: at the model's default effort and at its lowest.** `gpt-fast`'s
  ten seconds are reasoning, not throughput — its answer is *shorter* than the pool's
  — so the thinking phase is the variable. llmbroker's direct client now takes a
  request parameter for a model reached by name, which is what this arm needed.
- ~20 unit fixtures per arm, drawn from the registered set so the prompt is the
  production one. On the order of 240 calls.
- Record: median and p90 whole answer, median time to first character, and any refusal
  or empty answer.
- **The bar, fixed before the run:** median whole answer ≤ 4 s *and* median first
  character ≤ 1.5 s. That is the band where the change does not read as a regression to
  a reader used to 2.2 s. An arm that misses it is out of the card race whatever it
  scores on quality — and may still be a candidate for the deeper article, which has no
  such bar.
- **Re-take the pool's own numbers in the same run.** The 2.2 s baseline predates
  llmbroker's queued routing fix, and a candidate compared against a stale baseline is
  compared against nothing.

### Step 2 — a quality tier on the survivors only

For each arm that cleared the bar, a full tier over the registered fixtures, with the
metrics the pool and `gpt-fast` were read on, so the three are comparable: contract
validity, formatting, verdict correctness, target-language card sentences and the
payload-repair rate. Read the card-level classes of `decision-llm-backend.md` as well
— they are what the reader meets.

Then the mandatory reading: a **fresh** agent, one that did not run the bench, reads
every item of the review packet. A green screen is conformance, not quality.

### Step 3 — the configuration that follows

- A survivor that matches `gpt-fast` on the defect classes and clears the latency bar
  becomes the model a language row may name, with the pool kept as the fallback.
- The deeper article takes the best quality survivor, bar or no bar, together with
  whatever bound the same run showed its length needs.
- Whatever wins, re-read which deterministic repairs it makes dead weight. A repair
  goes only if its measured rate on the new tier is zero over a full tier, and only for
  as long as that tier answers; it stays while the pool can answer at all.
- If nothing clears the bar, the choice is between ten seconds and two, and it is a
  product judgement about waiting rather than a measurement. Put the numbers to the
  operator.

### What it costs

A paid arm does not spend the free pool's daily quota, so the rule that governs every
other experiment here — one change per tier, the quota does not fit two — does not
apply. What it spends is money: step 1 is on the order of a dollar, each step 2 arm a
few. In service, at the volume one reader produces — some twenty words a day, on the
order of two million tokens a month — a model of this class costs single-digit dollars
a month.

**No arm starts without the operator's approval for that spend, and the estimate goes
to them first.**

## What this plan must not do

- **Do not fold the tier question into a prompt change.** A tier arm and a prompt
  revision in the same run measure neither.
- **Do not treat a fast model as a fix for the coinage class.** Paid judgement is worse
  there, measured.
- **Do not remove a deterministic repair on the strength of a single arm.** The pool
  answers when the paid path is unavailable, and the repair has to hold then.
- **Do not spend on step 2 before step 1 has excluded the slow arms.**
