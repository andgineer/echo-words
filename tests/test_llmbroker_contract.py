# The rest of the suite fakes the broker. Here echo-words' call sites drive the installed
# llmbroker itself, and only provider HTTP and the curated-list fetch are faked.

import asyncio
import io
import json
import os
import re
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import AsyncIterator, Callable
from contextlib import aclosing, asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from email.message import Message
from importlib import resources
from pathlib import Path

import httpx
import llmbroker
import pytest
from fastapi.testclient import TestClient
from llmbroker import AsyncBroker, CuratedModel, LLMConfig

from echo_words.api import create_app
from echo_words.api_backend import stream_api
from echo_words.backend import Cascade
from echo_words.broker import BackendError, BudgetMissError, create_broker, paid_aliases
from echo_words.config import Settings
from echo_words.languages import Language
from echo_words.llm_backend import ask_pool, open_pool_stream

pytestmark = pytest.mark.anyio

CURATED_HOST = "https://raw.githubusercontent.com/"
USAGE = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}


@dataclass(frozen=True)
class Answer:
    deltas: tuple[str, ...]
    # Streamed replies only: what follows the first delta waits for it, which is how a
    # test decides which of two racing lanes finishes first.
    hold: asyncio.Event | None = None


@dataclass(frozen=True)
class Refusal:
    status: int
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Silence:
    """The provider never answers, and httpx gives up on the read."""


Reply = Answer | Refusal | Silence


@dataclass(frozen=True)
class Sent:
    host: str
    model: str
    stream: bool
    authorization: str


@dataclass(frozen=True)
class Curated:
    """What the installed llmbroker ships: the models echo-words' calls can land on."""

    # Pool entries whose key pays for no other entry, so one key admits exactly one lane.
    pool: tuple[LLMConfig, ...]
    pool_refs: frozenset[str]
    alias: str
    paid: CuratedModel
    refs: frozenset[str]


def fake_key(ref: str) -> str:
    return f"fake-{ref.lower()}"


def sse(chunk: dict) -> bytes:
    return f"data: {json.dumps(chunk)}\n\n".encode()


