# Phrases and sentences — decision

Status: **decided 2026-08-24 — a multi-word input is analysed whole and carded
when it is one unit, and produces no note when it is a use of one; running text
is translated and explained instead of being carded; the backend decides which
shape an input is.** This document records the benchmark
behind those defaults. Its harnesses are `experiments/backend_bench.py` with
`experiments/bench_items.py` and `experiments/route.py` for routing and sentence
mode, and `experiments/extract_bench.py` with `experiments/extract_items.py` and
`experiments/extract_prompts.py` for whether a multi-word input is a unit.

## The problem

Words do not always come one at a time. A collocation is a unit whose parts
cannot be looked up separately, because the mapping between languages is not
word-for-word: Russian «ездить на велосипеде» takes a preposition, German
`Rad fahren` and Serbian `voziti bicikl` take a bare object. Asking which of
those words the user meant has no good answer.

Running text is a second shape again. What the reader wants there is the
sentence rendered whole and the hard parts named — above all the units whose
pieces stand apart, which no amount of word-by-word lookup will reach: a German
separable prefix stranded at the clause end, a Serbian reflexive particle
sitting in second position far from its verb.

## What was measured

- **Routing**, without any model: 147 labelled inputs over German and Serbian —
  every benchmark word and collocation, every sentence fixture, plus an
  adversarial middle of clauses short enough to look like lexemes and fixed
  expressions long enough to look like clauses.
- **Sentence mode**, 21 sentences over the two languages, each carrying the
  units its answer is expected to surface, so the score is objective rather
  than a judge's opinion. The fixtures are graded: units torn apart in the
  surface, units merely inflected away from their dictionary form, and
  trap-free sentences that serve as the negative control.
- **The recovery path**, 32 fixed expressions pushed through the sentence
  prompt on purpose — the misroute this design has to survive.
- **Collocations as notes**, 16 non-idiomatic collocations through the
  vocabulary prompt.
- All of it on the free pool, paced as one person, under the production
  complete-answer budget. The Serbian set mixes both scripts.

## Multi-word input was never the model's problem

160 multi-word runs were already on record from the backend benchmark, all of
them idioms: the card contract came back clean on the paced pool in every
language. The 16 non-idiomatic collocations added here scored 16 of 16 usable
notes, formatting clean, the input echoed unchanged. German `Rad fahren` comes
back as a unit, with «ездить на велосипеде» as its first translation and the
compound-spelling trap named.

So the gap was never the model's willingness to treat a phrase as one thing.
It was that the interface refused to send one.

## Sentence mode: the pool is sufficient

21 sentences, German and Serbian, on the free pool:

| measure | result |
|---|---|
| suggested-unit payload valid | 100% |
| expected unit surfaced | 100% |
| expected unit offered first | 95% |
| suggested forms usable as a word | 100% |
| formatting clean, answer on target | 100% |
| trap-free sentence | 0 suggestions |
| whole answer, median / p90 | 1.2 s / 1.6 s |

Every torn-apart unit was found: `aufstehen` out of *steht … auf*, `ausfallen`
out of *fällt … aus*, `in Frage kommen` out of *kommt … in Frage*, `вратити се`
out of *се … вратио*, `јавити се` out of *ми се … јавио*. The negative control
is the result that matters most for the interface: on a sentence with nothing
hard in it the model returns nothing rather than padding the list, so the
suggestions are signal instead of decoration.

The one case not offered first was Serbian *Данас ми се уопште не иде на посао*,
where the model led with `ићи на посао` and put the impersonal reflexive second.
Both are worth a look; the order is a preference, not an error.

Latency is not a concern: a sentence answer is longer than a word answer and
still lands an order of magnitude inside the budget.

## Routing: the middle band is irreducible, and that is the finding

A sentence never becomes a note, so the router decides whether the deck is
touched at all. Its two errors are not symmetric, and the sweep over the
labelled fixtures separates them:

- Every sentence that arrives **looking like** a sentence — terminal or
  internal punctuation, or more than a handful of words — routes correctly at
  every setting. The path is never missed for text that reads as text.
