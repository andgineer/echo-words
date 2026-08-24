# The shape of an answer — decision

Status: **decided 2026-08-24 — the answer opens on the meaning, never names a
part of speech, and shows how a word inflects as a table of live phrases when
and only when the word inflects.** The harness is `experiments/forms_bench.py`,
with `experiments/forms_items.py` and `experiments/forms_prompts.py`.

## The problem

An answer that opened `наречие, разговорное: позавчера` made the reader work
past two pieces of metadata to reach the one thing they asked for. The part of
speech is the worse of the two: a reader who typed a word can see it is an
adverb, and the label earns none of the space it takes at the top.

The forms are the opposite case — genuinely wanted and genuinely absent. What a
learner of German needs from `nehmen` is that the vowel changes in `du nimmst`,
and what they need from an English irregular verb is `brought`, not `bringed`.
Naming those forms in grammatical terms («третье лицо множественное число»)
delivers the label instead of the knowledge: the phrase teaches, the term does
not.

## What the answer does

- The translations come first, with nothing in front of them. A register mark
  follows the translation it belongs to, where it changes how the word is used.
- The part of speech is never named anywhere.
- A **forms** section appears only when the word changes shape in a way the
  reader must recognise or produce, and is a table whose cells are short
  everyday phrases with their translations. No person, number, gender, case or
  tense is named — not inside the table, not beside it. Invariable words get no
  table at all.
- The answer may therefore use `<table>`, `<tr>` and `<td>` alongside `<b>` and
  `<i>`. No tag ever carries an attribute; the sanitizer matches whole literals,
  so the answer has no way to express one.

## What was measured

29 inputs over English, German and Serbian: 22 whose informative forms are
recorded exactly, and 7 invariable words that must produce no table. Each of the
22 also names its **trap** — the regularised shape a model invents when it does
not know (`bekommte`, `childs`, `човеци`) — because a wrong form is the one part
of the answer the reader cannot check, having asked precisely because they did
not know it.

| | free pool | metered |
|---|---|---|
| a table when the word inflects | 100% | 100% |
| informative forms present | 94% | 98% |
| every informative form present | 89% | 95% |
| **an invented form** | **0** | **0** |
| a table where there should be none | 0% | 0% |
| a part of speech leading the answer | 4% | 3% |
| a tag or attribute outside the allowed set | 0 | 0 |
| whole answer, median | 1.6 s | 19.8 s |

**No invented form appeared on either backend.** The pool's documented weakness
is morphology (`decision-llm-backend.md`), and it shows here as *fewer* forms
rather than *wrong* ones: a thin table is visible and harmless, an invented one
is neither. Twelve times the latency buys six points of completeness and no
correctness, so the free pool serves this section like every other.

## What would re-open this

A revision of the vocabulary prompt, or the pool's primary model changing. One
known residue: on the pool a table row is occasionally filler rather than a form
of the word asked about, which the fixtures do not detect — they check that the
informative forms are present, not that every row earns its place.
