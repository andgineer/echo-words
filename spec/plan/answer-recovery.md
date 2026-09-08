# Implementation plan — recovering from an answer the parser cannot read

**Status: designed, agreed with the operator, nothing implemented except the two
logging commits below.** The design was settled in review on 2026-09-08 after a
production failure was traced end to end; the parts that touch the prompt or the
parser are unmeasured and gated on a bench run the operator has yet to schedule.

The subject is one path: what happens between "the pool answered" and "the reader
has a card". Today a payload the parser cannot read costs the reader the page
they were already reading, twenty-five seconds of blank screen, and a paid call —
and production says that payload is almost always an answer they would have
accepted.

---

## What prompted it

`allein`, submitted with a context sentence on 2026-09-08. Times are UTC, from
the service log and llmbroker's own journal.

| time | event |
|---|---|
| 05:07:58 | `POST /api/words` |
| 05:07:58.59 | attestation answered (groq-gpt-oss-120b, 0.5 s, rated 1.0) |
| 05:08:00.08 | pool answer complete in **2.007 s** — google-gemini-3.5-flash-lite won the `fastest_of=2` race, groq-gpt-oss-120b settled `superseded` at the same instant |
| 05:08:00.08 | payload rejected (`selected context example must equal the supplied context`), pool call rated 0.0, step-up begins, **the page is cleared** |
| ~05:08:25 | the paid step ends without ever having written a token; the entry fails |
| 05:08:30 | the reader submits the same word again |
| 05:08:32.70 | pool answer complete in 1.878 s, rejected (`answer.meanings contains no usable meaning`), rated 0.0, step-up, page cleared |
| 05:08:51 | `gpt-5.6-luna` answers after **18.4 s** — its payload is rejected by the same context rule, so the article is displayed and **no card is made** |

Three answers, three rejections, one paid call, no note in the deck. The reader
believes the second attempt worked, because the article is on the screen.

Two facts about the first attempt could not be established from the log at all:
whether the paid step timed out or failed, and whether it wrote anything. That
gap is what the logging commits close.

---

## Already built

- `b79a2380` — a `BackendError` is logged with the step, the model, the elapsed
  time and the trace id that names the row in llmbroker's journal; the paid step
  logs its first-token and total time from a `finally`, so a step cut off by a
  resubmission is told apart from one that timed out silent; the step-up logs the
  reason it happened.
- `034bfd31` — the rejected-payload warning carries the context the answer was
  judged against. Without the sentence, a copy that missed it by one word is
  indistinguishable from an invented one, and that distinction decides part B
  below.

Nothing else has been written. `ANSWER_BUDGET_SECONDS` is untouched: on the one
occasion it may have fired there is no evidence it was the wrong number, and the
new log answers that on the next occurrence.

---

## Evidence

### Every payload production has rejected

Fifteen rejections between 2026-08-21 (first boot of the current service) and
2026-09-08, read out of the service log with their payloads. The verdict column
is a reading of the payload itself, not of the rule that rejected it.

| date | word | rule | what the answer actually contained |
|---|---|---|---|
| 08-29 | `Treppe` | context | `Wir nehmen der <b>Treppe</b>.` — the copy mangles one article; senses and translations are right |
| 08-29 | `envi` (en) | context | the typo is declared correctly (`envi`→`envy`), examples are sound |
| 09-02 | `fahrt` ×2 | context | both answers copy `Ihr fahrt bis zum Grafenplatz.`, and **both re-parse cleanly** against that sentence |
| 09-02 | `geradeaus` | no usable meaning | every example bolds the whole sentence (`<b>Er fuhr geradeaus</b>`); the content is faultless |
| 09-02 | `geseft` | no usable meaning | same whole-sentence bolding; `Geschäft` is recognised correctly |
| 09-03 | `dann` ×2 | context | the first copies the sentence with a lowercased first letter; the second answers with different examples |
| 09-03 | `nehme` ×2 | context | the first copies `Dann nehme ich das Buch.` and **re-parses cleanly** against it |
| 09-04 | `der Verkehr` | no usable meaning | marks `Verkehr` where the submitted surface is `der Verkehr` |
| 09-07 | `genauso wie` | context | **re-parses cleanly** against the sentence its own example carries |
| 09-08 | `allein` | context | **re-parses cleanly** against a plausible sentence |
| 09-08 | `allein` | no usable meaning | **examples written in the target language** — the one answer of the fifteen a reader would reject |
| 09-08 | `allein` (luna) | context | ignores the context; the senses themselves are sound |

