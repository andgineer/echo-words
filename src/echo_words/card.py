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

from echo_words.languages import Language, fold_for_match, validate_word
from echo_words.sanitizer import sanitize_html
from echo_words.segments import Segment, fill_text_segments, parse_component_segments

MAX_EXAMPLES_PER_MEANING = 2
type AnswerKind = Literal["unit", "text"]
type WordRelation = Literal["same", "morphology", "typo"]


class CardParseError(ValueError):
    """The hidden answer payload is not usable."""


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
        "also_common",
        "meanings",
        "context_sense",
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


def parse_answer_payload(  # noqa: C901, PLR0912 - the answer discriminator boundary.
    payload: str,
    submitted: str,
    language: Language,
    *,
    unit_intent: bool = False,
    context: str = "",
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
    # The commoner near-spelling is advice about wording the answer vouched for, so a
    # correction outranks it: the reader is told what to fix before what to weigh.
    if word_relation != "typo" and suggestion is None:
        suggestion = _commoner_near_spelling(
            card.get("also_common"),
            headword,
            submitted,
            language,
        )
    raw_meanings = card.get("meanings")
    if not isinstance(raw_meanings, list) or not raw_meanings:
        raise CardParseError("answer.meanings must be a non-empty list")
    candidates: list[tuple[int, Meaning]] = []
    for raw_index, item in enumerate(raw_meanings):
        meaning = _parse_meaning(
            item,
            context=context,
            selected_surface=submitted,
            target_lexeme=headword,
        )
        if meaning is None:
            continue
        candidates.append((raw_index, meaning))
    labelled = [item for item in candidates if item[1].label]
    # Labels tell several senses apart; with none returned they cannot, and dropping
    # every sense over a missing label would throw away an otherwise usable answer.
    if len(candidates) > 1 and labelled:
        candidates = labelled
    retained: list[Meaning] = []
    remap: dict[int, int] = {}
    for raw_index, meaning in candidates:
        remap[raw_index] = len(retained)
        retained.append(meaning)
    if not retained:
        raise CardParseError("answer.meanings contains no usable meaning")
    raw_sense = _context_sense(card.get("context_sense"), len(raw_meanings))
    sense = remap.get(raw_sense, 0)
    note = Note(headword, retained, sense)
    if context and note.meaning.examples[0].text != context:
        raise CardParseError("selected context example must equal the supplied context")
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
) -> ParsedUnit:
    """Parse a payload which the caller already knows must be a unit."""
    parsed = parse_answer_payload(
        payload,
        word,
        language,
        unit_intent=True,
        context=context,
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


def _parse_meaning(
    value: Any,
    *,
    context: str,
    selected_surface: str,
    target_lexeme: str,
) -> Meaning | None:
    if not isinstance(value, dict) or not isinstance(value.get("label"), str):
        return None
    label = value["label"]
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
    examples = _usable_examples(
        value.get("examples"),
        context=context,
        selected_surface=selected_surface,
        target_lexeme=target_lexeme,
    )
    if not examples:
        return None
    return Meaning(label.strip(), translations, examples)


def _usable_examples(
    value: Any,
    *,
    context: str,
    selected_surface: str,
    target_lexeme: str,
) -> list[Example]:
    values = [value] if isinstance(value, dict) else value
    if not isinstance(values, list):
        return []
    examples: list[Example] = []
    for item in values:
        if example := _parse_example(
            item,
            context=context,
            selected_surface=selected_surface,
            target_lexeme=target_lexeme,
        ):
            examples.append(example)
        if len(examples) == MAX_EXAMPLES_PER_MEANING:
            break
    return examples


def _parse_example(
    value: Any,
    *,
    context: str,
    selected_surface: str,
    target_lexeme: str,
) -> Example | None:
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
    if context and text == context:
        contextual = _context_sentence_forms(context, selected_surface)
        if contextual is not None:
            highlighted, gapped = contextual
            return Example(text, translation, highlighted, gapped)
    sentence_forms = _normalized_sentence_forms(sanitize_html(marked))
    if sentence_forms is None or (
        not context
        and not _generated_target_covers_submitted_tokens(
            text,
            sentence_forms[0],
            selected_surface,
            target_lexeme,
        )
    ):
        return None
    return Example(text, translation, *sentence_forms)


def _normalized_sentence_forms(highlighted: str) -> tuple[str, str] | None:
    # Neighbouring spans are tried merged first: one contiguous unit earns one blank.
    for candidate in (_ADJACENT_BOLD_SPANS.sub(r"\1", highlighted), highlighted):
        if _marked_sentence_usable(candidate):
            return candidate, _BOLD_SPAN.sub("___", candidate)
    return None


def _marked_sentence_usable(highlighted: str) -> bool:
    spans = list(_BOLD_SPAN.finditer(highlighted))
    if not spans or "___" in highlighted:
        return False
    outside = _BOLD_SPAN.sub("", highlighted)
    return bool(
        "<" not in outside
        and any(char.isalpha() for char in unescape(outside))
        and all(any(char.isalpha() for char in unescape(match.group(1))) for match in spans),
    )


def _context_sentence_forms(context: str, selected_surface: str) -> tuple[str, str] | None:
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
    return result if _marked_sentence_usable(result[0]) else None


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


def _commoner_near_spelling(
    value: Any,
    headword: str,
    submitted: str,
    language: Language,
) -> str | None:
    advice = _usable_suggestion(value, _submitted_spelling(submitted), language)
    return None if advice == headword else advice


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
