"""Validated, compact note data extracted from an LLM answer."""

import json
import unicodedata
from dataclasses import dataclass
from typing import Any

from echo_words.languages import Language, sanitize_context, validate_word
from echo_words.shape import word_count

MAX_MEANINGS = 3
MAX_EXAMPLES_PER_MEANING = 2
MAX_CANDIDATES = 3


class CardParseError(ValueError):
    """The card payload is not usable as a vocabulary note."""


@dataclass(frozen=True)
class Example:
    text: str
    translation: str


@dataclass(frozen=True)
class Meaning:
    label: str
    translations: list[str]
    examples: list[Example]


@dataclass(frozen=True)
class Note:
    word: str
    meanings: list[Meaning]
    # The card set this note asks Anki for, beyond the two every note has.
    context: str = ""
    context_sense: int | None = None
    context_prompt: str = ""
    split_recall: bool = False


@dataclass(frozen=True)
class ParsedCard:
    note: Note
    suggestion: str | None
    # The unit the answer is actually about. It differs from the submitted text
    # when that text was a use of a unit rather than a unit itself, and the
    # difference is what tells the two apart — nothing else in the answer does.
    analysed: str
    candidates: list[str]
    # The model decides which extra cards are worth making and points at the
    # sense they are about; every front is built here, from fields it never sees.
    context_sense: int | None = None
    context_prompt: str = ""
    split_recall: bool = False

    @property
    def input_is_unit(self) -> bool:
        # Only a multi-word input can be a use of a unit; a single word is one already.
        if word_count(self.note.word) <= 1:
            return True
        return _fold(self.analysed) == _fold(self.note.word)


def _fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


@dataclass(frozen=True)
class _RequestedCards:
    context_sense: int | None = None
    context_prompt: str = ""
    split_recall: bool = False


def _requested_cards(value: Any, meanings: int) -> _RequestedCards:
    """Read the card requests, dropping any one of them without failing the note.

    An extra card is an improvement on a note that already works, so nothing here
    is fatal: an entry the model got wrong costs that card, never the note.
    """
    if not isinstance(value, list):
        return _RequestedCards()
    fields: dict[str, Any] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if not isinstance(kind, str) or kind not in _CARD_REQUESTS or kind in fields:
            continue
        # Recorded even when the entry is dropped: a duplicate keeps the first,
        # and a first request the model spoiled must not be rescued by a second.
        fields[kind] = _CARD_REQUESTS[kind](item, meanings)
    return _RequestedCards(
        context_sense=fields.get("context"),
        context_prompt=fields.get("context_production") or "",
        split_recall=bool(fields.get("split_recall")),
    )


def _requested_sense(item: dict[str, Any], meanings: int) -> int | None:
    sense = item.get("sense")
    if not isinstance(sense, int) or isinstance(sense, bool) or not 0 <= sense < meanings:
        return None
    return sense


def _requested_prompt(item: dict[str, Any], _meanings: int) -> str:
    # Held to exactly what a submitted context is held to: it is free text that goes
    # on a card front, where a wall of it, or a control character, would stay forever.
    prompt = item.get("prompt")
    return sanitize_context(prompt) if isinstance(prompt, str) else ""


def _requested_split(_item: dict[str, Any], meanings: int) -> bool:
    # A split replaces the one recall card, so a single meaning would leave none.
    return meanings > 1


_CARD_REQUESTS = {
    "context": _requested_sense,
    "context_production": _requested_prompt,
    "split_recall": _requested_split,
}


