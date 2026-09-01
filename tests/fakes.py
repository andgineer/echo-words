"""Fakes for the LLM boundary: no pool, no provider, no network."""

from collections.abc import AsyncIterator, Iterable
from types import SimpleNamespace

from llmbroker import InvalidProviderResponseError

from echo_words.backend import Cascade
from echo_words.config import Settings


class FakeHandle:
    """Stands in for llmbroker's ``StreamHandle``: deltas, identity, rating, close."""

    def __init__(
        self,
        deltas: Iterable[str] = (),
        *,
        error: Exception | None = None,
        llm_name: str | None = "pool-model",
    ) -> None:
        self.deltas = list(deltas)
        self.error = error
        self.llm_name = llm_name
        self.closed = False
        self.scores: list[float] = []
        self.delivered: list[str] = []
        self.settled = False
        self._iterator = self._stream()

    def __aiter__(self) -> AsyncIterator[str]:
        return self._iterator

    async def _stream(self) -> AsyncIterator[str]:
        for delta in self.deltas:
            self.delivered.append(delta)
            yield delta
        if self.error is not None:
            raise self.error
        if not self.delivered:
            raise InvalidProviderResponseError(
                "the provider returned no text",
                model=self.llm_name or "unknown",
            )
        self.settled = True

    async def aclose(self) -> None:
        await self._iterator.aclose()
        self.closed = True

    async def record_quality(self, score: float) -> None:
        if not self.settled:
            raise ValueError("a streamed call becomes rateable only after its answer ends")
        self.scores.append(score)


class FakeDirectClient:
    """Stands in for llmbroker's ``AsyncDirectClient``: one named paid model."""

    def __init__(self, deltas: Iterable[str] = ("paid ", "answer"), *, error=None) -> None:
        self.deltas = list(deltas)
        self.error = error
        self.closed = False
        self.calls: list[dict] = []

    async def stream(self, prompt: str, *, timeout: float | None = None) -> AsyncIterator[str]:
        self.calls.append({"prompt": prompt, "timeout": timeout})
        produced = False
        for delta in self.deltas:
            produced = True
            yield delta
        if self.error is not None:
            raise self.error
        if not produced:
            raise InvalidProviderResponseError("the provider returned no text", model="direct")

    async def aclose(self) -> None:
        self.closed = True


ATTESTATION_MARK = "You judge whether a wording is actually used"
VOUCHED_ANSWER = '{"used": true, "where": "everyday"}'


class FakeBroker:
    """Stands in for the one ``AsyncBroker``: hands out prepared handles and clients."""

    def __init__(  # noqa: PLR0913
        self,
        home=None,
        direct: Iterable[str] = (),
        *,
        handles: Iterable[FakeHandle] = (),
        client: FakeDirectClient | None = None,
        direct_error: Exception | None = None,
        snapshot: object | None = None,
        stats: dict[str, object] | None = None,
        attestation: str = VOUCHED_ANSWER,
    ) -> None:
        self.home = home
        self.direct_aliases = list(direct)
        self.handles = list(handles)
        self.client = client
        self.direct_error = direct_error
        self.stream_calls: list[dict] = []
        self.attestation_calls: list[str] = []
        self.attestation = attestation
        self.direct_calls: list[str] = []
        self.closed = False
        self.snapshot_value = snapshot or SimpleNamespace(
            providers_usable=0,
            providers_total=0,
            degraded=False,
            missing_keys=(),
            direct_missing_keys=(),
        )
        self.stats_values = stats or {}

    def stream(
        self,
        prompt: str,
        *,
        operation: str | None = None,
        trace_id: str | None = None,
        wait: float | None = None,
    ) -> FakeHandle:
        self.stream_calls.append(
            {"prompt": prompt, "operation": operation, "trace_id": trace_id, "wait": wait},
        )
        if ATTESTATION_MARK in prompt:
            # Answered off the prepared handles and in any order: it runs in parallel
            # with the article, so a test cannot script it by position.
            self.attestation_calls.append(prompt)
            return FakeHandle([self.attestation])
        if not self.handles:
            raise AssertionError("the pool was asked for one stream more than the test prepared")
        return self.handles.pop(0)

    async def direct(self, alias: str) -> FakeDirectClient:
        self.direct_calls.append(alias)
        if self.direct_error is not None:
            raise self.direct_error
        if self.client is None:
            self.client = FakeDirectClient()
        return self.client

    async def aclose(self) -> None:
        self.closed = True

    async def snapshot(self):
        return self.snapshot_value

    async def stats(self, *, operation=None, **_kwargs):
        return self.stats_values.get(operation, {})


def fake_cascade(settings: Settings, **broker: object) -> Cascade:
    """A cascade over a ``FakeBroker``, which the test reaches as ``cascade.broker``."""
    return Cascade(FakeBroker(**broker), settings)
