"""The cascade's second step: llmbroker's direct client on one named paid model."""

from collections.abc import AsyncIterator, Callable, Mapping
from typing import TYPE_CHECKING

from echo_words.broker import ANSWER_BUDGET_SECONDS, BackendError, llmbroker

if TYPE_CHECKING:
    from llmbroker import AsyncBroker

API_TIMEOUT_SECONDS = ANSWER_BUDGET_SECONDS


async def stream_api(  # noqa: PLR0913 - one call, and every setting the caller puts on it.
    broker: "AsyncBroker",
    alias: str,
    prompt: str,
    *,
    timeout: float = API_TIMEOUT_SECONDS,
    params: Mapping[str, object] | None = None,
    on_resolved: Callable[[], None] | None = None,
) -> AsyncIterator[str]:
    errors = llmbroker()
    try:
        client = await broker.direct(alias)
    except errors.LLMRequestError as exc:
        raise BackendError(
            f"the paid model {alias!r} is unreachable ({type(exc).__name__}: {exc})",
        ) from exc
    if on_resolved is not None:
        on_resolved()
    try:
        # The client borrows the broker's one shared httpx client: closing it here
        # would close it for every later call, so it is never closed by echo-words.
        async for delta in client.stream(prompt, timeout=timeout, params=params):
            yield delta
    except errors.LLMRequestError as exc:
        raise BackendError(
            f"the paid model {alias!r} failed ({type(exc).__name__}: {exc})",
        ) from exc
