"""Validated compact data extracted from a merged language-model answer."""

import itertools
import json
import re
import unicodedata
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass
from html import escape, unescape
from typing import Any, Literal

from echo_words.languages import (
    DEFAULT_TARGET_LANGUAGE,
    Language,
    fold_for_match,
    sentence_is_source_language,
    validate_word,
)
from echo_words.sanitizer import sanitize_html
from echo_words.segments import Segment, fill_text_segments, parse_component_segments

MAX_EXAMPLES_PER_MEANING = 2
type AnswerKind = Literal["unit", "text"]
type WordRelation = Literal["same", "morphology", "typo"]


class CardParseError(ValueError):
    """The hidden answer payload is not usable."""


@dataclass(frozen=True)
class _Request:
    """What an answer is being read for: the two languages and the wording asked about."""

    language: Language
    target: str
    context: str
    selected_surface: str
    target_lexeme: str


@dataclass(frozen=True)
class Example:
    text: str
    translation: str
    highlighted: str
    gapped: str


@dataclass(frozen=True)
class Meaning:
    label: str
    translations: list[str]
    examples: list[Example]


@dataclass(frozen=True)
class Note:
    word: str
    meanings: list[Meaning]
    sense: int = 0

    @property
    def meaning(self) -> Meaning:
        return self.meanings[self.sense]


@dataclass(frozen=True)
class ParsedUnit:
    kind: Literal["unit"]
    note: Note
    word_relation: WordRelation
    suggestion: str | None
    segments: list[Segment]


@dataclass(frozen=True)
class ParsedText:
    kind: Literal["text"]
    segments: list[Segment]


type ParsedAnswer = ParsedUnit | ParsedText

_UNIT_FIELDS = frozenset(
    {
        "word",
        "word_relation",
        "suggestion",
        "meanings",
        "context_sense",
        "context_translation",
        "context_surface",
        "segments",
    },
)
_TEXT_FIELDS = frozenset({"combinations"})
_BOLD_SPAN = re.compile(r"<b>([^<>]+)</b>")
_ADJACENT_BOLD_SPANS = re.compile(r"</b>(\s+)<b>")
_BOLD_TAG = re.compile(r"</?b>")
# The colon must close a key, or the repair would also fire inside a string value.
_BARE_VALUE = re.compile(r'(?<=")(:\s*)(?![\s"\[{\d-]|true|false|null)([^,}\]\n"]*[^\s,}\]\n"])')
_FULL_STOP_SEPARATOR = re.compile(r'([}\]])\s*\.\s*(")')
_NON_ESCAPE = re.compile(r'\\(?=[^\\"/bfnrtu])')
_SOURCE_TOKEN = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", re.UNICODE)