async def events(answer: Answer) -> AsyncIterator[bytes]:
    first, *rest = answer.deltas
    yield sse({"choices": [{"index": 0, "delta": {"content": first}}]})
    if answer.hold is not None:
        await answer.hold.wait()
    for delta in rest:
        yield sse({"choices": [{"index": 0, "delta": {"content": delta}}]})
    yield sse({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
    yield sse({"choices": [], "usage": USAGE})
    yield b"data: [DONE]\n\n"


class Wire:
    """Every provider llmbroker calls and the host it fetches curated lists from."""

    def __init__(self) -> None:
        self.replies: dict[str, Reply] = {}
        self.sent: list[Sent] = []
        self.fetched: list[str] = []
        self.clients: list[httpx.AsyncClient] = []

    def reply(self, model: str, reply: Reply) -> None:
        self.replies[model] = reply

    def to(self, model: str) -> list[Sent]:
        return [sent for sent in self.sent if sent.model == model]

    async def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions"), request.url
        body = json.loads(request.content)
        stream = bool(body.get("stream"))
        self.sent.append(
            Sent(request.url.host, body["model"], stream, request.headers["authorization"]),
        )
        reply = self.replies.get(body["model"], Answer((f"{body['model']} answers",)))
        if isinstance(reply, Silence):
            raise httpx.ReadTimeout("the provider did not answer in time", request=request)
        if isinstance(reply, Refusal):
            return httpx.Response(reply.status, headers=reply.headers, json={"error": "scripted"})
        if stream:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=events(reply),
            )
        message = {"role": "assistant", "content": "".join(reply.deltas)}
        return httpx.Response(
            200,
            json={
                "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                "usage": USAGE,
            },
        )

    def urlopen(self, url: object, timeout: float | None = None) -> io.BytesIO:
        target = url if isinstance(url, str) else url.full_url
        assert target.startswith(CURATED_HOST), target
        self.fetched.append(target)
        bundled = resources.files("llmbroker").joinpath("presets", target.rsplit("/", 1)[-1])
        if not bundled.is_file():
            raise urllib.error.HTTPError(target, 404, "Not Found", Message(), None)
        return io.BytesIO(bundled.read_bytes())


@pytest.fixture(autouse=True)
def _no_real_broker() -> None:
    """Overrides the suite-wide fake broker: this module runs the real one."""


@pytest.fixture
def curated(settings: Settings, languages: dict[str, Language], tmp_path: Path) -> Curated:
    home = tmp_path / "curated"
    pool = llmbroker.curated_pool(home=home).configs
    per_ref = Counter(entry.api_key_ref for entry in pool)
    (alias,) = paid_aliases(languages, settings)
    paid = next(row for row in llmbroker.curated_paid(home=home) if row.alias == alias)
    providers = llmbroker.curated_providers(home=home)
    return Curated(
        pool=tuple(entry for entry in pool if per_ref[entry.api_key_ref] == 1),
        pool_refs=frozenset(per_ref),
        alias=alias,
        paid=paid,
        refs=frozenset({*per_ref, *(provider.api_key_ref for provider in providers)}),
    )


@pytest.fixture(autouse=True)
def wire(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    settings: Settings,
    curated: Curated,
) -> Wire:
    wire = Wire()
    for name in {*curated.refs, *(name for name in os.environ if name.endswith("_API_KEY"))}:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("LLMBROKER_HOME", raising=False)
    # llmbroker also reads keys from a .env in the working directory.
    monkeypatch.chdir(tmp_path)
    assert settings.llmbroker_home.is_relative_to(tmp_path)

    build = httpx.AsyncClient.__init__

    def mocked(client: httpx.AsyncClient, *args: object, **kwargs: object) -> None:
        kwargs["transport"] = httpx.MockTransport(wire.handle)
        build(client, *args, **kwargs)
        wire.clients.append(client)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", mocked)
    monkeypatch.setattr(urllib.request, "urlopen", wire.urlopen)
    return wire


@pytest.fixture
def pay(monkeypatch: pytest.MonkeyPatch, wire: Wire) -> Callable[..., None]:
    def pay(*refs: str) -> None:
        for ref in refs:
            monkeypatch.setenv(ref, fake_key(ref))

    return pay


@asynccontextmanager
async def running(
    settings: Settings,
    languages: dict[str, Language],
) -> AsyncIterator[AsyncBroker]:
    # Not ``async with`` on the broker: echo-words never enters it, and entering is
    # itself something llmbroker releases have changed.
    broker = create_broker(settings, languages)
    try:
        yield broker
    finally:
        await broker.aclose()


async def drain(stream) -> list[str]:
    return [delta async for delta in stream]


async def ask_the_pool(
    adapter: str,
    broker: AsyncBroker,
    language: Language,
    settings: Settings,
) -> str:
    if adapter == "whole":
        return (await ask_pool(broker, "prompt", language, settings)).text
    async with open_pool_stream(broker, "prompt", language, settings) as stream:
        return "".join(await drain(stream))


def paid_refusal(paid: CuratedModel) -> str:
    assert paid.provider.key_help, "the paid catalog lost the help for its key"
    return f"the paid model is missing {paid.provider.api_key_ref}: {paid.provider.key_help}"


def other(holds: dict[str, asyncio.Event], name: str) -> str:
    return next(held for held in holds if held != name)


async def test_the_broker_is_llmbrokers_own_and_keeps_its_state_in_the_configured_home(
    settings: Settings,
    languages: dict[str, Language],
    curated: Curated,
    wire: Wire,
    pay: Callable[..., None],
):
    pool = curated.pool[0]
    pay(pool.api_key_ref)
    async with running(settings, languages) as broker:
        assert isinstance(broker, llmbroker.AsyncBroker)
        answer = await ask_pool(broker, "prompt", languages["sr"], settings)

    assert answer.llm_name == pool.name
    assert any(settings.llmbroker_home.iterdir())
    assert wire.fetched
    assert wire.sent == [
        Sent(
            httpx.URL(pool.base_url).host,
            pool.model,
            False,
            f"Bearer {fake_key(pool.api_key_ref)}",
        ),
    ]


async def test_a_whole_pool_answer_is_named_labelled_and_rateable(
    settings: Settings,
    languages: dict[str, Language],
    curated: Curated,
    wire: Wire,
    pay: Callable[..., None],
):
    pool = curated.pool[0]
    pay(pool.api_key_ref)
    wire.reply(pool.model, Answer(("Гла", "гол")))
    async with running(settings, languages) as broker:
        answer = await ask_pool(broker, "prompt", languages["sr"], settings, trace_id="entry-1")
        await answer.record_quality(1.0)
        rows = await broker.calls(limit=10, trace_id="entry-1")

    assert (answer.text, answer.llm_name) == ("Глагол", pool.name)
    assert [(row.llm_name, row.operation, row.score) for row in rows] == [
        (pool.name, "vocab-sr", 1.0),
    ]


async def test_a_pool_stream_arrives_delta_by_delta_and_is_rateable_once_closed(
    settings: Settings,
    languages: dict[str, Language],
    curated: Curated,
    wire: Wire,
    pay: Callable[..., None],
):
    pool = curated.pool[0]
    pay(pool.api_key_ref)
    wire.reply(pool.model, Answer(("Гла", "гол ", "«идти»")))
    async with running(settings, languages) as broker:
        stream = open_pool_stream(broker, "prompt", languages["sr"], settings, trace_id="entry-1")
        async with stream:
            deltas = await drain(stream)
        await stream.record_quality(1.0)
        rows = await broker.calls(limit=10, trace_id="entry-1")

    assert deltas == ["Гла", "гол ", "«идти»"]
    assert stream.llm_name == pool.name
    assert [(row.llm_name, row.operation, row.score) for row in rows] == [
        (pool.name, "vocab-sr", 1.0),
    ]
    assert [(sent.model, sent.stream) for sent in wire.sent] == [(pool.model, True)]


@pytest.mark.parametrize("adapter", ["whole", "streamed"])
async def test_a_pool_provider_that_never_answers_is_a_budget_miss(
    settings: Settings,
    languages: dict[str, Language],
    curated: Curated,
    wire: Wire,
    pay: Callable[..., None],
    adapter: str,
):
    pool = curated.pool[0]
    pay(pool.api_key_ref)
    wire.reply(pool.model, Silence())
    async with running(settings, languages) as broker:
        with pytest.raises(BudgetMissError):
            await ask_the_pool(adapter, broker, languages["sr"], settings)


async def test_a_rate_limited_pool_asked_for_a_whole_answer_is_a_budget_miss_once_it_waited(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    languages: dict[str, Language],
    curated: Curated,
    wire: Wire,
    pay: Callable[..., None],
):
    # The whole-answer call waits for the cooling provider until the budget is gone; a
    # short budget keeps that wait short without changing what it ends in.
    monkeypatch.setattr("echo_words.llm_backend.POOL_WAIT_SECONDS", 0.5)
    pool = curated.pool[0]
    pay(pool.api_key_ref)
    wire.reply(pool.model, Refusal(429, {"Retry-After": "3600"}))
    async with running(settings, languages) as broker:
        with pytest.raises(BudgetMissError):
            await ask_the_pool("whole", broker, languages["sr"], settings)


async def test_a_stream_every_pool_model_rate_limits_is_a_failure_and_not_a_budget_miss(
    settings: Settings,
    languages: dict[str, Language],
    curated: Curated,
    wire: Wire,
    pay: Callable[..., None],
):
    # A stream does not wait for a lane it has already tried: llmbroker ends it at once
    # as `excluded`, which echo-words reads as a fault rather than a missed budget.
    pool = curated.pool[0]
    pay(pool.api_key_ref)
    wire.reply(pool.model, Refusal(429, {"Retry-After": "3600"}))
    async with running(settings, languages) as broker:
        with pytest.raises(BackendError, match="excluded") as failure:
            await ask_the_pool("streamed", broker, languages["sr"], settings)

    assert not isinstance(failure.value, BudgetMissError)


@pytest.mark.parametrize("adapter", ["whole", "streamed"])
async def test_a_request_the_pool_rejects_is_a_failure_and_not_a_budget_miss(
    settings: Settings,
    languages: dict[str, Language],
    curated: Curated,
    wire: Wire,
    pay: Callable[..., None],
    adapter: str,
):
    pool = curated.pool[0]
    pay(pool.api_key_ref)
    wire.reply(pool.model, Refusal(400))
    async with running(settings, languages) as broker:
        with pytest.raises(BackendError) as failure:
            await ask_the_pool(adapter, broker, languages["sr"], settings)

    assert not isinstance(failure.value, BudgetMissError)


async def test_the_paid_alias_streams_from_its_catalog_model_on_its_own_key(
    settings: Settings,
    languages: dict[str, Language],
    curated: Curated,
    wire: Wire,
    pay: Callable[..., None],
):
    paid = curated.paid
    pay(paid.provider.api_key_ref)
    wire.reply(paid.model, Answer(("paid ", "answer")))
    resolved: list[str] = []
    async with running(settings, languages) as broker:
        stream = stream_api(
            broker, curated.alias, "prompt", on_resolved=lambda: resolved.append("")
        )
        deltas = await drain(stream)
        # The client shares the broker's HTTP client, which a second call must find open.
        again = await drain(stream_api(broker, curated.alias, "prompt"))

    assert deltas == again == ["paid ", "answer"]
    assert resolved == [""]
    assert wire.sent == 2 * [
        Sent(
            httpx.URL(paid.provider.base_url).host,
            paid.model,
            True,
            f"Bearer {fake_key(paid.provider.api_key_ref)}",
        ),
    ]


async def test_a_paid_alias_without_its_key_is_unreachable_and_named_missing_afterwards(
    settings: Settings,
    languages: dict[str, Language],
    curated: Curated,
    wire: Wire,
):
    resolved: list[str] = []
    async with running(settings, languages) as broker:
        with pytest.raises(BackendError, match="is unreachable"):
            await drain(
                stream_api(
                    broker,
                    curated.alias,
                    "prompt",
                    on_resolved=lambda: resolved.append(""),
                ),
            )
        # Asked only after the paid call, so nothing had provisioned the pool before it.
        snapshot = await broker.snapshot()

    assert resolved == []
    assert wire.sent == []
    assert [
        (key.api_key_ref, key.help, list(key.entry_names)) for key in snapshot.direct_missing_keys
    ] == [(curated.paid.provider.api_key_ref, curated.paid.provider.key_help, [curated.alias])]


@pytest.mark.parametrize(
    "reply",
    [Refusal(429), Refusal(500), Silence()],
    ids=["rate-limited", "server-error", "timeout"],
)
async def test_a_paid_provider_that_fails_is_a_backend_error(
    settings: Settings,
    languages: dict[str, Language],
    curated: Curated,
    wire: Wire,
    pay: Callable[..., None],
    reply: Reply,
):
    paid = curated.paid
    pay(paid.provider.api_key_ref)
    wire.reply(paid.model, reply)
    async with running(settings, languages) as broker:
        with pytest.raises(BackendError, match="failed"):
            await drain(stream_api(broker, curated.alias, "prompt"))


async def test_a_pool_that_never_answers_steps_up_to_the_paid_model(
    settings: Settings,
    languages: dict[str, Language],
    curated: Curated,
    wire: Wire,
    pay: Callable[..., None],
):
    pool, paid = curated.pool[0], curated.paid
    pay(pool.api_key_ref, paid.provider.api_key_ref)
    wire.reply(pool.model, Silence())
    wire.reply(paid.model, Answer(("paid ", "answer")))
    async with running(settings, languages) as broker:
        cascade = Cascade(broker, settings)
        completion = cascade.stream_completion("prompt", languages["sr"])
        deltas = await drain(completion)

    assert deltas == ["paid ", "answer"]
    assert (completion.paid, completion.llm_name) == (True, curated.alias)
    assert cascade.calls_today == 1


async def test_a_missing_paid_key_is_refused_with_llmbrokers_help_before_anything_is_sent(
    settings: Settings,
    languages: dict[str, Language],
    curated: Curated,
    wire: Wire,
    pay: Callable[..., None],
):
    pool, paid = curated.pool[0], curated.paid
    pay(pool.api_key_ref)
    wire.reply(pool.model, Silence())
    refusal = paid_refusal(paid)
    serbian = languages["sr"]
    async with running(settings, languages) as broker:
        cascade = Cascade(broker, settings)
        assert await cascade.refresh_paid_availability(serbian) == refusal
        with pytest.raises(BackendError, match=re.escape(refusal)):
            cascade.stream_paid("prompt", serbian)
        with pytest.raises(BackendError) as miss:
            await drain(cascade.stream_completion("prompt", serbian))

    assert str(miss.value).endswith(f"paid step unavailable: {refusal}")
    assert wire.to(paid.model) == []
    assert cascade.calls_today == 0


@pytest.mark.parametrize(
    "order", [("paid", "pool"), ("pool", "paid")], ids=["paid-first", "pool-first"]
)
async def test_the_paid_step_and_the_pool_both_answer_whichever_is_asked_first(
    settings: Settings,
    languages: dict[str, Language],
    curated: Curated,
    wire: Wire,
    pay: Callable[..., None],
    order: tuple[str, str],
):
    pool, paid = curated.pool[0], curated.paid
    pay(pool.api_key_ref, paid.provider.api_key_ref)
    wire.reply(pool.model, Answer(("free ", "answer")))
    wire.reply(paid.model, Answer(("paid ", "answer")))
    serbian = languages["sr"]
    answers: dict[str, str] = {}
    async with running(settings, languages) as broker:
        cascade = Cascade(broker, settings)
        for step in order:
            if step == "paid":
                completion = cascade.stream_paid("prompt", serbian, trace_id="entry-1-detail")
            else:
                completion = cascade.stream_completion("prompt", serbian, trace_id="entry-1")
            answers[step] = "".join(await drain(completion))
        snapshot = await broker.snapshot()
        journal = await broker.stats(operation="vocab-sr")

    assert answers == {"paid": "paid answer", "pool": "free answer"}
    assert cascade.calls_today == 1
    assert snapshot.providers_usable == 1
    assert list(snapshot.direct_missing_keys) == []
    assert {name: stats.total for name, stats in journal.items()} == {pool.name: 1}
    assert sorted((sent.model, sent.stream) for sent in wire.sent) == sorted(
        [(pool.model, True), (paid.model, True)],
    )


async def test_an_answer_the_caller_cannot_read_is_rated_down_and_the_same_call_answers_again(
    settings: Settings,
    languages: dict[str, Language],
    curated: Curated,
    wire: Wire,
    pay: Callable[..., None],
):
    first, second = curated.pool[:2]
    pay(first.api_key_ref, second.api_key_ref)
    holds = {entry.name: asyncio.Event() for entry in (first, second)}
    for entry in (first, second):
        wire.reply(entry.model, Answer((entry.name, " answers"), hold=holds[entry.name]))
    page: list[str] = []
    streamed: list[str] = []

    async def reset() -> None:
        page.clear()

    def usable(answer: str) -> bool:
        # Judged once the streamed answer is whole, so the other lane is still running
        # when the call is asked for another answer.
        holds[other(holds, streamed[0])].set()
        return answer != f"{streamed[0]} answers"

    async with running(settings, languages) as broker:
        cascade = Cascade(broker, settings)
        completion = cascade.stream_completion(
            "prompt",
            languages["sr"],
            trace_id="entry-1",
            on_reset=reset,
            usable=usable,
        )
        try:
            async with aclosing(completion):
                async for delta in completion:
                    if not streamed:
                        streamed.append(completion.llm_name or "")
                        holds[streamed[0]].set()
                    page.append(delta)
            await completion.record_quality(1.0)
            rows = await broker.calls(limit=10, trace_id="entry-1")
        finally:
            for hold in holds.values():
                hold.set()

    rejected = streamed[0]
    kept = other(holds, rejected)
    assert "".join(page) == f"{kept} answers"
    assert (completion.llm_name, completion.paid) == (kept, False)
    assert {row.llm_name: row.score for row in rows} == {rejected: 0.0, kept: 1.0}
    assert wire.to(curated.paid.model) == []


async def test_a_stream_overtaken_by_a_whole_answer_gives_the_page_that_answer_and_rates_it(
    settings: Settings,
    languages: dict[str, Language],
    curated: Curated,
    wire: Wire,
    pay: Callable[..., None],
):
    first, second = curated.pool[:2]
    pay(first.api_key_ref, second.api_key_ref)
    holds = {entry.name: asyncio.Event() for entry in (first, second)}
    for entry in (first, second):
        wire.reply(entry.model, Answer((entry.name, " answers"), hold=holds[entry.name]))
    page: list[str] = []
    streamed: list[str] = []
    resets: list[str] = []

    async def reset() -> None:
        resets.append("".join(page))
        page.clear()

    async with running(settings, languages) as broker:
        cascade = Cascade(broker, settings)
        completion = cascade.stream_completion(
            "prompt",
            languages["sr"],
            trace_id="entry-1",
            on_reset=reset,
        )
        try:
            async with aclosing(completion):
                async for delta in completion:
                    if not streamed:
                        streamed.append(completion.llm_name or "")
                        # The lane on the page stays held, so the other one finishes first.
                        holds[other(holds, streamed[0])].set()
                    page.append(delta)
            await completion.record_quality(1.0)
            rows = await broker.calls(limit=10, trace_id="entry-1")
        finally:
            for hold in holds.values():
                hold.set()

    overtaken = streamed[0]
    winner = other(holds, overtaken)
    assert resets == [overtaken]
    assert "".join(page) == f"{winner} answers"
    assert completion.llm_name == winner
    assert {row.llm_name: row.score for row in rows if row.score is not None} == {winner: 1.0}


def test_the_app_runs_on_the_real_broker_reports_it_and_closes_it_on_shutdown(
    settings: Settings,
    curated: Curated,
    wire: Wire,
    pay: Callable[..., None],
):
    pool, paid = curated.pool[0], curated.paid
    pay(pool.api_key_ref)
    app = create_app(settings)
    with TestClient(app) as client:
        broker = app.state.cascade.broker
        assert isinstance(broker, llmbroker.AsyncBroker)
        portal = client.portal
        assert portal is not None
        # Straight to the pool, past the cascade's memory, so the page falls back to
        # llmbroker's journal for the last call.
        portal.call(ask_pool, broker, "prompt", app.state.languages["sr"], settings)
        body = client.get("/api/status").json()
        snapshot = portal.call(broker.snapshot)
        assert wire.clients
        assert not any(http.is_closed for http in wire.clients)

    assert all(http.is_closed for http in wire.clients)
    status = body["pool"]
    assert status["available"] is True
    assert (status["providers_usable"], status["providers_total"]) == (1, len(curated.pool_refs))
    assert status["degraded"] is snapshot.degraded
    assert sorted(key["api_key_ref"] for key in status["missing_keys"]) == sorted(
        curated.pool_refs - {pool.api_key_ref},
    )
    assert all(key["help"] and key["entry_names"] for key in status["missing_keys"])
    assert status["direct_missing_keys"] == [
        {
            "api_key_ref": paid.provider.api_key_ref,
            "help": paid.provider.key_help,
            "entry_names": [curated.alias],
        },
    ]
    serbian = body["languages"]["sr"]
    assert serbian["paid_alias"] == curated.alias
    assert serbian["paid_available_today"] is False
    assert serbian["paid_refusal"] == paid_refusal(paid)
    assert serbian["journal"] == {pool.name: 1}
    last_call = serbian["last_call"]
    assert datetime.fromisoformat(last_call.pop("at")).tzinfo is not None
    assert last_call == {
        "model": pool.name,
        "paid": False,
        "ok": True,
        "error": None,
        "source": "journal",
    }
    assert body["languages"]["en"]["journal"] == {}
    assert body["languages"]["en"]["last_call"] is None
