"""Merged-prompt candidates for the unit-verdict gate.

Every variant is derived from the same template. The only delta in ``v1`` is
the JSON schema's boolean placeholder: ``v0`` shows the literal ``true`` that
the first scratch run showed, while ``v1`` makes the model supply the value.
"""

import hashlib


_TEMPLATE = """You are a language tutor. The request below concerns {source_lang}.

Request: {request}

WRITE YOUR ENTIRE ANSWER IN {target_lang}.
This is absolute. Explanations, translations, labels, register marks, usage
notes, origin and the reasons attached to suggestions are in {target_lang}.
The headword, quoted source text and source-language examples stay in
{source_lang}. These instructions being English says nothing about the answer
language. {source_hints}

First decide whether the submitted text is ONE LEXICAL UNIT WORTH PUTTING ON A
CARD WHOLE.

A unit may be one word or several: an idiom, collocation, phrasal or separable
verb, fixed expression, or simply the conventional way {source_lang} says
something. Its dictionary form may differ from the submitted inflected form.
Its words may stand apart in the submitted text. A phrase is still one unit
when dropping its object, governed preposition, reflexive particle, article or
other fixed part changes what has to be learned.

A sentence, clause, or fragment with context around a unit is NOT one unit.
This remains true when it is short, has no punctuation, has an implicit subject,
or happens to consist only of an inflected verb phrase. If the text asserts,
asks, commands or reports something about a particular situation, it is a
clause, not a dictionary entry. Do not turn such a text into a card by choosing
one focus from it. Instead explain the whole text and return its learnable units
and ordinary content words as suggestions. A fixed greeting or other expression
normally learned and reused whole is a unit, not a clause.

For an "analyse this text" request, decide from the submitted text itself. No
context was supplied. For a "make a card" request, the unit has already been
chosen: make its card using the supplied context and do not reverse that choice.

The article has one of two shapes, chosen by that same decision:

- For a unit, begin with the dictionary headword in <b> tags. Then give its
  translations, forms only when useful, usage, origin, and 2-4 short everyday
  examples. For a set expression, also explain what its parts contribute and why
  the whole has its meaning.
- For text with units inside it, begin with a natural translation of the whole
  submitted text. Then give 2-5 compact notes about the constructions, word
  order, forms, or meanings that are genuinely difficult in this text. Do not
  begin with a bold source-language headword and do not write an entry about one
  word selected from the text.

No phonetic transcription. Use only <b>, <i>, <table>, <tr>, and <td>, with no
attributes. Use tables only for forms. No Markdown, headings, bullets, code
fences, preamble, or closing remarks. The article is at most 3500 characters.

After the article output ===CARD=== on its own line, followed immediately by one
line of JSON matching this schematic shape. Angle-bracketed values are
placeholders, not strings to copy:

{{"unit": __UNIT_VALUE__, "word": "<dictionary headword or empty>",
 "suggestion": "<likely typo correction or empty>",
 "meanings": [{{"label": "<short target-language sense label or empty>",
 "translations": ["<target-language translation>"],
 "examples": [{{"text": "<source-language sentence>",
 "translation": "<target-language translation>",
 "highlighted": "<the complete sentence with every surface part of the unit in b tags>",
 "gapped": "<the complete sentence with every surface part of the unit replaced by ___>"}}]}}],
 "segments": [{{"label": "<dictionary form>", "surface": "<form in the submitted text>",
 "context": "<the sentence a tap must send>", "why": "<short target-language reason>"}}]}}

The fields obey these rules:

unit — a JSON boolean. It is true exactly for one lexical unit worth carding
whole. It is false for a sentence, clause, or fragment with units inside it.

word — for a unit, its dictionary form in the source language and script. For
non-unit text, an empty string. Never put a focus chosen from a clause here.

meanings — for a unit, the senses that need different words in {target_lang},
most common first. It is empty for non-unit text. Every meaning has 2-4 main
translations and 1-2 short examples of exactly that sense. When there is more
than one meaning, every label is a short {target_lang} tag distinguishing it;
when there is one, its label is empty. Every highlighted and gapped value is a
finished string ready to print. Preserve the complete sentence. Mark or gap all
parts of a separable or reflexive unit, wherever they stand.

segments — for non-unit text, every useful lexical unit and ordinary content
word a learner may tap, most useful first, at most five. Each carries the entire
submitted text as context. For a multi-word set expression that is itself a
unit, segments instead contains the individual content words worth looking up;
for a single word it is empty. Never repeat the whole expression as its own
component.

context_sense — include this extra integer field ONLY for a "make a card"
request with supplied context. It is the zero-based index into meanings of the
sense used in that context. Never include it for "analyse this text".

Before answering, reconcile the article and JSON: a unit article begins with
the bold headword and has unit true; a whole-text translation has unit false,
an empty word and empty meanings. Never describe one branch and encode the
other.
"""


_SAFETY_ANCHOR = """For an \"analyse this text\" request, decide from the submitted text itself. No
context was supplied."""

_SAFETY_RULE = """Use the safe direction when the surface is ambiguous. If any word is merely
context around the learnable unit — a degree or time adverb, an auxiliary, a
subject, or an argument that is not fixed — unit is false. Inflection alone does
not make context: when every content word belongs to one reusable expression and
there is no contextual material around it, an inflected form may still be that
unit. If you choose false for text that could itself be learned whole, put that
whole expression's clean dictionary form first in segments, with no grammar
labels or parenthetical notes, so one tap recovers it.

For an \"analyse this text\" request, decide from the submitted text itself. No
context was supplied."""


VARIANTS = {
    "v0": ("literal true in the JSON schematic", "true", []),
    "v1": ("neutral boolean placeholder", "<boolean decided above>", []),
    "v2": (
        "v1 + safe tie-break and first-chip recovery",
        "<boolean decided above>",
        [(_SAFETY_ANCHOR, _SAFETY_RULE)],
    ),
}


def build(variant: str) -> str:
    if variant not in VARIANTS:
        raise SystemExit(f"unknown variant {variant!r}; expected one of {sorted(VARIANTS)}")
    text = _TEMPLATE.replace("__UNIT_VALUE__", VARIANTS[variant][1], 1)
    for anchor, replacement in VARIANTS[variant][2]:
        if anchor not in text:
            raise RuntimeError(f"{variant}: prompt anchor did not match:\n{anchor}")
        text = text.replace(anchor, replacement, 1)
    return text


def fingerprint(variant: str) -> str:
    return hashlib.sha256(build(variant).encode()).hexdigest()[:12]
