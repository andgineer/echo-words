from datetime import date

import pytest
from fakes import FakeDirectClient, FakeHandle, fake_cascade
from llmbroker import (
    LLMTimeoutError,
    MissingKeyError,
    NoLLMAvailableError,
    PoolModelError,
    StreamInterruptedError,
    UnknownModelError,
)

from echo_words.backend import Cascade
from echo_words.broker import BackendError, BudgetMissError
from echo_words.config import Settings
from echo_words.languages import Language

pytestmark = pytest.mark.anyio

POOL_MISSED = NoLLMAvailableError("pool exhausted", reason="timeout")
POOL_RAN_LONG = LLMTimeoutError("the answer outlived the budget")


class ResetHook:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> None:
        self.calls += 1


async def drain(stream) -> list[str]:
    return [delta async for delta in stream]


async def run(cascade: Cascade, language: Language, on_reset=None) -> list[str]:
    return await drain(cascade.stream_completion("prompt", language, on_reset=on_reset))


async def test_a_completed_pool_answer_never_touches_the_paid_client(settings, languages):
    cascade = fake_cascade(settings, handles=[FakeHandle(["free ", "answer"])])
    assert await run(cascade, languages["en"]) == ["free ", "answer"]
    assert cascade.broker.direct_calls == []
    assert cascade.calls_today == 0


async def test_a_pool_that_says_nothing_in_time_steps_up_invisibly(settings, languages):
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(error=POOL_MISSED)],
        client=FakeDirectClient(["paid ", "answer"]),
    )
    reset = ResetHook()
    assert await run(cascade, languages["en"], reset) == ["paid ", "answer"]
    assert reset.calls == 0
    assert cascade.calls_today == 1


async def test_a_pool_that_outlives_the_budget_steps_up_with_a_reset(settings, languages):
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(["half an "], error=POOL_RAN_LONG)],
        client=FakeDirectClient(["paid ", "answer"]),
    )
    reset = ResetHook()
    assert await run(cascade, languages["en"], reset) == ["half an ", "paid ", "answer"]
    assert reset.calls == 1


async def test_a_fault_is_not_paid_for(settings, languages):
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(["half "], error=StreamInterruptedError("died", llm_name="flash"))],
        client=FakeDirectClient(),
    )
    reset = ResetHook()
    with pytest.raises(BackendError):
        await run(cascade, languages["en"], reset)
    assert cascade.broker.direct_calls == []
    assert reset.calls == 0


@pytest.mark.parametrize("reason", ["empty_pool", "no_keys", "all_disabled", "excluded"])
async def test_a_pool_configuration_fault_never_steps_up(settings, languages, reason):
    error = NoLLMAvailableError("pool unavailable", reason=reason)
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(error=error)],
        client=FakeDirectClient(),
    )
    with pytest.raises(BackendError) as caught:
        await run(cascade, languages["en"])
    assert not isinstance(caught.value, BudgetMissError)
    assert cascade.broker.direct_calls == []
    assert cascade.calls_today == 0


@pytest.mark.parametrize("score", [1.0, 0.0])
async def test_the_call_that_answered_is_the_call_that_is_rated(settings, languages, score):
    handle = FakeHandle(["free answer"])
    cascade = fake_cascade(settings, handles=[handle])
    completion = cascade.stream_completion("prompt", languages["en"])
    await drain(completion)
    await completion.record_quality(score)
    assert handle.scores == [score]


async def test_an_abandoned_stream_is_not_rated(settings, languages):
    handle = FakeHandle(["one", "two"])
    cascade = fake_cascade(settings, handles=[handle])
    completion = cascade.stream_completion("prompt", languages["en"])
    async for _delta in completion:
        break
    await completion.aclose()
    await completion.record_quality(1.0)
    assert handle.closed is True
    assert handle.scores == []


async def test_a_stepped_up_answer_does_not_rate_the_pool(settings, languages):
    handle = FakeHandle(error=POOL_MISSED)
    cascade = fake_cascade(settings, handles=[handle], client=FakeDirectClient())
    completion = cascade.stream_completion("prompt", languages["en"])
    await drain(completion)
    await completion.record_quality(1.0)
    assert handle.scores == []


async def test_the_model_that_answered_is_kept_for_the_status_view(settings, languages):
    cascade = fake_cascade(settings, handles=[FakeHandle(["ok"], llm_name="free-flash")])
    await run(cascade, languages["en"])
    call = cascade.last_calls["en"]
    assert call.llm_name == "free-flash"
    assert call.paid is False
    assert call.ok is True
    assert call.at is not None


async def test_the_last_call_is_kept_per_language(settings, languages):
    cascade = fake_cascade(
        settings,
        handles=[
            FakeHandle(["English"], llm_name="free-en"),
            FakeHandle(["Serbian"], llm_name="free-sr"),
        ],
    )
    await run(cascade, languages["en"])
    await run(cascade, languages["sr"])
    assert cascade.last_calls["en"].llm_name == "free-en"
    assert cascade.last_calls["sr"].llm_name == "free-sr"


async def test_a_step_up_is_kept_under_the_alias_that_answered(settings, languages):
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(error=POOL_MISSED)],
        client=FakeDirectClient(),
    )
    await run(cascade, languages["sr"])
    call = cascade.last_calls["sr"]
    assert call.llm_name == "gpt-fast"
    assert call.paid is True


