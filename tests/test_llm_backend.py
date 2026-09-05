from contextlib import aclosing

import pytest
from fakes import FakeBroker, FakeHandle
from llmbroker import (
    LLMTimeoutError,
    NoLLMAvailableError,
    ProviderError,
)

from echo_words.broker import BackendError, BudgetMissError
from echo_words.config import Settings
from echo_words.languages import Language
from echo_words.llm_backend import POOL_FASTEST_OF, POOL_WAIT_SECONDS, ask_pool, open_pool_stream

pytestmark = pytest.mark.anyio


async def drain(stream) -> list[str]:
    return [delta async for delta in stream]


def test_the_budget_sits_at_the_low_end_of_the_stated_range():
    assert 20 <= POOL_WAIT_SECONDS <= 25


async def test_the_complete_answer_arrives_at_once(settings: Settings, languages):
    broker = FakeBroker(handles=[FakeHandle(["Hel", "lo ", "world"])])
    answer = await ask_pool(broker, "prompt", languages["en"], settings)
    assert answer.text == "Hello world"


async def test_the_dormant_stream_adapter_preserves_deltas_and_racing(
    settings: Settings,
    languages,
):
    broker = FakeBroker(handles=[FakeHandle(["Hel", "lo ", "world"])])
    stream = open_pool_stream(broker, "prompt", languages["en"], settings)
    async with aclosing(stream):
        assert await drain(stream) == ["Hel", "lo ", "world"]
    assert broker.ask_calls == []
    assert broker.stream_calls == [
        {
            "prompt": "prompt",
            "operation": "vocab-en",
            "trace_id": None,
            "wait": POOL_WAIT_SECONDS,
            "fastest_of": POOL_FASTEST_OF,
        },
    ]


@pytest.mark.parametrize(("code", "operation"), [("en", "vocab-en"), ("sr", "vocab-sr")])
async def test_the_call_is_labelled_traced_bounded_and_races_two_complete_answers(
    settings: Settings,
    languages: dict[str, Language],
    code: str,
    operation: str,
):
    broker = FakeBroker(handles=[FakeHandle(["ok"])])
    await ask_pool(broker, "prompt", languages[code], settings, trace_id="entry-1")
    assert broker.ask_calls == [
        {
            "prompt": "prompt",
            "operation": operation,
            "trace_id": "entry-1",
            "wait": POOL_WAIT_SECONDS,
            "fastest_of": 2,
        },
    ]


async def test_the_model_that_answered_is_on_the_result(settings: Settings, languages):
    broker = FakeBroker(handles=[FakeHandle(["ok"], llm_name="free-flash")])
    answer = await ask_pool(broker, "prompt", languages["en"], settings)
    assert answer.llm_name == "free-flash"


async def test_the_provider_attempt_is_settled_before_the_answer_is_returned(
    settings: Settings,
    languages: dict[str, Language],
):
    handle = FakeHandle(["one", "two", "three"])
    broker = FakeBroker(handles=[handle])
    answer = await ask_pool(broker, "prompt", languages["en"], settings)
    assert answer.text == "onetwothree"
    assert handle.closed is True
    assert handle.delivered == ["one", "two", "three"]


async def test_a_rating_reaches_the_call_that_earned_it(settings: Settings, languages):
    handle = FakeHandle(["ok"])
    broker = FakeBroker(handles=[handle])
    answer = await ask_pool(broker, "prompt", languages["en"], settings)
    await answer.record_quality(1.0)
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
    with pytest.raises(BudgetMissError):
        await ask_pool(broker, "prompt", languages["en"], settings)


async def test_a_fault_is_a_failure_and_not_a_budget_miss(
    settings: Settings,
    languages: dict[str, Language],
):
    error = ProviderError("bad gateway", status=502)
    broker = FakeBroker(handles=[FakeHandle(["half "], error=error)])
    with pytest.raises(BackendError) as caught:
        await ask_pool(broker, "prompt", languages["en"], settings)
    assert not isinstance(caught.value, BudgetMissError)


@pytest.mark.parametrize("reason", ["empty_pool", "no_keys", "all_disabled", "excluded"])
async def test_pool_exhaustion_that_is_not_a_timeout_is_a_fault(
    settings: Settings,
    languages: dict[str, Language],
    reason: str,
):
    error = NoLLMAvailableError("pool unavailable", reason=reason)
    broker = FakeBroker(handles=[FakeHandle(error=error)])
    with pytest.raises(BackendError) as caught:
        await ask_pool(broker, "prompt", languages["en"], settings)
    assert not isinstance(caught.value, BudgetMissError)


async def test_an_empty_success_is_a_failure(settings: Settings, languages):
    broker = FakeBroker(handles=[FakeHandle()])
    with pytest.raises(BackendError, match="InvalidProviderResponseError"):
        await ask_pool(broker, "prompt", languages["en"], settings)
