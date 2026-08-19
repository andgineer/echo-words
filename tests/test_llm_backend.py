from contextlib import aclosing

import pytest
from fakes import FakeBroker, FakeHandle
from llmbroker import (
    LLMTimeoutError,
    NoLLMAvailableError,
    ProviderError,
    StreamInterruptedError,
)

from echo_words.broker import BackendError, BudgetMissError
from echo_words.config import Settings
from echo_words.languages import Language
from echo_words.llm_backend import POOL_WAIT_SECONDS, open_pool_stream

pytestmark = pytest.mark.anyio


async def drain(stream) -> list[str]:
    return [delta async for delta in stream]


def test_the_budget_sits_at_the_low_end_of_the_stated_range():
    assert 20 <= POOL_WAIT_SECONDS <= 25


async def test_the_answer_arrives_as_it_is_produced(settings: Settings, languages):
    broker = FakeBroker(handles=[FakeHandle(["Hel", "lo ", "world"])])
    stream = open_pool_stream(broker, "prompt", languages["en"], settings)
    assert await drain(stream) == ["Hel", "lo ", "world"]


def test_the_fake_handle_exposes_one_iterator():
    handle = FakeHandle(["one", "two"])
    assert handle.__aiter__() is handle.__aiter__()


@pytest.mark.parametrize(("code", "operation"), [("en", "vocab-en"), ("sr", "vocab-sr")])
async def test_the_call_is_labelled_per_language_traced_and_bounded(
    settings: Settings,
    languages: dict[str, Language],
    code: str,
    operation: str,
):
    broker = FakeBroker(handles=[FakeHandle(["ok"])])
    open_pool_stream(broker, "prompt", languages[code], settings, trace_id="entry-1")
    assert broker.stream_calls == [
        {
            "prompt": "prompt",
            "operation": operation,
            "trace_id": "entry-1",
            "wait": POOL_WAIT_SECONDS,
        },
    ]


async def test_the_model_that_answered_is_on_the_stream(settings: Settings, languages):
    broker = FakeBroker(handles=[FakeHandle(["ok"], llm_name="free-flash")])
    stream = open_pool_stream(broker, "prompt", languages["en"], settings)
    await drain(stream)
    assert stream.llm_name == "free-flash"


async def test_the_slot_is_handed_back_when_the_consumer_walks_away(
    settings: Settings,
    languages: dict[str, Language],
):
    handle = FakeHandle(["one", "two", "three"])
    broker = FakeBroker(handles=[handle])
    stream = open_pool_stream(broker, "prompt", languages["en"], settings)
    async with aclosing(stream):
        async for _delta in stream:
            break
    assert handle.closed is True
    assert handle.delivered == ["one"]


async def test_a_rating_reaches_the_call_that_earned_it(settings: Settings, languages):
    handle = FakeHandle(["ok"])
    broker = FakeBroker(handles=[handle])
    stream = open_pool_stream(broker, "prompt", languages["en"], settings)
    await drain(stream)
    await stream.record_quality(1.0)
    assert handle.scores == [1.0]


@pytest.mark.parametrize(
    "error",
    [
        NoLLMAvailableError("pool exhausted", reason="timeout"),
        LLMTimeoutError("the answer outlived the budget"),
    ],
)
async def test_a_budget_miss_asks_for_the_next_step(
    settings: Settings,
    languages: dict[str, Language],
    error: Exception,
):
    broker = FakeBroker(handles=[FakeHandle(error=error)])
    stream = open_pool_stream(broker, "prompt", languages["en"], settings)
    with pytest.raises(BudgetMissError):
        await drain(stream)


@pytest.mark.parametrize(
    "error",
    [
        StreamInterruptedError("the stream died", llm_name="free-flash"),
        ProviderError("bad gateway", status=502),
    ],
)
async def test_a_fault_is_a_failure_and_not_a_budget_miss(
    settings: Settings,
    languages: dict[str, Language],
    error: Exception,
):
    broker = FakeBroker(handles=[FakeHandle(["half "], error=error)])
    stream = open_pool_stream(broker, "prompt", languages["en"], settings)
    with pytest.raises(BackendError) as caught:
        await drain(stream)
    assert not isinstance(caught.value, BudgetMissError)


@pytest.mark.parametrize("reason", ["empty_pool", "no_keys", "all_disabled", "excluded"])
async def test_pool_exhaustion_that_is_not_a_timeout_is_a_fault(
    settings: Settings,
    languages: dict[str, Language],
    reason: str,
):
    error = NoLLMAvailableError("pool unavailable", reason=reason)
    broker = FakeBroker(handles=[FakeHandle(error=error)])
    stream = open_pool_stream(broker, "prompt", languages["en"], settings)
    with pytest.raises(BackendError) as caught:
        await drain(stream)
    assert not isinstance(caught.value, BudgetMissError)


async def test_an_empty_success_is_a_failure(settings: Settings, languages):
    broker = FakeBroker(handles=[FakeHandle()])
    stream = open_pool_stream(broker, "prompt", languages["en"], settings)
    with pytest.raises(BackendError, match="InvalidProviderResponseError"):
        await drain(stream)
