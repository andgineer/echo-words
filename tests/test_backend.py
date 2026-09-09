import logging
from datetime import date
from types import SimpleNamespace

import pytest
from fakes import FakeDirectClient, FakeHandle, another_answer, fake_cascade, lost_the_race
from llmbroker import (
    InvalidProviderResponseError,
    LLMTimeoutError,
    MissingKeyError,
    NoLLMAvailableError,
    PoolModelError,
    StreamInterruptedError,
    UnknownModelError,
)

import echo_words.backend as backend_module
from echo_words.backend import Cascade
from echo_words.broker import BackendError, BudgetMissError
from echo_words.config import Settings
from echo_words.languages import Language
from echo_words.prompt import MAX_COMPLETE_ANSWER_CHARS

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


async def test_the_shipped_adapter_streams_the_pool_answer_as_it_arrives(settings, languages):
    cascade = fake_cascade(settings, handles=[FakeHandle(["free ", "answer"])])

    assert await run(cascade, languages["en"]) == ["free ", "answer"]
    assert cascade.broker.ask_calls == []
    assert cascade.broker.stream_calls[0]["fastest_of"] == 2


async def test_the_code_flag_switches_the_pool_adapter_back_to_one_complete_response(
    monkeypatch,
    settings,
    languages,
):
    monkeypatch.setattr(backend_module, "STREAM_POOL_ANSWERS", False)
    cascade = fake_cascade(settings, handles=[FakeHandle(["free ", "answer"])])

    assert await run(cascade, languages["en"]) == ["free answer"]
    assert cascade.broker.stream_calls == []
    assert cascade.broker.ask_calls[0]["fastest_of"] == 2


async def test_a_lost_race_drops_the_provisional_deltas_for_the_answer_that_won(
    settings,
    languages,
):
    """Two lanes race the whole answer, so the deltas on the page are provisional. When
    another lane finishes first the page is cleared and shows that answer instead —
    the reader never reads one model continued by another."""
    lost = lost_the_race("whole answer", winner="free-flash", streamed="free-slow")
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(["half ", "an answer"], error=lost)],
        client=FakeDirectClient(),
    )
    reset = ResetHook()

    assert await run(cascade, languages["en"], reset) == ["half ", "an answer", "whole answer"]
    assert reset.calls == 1
    assert cascade.broker.direct_calls == []
    assert cascade.calls_today == 0


async def test_a_race_settled_before_any_delta_has_nothing_to_drop(settings, languages):
    lost = lost_the_race("whole answer", winner="free-flash", streamed="free-slow")
    cascade = fake_cascade(settings, handles=[FakeHandle(error=lost)])
    reset = ResetHook()

    assert await run(cascade, languages["en"], reset) == ["whole answer"]
    assert reset.calls == 0


async def test_the_lane_that_won_is_the_one_named_and_the_one_rated(settings, languages):
    lost = lost_the_race("whole answer", winner="free-flash", streamed="free-slow")
    handle = FakeHandle(["half "], error=lost, llm_name="free-slow")
    cascade = fake_cascade(settings, handles=[handle])
    completion = cascade.stream_completion("prompt", languages["en"])

    await drain(completion)
    await completion.record_quality(1.0)

    assert completion.llm_name == "free-flash"
    assert cascade.last_calls["en"].llm_name == "free-flash"
    assert lost.replacement.scores == [1.0]
    assert handle.scores == []


async def test_a_replacement_the_caller_cannot_use_stands_like_any_other_answer(
    settings,
    languages,
):
    lost = lost_the_race("whole answer", winner="free-flash", streamed="free-slow")
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(["half "], error=lost)],
        client=FakeDirectClient(["paid ", "answer"]),
    )
    reset = ResetHook()
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        on_reset=reset,
        usable=lambda answer: "paid" in answer,
    )

    assert await drain(completion) == ["half ", "whole answer"]
    # Once, for the deltas the race voided. Winning a race does not make an answer
    # readable, and failing to be readable does not buy a paid one.
    assert reset.calls == 1
    assert cascade.broker.direct_calls == []
    assert lost.replacement.scores == [0.0]


