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
  the same path the `api` backend uses — on `sonnet`, `gpt` and
  OpenAI's `gpt-5.6-luna`, 15 items per language. The last is not in
  llmbroker's curated catalog and had to be named by provider and model
  id, which is why the harness can do that.
- Scoring: objective contract checks on every answer (card payload
  parses and validates, HTML discipline, the word echoed unchanged, a
  correction offered for a misspelling, answer actually in the target
  language, latencies), plus an LLM judge as a pre-filter on 12 items
  per group — translation and register, etymology, examples,
  morphology, 1–5. The judge is a filter, not a verdict.
- **IPA is not a quality axis here.** Pronunciation reaches the learner
  as audio, so the transcription is welcome when it is right and
  decides nothing when it is not. Whether it is *present* is still
  checked, as one more signal that a model follows the prompt at all.
- Not measured: `grok` and `deepseek` — no keys. The pool's fifth model,
  `glm-4.7-flash`, has a working key but would not answer: its shared
  free tier hands back HTTP 429 ("the service may be temporarily
  overloaded") most of the time, and availability swings from roughly a
  third of attempts to none at all within the same hour — 26 consecutive
  refusals in one stretch, short prompts and real ones alike. Nothing to
  configure: that provider's free tier is simply oversubscribed. Four of
  the five pool models answered.

## Hypothesis 1 — sufficiency varies by source language: confirmed, mildly

Under the paced profile the pool's primary model answered **every**
request in all three languages with a clean contract: 20/20 valid card
payloads, clean HTML, the input word echoed unchanged, a correction
offered for every misspelling, IPA present, answer in Russian.

The gap is not in the contract but in the content, and on the rubric
that counts it comes down to a single axis: **morphology**. The pool
scores 3.5 on German and 3.6 on Serbian, against 4.7–4.9 for the paid
models. Translation, register, etymology and examples sit between 3.7
and 4.4 for the pool in all three languages — a step below the paid
tier, not a different league.

Morphology is the axis that matters most, because gender, plural and
verbal aspect go into the deck and get memorized wrong. It is also a
prompt-side gap as much as a model-side one: the per-language
morphology hint exists precisely for this, and improving that line is
cheaper and safer than moving a language onto a metered backend.

## Hypothesis 2 — speed: the pool wins outright, one paid model fails the NFR

Paced, single user, per language: **first delta 0.8 s, whole answer
1.8–1.9 s, p90 2.6 s** — an order of magnitude inside both budgets
(first content ~3–5 s, complete answer ~20–30 s).

The paid tier is far slower, and the models differ by a factor of
three among themselves:

- `sonnet` — first delta 2.2–3.4 s, whole answer ~11 s. Inside both
  budgets.
- `gpt-5.6-luna` — first delta 5.5–6.3 s, whole answer 8.6–9.7 s, p90
  under 14 s. Marginally over the first-content budget, comfortably
  inside the complete-answer one.
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
| `zai-glm-4.7-flash` | — | refused every attempt; its free tier is oversubscribed |

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

## The paid tier: `gpt-5.6-luna` is the one worth reaching for

- `sonnet` writes **markdown** — `**word**`, `*example*` — instead of
  the `<b>`/`<i>` the prompt demands, on 100% of answers in all three
  languages. Rendered in the app that is literal asterisks. It also
  offered a correction for only half the Serbian misspellings, and it
  is the weakest of the three on content.
- `gpt` is contract-perfect everywhere and the strongest on content
  (4.6–4.9 across the rubric in every language). It is the quality
  ceiling of this survey, and the one that misses the latency NFR.
- `gpt-5.6-luna` is contract-perfect too, scores 4.3–4.8 — within
  0.1–0.3 of the ceiling, and on Serbian morphology, the axis that
  decides anything here, it matches it (4.7 against 4.7) — and answers
  three times faster.

So the paid tier has one clear pick. Its catch is administrative:
`gpt-5.6-luna` is not in llmbroker's curated paid catalog, and the
design deliberately reaches paid models by curated alias, so that
llmbroker can re-point the alias at the next model generation on its
own. Reaching this model as a first-class option means adding it to
that catalog upstream.

## Decisions for v0.1

- **Fallback backend kind: the free `llmbroker` pool.** Unchanged from
  the plan's default; the spike confirms it rather than assuming it.
- **English: the pool.** No reservation.
- **German: the pool.** The morphology score is the weakest of the
  three languages' contract-clean results; the per-language morphology
  hint is the place to improve it.
- **Serbian: the pool**, not the paid client. The pool is
  contract-clean and answers in under two seconds; the one real gap is
  morphology, which the language's own prompt hint is the right and
  cheaper place to attack. The paid tier stays one config line away
  for whoever wants it.
- **The paid direct client still ships.** Preferred model:
  `gpt-5.6-luna` — contract-perfect, near the quality ceiling,
  three times faster than `gpt`; it needs a curated-catalog entry
  upstream before a language can name it by alias. Until then `gpt` is
  the catalog alias to use, with its latency understood. `sonnet` is
  not recommended while it answers in markdown.
- **Web grounding is dropped** from v0.1 — no switch, no search
  dependency.

## What would re-open this

- The pool's primary model degrading or disappearing from the curated
  list: the measured fallbacks are not equivalent, and Serbian would
  then need re-testing against the paid tier.
- A prompt revision aimed at morphology: it changes the numbers this
  decision rests on, for the pool and the paid tier alike. This is the
  first thing to try before any language moves to a metered backend.
- Sustained use past a couple of dozen requests a day, which is where
  the fallback tail stops being theoretical.

The harness is `experiments/backend_bench.py`; it is outside CI, calls
real models, and its paid phase spends real money.
