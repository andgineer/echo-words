# Phrases and sentences — decision

Status: **decided 2026-08-27 — one prompt analyses every submission; its
answer says whether the input is a lexical unit or text containing units. A
unit creates one note, while text creates no note and offers complete lookup
chips.** The production-flow harness is `experiments/one_note_bench.py`; the
verdict fixtures originate in `experiments/unit_verdict_bench.py`.

## Why the model decides inside the answer

Words do not always arrive one at a time. A multi-word string can be a unit
whose mapping is not word-for-word, an inflected occurrence of such a unit, a
fragment of a clause, or running text. The ambiguous cases share the same
surface shape: German `von Zeit zu Zeit` and `Ich habe keine Zeit` have the
same length and punctuation but require different outcomes. Serbian
`чувам се.` can likewise be either a lexical target or a clause. No threshold
over word count and punctuation can answer the linguistic question.

The old surface router therefore left the design with two prompts and still
made errors in the irreducible middle band. The merged contract asks for one
of two neutral branches in the same call that writes the article:

- `unit` returns the dictionary article, validated dictionary headword,
  target-language-distinct meanings, examples ready for four cards, and the
  component words of a set expression;
- `text` returns the text translated and explained plus conservative
  multi-word combinations. The backend maps their surface parts back to the
  submitted text and supplies every remaining source word itself.

A single submitted word is a unit by definition. Tapping any chip carries
explicit unit intent, so the same prompt must return the unit branch or the
answer is unusable and takes the ordinary fallback. An undecided multi-word
submit trusts the returned branch. There is no preliminary classification
call and no second prompt selected by punctuation or length.

## What text produces

Running text is translated and explained as a whole. It never creates an Anki
note: a clause on the front would be unreviewable, and a paraphrase would ask
the same question under a second front. Instead it offers a compact row of
lookup chips in source order.

The model names only multi-word lexical combinations worth learning. For each
usable proposal the backend identifies at least two unclaimed source-word
occurrences case-insensitively and without requiring contiguity or model order.
It prints the actual inflected source forms, not the proposed dictionary
label. The answer carries the unit twice — its dictionary form and the
forms the text spells — and only the second is ever printed. The first is not
redundant: it is what makes the second well defined. Asked for one form alone,
the model returns the lemma. Dropping the dictionary form cut recovered units
from 18 of 21 to 9 of 21 and clicks from six of six to four of six, because a
chip carrying a lemma cannot be located in the text and is never built. Both
forms therefore stay in the contract, with an explicit example of the two side
by side, even though the product reads only one of them.

Carrying the unit twice also lets each copy check the other, and the backend
repairs the copied boundary against the dictionary form the same answer
returned. Closed-class material a unit never carries — negation, subordinators
and copulas, listed per language — is dropped from the chip, and a reflexive
marker the dictionary form names is taken back in as the form the sentence
spells. The trim is withheld unless what survives it is the unit itself: a
negation dropped from a span still carrying free material would card a chip
saying the opposite of the sentence the reader is looking at, which is worse
than the untidy boundary it replaces. Re-scored over every recorded answer the
repair raises exact boundaries from 420 of 878 to 508 of 878 without costing a
single chip that was exact before, and on the tier that gates it moves 13 of 21
to 16 of 21. Resolving an overlap by fit rather than by arrival was measured on
the same answers and rejected: it recovered one boundary and lost two.

The first overlapping proposal wins, repeated words use the earliest
unclaimed occurrence, and an unmatchable proposal is ignored independently.
Every source word then becomes its own chip too, including articles, particles
and prepositions, and including the words a combination already claims: a chip
row therefore offers both the phrase and each of its words. Consequently
lookup completeness does not depend on the model deciding which ordinary words
matter, and an imprecise phrase boundary cannot cost the learner a lookup.

There is no numerical combination limit. Accepted combinations cannot overlap
and each occupies at least two source occurrences, so a text of `N` words
already has the structural bound `floor(N / 2)`. The prompt asks for every
clearly qualifying unit, explicitly accepts an empty list, and tells the model
not to pad it.

