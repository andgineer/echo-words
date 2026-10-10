"""The two language-analysis prompts and their hidden structured answer.

The unit prompt answers a request whose branch the learner's own action already
settled; the submit box, where it has not, gets the prompt that carries both
branches and decides between them.
"""

import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from echo_words.card import (
    CardParseError,
    ParsedAnswer,
    context_sentence_forms,
    parse_answer_payload,
)
from echo_words.languages import (
    DEFAULT_TARGET_LANGUAGE,
    MAX_CONTEXT_LENGTH,
    Language,
    fold_for_match,
    plain_unit,
    sentence_is_source_language,
    validate_text,
    validate_word,
)

CARD_DELIMITER = "===CARD==="
PAYLOAD_LOG_LIMIT = 2000
MAX_COMPLETE_ANSWER_CHARS = 16_000
# A reverse lookup is a handful of chips, and the first is the one carded.
MAX_EQUIVALENTS = 6
_WORD_TOKEN = re.compile(r"[^\W\d_]+", re.UNICODE)
# A model can drop a string value's opening quote («"example": Potpisali su…"»), and
# asked again it drops it again.
_UNQUOTED_VALUE = re.compile(r'(":\s*)(?!true\b|false\b|null\b)(?=[^\W\d_])')
# The deeper article is read on a phone, right after the short one. Asked for "every
# sense, in depth" and given no bound, it came back as a dissertation; this is the
# length a reader spends a couple of minutes on, and the prompt names it.
MAX_DETAIL_CHARS = 4_000

logger = logging.getLogger(__name__)

_INTRO = """You are a language tutor. The request below concerns {source_lang}.

{request}

WRITE YOUR ENTIRE ANSWER IN {target_lang}. Explanations, translations, usage
notes, origin and reasons are in {target_lang}. Only a headword, quoted source
text, source-language examples and the card sense label stay in {source_lang}.
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
 "meanings": [{{"label": "<short {source_lang} word this sense occurs with, or empty>",
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
and 1-2 examples. When several meanings remain, every label is a short cue in
{source_lang} telling them apart, and it is a word the headword habitually keeps
company with in that sense: what it takes as its object or subject, its governed
preposition, the thing it is typically done to or with. It is not a synonym of
the headword and not a synonym of the translation. Only where the sense keeps no
such company, name the field it belongs to instead. Write it in {source_lang} and
never in {target_lang}, and never repeat a word of this meaning's own
translations: the label is printed beside the headword on the front of the card
whose answer is those translations, so a {target_lang} label gives that answer
away. For one meaning its label is empty.
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

_REVERSE_PROMPT = """You are a bilingual dictionary from {target_lang} into {source_lang}.

Wording: "{word}"

Read the wording as {target_lang}. An inflected word is read as its dictionary form;
a fixed expression is its own dictionary form and keeps its wording. A slip of one or
two letters off a common {target_lang} word — letters swapped, missing, doubled or
mistyped — is that word misspelled, and is read as the word it was meant to be.

Give the {source_lang} words for it: one for each meaning a {target_lang} dictionary
gives the wording that needs a different {source_lang} word — usually one to three,
the commonest meaning first, never more than six. Every equivalent translates a
meaning the {target_lang} wording itself has, so that a {target_lang} speaker reading
its example would put the wording back: a further meaning of the {source_lang} word,
a narrower kind of the same thing and a merely related word are not translations.
Translate from {target_lang} directly, never by way of English or another third
language: a meaning only the go-between word has is no meaning of the wording.
Where {source_lang} has no exact equivalent, give the closest word or expression its
speakers actually use, never a coinage or a word-for-word rendering; for an
expression, give a {source_lang} expression or word with the same meaning. Each word
is its bare dictionary form, spelled and capitalised exactly as a {source_lang}
dictionary heads its entry, with no article and a verb in its infinitive.{script_rule}

For each, write one short, natural, everyday sentence entirely in {source_lang} that
uses that very word in that meaning, since it becomes the front of a flashcard and is
read aloud, and copy the word exactly as that sentence spells it. No sentence carries
a swearword, an insult or a slur, and a meaning that is only one is left out.

Answer with one line of JSON and nothing else, in this schematic shape;
angle-bracketed values are placeholders, not strings to copy:
{{"verdict": "word", "read_as": "<the {target_lang} dictionary form you read it as>",
 "equivalents": [{{"word": "<{source_lang} dictionary form>",
 "example": "<short {source_lang} sentence using it in this meaning>",
 "form": "<that word as the sentence spells it: its own words, in order>"}}]}}

