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
# first token and a miss carries no half-answer (spec/decision-llm-backend.md).
POOL_WAIT_SECONDS = ANSWER_BUDGET_SECONDS
POOL_FASTEST_OF = 2
# Current streaming races commit on the first delta, whose semantic failure is
# measured in the backend decision. Flip only when llmbroker can protect that path.
STREAM_POOL_ANSWERS = False


class PoolStream:
    """One streamed pool answer with the same error and rating seam as a result."""

    def __init__(self, handle: "StreamHandle") -> None:
        self._handle = handle
        self._deltas: AsyncGenerator[str] | None = None

    @property
    def llm_name(self) -> str | None:
        return self._handle.llm_name

    def __aiter__(self) -> AsyncIterator[str]:
        if self._deltas is None:
            self._deltas = self._stream()
        return self._deltas

    async def aclose(self) -> None:
        if self._deltas is not None:
            await self._deltas.aclose()
        await self._handle.aclose()

    async def _stream(self) -> AsyncGenerator[str]:
        errors = llmbroker()
        try:
            async for delta in self._handle:
                yield delta
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