def parse_card_payload(payload: str, word: str, language: Language) -> ParsedCard:
    """Parse one JSON object, ignoring text after it, and keep ``word`` canonical."""
    try:
        value, _end = json.JSONDecoder().raw_decode(payload.lstrip())
    except (json.JSONDecodeError, TypeError) as exc:
        raise CardParseError(f"card payload is not valid JSON: {exc}") from exc
    card = _object(value, "card")
    # The model's echo is required by the contract but never trusted for identity.
    _non_empty_string(card.get("word"), "card.word")
    meanings_value = card.get("meanings")
    if not isinstance(meanings_value, list):
        raise CardParseError("card.meanings must be a list")
    if not 1 <= len(meanings_value) <= MAX_MEANINGS:
        raise CardParseError("card.meanings must contain between one and three meanings")
    meanings = [
        _parse_meaning(item, index, require_label=len(meanings_value) > 1)
        for index, item in enumerate(meanings_value)
    ]
    suggestion = _usable_suggestion(card.get("suggestion"), word, language)
    analysed = _analysed_unit(card.get("word"), word, language)
    requested = _requested_cards(card.get("cards"), len(meanings))
    return ParsedCard(
        note=Note(word=word, meanings=meanings),
        suggestion=suggestion,
        analysed=analysed,
        candidates=_candidates(card.get("candidates"), analysed, language),
        context_sense=requested.context_sense,
        context_prompt=requested.context_prompt,
        split_recall=requested.split_recall,
    )


def _analysed_unit(value: Any, word: str, language: Language) -> str:
    """What the answer is about: the model's own headword, or the input when it is unusable.

    Falling back to the input is deliberate. A headword that would have been
    refused had the user typed it must never reach the deck, and treating the
    input as the analysed unit keeps today's behaviour rather than inventing new.
    """
    if not isinstance(value, str):
        return word
    analysed = unicodedata.normalize("NFC", value).strip()
    if not analysed or validate_word(analysed, language) is not None:
        return word
    return analysed


def _candidates(value: Any, analysed: str, language: Language) -> list[str]:
    """The units worth looking up, held to the rule typed input is held to.

    One tap turns a candidate into the front of a real note, so a candidate that
    would have been refused had the user typed it is dropped and never offered.
    """
    if not isinstance(value, list):
        return []
    picked: list[str] = []
    seen = {_fold(analysed)}
    for item in value:
        if not isinstance(item, str):
            continue
        candidate = unicodedata.normalize("NFC", item).strip()
        if not candidate or validate_word(candidate, language) is not None:
            continue
        if _fold(candidate) in seen:
            continue
        seen.add(_fold(candidate))
        picked.append(candidate)
        if len(picked) == MAX_CANDIDATES:
            break
    return picked


def _parse_meaning(value: Any, index: int, *, require_label: bool) -> Meaning:
    path = f"card.meanings[{index}]"
    meaning = _object(value, path)
    translations_value = meaning.get("translations")
    if not isinstance(translations_value, list) or not translations_value:
        raise CardParseError(f"{path}.translations must be a non-empty list")
    translations = [
        _non_empty_string(item, f"{path}.translations[{translation_index}]")
        for translation_index, item in enumerate(translations_value)
    ]
    examples_value = meaning.get("examples")
    if (
        not isinstance(examples_value, list)
        or not 1 <= len(examples_value) <= MAX_EXAMPLES_PER_MEANING
    ):
        raise CardParseError(f"{path}.examples must contain between one and two examples")
    examples = [
        _parse_example(item, f"{path}.examples[{example_index}]")
        for example_index, item in enumerate(examples_value)
    ]
    return Meaning(
        label=(
            _non_empty_string(meaning.get("label"), f"{path}.label")
            if require_label
            else _required_string(meaning, "label", path)
        ),
        translations=translations,
        examples=examples,
    )


def _parse_example(value: Any, path: str) -> Example:
    example = _object(value, path)
    return Example(
        text=_non_empty_string(example.get("text"), f"{path}.text"),
        translation=_non_empty_string(example.get("translation"), f"{path}.translation"),
    )


def _usable_suggestion(value: Any, word: str, language: Language) -> str | None:
    # Suggestion is advisory UI state, so a bad one never invalidates an otherwise good note.
    if not isinstance(value, str):
        return None
    suggestion = unicodedata.normalize("NFC", value).strip()
    if not suggestion or suggestion.casefold() == word.casefold():
        return None
    if validate_word(suggestion, language) is not None:
        return None
    return suggestion


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CardParseError(f"{path} must be an object")
    return value


def _required_string(value: dict[str, Any], key: str, path: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise CardParseError(f"{path}.{key} must be a string")
    return item


def _non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CardParseError(f"{path} must be a non-empty string")
    return value
