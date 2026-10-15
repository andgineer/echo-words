"""Server-side sanitizing for the small HTML subset accepted from the LLM."""

import re
from html import escape

# Matched as whole literals, so no tag can ever carry an attribute — the answer
# has no way to express one, and the frontend renders this straight into v-html.
_ALLOWED = ("b", "i", "table", "tr", "td")
_OPEN_TAGS = {f"<{name}>": name for name in _ALLOWED}
_CLOSE_TAGS = {f"</{name}>": name for name in _ALLOWED}
_TAGS = (*_OPEN_TAGS, *_CLOSE_TAGS)
# Only a doubled pair is bold: a lone `*` is an etymology's reconstructed form
# (`*or-*`) or an italic the answer was told not to write, and both print as written.
_MARKDOWN_BOLD = re.compile(
    r"(?<!\*)\*\*(?=\S)((?:[^*\n]|(?<!\*)\*(?!\*))+?\*?)(?<=\S)\*\*(?!\*(?!\*))",
)
_STRAY_BRACKET = re.compile(r"<(?=<b>)|(?<=</b>)>")


def normalize_emphasis(text: str) -> str:
    """Write Markdown bold as `<b>` and drop a bracket doubling a bold tag's own."""
    # Repeated, so a pair nested in another is read from the inside out.
    while (bolded := _MARKDOWN_BOLD.sub(r"<b>\1</b>", text)) != text:
        text = bolded
    return _STRAY_BRACKET.sub("", text)


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
