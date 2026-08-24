"""Validated, compact note data extracted from an LLM answer."""

import json
import unicodedata
from dataclasses import dataclass
from typing import Any

from echo_words.languages import Language, validate_word

MAX_MEANINGS = 3
MAX_EXAMPLES_PER_MEANING = 2


class CardParseError(ValueError):
    """The card payload is not usable as a vocabulary note."""


@dataclass(frozen=True)
class Example:
    text: str
    translation: str


@dataclass(frozen=True)
class Meaning:
    label: str
    pos: str
    translations: list[str]
    examples: list[Example]


@dataclass(frozen=True)
class Note:
    word: str
    meanings: list[Meaning]


ParsedCard = tuple[Note, str | None]


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
    return Note(word=word, meanings=meanings), suggestion


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
        pos=_optional_string(meaning, "pos", path),
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


def _optional_string(value: dict[str, Any], key: str, path: str) -> str:
    item = value.get(key, "")
    if not isinstance(item, str):
        raise CardParseError(f"{path}.{key} must be a string")
    return item


def _non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CardParseError(f"{path} must be a non-empty string")
    return value
