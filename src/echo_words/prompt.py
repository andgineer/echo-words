"""The merged language-analysis prompt and its hidden structured answer."""

import logging

from echo_words.card import CardParseError, ParsedAnswer, parse_answer_payload
from echo_words.languages import Language

CARD_DELIMITER = "===CARD==="
PAYLOAD_LOG_LIMIT = 2000
MAX_COMPLETE_ANSWER_CHARS = 16_000

logger = logging.getLogger(__name__)

_PROMPT = """You are a language tutor. The request below concerns {source_lang}.

{request}

WRITE YOUR ENTIRE ANSWER IN {target_lang}. Explanations, translations, sense
labels, usage notes, origin and reasons are in {target_lang}. Only a headword,
quoted source text and source-language examples stay in {source_lang}.
{source_hints}

First decide whether the submission is ONE LEXICAL UNIT WORTH LEARNING WHOLE or
text containing units. A single source word is a unit, and so is a multi-word
expression whose whole wording is the reusable lookup target: an idiom,
collocation, phrasal or separable verb or conventional formula. Its dictionary
form may differ from the submitted one and its pieces may stand apart. Anything
that reports a particular situation is text, even when a fixed expression fills
most of it — return that expression separately in combinations rather than making
its changing context part of a dictionary entry. If uncertain, choose text.
{intent_rule}

For a unit, write a complete compact dictionary article in this order:
1. Begin with the unit heading in <b> tags, using the dictionary lemma; when you
   suspect a misspelling, head the article with the submitted spelling instead.
2. Give the translations, most frequent in everyday speech first. Never name the
   part of speech. Put a register mark after the translation it qualifies.
3. Forms only when useful to recognise or produce. Use a table of at most six
   rows, each with a short {source_lang} form or phrase and its {target_lang}
   rendering. Skip forms completely for invariable words and fixed expressions.
4. Usage: collocations, governed prepositions, confusions, register and
   countability where relevant.
5. Origin: always include it; 1-3 sentences for a borrowing, one compact line for
   a native word.
6. Give 2-4 short everyday examples with translations.
For a set expression, also explain what its parts contribute and why the whole
means what it does. With supplied context, lead with the sense used there but
keep all other senses below it.

For text, begin with a natural translation of the whole submitted text. Then give
2-5 compact notes about genuinely difficult constructions, word order, forms,
set expressions or meanings. Do not write a dictionary entry about one selected
word.

No phonetic transcription. Use only <b>, <i>, <table>, <tr>, and <td>, with no
attributes; tables are only for forms. No Markdown emphasis, headings, code
fences, preamble or closing remarks. The article is at most 3500 characters.

After the article output ===CARD=== on its own line, followed immediately by one
line of JSON matching ONE of these neutral schematic branches. Angle-bracketed
values are placeholders, not strings to copy:

{{"kind": "unit", "word": "<dictionary lemma of the unit>",
 "word_relation": "<same, morphology or typo>",
 "suggestion": "<corrected spelling, or empty>",
 "meanings": [{{"label": "<short target-language sense label or empty>",
 "translations": ["<target-language translation>"],
 "examples": [{{"highlighted": "<short source-language sentence, unit in b tags>",
 "translation": "<target-language translation>"}}]}}],
 "segments": [{{"label": "<component dictionary form>",
 "surface": "<component form seen in the expression>",
 "why": "<short target-language reason>"}}]{context_field}}}

OR

{{"kind": "text", "combinations": [{{"label": "<dictionary form of the unit>",
 "surface": "<the same unit as the text spells it>",
 "why": "<short target-language reason>"}}]}}

word_relation is typo when the submission is misspelled, and then suggestion holds
the correct spelling; morphology when word is a different dictionary form of a
correctly spelled submission; same when word is the submission itself. suggestion
is empty unless the relation is typo.

meanings are the senses that need different words in {target_lang}, most common
first; do not impose a numerical limit. Every meaning has 2-4 main translations
and 1-2 examples. When several meanings remain, every label is a short
{target_lang} tag distinguishing them; for one meaning its label is empty.
Each highlighted example is a whole sentence carrying <b> tags around all and
only the unit, since it becomes the front of a card. Mark a contiguous unit with
one span and separated or reflexive pieces with one span each, in their original
positions. Never mark a subject, object, auxiliary or argument merely because it
occurs with the unit, and always leave at least one unmarked source-language word
in the sentence. {context_rule}

For a multi-word set expression, segments contains every word-shaped component,
including particles and prepositions, with no count cap. Preserve the forms seen
in the submitted expression. Do not repeat the whole expression as a component.

For text, put every clear multi-word lookup target in combinations, even when one
accounts for most of the utterance. It qualifies when its meaning does not follow
from its words one at a time, or when its lexical pieces stand apart so no piece
can be looked up alone: a separable or reflexive verb, governed combination,
collocation or set expression. A single ordinary word and an arbitrary tense,
negation or current argument do not qualify. Keep distinct non-overlapping units
separate. Return every clear unit, do not pad the list, and use an empty list when
nothing qualifies.

label and surface are the same unit twice: label is its dictionary form, and
surface holds its lexical pieces copied token for token out of the submitted
text, in the same spelling, script and capitalization and in source order, with
an ellipsis joining pieces which stand apart. So label may read `aufstehen`
while surface reads `steht ... auf`. Copy surface out of the sentence: never
translate, transliterate, correct or lemmatise it. Include every fixed piece —
reflexive particle, separable particle, governed preposition, support verb — in
the form it takes in this sentence, and leave out negation and the current
subject, object or complement. Do not enumerate ordinary words: the backend
gives every source word its own chip anyway. Text JSON contains no word,
meanings, segments or other card fields.

Check before answering that the JSON is valid, with every string in double
quotes, and that a unit article begins with the bold heading its word names.
"""

