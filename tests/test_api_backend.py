import pytest
from fakes import FakeBroker, FakeDirectClient
from llmbroker import (
    AuthError,
    InvalidProviderResponseError,
    LLMTimeoutError,
    MissingKeyError,
    PoolModelError,
    ProviderError,
    RateLimitError,
    UnknownModelError,
)

from echo_words.api_backend import API_TIMEOUT_SECONDS, stream_api
from echo_words.broker import BackendError
from echo_words.llm_backend import POOL_WAIT_SECONDS

pytestmark = pytest.mark.anyio


async def drain(stream) -> list[str]:
    return [delta async for delta in stream]


async def test_the_answer_arrives_as_it_is_produced():
    broker = FakeBroker(client=FakeDirectClient(["Гла", "гол ", "«идти»"]))
    assert await drain(stream_api(broker, "gpt-fast", "prompt")) == ["Гла", "гол ", "«идти»"]


async def test_the_named_alias_is_the_model_asked_for():
    broker = FakeBroker(client=FakeDirectClient())
    await drain(stream_api(broker, "gpt-fast", "prompt"))
    assert broker.direct_calls == ["gpt-fast"]
    assert broker.client.calls == [{"prompt": "prompt", "timeout": API_TIMEOUT_SECONDS}]


def test_the_paid_attempt_gets_a_fresh_full_budget_equal_to_the_pool_attempt():
    assert API_TIMEOUT_SECONDS == POOL_WAIT_SECONDS


async def test_the_shared_client_is_never_closed_here():
    client = FakeDirectClient()
    broker = FakeBroker(client=client)
    await drain(stream_api(broker, "gpt-fast", "prompt"))
    assert client.closed is False


@pytest.mark.parametrize(
    "error",
    [
        UnknownModelError("no such alias"),
        PoolModelError("that alias is a pool model"),
        MissingKeyError("no key for that provider"),
    ],
)
async def test_an_unresolvable_alias_is_a_backend_error(error: Exception):
    broker = FakeBroker(direct_error=error)
    with pytest.raises(BackendError):
        await drain(stream_api(broker, "gpt-fast", "prompt"))


@pytest.mark.parametrize(
    "error",
    [
        AuthError("bad key", status=401),
        RateLimitError("slow down", status=429),
        LLMTimeoutError("no answer in time"),
        ProviderError("bad gateway", status=502),
        InvalidProviderResponseError("no choices", model="gpt-fast"),
    ],
)
async def test_a_failed_call_is_a_backend_error(error: Exception):
    broker = FakeBroker(client=FakeDirectClient(["half "], error=error))
    with pytest.raises(BackendError):
        await drain(stream_api(broker, "gpt-fast", "prompt"))


async def test_a_200_without_text_is_a_backend_error():
    broker = FakeBroker(client=FakeDirectClient([]))
    with pytest.raises(BackendError, match="InvalidProviderResponseError"):
        await drain(stream_api(broker, "gpt-fast", "prompt"))