**Fourteen of fifteen** carried content a reader would have accepted. As a
trigger for buying a paid answer, the parse verdict has a precision near 1/15 —
and in the single case where the trigger was right, the paid answer was
unreadable too.

Method: each payload was replayed through `parse_answer_payload` with the
language row and target the app uses. "Re-parses cleanly" means the recorded
payload produced a `ParsedUnit` once the context sentence was supplied; the
sentence itself is reconstructed from the answers, because the log did not carry
it. That reconstruction is the reason `034bfd31` exists.

### How strict the context rule actually is

Measured by replaying one recorded payload against variants of its sentence:

| context offered | verdict |
|---|---|
| `Wir wohnten damals in der Wohnung immer allein.` | accepted |
| the same without the final full stop | accepted |
| the same with a lowercased first letter | rejected |
| the same with one doubled space | rejected |
| `der` → `dieser` | rejected |
| the same clause reordered | rejected |

So the tolerance is exactly one degree of freedom: final punctuation.
`decision-answer-shape.md` states this deliberately, and measured it: "Of 152
recorded contextual answers three failed strict equality: one dropped its full
stop, and two rewrote the sentence."

Production disagrees with that 2%: the same rule is the single most common
rejection there, ten of fifteen. The likely reason is the denominator, not the
rule — bench contexts are sentences the bench wrote, and a reader's context is a
sentence they selected, with its own capitalisation, its own fragment boundary
and its own punctuation. **The measurement that justified strict equality was
taken on bench-authored contexts, not on reader-supplied ones.**

### What llmbroker does with the losing lane

- In the streamed race that ships, `_retire` takes the other lanes off their
  providers "the instant a complete answer exists" — when the winner *finishes*,
  not at its first token. The journal shows it: both lanes of the 05:07:58 call
  settled at 2007 ms. The losing answer was generated almost in full and thrown
  away.
- `_settle_superseded` releases the slot and writes a neutral row: "nothing is
  cooled, counted, bounded or rated". The provider request, however, was already
  spent — cancelling saves only the tail of the output.
- A lane that fails for real is already refilled from a model the call has not
  tried (`_refill`), until the `wait` window is gone. A failed *attempt* therefore
  never reaches the host as an error while any model is left.
- When nothing is left, the pool says which kind of nothing:
  `NoLLMAvailableError.reason` is one of `excluded`, `empty_pool`, `no_keys`,
  `all_disabled`, `timeout`.

The gap is narrow and specific: an answer that *arrived* and that the host cannot
use is, to the router, a success. The race is closed and the other lanes are gone
before the host has parsed anything.

---

## The design

### A. Repair locally instead of rejecting wholesale

The parser is all-or-nothing where it holds every fact needed to fix the answer
itself. One misplaced `<b>` empties an example; an empty example list drops the
meaning (`_parse_meaning` returns `None`); no retained meaning fails the answer;
a failed answer costs a paid call. Three of the fifteen rejections are exactly
this chain, and the repair needs no model:

1. **Re-mark the highlight.** The submitted surface and the sentence are both
   ours. Where the plain sentence contains the submitted tokens, build the
   highlighted and gapped forms from our own marking and ignore the model's —
   this is already what happens for a matched context (`_context_sentence_forms`),
   and it should not be reserved for that case. Covers `geradeaus`, `geseft`,
   `der Verkehr`.