verdict is "not_a_word", with read_as empty and no equivalents, when no
{target_lang} word or expression reads the wording: a random string, a word of another
language, or a string only a rare, slang or euphemistic reading would make a word. A
{source_lang} word typed in {target_lang} letters that is no {target_lang} word is
not_a_word too, and is never read as a misspelled {target_lang} word. It is
"sentence", with read_as empty and no equivalents, when the wording reports a
particular situation rather than naming a word or expression; a clause with its own
subject and finite verb does. Do not write an article, an explanation or anything
else."""

# Serbian is read in Latin letters, and its Cyrillic shares its letters with Russian, which
# leaks into the answers.
_LATIN_ONLY_RULE = (
    " {source_lang} is written in two alphabets: write every word, form and sentence in"
    " its Latin one, latinica, and never in Cyrillic."
)

_CONTEXT_RULE = (
    'Include "context_sense": <zero-based index> naming the sense the unit carries in '
    'the supplied context, "context_translation": the target-language translation of '
    'that context sentence, and "context_surface": the unit\'s own words exactly as '
    "they appear in that sentence, in order and separated by single spaces, with "
    "nothing else. Do not copy the context sentence into the examples — write ordinary "
    "examples for every sense."
)
_NO_CONTEXT_RULE = "Do not add a field selecting a contextual sense."

_EXTENDED_PROMPT = """You are a lexicographer. The word below is in {source_lang}.
Analyse it in depth: {word}

WRITE YOUR ENTIRE ANSWER IN {target_lang}, and in no other language. Only the
headword and example sentences stay in {source_lang}, and every example is
followed by its {target_lang} translation.

{context_note}The reader has already seen the short entry and wants more of it,
not a monograph. Add what the short entry left out: senses it did not cover,
where the word came from, how it is actually used and the mistakes learners make
with it, and how it differs from its near-synonyms. One example per sense. Leave
out archaic, regional and narrowly technical senses unless the word is mainly
known for one. Aim for something read in a couple of minutes — around 2000
characters, and never more than {bound}. Use only <b> and <i>, no Markdown. Give
no phonetic transcription, JSON or delimiters.
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
        context_field=(
            ', "context_sense": <zero-based index>,'
            ' "context_translation": "<target-language translation of the context>",'
            ' "context_surface": "<the unit\'s words as they stand in the context>"'
            if context
            else ""
        ),
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
        bound=f"{MAX_DETAIL_CHARS} characters",
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
    value = json_object(raw)
    used = value.get("used") if value is not None else None
    return Verdict(used) if isinstance(used, bool) else None


type ReverseVerdict = Literal["word", "not_a_word", "sentence"]
_REVERSE_VERDICTS = frozenset({"word", "not_a_word", "sentence"})


@dataclass(frozen=True)
class Equivalent:
    """A source-language word for the target-language wording, and the sentence
    using it in its meaning — empty where the card could not have used that sentence."""

    word: str
    example: str


@dataclass(frozen=True)
class ReverseAnswer:
    verdict: ReverseVerdict
    read_as: str
    equivalents: tuple[Equivalent, ...]


def build_reverse_prompt(language: Language, word: str, target: str) -> str:
    """Build the question that turns a target-language wording into source-language words."""
    latin_only = language.script == "latin+cyrillic"
    return _REVERSE_PROMPT.format(
        source_lang=language.name,
        target_lang=target,
        word=word,
        script_rule=_LATIN_ONLY_RULE.format(source_lang=language.name) if latin_only else "",
    )


def parse_reverse(
    raw: str,
    language: Language,
    target: str = DEFAULT_TARGET_LANGUAGE,
) -> ReverseAnswer | None:
    """Read the reverse lookup, or None when it carries no verdict or no usable word.

    An equivalent the source language would refuse is dropped, and an example the card
    could not use is dropped from its equivalent: either costs a chip or a sentence,
    never the answer.
    """
    value = json_object(raw)
    verdict = value.get("verdict") if value is not None else None
    if value is None or verdict not in _REVERSE_VERDICTS:
        return None
    if verdict != "word":
        return ReverseAnswer(verdict, "", ())
    equivalents = _equivalents(value.get("equivalents"), language, target)
    if not equivalents:
        return None
    read_as = value.get("read_as")
    return ReverseAnswer(
        "word",
        _plain(read_as) if isinstance(read_as, str) else "",
        equivalents,
    )


def reverse_example_issue(
    example: str,
    form: str,
    word: str,
    language: Language,
    target: str = DEFAULT_TARGET_LANGUAGE,
) -> str | None:
    """Why the card could not use this sentence as its front, or None when it could.

    It is the card's own test: a sentence the card cannot mark the word in would fail
    the card later, and a whole-word comparison would refuse every inflected example.
    """
    if not example:
        return "missing"
    if len(example) > MAX_CONTEXT_LENGTH:
        return "too_long"
    if validate_text(example, language) is not None:
        return "script"
    if not sentence_is_source_language(example, language, target):
        return "letters"
    related = bool(form) and _spells_the_word(form, word, language)
    marked = context_sentence_forms(example, form, language, target) if related else None
    if marked is None:
        marked = context_sentence_forms(example, word, language, target)
    if marked is not None:
        return None
    return "unrelated" if form and not related else "form"