def parse_answer_payload(  # noqa: C901, PLR0912, PLR0913 - the answer discriminator.
    payload: str,
    submitted: str,
    language: Language,
    *,
    unit_intent: bool = False,
    context: str = "",
    target: str = DEFAULT_TARGET_LANGUAGE,
) -> ParsedAnswer:
    """Parse the first JSON object and enforce the answer branch and request intent."""
    try:
        value = _decoded(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise CardParseError(f"answer payload is not valid JSON: {exc}") from exc
    card = _object(value, "answer")
    kind = card.get("kind")
    if kind == "text":
        if unit_intent:
            raise CardParseError("a unit-intent request returned text")
        if any(key in card for key in _UNIT_FIELDS):
            raise CardParseError("a text answer contains unit fields")
        try:
            segments = fill_text_segments(card.get("combinations"), submitted, language)
        except Exception as exc:
            raise CardParseError(str(exc)) from exc
        return ParsedText("text", segments)
    if kind != "unit":
        raise CardParseError("answer.kind must be unit or text")
    if any(key in card for key in _TEXT_FIELDS):
        raise CardParseError("a unit answer contains text combinations")

    headword = _headword(card.get("word"), language)
    word_relation, headword, suggestion = _word_relation(
        card.get("word_relation"),
        card.get("suggestion"),
        headword,
        submitted,
        language,
    )
    raw_meanings = card.get("meanings")
    if not isinstance(raw_meanings, list) or not raw_meanings:
        raise CardParseError("answer.meanings must be a non-empty list")
    request = _Request(language, target, context, submitted, headword)
    candidates: list[tuple[int, Meaning]] = []
    for raw_index, item in enumerate(raw_meanings):
        meaning = _parse_meaning(item, request)
        if meaning is None:
            continue
        candidates.append((raw_index, meaning))
    # A missing label never drops a sense. Labels tell retained senses apart on a bare
    # front, and an unlabelled front is merely less informative; dropping the sense
    # instead cards whichever sibling happened to carry a label, and the answer orders
    # the commonest sense first, so that is the one a label rule would delete.
    retained: list[Meaning] = []
    remap: dict[int, int] = {}
    for raw_index, meaning in candidates:
        remap[raw_index] = len(retained)
        retained.append(meaning)
    if not retained:
        raise CardParseError("answer.meanings contains no usable meaning")
    raw_sense = _context_sense(card.get("context_sense"), len(raw_meanings))
    if context and raw_sense is not None and raw_sense not in remap:
        # Falling back to sense 0 here cards a sense the answer did not choose, and
        # then fails the context check below — which names the sentence, not the sense
        # that went missing. Two different faults must not share one message.
        raise CardParseError("the sense the answer chose for the context was dropped")
    sense = remap.get(raw_sense, 0)
    if context:
        retained[sense] = _with_context_example(
            retained[sense],
            card.get("context_translation"),
            card.get("context_surface"),
            request,
        )
    note = Note(headword, retained, sense)
    try:
        segments = parse_component_segments(
            card.get("segments"),
            language,
            context=note.meaning.examples[0].text,
        )
    except Exception as exc:
        raise CardParseError(str(exc)) from exc
    return ParsedUnit(
        "unit",
        note,
        word_relation,
        suggestion,
        segments,
    )


def _decoded(payload: str) -> Any:
    """Decode the payload, repairing only punctuation slips a model makes under load.

    A repair is a guess about intent, so it stands only when it yields valid JSON;
    the value it produces still faces every check below.
    """
    text = payload.lstrip()
    try:
        return json.JSONDecoder().raw_decode(text)[0]
    except (json.JSONDecodeError, TypeError) as first:
        error = first
    repairs = (_quote_bare_values, _comma_for_full_stop, _drop_stray_escape)
    # Fewest repairs first, and each combination starts from the original text: a
    # repair which does not apply must not corrupt the input of the one which does.
    for size in range(1, len(repairs) + 1):
        for combination in itertools.combinations(repairs, size):
            repaired = text
            for repair in combination:
                repaired = repair(repaired)
            with suppress(json.JSONDecodeError, TypeError):
                return json.JSONDecoder().raw_decode(repaired)[0]
    raise error


def _quote_bare_values(text: str) -> str:
    """Put quotes back around a bare string value: ``"label": ити се``."""
    return _BARE_VALUE.sub(lambda match: f'{match.group(1)}"{match.group(2)}"', text)


def _comma_for_full_stop(text: str) -> str:
    """Restore a comma typed as a full stop between two items: ``}]}]. "segments"``."""
    return _FULL_STOP_SEPARATOR.sub(r"\1, \2", text)


def _drop_stray_escape(text: str) -> str:
    """Drop a backslash which escapes nothing: ``"\\прекратить"``."""
    return _NON_ESCAPE.sub("", text)


def parse_card_payload(
    payload: str,
    word: str,
    language: Language,
    *,
    context: str = "",
    target: str = DEFAULT_TARGET_LANGUAGE,
) -> ParsedUnit:
    """Parse a payload which the caller already knows must be a unit."""
    parsed = parse_answer_payload(
        payload,
        word,
        language,
        unit_intent=True,
        context=context,
        target=target,
    )
    if not isinstance(parsed, ParsedUnit):
        raise CardParseError("answer is not a unit")
    return parsed


def _headword(value: Any, language: Language) -> str:
    if not isinstance(value, str):
        raise CardParseError("answer.word must be a non-empty string")
    headword = unicodedata.normalize("NFC", value).strip()
    if not headword or validate_word(headword, language) is not None:
        raise CardParseError("answer.word is not a usable dictionary headword")
    return headword


def _parse_meaning(value: Any, request: "_Request") -> Meaning | None:
    if not isinstance(value, dict):
        return None
    translations_value = value.get("translations", value.get("translation"))
    if isinstance(translations_value, str):
        translations_value = [translations_value]
    if not isinstance(translations_value, list):
        return None
    translations = [
        item.strip() for item in translations_value if isinstance(item, str) and item.strip()
    ]
    if not translations:
        return None
    examples = _usable_examples(value.get("examples"), request)
    if not examples:
        return None
    return Meaning(_sense_label(value.get("label"), translations, request), translations, examples)


def _sense_label(value: Any, translations: list[str], request: "_Request") -> str:
    if not isinstance(value, str):
        return ""
    return usable_sense_label(value, translations, request.language, request.target)


def usable_sense_label(
    label: str,
    translations: list[str],
    language: Language,
    target: str = DEFAULT_TARGET_LANGUAGE,
) -> str:
    """The cue as it may be printed beside the headword on the bare front, or nothing.

    That front's answer is the target-language translation, so a cue written in the
    target language, or one repeating a word of this sense's own translations, hands
    over the answer the card asks for. Dropping it only makes the front less
    informative, which is why an unusable cue empties rather than sinking the sense.
    """
    cue = label.strip()
    if not cue or not sentence_is_source_language(cue, language, target):
        return ""
    answered = {
        fold_for_match(match.group(), language)
        for translation in translations
        for match in _SOURCE_TOKEN.finditer(translation)
    }
    cued = {fold_for_match(match.group(), language) for match in _SOURCE_TOKEN.finditer(cue)}
    return "" if cued & answered else cue


def _usable_examples(value: Any, request: "_Request") -> list[Example]:
    values = [value] if isinstance(value, dict) else value
    if not isinstance(values, list):
        return []
    examples: list[Example] = []
    for item in values:
        if example := _parse_example(item, request):
            examples.append(example)
        if len(examples) == MAX_EXAMPLES_PER_MEANING:
            break
    return examples


def _parse_example(value: Any, request: "_Request") -> Example | None:
    if not isinstance(value, dict):
        return None
    translation = _plain(value.get("translation"))
    highlighted_raw = value.get("highlighted")
    marked = _plain(highlighted_raw) if isinstance(highlighted_raw, str) else ""
    # The sentence is the highlight without its marks, so no other markup may appear
    # there: sanitizing it away would leave the escaped residue inside the sentence.
    if not translation or not marked or any(char in _BOLD_TAG.sub("", marked) for char in "<>"):
        return None
    text = _BOLD_SPAN.sub(lambda match: match.group(1), marked)
    if not text:
        return None
    forms = _example_forms(text, marked, request)
    if forms is None:
        return None
    return Example(text, translation, *forms)


def _example_forms(text: str, marked: str, request: "_Request") -> tuple[str, str] | None:
    """The marking the card carries: the model's where it is sound, ours where it is not.

    A whole-sentence bold and a two-token surface with one token marked are the same
    fault — the sentence is right and the marking of it is wrong — and both used to cost
    the example, its sense, and usually the card. The sentence and the wording asked
    about are both ours, so the marking is simply redone from them; only a sentence our
    tokens cannot be found in is beyond it.
    """
    sentence_forms = _normalized_sentence_forms(
        sanitize_html(marked),
        request.language,
        request.target,
    )
    if sentence_forms is not None and (
        request.context
        or _generated_target_covers_submitted_tokens(
            text,
            sentence_forms[0],
            request.selected_surface,
            request.target_lexeme,
        )
    ):
        return sentence_forms
    return _context_sentence_forms(
        text,
        request.selected_surface,
        request.language,
        request.target,
    )


def _with_context_example(
    meaning: Meaning,
    translation: Any,
    surface: Any,
    request: "_Request",
) -> Meaning:
    """The sense the answer chose, with the reader's own sentence as its first example.

    The sentence is the backend's and so is its marking. What only the answer can give
    is asked for instead: which sense the unit carries here, what the sentence means,
    and which of its words the unit actually is — a separable verb submitted as
    `aufstehen` stands in the sentence as `steht … auf`, and no rule the backend can
    write will find that. So nothing is copied and nothing is compared.
    """
    forms = _context_sentence_forms(
        request.context,
        _plain(surface) or request.selected_surface,
        request.language,
        request.target,
    ) or _context_sentence_forms(
        request.context,
        request.selected_surface,
        request.language,
        request.target,
    )
    if forms is None:
        # The submitted unit is not in the sentence it was said to come from, so the
        # request itself does not hold together and no card can be built for it.
        raise CardParseError("the submitted unit does not occur in the supplied context")
    rendered = _plain(translation)
    if not rendered:
        raise CardParseError("the answer did not translate the supplied context")
    example = Example(request.context, rendered, *forms)
    kept = [item for item in meaning.examples if item.text != request.context]
    return Meaning(meaning.label, meaning.translations, [example, *kept][:MAX_EXAMPLES_PER_MEANING])


def _normalized_sentence_forms(
    highlighted: str,
    language: Language | None = None,
    target: str = DEFAULT_TARGET_LANGUAGE,
) -> tuple[str, str] | None:
    # Neighbouring spans are tried merged first: one contiguous unit earns one blank.
    for candidate in (_ADJACENT_BOLD_SPANS.sub(r"\1", highlighted), highlighted):
        if _marked_sentence_usable(candidate, language, target):
            return candidate, _BOLD_SPAN.sub("___", candidate)
    return None


def _marked_sentence_usable(
    highlighted: str,
    language: Language | None = None,
    target: str = DEFAULT_TARGET_LANGUAGE,
) -> bool:
    spans = list(_BOLD_SPAN.finditer(highlighted))
    if not spans or "___" in highlighted:
        return False
    outside = unescape(_BOLD_SPAN.sub("", highlighted))
    # The sentence around the unit has to be in the language being learned. A target
    # sentence with the source word wedged into it is a card front teaching nothing.
    if language is not None and not sentence_is_source_language(outside, language, target):
        return False
    return bool(
        "<" not in outside
        and any(char.isalpha() for char in outside)
        and all(any(char.isalpha() for char in unescape(match.group(1))) for match in spans),
    )


def _context_sentence_forms(
    context: str,
    selected_surface: str,
    language: Language | None = None,
    target: str = DEFAULT_TARGET_LANGUAGE,
) -> tuple[str, str] | None:
    wanted = [_fold(match.group()) for match in _SOURCE_TOKEN.finditer(selected_surface)]
    if not wanted:
        return None
    matches = list(_SOURCE_TOKEN.finditer(context))
    selected = []
    cursor = 0
    for token in wanted:
        found = next(
            (
                match
                for match in matches
                if match.start() >= cursor and _fold(match.group()) == token
            ),
            None,
        )
        if found is None:
            return None
        selected.append(found)
        cursor = found.end()
    highlighted: list[str] = []
    gapped: list[str] = []
    cursor = 0
    for match in selected:
        before = escape(context[cursor : match.start()])
        form = escape(context[match.start() : match.end()])
        highlighted.extend((before, "<b>", form, "</b>"))
        gapped.extend((before, "___"))
        cursor = match.end()
    tail = escape(context[cursor:])
    highlighted.append(tail)
    gapped.append(tail)
    result = "".join(highlighted), "".join(gapped)
    return result if _marked_sentence_usable(result[0], language, target) else None


def _generated_target_covers_submitted_tokens(
    text: str,
    highlighted: str,
    selected_surface: str,
    target_lexeme: str,
) -> bool:
    target_tokens = {_fold(match.group()) for match in _SOURCE_TOKEN.finditer(target_lexeme)}
    submitted = Counter(
        token
        for match in _SOURCE_TOKEN.finditer(selected_surface)
        if (token := _fold(match.group())) in target_tokens
    )
    in_text = Counter(_fold(match.group()) for match in _SOURCE_TOKEN.finditer(text))
    in_target = Counter(
        _fold(token.group())
        for span in _BOLD_SPAN.findall(highlighted)
        for token in _SOURCE_TOKEN.finditer(unescape(span))
    )
    return all(
        in_target[token] >= min(count, in_text[token])
        for token, count in submitted.items()
        if in_text[token]
    )


def _context_sense(value: Any, meanings: int) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < meanings:
        return None
    return value


def _word_relation(
    relation_value: Any,
    suggestion_value: Any,
    headword: str,
    submitted: str,
    language: Language,
) -> tuple[WordRelation, str, str | None]:
    """Reconcile the declared relation with the spellings; return the relation and headword."""
    declared = relation_value if relation_value in {"same", "morphology", "typo"} else None
    submitted_spelling = _submitted_spelling(submitted)
    differs = fold_for_match(headword, language) != fold_for_match(submitted_spelling, language)
    suggestion = _usable_suggestion(suggestion_value, submitted_spelling, language)
    # A typo claim that put the correction in word instead of suggestion still declares
    # one; the headword stays the wording analysed, since the meanings describe it.
    if suggestion is None and differs and declared == "typo":
        suggestion = headword if validate_word(headword, language) is None else None
    # A suggestion repeating the headword would offer the word already being carded.
    advice = None if suggestion is None or suggestion == headword else suggestion
    # Only an admitted correction reads as a misspelling. A suggestion beside a same or
    # morphology claim names a more usual spelling for a word the answer did vouch for.
    if declared == "typo" and suggestion is not None:
        return "typo", headword, advice
    return ("same" if not differs else "morphology"), headword, advice


def _usable_suggestion(value: Any, submitted_spelling: str, language: Language) -> str | None:
    if not isinstance(value, str):
        return None
    suggestion = unicodedata.normalize("NFC", value).strip()
    if not suggestion or fold_for_match(suggestion, language) == fold_for_match(
        submitted_spelling,
        language,
    ):
        return None
    return suggestion if validate_word(suggestion, language) is None else None


def _submitted_spelling(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip()


def _fold(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _plain(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CardParseError(f"{path} must be an object")
    return value
