"""A follow-up question about an entry: its context, its bound, and its streamed reply."""

import asyncio
import contextlib
import logging
import re
from collections.abc import AsyncIterator, Iterable
from contextlib import aclosing
from dataclasses import dataclass, field
from html import unescape
from typing import Literal

from echo_words.backend import Cascade
from echo_words.broker import BackendError
from echo_words.i18n import message
from echo_words.languages import Language, sanitize_context
from echo_words.prompt import Chip, Exchange, FollowUpMaterial, build_follow_up_prompt

MAX_QUESTION_CHARS = 1_000
# Several times a card, its deeper article and a long conversation (under 10 000), yet
# inside the context and per-minute token allowance of the pool's smaller models.
MAX_FOLLOW_UP_PROMPT_CHARS = 32_000

_CELL_BREAK = re.compile(r"\s*</td>\s*<td>\s*", re.IGNORECASE)
_ROW_EDGE = re.compile(r"(?:\s*</?tr>\s*)+", re.IGNORECASE)
_LINE_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"</?[A-Za-z][^<>]*>")
_BLANK_LINES = re.compile(r"\n{3,}")

logger = logging.getLogger(__name__)

type ReplyEventName = Literal["delta", "reset", "done", "error"]


class FollowUpRefusedError(ValueError):
    """The question cannot be asked as sent; the message is the reader's."""

    def __init__(self, detail: str, *, too_large: bool = False) -> None:
        super().__init__(detail)
        self.too_large = too_large


@dataclass(frozen=True)
class ReplyEvent:
    name: ReplyEventName
    data: dict[str, object] = field(default_factory=dict)


def reading_text(html: str) -> str:
    text = _CELL_BREAK.sub(" | ", html)
    text = _ROW_EDGE.sub("\n", text)
    text = _LINE_BREAK.sub("\n", text)
    # Markup the sanitizer refused is already escaped, so it survives as the text it shows.
    text = unescape(_TAG.sub("", text))
    lines = "\n".join(line.rstrip() for line in text.splitlines())
    return _BLANK_LINES.sub("\n\n", lines).strip()


def follow_up_material(  # noqa: PLR0913 - everything the reader can see on the entry.
    *,
    submitted: str,
    question: str,
    analysis_html: str,
    analysed_as: str = "",
    context: str = "",
    chips: Iterable[Chip] = (),
    detail_html: str = "",
    exchanges: Iterable[Exchange] = (),
) -> FollowUpMaterial:
    return FollowUpMaterial(
        submitted=submitted.strip(),
        question=question.strip(),
        analysis=reading_text(analysis_html),
        analysed_as=analysed_as.strip(),
        context=sanitize_context(context),
        chips=tuple(
            Chip(chip.label.strip(), chip.note.strip()) for chip in chips if chip.label.strip()
        ),
        detail=reading_text(detail_html),
        exchanges=tuple(
            Exchange(exchange.question.strip(), exchange.answer.strip())
            for exchange in exchanges
            if exchange.question.strip() and exchange.answer.strip()
        ),
    )


def follow_up_prompt(
    language: Language,
    target_lang: str,
    material: FollowUpMaterial,
    *,
    locale: str,
) -> str:
    if not material.question:
        raise FollowUpRefusedError(message("question.empty", locale))
    if len(material.question) > MAX_QUESTION_CHARS:
        raise FollowUpRefusedError(message("question.too_long", locale, limit=MAX_QUESTION_CHARS))
    prompt = build_follow_up_prompt(language, target_lang, material, locale=locale)
    if len(prompt) > MAX_FOLLOW_UP_PROMPT_CHARS:
        raise FollowUpRefusedError(
            message(
                "question.too_much",
                locale,
                length=len(prompt),
                limit=MAX_FOLLOW_UP_PROMPT_CHARS,
            ),
            too_large=True,
        )
    return prompt


async def reply_events(
    cascade: Cascade,
    prompt: str,
    language: Language,
    *,
    trace_id: str,
    locale: str,
) -> AsyncIterator[ReplyEvent]:
    replaced = False

    async def reset() -> None:
        nonlocal replaced
        replaced = True

    completion = cascade.stream_completion(
        prompt,
        language,
        trace_id=trace_id,
        on_reset=reset,
        pool_only=True,
        reported=False,
    )
    written = False
    try:
        async with aclosing(completion):
            async for delta in completion:
                if replaced:
                    # The text shown so far lost the race to a whole answer from another model.
                    replaced = False
                    yield ReplyEvent("reset")
                written = True
                yield ReplyEvent("delta", {"text": delta})
    except BackendError:
        key = "question.broken_off" if written else "question.no_reply"
        yield ReplyEvent("error", {"detail": message(key, locale), "retryable": True})
        return
    await completion.record_quality(0.0 if completion.oversized else 1.0)
    yield ReplyEvent("done", {"model": completion.llm_name, "complete": not completion.oversized})


class ReplyPump:
    """Runs a reply in a task of its own, so the request can wait for its first event
    and the response can stream the rest: the pool's stream stays in one task."""

    def __init__(self, events: AsyncIterator[ReplyEvent]) -> None:
        self._queue: asyncio.Queue[ReplyEvent | None] = asyncio.Queue()
        self._task = asyncio.create_task(self._pump(events), name="echo-words-follow-up")

    async def _pump(self, events: AsyncIterator[ReplyEvent]) -> None:
        try:
            async with aclosing(events) as stream:
                async for event in stream:
                    self._queue.put_nowait(event)
        except Exception:
            # The reader is left with a reply that never says it is done, which the page
            # treats as interrupted; the cause is only ever seen here.
            logger.exception("the follow-up reply failed unexpectedly")
        finally:
            self._queue.put_nowait(None)

    async def next(self) -> ReplyEvent | None:
        return await self._queue.get()

    async def aclose(self) -> None:
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