Every text chip owns the complete submitted text as its context. Tapping its
visible source form submits that form with explicit unit intent; the resulting
unit answer supplies the dictionary headword used by the note. A false-positive
combination therefore costs only an optional chip. Deleting a coherent proposal
would make a real lookup impossible, and the backend has no better lexical
judge than the model.

## What a unit produces

A unit answer keeps the full article: translations first, useful forms shown as
live phrases, usage, origin and examples. It creates one note about its selected
sense and four cards. A bare input selects the most common retained sense; a
chip with context selects the contextual sense. Every sense remains available
as a chip for a separate note.

A set expression is analysed whole and additionally offers every word-shaped
component in expression order, preserving its submitted surface form. Those
chips carry the first example sentence of the selected sense, not the bare
expression, because their contextual cards require a sentence.
A word or sense chip carries its own example; a chip from text carries the
source text. The frontend submits this chip-owned context directly.

## The pre-merge verdict measurement

The deliberately strict Step 0 gate used 122 English, German and Serbian
fixtures: 65 units and 57 clauses, fragments or sentences. Every answer was
usable under the neutral schema, but the zero-error gate did not pass:

| result | first merged wording |
|---|---:|
| text-like input called a unit | 1 / 57 |
| unit called text | 4 / 65 |
| false-text unit recovered as first chip | 0 / 4 |
| article contradicting JSON verdict | 3 / 122 |
| context sense selected without a context | 0 / 122 |

The false unit was `völlig durcheinander gebracht`. The four false text
verdicts were `возим бицикл`, `донео одлуку`, `steht zur Verfügung` and
`ide pešice`. Replacing a literal preferred value did not remove either class
of mistake. A second wording removed the expensive false positive on the
13-item regression slice but split three real inflected units and contradicted
its verdict once. It therefore also failed the pre-registered zero-error gate.

The product accepts the measured trade-off. A false unit is visible, undoable
and rare. A false text verdict cannot lose source words under the final
backend-filled chip design, although recovering the intended combination may
take more than one tap. Restoring the surface router would not resolve the
linguistic ambiguity and would reintroduce two divergent prompts.

The benchmark does not pretend that this linguistic boundary has one exact
answer. Its report always prints the raw fixture-by-verdict confusion matrix,
then adds a tolerant interpretation without changing the recorded answers:

- `correct` means the returned branch matches the fixture expectation;
- `acceptable` is a useful whole-unit boundary even though a smaller boundary
  is also plausible. In particular, `was rather reluctant about it` is useful
  enough as one learnable chunk: `it` is dispensable and `rather` is debatable,
  but neither makes the result an error;
- `ambiguous/defensible` covers reusable short utterances on either reasonable
  side of the boundary. `I have no idea`, `Ich habe keine Zeit`, `Ich weiß
  nicht`, `Das stimmt` and `Не знам` are examples, not false-unit failures. The
  class is registered by the shape of the utterance, never by what an answer
  happened to extract from it: `Ich habe keine Zeit` yields `Zeit haben`, a
  multi-word collocation on its own accepted list and a better unit than the
  bare `wissen` and `stimmen` its registered siblings yield, so scoring it a
  hard error while excusing them would grade the registration rather than the
  answer. Registering it leaves the hard-error count above its gate, which is
  what keeps this a correction and not a way through;
- `hard error` is reserved for a clear loss of the requested operation, such as
  treating a registered set expression as surrounding text or carding a whole
  contextual sentence whose changing subject, time or arguments are not part
  of its lexical unit.

`Пада киша` is an expected unit, not an ambiguous short-clause control. It is
the conventional Serbian predicate whose Russian, English and German
counterparts select different verbs: «дождь идёт», `it rains`, `es regnet`.
Exact dictionary labels and exact surface grouping remain separate diagnostics;
a reasonable headword form or useful unit boundary does not become a verdict
error merely because it differs from one registered string.

## Merged-prompt measurements and current state

