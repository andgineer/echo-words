"""The dispatcher: every answer starts on the pool and steps up to the paid model."""

import logging
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from echo_words.api_backend import stream_api
from echo_words.broker import BackendError, BudgetMissError, paid_alias
from echo_words.config import Settings
from echo_words.languages import Language
from echo_words.llm_backend import PoolStream, open_pool_stream
from echo_words.prompt import MAX_COMPLETE_ANSWER_CHARS

if TYPE_CHECKING:
    from llmbroker import AsyncBroker

ResetHook = Callable[[], Awaitable[None]]
AnswerCheck = Callable[[str], bool]

logger = logging.getLogger(__name__)


def utc_today() -> date:
    return datetime.now(tz=UTC).date()


@dataclass(frozen=True)
class CallRequest:
    """What one answer is asked for: the prompt, its language and the entry it belongs to."""

    prompt: str
    language: Language
    trace_id: str | None = None
    on_reset: ResetHook | None = None
    usable: AnswerCheck | None = None


@dataclass(frozen=True)
class CallRecord:
    """What answered, how it ended and when — the memory `/api/status` reads."""

    llm_name: str | None
    paid: bool
    ok: bool
    at: datetime
    error: str | None = None


class Completion:
    """One answer: the deltas, who produced them, and the rating hook for that call."""

    def __init__(
        self,
        cascade: "Cascade",
        request: CallRequest,
        *,
        paid_only: bool = False,
    ) -> None:
        self._cascade = cascade
        self._request = request
        self._paid_only = paid_only
        self._deltas: AsyncGenerator[str] | None = None
        self._pool: PoolStream | None = None
        self._pool_answered = False
        self._rated = False
        self._oversized = False
        self.llm_name: str | None = None
        self.paid = paid_only

    def __aiter__(self) -> AsyncIterator[str]:
        if self._deltas is None:
            self._deltas = self._recorded()
        return self._deltas

    @property
    def oversized(self) -> bool:
        """Whether the final attempted answer exceeded the complete-answer bound."""
        return self._oversized

    async def aclose(self) -> None:
        if self._deltas is not None:
            await self._deltas.aclose()

    async def record_quality(self, score: float) -> None:
        """Rate the pool call that answered, once; an abandoned or stepped-up stream is
        not rated, and a rating the cascade already gave stands."""
        if self._rated or self._pool is None or not self._pool_answered:
            return
        self._rated = True
        await self._pool.record_quality(score)

    async def _recorded(self) -> AsyncGenerator[str]:
        # Every nested generator is closed through ``aclosing``: an ``async for``
        # alone leaves the one it drives to the garbage collector, and the pool's
        # slot would then come back whenever that happened to run.
        try:
            async with aclosing(self._answer()) as answer:
                async for delta in answer:
                    yield delta
        except BackendError as exc:
            self._cascade.record_call(
                self._request.language,
                self.llm_name,
                paid=self.paid,
                ok=False,
                error=str(exc),
            )
            raise
        self._cascade.record_call(
            self._request.language,
            self.llm_name,
            paid=self.paid,
            ok=True,
        )

    async def _answer(self) -> AsyncIterator[str]:
        if self._paid_only:
            async with aclosing(self._paid_deltas()) as paid:
                async for delta in self._bounded_deltas(paid):
                    yield delta
            return
        delivered: list[str] = []
        miss: BudgetMissError | None = None
        try:
            async with aclosing(self._pool_deltas()) as pool:
                async for delta in self._bounded_deltas(pool):
                    delivered.append(delta)
                    yield delta
        except BudgetMissError as exc:
            miss = exc
        if not await self._steps_up(miss, "".join(delivered)):
            return
        # Text already on the page cannot be spliced with the paid answer: the
        # pipeline is told to drop it before the second step starts.
        if delivered and self._request.on_reset is not None:
            await self._request.on_reset()
        self._oversized = False
        async with aclosing(self._paid_deltas()) as paid:
            async for delta in self._bounded_deltas(paid):
                yield delta

    async def _steps_up(self, miss: BudgetMissError | None, answer: str) -> bool:
        """Whether the paid model takes the request over from the pool."""
        if (
            miss is None
            and not self._oversized
            and (self._request.usable is None or self._request.usable(answer))
        ):
            return False
        refusal = self._cascade.paid_refusal(self._request.language)
        if miss is not None:
            if refusal is not None:
                raise BackendError(f"{miss}; paid step unavailable: {refusal}") from miss
            return True
        # An answer the caller cannot use is no more complete than one that never
        # arrived: it is rated down here, and stands only when nothing can replace it.
        await self.record_quality(0.0)
        return refusal is None

    async def _bounded_deltas(self, stream: AsyncIterator[str]) -> AsyncIterator[str]:
        remaining = MAX_COMPLETE_ANSWER_CHARS
        async for delta in stream:
            if self._oversized:
                # Drain to settlement without retaining or exposing more output.
                # A settled pool call can then receive the required quality score.
                continue
            bounded = delta[:remaining]
            if bounded:
                yield bounded
                remaining -= len(bounded)
            if len(bounded) != len(delta):
                self._oversized = True
                logger.warning(
                    "LLM answer exceeded the %s-character complete-answer bound",
                    MAX_COMPLETE_ANSWER_CHARS,
                )

    async def _pool_deltas(self) -> AsyncIterator[str]:
        pool = open_pool_stream(
            self._cascade.broker,
            self._request.prompt,
            self._request.language,
            self._cascade.settings,
            trace_id=self._request.trace_id,
        )
        self._pool = pool
        async with aclosing(pool):
            async for delta in pool:
                self.llm_name = pool.llm_name
                yield delta
        self._pool_answered = True

    async def _paid_deltas(self) -> AsyncIterator[str]:
        alias = self._cascade.paid_alias(self._request.language)
        self.paid = True
        self.llm_name = alias
        paid_stream = stream_api(
            self._cascade.broker,
            alias,
            self._request.prompt,
            on_resolved=lambda: self._cascade.spend_paid_call(self._request.language),
        )
        async with aclosing(paid_stream) as paid:
            async for delta in paid:
                yield delta


