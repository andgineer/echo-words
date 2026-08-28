"""Suggested lookup targets derived from a model answer and the submitted text."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from echo_words.languages import Language, fold_for_match, split_words, validate_word

MAX_SURFACE_LENGTH = 120
MAX_REASON_LENGTH = 200
MIN_COMBINATION_WORDS = 2


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
    return matched


def display_text(value: Any, limit: int | None) -> str:
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFC", value).strip()
    return text if limit is None else text[:limit]
