"""The vocabulary and running-text prompts, and the payloads their answers hide."""

import logging

from echo_words.card import CardParseError, ParsedCard, parse_card_payload
from echo_words.languages import Language
from echo_words.segments import Segment, SegmentParseError, parse_segments_payload

CARD_DELIMITER = "===CARD==="
# A rejected payload is logged whole because nothing else keeps it: the answer it
# came in is gone, and what the model got wrong is only visible here.
PAYLOAD_LOG_LIMIT = 2000

logger = logging.getLogger(__name__)

_PROMPT = """You are a vocabulary tutor. The word below is in {source_lang}. Analyse
this word or short phrase: {word}

WRITE YOUR ENTIRE ANSWER IN {target_lang}.
This is absolute. Every part of the answer — the translations, the labels,
the register marks, the usage notes, the origin, the explanations of the
examples — is written in {target_lang}, and in no other language. These
instructions are in English; that says nothing about the answer language.
Do not answer in English unless {target_lang} IS English. Do not answer in
{source_lang} unless {target_lang} IS {source_lang}. Two things, and only
these two, stay in {source_lang}: the headword itself and the example
sentences (each of which is followed by its {target_lang} translation).

{context_note}Be compact. No preamble, no closing remarks. {source_hints}
The order of the sections is fixed:

1. First line: the word being analysed, in bold.
2. The translations, and nothing in front of them. Most frequent in
   everyday speech first. NEVER name the part of speech — not here, not
   anywhere in the answer. A register mark (colloquial, formal, slang,
   vulgar) goes AFTER the translation it belongs to, and only where it
   changes how the word is used.
3. Forms — ONLY when this word actually changes shape in a way a learner
   has to recognise or produce. An adverb, a preposition, a particle, an
   invariable word and a fixed expression have none: for those, skip this
   section completely — no table, no heading, no remark about forms
   anywhere in the answer. When the word does change, give a table of at
   most six rows: first cell a short everyday phrase in {source_lang}
   using the form, second cell that phrase in {target_lang}.
   The phrases carry the grammar, so name no person, number, gender, case
   or tense — not inside the table, not on a line above or below it, not
   anywhere near it. No labels, no abbreviations, no gender note. Choose
   the forms that are irregular or that learners get wrong; leave out
   whatever follows the regular pattern. For a verb: the present forms
   whose stem changes, the past, and the participle. For a noun: the
   plural, and an article or ending that shows its gender. For an
   adjective: an irregular comparative.
4. Usage: typical collocations and prepositions, what it is confused
   with; countability where it matters.
5. Origin: if the word was borrowed, 1-3 sentences on which language it
   came from and how it travelled; for a native word, one line.
6. Examples: 2-4 short everyday sentences, each followed by its translation.

Give no phonetic transcription: pronunciation is delivered as audio.

The input is either one lexical unit, or a single unit shown with the
words around it. Decide which before you answer.
- If the input is one lexical unit — an idiom, a collocation, a phrasal or
  separable verb, a fixed expression — analyse it WHOLE. Never take it
  apart, and never analyse one of its words on its own.
- Otherwise the input is a use of one unit, given with its context.
  Analyse THAT unit, in the sense it carries here, and treat the rest of
  the input as context only.
The unit you analyse is the headword of the first line and the value of
the word field. Everything else in the answer is about that unit.
Do not substitute a different word. If it looks
like a typo, do not silently fix it:
The test for one unit: its meaning does not follow from its words taken
separately, or it is simply the fixed way the language says this. When the
test passes, the whole input is the unit — a verb's object, a preposition
the verb governs, an article inside a set phrase are PART of it, never
context around it. When in doubt, keep the input whole: a unit carded whole
is at worst too specific, while a unit taken apart is wrong.
When the test fails, find the focus: the one word or unit a learner would
have stopped at. Prefer the word carrying the meaning over grammar words;
prefer a word with several senses over a transparent one; never pick a
proper name, a number, or a word spelled nearly as in {target_lang}. If the
focus is a verb bound to a reflexive particle, a separable prefix or a
governed preposition, it is that whole verb in its dictionary form, never
the bare stem.
Give the SMALLEST form a dictionary would list on its own. A word that only
modifies is never part of the unit and is dropped, however natural it sounds
attached: degree adverbs and intensifiers, quantifiers, adverbs of time, and
an auxiliary carrying no meaning of its own. "very tired" is not a unit and
"tired" is; keep the modifier only when dropping it changes the meaning, as
in a set phrase whose parts have stopped meaning what they say. add one short line beginning with ✏️
and naming the likely intended spelling, and put that spelling in the
suggestion field of the card JSON. If there is no typo, suggestion is an
empty string.
If it is an idiom or a phrasal verb, explain both the literal and the
figurative sense and when it is used.
ALL EMPHASIS IS HTML. Use these tags and no others: <b> around the
headword, <i> around the {source_lang} example sentences and any
{source_lang} form quoted inside the text, and <table>, <tr> and <td> for
the forms section and nowhere else. No attributes on any tag. Emphasis
punctuation of any kind is forbidden — no markdown, no headings, no
bullet markers, no code fences.
The whole analysis: at most 3500 characters.

After the analysis output the line ===CARD=== exactly, and immediately
after it one line of JSON, with no commentary and no HTML tags inside the
values:
{{"word": "...", "suggestion": "...", "candidates": ["...", "..."],
 "cards": [{{"kind": "...", "sense": 0, "prompt": "..."}}],
 "meanings": [{{"label": "...", "translations": ["...", "..."],
 "examples": [{{"text": "...", "translation": "..."}}]}}]}}
word — the unit you analysed, in the form a dictionary lists it and the way
it would be typed into a search box: letters, spaces, hyphens and
apostrophes only, in the same script as the input. It is the whole input
when the input was itself one unit, and the unit you found inside it
otherwise. suggestion — the
likely intended spelling of a typo, or an empty string.
candidates — every unit of the input worth looking up on its own, most
useful first, at most three, each in the dictionary form the word field is
held to, and each able to stand as a headword alone. The first is always
identical to word. When the input was itself one unit, candidates holds
that one unit and nothing else.
Order them by what the learner most likely did not know and put that one
first. Never lead with the input restated.

cards — the review cards this entry is worth beyond the two it always makes,
most often an empty list. Each element names one kind and carries only what
that kind needs:
{{"kind": "context", "sense": 0}} — the context you were given settles which
sense is meant, so a card fronted with that context is worth reviewing. sense
is the index into meanings, counting from zero, of the sense used there.
{{"kind": "context_production", "prompt": "..."}} — that same context is worth
producing and not merely recognising. prompt is the whole context rendered in
{target_lang}; without it the card asks nothing.
{{"kind": "split_recall"}} — the senses are so unrelated that one card asking
for all of them at once cannot be answered, so each should be asked for on its
own. Only ever when meanings holds more than one element.
Emit either context kind ONLY when the context actually pins down a sense the
bare word would leave open. A context in which the word means exactly what it
always means adds nothing to the word, and gets NO card — that is the normal
case, and an empty list is the right answer for it. When you were given no
context at all, neither context kind may appear.

meanings normally holds one element with an empty label. Split it into
several (at most three) only when the senses are genuinely unrelated (like
bank "financial institution" and bank "river edge"); then label is a
1-3 word tag in {target_lang} telling the senses apart.
translations — the 2-4 main {target_lang} translations of that sense;
examples — the 1-2 shortest examples of that very sense: text is a
sentence in {source_lang}, translation is its rendering in {target_lang}.
In at least one example per sense, use the headword in exactly the form it
was given, unless that makes the sentence unnatural.

Before you answer, check two things once more. Is every word of it in
{target_lang}, except the headword and the {source_lang} example sentences?
And is every emphasis an HTML tag, with no punctuation used for emphasis
anywhere?
"""