async def test_the_answer_bound_belongs_to_the_replacement_and_not_to_what_it_voided(
    settings,
    languages,
):
    """An oversized provisional answer is not the answer: bounding the one that won by
    what the loser already spent would truncate a perfectly sized replacement."""
    lost = lost_the_race("whole answer", winner="free-flash", streamed="free-slow")
    oversized = "x" * (MAX_COMPLETE_ANSWER_CHARS + 500)
    cascade = fake_cascade(settings, handles=[FakeHandle([oversized], error=lost)])
    completion = cascade.stream_completion("prompt", languages["en"])

    deltas = await drain(completion)

    assert len(deltas[0]) == MAX_COMPLETE_ANSWER_CHARS
    assert deltas[1] == "whole answer"
    assert completion.oversized is False


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


async def test_a_pool_that_outlives_the_budget_steps_up_over_the_half_answer_it_showed(
    settings,
    languages,
):
    """A streamed answer that dies past its budget has already reached the page, so the
    step-up drops it there: what the reader keeps is one answer, never two halves."""
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(["half an "], error=POOL_RAN_LONG)],
        client=FakeDirectClient(["paid ", "answer"]),
    )
    reset = ResetHook()
    assert await run(cascade, languages["en"], reset) == ["half an ", "paid ", "answer"]
    assert reset.calls == 1


async def test_a_pool_answer_the_caller_cannot_use_stays_in_front_of_the_reader(
    settings,
    languages,
):
    """The analysis is worth reading even when the card behind it failed. Clearing it
    for a paid step spends the cap and a second budget of waiting on a verdict about the
    payload, which production says is wrong far more often than it is right — so the
    paid answer becomes the reader's own call, and the page is left alone."""
    handle = FakeHandle(["free ", "answer"])
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient(["paid ", "answer"]),
    )
    reset = ResetHook()
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        on_reset=reset,
        usable=lambda answer: "paid" in answer,
    )
    assert await drain(completion) == ["free ", "answer"]
    assert reset.calls == 0
    assert cascade.broker.direct_calls == []
    assert cascade.calls_today == 0


async def test_an_answer_the_caller_cannot_use_never_buys_a_paid_one_by_itself(
    settings,
    languages,
):
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(["free ", "answer"])],
        client=FakeDirectClient(["paid ", "answer"]),
    )
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda _answer: False,
    )
    assert await drain(completion) == ["free ", "answer"]
    assert cascade.broker.direct_calls == []
    assert cascade.calls_today == 0


async def test_a_usable_answer_handed_over_is_stepped_up_without_being_rated_down(
    settings,
    languages,
):
    """Handing an answer to the paid model on policy is not a complaint about it.
    Rating it zero would push a pool model down the ranking for answering exactly as
    it was asked, which is how a caller's preference becomes a broken pool."""
    handle = FakeHandle(["free ", "answer"])
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient(["paid ", "answer"]),
    )
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda _answer: True,
        hand_over=lambda _answer: True,
    )
    assert await drain(completion) == ["free ", "answer", "paid ", "answer"]
    assert cascade.broker.direct_calls == ["gpt-fast"]
    assert handle.scores == []

    # The caller rates the answer it ends up with, and that answer came from the paid
    # model: letting it land on the pool handle would score one model on another's work.
    await completion.record_quality(1.0)
    assert handle.scores == []


async def test_a_handed_over_answer_stands_unrated_when_nothing_can_take_it(
    settings,
    languages,
):
    handle = FakeHandle(["free ", "answer"])
    cascade = fake_cascade(
        settings.model_copy(update={"api_model": ""}),
        handles=[handle],
        client=FakeDirectClient(),
    )
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda _answer: True,
        hand_over=lambda _answer: True,
    )
    assert await drain(completion) == ["free ", "answer"]
    assert cascade.broker.direct_calls == []
    assert handle.scores == []

    # Nothing took it, so this pool answer is the one the reader got, and it is rated.
    await completion.record_quality(1.0)
    assert handle.scores == [1.0]


async def test_an_unusable_answer_is_rated_down_whatever_the_hand_over_says(
    settings,
    languages,
):
    handle = FakeHandle(["free ", "answer"])
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient(["paid ", "answer"]),
    )
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda _answer: False,
        hand_over=lambda _answer: False,
    )
    assert await drain(completion) == ["free ", "answer"]
    assert handle.scores == [0.0]
    assert cascade.broker.direct_calls == []


