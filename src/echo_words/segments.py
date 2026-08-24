"""The units of a running text that are worth looking up on their own."""

import json
import unicodedata
from dataclasses import dataclass
from typing import Any

from echo_words.languages import Language, validate_word

MAX_SEGMENTS = 5
MAX_SURFACE_LENGTH = 120
MAX_REASON_LENGTH = 200


class SegmentParseError(ValueError):
    """The segment payload is not usable as a list of suggested units."""


@dataclass(frozen=True)
class Segment:
    label: str
    surface: str
    reason: str


def parse_segments_payload(payload: str, language: Language) -> list[Segment]:
    """Parse one JSON object, ignoring text after it; an empty list is a valid answer."""
    try:
        value, _end = json.JSONDecoder().raw_decode(payload.lstrip())
    except (json.JSONDecodeError, TypeError) as exc:
        raise SegmentParseError(f"segment payload is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SegmentParseError("segment payload must be an object")
    listed = value.get("segments")
    if not isinstance(listed, list):
        raise SegmentParseError("segments must be a list")
    segments: list[Segment] = []
    seen: set[str] = set()
    for item in listed:
        segment = _segment(item, language)
        if segment is None or segment.label in seen:
            continue
        seen.add(segment.label)
        segments.append(segment)
        if len(segments) == MAX_SEGMENTS:
            break
    return segments


def _segment(value: Any, language: Language) -> Segment | None:
    if not isinstance(value, dict):
        return None
    # One tap turns a label into the front of a real note, so it is held to the rule a
    # typed word is held to; a label that would have been refused is dropped silently.
    label = _display_text(value.get("label"), None)
    if not label or validate_word(label, language) is not None:
        return None
    return Segment(
        label=label,
        surface=_display_text(value.get("surface"), MAX_SURFACE_LENGTH),
        reason=_display_text(value.get("why"), MAX_REASON_LENGTH),
    )


def _display_text(value: Any, limit: int | None) -> str:
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFC", value).strip()
    return text if limit is None else text[:limit]