2. **Drop the piece, not the whole.** An unusable example drops that example; a
   meaning keeps its remaining examples; a meaning with none left drops itself;
   only an answer with no retained meaning fails. The first three steps exist;
   the failure cascade is what turns one bad example into a paid call.
3. **The chosen sense may not silently become sense 0.** `sense = remap.get(raw_sense, 0)`
   makes a dropped contextual sense look like a context mismatch, which is a
   second reason the context rule appears in the log more often than it fires.
   When the sense the answer chose is gone, that is what the log must say.

### B. The context copy is a key, not a claim

The card never carries the model's copy — `_parse_example` substitutes the
sentence the backend owns. The comparison exists to identify *which* example is
the contextual one, and to confirm the model analysed the sentence it was given
rather than one it invented. Those are two different jobs and only the second
justifies strictness.

The proposal is a graded tolerance: differences that cannot change meaning —
case, whitespace runs, quote and dash forms, terminal punctuation — are accepted
and the backend's own sentence is used; a changed, added or dropped word is still
a rewrite and still rejected, because a rewrite means the translation and the
`context_sense` belong to a sentence the reader never wrote.

**This part is blocked on evidence, and collecting it starts with a deploy.**
`034bfd31` logs the reader's sentence beside the rejected payload, so a fortnight
of ordinary use will say how many of these rejections are meaning-preserving
near-misses and how many are genuine rewrites — but only from the moment that
commit is running on the host, which as of writing it is not. Deploy it, wait,
then classify, and only then write the comparison or re-open
`decision-answer-shape.md`.

The end state worth considering if the residue is still large: stop asking for
the copy at all. `context_sense` plus a translation of the context sentence is
enough for the backend to build the example itself, and it asks the model for
less, not more.

### C. Two triggers, and never a blank page

Today every unusable answer takes the same road as a pool that never answered.
Split them:

- **The pool did not answer** — `NoLLMAvailableError` of any reason, or the wait
  budget gone. There is nothing on the screen and nothing to show. The paid step
  runs automatically, as it does today.
- **The pool answered and the payload cannot be repaired** — the article is
  worth reading, and the entry already knows how to say the card failed (that is
  what happens today when no paid model is configured). Keep the analysis on the
  page, mark the card failed, and offer the paid step as the reader's own
  decision.

In both cases the page is never cleared to make room for a step that has not
produced anything yet. The paid answer replaces what is on screen only when it
has arrived complete and parsed; if it fails, what was there stays. Nothing is
spliced — the rule the current clearing protects — because the replacement is
atomic.

Keep the answer, its chips and its carded-sense identity together during that
swap. A sense chip is hidden only after a note is successfully saved from that
same answer. A failed replacement which preserves an older note does not make
any sense of the new answer carded. Neither text comparison nor the mere
existence of an older note can choose which chip to hide.

### D. `another()`: the pool's next answer

In llmbroker, on the streamed handle:

```python
stream = broker.stream(prompt, fastest_of=3, ...)
async for delta in stream: ...      # the fastest answer
answer = await stream.another()     # the next one, or None
answer = await stream.another()     # and the next
```

- **No flag.** A lane another lane beat is not cancelled while the caller still
  holds the handle; closing the handle — which every caller already does through
  `aclosing` — is what ends everything. The only real cost of holding a lane is
  the pool slot it keeps, and it is held for exactly as long as the host takes to
  decide, which for this host is a synchronous parse.
- **Not "the runner-up".** `another()` walks the lanes this call already has in
  completion order, then models the call has not tried (`_untried`/`_refill`,
  which exist), then returns `None`. Any `fastest_of` works and no width is
  written into the API.
- **Termination is structural.** `_Call` accumulates `tried | client_failed`
  monotonically, `_untried` excludes them, and when nothing is left the pool
  itself raises `NoLLMAvailableError(reason="excluded")` — "every candidate model
  was excluded for this request". There is no counter to add and no loop to
  guard: the sequence is finite by construction and bounded above by the `wait`
  window.
- It returns a complete `AsyncResult`, not a stream: the answer is already
  written, and the cascade already knows how to put a whole answer on the page
  (`_replacement_deltas`).