_TEXT_PROMPT = """You are a language tutor. The text below is in {source_lang}. It is running
text — a sentence or a fragment of one — and not a dictionary entry: {word}

WRITE YOUR ENTIRE ANSWER IN {target_lang}.
This is absolute. Every part of the answer — the translation, the notes, the
explanations — is written in {target_lang}, and in no other language. These
instructions are in English; that says nothing about the answer language. Do
not answer in English unless {target_lang} IS English. Do not answer in
{source_lang} unless {target_lang} IS {source_lang}. One thing only stays in
{source_lang}: the words and phrases you quote from the text itself.

{source_hints}Be compact. No preamble, no closing remarks.
The order of the sections is fixed:

1. A natural translation of the whole text into {target_lang}. One paragraph,
   reading as {target_lang} rather than as a gloss of the original.
2. What is hard here: 2-5 short notes, each on one thing a learner of
   {source_lang} would stumble over in this very text — a construction, the
   word order, a case or a mood, a set expression, a word that does not mean
   what it looks like. Say what the difficulty is, not what the word means.
   Leave out everything that is plain, and do not walk through the text word
   by word.

Give no phonetic transcription.
ALL EMPHASIS IS HTML. Use exactly two tags and no others: <i> around anything
quoted from the text in {source_lang}, <b> around a term you are naming.
Emphasis punctuation of any kind is forbidden — no markdown, no headings, no
bullet markers, no tables, no code fences.
The whole answer: at most 3500 characters.

After the answer output the line ===CARD=== exactly, and immediately after it
one line of JSON, with no commentary and no HTML tags inside the values:
{{"segments": [{{"label": "...", "surface": "...", "why": "..."}}]}}

segments — the units of this text that are worth learning whole and looking up
on their own, at most five, the most useful first. A unit qualifies when its
meaning does not follow from its words taken one at a time, or when its parts
stand apart in the text so that neither part can be looked up alone: a verb
with a separable prefix, a verb bound to a reflexive particle, a verb bound to
a preposition or to a case, a set expression. A single ordinary word never
qualifies.
label — the unit's dictionary form in {source_lang}, written the way a
dictionary lists it and the way it would be typed into a search box: letters,
spaces, hyphens and apostrophes, nothing else, and in the same script as the
text you were given.
surface — the unit as it actually stands in this text, in {source_lang}; when
its parts stand apart, give them in the order they appear, joined by a space,
an ellipsis character and a space.
why — one short line in {target_lang} saying what makes the unit worth a look.
If the text you were given is itself one such unit and not a sentence, return
exactly one segment, whose label is that unit in its dictionary form.
If nothing in the text qualifies, return an empty list.
"""

