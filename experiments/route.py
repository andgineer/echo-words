"""Input-shape routing: word/collocation vs sentence, measured instead of guessed.

The heuristic decides which prompt an input gets and — because a sentence never
becomes a card — whether the deck is touched at all. Its two error directions
are not equally bad, so they are counted separately:

    dangerous   a clause routed to lexeme mode: it becomes a card with a whole
                sentence on the front, and nothing catches it afterwards
    benign      a fixed expression routed to sentence mode: the answer still
                explains it, the segment list is expected to offer it back as
                the first chip, and one tap recovers the card

So the sweep minimises benign errors subject to dangerous errors being zero,
rather than maximising plain accuracy.

Run:  python experiments/route.py
"""

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bench_items import COLLOCATIONS, ITEMS, ROUTING_EXTRA, SENTENCES  # noqa: E402

INTERNAL = ",;:—–"
MAX_WORD_LENGTH = 50  # languages.MAX_WORD_LENGTH — the canonical-word limit

_EDGE = re.compile(r"^[^\w]+|[^\w]+$", re.UNICODE)

# Clauses short enough to stand inside the unit band. They read as sentences, and
# the routing truth is still lexeme: the band takes them on purpose, so a rule that
# sent them to sentence mode again would show up here as a benign error.
ROUTED_WHOLE = {
    "Wie geht es dir?": "lexeme",
    "Како си?": "lexeme",
    "Данас је лепо време.": "lexeme",
}


def tokens(text: str) -> list[str]:
    """The PWA's own tokenisation (AddView.splitPhrase), so routing sees what the user sees."""
    return [t for t in (_EDGE.sub("", part) for part in text.split()) if t]


def classify(text: str, *, max_tokens: int, max_chars: int = MAX_WORD_LENGTH) -> str:
    text = unicodedata.normalize("NFC", text).strip()
    if len(tokens(text)) <= 1:
        return "lexeme"
    if any(char in text for char in INTERNAL):
        return "sentence"
    if len(text) > max_chars:
        return "sentence"
    if len(tokens(text)) > max_tokens:
        return "sentence"
    return "lexeme"


def fixtures(lang: str) -> list[tuple[str, str, str]]:
    """(text, truth, origin) for one language."""
    rows = [(word, "lexeme", shape) for word, shape in ITEMS[lang]]
    rows += [(text, "lexeme", shape) for text, shape in COLLOCATIONS[lang]]
    rows += [(text, "sentence", kind) for text, _expected, kind in SENTENCES[lang]]
    rows += [(text, truth, "extra") for text, truth in ROUTING_EXTRA[lang]]
    return [(text, ROUTED_WHOLE.get(text, truth), origin) for text, truth, origin in rows]


def sweep(langs: list[str], thresholds: range) -> None:
    rows = [(lang, *row) for lang in langs for row in fixtures(lang)]
    print(f"{len(rows)} fixtures over {', '.join(langs)}\n")
    print(f"{'max_tokens':>10} {'dangerous':>10} {'benign':>7} {'accuracy':>9}")
    for limit in thresholds:
        dangerous = [r for r in rows if r[2] == "sentence" and classify(r[1], max_tokens=limit) == "lexeme"]
        benign = [r for r in rows if r[2] == "lexeme" and classify(r[1], max_tokens=limit) == "sentence"]
        acc = (len(rows) - len(dangerous) - len(benign)) / len(rows)
        print(f"{limit:>10} {len(dangerous):>10} {len(benign):>7} {acc:>8.1%}")
    print()
    for limit in thresholds:
        dangerous = [r for r in rows if r[2] == "sentence" and classify(r[1], max_tokens=limit) == "lexeme"]
        benign = [r for r in rows if r[2] == "lexeme" and classify(r[1], max_tokens=limit) == "sentence"]
        print(f"--- max_tokens={limit} ---")
        for lang, text, _truth, origin in dangerous:
            print(f"  DANGEROUS {lang} [{origin}] {text!r}")
        for lang, text, _truth, origin in benign:
            print(f"  benign    {lang} [{origin}] {text!r}")
        if not dangerous and not benign:
            print("  (clean)")
    print()


if __name__ == "__main__":
    sweep(["de", "sr"], range(2, 7))
