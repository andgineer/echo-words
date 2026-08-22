"""The vocabulary and running-text prompts, and the payloads their answers hide."""

from echo_words.card import CardParseError, ParsedCard, parse_card_payload
from echo_words.languages import Language
from echo_words.segments import Segment, SegmentParseError, parse_segments_payload

CARD_DELIMITER = "===CARD==="

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
2. Translations, most frequent in everyday speech first; each with its
   part of speech and a register mark (colloquial, formal, slang, vulgar
   and so on) where it matters.
3. Usage: typical collocations and prepositions, what it is confused
   with; countability and irregular forms where they matter.
4. Origin: if the word was borrowed, 1-3 sentences on which language it
   came from and how it travelled; for a native word, one line.
5. Examples: 2-4 short everyday sentences, each followed by its translation.

Give no phonetic transcription: pronunciation is delivered as audio.

Analyse EXACTLY the word given and do NOT substitute another. If it looks
like a typo, do not silently fix it: add one short line beginning with ✏️
and naming the likely intended spelling, and put that spelling in the
suggestion field of the card JSON. If there is no typo, suggestion is an
empty string.
If it is an idiom or a phrasal verb, explain both the literal and the
figurative sense and when it is used.
ALL EMPHASIS IS HTML. Use exactly two tags and no others: <b> around the
headword, <i> around the {source_lang} example sentences and any
{source_lang} form quoted inside the text. Emphasis punctuation of any
kind is forbidden — no markdown, no headings, no bullet markers, no
tables, no code fences.
The whole analysis: at most 3500 characters.

After the analysis output the line ===CARD=== exactly, and immediately
after it one line of JSON, with no commentary and no HTML tags inside the
values:
{{"word": "...", "suggestion": "...",
 "meanings": [{{"label": "...", "pos": "...", "translations": ["...", "..."],
 "examples": [{{"text": "...", "translation": "..."}}]}}]}}
word — the input word exactly as given (never corrected); suggestion — the
likely intended spelling of a typo, or an empty string.
meanings normally holds one element with an empty label. Split it into
several (at most three) only when the senses are genuinely unrelated (like
bank "financial institution" and bank "river edge"); then label is a
1-3 word tag in {target_lang} telling the senses apart. pos is that
sense's part of speech as one short abbreviation in {target_lang}.
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
        return None
    payload = raw[delimiter_at + len(CARD_DELIMITER) :]
    try:
        return parse_card_payload(payload, word, language)
    except CardParseError:
        return None


def extract_segments(raw: str, language: Language) -> list[Segment] | None:
    """Extract the suggested units, returning ``None`` when the payload is unusable."""
    delimiter_at = raw.find(CARD_DELIMITER)
    if delimiter_at < 0:
        return None
    payload = raw[delimiter_at + len(CARD_DELIMITER) :]
    try:
        return parse_segments_payload(payload, language)
    except SegmentParseError:
        return None