_UNIT_INTENT = "The learner explicitly selected a unit, so kind must be unit."
_OPEN_INTENT = "For this submit-box request, choose the branch yourself."
# Appended to the intent line rather than placed on its own, so the prompt every
# other request sends stays byte for byte what the benchmark measured.
_CONFIRMED_SPELLING = (
    "The learner has confirmed this spelling deliberately, so treat it as correct: "
    "analyse exactly the submitted spelling, copy it into word unchanged, set "
    "word_relation to same, leave suggestion empty, and spell it that way in every "
    "example and heading."
)
_CONTEXT_RULE = (
    "Use the supplied context as the first example of its sense and include "
    '"context_sense": <zero-based index> in the unit object. In that example, '
    "copy the submitted selected-unit surface exactly, mark those selected "
    "tokens and no others, and do not expand the selection to neighbouring context."
)
_NO_CONTEXT_RULE = "Do not add a field selecting a contextual sense."

_EXTENDED_PROMPT = """You are a lexicographer. The word below is in {source_lang}.
Analyse it in depth: {word}

WRITE YOUR ENTIRE ANSWER IN {target_lang}, and in no other language. Only the
headword and example sentences stay in {source_lang}, and every example is
followed by its {target_lang} translation.

{context_note}The reader has already seen the short entry. Cover every sense,
including domain-specific, archaic, regional and slang senses; origin and its
route in depth; usage and common mistakes; shades and near-synonyms; and one or
two examples per sense. Use only <b> and <i>, no Markdown. Give no phonetic
transcription, JSON or delimiters.
"""


def build_prompt(  # noqa: PLR0913 - one prompt, and every switch that varies it.
    language: Language,
    word: str,
    target_lang: str,
    *,
    context: str = "",
    unit_intent: bool = False,
    spelling_confirmed: bool = False,
) -> str:
    """Build the sole compact prompt; only the request intent varies."""
    request = (
        f'Make a card for this selected unit: "{word}"\nContext: "{context}"'
        if unit_intent and context
        else f'Make a card for this selected unit: "{word}"'
        if unit_intent
        else f'Analyse this submitted text: "{word}"'
    )
    context_field = ', "context_sense": <zero-based index>' if context else ""
    intent_rule = _UNIT_INTENT if unit_intent else _OPEN_INTENT
    if spelling_confirmed:
        intent_rule = f"{intent_rule} {_CONFIRMED_SPELLING}"
    return _PROMPT.format(
        source_lang=language.name,
        target_lang=target_lang,
        source_hints=language.prompt_hints or "",
        request=request,
        intent_rule=intent_rule,
        context_field=context_field,
        context_rule=_CONTEXT_RULE if context else _NO_CONTEXT_RULE,
    )


def build_extended_prompt(
    language: Language,
    word: str,
    target_lang: str,
    *,
    context: str = "",
) -> str:
    """Build the card-free paid deeper-analysis prompt."""
    context_note = f'The word was met in this context: "{context}"\n' if context else ""
    return _EXTENDED_PROMPT.format(
        source_lang=language.name,
        target_lang=target_lang,
        word=word,
        context_note=context_note,
    )


def extract_answer(
    raw: str,
    submitted: str,
    language: Language,
    *,
    unit_intent: bool = False,
    context: str = "",
) -> ParsedAnswer | None:
    """Extract and validate the hidden answer, returning None when unusable."""
    if len(raw) > MAX_COMPLETE_ANSWER_CHARS:
        logger.warning(
            "oversized answer for %s/%r: %s characters exceeds the %s-character bound",
            language.code,
            submitted,
            len(raw),
            MAX_COMPLETE_ANSWER_CHARS,
        )
        return None
    delimiter_at = raw.find(CARD_DELIMITER)
    if delimiter_at < 0:
        logger.warning(
            "no answer block for %s/%r: the answer never wrote the delimiter",
            language.code,
            submitted,
        )
        return None
    payload = raw[delimiter_at + len(CARD_DELIMITER) :]
    try:
        return parse_answer_payload(
            payload,
            submitted,
            language,
            unit_intent=unit_intent,
            context=context,
        )
    except CardParseError as exc:
        logger.warning(
            "unusable answer block for %s/%r: %s; payload %s",
            language.code,
            submitted,
            exc,
            _logged(payload),
        )
        return None


def _logged(payload: str) -> str:
    payload = payload.strip()
    if len(payload) <= PAYLOAD_LOG_LIMIT:
        return repr(payload)
    return f"{payload[:PAYLOAD_LOG_LIMIT]!r} … ({len(payload)} chars)"
