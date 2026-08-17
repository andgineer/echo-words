# LLM backend per language — decision

Status: **decided 2026-08-17 — the free `llmbroker` pool is the default
for all three v0.1 languages, including Serbian; the paid direct client
ships as the opt-in quality tier it was designed to be, and web
grounding is dropped from v0.1.** This document records the M0 spike
behind those defaults. It is an input to M2.

## What was measured

- 40–41 items per source language (English, German, Serbian), covering
  the shapes the prompt must survive: common words, rare words, idioms
  and phrasal/separable verbs, borrowed words with a real etymology,
  misspellings that must not be silently corrected, and homonyms with
  unrelated meanings. The Serbian set mixes Cyrillic and Latin.
- The production prompt, taken verbatim from the implementation plan,
  with the language slots filled per item; answers in Russian. Backends
  were compared, never prompts.
- Two load profiles, because they give opposite answers: a **burst**
  (four requests in flight, 120 answers in seven minutes) and a
  **paced** single-user session (one request at a time, five seconds
  apart). The paced profile is the real one — this is a personal tool
  with a couple of dozen words a day.
- The paid tier was surveyed through llmbroker's own direct client —
  the same path the `api` backend uses — on `sonnet` and `gpt`, 15
  items per language.
- Scoring: objective contract checks on every answer (card payload
  parses and validates, HTML discipline, the word echoed unchanged, a
  correction offered for a misspelling, IPA present, answer actually in
  the target language, latencies), plus an LLM judge as a pre-filter on
  12 items per group — translation and register, IPA, etymology,
  examples, morphology, 1–5. The judge is a filter, not a verdict.
- Not measured: `grok` and `deepseek` (no keys), and the pool's
  `glm-4.7-flash` (no key). The four remaining pool models answered.

## Hypothesis 1 — sufficiency varies by source language: confirmed, mildly

Under the paced profile the pool's primary model answered **every**
request in all three languages with a clean contract: 20/20 valid card
payloads, clean HTML, the input word echoed unchanged, a correction
offered for every misspelling, IPA present, answer in Russian.

The gap is not in the contract but in the content, and only in two
places: Serbian and German **morphology** (judge 3.6 and 3.5, against
4.8 and 4.9 for the strongest paid model) and Serbian **IPA** (3.4;
Serbian tone marks are hard for every model tested — the best paid
score was 4.2 and one paid model scored 2.8, worse than the pool).
Translation, register and etymology sit between 3.7 and 4.3 for the
pool in all three languages.

Morphology is the gap that matters, because gender, plural and verbal
aspect go into the deck and get memorized. It is a prompt-side gap as
much as a model-side one: the per-language morphology hint exists
precisely for this, and improving that line is cheaper and safer than
moving a language onto a metered backend.

## Hypothesis 2 — speed: the pool wins outright, one paid model fails the NFR

Paced, single user, per language: **first delta 0.8 s, whole answer
1.8–1.9 s, p90 2.6 s** — an order of magnitude inside both budgets
(first content ~3–5 s, complete answer ~20–30 s).

The paid tier is far slower, and one option misses a budget:

- `sonnet` — first delta 2.2–3.4 s, whole answer ~11 s. Inside both
  budgets.
- `gpt` — first delta 12–20 s, whole answer 19–27 s, p90 up to 48 s on
  Serbian. **Misses the first-content budget on every call** and its
  tail misses the complete-answer budget.

Under the burst profile the pool's p90 degraded to 40–49 s and three
requests out of 120 got no answer at all. That is an artefact of the
harness, not of the product: it is what happens when one client sends
four concurrent requests at free-tier rate limits. It matters only as
the description of the tail — see the fallback finding below.

## Hypothesis 3 — web grounding: dropped from v0.1

Never tested, and deliberately: the plan makes it conditional on a
hard-language gap that grounding would be the cheapest way to close.
No such gap was found. The pool's Serbian weaknesses are morphology and
tone-mark transcription — knowledge a search tool does not supply — and
the paid path already covers "who wants top quality" at one config
line. llmbroker ships no web-search tool, so grounding would mean
bringing a search API, its key and its metering into a project whose
cost requirement is that no metered API is ever required.

The grounding switch is therefore not part of v0.1.

## The finding that shapes the tail: fallback order ignores latency