async def test_an_unreadable_payload_takes_the_pools_next_answer_before_any_paid_one(
    settings,
    languages,
):
    """The models this call already raced hold answers of their own, and production says
    an answer the parser refuses is almost always one the reader would have accepted.
    Buying a paid answer while the pool is still holding one spends the cap on a coin
    flip and makes the reader wait a second budget for it."""
    handle = FakeHandle(["free ", "answer"], others=[another_answer("second answer")])
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient(["paid ", "answer"]),
    )
    reset = ResetHook()
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        on_reset=reset,
        usable=lambda answer: "second" in answer,
    )
    assert await drain(completion) == ["free ", "answer", "second answer"]
    assert handle.another_calls == 1
    assert cascade.broker.direct_calls == []
    assert cascade.calls_today == 0
    # The refused text is dropped from the page rather than spliced with what replaces
    # it, exactly as the paid step drops the answer it takes over from.
    assert reset.calls == 1


async def test_the_pool_is_asked_again_until_one_answer_can_be_read(settings, languages):
    handle = FakeHandle(
        ["free ", "answer"],
        others=[another_answer("also unreadable"), another_answer("second answer")],
    )
    cascade = fake_cascade(settings, handles=[handle], client=FakeDirectClient())
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda answer: "second" in answer,
    )
    assert await drain(completion) == ["free ", "answer", "also unreadable", "second answer"]
    assert handle.another_calls == 2
    assert cascade.broker.direct_calls == []


async def test_every_refused_answer_is_rated_down_and_the_one_that_stands_is_not(
    settings,
    languages,
):
    """A rating names the model that earned it. The router learns which model wrote a
    payload nobody could read only if each refusal lands on its own call, and the
    caller's rating at the end belongs to the answer the reader was left with."""
    replacement = another_answer("second answer", llm_name="free-other")
    handle = FakeHandle(["free ", "answer"], others=[replacement])
    cascade = fake_cascade(settings, handles=[handle], client=FakeDirectClient())
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda answer: "second" in answer,
    )
    await drain(completion)
    assert handle.scores == [0.0]
    assert completion.llm_name == "free-other"

    await completion.record_quality(1.0)
    assert replacement.scores == [1.0]
    assert handle.scores == [0.0]


async def test_a_pool_with_no_other_answer_leaves_the_one_it_gave_standing(settings, languages):
    handle = FakeHandle(["free ", "answer"])
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient(["paid ", "answer"]),
    )
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda answer: "paid" in answer,
    )
    assert await drain(completion) == ["free ", "answer"]
    assert handle.another_calls == 1
    assert cascade.broker.direct_calls == []


async def test_a_pool_that_fails_on_the_way_to_another_answer_does_not_fail_the_entry(
    settings,
    languages,
):
    """Nothing has failed for the reader when the pool cannot produce a second answer:
    the first one is still in front of them, and it is what the entry settles on."""
    handle = FakeHandle(
        ["free ", "answer"],
        others=[InvalidProviderResponseError("the provider returned no text", model="free-other")],
    )
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient(["paid ", "answer"]),
    )
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda answer: "paid" in answer,
    )
    assert await drain(completion) == ["free ", "answer"]
    assert cascade.broker.direct_calls == []


async def test_an_answer_the_caller_can_read_leaves_the_rest_of_the_call_alone(
    settings,
    languages,
):
    handle = FakeHandle(["free ", "answer"], others=[another_answer("never asked for")])
    cascade = fake_cascade(settings, handles=[handle])
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda _answer: True,
    )
    assert await drain(completion) == ["free ", "answer"]
    assert handle.another_calls == 0
    assert handle.closed is True


async def test_an_answer_handed_over_on_policy_does_not_ask_the_pool_again(
    settings,
    languages,
):
    """The hand-over is a preference for the better model on one kind of question, not
    a complaint about the answer. Another pool answer would be another answer of the
    same kind, which is not what the hand-over asked for."""
    handle = FakeHandle(["free ", "answer"], others=[another_answer("second answer")])
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient(["paid ", "answer"]),
    )
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda _answer: True,
        hand_over=lambda _answer: True,
    )
    assert await drain(completion) == ["free ", "answer", "paid ", "answer"]
    assert handle.another_calls == 0


async def test_a_lost_race_that_cannot_be_read_falls_back_on_the_lane_that_lost_it(
    settings,
    languages,
):
    """The lane that was beaten wrote a whole answer and llmbroker kept it. When the
    winner's payload is the unreadable one, that retained answer is the nearest thing
    to a card there is."""
    lost = lost_the_race("winning answer", winner="free-flash", streamed="free-slow")
    handle = FakeHandle(
        ["half "],
        error=lost,
        others=[another_answer("second answer", llm_name="free-slow")],
    )
    cascade = fake_cascade(settings, handles=[handle], client=FakeDirectClient())
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda answer: "second" in answer,
    )
    assert await drain(completion) == ["half ", "winning answer", "second answer"]
    assert completion.llm_name == "free-slow"
    assert cascade.broker.direct_calls == []


