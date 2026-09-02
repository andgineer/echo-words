# The shape of an answer — decision

Status: **decided 2026-08-27 — one neutral contract returns either a full
dictionary article for a unit or a translation and explanation for text. Unit
articles open on meaning, never name a part of speech, and show useful
inflection as live phrases. The prompt asking for it carries only the branches
the request can still be in: a selected unit gets the unit contract alone, and
the submit box gets both.** The production-prompt harness is
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
two prompts *in code* before asking the model reproduced a classification
problem that surface punctuation and length cannot solve, so where the branch
is open it belongs to the answer itself. Where it is not open the question
never arises: a tapped chip and a one-word submission are units by the action
that made them.

## The one answer contract, asked by the prompt the request needs

Every attempt ends with a bounded JSON object whose neutral `kind` is `unit`
or `text`. The contract is one; which of its branches the prompt states is not.

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

### Two prompts, because half of one of them could never apply

A chip tap was asked with 8,787 characters, of which the text branch, the
branch decision it had already made, the leading verdict and the near-spelling
search were 47% that could not apply to it. A fast free model was being asked
to hold two contracts in view and obey whichever turned out to be live.

The selected-unit prompt now states the unit contract and nothing else — no
text branch, no branch-decision paragraph — and runs 4,651 characters; the
submit box keeps both branches at 7,205. Both are built from the same
fragments, so a rule that applies to both is written once.

Measured over a full tier: every selected-unit article call answered on the
unit branch, all six clicks kept their context and surface exactly, and usable
results rose to 156 of 157 against 147 on the merged prompt. Known text reached
the text branch 26 times of 26 against 24, cardable registered units 19 of 21
against 17, and obvious hard verdict errors fell to 6 of 121 usable verdicts
from 10 of 113. Nothing measured here got worse. The registered-unit count sits
above the 13-17 spread six earlier runs measured, on one sample, which is a hint
and not a new floor.

A rule that only ever mattered to one branch belongs in that branch's prompt.
The three rules added on the tier before the split — source-language examples,
heading-and-gloss coherence, and a clause with its own subject and finite verb
read as text — were checked against that: the first two apply to any unit
article and stay in both, and the clause rule is part of the branch decision,
so it now sits only where a branch is still to be decided.

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
confirmation and full tiers contain 55, 125 and 216 calls respectively; the full
tier keeps the canonical 157 unchanged and adds six typo, sixteen attested,
twenty-two attestation, six near-neighbour, three word-list and six click calls.
A handful of derived second judgements sit outside those totals, because how many
of them a run needs is the draw's to decide and not the manifest's. Aggregate
availability and semantic thresholds tolerate bounded model misses. Every accepted unit still has four-card readiness and safe targeted
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

### The near neighbour is prose, not an offer

A commoner word one or two letters from the submission is named in the article
if the answer notices it, and there is no field for it. Six fixtures measure
what the reader gets: three real words a letter or two from a markedly commoner
one, three ordinary words that must be offered nothing.

A field of its own was built and measured first, because the shared
`suggestion` field produced nothing — models fill a field with that name only
for a spelling they are calling wrong. The separate field did appear, and only
where it should: non-empty exactly once in 201 answers, on one registered pair,
no ordinary word or coinage drawing an offer. What it bought was one tap on one
of three pairs, and it carried a premise the answer was not held to — on a later
tier `definately` filled it with `defiantly`, the rarer word of the two, which
reached no reader only because a declared correction outranks the offer.

A paragraph in the most expensive position in the prompt, plus its schema field
and its rule, is a large price for an offer that arrives once in 201 answers.
Both came out, and the tier that followed measured the loss: the article prose
names the commoner word on two of the three registered pairs — `casual` beside
`causal`, `wieder` beside `wider`, with `место` beside `месо` named by nothing.
That is more often than the field ever fired, and better: the previous tier's
prose named `weiter` for `wider`, the wrong word, while this one names the right
one. No ordinary word was told its spelling was wrong, and a non-empty
`suggestion` now appears only on a spelling the answer is correcting.

What is lost is real and bounded: the hint is a clause the reader has to notice
and retype, where the field was one tap. Nothing downstream ever depended on the
offer's presence, and the inverted-premise failure is now structurally
impossible.

A fixture instantiates this requirement only when the submission is wording the
answer will vouch for. One the standalone judgement refuses as unused never
reaches the branch that names a neighbour, and measures the refusal instead.

### Origin is asked for only where it is known, and that is not the fix

"Origin: always include it" was the suspected cause of confident invented
etymologies: told to supply one for every word, the answer supplies one for the
words that have none. The rule now asks for it only where the answer knows it and
says to leave it out rather than reason one out from a word's parts.

Measured over a full tier, that is not what invented etymology turns on. It does
stop an origin being manufactured for a shape that plainly has no history:
`blorptium` carries none, and the coinages that reached a reader carry a note on
how the suffix works rather than a past. Five unit articles omit the section
entirely where every article used to carry one, and origin on ordinary real words
is unchanged at eight of nine.

It does not stop a confident false etymology about a real, common word. Fresh
review read every origin in the tier: twenty were accurate, and the fabrications
are about words that exist — an invented Indo-European base meaning for `прозор`,
an invented narrative for `give up`. Two of them reach a reader. The rest of the
fabricated ones are withheld, and by the judgement rather than by this rule: an
answer that gives `vieleicht` an origin from Old High German `fior` "four" is
withheld because the wording was refused, not because it was asked to keep quiet.