llmbroker picks, among the models available at that instant, by
curated weight displaced by the host's own quality ratings per
(model, operation label) — a strict order, not a lottery. So "the best
free model answers everything, and when it is cooling the request goes
down the list instead of failing" is already the behaviour, with no
work on echo-words' side beyond rating its calls.

What the curated order does not know is **latency**. Measured per
answering model:

| model | whole answer, median | contract |
|---|---|---|
| `gemini-3.5-flash-lite` | 1.6–1.7 s | ~100% in all three languages |
| `groq-gpt-oss-120b` | 2.8–3.5 s | clean on en/de; HTML discipline collapses on Serbian |
| `openrouter-nemotron-3-ultra` | 35–57 s (worst 101 s) | 79–83% cards on de/en; a sixth of German answers not in Russian |
| `openrouter-laguna-s-2.1` | 43 s | one sample |

The two slowest models carry the highest curated weights after the
primary, so the *first* fallback is the worst possible choice for an
interactive tool: when the primary cools down, the answer arrives 20–60
times slower and breaks the latency NFR. This is invisible at a couple
of dozen requests a day — the primary never cooled once in the paced
run — and it is the whole story under any burst.

Two consequences, both recorded here rather than acted on in v0.1:

- The only lever echo-words holds is rating its calls, which is
  per-language by construction and therefore also the production
  counterpart of hypothesis 1. It shifts *which* model is preferred; it
  cannot express "prefer a fast one when the good one is busy".
- The fix belongs in llmbroker: it already deprioritises (never
  excludes) a model that recently failed to answer within a comparable
  budget, and it already journals each call's full latency. Feeding
  observed latency into that same mechanism would order the fallback by
  speed for a caller that offers a small budget, while still answering
  slowly rather than not at all when nothing faster is free.

A related correction: a wait budget bounds queueing and the **first
delta** only. Once deltas flow, nothing stops a model from trickling
for a hundred seconds — which is exactly what the slow fallback did.
A whole-answer budget is the consumer's own responsibility.

## The paid tier: both options have a defect at the current prompt

- `sonnet` writes **markdown** — `**word**`, `*example*` — instead of
  the `<b>`/`<i>` the prompt demands, on 100% of answers in all three
  languages. Rendered in the app that is literal asterisks. It also
  offered a correction for only half the Serbian misspellings.
- `gpt` is contract-perfect everywhere — every card valid, HTML clean,
  every misspelling flagged — and the strongest on content in every
  language (4.2–5.0 across the rubric). It is the quality ceiling of
  this survey, and it is the one that misses the latency NFR.

Neither defect disqualifies the paid tier: it is opt-in, and the
formatting one is a prompt matter that M2 can revisit. But neither
option is good enough to *default* a language to, which is what the
plan had penciled in for Serbian.

## Decisions for v0.1

- **Fallback backend kind: the free `llmbroker` pool.** Unchanged from
  the plan's default; the spike confirms it rather than assuming it.
- **English: the pool.** No reservation.
- **German: the pool.** The morphology score is the weakest of the
  three languages' contract-clean results; the per-language morphology
  hint is the place to improve it.
- **Serbian: the pool**, not the paid client. The pool is
  contract-clean and fast on Serbian; the paid alternatives are a
  latency violation on one hand and a formatting violation on the
  other; and the real gap — morphology and tone-mark IPA — is not
  closed by either at an acceptable cost. Serbian keeps its morphology
  hint, and the paid tier stays one config line away for whoever wants
  it.
- **The paid direct client still ships**, with `gpt` as the alias to
  reach for when a language or a user wants top quality and can accept
  ~20 s answers. `sonnet` is not recommended until the prompt makes the
  HTML rule stick.
- **Web grounding is dropped** from v0.1 — no switch, no search
  dependency.

## What would re-open this

- The pool's primary model degrading or disappearing from the curated
  list: the measured fallbacks are not equivalent, and Serbian would
  then need re-testing against the paid tier.
- A prompt revision aimed at morphology: it changes the numbers this
  decision rests on, for the pool and the paid tier alike.
- Sustained use past a couple of dozen requests a day, which is where
  the fallback tail stops being theoretical.

The harness is `experiments/backend_bench.py`; it is outside CI, calls
real models, and its paid phase spends real money.