async def test_the_call_is_released_once_its_answer_is_settled(settings, languages):
    """The broker outlives every request, so the lanes this call kept open for the sake
    of another answer are given back by leaving the stream's context and by nothing
    else. Holding them past the verdict would keep pool slots for a finished request."""
    handle = FakeHandle(["free ", "answer"], others=[another_answer("second answer")])
    cascade = fake_cascade(settings, handles=[handle])
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda answer: "second" in answer,
    )
    await drain(completion)
    assert handle.closed is True


async def test_a_failed_paid_step_gives_back_the_pool_answer_it_replaced(
    settings,
    languages,
):
    """The pool answered completely and was handed over on policy alone. A provider
    error on the paid side is not the reader's problem: losing their analysis to it
    would make an optional second opinion strictly worse than not asking."""
    handle = FakeHandle(["free ", "answer"])
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient([], error=InvalidProviderResponseError("boom", model="gpt-fast")),
    )
    reset = ResetHook()
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        on_reset=reset,
        usable=lambda _answer: True,
        hand_over=lambda _answer: True,
    )

    # Written once and never taken off the page: the paid step that was going to
    # replace it produced nothing, so there was nothing to swap in and nothing to undo.
    assert await drain(completion) == ["free ", "answer"]
    assert reset.calls == 0
    assert completion.paid is False
    # The pool answer stands, so the caller's rating belongs to it again.
    await completion.record_quality(1.0)
    assert handle.scores == [1.0]


async def test_a_failed_paid_step_after_a_budget_miss_fails_the_entry_but_keeps_the_page(
    settings,
    languages,
):
    """The pool never finished, so there is no answer to fall back on and the entry
    fails. What the pool part-wrote is still what the reader is looking at: it was never
    cleared to make room for a step that then produced nothing."""
    handle = FakeHandle(["half an "], error=POOL_MISSED)
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient([], error=InvalidProviderResponseError("boom", model="gpt-fast")),
    )
    reset = ResetHook()
    completion = cascade.stream_completion("prompt", languages["en"], on_reset=reset)

    with pytest.raises(BackendError):
        await drain(completion)
    assert reset.calls == 0


async def test_the_page_is_not_cleared_for_a_paid_step_that_has_written_nothing(
    settings,
    languages,
):
    """The reader keeps what the pool part-wrote until the paid answer is whole. The
    swap happens in one breath, so text from two models is still never spliced, and a
    paid step that produces nothing costs no one their page."""
    order: list[str] = []

    class WatchingReset(ResetHook):
        async def __call__(self) -> None:
            order.append("reset")
            await super().__call__()

    class WatchingClient(FakeDirectClient):
        async def stream(self, prompt, *, timeout=None):
            async for delta in super().stream(prompt, timeout=timeout):
                order.append(f"paid:{delta}")
                yield delta

    reset = WatchingReset()
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(["half an "], error=POOL_MISSED)],
        client=WatchingClient(["paid ", "answer"]),
    )
    completion = cascade.stream_completion("prompt", languages["en"], on_reset=reset)

    assert await drain(completion) == ["half an ", "paid ", "answer"]
    # Every paid delta is in hand before the page is touched.
    assert order == ["paid:paid ", "paid:answer", "reset"]


async def test_a_paid_answer_no_more_readable_than_the_one_it_took_over_gives_way_to_it(
    settings,
    languages,
):
    """A hand-over is a bet that the better model does better. Losing the analysis the
    reader already had when that bet does not pay is the one outcome worse than not
    asking, so the answer in hand wins a tie it never sought."""
    handle = FakeHandle(["free ", "answer"])
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient(["unreadable paid answer"]),
    )
    reset = ResetHook()
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        on_reset=reset,
        usable=lambda answer: "free" in answer,
        hand_over=lambda _answer: True,
    )

    assert await drain(completion) == ["free ", "answer"]
    assert reset.calls == 0
    assert completion.paid is False
    assert completion.llm_name == "pool-model"
    await completion.record_quality(1.0)
    assert handle.scores == [1.0]


