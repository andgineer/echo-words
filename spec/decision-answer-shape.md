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

The advice has its own field, separate from the correction. One field carrying
both was measured and produced neither: models fill a field called `suggestion`
only for a spelling they are calling wrong, and for a correctly spelled word they
left it empty across two promptings and three model families. The knowledge was
never missing — those same answers name the commoner word in the usage prose,
"не следует путать с *casual*" — so what failed was routing a finding into a
field whose primary sense contradicted it. Binding the prose to the shared field
made it worse: told that naming a confusion obliged it to fill the field, the
model stopped naming the confusion.

With a field of its own the offer appears, and appears only where it should.
Six fixtures measure it — three real words a letter or two from a markedly
commoner one, three ordinary words that must be offered nothing. Over a tier
answering every one of its calls, the field is non-empty exactly once in 201
answers, on the registered pair, with the article still entirely about the
submission; no ordinary word, sentence or coinage drew an offer, and the
correction field stayed non-empty only on misspellings, always holding the
correction. The separation the two fields were meant to produce is what the
answers show.

A misspelling does draw one. On a later tier `definately` returned `also_common:
"defiantly"` — and inverted the field's premise, since `defiantly` is the rarer
word of the two. It reached no reader: a declared correction outranks the offer,
so the entry showed `definitely`. It is invisible to the gate as well, which
scans the six registered pairs and nothing else. The field is therefore advice
whose premise the answer is not held to, and the misspelling branch is the one
place that has been seen to break it.

What it costs is coverage, not correctness: one of three registered pairs fired.
A second pair produced a shorter article that named no confusion at all, so
nothing reached the field. The offer is therefore advice that arrives when the
answer happens to notice, not a guarantee — which is what an offer beside the
card can be, and is why nothing downstream depends on its presence.

A fixture instantiates this requirement only when the submission is wording the
answer will vouch for. One the standalone judgement refuses as unused never
reaches the branch that offers a neighbour, and measures the refusal instead.

### Where the free pool's answers stand against fresh review

The deterministic contracts pass, the answers around them are uneven, and the
gap is invisible to the screen: every defect below satisfies every contract.
Roughly half of a review packet's items carry a defect the learner would read,
and a quarter of the packet one they would drill. The classes, worst first:

- **A misspelling carded as if correct.** The article keeps the misspelled
  wording, calls the relation `same`, and spells the non-word in every example.
  Nothing in the card contract can catch it. What catches it is the parallel
  judgement, which refuses the wording separately and withholds the note — the
  measured case where that safety net is the only thing standing between the
  learner and four cards teaching a word that does not exist.
- **Cards headed by the wrong word** — a copula glossed with the adjective's
  sense, an article headed by a different verb than the one submitted.
- **Ungrammatical or bilingual example sentences**, some of them on card fronts:
  wrong adjective declension after a determiner, a wrong auxiliary, a Russian
  subject with a German predicate.
- **Etymology invented with a straight face**, stated as fact rather than hedged.

None of these classes is created by the answer contract, and the review found
nothing in the packet arguing against it. They are the free pool's own quality,
and they are why fresh semantic review is mandatory rather than advisory: the
screen certifies conformance, and conformance is not correctness.

Two findings sit in our own code rather than the model's, and they are not the
same kind of thing. Repairing a payload whose string values are unquoted is
deliberate and earns its keep — a repaired card reaches the learner where a
rejected one does not; what is wrong is that the screen counts the repaired
answer as a parseable one, so a measurement of how well models follow the
contract silently includes answers that did not. The other is a product
strictness: a contextual analysis correct in every other respect is discarded
because it reproduced the supplied sentence without its final period.

### The verdict gate reads high against its own manifest

The hard-error rate sits above its threshold on a screen whose reviewed rate sits
below it. Three of the fourteen counted errors carded exactly the extraction
their fixture registers as accepted, and behave identically to sibling fixtures
the manifest already lists as defensible; the difference between them is the
registration, not the answer. The reviewed rate over the genuine errors is inside
the band every earlier run measured, so the model has not regressed.

The gate stays as it reads. Re-labelling those three would be an argued change to
the manifest, and it is not one to make in the same breath as accepting a feature
the same run was measuring — the party defending a result does not get to move
the line it is judged against.

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

The correction and the commoner near-spelling arrive in separate fields and are
reconciled into one thing the entry shows, because the reader has room for one
piece of advice about their spelling. The correction outranks it: a reader told
their word is misspelled is not also asked to weigh a different word. The
near-spelling is read only beside a relation the answer itself vouched for, and
it passes the same validation and the same repeats-the-headword drop, so a field
the model fills carelessly can add an offer but never a claim.
It is a consistency boundary, not an independent spelling judge: a model can
still call a misspelling morphology, so registered typo fixtures and fresh
review remain required. For an explicit context request, the selected meaning's
first plain example must be the supplied context, allowing only the sentence's
final punctuation to differ — a difference anywhere further in is a rewrite, and
a rewrite is what the rule exists to reject. The card then carries the context
the backend supplied rather than the model's copy of it, so the comparison has
one degree of freedom and the card has none. Of 152 recorded contextual answers
three failed strict equality: one dropped its full stop, and two rewrote the
sentence. Where the submitted click surface can be matched token-for-token in
that context, the backend constructs the two forms itself; otherwise the model's
forms must pass the same structural checks. The parser does not verify morphology, infer the
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