`experiments/one_note_bench.py` imports the production prompt builder, answer
parser and segment filler. It groups append-only answers by prompt hash,
preserves earlier arms for comparison, resumes provider or parse misses from the
current production arm, and fails if either retired branch-prompt fixture
reappears. A valid wrong-branch answer is retained as quality evidence rather
than retried away. Its merged-prompt run combines the complete 122-item verdict
matrix with 26 text flows, nine bare unit flows and six possible chip flows.

All 157 initial fixture IDs must have a canonical attempt at the current prompt
hash, but small provider or parse misses are allowed: at least 142 must yield a
usable result. Availability and parseability are reported separately from
semantic scores. Hard errors may be at most 10% of usable verdicts; acceptable
and ambiguous/defensible boundaries do not count. The downstream quality
thresholds are at least 23 of 26 known texts on the text branch, eight of nine
cardable bare units, 18 of 21 distinct registered lexical units, five of six
successful clicks and two of three successful expression-component cases.
Every counted click still has exact identity and kind, carried context,
highlights, no components and four-card readiness; every counted expression has
the exact ordered component tuple and backend-owned context.

Zero tolerance is reserved for deterministic contracts: canonical current
fixture/hash identity, no accepted mixed branch, bounded and sanitized accepted
payloads, no context selector without context, four-card readiness for every
accepted unit note, exact source-token preservation by backend fill for every
accepted actual text payload, and carried-context preservation for accepted
click payloads. A wrong verdict is a verdict/branch-quality error; it does not
cascade into missing-token or missing-card structural failures.

One production-filled chip can recover at most one registered unit. A merged
chip containing neighbouring registered material is reported as partial/merged
recovery and cannot count once for each boundary it contains. Lookup labels,
optional combinations, strict article format, article/verdict disagreements and
tolerant verdict interpretation remain diagnostic.

A unit counts toward the gate only when its chip cards the registered entry:
an exact boundary, or a surface registered as an accepted alternative, where a
current experiencer may be left out of a reusable impersonal or reflexive unit.
A chip sharing at least two words with the unit and drifting by at most one
word in each direction is still reported, because it shows the model located
the unit; it does not count, because locating a unit is not carding it.

Tapping nine drifted chips reached the intended dictionary entry three times.
Four returned the drifted surface itself as the headword and declared it a
spelling correction, so the note carries the surface and the correction control
offers to undo a spelling the reader never mistyped; two answers were rejected
outright and fell to the paid fallback. Chips whose boundary is exact succeed
six times in six. That is why the gate counts what cards, and why the drift
stays visible beside it rather than absorbed into it.

A chip which shares nothing with the registered unit, or which runs on past it,
is still a miss.

The append-only file currently contains six complete 157-fixture prompt arms.
The raw verdict matrix and tolerant interpretation are:

| arm | provider answers | usable verdicts | raw `unit→unit / unit→text / text→unit / text→text` | `correct / acceptable / ambiguous / hard / unusable` |
|---|---:|---:|---:|---:|
| first merged arm | 148 / 157 | 109 / 122 | 59 / 3 / 9 / 38 | 97 / 1 / 4 / 7 / 13 |
| stricter exploratory arm | 33 / 157 | 17 / 122 | 6 / 1 / 3 / 7 | 13 / 0 / 0 / 4 / 105 |
| complete semantic arm | 157 / 157 | 114 / 122 | 62 / 0 / 34 / 18 | 80 / 1 / 3 / 30 / 8 |
| conservative-context arm | 155 / 157 | 112 / 122 | 62 / 0 / 18 / 32 | 94 / 0 / 4 / 14 / 10 |
| embedded-unit arm (v5) | 156 / 157 | 115 / 122 | 60 / 0 / 8 / 47 | 107 / 0 / 4 / 4 / 7 |
| production prompt (v6) | 157 / 157 | 122 / 122 | 62 / 4 / 5 / 51 | 113 / 0 / 2 / 7 / 0 |

The stricter arm is not a quality comparison: 124 calls found no available
model. The complete semantic arm carded every usable registered unit directly,
and correctly treated `was rather reluctant about it` as the acceptable whole
unit and `Пада киша` as an expected unit. It made 12 hard errors by carding
whole contextual sentences. Corrected scoring exposes another 18 obvious
over-broad unit verdicts among contextual fragments and ordinary short clauses
rather than treating their whole fixture classes as ambiguous. The 30 hard
errors are three English, 19 German and eight Serbian. That is why its numbers
are retained as evidence rather than presented as the current prompt's final
result.