In `echo_words/backend.py` this is one step between the pool and the paid model,
and in `llm_backend.py` `pool_error()` grows the distinction C needs:
`NoLLMAvailableError` of any reason means the pool is out and the paid step is
right; anything else is one attempt failing, which is `another()`'s business. In
practice that second branch rarely fires — the router holds a lane's failure
until `not race.live()` — so it is a guard, not a working path.

---

## What this changes in the specs

Each is part of the work, not a follow-up. Where a plan and the functional
description disagree, the description wins — so these sentences change in the
same commit as the code that contradicts them.

- `functional-description.md`: "When a whole answer already shown turns out
  unusable, its text is discarded and replaced by the paid model's" — C replaces
  the discard with an atomic swap.
- `functional-description.md`: an answer with no usable payload "moves the
  request the same way" as a pool that missed its budget — A, C and D make those
  two different roads.
- `functional-description.md`: "The step-up happens at most once per request" —
  still true of the *paid* step; the pool may now answer more than once.
- `decision-answer-shape.md`: the strict-equality rule and its 152-answer
  measurement. B re-opens it, and only a measurement closes it again — never an
  edit.

---

## Found on the way, and not part of this work

The paid step's budget does not mean what its name says. `stream_api` passes
`ANSWER_BUDGET_SECONDS` to `client.stream(prompt, timeout=…)`, llmbroker hands
that number to httpx as a bare float, and httpx spreads a bare float across
connect, read, write and pool separately. For a streaming response the one that
governs is `read` — the gap between two chunks. So the constant bounds *silence*,
not the answer: a model that trickles for two minutes is never cut off, and one
that thinks quietly for twenty-six seconds is, before it has written anything.

That is the opposite of what the functional description asks for. It calls the
number the "complete-answer budget of one model attempt" and says plainly that
time to the first token "is deliberately not a requirement", because bounding it
"would prefer a model that trickles for a minute over one that thinks briefly and
then answers at once". The implementation bounds exactly that.

It is written down rather than fixed because there is no evidence yet that the
number is wrong. The one occasion it may have fired — the paid step of the
05:07:58 call — left no record of whether it timed out or failed some other way;
`b79a2380` is what will say. Fixing the semantics means an overall deadline
around the stream plus a short connect timeout, and changing the semantics
without knowing which failure it caused would be tuning blind.

---

## Bench plan

One change per run, and the free pool's daily quota does not fit a tier twice.
A is the first run; B does not go to the bench until its production evidence has
been read.

Fixtures, each chosen because it instantiates one repair and nothing else:

| fixture | shape | what it instantiates |
|---|---|---|
| `der Verkehr` | unit, no context | a submitted surface of two tokens, where the model marked one |
| `geradeaus` | unit, no context | whole-sentence bolding |
| `dann` | unit with context, word first in the sentence | capitalisation pressure on the copy |
| `allein` | unit with context inside a collocation | a short adverb whose neighbours invite an expanded selection |
| an everyday noun with context | control | nothing should fire; a repair that changes this answer is a repair that is too eager |

Read availability before results: provider answers well below the run before it,
or the workhorse model missing from the tally, means an exhausted pool and a void
run. Resume with `--resume`, never restart.

Beware the confound: A changes what counts as a rejection, so it moves the
denominator of the step-up rate. Report the rejection count and the step-up count
separately, and compare each against the same tier before the change.

The run is finished only when a fresh agent has semantically reviewed every item
of `review-packet-*.json` and the decision is recorded in a `spec/decision-*.md`.

## Verification

- `uv run inv pre` — every hook green, `0 errors` from pyrefly.
- `uv run inv test` — the Python suite and the frontend suite, the latter passed
  rather than skipped.
- The browser suite is where C is pinned: what the reader is left looking at when
  a payload fails is behaviour that only exists in the browser, and the fake
  answers stop at a gate the test opens by hand, so the provisional page is
  asserted rather than raced.