class Cascade:
    """The single seam the pipeline calls, and the one wallet the paid step spends from."""

    def __init__(self, broker: "AsyncBroker", settings: Settings) -> None:
        self.broker = broker
        self.settings = settings
        self._paid_calls = 0
        self.last_calls: dict[str, CallRecord] = {}
        self._direct_refusals: dict[str, str] = {}
        self._day = utc_today()

    @property
    def calls_today(self) -> int:
        self._roll_over()
        return self._paid_calls

    def stream_completion(
        self,
        prompt: str,
        language: Language,
        *,
        trace_id: str | None = None,
        on_reset: ResetHook | None = None,
        usable: AnswerCheck | None = None,
    ) -> Completion:
        request = CallRequest(
            prompt,
            language,
            trace_id=trace_id,
            on_reset=on_reset,
            usable=usable,
        )
        return Completion(self, request)

    def stream_paid(
        self,
        prompt: str,
        language: Language,
        *,
        trace_id: str | None = None,
    ) -> Completion:
        """The paid model asked for by name — the deeper analysis and the card rebuild."""
        refusal = self.paid_refusal(language)
        if refusal is not None:
            raise BackendError(refusal)
        request = CallRequest(prompt, language, trace_id=trace_id)
        return Completion(self, request, paid_only=True)

    def paid_alias(self, language: Language) -> str:
        return paid_alias(language, self.settings)

    def paid_refusal(self, language: Language) -> str | None:
        """Why the paid step cannot happen, or ``None`` when it can."""
        alias = self.paid_alias(language)
        if not alias:
            return "no paid model is configured"
        if refusal := self._direct_refusals.get(alias):
            return refusal
        self._roll_over()
        cap = self.settings.api_daily_cap
        if cap and self.calls_today >= cap:
            return f"the daily paid-call cap ({cap}) is spent"
        return None

    async def refresh_paid_availability(self, language: Language) -> str | None:
        """Refresh local key diagnostics before accepting an explicit paid job."""
        try:
            snapshot = await self.broker.snapshot()
        except Exception as exc:  # noqa: BLE001 - the direct call is the final authority.
            # snapshot() is local, but a corrupt journal should not prevent a
            # direct client from reporting its own more precise error.
            logging.getLogger(__name__).debug("paid availability snapshot failed: %s", exc)
        else:
            self.note_snapshot(snapshot)
        return self.paid_refusal(language)

    def note_snapshot(self, snapshot: object) -> None:
        """Cache direct-key refusals from llmbroker's local snapshot."""
        refusals: dict[str, str] = {}
        for missing in getattr(snapshot, "direct_missing_keys", ()):
            key = getattr(missing, "api_key_ref", "")
            help_text = getattr(missing, "help", "")
            reason = f"the paid model is missing {key}" if key else "the paid model key is missing"
            if help_text:
                reason = f"{reason}: {help_text}"
            for alias in getattr(missing, "entry_names", ()):
                refusals[str(alias)] = reason
        self._direct_refusals = refusals

    def spend_paid_call(self, language: Language) -> None:
        refusal = self.paid_refusal(language)
        if refusal is not None:
            raise BackendError(refusal)
        self._paid_calls += 1

    def record_call(
        self,
        language: Language,
        llm_name: str | None,
        *,
        paid: bool,
        ok: bool,
        error: str | None = None,
    ) -> None:
        self.last_calls[language.code] = CallRecord(
            llm_name=llm_name,
            paid=paid,
            ok=ok,
            at=datetime.now(tz=UTC),
            error=error,
        )

    def _roll_over(self) -> None:
        today = utc_today()
        if today != self._day:
            self._day = today
            self._paid_calls = 0