async def test_a_budget_miss_still_buys_a_paid_answer_without_being_asked(
    settings,
    languages,
):
    """The two triggers are not the same road. Nothing answered, so there is nothing on
    the page worth keeping and nothing for the reader to decide about."""
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(error=POOL_MISSED)],
        client=FakeDirectClient(["paid ", "answer"]),
    )
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda _answer: True,
    )
    assert await drain(completion) == ["paid ", "answer"]
    assert cascade.broker.direct_calls == ["gpt-fast"]
    assert cascade.calls_today == 1


async def test_a_pool_only_call_never_reaches_the_paid_model(settings, languages):
    """The judgement asked beside the answer is a pool question by design: paying for
    one would spend the day's cap on every ordinary word, and the paid models are no
    better at it. A pool miss is an error here, never a reason to buy an answer."""
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(["free ", "answer"])],
        client=FakeDirectClient(["paid ", "answer"]),
    )
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        pool_only=True,
        usable=lambda _answer: False,
    )
    assert await drain(completion) == ["free ", "answer"]
    assert cascade.broker.direct_calls == []
    assert cascade.calls_today == 0


async def test_a_pool_only_call_that_misses_its_budget_fails_instead_of_buying_one(
    settings,
    languages,
):
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle([], error=BudgetMissError("pool budget spent"))],
        client=FakeDirectClient(["paid ", "answer"]),
    )
    completion = cascade.stream_completion("prompt", languages["en"], pool_only=True)
    with pytest.raises(BackendError):
        await drain(completion)
    assert cascade.broker.direct_calls == []


async def test_a_pool_answer_the_caller_can_use_never_steps_up(settings, languages):
    cascade = fake_cascade(settings, handles=[FakeHandle(["free ", "answer"])])
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda answer: "free" in answer,
    )
    assert await drain(completion) == ["free ", "answer"]
    assert cascade.broker.direct_calls == []


async def test_an_oversized_pool_answer_is_bounded_and_stands(settings, languages):
    """Truncated at the bound is one more way for an answer to be unreadable, and it
    buys a paid answer no more than any other: the prefix stays on the page, rated down
    and with its card failed."""
    oversized = "x" * (MAX_COMPLETE_ANSWER_CHARS + 500)
    handle = FakeHandle([oversized])
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient(["paid answer"]),
    )
    reset = ResetHook()

    deltas = await run(cascade, languages["en"], reset)

    assert len(deltas) == 1
    assert len(deltas[0]) == MAX_COMPLETE_ANSWER_CHARS
    assert reset.calls == 0
    assert cascade.broker.direct_calls == []
    assert handle.delivered == [oversized]
    assert handle.settled is True
    assert handle.scores == [0.0]


async def test_an_oversized_paid_answer_is_bounded(settings, languages):
    oversized = "x" * (MAX_COMPLETE_ANSWER_CHARS + 500)
    cascade = fake_cascade(settings, client=FakeDirectClient([oversized]))

    deltas = await drain(cascade.stream_paid("prompt", languages["en"]))

    assert len(deltas) == 1
    assert len(deltas[0]) == MAX_COMPLETE_ANSWER_CHARS


async def test_an_answer_at_the_exact_bound_is_not_oversized(settings, languages):
    answer = "x" * MAX_COMPLETE_ANSWER_CHARS
    cascade = fake_cascade(settings, handles=[FakeHandle([answer])])
    completion = cascade.stream_completion("prompt", languages["en"])

    assert await drain(completion) == [answer]
    assert completion.oversized is False


async def test_an_extra_delta_after_the_bound_is_drained_but_never_exposed(settings, languages):
    answer = "x" * MAX_COMPLETE_ANSWER_CHARS
    handle = FakeHandle([answer, "excess"])
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient(["paid answer"]),
    )

    deltas = await run(cascade, languages["en"])

    assert deltas == [answer]
    assert cascade.broker.direct_calls == []
    assert handle.delivered == [answer, "excess"]
    assert handle.settled is True
    assert handle.scores == [0.0]


async def test_an_unusable_answer_stands_when_there_is_nothing_to_step_up_to(settings, languages):
    handle = FakeHandle(["free ", "answer"])
    cascade = fake_cascade(
        settings.model_copy(update={"api_model": ""}),
        handles=[handle],
        client=FakeDirectClient(),
    )
    reset = ResetHook()
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        on_reset=reset,
        usable=lambda _answer: False,
    )
    assert await drain(completion) == ["free ", "answer"]
    assert cascade.broker.direct_calls == []
    assert reset.calls == 0
    assert handle.scores == [0.0]


