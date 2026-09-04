"""The two language-analysis prompts and their hidden structured answer.

The unit prompt answers a request whose branch the learner's own action already
settled; the submit box, where it has not, gets the prompt that carries both
branches and decides between them.
"""

import json
import logging
from dataclasses import dataclass

from echo_words.card import CardParseError, ParsedAnswer, parse_answer_payload
from echo_words.languages import DEFAULT_TARGET_LANGUAGE, Language

CARD_DELIMITER = "===CARD==="
PAYLOAD_LOG_LIMIT = 2000
MAX_COMPLETE_ANSWER_CHARS = 16_000

logger = logging.getLogger(__name__)

_INTRO = """You are a language tutor. The request below concerns {source_lang}.

{request}

WRITE YOUR ENTIRE ANSWER IN {target_lang}. Explanations, translations, sense
labels, usage notes, origin and reasons are in {target_lang}. Only a headword,
quoted source text and source-language examples stay in {source_lang}.
{source_hints}"""

_BRANCH = """First decide whether the submission is ONE LEXICAL UNIT WORTH LEARNING WHOLE or
text containing units. A single source word is a unit, and so is a multi-word
expression whose whole wording is the reusable lookup target: an idiom,
collocation, phrasal or separable verb or conventional formula. Its dictionary
form may differ from the submitted one and its pieces may stand apart. Anything
that reports a particular situation is text, even when a fixed expression fills
most of it — return that expression separately in combinations rather than making
its changing context part of a dictionary entry. A clause with its own subject and
finite verb reports a situation however ordinary a thing it is to say, so it is
text too. If uncertain, choose text."""

_ARTICLE_RULES = """1. Begin with the unit heading in <b> tags, using the dictionary lemma, which is
   also what goes in word; head a suspected misspelling with the correction, never
   with the submitted spelling.
2. Give the translations, most frequent in everyday speech first. Never name the
   part of speech. Put a register mark after the translation it qualifies.
3. Forms only when useful to recognise or produce. Use a table of at most six
   rows, each with a short {source_lang} form or phrase and its {target_lang}
   rendering. Name no grammatical category in it — no case, tense, person,
   number, gender or part of speech — because the phrase carries the grammar.
   Skip forms completely for invariable words and fixed expressions.
4. Usage: collocations, governed prepositions, confusions, register and
   countability where relevant.
5. Origin only where you know it: 1-3 sentences for a borrowing, one compact line
   for a native word. Where you do not, leave it out — an origin reasoned out from
   the parts of a word reads exactly like one you know, and teaches a fiction.
6. Give 2-4 short everyday examples with translations.
For a set expression, also explain what its parts contribute and why the whole
means what it does. With supplied context, lead with the sense used there but
keep all other senses below it. The heading, the translations and the examples are
all about one and the same wording. Where a submission means what it means because
it is negated, either head that negated wording or leave the negation out of the
translations too: never head the bare positive unit and translate the negative
sense."""

_SELECTED_ARTICLE = (
    "The learner selected this unit, so write a complete compact dictionary\n"
    "article about it, in this order:\n" + _ARTICLE_RULES
)
_BRANCH_ARTICLE = (
    "For a unit, write a complete compact dictionary article in this order:\n" + _ARTICLE_RULES
)

_TEXT_ARTICLE = """For text, begin with a natural translation of the whole submitted text. Then give
2-5 compact notes about genuinely difficult constructions, word order, forms,
set expressions or meanings. Do not write a dictionary entry about one selected
word."""

_FORMAT_RULES = """No phonetic transcription. Use only <b>, <i>, <table>, <tr>, and <td>, with no
attributes; tables are only for forms. No Markdown emphasis, headings, code
fences, preamble or closing remarks. The article is at most 3500 characters."""

_SELECTED_CARD_LEAD = """After the article output ===CARD=== on its own line, followed
immediately by one line of JSON in this neutral schematic shape. Angle-bracketed
values are placeholders, not strings to copy:"""

_BRANCH_CARD_LEAD = """After the article output ===CARD=== on its own line, followed
immediately by one line of JSON matching ONE of these neutral schematic branches.
Angle-bracketed values are placeholders, not strings to copy:"""

_UNIT_JSON = """{{"kind": "unit", "word": "<dictionary lemma of the unit>",
 "word_relation": "<same, morphology or typo>",
 "suggestion": "<corrected spelling, or empty>",
 "meanings": [{{"label": "<short target-language sense label or empty>",
 "translations": ["<target-language translation>"],
 "examples": [{{"highlighted": "<short source-language sentence, unit in b tags>",
 "translation": "<target-language translation>"}}]}}],
 "segments": [{{"label": "<component dictionary form>",
 "surface": "<component form seen in the expression>",
 "why": "<short target-language reason>"}}]{context_field}}}"""

_TEXT_JSON = """OR

{{"kind": "text", "combinations": [{{"label": "<dictionary form of the unit>",
 "surface": "<the same unit as the text spells it>",
 "why": "<short target-language reason>"}}]}}"""

