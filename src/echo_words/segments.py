"""Suggested lookup targets derived from a model answer and the submitted text."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from echo_words.languages import (
    Language,
    fold_for_match,
    reflexive_forms,
    reflexive_markers,
    split_words,
    unit_excluded_words,
    validate_word,
)

MAX_SURFACE_LENGTH = 120
MAX_REASON_LENGTH = 200
MIN_COMBINATION_WORDS = 2
# Enough of a shared prefix to recognize an inflected form of a word the dictionary
# form names: `bojim`/`bojati`, `изненадио`/`изненадити`, `looking`/`look`.
MIN_SHARED_STEM = 3


class SegmentParseError(ValueError):
    """The segment payload is not usable as a list of suggested units."""


@dataclass(frozen=True)
class Segment:
    label: str
    reason: str
    context: str


def fill_text_segments(value: Any, text: str, language: Language) -> list[Segment]:
    """Add a chip for every proposed combination and for every source word."""
    if not isinstance(value, list):
        raise SegmentParseError("combinations must be a list")
    words = split_words(text)
    claimed: set[int] = set()
    placed: list[tuple[int, int, Segment]] = []
    for proposal in value:
        matched = _matched_occurrences(proposal, words, claimed, language)
        if len(matched) < MIN_COMBINATION_WORDS:
            continue
        claimed.update(matched)
        source_order = sorted(matched)
        label = " ".join(words[index] for index in source_order)
        if validate_word(label, language) is not None:
            continue
        reason = display_text(proposal.get("why"), MAX_REASON_LENGTH)
        placed.append((source_order[0], 0, Segment(label, reason, text)))
    # A word stays clickable in its own right even when a combination also claims it,
    # so an imprecise phrase boundary can never cost the learner a lookup.
    placed.extend(
        (index, 1, Segment(word, "", text))
        for index, word in enumerate(words)
        # A chip the submission endpoint would reject is not a lookup the reader can make.
        if validate_word(word, language) is None
    )
    return [segment for _index, _rank, segment in sorted(placed, key=lambda item: item[:2])]


def parse_component_segments(
    value: Any,
    language: Language,
    *,
    context: str,
) -> list[Segment]:
    """Parse all expression components, attaching the example owned by the backend."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise SegmentParseError("segments must be a list")
    result: list[Segment] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        visible = display_text(item.get("surface"), None) or display_text(item.get("label"), None)
        if not visible or validate_word(visible, language) is not None:
            continue
        result.append(
            Segment(
                visible,
                display_text(item.get("why"), MAX_REASON_LENGTH),
                context,
            ),
        )
    return result


def _matched_occurrences(
    proposal: Any,
    words: list[str],
    claimed: set[int],
    language: Language,
) -> list[int]:
    if not isinstance(proposal, dict):
        return []
    surface = display_text(proposal.get("surface"), MAX_SURFACE_LENGTH)
    parts = split_words(re.sub(r"(?:\.\.\.|…)", " ", surface))
    if len(parts) < MIN_COMBINATION_WORDS:
        return []
    available = [index for index in range(len(words)) if index not in claimed]
    matched: list[int] = []
    for part in parts:
        folded = fold_for_match(part, language)
        found = next(
            (index for index in available if fold_for_match(words[index], language) == folded),
            None,
        )
        if found is None:
            continue
        matched.append(found)
        available.remove(found)
    return _repaired(matched, proposal, words, claimed, language)


def _repaired(
    matched: list[int],
    proposal: dict,
    words: list[str],
    claimed: set[int],
    language: Language,
) -> list[int]:
    """Correct the copied boundary against the dictionary form the same answer returned.

    The trim is withheld unless what survives it is the unit itself: dropping a
    negation from a span that still carries free material would card a chip saying
    the opposite of the sentence the reader is looking at.
    """
    excluded = unit_excluded_words(language)
    kept = [index for index in matched if fold_for_match(words[index], language) not in excluded]
    if kept == matched:
        return _with_reflexive(matched, proposal, words, claimed, language)
    candidate = _with_reflexive(kept, proposal, words, claimed, language)
    label = _label_tokens(proposal, language)
    forms = reflexive_forms(language)
    tight = all(
        _accounted(fold_for_match(words[index], language), label)
        or fold_for_match(words[index], language) in forms
        for index in candidate
    )
    if tight:
        return candidate
    return _with_reflexive(matched, proposal, words, claimed, language)


def _with_reflexive(
    matched: list[int],
    proposal: dict,
    words: list[str],
    claimed: set[int],
    language: Language,
) -> list[int]:
    """Take in the reflexive pronoun the dictionary form names and the copy left out."""
    markers = reflexive_markers(language)
    if not matched or not markers & set(_label_tokens(proposal, language)):
        return matched
    forms = reflexive_forms(language)
    if any(fold_for_match(words[index], language) in forms for index in matched):
        return matched
    nearby = [
        index
        for index in range(len(words))
        if index not in claimed
        and index not in matched
        and fold_for_match(words[index], language) in forms
    ]
    if not nearby:
        return matched
    low, high = min(matched), max(matched)
    return [*matched, min(nearby, key=lambda index: min(abs(index - low), abs(index - high)))]


def _label_tokens(proposal: dict, language: Language) -> list[str]:
    label = display_text(proposal.get("label"), MAX_SURFACE_LENGTH)
    return [fold_for_match(part, language) for part in split_words(label)]


def _accounted(token: str, label: list[str]) -> bool:
    return any(token == part or _shares_stem(token, part) for part in label)


def _shares_stem(one: str, other: str) -> bool:
    shared = 0
    for left, right in zip(one, other, strict=False):
        if left != right:
            break
        shared += 1
    return shared >= min(MIN_SHARED_STEM, len(one), len(other))


def display_text(value: Any, limit: int | None) -> str:
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFC", value).strip()
    return text if limit is None else text[:limit]
