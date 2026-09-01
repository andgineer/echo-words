# The shape of an answer — decision

Status: **decided 2026-08-27 — one neutral contract returns either a full
dictionary article for a unit or a translation and explanation for text. Unit
articles open on meaning, never name a part of speech, and show useful
inflection as live phrases.** The production-prompt harness is
`experiments/one_note_bench.py`; the original forms study remains in
`experiments/forms_bench.py`.

## The problem

An answer that opened `наречие, разговорное: позавчера` made the reader work
past metadata to reach the thing they asked for. The part of speech is the
worse piece: it takes the most prominent space while adding little a reader
cannot infer.

Forms are the opposite case — genuinely wanted and easy to state badly. A
learner of German needs to recognise `du nimmst`, and a learner of English
needs `brought`, not a grammatical inventory. A short phrase teaches the form;
the terminology does not.

The same input box also accepts running text. It needs a coherent translation
and explanation, not a dictionary article or a card payload. Selecting one of
two prompts before asking the model reproduced a classification problem that
surface punctuation and length cannot solve, so branch selection now belongs
to the answer itself.

## The one answer contract

Every attempt uses the same production prompt and ends with a bounded JSON
object whose neutral `kind` is `unit` or `text`.

- A unit article starts with the meanings that require different words in the
  configured target language, ordered most common first. A register mark
  follows the translation it qualifies. Usage, origin and examples follow;
  a set expression also explains its parts and why the whole means what it
  does.
- A forms section appears only when a changing shape is useful to recognise or
  produce. It is a table of short everyday phrases with translations. Person,
  number, gender, case, tense and part-of-speech headings are not printed.
  Invariable units get no table.
- A text article translates and explains the submission as a whole, focusing
  on what is difficult in that text rather than walking through every word.
  Its JSON names only conservative multi-word combinations; the backend adds a
  chip for every source word alongside them.
- Unit JSON carries the validated dictionary headword, its claimed `same`,
  `morphology` or `typo` relation to the submitted spelling, advisory spelling
  suggestion, all retained meanings, finished highlighted examples, optional
  contextual-sense index and expression components. Text JSON carries
  none of those card fields. Mixed branches are unusable.

The visible article may use `<b>`, `<i>`, `<table>`, `<tr>` and `<td>`. No tag
has attributes. JSON sentence strings use only the allowed emphasis and blank
marker required for the four cards. The sanitizer matches whole literals, so
the model has no general HTML surface.

## What was measured

The original, vocabulary-only forms study covered 29 English, German and
Serbian inputs: 22 with recorded informative forms and seven invariable
controls. Its free pool returned a table for every inflecting unit, included at
least one informative form in 94%, every expected form in 89%, invented no
registered trap form, and added no table to an invariable control. That result
motivated the phrase-table design, but the merged production prompt supersedes
its prompt-bound percentages.

The append-only production-flow run in
`experiments/.bench-one-note-post/` measures nine bare unit flows alongside the
unit/text verdict matrix and derives six contextual chip flows only after the
text branch is confirmed. The v6 prompt returned a usable result for all 157
initial fixtures. Its 122 usable verdicts comprised 113 correct, two
ambiguous/defensible and seven hard errors. Its automated scorer sent 25 of 26
known texts to the text branch, called all nine bare units cardable, recovered 18 of 21 distinct
registered lexical units, and returned exact components and backend-owned
contexts for all three expression cases. Exact raw dictionary labels were 14
of 21 and exact source boundaries were 15 of 21; both remain diagnostics because
useful headword normalization and boundary variation do not break the answer
contract. The Serbian slice returned 57 of 57 usable results, with 40 exact and
three hard errors among its 44 verdict fixtures.

The automated v6 screen initially counted five of six dependent clicks and all
nine bare cases as cardable. Fresh semantic review blocked that arm: many of
those nominally complete card fronts marked context beyond the requested unit.
The prompt and structural parser therefore changed, and those aggregate v6
figures are evidence for the failure rather than acceptance evidence for the
current prompt.

The production gate does not require a perfect model sample. Its smoke,
confirmation and full tiers contain 44, 103 and at most 179 calls respectively;
the full tier keeps the canonical 157 unchanged and adds six click, six typo and
ten attestation calls. Aggregate availability and semantic thresholds tolerate bounded model
misses. Every accepted unit still has four-card readiness and safe targeted
sentence forms, every counted click has exact target identity/kind, context,
surface and empty components, and every accepted typo cards the corrected
spelling. Strict article format, morphology, usage and origin percentages remain
diagnostics, including in the Serbian slice. A fresh-agent review of the
structured error packet is mandatory even when the automated screen passes.

Sanitization alone is insufficient for card sentence fields. Accepted forms
must also be exact transformations of the plain example and must retain a real
word of sentence context outside the unit. The post-sanitizer structural check
remains distinct from strict raw article formatting.