So the rule is kept for what it does — an article about a shape with no history
no longer manufactures one — and credited with nothing else. What stands between
a learner and an invented etymology is the judgement, and reading the answers.
Nothing in the automated screen can see this: its origin count matches the word
"этимология", not the truth of the sentence around it.

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

### A dictionary is asked, and the reader is told rather than overruled

Neither model tier reaches "no card ever carries a word nobody says". Over the same
fixtures, six notes of 42 on the free pool and four of 42 on `gpt-fast` carry
something a learner would memorise wrong, and the class no model fixes is
well-formed nonsense carded with a confident sense. Requiring both models to vouch
buys nothing: both vouch for `bookshelfy` and both for `tablewards`, so the blind
spot is shared and agreement cannot separate a productive derivation from a word.

The lever is a source outside the models, and one exists. **Wiktionary covers
English, German and Serbian, free and without a key** — the source-language wiki
for what it has, the English one, which documents every language, for the rest;
present in either is present. Scored over every headword the two recorded tiers
would have carded, 31 free and 34 paid, exactly four are absent from both wikis:
`bookshelfy` and `змркалица`, both coinages that reach the reader; `водити рачуна`,
a real Serbian set expression neither wiki carries; and `das Fenster`, real and
present as `Fenster`, where the answer kept the article. One lookup is 183 ms at the
median against a 2.5 s answer.

**The check warns and never withholds.** Withholding on absence would refuse
`водити рачуна`, and the product's own rule is that a false refusal costs the reader
more than a warning they can act on. So where no wiki has the wording a note carries,
the entry says so in the terms that are true — a rare word, an unexpected form, or no
word at all. An unreachable Wiktionary is not a miss, on the same rule as the
judgement: silence is not an objection.

**And the question the warning raises is answered rather than described.** A
dictionary cannot settle whether a wording is used — it holds only what someone wrote
down, and no dictionary holds everything — so the reader is not sent back to the one
already asked. One control runs the search they would have run: how often the exact
wording occurs in the encyclopedia in that language, with the fragments that show it
in use.

Measured over the same fixtures, the count separates the two cases the dictionary
leaves open. Every invented wording occurs **nought** times — `bookshelfy`,
`tablewards`, `змркалица`, `Fahrradsuppe`. Every real one occurs at least six:
`Kummerspeck` 6, `сврака` 87, `Rad fahren` 100, `водити рачуна` 249 — which is the
dictionary check's own false alarm, rescued here — `petrichor` 147, and ordinary
colloquial wording in the hundreds or thousands in all three languages. Serbian is
the smallest of the three encyclopedias and still leaves that margin.

Nought occurrences and a failed lookup read alike to a reader and mean opposite
things, so a search that did not answer is never shown as one that found nothing.

The question is asked of the headword rather than the submission, because the
headword is what the note teaches. It is an existence check and nothing more: a
wrong gloss on a real word passes it untouched, and that class stays open.

### The verdict gate is read as it stands, never re-labelled to pass

Some counted hard errors card exactly the extraction their own fixture registers
as accepted, and behave identically to sibling fixtures the manifest already
lists as defensible; the difference between them is the registration, not the
answer. Re-labelling them would be an argued change to the manifest, and it is
never one to make in the same breath as accepting a feature the same run was
measuring — the party defending a result does not get to move the line it is
judged against. A manifest change is its own piece of work, argued on its own.

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

The reader has room for one piece of advice about their spelling, and only the
correction field carries one. It is a consistency boundary, not an independent
spelling judge: a model can still call a misspelling morphology, so registered
typo fixtures and fresh review remain required.

**A declared correction is wording nothing has vouched for yet.** The relation
`typo` is the one claim that replaces the submission with another word, and the
note is then about that other word. Where the judgement refused the submission,
the claim alone used to be enough to discard the refusal — so an answer that
"corrected" the coinage `змркалица` into `сумралица`, itself not a word, stored
four cards under the second invention and told the reader they had misspelled it.
Neither the card contract nor the screen could see it: the payload was clean, and
the arm counted the fixture as withheld. The correction is therefore put to the
same judgement, and the refusal stands unless that wording comes back used.

**What the answers are known to get wrong, and what no contract catches.** The
structural checks bind the shape of a note, never its content, so these are found
by reading answers and not by any gate. The product accepts these as the free
pool's own quality, measured and not hoped for; the fixtures and the mandatory
review stay because the numbers move with the prompt.

An article can invert the sense of the unit it heads — `Zeit haben` glossed "не
иметь времени", `wissen` glossed "не знаю". The cause is a branch call rather than
a translation slip: a clause the answer should have read as text is read as a unit,
and the answer then names the positive lemma while glossing the whole clause,
negation included. Where the branch is right no card is made and nothing is
inverted. The prompt therefore asks for the heading, the translations and the
examples to be about one and the same wording, and reads a clause with its own
subject and finite verb as text.

An article can state grammar that is simply false: a wrong case, an invented
pronoun form, `es` described as `er`. It can give a confident etymology for a word
that has none. It can put
a table on an invariable word or print a bare part of speech. A forms table naming
case, tense or person is the one of these the prompt now forbids in those words:
naming a grammatical category in a table fell from 26% to 11% of tables when the
rule was stated, measured over 139 tables before and 56 after.

These are article defects rather than card defects — the payload is usually clean
while the visible prose carries them — and the mandatory semantic review is the
only thing that sees them. Over a reviewed full tier, roughly half of a packet's
items carry a defect the reader would read and about a fifth one that reaches a
card they would drill. For an explicit context request, the selected meaning's
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
