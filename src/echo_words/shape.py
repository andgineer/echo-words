"""Whether a submitted string is one unit to analyse or running text to explain."""

import unicodedata
from typing import Literal

from echo_words.languages import MAX_WORD_LENGTH, split_words

Shape = Literal["unit", "text"]

MAX_UNIT_WORDS = 4
INTERNAL_MARKS = ",;:—–"


def word_count(text: str) -> int:
    return len(split_words(text))


def classify(text: str) -> Shape:
    """Route by punctuation and length alone — no language knowledge, every language alike."""
    text = unicodedata.normalize("NFC", text).strip()
    words = word_count(text)
    if words <= 1:
        return "unit"
    if any(char in text for char in INTERNAL_MARKS):
        return "text"
    if len(text) > MAX_WORD_LENGTH:
        return "text"
    if words > MAX_UNIT_WORDS:
        return "text"
    return "unit"
