"""The merged language-analysis prompt and its hidden structured answer."""

import json
import logging
from dataclasses import dataclass

from echo_words.card import CardParseError, ParsedAnswer, parse_answer_payload
from echo_words.languages import Language

CARD_DELIMITER = "===CARD==="
PAYLOAD_LOG_LIMIT = 2000
MAX_COMPLETE_ANSWER_CHARS = 16_000
# The verdict leads the answer so a refusal costs no article. Measured on the free
# pool with the prompt the submit box actually sends: asked as a leading judgement it
# withholds two coinages of six, asked as prose inside the article rules it withheld
# none. What it catches is nonsense strings; a well-formed compound it still cards.
VERDICT_PREFIX = "===USED==="
# The marker is looked for in the lead rather than at the very start: a model that
# prefixes one courtesy word must not thereby switch the judgement off.
VERDICT_LEAD_CHARS = 200
# How much may follow an opened but unclosed judgement before it is given up on. A
# judgement wrapped over several lines closes well inside this even with a wordy
# register; one that never closes would otherwise hold the whole article back for
# good. Set too tight, the bound expires mid-object and prints the rest of the JSON
# to the reader as prose.
MAX_VERDICT_JSON_CHARS = 400

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

Having chosen the unit branch, judge the submitted wording before writing about
it, and open the answer with that judgement on its own line:
{verdict_prefix} {{"used": true or false, "where": "<the register, field, dialect or
period this exact wording is used in, in a few words; empty when used is false>"}}
Rarity is no objection: wording real speakers use in any register, field, dialect
or period is used, however uncommon. Wording that is merely well formed — a
compound, derivation or coinage nobody actually says — is not used. A misspelling
is not this case: it is real wording written wrong, so answer it as the misspelling
rules below require, with the correction in suggestion. Say used false only when
nothing attested is close at all, and then write nothing else: no article, no card,
no explanation. The text branch has no such line.

For a unit, write a complete compact dictionary article in this order:
1. Begin with the unit heading in <b> tags, using the dictionary lemma, which is
   also what goes in word; head a suspected misspelling with the correction, never
   with the submitted spelling. Before writing anything else, check whether changing
   a letter or two of a correctly spelled submission spells a markedly commoner word
   — quiet beside quite, Rate beside Ratte. When it does, keep the heading on the
   submission and name that commoner word in also_common.
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
 "also_common": "<markedly commoner near-spelling, or empty>",
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
correctly spelled submission; same when word is the submission itself.

suggestion is empty otherwise: it is only ever a correction.

also_common is the separate, weaker thing — the markedly commoner near-spelling of
rule 1, filled while the relation stays same or morphology. That submission is real,
so the article and card stay about it and the commoner word is only offered beside
it. Fill it whenever rule 1 found such a word, including when you also warn about the
confusion in usage. Never put a synonym there, or a commoner word spelled
differently, or the submission itself. It is empty otherwise.

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

_ATTESTATION_PROMPT = """You judge whether a wording is actually used by speakers of {source_lang}.

Wording: "{word}"

Answer with one line of JSON and nothing else:
{{"used": true or false, "where": "<the register, field, dialect or period this exact
wording is used in, in a few words; empty when used is false>"}}

Rarity is no objection: wording real speakers use in any register, field, dialect or
period is used, however uncommon. Wording that is merely well formed — a compound,
derivation or coinage nobody actually says — is not used, however natural it looks.
Do not write an article, an explanation or anything else."""

_UNIT_INTENT = "The learner explicitly selected a unit, so kind must be unit."
_OPEN_INTENT = "For this submit-box request, choose the branch yourself."
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
    return _PROMPT.format(
        source_lang=language.name,
        target_lang=target_lang,
        source_hints=language.prompt_hints or "",
        request=request,
        verdict_prefix=VERDICT_PREFIX,
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


@dataclass(frozen=True)
class Verdict:
    """The answer's own judgement on whether the submitted wording is used at all.

    The prompt also asks where it is used: naming a register or period is what makes
    the judgement concrete rather than a guess. Nothing here reads that answer back,
    so it is not kept.
    """

    used: bool


def _marker_at(raw: str) -> int | None:
    """Where the verdict marker starts in the answer's lead, whole or still arriving."""
    # The window covers a marker that *starts* inside the lead, so one beginning at its
    # last character is still found whole rather than read as prose.
    lead = raw[: VERDICT_LEAD_CHARS + len(VERDICT_PREFIX)]
    at = lead.find(VERDICT_PREFIX)
    if 0 <= at < VERDICT_LEAD_CHARS:
        return at
    # A marker still arriving may start anywhere the whole one may, so the two scans
    # share a window: gating the partial one tighter showed half a marker as prose.
    if len(raw) > VERDICT_LEAD_CHARS + len(VERDICT_PREFIX):
        return None
    # Only the end of the stream can hold half a marker, and it must not flash on
    # the page as prose before the judgement it belongs to is readable.
    for length in range(min(len(VERDICT_PREFIX) - 1, len(raw)), 0, -1):
        if raw.endswith(VERDICT_PREFIX[:length]) and len(raw) - length < VERDICT_LEAD_CHARS:
            return len(raw) - length
    return None


def _read_verdict(raw: str) -> tuple[Verdict | None, int, int | None] | None:
    """Scan the lead for the verdict: what it says, where it starts, where it ends.

    None when no marker has arrived at all. An end of None means the marker is still
    arriving and everything from it is held back; a marker that has arrived whole but
    cannot be read yields no verdict and is dropped, because unreadable is absent and
    the marker itself is not prose the reader is owed.
    """
    at = _marker_at(raw)
    if at is None:
        return None
    after = at + len(VERDICT_PREFIX)
    tail = raw[after:]
    indent = len(tail) - len(tail.lstrip())
    try:
        value, consumed = json.JSONDecoder().raw_decode(tail[indent:])
    except ValueError:
        opened = tail.lstrip().startswith("{")
        if opened and len(tail) <= MAX_VERDICT_JSON_CHARS:
            # A judgement written over more than one line has not finished arriving.
            # Cutting it at the first newline would print the rest of its JSON as prose.
            return (None, at, None)
        line_end = tail.find("\n")
        # No line break yet means the judgement may still be on its way.
        return (None, at, None if line_end < 0 else after + line_end + 1)
    end = after + indent + consumed
    used = value.get("used") if isinstance(value, dict) else None
    verdict = Verdict(used) if isinstance(used, bool) else None
    return verdict, at, end + len(raw[end:]) - len(raw[end:].lstrip())


def build_attestation_prompt(language: Language, word: str) -> str:
    """Build the standalone attestation question.

    Asked on its own rather than inside the article call: a model already writing a
    dictionary entry has an entry to produce, and measurably keeps producing one.
    """
    return _ATTESTATION_PROMPT.format(source_lang=language.name, word=word)


def parse_attestation(raw: str) -> Verdict | None:
    """Read the standalone answer, which is one bare JSON object and no marker."""
    start = raw.find("{")
    if start < 0:
        return None
    try:
        value, _consumed = json.JSONDecoder().raw_decode(raw[start:])
    except ValueError:
        return None
    used = value.get("used") if isinstance(value, dict) else None
    return Verdict(used) if isinstance(used, bool) else None


def parse_verdict(raw: str) -> Verdict | None:
    """Read the answer's verdict, or None when it gave none this side of readable."""
    read = _read_verdict(raw)
    return None if read is None else read[0]


def strip_verdict(raw: str) -> str:
    """Drop the verdict from what the reader sees, and every partial prefix of it."""
    read = _read_verdict(raw)
    if read is None:
        return raw
    _, at, end = read
    return raw[:at] if end is None else raw[:at] + raw[end:]


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
