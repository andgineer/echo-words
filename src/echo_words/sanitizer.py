"""Server-side sanitizing for the small HTML subset accepted from the LLM."""

import re
import unicodedata
from dataclasses import dataclass
from html import escape

# Matched as whole literals, so no tag can ever carry an attribute — the answer
# has no way to express one, and the frontend renders this straight into v-html.
_ALLOWED = ("b", "i", "table", "tr", "td")
_OPEN_TAGS = {f"<{name}>": name for name in _ALLOWED}
_CLOSE_TAGS = {f"</{name}>": name for name in _ALLOWED}
_TAGS = (*_OPEN_TAGS, *_CLOSE_TAGS)
_STRAY_BRACKET = re.compile(r"<(?=<b>)|(?<=</b>)>")
# Only a doubled run is bold: a lone `*` is an etymology's reconstructed form
# (`*or-*`) or an italic the answer was told not to write, and both print as written.
_BOLD = "**"
_TOKEN = re.compile("|".join(("\n", r"\*+", *map(re.escape, _TAGS))))


@dataclass
class _Run:
    start: int
    end: int
    kept: int = 0
    closes: int = 0
    opens: bool = False


def normalize_emphasis(text: str) -> str:
    """Drop a bracket doubling a bold tag's own, then write Markdown bold as `<b>`."""
    # In this order, so a bracket the answer set beside its `**x**` stays: `*mirъ* <**мир**`.
    return _markdown_bold(_STRAY_BRACKET.sub("", text))


def _markdown_bold(text: str) -> str:
    runs: list[_Run] = []
    openers: list[tuple[_Run, int]] = []
    tags: list[str] = []
    for token in _TOKEN.finditer(text):
        value = token.group()
        if value == "\n":
            openers.clear()
        elif value in _OPEN_TAGS:
            tags.append(_OPEN_TAGS[value])
        elif value in _CLOSE_TAGS:
            # A pair holds only whole tags: one crossing a tag, or holding a close tag
            # the walk escapes, would leave the walk escaping the tags around it.
            if tags and tags[-1] == _CLOSE_TAGS[value]:
                tags.pop()
                # Openers stack in depth order, so the ones inside the closed tag are on top.
                while openers and openers[-1][1] > len(tags):
                    openers.pop()
            else:
                openers.clear()
        elif len(value) >= len(_BOLD):
            runs.append(_paired_run(text, token.start(), token.end(), openers, len(tags)))
    return _rendered(text, runs)


def _paired_run(
    text: str, start: int, end: int, openers: list[tuple[_Run, int]], depth: int
) -> _Run:
    run = _Run(start, end)
    before = text[start - 1] if start else ""
    after = text[end] if end < len(text) else ""
    stars = end - start
    if _flanks(before, after) and openers and openers[-1][1] == depth:
        # The odd star of `*the***` closes the italic inside, so it stays inside the bold.
        run.kept = stars % 2
        stars -= run.kept
        while stars >= len(_BOLD) and openers and openers[-1][1] == depth:
            openers.pop()[0].opens = True
            run.closes += 1
            stars -= len(_BOLD)
    if stars == len(_BOLD) and _flanks(after, before):
        openers.append((run, depth))
    return run


def _flanks(inner: str, outer: str) -> bool:
    """CommonMark's left- or right-flanking test, `inner` being the character the run faces."""
    return not _is_space(inner) and (
        not _is_punctuation(inner) or _is_space(outer) or _is_punctuation(outer)
    )


def _is_space(char: str) -> bool:
    return not char or char.isspace()


def _is_punctuation(char: str) -> bool:
    return bool(char) and unicodedata.category(char)[0] in "PS"


def _rendered(text: str, runs: list[_Run]) -> str:
    pieces: list[str] = []
    position = 0
    for run in runs:
        rest = run.end - run.start - run.kept - len(_BOLD) * run.closes
        tail = "<b>" if run.opens else "*" * rest
        pieces += (text[position : run.start], "*" * run.kept, "</b>" * run.closes, tail)
        position = run.end
    pieces.append(text[position:])
    return "".join(pieces)


def sanitize_html(text: str) -> str:
    """Escape all markup except the balanced tags the answer is allowed to use.

    The function always receives the complete text accumulated so far. This is
    important during streaming: a ``<b>`` split between deltas is escaped while
    incomplete, then becomes an allowed tag in the next replacement update.
    """
    text = normalize_emphasis(text)
    result: list[str] = []
    stack: list[str] = []
    position = 0
    while position < len(text):
        tag = next((candidate for candidate in _TAGS if text.startswith(candidate, position)), None)
        if tag is None:
            result.append(escape(text[position], quote=False))
            position += 1
            continue

        if tag in _OPEN_TAGS:
            result.append(tag)
            stack.append(_OPEN_TAGS[tag])
        elif stack and stack[-1] == _CLOSE_TAGS[tag]:
            result.append(tag)
            stack.pop()
        else:
            result.append(escape(tag, quote=False))
        position += len(tag)

    result.extend(f"</{name}>" for name in reversed(stack))
    return "".join(result)