Qualitative linguistic mistakes stay visible evidence rather than being
silently repaired by deterministic code. A prompt arm with invalid or missing
answers is reported as such; availability misses are never counted as content
quality and an earlier hash is never substituted for the current prompt.

### The near neighbour offered beside the card

Six fixtures measure the offer: three real words a letter or two from a markedly
commoner one, and three ordinary words that must be offered nothing. On a pool
answering every call, no registered pair produced the offer and no ordinary word
drew a false one.

The neighbour itself is present in those answers, as prose. `causal` is analysed
with "не следует путать с *casual*" and `wider` with "не следует путать … с
*wieder*", by two different pool models, while the structured suggestion stays
empty. The knowledge the requirement needs is in the free pool's first answer;
what the current wording does not do is carry it into the field the interface
reads. That is a routing result, not the pool's refusal, so the requirement
stands: dropping it, or deriving the neighbour from an edit distance against a
per-language frequency list the project does not have, would both be answers to
a question this measurement did not ask.

A fixture instantiates this requirement only when the submission is wording the
answer will vouch for. One that the standalone judgement refuses as unused never
reaches the branch that offers a neighbour, and measures the refusal instead.

### Where the free pool's answers stand against fresh review

The deterministic contracts pass and the answers are still not acceptable. Over
half of a review packet's items carry a defect the learner would see, and a third
of the packet one they would memorise. Four classes block acceptance:

- **Ungrammatical target-language sentences on card fronts** — `einen äußerst
  gelungener Abend`, `the definitely best solution`, a German example with the
  finite verb off second position. The card is the product; a drilled error is
  the worst outcome the answer can produce.
- **Analyses in the wrong language, or half in it** — a Serbian submission
  answered entirely in Serbian with no Russian anywhere, and example sentences
  that switch language mid-clause.
- **Invented facts stated with confidence** — a non-existent idiom as the bold
  heading, an aspect pair that is not a verb, an etymology built on a false
  cognate, a Swiss orthographic rule that does not exist, and a spelling card
  that states its own rule backwards.
- **Silent card loss** — a correct analysis that cards nothing because its
  payload is malformed, empty, or reproduces the supplied context with the final
  period dropped.

Two further findings sit in our own code rather than the model's. A card payload
whose string values are unquoted is repaired and scored valid, so the screen
reports conformance the answer did not have; and an exactly correct contextual
analysis is discarded over one character of punctuation. Repair generous enough
to hide a malformed payload, and a comparison strict enough to throw away a
correct one, are the same boundary set wrongly in opposite directions.

## Trust boundary

The parser normalizes harmless singular/list variation, drops an independently
malformed meaning and sanitizes the printed strings. The highlighted form must
be the plain example with bold spans added and nothing else changed, and must
not consume the entire sentence; the blanked form is then derived from it, so
the two cannot disagree. Adjacent bold spans separated only by whitespace are
merged into one contiguous span in preference to keeping them apart, and the
same outside-context guard applies to the result, so splitting every word
cannot bypass whole-sentence rejection. The claimed word relation is
reconciled rather than enforced. An admitted correction produces a typo whose
headword is the wording the answer analysed — the same wording its meanings,
examples and gapped sentence describe. A `same` claim contradicted by a differing
word produces morphology instead: a dictionary form for an inflected submission is
by far the commoner reading of that contradiction, and calling it a misspelling
would accuse the learner on a large share of everything they submit. The card is
the same either way; only what the entry says about it differs. A suggestion that
merely repeats the headword is dropped, because it would offer the reader the word
already carded.
It is a consistency boundary, not an independent spelling judge: a model can
still call a misspelling morphology, so registered typo fixtures and fresh
review remain required. For an explicit context request,
the selected meaning's first plain example must equal the supplied context. Where
the submitted click surface can be matched token-for-token in that context, the
backend constructs the two forms itself; otherwise the model's forms must pass
the same structural checks. The parser does not verify morphology, infer the
linguistic boundary of a generated example, or decide whether prose agrees with
`kind`. The complete response is bounded at
16,000 characters before JSON decoding and segment filling. Streaming exposes
at most that prefix while draining any excess to provider settlement; the
settled pool call is rated as unusable, and a final oversized attempt cannot
make a note from its truncated prefix.

## What would re-open this

- Another production-prompt revision, because both the branch and answer-shape
  measurements are prompt-bound.
- The pool's primary model changing.
- Repeated learner-visible invented forms. The first response should be prompt
  and model evaluation, not hardcoded morphology.

## Why a combination never consumes its words

A word which a combination claims keeps its own chip, so the chip list holds
both the phrase and each of its parts. Tapping the phrase looks up the whole
construction; tapping a part looks up that word alone. Both are useful, and the
learner chooses.

This is what makes an imprecise phrase boundary cheap. When an answer omits an
obligatory reflexive particle, drags in an auxiliary or lemmatises a piece, the
phrase chip is merely less good — no lookup disappears, because every word is
still there on its own. The prompt therefore states the surface rule once and
does not spend paragraphs defending a boundary whose cost is now bounded.