Its downstream figures expose the same problem without hiding it in the
denominator: only 12 of 26 known-text fixtures reached the text branch, covering
78 of 178 source words and 22 of 53 function words and recovering four of 21
registered lexical units. Seven of nine bare-unit payloads were cardable and
five of seven morphology controls included forms. No contextual click arm was
run from that failed branch assignment.

The conservative-context arm passed availability with 145 usable initial
results, but failed the semantic thresholds. Fourteen of 112 usable verdicts
were hard errors: none in English, nine in German and five in Serbian. Only 16
of 26 known texts reached the text branch, so production-filled chips recovered
8 of 21 registered units; the accepted text payloads still preserved all 102
source tokens and all 29 function-word controls. All nine bare units were
cardable and all three expressions returned exact components, but no clicks
were run because the source text branches failed.

The embedded-unit arm (v5) passed every deterministic contract, availability
with 147 of 157 usable initial results, and verdict quality with four hard errors
among 115 usable verdicts. Eight of nine bare units were cardable and all three
expressions returned exact components. It nevertheless failed the downstream
semantic gates: only 20 of 26 known texts reached the text branch and their
production-filled chips recovered 13 of 21 distinct registered units, so the
dependent click arm did not run and reported zero of six successes. Two of the
six text misses were retriable parse misses. The other four were whole-unit
verdicts for finite situational clauses: three German and one Serbian.

Those four errors share one boundary rather than a surface shape. A fixed
expression occupied most of each clause, and the model absorbed a freely chosen
subject, object, complement, experiencer or subordinate proposition into the
unit. The production prompt therefore defaults an uncertain whole-clause unit
to text and returns its embedded expression separately. Only a conventional
fixed formula whose whole wording is reusable as-is is excepted; genuinely
borderline short formulas retain either reasonable branch.

Its complete arm returned 157 of 157 usable initial results. Among 122 verdicts,
113 were correct, two were ambiguous/defensible and seven were hard errors. The
two gray-zone unit verdicts, `Das stimmt` and `Не знам`, are reusable short
formulas for which either branch is defensible; the seven clear operation-loss
cases remain hard errors. Twenty-five of 26 known texts reached text, every one
of nine bare units was cardable, production fill recovered 18 of 21 distinct
registered lexical units, and all three expression cases returned exact ordered
components and backend-owned contexts. Five of six clicks met every registered
success condition. The remaining click produced an unusable payload with an
empty meaning label, not an accepted payload that broke a deterministic
contract.

The then-registered automated contracts passed. Exact dictionary labels were 14
of 21 and exact source boundaries were 15 of 21; these remain diagnostics rather
than being reclassified as semantic or structural failures. The Serbian slice
returned 57 of 57 usable results, with 40 exact and three hard verdict errors
among 44 verdict fixtures.

The conservative-context arm's apparent sanitization failure was a harness
error, not an accepted production-contract defect. The scorer sanitized the
article and then required a second sanitizer pass to leave it unchanged, even
though escaping an ampersand is intentionally not idempotent. Scoring the
actual post-sanitizer article and parsed sentence fields structurally makes all
of that arm's deterministic contracts pass. Strict raw article format remains
the separate diagnostic it was registered as.

The preceding isolated downstream run remains useful background, not a claim
about the merged prompt. Its deterministic fill covered all 178 of 178 source
words and all 53 of 53 function-word controls, recovered 21 of 21 registered
lexical units, and retained every meaning with four non-empty fronts across
nine bare and six click results. Nineteen of 21 combinations contained every
registered source part; omitted pronouns remained as standalone chips. Three of
six negative controls stayed empty, with `hat … angerufen`, `richtig schön`
and `went outside` as the optional extras.