def _headword_case(word: str, form: str, example: str) -> str:
    """The headword in the letter case its own sentence writes it in, where that shows.

    Asked for a word as a dictionary heads it, answers come back in dictionary
    typography — all capitals, or every headword capitalised — and with German nouns
    lowered; a single word standing mid-sentence shows the case the language gives it.
    """
    if word.isupper() and len(word) > 1:
        word = word.lower()
    if len(word.split()) > 1:
        return word
    tokens = [match.group() for match in _WORD_TOKEN.finditer(example)]
    wanted = (form or word).casefold()
    position = next(
        (index for index, token in enumerate(tokens) if token.casefold() == wanted),
        None,
    )
    if position is None:
        return word
    if position == 0:
        # Opening the sentence hides the case. A form the answer copied in lower case
        # shows it; one in capitals may only have copied the sentence's first letter.
        lowered = form[:1].islower() and form.casefold() == word.casefold()
        return form if lowered else word
    spelled = tokens[position]
    if spelled.casefold() == word.casefold():
        return spelled
    first = word[0].upper() if spelled[0].isupper() else word[0].lower()
    return first + word[1:]


def _spells_the_word(form: str, word: str, language: Language) -> bool:
    """Whether every token of the form is a form of some token of the word.

    A sentence written around another word would be marked at that word, so the form
    has to share a stem with its word; only suppletive forms (went for go) fail this.
    """
    stems = [_stem_fold(token, language) for token in _WORD_TOKEN.findall(word)]
    return bool(stems) and all(
        any(_shares_a_stem(_stem_fold(token, language), stem) for stem in stems)
        for token in _WORD_TOKEN.findall(form)
    )


def _stem_fold(token: str, language: Language) -> str:
    decomposed = unicodedata.normalize("NFD", fold_for_match(token, language))
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _shares_a_stem(token: str, stem: str) -> bool:
    # Compared from any point of the word's token, so a separated particle (stehe ...
    # auf for aufstehen) matches; a vowel change of one letter (gave, give) passes too.
    shorter = min(len(token), len(stem))
    wanted = min(max(3, shorter - 2), shorter)
    longest = max(len(os.path.commonprefix((token, stem[offset:]))) for offset in range(len(stem)))
    return longest >= wanted or _within_one_edit(token, stem)


def _within_one_edit(first: str, second: str) -> bool:
    if abs(len(first) - len(second)) > 1:
        return False
    if len(first) == len(second):
        return sum(a != b for a, b in zip(first, second, strict=True)) <= 1
    longer, shorter = (first, second) if len(first) > len(second) else (second, first)
    return any(longer[:index] + longer[index + 1 :] == shorter for index in range(len(longer)))


def _equivalents(value: Any, language: Language, target: str) -> tuple[Equivalent, ...]:
    if not isinstance(value, list):
        return ()
    kept: list[Equivalent] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        word = plain_unit(_plain(item.get("word")))
        folded = fold_for_match(word, language)
        if validate_word(word, language) is not None or folded in seen:
            continue
        seen.add(folded)
        example, form = _plain(item.get("example")), _plain(item.get("form"))
        if reverse_example_issue(example, form, word, language, target) is None:
            kept.append(Equivalent(_headword_case(word, form, example), example))
        else:
            kept.append(Equivalent(_headword_case(word, "", ""), ""))
        if len(kept) == MAX_EQUIVALENTS:
            break
    return tuple(kept)


def _plain(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFC", value).split())


def json_object(raw: str) -> dict | None:
    """The JSON object the text opens with, read past a string value missing its opening quote."""
    start = raw.find("{")
    if start < 0:
        return None
    text = raw[start:]
    for candidate in (text, _UNQUOTED_VALUE.sub(r'\1"', text)):
        try:
            value, _consumed = json.JSONDecoder().raw_decode(candidate)
        except ValueError:
            continue
        return value if isinstance(value, dict) else None
    return None


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
        # The context is logged beside the payload because most rejections are about
        # the two of them disagreeing: without the sentence that was asked about, a
        # copy that missed it by one word reads exactly like an invented one.
        logger.warning(
            "unusable answer block for %s/%r in context %r: %s; payload %s",
            language.code,
            submitted,
            context,
            exc,
            _logged(payload),
        )
        return None


def _logged(payload: str) -> str:
    payload = payload.strip()
    if len(payload) <= PAYLOAD_LOG_LIMIT:
        return repr(payload)
    return f"{payload[:PAYLOAD_LOG_LIMIT]!r} … ({len(payload)} chars)"
