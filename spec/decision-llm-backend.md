# LLM backend per language — decision

Status: **decided 2026-08-17 — the free `llmbroker` pool is the default
for all three v0.1 languages, including Serbian; the paid direct client
ships as the opt-in quality tier it was designed to be, and web
grounding is dropped from v0.1.** This document records the benchmark
behind those defaults; its harness is `experiments/backend_bench.py`.

## What was measured

- 40–41 items per source language (English, German, Serbian), covering
  the shapes the prompt must survive: common words, rare words, idioms
  and phrasal/separable verbs, borrowed words with a real etymology,
  misspellings that must not be silently corrected, and homonyms with
  unrelated meanings. The Serbian set mixes Cyrillic and Latin.
- The production prompt verbatim, with the language slots filled per
  item; the target language Russian.
  Backends were compared against each other with the prompt held fixed.
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
- **IPA played no part in this decision.** Pronunciation reaches the
  learner as audio, so a transcription is not a quality axis anything
  here rests on.
- Not measured: `grok` and `deepseek` — no keys. The pool's fifth model,
  `glm-4.7-flash`, answers too rarely to score: its shared free tier
  returns HTTP 429 for most requests, and one answer in eight is what it
  gives even when it is the only candidate the pool has. Its quality is
  therefore unknown, and it does not matter — it is a reasoning model
  whose whole answer takes 34 s, outside the complete-answer budget
  whatever the answer turns out to be worth.

## Hypothesis 1 — sufficiency varies by source language: confirmed, mildly

Under the paced profile the pool's primary model answered **every**
request in all three languages with a clean contract: 20/20 valid card
payloads, clean HTML, the input word echoed unchanged, a correction
offered for every misspelling, and the answer in the target language.

**No model drifted out of the target language, in any language, at any
point.** Measuring that takes more care than it looks: a good German
answer is full of German — `Prät.`, `Part. II`, the collocations, the
examples — so a share-of-script test reads it as off-target. The check
drops the italicised example sentences first, which are in the source
language by contract, and only then decides.

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

Paced, single user, per language: **whole answer 1.8–1.9 s, p90 2.6 s**
— an order of magnitude inside the complete-answer budget (~20–30 s),
which is the only budget the product states. Time to the first token is
recorded here because the harness records it, and is not a criterion:
it says how quickly a model starts talking, not how long the user waits.

The paid tier is far slower, and the models differ by a factor of
three among themselves:

- `sonnet` — whole answer ~11 s. Inside the budget.
- `gpt-5.6-luna` — whole answer 8.6–9.7 s, p90 under 14 s. Comfortably
  inside it, and the fastest paid model measured.
- `gpt` — whole answer 19–27 s, p90 up to 48 s on Serbian. At the edge
  of the budget, and its tail misses it.

Under the burst profile the pool's p90 degrades to 20–29 s and ten
requests out of 120 get no answer at all. That is an artefact of the
harness, not of the product: it is what happens when one client sends
four concurrent requests at free-tier rate limits. It matters only as
the description of the tail — see the fallback finding below, and the
budget section after it.

## The prompt is in English, and the answer language is a slot

The target language must be free to be anything, so it cannot be baked into
the prose; and English is what models follow instructions in most reliably.
An English prompt carries one specific risk — the model mirroring the
language it was instructed in — so that risk is measured, not assumed.