Those figures name the scoring policy printed with that run. Raw JSONL is
append-only and is not rewritten when the scorer changes. Current rescoring uses
one-to-one recovery, so a single merged chip cannot preserve an older 21/21
label by standing in for two distinct clickable units; the merged chip remains
visible as useful boundary drift and the aggregate registered-unit floor absorbs
one such case.

## Prompt-bound qualitative review and benchmark promotion

**The v6 arm is BLOCKED.** Its aggregate automated screen passed the contracts
registered at generation time, but a fresh semantic review of the accepted
current-hash unit payloads found that **24 of 82 results highlighted contextual
words beyond the lexical unit**. Twenty-two left no source-language word outside
the bold spans at all, usually producing a sentence made almost entirely of
blanks on ContextProduction:

- `bare-en-reluctant`, `bare-de-bank`, `bare-sr-grad`, `bare-sr-umoran`;
- `verdict:units:en:6`, `verdict:units:de:1`, `verdict:units:de:2`,
  `verdict:units:de:10`, `verdict:units:de:11`;
- `verdict:units:sr:1`, `verdict:units:sr:4`, `verdict:units:sr:8`,
  `verdict:units:sr:10`, `verdict:units:sr:11`;
- `verdict:inflected:en:3`, `verdict:inflected:de:1`,
  `verdict:inflected:de:2`, `verdict:inflected:sr:3`;
- `verdict:controls:de:1`, `verdict:controls:sr:0`,
  `verdict:fragments:de:7`, `click-de-function`.

The other two were `text-de-3`, which absorbed the subject and current object
into `etwas unter die Lupe nehmen`, and `verdict:fragments:de:6`, which absorbed
the subject and auxiliary into `sich bewerben`. Those two are linguistic
boundary errors and remain review evidence; backend grammar guesses would be
brittle. The 22 whole-sentence cases are structurally provable and are rejected
by the parser. A supplied click is safer still: when its exact submitted surface
tokens occur in the carried context, the backend constructs the highlighted and
gapped forms from that surface and cannot expand it. The prompt independently
states that subjects, objects, auxiliaries, modifiers and current arguments stay
outside the unit.

This review does not change the declared gray zone. `Пада киша` remains an
expected unit; `was rather reluctant about it` remains an acceptable whole-unit
boundary; `I have no idea`, `Ich weiß nicht`, `Das stimmt` and `Не знам` remain
defensible reusable formulas on either branch. The stricter sentence-form rule
asks each formula to occur inside a short context; it does not reclassify the
formula itself.

### v7 smoke review and current measurement state

**The v7 smoke arm is BLOCKED only by its systematic typo failure: zero of
three registered corrections succeeded.** `recieve` returned both `word` and
`suggestion` as `receive`; `Strase` returned both as `Straße`. `мозда` retained
`word` as submitted but left `suggestion` empty while its visible article
silently opened on and analysed `можда`. The prompt told the model both to
retain submitted spelling and to make `word` a clean dictionary headword. The
correction behavior is therefore a prompt conflict, not three unrelated
content slips. It is settled the other way now: the dictionary lemma heads the
article and goes in `word`, the misspelling is reported through `suggestion`
alone, and the card carries the corrected spelling.

Fresh review found none of v6's whole-context highlighting pathology in any
accepted v7 unit. All 21 registered-combination smoke texts reached the text
branch and backend fill preserved every source token. Eight of nine bare units
were cardable and five of six dependent clicks met their complete structural
contract. `bare-en-give-up` was safely rejected: the provider put adjacent
`<b>give</b> <b>up</b>` spans over one contiguous target but supplied one blank,
so its raw forms did not match. This is a bounded provider/format miss, not an
accepted unsafe card. The prompt now asks for one bold span around a contiguous
multi-word unit, and the parser may normalize only whitespace-adjacent bold
spans whose one-blank transformation is otherwise exact; the outside-context
guard is unchanged.

The automated v7 recovery scorer over-counted `text-de-1` and `text-de-9`.
Their chips omitted fixed material: `freue … auf` omitted the reflexive `mich`,
and `uns … beschränken` omitted governed `auf`. A dictionary label cannot repair
missing clickable source pieces. Recovery now uses exact filled pieces,
expanded boundaries which contain every required piece, or a named accepted
surface alternative. The only such smoke alternative is the variable
experiencer boundary `se čini` for `mi se čini`; it is explicit rather than
inferred by token omission. Strict semantic recovery is consequently 18 of 21
and still passes its aggregate threshold.

