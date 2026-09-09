"""The cascade's first step: llmbroker's free pool behind one local mode flag."""

from collections.abc import AsyncGenerator, AsyncIterator
from typing import TYPE_CHECKING

from echo_words.broker import ANSWER_BUDGET_SECONDS, BackendError, BudgetMissError, llmbroker
from echo_words.config import Settings
from echo_words.languages import Language

if TYPE_CHECKING:
    from llmbroker import AsyncBroker, AsyncResult, StreamHandle

# The low end of the ~20-30 s complete-answer budget: it bounds queueing and the
# whole answer in provider time, so the pool's slow entries are cut before their
# first token rather than mid-answer (spec/decision-llm-backend.md).
POOL_WAIT_SECONDS = ANSWER_BUDGET_SECONDS
POOL_FASTEST_OF = 2
# Both pool adapters stay in the code so which one ships is a source-level choice a
# deployment typo cannot reach; the measurement behind the choice is in
# spec/decision-llm-backend.md. The streamed race leaves ``stream_selection_window``
# at llmbroker's default: the reader feels the visible delay more than the replacement.
STREAM_POOL_ANSWERS = True


class PoolReplacementError(Exception):
    """A raced stream lost: every delta already yielded is void and ``result`` is the
    whole answer that won it. Deliberately not a ``BackendError`` — nothing failed, so
    a caller that steps up on one would buy an answer it already has."""

    def __init__(self, result: "AsyncResult", streamed_llm_name: str) -> None:
        super().__init__(
            f"{streamed_llm_name} lost the race to a complete answer from {result.llm_name}",
        )
        self.result = result
        self.streamed_llm_name = streamed_llm_name


class PoolStream:
    """One streamed pool answer with the same error and rating seam as a result.

    Its context is the resource boundary. llmbroker keeps the lanes this call opened
    alive for as long as the handle is, which is what lets ``another()`` hand back an
    answer a losing lane had already written; leaving the context is what gives their
    pool slots back. The broker outlives every request, so nothing else would.
    """

    def __init__(self, handle: "StreamHandle") -> None:
        self._handle = handle
        self._deltas: AsyncGenerator[str] | None = None

    @property
    def llm_name(self) -> str | None:
        return self._handle.llm_name

    async def __aenter__(self) -> "PoolStream":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    def __aiter__(self) -> AsyncIterator[str]:
        if self._deltas is None:
            self._deltas = self._stream()
        return self._deltas

    async def aclose(self) -> None:
        if self._deltas is not None:
            await self._deltas.aclose()
        await self._handle.aclose()

    async def another(self) -> "AsyncResult | None":
        """The next complete answer this same call can still produce, or ``None``.

        Not a second call: it walks the lanes this one already raced, then the models
        it has not tried, inside the wait budget the first answer was asked under.
        """
        errors = llmbroker()
        try:
            return await self._handle.another()
        except errors.LLMRequestError as exc:
            raise pool_error(exc) from exc

    async def _stream(self) -> AsyncGenerator[str]:
        errors = llmbroker()
        try:
            async for delta in self._handle:
                yield delta
        except errors.StreamReplacementError as exc:
            # Caught above the LLMRequestError it subclasses: a complete answer read as
            # a pool failure would step up to the paid model over an answer in hand.
            raise PoolReplacementError(exc.replacement, exc.streamed_llm_name) from exc
        except errors.LLMRequestError as exc:
            raise pool_error(exc) from exc

    async def record_quality(self, score: float) -> None:
        await self._handle.record_quality(score)


async def ask_pool(
    broker: "AsyncBroker",
    prompt: str,
    language: Language,
    settings: Settings,
    *,
    trace_id: str | None = None,
) -> "AsyncResult":
    errors = llmbroker()
    try:
        return await broker.ask(
            prompt,
            operation=f"{settings.llmbroker_operation}-{language.code}",
            trace_id=trace_id,
            wait=POOL_WAIT_SECONDS,
            fastest_of=POOL_FASTEST_OF,
        )
    except errors.LLMRequestError as exc:
        raise pool_error(exc) from exc


def open_pool_stream(
    broker: "AsyncBroker",
    prompt: str,
    language: Language,
    settings: Settings,
    *,
    trace_id: str | None = None,
) -> PoolStream:
    return PoolStream(
        broker.stream(
            prompt,
            operation=f"{settings.llmbroker_operation}-{language.code}",
            trace_id=trace_id,
            wait=POOL_WAIT_SECONDS,
            fastest_of=POOL_FASTEST_OF,
        ),
    )


def pool_error(exc: Exception) -> BackendError:
    errors = llmbroker()
    detail = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, errors.LLMTimeoutError) or (
        isinstance(exc, errors.NoLLMAvailableError) and exc.reason == "timeout"
    ):
        return BudgetMissError(f"the pool missed the answer budget ({detail})")
    return BackendError(f"the pool failed ({detail})")