_CONTEXT_NOTE = """The word was met in this context: "{context}"
Analyse the sense in which it is used there. If that sense is rare,
domain-specific or not recorded in dictionaries at all, say so plainly and
explain that sense — do not substitute the nearest dictionary meaning.

"""

_EXTENDED_PROMPT = """You are a lexicographer. The word below is in {source_lang}. Analyse this
word or short phrase in depth: {word}

WRITE YOUR ENTIRE ANSWER IN {target_lang}, and in no other language. These
instructions are in English; that says nothing about the answer language.
Only the headword and the example sentences stay in {source_lang}, and
every example is followed by its {target_lang} translation.

{context_note}The reader has already seen the short entry, so do not skimp
on detail — but stay on the point in every section.

1. First line: the word being analysed, in bold.
2. EVERY sense, not only the frequent ones: figurative, domain-specific,
   archaic, regional and slang alike. For each, the part of speech, the
   register mark, and the field it belongs to. If a sense lives only in a
   particular domain (law, medicine, sport, jargon), name that domain.
3. Origin, in depth: the source language, the original form and meaning,
   the route the word travelled, when it entered the language, related
   words within the language and cognates elsewhere. For a native word,
   the root and how it developed. Where the etymology is disputed, give
   the competing accounts.
4. Usage: set phrases, government, register, what it is confused with,
   false friends, the mistakes learners typically make.
5. Shades and near-synonyms: how it differs from them and which is apt
   where.
6. Examples: one or two per sense from section 2, each followed by its
   translation.

For emphasis use ONLY the HTML tags <b> and <i>: the headword in bold, the
{source_lang} examples in italics. No markdown, no other tags. Give no
phonetic transcription. No JSON and no delimiters of any kind — this is
reading matter only.
"""


def build_prompt(language: Language, word: str, target_lang: str, *, context: str = "") -> str:
    """Build the compact analysis prompt."""
    context_note = _CONTEXT_NOTE.format(context=context) if context else ""
    return _PROMPT.format(
        source_lang=language.name,
        target_lang=target_lang,
        source_hints=language.prompt_hints or "",
        word=word,
        context_note=context_note,
    )


def build_text_prompt(language: Language, text: str, target_lang: str) -> str:
    """Build the running-text prompt: a translation, what is hard, and the units to look up."""
    return _TEXT_PROMPT.format(
        source_lang=language.name,
        target_lang=target_lang,
        source_hints=language.prompt_hints or "",
        word=text,
    )


def build_extended_prompt(
    language: Language,
    word: str,
    target_lang: str,
    *,
    context: str = "",
) -> str:
    """Build the card-free, paid deeper-analysis prompt."""
    context_note = _CONTEXT_NOTE.format(context=context) if context else ""
    return _EXTENDED_PROMPT.format(
        source_lang=language.name,
        target_lang=target_lang,
        word=word,
        context_note=context_note,
    )


def extract_card(raw: str, word: str, language: Language) -> ParsedCard | None:
    """Extract and validate the hidden card block, returning ``None`` when it is unusable."""
    delimiter_at = raw.find(CARD_DELIMITER)
    if delimiter_at < 0:
        logger.warning(
            "no card block for %s/%r: the answer never wrote the delimiter",
            language.code,
            word,
        )
        return None
    payload = raw[delimiter_at + len(CARD_DELIMITER) :]
    try:
        return parse_card_payload(payload, word, language)
    except CardParseError as exc:
        logger.warning(
            "unusable card block for %s/%r: %s; payload %s",
            language.code,
            word,
            exc,
            _logged(payload),
        )
        return None


def extract_segments(raw: str, language: Language) -> list[Segment] | None:
    """Extract the suggested units, returning ``None`` when the payload is unusable."""
    delimiter_at = raw.find(CARD_DELIMITER)
    if delimiter_at < 0:
        logger.warning(
            "no segments block for %s: the answer never wrote the delimiter",
            language.code,
        )
        return None
    payload = raw[delimiter_at + len(CARD_DELIMITER) :]
    try:
        return parse_segments_payload(payload, language)
    except SegmentParseError as exc:
        logger.warning(
            "unusable segments block for %s: %s; payload %s",
            language.code,
            exc,
            _logged(payload),
        )
        return None


def _logged(payload: str) -> str:
    payload = payload.strip()
    if len(payload) <= PAYLOAD_LOG_LIMIT:
        return repr(payload)
    return f"{payload[:PAYLOAD_LOG_LIMIT]!r} … ({len(payload)} chars)"