Other reviewed v7 errors were bounded model-quality misses: optional expanded
or reduced combination boundaries, one safely rejected bare payload, the one
failed click derived from it, and article-level translation, morphology,
formatting or explanatory slips. They remain visible evidence under the
existing tolerant thresholds and are not blockers. In particular, numbered or
bulleted article prose is already reported by the strict-format diagnostic and
does not justify another parser rejection rule.

The typo and contiguous-span wording changes created the v8 production prompt
hash; the v7 result did not accept it.

### v8 smoke review and current measurement state

**Fresh semantic review BLOCKED v8.** All 30 canonical answers parsed, 20 of 21
known texts chose text, all nine bare answers passed the structural screen, all
six clicks and all three expressions passed, and the v6 whole-context failure
was absent. The accepted typo gate nevertheless failed: `typo-sr-mozda`
silently changed submitted `мозда` to visible and payload `можда` with an empty
suggestion. Its two-of-three exact typo total cannot override that failure.

Strict registered recovery was genuinely 16 of 21. The exact misses were
`text-de-1` (fixed reflexive `mich` omitted), `text-de-4` (support verb `habe`
omitted), `text-de-6` (the whole sentence returned as a unit instead of `in
Frage kommen`), `text-sr-3` (`се` omitted while negation was absorbed), and
`text-sr-4` (the experiencer construction omitted while destination `на посао`
was absorbed). General prompt self-audit now requires every present fixed
reflexive, particle, preposition and support verb, excludes current negation,
destination and arguments, and reconciles the label with the surface. It does
not encode these five fixture strings or revoke the approved variable-
experiencer gray zones.

The separate `bare-de-rad` answer contained `Rad zu fahren` but highlighted
only `Rad zu`, leaving exact submitted token `fahren` unmarked. Semantic review
therefore treated it as uncardable and the tolerated bare total as eight of
nine. The parser now catches only this general literal-token case and still
does not assume morphology when the submitted and example tokens differ.

The schema asks the model to declare whether the unit word is the same
submission, a morphology lemma or a typo. The parser reconciles that claim with
the two spellings rather than refusing a payload which contradicts itself, so
an admitted correction always ends up visible instead of discarded. The field
still cannot prove that the model chose the right linguistic class: a spelling
error can be mislabeled as morphology and believed. Registered typo fixtures and
fresh review remain mandatory; an absolute distinction would require an
independent judge. The harness marks an incomplete current-hash packet
`unmeasured`; even a complete automated packet is only
`pending_semantic_review`. Promotion restarts at smoke without substituting any
earlier answer from the append-only store.

### Two-judgement arm: full-tier review and decision

**Accepted.** The full tier ran 195 calls on a healthy free pool: every deterministic
contract passed and every quality threshold passed, with hard verdict errors at 7 of
120 usable against a 10% ceiling. The mandatory semantic review of the concrete packet
found three things to settle before acceptance, and all three are settled.

Sentence form is screened on the marked example, which is the only copy the contract
asks for: a sentence carrying markup other than its own highlight is a defect. Four
stand in the measured packet — `put up with` bolded two whole sentences, and two
separated German units were marked incompletely, `eine Rolle spielen` without `eine`
and `unter die Lupe nehmen` without `nehmen`.

The coinage operating point is accepted as measured, not as hoped: none to three of
six survive both judgements, and what survives is the well-formed compound carded with
an invented sense and origin. The band is a property of particular strings rather than
of a run. Counted over eleven samples of the standalone judgement, `Löffelangst`,
`змркалица` and `blorptium` are refused eleven times out of eleven and `Fahrradsuppe`
nine, while `tablewards` is refused three times and `bookshelfy` once. Asking the same
question twice would therefore buy almost nothing on the two that get through, and a
third check of the same kind is not the lever; only an attestation source would be, and
no free one covers English, German and Serbian alike.