- Every error in either direction lives in one band: two to five words, no
  punctuation. There, the two classes are indistinguishable by any surface
  signal. German `von Zeit zu Zeit` and `Ich habe keine Zeit` are the same
  length, the same shape, and opposite answers. No threshold separates them,
  and none is defensible over another on accuracy alone.

What settles it is the measured cost of each error. A fixed expression pushed
into sentence mode comes back as its own first suggestion in **28 of 29** cases,
so the recovery is one tap. A short clause pushed into lexeme mode becomes a
note fronted with something like *Ich habe keine Zeit* or *Не знам* — a
phrasebook card a learner would want. Neither error is expensive; both grow
expensive with length, which is the one thing the threshold does control.

So the boundary sits just above the longest fixed expressions that are common
in practice and just below the length at which a clause stops making a usable
card. Set lower, it taxes idioms — the app's whole subject — with an extra tap
each. Set higher, it starts carding throwaway sentences. The rule:

- A single word is always analysed as a word, whatever punctuation trails it.
- A comma, semicolon, colon or dash *inside* makes it running text. A mark that
  merely ends the input does not: within the band a trailing mark carries no
  information, because the selection an input was copied from carries the
  punctuation of the sentence it was cut from — the same reason a single word
  keeps its shape whatever trails it. Above the band the word count routes
  anyway, so nothing that reads as a sentence changes shape.
- Anything longer than the canonical-word limit is running text.
- More than four words is running text.
- Everything else is analysed whole, as one unit.

The single miss in the recovery arm is Serbian «не пада ми на памет», returned
as `не падати на памет`: the model gave the dictionary form rather than the
inflected one it was handed. As the front of a note that is the better of the
two.

## What a sentence answer is, and what it is not

- **A sentence never produces a note.** A whole clause on the front of a card
  is unreviewable, duplicate detection over it is meaningless — a paraphrase is
  a new card — and the reverse card would have to mask the entire sentence.
  The deck stays a dictionary.
- The answer is the text rendered whole in the target language, then a short
  list of what is hard **in this particular text**: a construction, the word
  order, a case or a mood, a set expression, a word that is not what it looks
  like. Not a word-by-word walk-through.
- Alongside it the backend returns the units worth learning whole, most useful
  first and few in number. Each carries the form a dictionary would list, how
  it actually appears in the text — with the pieces shown apart when they stand
  apart — and one line on why it is worth a look.
- **A suggested unit is one tap from being a canonical word**, so it is held to
  exactly the rule a typed word is held to, and one that would have been
  refused had the user typed it is dropped and never offered. This is the same
  guard the spelling suggestion already lives under, for the same reason.
- Tapping one is an ordinary submission of that unit, carrying the sentence as
  its context. The note it makes is fronted with the dictionary form, not with
  the sentence.

## The shape of the input is decided by the backend

Not by the app. The share-sheet path posts straight to the API, so a rule that
lived in the frontend would have to be written twice and would drift; today it
already is, and the iOS Shortcut carries a hand-built copy of the app's word
picker. With the decision behind the API that whole apparatus collapses into
posting the shared text.

The alternative — asking the user which shape they meant before answering — was
rejected. It charges a tap on every multi-word input, including the long pasted
prose where choosing from a dozen words is worst, to prevent errors that are
measurably cheap. Letting the model decide inside a single branching call was
rejected too: it doubles a prompt that Serbian already strains, it hands the
deck-safety decision to the model, and the shape stays unknown until the answer
finishes streaming.

## A Serbian artefact worth knowing about

One Serbian answer in 34 mixed both scripts inside a single word (*возiti*) and
leaked a Serbian word into the target-language prose. It stayed in the prose:
no card payload and no suggested unit was affected, and the word rule rejects a
mixed-script form anyway. It is consistent with the pool's known Serbian
weaknesses (`decision-llm-backend.md`) and is not a reason to move the language
to a metered backend.

## What would re-open this

- A revision of either prompt: these numbers are prompt-bound, and the
  sentence prompt in particular was measured in its first revision because the
  first revision passed.