_RELATION_RULES = """word_relation is typo when the submission is misspelled, and
then suggestion holds the correct spelling; morphology when word is a different
dictionary form of a correctly spelled submission; same when word is the submission
itself.

suggestion is empty otherwise: it is only ever a correction."""

_MEANING_RULES = """meanings are the senses that need different words in {target_lang}, most common
first; do not impose a numerical limit. Every meaning has 2-4 main translations
and 1-2 examples. When several meanings remain, every label is a short
{target_lang} tag distinguishing them; for one meaning its label is empty.
Each highlighted example is a whole sentence carrying <b> tags around all and
only the unit, since it becomes the front of a card. Write that sentence entirely
in {source_lang}, in one script from end to end — a {target_lang} sentence with
the {source_lang} unit dropped into it is not an example and teaches nothing.
Mark a contiguous unit with one span and separated or reflexive pieces with
one span each, in their original positions. Never mark a subject, object,
auxiliary or argument merely because it occurs with the unit, and always leave
at least one unmarked source-language word in the sentence. {context_rule}"""

_SEGMENT_RULES = """For a multi-word set expression, segments contains every word-shaped component,
including particles and prepositions, with no count cap. Preserve the forms seen
in the submitted expression. Do not repeat the whole expression as a component."""

_COMBINATION_RULES = """For text, put every clear multi-word lookup target in
combinations, even when one accounts for most of the utterance. It qualifies when
its meaning does not follow
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
meanings, segments or other card fields."""

_SELECTED_CHECK = """Check before answering that the JSON is valid, with every string in double
quotes, and that the article begins with the bold heading its word names."""

_BRANCH_CHECK = """Check before answering that the JSON is valid, with every string in double
quotes, and that a unit article begins with the bold heading its word names."""

_SELECTED_PROMPT = "\n\n".join(
    (
        _INTRO,
        _SELECTED_ARTICLE,
        _FORMAT_RULES,
        _SELECTED_CARD_LEAD,
        _UNIT_JSON,
        _RELATION_RULES,
        _MEANING_RULES,
        _SEGMENT_RULES,
        _SELECTED_CHECK,
    ),
)

_OPEN_PROMPT = "\n\n".join(
    (
        _INTRO,
        _BRANCH,
        _BRANCH_ARTICLE,
        _TEXT_ARTICLE,
        _FORMAT_RULES,
        _BRANCH_CARD_LEAD,
        _UNIT_JSON,
        _TEXT_JSON,
        _RELATION_RULES,
        _MEANING_RULES,
        _SEGMENT_RULES,
        _COMBINATION_RULES,
        _BRANCH_CHECK,
    ),
)

_ATTESTATION_PROMPT = """You judge whether a wording is actually used by speakers of {source_lang}.

Wording: "{word}"

Answer with one line of JSON and nothing else:
{{"used": true or false, "where": "<the register, field, dialect or period this exact
wording is used in, in a few words; empty when used is false>"}}

Rarity is no objection: wording real speakers use in any register, field, dialect or
period is used, however uncommon. Wording that is merely well formed — a compound,
derivation or coinage nobody actually says — is not used, however natural it looks.
Do not write an article, an explanation or anything else."""

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


def build_prompt(
    language: Language,
    word: str,
    target_lang: str,
    *,
    context: str = "",
    unit_intent: bool = False,
) -> str:
    """Build the prompt for the branch the request is in, or for deciding it."""
    request = (
        f'Make a card for this selected unit: "{word}"\nContext: "{context}"'
        if unit_intent and context
        else f'Make a card for this selected unit: "{word}"'
        if unit_intent
        else f'Analyse this submitted text: "{word}"'
    )
    template = _SELECTED_PROMPT if unit_intent else _OPEN_PROMPT
    return template.format(
        source_lang=language.name,
        target_lang=target_lang,
        source_hints=language.prompt_hints or "",
        request=request,
        context_field=', "context_sense": <zero-based index>' if context else "",
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


@dataclass(frozen=True)
class Verdict:
    """The standalone judgement on whether the submitted wording is used at all.

    The prompt also asks where it is used: naming a register or period is what makes
    the judgement concrete rather than a guess. Nothing here reads that answer back,
    so it is not kept.
    """

    used: bool


def build_attestation_prompt(language: Language, word: str) -> str:
    """Build the standalone attestation question.

    Asked on its own rather than inside the article call: a model already writing a
    dictionary entry has an entry to produce, and measurably keeps producing one.
    """
    return _ATTESTATION_PROMPT.format(source_lang=language.name, word=word)


def parse_attestation(raw: str) -> Verdict | None:
    """Read the judgement, which is one bare JSON object and nothing else."""
    start = raw.find("{")
    if start < 0:
        return None
    try:
        value, _consumed = json.JSONDecoder().raw_decode(raw[start:])
    except ValueError:
        return None
    used = value.get("used") if isinstance(value, dict) else None
    return Verdict(used) if isinstance(used, bool) else None


def extract_answer(  # noqa: PLR0913 - the whole request the answer is read against.
    raw: str,
    submitted: str,
    language: Language,
    *,
    unit_intent: bool = False,
    context: str = "",
    target: str = DEFAULT_TARGET_LANGUAGE,
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
            target=target,
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