The false-refusal half is accepted with it. Rare real wording drew no refusal in
forty-four samples, and ordinary mid-frequency wording scored five of six on two
successive tiers with the same word — `сврака` — refused both times. Eleven of twelve
ordinary lookups keeping their entry, with the single failure being one repeatable
item rather than a different word each time, is the measured cost of the judgement
that withholds the coinages. The review's quality observations — a Serbian card
headed by a Russian verb, an imperative kept as a headword, three registered Serbian
combinations missed — are recorded as this arm's known cost; they sit inside the
declared tolerances and are properties of the free pool rather than of the contract.

### What the answers are known to get wrong

A second full tier, semantically reviewed item by item, blocks on nothing and records
the limitations below. The attestation slice is the strongest part of the run — all
six coinages refused, all four rare real words kept with accurate registers — and the
Serbian slice the weakest.

**A misrouted fragment cards a note whose two directions teach different things.** The
recognition side carries the lemma the answer chose and the production side the gap
from the submitted fragment, so `sehr schüchtern gewesen` cards the front `sein` with
the back "быть" against the gap `Er ist früher ___.`. This is the only class here that
is silently and confidently wrong rather than merely imperfect, and it is the first
thing to fix. An example pinned to a submitted fragment also keeps that fragment's
inflection, so it can be ungrammatical in its own sentence.

**A free combination submitted as a fragment is carded as a set expression**, with a
compositional etymology invented to justify it. When a sentence is answered on the
unit branch, its examples can be written in the target language with the source unit
embedded, while the card payload of the same answer stays correct.

**Grammar and etymology stated in the prose are wrong often enough to matter, and no
gate sees them.** Serbian is the worst-affected: seven of twelve Serbian articles here
state at least one false fact about Serbian grammar, against six of nineteen German
and two of eight English. A correctly headed, correctly carded article can still teach
a false rule or an invented etymon. The forms table also names cases and tenses
instead of carrying grammar in phrases, which the functional description forbids.

**Three screen rules are known to measure the wrong thing.** A payload the production
parser repaired but the strict reader rejected skips the highlight checks entirely,
because those checks are gated on the strict payload naming a unit. "Submitted token
occurs outside target" fires on every legitimate discontinuous unit. `origin`, `usage`
and `morphology` are presence regexes, so a false etymology scores as an etymology and
a case-labelled table scores as morphology — the most common real defect in the run is
invisible to every gate. The review packet should also carry the screen's own counts
and thresholds, which it does not.

### Two experiments that were not run, and why

Worked examples in the prompt — one positive and one negative instead of restating
the boundary rule — are abandoned. They cannot be accepted on one run, and the misses
they would address are proposals the model never made at all, which no example of a
boundary reaches. Tapping the chips a repair produces, against unrepaired controls,
stays available but unspent: the repair was measured to remove most failing taps at
source, so the measurement is worth its calls only where a tier shows the boundary
still costing cards.

## What the shorter prompt cost and bought

Moving the derivable obligations into the parser let the prompt drop by about a
quarter. The smoke arm for that shorter prompt clears every deterministic
contract and every aggregate threshold, with exact typo correction and the
click cases both complete. Cutting the surface-boundary rule out entirely was
too far: without it the answers pulled negation, complementizers and current
objects into a surface and lemmatised reflexive particles the sentence spelled
differently, and two reflexive-verb sentences returned no combination at all.
The rule is therefore stated once, inside the surface paragraph, naming what to
exclude and requiring each fixed piece in the form the sentence gives it.

Semantic review of that arm leaves seven concrete items. Two are tolerated: an
impersonal reflexive whose experiencer is omitted, and a governed instrumental
kept inside a Serbian surface. Five are genuine and remain review evidence: an
omitted obligatory reflexive, a lemmatised reflexive with the current object
swallowed, an auxiliary pulled into an English surface, an example whose
highlight replaced an inflected verb with its infinitive, and one Serbian
payload with unquoted JSON string values. Serbian JSON validity is the
recurring availability-independent defect and is the first thing to watch on
the next arm.