async def test_an_answer_replaced_over_its_payload_keeps_the_rating_that_rejected_it(
    settings,
    languages,
):
    handle = FakeHandle(["free ", "answer"])
    cascade = fake_cascade(settings, handles=[handle], client=FakeDirectClient())
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda answer: "paid" in answer,
    )
    await drain(completion)
    await completion.record_quality(1.0)
    assert handle.scores == [0.0]


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


async def test_direct_missing_key_refuses_explicit_paid_work_before_it_is_queued(
    settings,
    languages,
):
    cascade = fake_cascade(settings)
    cascade.broker.snapshot_value = SimpleNamespace(
        providers_usable=1,
        providers_total=1,
        degraded=False,
        missing_keys=(),
        direct_missing_keys=(
            SimpleNamespace(
                api_key_ref="PAID_KEY",
                help="configure it here",
                entry_names=("gpt-fast",),
            ),
        ),
    )

    refusal = await cascade.refresh_paid_availability(languages["en"])

    assert refusal == "the paid model is missing PAID_KEY: configure it here"


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


async def test_a_failed_answer_says_in_the_log_which_step_failed_and_after_how_long(
    settings,
    languages,
    caplog,
):
    """The reader is told one word — the entry failed — and `/api/status` keeps the
    reason only until the language's next call overwrites it. Without this line a
    production failure leaves nothing to diagnose it from."""
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(error=POOL_MISSED)],
        client=FakeDirectClient([], error=LLMTimeoutError("direct stream timed out")),
    )
    with (
        caplog.at_level(logging.WARNING, logger="echo_words.backend"),
        pytest.raises(BackendError),
    ):
        await drain(cascade.stream_completion("prompt", languages["en"], trace_id="entry-7"))

    assert "no answer for en" in caplog.text
    assert "paid model gpt-fast" in caplog.text
    assert "entry-7" in caplog.text
    assert "direct stream timed out" in caplog.text


async def test_the_paid_step_reports_whether_it_ever_wrote_a_token(
    settings,
    languages,
    caplog,
):
    """The direct client journals nothing, so how long the paid model took and whether
    it spoke at all is measured here or nowhere."""
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(error=POOL_MISSED)],
        client=FakeDirectClient([], error=LLMTimeoutError("direct stream timed out")),
    )
    with (
        caplog.at_level(logging.INFO, logger="echo_words.backend"),
        pytest.raises(BackendError),
    ):
        await run(cascade, languages["en"])
    assert "the paid model gpt-fast: first token after never" in caplog.text

    caplog.clear()
    answering = fake_cascade(
        settings,
        handles=[FakeHandle(error=POOL_MISSED)],
        client=FakeDirectClient(),
    )
    with caplog.at_level(logging.INFO, logger="echo_words.backend"):
        await run(answering, languages["en"])
    assert "first token after 0.0 s" in caplog.text


async def test_the_step_up_says_which_answer_it_replaces_and_why(settings, languages, caplog):
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(["free ", "answer"])],
        client=FakeDirectClient(),
    )
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda _answer: True,
        hand_over=lambda _answer: True,
    )
    with caplog.at_level(logging.INFO, logger="echo_words.backend"):
        assert await drain(completion) == ["free ", "answer", "paid ", "answer"]
    assert (
        "the paid model takes over for en: the pool answer from pool-model is a declared"
        " misspelling"
    ) in caplog.text


async def test_an_unreadable_payload_says_in_the_log_that_the_card_was_left_failed(
    settings,
    languages,
    caplog,
):
    """The entry keeps an analysis whose payload failed, and the log says so: the card
    was lost to the payload, with the pool out of answers and no paid call made."""
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(["free ", "answer"])],
        client=FakeDirectClient(),
    )
    completion = cascade.stream_completion(
        "prompt",
        languages["en"],
        usable=lambda _answer: False,
        hand_over=lambda _answer: False,
    )
    with caplog.at_level(logging.INFO, logger="echo_words.backend"):
        assert await drain(completion) == ["free ", "answer"]
    assert "the pool answer from pool-model stands for en" in caplog.text
    assert "the card is left failed" in caplog.text
    assert cascade.broker.direct_calls == []