async def test_a_failure_is_kept_too(settings, languages):
    cascade = fake_cascade(settings, handles=[FakeHandle(error=POOL_MISSED)])
    paidless = Cascade(cascade.broker, settings.model_copy(update={"api_model": ""}))
    with pytest.raises(BackendError, match="no paid model"):
        await run(paidless, languages["en"])
    assert paidless.last_calls["en"].ok is False
    assert "no paid model" in paidless.last_calls["en"].error


async def test_the_language_names_which_paid_model_it_steps_up_to(settings, languages):
    named = settings.model_copy(update={"api_model": "gpt-default"})
    cascade = fake_cascade(
        named,
        handles=[FakeHandle(error=POOL_MISSED), FakeHandle(error=POOL_MISSED)],
        client=FakeDirectClient(),
    )
    await run(cascade, languages["en"])
    await run(cascade, languages["sr"])
    assert cascade.broker.direct_calls == ["gpt-default", "gpt-fast"]


async def test_without_a_paid_alias_a_pool_miss_is_a_failure(settings, languages):
    cascade = fake_cascade(
        settings.model_copy(update={"api_model": ""}),
        handles=[FakeHandle(error=POOL_MISSED)],
        client=FakeDirectClient(),
    )
    with pytest.raises(BackendError, match="no paid model"):
        await run(cascade, languages["en"])
    assert cascade.broker.direct_calls == []


async def test_without_a_paid_alias_a_deeper_analysis_is_refused(settings, languages):
    cascade = fake_cascade(settings.model_copy(update={"api_model": ""}))
    with pytest.raises(BackendError, match="no paid model"):
        cascade.stream_paid("prompt", languages["en"])


async def test_the_deeper_analysis_goes_straight_to_the_paid_model(settings, languages):
    cascade = fake_cascade(settings, client=FakeDirectClient(["deep ", "brief"]))
    completion = cascade.stream_paid("prompt", languages["sr"])
    assert await drain(completion) == ["deep ", "brief"]
    assert cascade.broker.direct_calls == ["gpt-fast"]
    assert cascade.calls_today == 1
    assert cascade.last_calls["sr"].llm_name == "gpt-fast"
    assert cascade.last_calls["sr"].paid is True


async def test_a_step_up_spends_from_the_same_wallet_as_the_deeper_analysis(settings, languages):
    capped = settings.model_copy(update={"api_daily_cap": 1})
    cascade = fake_cascade(
        capped,
        handles=[FakeHandle(error=POOL_MISSED)],
        client=FakeDirectClient(),
    )
    await run(cascade, languages["en"])
    assert cascade.calls_today == 1
    with pytest.raises(BackendError, match="cap"):
        cascade.stream_paid("prompt", languages["en"])


async def test_a_pool_miss_past_the_cap_fails_instead_of_paying(settings, languages):
    capped = settings.model_copy(update={"api_daily_cap": 1})
    cascade = fake_cascade(
        capped,
        handles=[FakeHandle(error=POOL_MISSED)],
        client=FakeDirectClient(),
    )
    await drain(cascade.stream_paid("prompt", languages["en"]))
    reset = ResetHook()
    with pytest.raises(BackendError, match="cap"):
        await run(cascade, languages["en"], reset)
    assert cascade.broker.direct_calls == ["gpt-fast"]
    assert cascade.calls_today == 1
    assert reset.calls == 0


async def test_an_unlimited_cap_never_refuses(settings: Settings, languages):
    unlimited = settings.model_copy(update={"api_daily_cap": 0})
    cascade = fake_cascade(unlimited, client=FakeDirectClient())
    for _ in range(3):
        await drain(cascade.stream_paid("prompt", languages["en"]))
    assert cascade.calls_today == 3


async def test_a_language_with_its_own_model_cannot_pay_past_the_off_switch(settings, languages):
    paidless = settings.model_copy(update={"api_model": ""})
    cascade = fake_cascade(
        paidless,
        handles=[FakeHandle(error=POOL_MISSED)],
        client=FakeDirectClient(),
    )
    assert languages["sr"].api_model == "gpt-fast"
    with pytest.raises(BackendError, match="no paid model"):
        await run(cascade, languages["sr"])
    assert cascade.broker.direct_calls == []


@pytest.mark.parametrize(
    "error",
    [
        UnknownModelError("no such alias"),
        PoolModelError("that alias is a pool model"),
        MissingKeyError("no key for that provider"),
    ],
)
async def test_an_unresolvable_paid_alias_does_not_spend_the_wallet(
    settings,
    languages,
    error,
):
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(error=POOL_MISSED)],
        direct_error=error,
    )
    with pytest.raises(BackendError, match="unreachable"):
        await run(cascade, languages["en"])
    assert cascade.calls_today == 0


async def test_calls_today_rolls_over_in_utc_when_read(settings, languages, monkeypatch):
    current_day = [date(2026, 8, 19)]
    monkeypatch.setattr("echo_words.backend.utc_today", lambda: current_day[0])
    cascade = fake_cascade(settings, client=FakeDirectClient())
    await drain(cascade.stream_paid("prompt", languages["en"]))
    assert cascade.calls_today == 1
    current_day[0] = date(2026, 8, 20)
    assert cascade.calls_today == 0