- The pool's primary model changing: the whole sentence arm was answered by it,
  and the measured fallbacks are not equivalent.
- Suggested units turning out to be ignored in practice. The negative control
  says they are not padding, but only use says whether they are tapped.

The harness is outside CI, calls real models, and its paid phase spends real
money.


## A multi-word input is not always a unit

The router places an input in the unit band from punctuation and length, which
cannot separate a fixed expression from a fragment of a clause — that is this
document's own finding. What the router cannot decide, the answer can: the model
is asked whether the text it was given is itself a lexical unit or a use of one,
and answers under the headword it chose. The input echoed back means a unit; a
different headword means a use. Only a multi-word input is read this way: a
single word is a unit whatever headword the answer names, because an inflected
word is answered under the dictionary form the card contract asks for.

The measurement covers 81 inputs over English, German and Serbian in four
classes — units that must survive whole, fragments whose focus has to be found,
short clauses, and single-word controls — plus 22 inputs whose bare stem is a
real word of the language (`aufstehen`/`stehen`, `вратити се`/`вратити`), which
is what makes a lost prefix or reflexive particle invisible.

| | free pool | metered |
|---|---|---|
| a unit survives whole | 100% | 100% |
| a unit taken apart | **0%** | **0%** |
| a prefix or reflexive particle lost | — | **0%** |
| the focus of a fragment, offered first | 42% | 92% |
| the focus of a fragment, offered at all | **100%** | 96% |
| an ordinary single word left alone | 100% | 100% |

Two results decide the design. **A unit is never taken apart** — not once, on
either backend, in any language — so carding a multi-word input the model
answered under its own name is safe. And **the focus of a fragment is offered
somewhere in the answer every time on the free pool**, while it leads only two
times in five. So the answer offers its units and a tap chooses; ranking them
correctly is what a metered model would buy, and a tap already buys it.

Auto-carding the model's first choice was rejected on those numbers: at 42% it
would put a wrong note in the deck three times in five, and a wrong note that
looks right is the one error nothing downstream catches.

### What the decision is worth, measured on its own

The extraction numbers above say the model finds the unit. They do not say how
often the card decision that reads them lands, and the fixtures they were taken
over could not: every unit in them was handed over already in its dictionary
form, so the headword could always echo it. A reader types what they just read.
Twenty inputs that are one unit in a form no dictionary lists — `fährt Rad`,
`донео одлуку`, `пада ми на памет` — close that gap, on the free pool:

| | free pool |
|---|---|
| a unit typed inflected, carded whole | 89% |
| a fragment, carded whole | 50% |

Over 18 and 24 answers. The first number is what the decision costs a reader:
one unit in nine is withheld and has to be tapped for. The second is what it is
worth: half the fragments the branch exists to catch are carded whole anyway,
because the model answers under the input itself and the headword echoes. The
discrimination is real, and it is far weaker than the extraction numbers
suggest.

Asking the model for the unit's surface in the input — the field the
running-text prompt already carries, where it measured clean — was tried as the
way out and rejected. Worded as *the part of the input the unit occupies*, it
came back as the whole input for four fragments in five, which would card 82% of
them. Tightened to name only the unit's own words and to leave out every word
that is not part of it, it reached 89% of inflected units carded and 43% of
fragments: the headword test's own two numbers, within one item on samples this
size. It buys nothing measurable and costs a prompt revision, which moves every
other prompt-bound number in this document. The field is therefore not in the
shipped prompt; both wordings of it are kept in the harness as deltas against
that prompt, so the comparison can be run again. The four numbers above were
taken before the card catalogue joined the same prompt, and are bound to it as
it then stood.

A decision rule is read off an answer already recorded, so `extract_bench.py
replay` scores every rule over the whole corpus without a single call. Only a
change to what the prompt *asks for* has to be bought again, and `--resume` and
`--only-wrong` keep that to the items that actually discriminate.

What would re-open this: a revision of the vocabulary prompt, or the pool's
primary model changing. Both numbers are bound to the prompt that produced them.