The harness has three exact, append-only-resumable tiers. Every tier derives the
same six click fixtures after their source texts succeed and runs at pacing two
seconds with concurrency one:

| tier | canonical manifest | typo manifest | attestation manifest | clicks | maximum calls |
|---|---:|---:|---:|---:|---:|
| smoke | 30 | 3 | 5 | 6 | 44 |
| confirmation | 81 | 6 | 10 | 6 | 103 |
| full | unchanged 157 | 6 | 10 | 6 | 179 |

The attestation manifest holds rare real wording alongside well-formed coinages,
and both classes are required at every tier: measured on one class alone the arm
rewards either fabrication or paranoia.

Smoke contains the 20 text fixtures with registered combinations, the
standalone English click source and all nine bare cases. Confirmation contains
all 35 downstream text/bare fixtures, the 38 distinct hard-verdict IDs observed
across the five complete and comparable historical arms, and eight disjoint
gray/stable anchors. The availability-collapsed v2 arm is not used to invent a
39th historical-hard fixture. Exact IDs live in the harness; tests freeze the
30/38/8/81 arithmetic.

The six typo fixtures are `recieve` → `receive`, `Strase` → `Straße`, `мозда` →
`можда`, `definately` → `definitely`, `vieleicht` → `vielleicht` and `podrska` →
`podrška`. They are validated source-language inputs and always use explicit
unit intent.

**What is gated is the card the reader ends up with, and nothing else: no entry
may be headed by the spelling they mistyped.** That is the only card a
misspelling can produce which teaches the mistake, and it is zero tolerance. A
withheld entry counts as safe, because production shows nothing rather than a
card — the reader is told the wording is not vouched for, and the correction is a
tap away. Measured across every run in which both judgements were in place, this
has been zero.

How often the answer *names* the misspelling as one is a diagnostic and gates
nothing. It measures the answer's manners rather than the reader's card: an entry
which silently heads itself with the correct spelling hands over exactly the right
card and scores nothing on that count. The free pool names three or four of six
across runs and has never named five; the entry is nonetheless about the right
word four to six times, and the paid model, which every declared misspelling is
handed to, corrects six of six. Gating the naming would hold the arm to a number
its own product does not depend on.

The zero-tolerance contract binds the parsed note rather than the raw payload.
This is typo coverage, not a morphology rule.

Every report labels itself **AUTOMATED SCREEN** and writes a structured review
packet containing every non-exact boundary/label, acceptable or ambiguous
verdict, hard error, recovery path, click, typo and provider/unusable miss, with
fixture ID, input, expected result, actual result and raw answer evidence. A
passing screen is never semantic acceptance. A fresh agent must review those
concrete errors and record the prompt-bound decision in this checked-in spec.

Prompt work is promoted in order: smoke while iterating; confirmation for a
candidate; fresh-agent packet review and a recorded decision; then the full
179-call maximum immediately before commit. A failed semantic review returns to
smoke. Full is the pre-commit measurement, not a substitute for review. Raw
outputs remain append-only through every tier and prompt hash.

## Trust boundary and Serbian

The model supplies linguistic judgement; the backend enforces types, bounds,
sanitization and the structure required to render or card the result. It does
not overrule a JSON verdict from article prose, adjudicate whether an optional
combination is lexically canonical, or repair translations and morphology.
Those disagreements and qualitative errors remain visible benchmark evidence.

Every rerun is read by language as well as in aggregate. Serbian mixes both
scripts and is already the weakest morphology slice on the selected free pool;
its measured arm figures are also recorded in `decision-llm-backend.md`. They
can reopen prompt wording, but not silently change the selected backend kind.
The Serbian slice reports availability, usable results, exact verdicts, hard
errors and strict format; it has no separate zero-error gate.

## What would re-open this

- A revision of the merged production prompt or its unit/text schema: all
  verdict and downstream figures are prompt-bound.
- The free pool's primary model changing or disappearing.
- Real use showing that false-positive combination chips obscure useful word
  chips, or that users cannot recover false-text units through the complete
  chip row.

The harness is outside CI and calls real models. Its free-pool phase is paced;
any paid fallback phase spends real money.
