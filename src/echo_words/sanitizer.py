"""Server-side sanitizing for the small HTML subset accepted from the LLM."""

from html import escape

_OPEN_TAGS = {"<b>": "b", "<i>": "i"}
_CLOSE_TAGS = {"</b>": "b", "</i>": "i"}
_TAGS = (*_OPEN_TAGS, *_CLOSE_TAGS)


def sanitize_html(text: str) -> str:
    """Escape all markup except balanced ``b`` and ``i`` tags.

    The function always receives the complete text accumulated so far. This is
    important during streaming: a ``<b>`` split between deltas is escaped while
    incomplete, then becomes an allowed tag in the next replacement update.
    """
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