With the model held fixed (the pool's primary), 40 items per source
language: **100% of answers on target, all three languages**, and the card
contract clean at 100 / 98 / 100% with formatting at 100% throughout. A
separate arm with an English source and a German target came back German in
12 of 12, so the slot drives the answer rather than the model inferring what
the reader wants.

**A prompt may name a forbidden form; it must never show one.** Spelling out
the forbidden markup by exhibiting it triples the rate at which a model
produces it — the example is reproduced and the negation does not cancel it.
This is why the formatting rule names what it forbids in words only, and why
the target-language demand is repeated three times without ever
demonstrating a wrong answer.

## Hypothesis 3 — web grounding: dropped from v0.1

Never tested, and deliberately: it was conditional on a hard-language
gap that grounding would be the cheapest way to close.
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
| `openrouter-nemotron-3-ultra` | 36–57 s (worst 101 s) | answered nothing at all on 3 German items of 14; 82% clean formatting |
| `openrouter-laguna-s-2.1` | 43 s | one sample |
| `zai-glm-4.7-flash` | 34 s, of which 31 s before the first token | a reasoning model on an oversubscribed free tier: 1 answer in 8 attempts |

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
- The fix belonged in llmbroker, and is there: a caller's `wait` bounds
  the **whole answer**, counted in provider time, so a model that
  outlives the budget ends the call however it chunked its output, and
  the pool deprioritises it for the next caller offering no more. That
  is one budget with one meaning, the same one a completion has.

What was tried and rejected on the way: ordering the pool by latency
read off the answers models gave. It measured time to the first token —
the one number a slow model looks good on — and bought, over the miss
bound already there, a single saved request per model per window. The
measurements behind the rejection are in llmbroker's own record of the
same workload.

## The budget's value: the low end of the range, and why it is not a detail

`wait` is the only knob echo-words sets on the pool, and where it sits
inside the functional description's ~20–30 s complete-answer budget
decides **what a miss looks like**, not merely how many misses there are.
Measured over the burst profile, 120 requests, three languages:

| budget | answered | the answers | what a miss is |
|---|---|---|---|
| 25 s | 64 of 120 | 100% valid card, clean HTML, word echoed and answer on target, in all three languages; slowest answer 20.3 s | 56 of 56 `NoLLMAvailableError` — the pool gave up before any model produced a delta |
| 45 s | 110 of 120 | 91–95% clean HTML; eight answers past 30 s | 8 of 10 `LLMTimeoutError` — the answer died with text already delivered |

The pool's slow entries spend 9–42 s before their first token, so a
budget at the low end cuts them before they start talking. That is the
difference between a step-up that begins from nothing and one that has
already shown the user half an answer it cannot finish — and past the
first delta there is nothing to fail over to. Every contract violation in
either run belongs to those same slow entries; the primary model is
clean on every axis in both.

So the budget goes at the **low end** of the range, and the paced profile
pays nothing for it: whole answers there are 1.3–2.5 s, an order of
magnitude inside it.

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

So the paid tier has one clear pick, and it is reachable the way the
design demands: llmbroker's curated paid catalog carries `gpt-5.6-luna`
under the alias `gpt-fast`. Paid models are named by curated alias and
never by model id, so that llmbroker can re-point the alias at the next
model generation on its own.

## Merged production-prompt recheck — 2026-08-27–28

The one-prompt unit/text contract invalidates the original prompt's contract
percentages, but not the selected backend kinds. Its append-only recheck uses
157 fixtures per arm: the 122-item verdict set, 26 known texts and nine bare
units. The Serbian slice has 57 fixtures, 44 of them undecided verdicts.

| arm | all provider answers | all parseable payloads | Serbian answers | Serbian parseable | Serbian usable verdicts | Serbian exact / hard errors | Serbian strict article format |
|---|---:|---:|---:|---:|---:|---:|---:|
| first merged arm | 148 / 157 | 144 / 157 | 55 / 57 | 54 / 57 | 41 / 44 | 37 / 41, 3 | 10 / 57 |
| stricter exploratory arm | 33 / 157 | 31 / 157 | 12 / 57 | 11 / 57 | 8 / 44 | 7 / 8, 1 | 2 / 57 |
| complete semantic arm | 157 / 157 | 147 / 157 | 57 / 57 | 52 / 57 | 40 / 44 | 32 / 40, 8 | 24 / 57 |
| conservative-context arm | 155 / 157 | 145 / 157 | 57 / 57 | 53 / 57 | 41 / 44 | 35 / 41, 5 | 21 / 57 |
| embedded-unit arm (v5) | 156 / 157 | 147 / 157 | 56 / 57 | 51 / 57 | 39 / 44 | 38 / 39, 0 | 23 / 57 |
| production prompt (v6) | 157 / 157 | 157 / 157 | 57 / 57 | 57 / 57 | 44 / 44 | 40 / 44, 3 | 19 / 57 |

The middle row is availability evidence, not a model-quality score: 124 calls
found no free slot. In the complete semantic arm,
`google-gemini-3.5-flash-lite` answered 152 fixtures and
`groq-gpt-oss-120b` answered five. The raw total verdict matrix was
`62 / 0 / 34 / 18` for unit→unit, unit→text, text→unit and text→text.
Tolerant interpretation left 80 correct, one acceptable boundary, three
ambiguous/defensible boundaries, 30 hard errors and eight unusable verdicts.
Those hard errors were over-broad unit verdicts for contextual fragments,
ordinary clauses and whole sentences, not Serbian morphology or an inability
to return the merged schema. Eight were Serbian.

The conservative-context arm improved the preceding over-broad result but still
failed its semantic gate: 14 hard verdict errors among 112 usable verdicts,
including nine German and five Serbian errors, while only 16 of 26 known texts
reached the text branch.

The embedded-unit arm (v5) passed every deterministic contract, produced 147 of
157 usable initial results and reduced hard verdict errors to four of 115. Its
Serbian slice had 56 provider answers, 51 usable results, 38 exact verdicts and
no hard verdict errors among 39 usable verdicts. The arm still failed downstream
quality: 20 of 26 known texts chose text and only 13 of 21 distinct registered
units were recovered; eight of nine bare units and all three expressions passed,
but clicks could not run and reported zero of six successes. Two text misses
were parse failures. Four semantic misses carded a finite situational clause
whole when a fixed expression occupied most of it.

The v6 prompt returned and parsed all 157 initial fixtures. All 122
verdict payloads were usable: 113 were correct, two were
ambiguous/defensible and seven were hard errors. The two gray-zone unit verdicts
were the reusable short formulas `Das stimmt` and `Не знам`; keeping them out of
the hard-error count does not excuse the seven clear losses of the requested
operation. The Serbian slice returned 57 of 57 usable results, with 40 exact and
three hard verdict errors among its 44 verdict fixtures. Nineteen of its 57
articles met the strict formatting diagnostic.

The same arm passed the automated contracts and aggregate quality gates
registered before its run: 25 of 26 known texts chose text, all nine bare units
were called cardable, production fill recovered 18 of 21 distinct registered
units, all three expressions succeeded, and five of six dependent clicks were
counted. Fresh qualitative review then found contextual over-highlighting in 24
of 82 accepted unit results, including four bare cases and one accepted click.
The v6 prompt is therefore **BLOCKED**; the quantitative figures are retained as
backend evidence, not prompt acceptance.

The subsequent v7 smoke removed that arm's accepted whole-context highlighting
failure and met the tolerant text, bare, registered-unit and click thresholds,
but failed all three typo cases because its headword instructions competed with
submitted-spelling retention. That prompt is blocked.

The prompt-bound fresh review of v8 also **BLOCKED** promotion. All 30 canonical
answers parsed, 20 of 21 known texts chose text, all nine bare results were
structurally cardable, all six clicks and all three expressions passed, and the
v6 whole-context failure did not recur. Exact typo correction was only two of
three: `typo-sr-mozda` silently changed submitted `мозда` to visible and payload
`можда` with an empty suggestion. The tolerated typo threshold cannot override
that accepted semantic correction failure.

Strict registered-unit recovery was 16 of 21, below the 18-unit threshold. The
five exact misses were: `text-de-1`, which omitted fixed reflexive `mich` from
`sich freuen auf`; `text-de-4`, which omitted support verb `habe` from `die Nase
voll haben`; `text-de-6`, which returned the whole sentence as a unit instead
of recovering `in Frage kommen`; `text-sr-3`, which omitted `се` and absorbed
negation into `изненадити се`; and `text-sr-4`, which omitted the variable
experiencer construction while absorbing destination `на посао`. Previously
approved variable-experiencer alternatives remain gray rather than being
converted into fixture-string rules. Separately, `bare-de-rad` highlighted
`Rad zu` in an example containing `Rad zu fahren`, leaving the exact submitted
token `fahren` unmarked; semantic review therefore tolerated only eight of nine
bare units.

The production contract asks for a same/morphology/typo relation and reconciles
it with the submitted and returned spellings, derives each blanked example form
from its highlighted one, folds the two Serbian scripts onto one spelling when
locating a surface in the submitted text, and rejects the narrow provable
generated-example token omission. Moving those obligations out of the prompt and
into the parser is what lets the prompt stay short enough for the free pool to
follow it. The relation field cannot itself prove spelling semantics because a
model can misclassify a typo as morphology; registered typo fixtures plus fresh
semantic review remain the promotion gate, while an absolute distinction would
need an independent judge. This does not change the selected backend: the
remaining failures are prompt-bound quality evidence, and undecodable JSON is a
generation weakness of the whole free pool rather than a reason to route Serbian
differently.

## Undecodable JSON is escaping, not Cyrillic — 2026-08-28

Across the 1377 recorded answers that carried a payload, 25 failed to decode:
15 of 513 Serbian (2.9%), 7 of 570 German (1.2%) and 3 of 294 English (1.0%).

The distinguishing cause is not the source script but `\uXXXX` escaping, which
the model applies to the target language instead of writing plain UTF-8. Each
escape is four consecutive low-probability hexadecimal tokens, and the model
derails inside one of them — a Serbian answer produced Japanese katakana in the
middle of a sequence, a German one Hungarian text, and that German answer broke
inside a *Russian* field rather than in its German source. Serbian breaks most
often because both its source text and its target text are non-ASCII, so the
surface exposed to escaping is twice as large.

Four failures break inside such a sequence. The rest are punctuation discipline
lost on a long generation: a string value left unquoted (10), a full stop typed
where a comma separates two items (6), a truncated string (4) and a backslash
escaping nothing (1).

The parser repairs the three punctuation classes, and a repair stands only when
it yields valid JSON; the repaired value then faces every ordinary check.
Measured against these recorded failures it recovers 10 of the 25 — fewer than
the three classes number, because a long answer often breaks more than once. A
truncated answer and a derailed escape carry no recoverable intent and take the
ordinary fallback.

Provider-side structured output would remove the class rather than 60% of it,
because grammar-constrained decoding cannot emit an invalid payload at all. It
is not adopted for v0.1, and the obstacle is the answer's shape before it is the
broker's. One generation carries the article, a separator and the payload, so it
is not a single JSON document: constraining it means either a second call, which
doubles consumption of the scarce free pool, or carrying the article as a field
inside the payload, which keeps streaming only if the article is parsed out of
the growing JSON incrementally.

The broker is the second obstacle. Its chat request carries no such parameter,
and threading one through is small; what is missing is per-model capability
data. The pool is heterogeneous — five models from four providers answered
during the measurement — and support differs between them, so sending the
parameter blindly would trade parse failures for provider rejections and skewed
routing. All three pieces are needed together; none helps alone.

Its value is also smaller than the parse numbers suggest, because the other
classes it would remove are already absorbed at no cost. The parser normalized a
singular translation key 50 times across 1609 decoded payloads with no visible
effect, and a click answer returning component parts it was told to omit — half
of them do — changes nothing either, since an explicit unit request builds its
chips from the senses and never reads those parts. What grammar cannot constrain
is the only class that reaches the learner: a wrong gender, a missing plural, an
invented usage, a translation of the wrong word. Constrained decoding is also
known to cost content quality on small models, so the trade would be paid in
exactly the quality that matters.

What would re-open this: a residual failure rate materially above the measured
one, a pool narrow enough that its capabilities are known, or a schema violation
that reaches the reader instead of being absorbed.

These results leave the backend decision unchanged. The historical failures
show a prompt-bound branching problem and the already measured free-pool
availability tail, not a reason to make the paid backend mandatory or to route
Serbian differently. Availability misses remain separate from content quality.
The production harness promotes a prompt through sequential smoke and
confirmation screens before the full pre-commit run. Full keeps all 157
canonical current-hash IDs and adds six clicks and six typo cases; it need not
make all 157 canonical cases usable, and retains the 142-result floor. `--resume`
improves availability and parse misses without replacing a usable semantic
disagreement with a lucky retry. Every screen emits a structured error packet,
and fresh-agent semantic review recorded in the prompt-bound decision spec is
mandatory before acceptance.

Semantic quality is aggregate: obvious hard verdict errors may be at most 10%
of usable verdict results, while acceptable and ambiguous/defensible boundaries
are not errors. Known-text, bare-unit, registered-unit, click and expression
flows use the documented 23/26, 8/9, 15/21, 5/6 and 2/3 thresholds; the
registered-unit floor sits at the bottom of its measured spread rather than
inside it, because repeated runs of one prompt answered by the same providers
have counted 15 through 18 of 21 and any floor above that bottom reddens on the
draw. The count and its spread stay in the report, where a human weighs them
before promoting a prompt. The Serbian
availability, usable-result, verdict-error and formatting slice remains visible
but has no separate zero-error requirement. Deterministic bounds, sanitization,
branch isolation, exact context-click surface, targeted sentence
transformations, the corrected spelling on a typo card, source-token fill and
four-card readiness remain zero-tolerance contracts for accepted payloads. Exact tier
manifests, pacing and promotion procedure are recorded in
`decision-phrases-and-sentences.md`.

## Decisions for v0.1

- **Fallback backend kind: the free `llmbroker` pool.** The spike
  confirms it rather than assuming it.
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
  `gpt-5.6-luna` — contract-perfect, near the quality ceiling, three
  times faster than `gpt` — named by the catalog alias `gpt-fast`. `gpt`
  remains the alias for the quality ceiling, with its latency
  understood. `sonnet` is not recommended while it answers in markdown.
- **Web grounding is dropped** from v0.1 — no switch, no search
  dependency.

## What money buys, measured on cards rather than on a rubric

The survey above scored a rubric. The question a learner cares about is how many
of the notes that reach their deck teach something false, and that is a different
measurement: the same production fixtures, the same prompts, once through the free
pool and once through `gpt-fast`, both read by the same fresh reviewer. Each tier
shipped exactly 42 notes.

**Cards carrying something the learner would memorise wrong: 6 of 42 free, 4 of 42
paid.** Neither tier is near "never"; both are around one card in ten.

What the paid tier removes outright, over these fixtures:

| defect | free | paid |
|---|---:|---:|
| example sentences in the target language with the unit dropped in | 11 | 0 |
| corrupted or mixed-script table cells | 10 | 0 |
| corrupted Serbian words inside articles | 8 | 0 |
| part of speech named in prose | 10 | 0 |
| invented etymology stated as fact | 2 | 0 |
| cards headed by a word other than the one analysed | 3 | 0 |
| misspellings named and corrected | 4/6 | 6/6 |
| Serbian cards carrying a defect | 3 of 10 | 1 of 13 |

Serbian is where the difference is largest, and Serbian is the language this
decision left on the pool because its one gap was morphology. That gap is what
the paid tier closes: `Седимо на клупу` becomes `Седи на клупи у парку`, and the
mixed-script and corrupted-token classes disappear entirely.

**What money does not buy is the class that matters most, and there it is worse.**
Well-formed nonsense carded with a confident sense reaches the reader twice of six
on the pool and three times of six on `gpt-fast`. The paid judgement is the reason:
asked about the invented `змркалица` it answered used, and invented a dialect and a
mealtime to justify it — contradicting, in the same run, its own article's story
about twilight. Invented provenance in the judgement's `where` field runs two of six
on the pool against four of six paid.

The configuration that follows is a mixed one: **the paid model writes the article
and the pool judges**. Scored over the recorded answers, it withholds four coinages
of six — the pool judge's rate — with the paid tier's article quality, and loses
none of the ten real words.

**A second judge is not the fix, and this was measured rather than assumed.**
Requiring both the pool and the paid model to vouch withholds the same four of six
and loses no real word — no better than the pool alone, because the two models
share the blind spot exactly: both vouch for `bookshelfy` and both for `tablewards`.
English productive derivation reads as a word to both of them, so model agreement
cannot separate it from a word.

**The article knows more than the card carries.** Asked about `blorptium`, the paid
article says it is probably a fictional form and that deriving an etymology for it
would be a guess. A note carries the headword, the translations and the two sentence
forms, so the hedge never reaches the deck: the card's confidence does not depend on
the article's. Where an answer will not commit, the product has no way to card that.

None of this moves the conclusion below, which is about latency as much as quality:
the paid article costs 10.6 s at the median against the pool's 2.5, with a 19 s tail.

**And the latency is reasoning, not throughput.** Seven of those ten seconds pass
before the first character arrives — 7.2 s to first token against the pool's 1.05 —
while the answer itself is *shorter* than the pool's, 1265 characters against 1396.
Asked a one-line question the same model answers in 1.6 s against 0.88, so the paid
path carries no large fixed overhead; the cost appears where a long answer follows a
thinking phase. That is a property of reasoning models rather than of paying for one:
the pool's own `glm-4.7-flash` is a reasoning model and takes 34 s. The request that
buys this is a bare one — llmbroker's direct client sends `model`, `messages` and the
streaming options and no reasoning budget — so the measurement is of the model's
default effort, and llmbroker is ours to change if a lower one is worth testing.
`haiku` and the paid `gemini-3.7-flash` are neither reasoning-first nor measured. A full tier of 218 calls spent roughly 325K input and 102K output tokens,
about a third of a month at a couple of dozen submissions a day.

## What would re-open this

- The pool's primary model degrading or disappearing from the curated
  list: the measured fallbacks are not equivalent, and Serbian would
  then need re-testing against the paid tier.
- A prompt revision aimed at morphology: it changes the numbers this
  decision rests on, for the pool and the paid tier alike. This is the
  first thing to try before any language moves to a metered backend.
- Sustained use past a couple of dozen requests a day, which is where
  the fallback tail stops being theoretical.
- An attestation source that covers all three languages. It is the only
  lever measured to reach the class neither tier reaches, and until one
  exists the choice between the tiers is a choice between kinds of
  defect rather than between fit and unfit for use.

The harness is `experiments/backend_bench.py`; it is outside CI, calls
real models, and its paid phase spends real money.
