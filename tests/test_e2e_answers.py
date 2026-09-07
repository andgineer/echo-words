"""What a reader's page does when the model fails, driven through a real browser.

Every case here is a failure the pipeline is written to absorb, and each asserts the
one thing a unit test cannot: what is left on the screen afterwards. The LLM is faked
and gated, so the provisional state is held until the assertion about it has run.
"""

import pytest
from e2e_app import WORD, Gate, answer, live_app, submit
from fakes import FakeDirectClient, FakeHandle, lost_the_race
from llmbroker import LLMTimeoutError
from playwright.sync_api import Page, expect

from echo_words.config import Settings

pytestmark = pytest.mark.e2e

PROVISIONAL = "<b>the lane that lost</b>"
WINNER = "<b>the whole answer that won</b>"
PAID = "<b>the answer that was paid for</b>"


def test_a_lost_race_repaints_the_entry_instead_of_splicing_the_answer_that_won(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reader is shown one lane's text while every lane runs on. When another lane
    finishes a whole answer first, what was on the page is void: it is dropped and the
    answer that won is written in its place, never appended to it."""
    gate = Gate()
    replaced = lost_the_race(answer(WINNER), winner="the-winner", streamed="the-loser")
    handle = FakeHandle([answer(PROVISIONAL)], error=replaced, hold=gate.wait)
    with live_app(settings, monkeypatch, handles=[handle]) as app:
        submit(page, app.url)
        entry = page.locator(".entry-text")
        expect(entry).to_contain_text("the lane that lost")

        gate.open()

        expect(entry).to_contain_text("the whole answer that won")
        expect(entry).not_to_contain_text("the lane that lost")
        expect(page.locator(".entry-model")).to_have_text("the-winner")


def test_a_budget_miss_drops_the_half_answer_it_showed_for_the_paid_one(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pool answer that never lands leaves half an article on the page. The paid step
    replaces the page rather than continuing it, so the reader is never shown one
    model's opening welded onto another model's ending."""
    gate = Gate()
    handle = FakeHandle(
        [answer(PROVISIONAL)],
        error=LLMTimeoutError("the pool missed the answer budget"),
        hold=gate.wait,
    )
    with live_app(
        settings,
        monkeypatch,
        handles=[handle],
        client=FakeDirectClient([answer(PAID)]),
    ) as app:
        submit(page, app.url)
        entry = page.locator(".entry-text")
        expect(entry).to_contain_text("the lane that lost")

        gate.open()

        expect(entry).to_contain_text("the answer that was paid for")
        expect(entry).not_to_contain_text("the lane that lost")


def test_a_pool_failure_with_no_paid_step_settles_the_entry_into_a_retryable_error(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the paid step switched off there is nothing to replace the answer with, so
    the entry settles into an error offering a retry. The part-written analysis stays
    with it — it was streamed only after the judgement vouched for the wording, and it
    is marked failed rather than passed off as finished. What must not survive is the
    spinner, which would leave a dead entry looking like one still being worked on."""
    gate = Gate()
    handle = FakeHandle(
        [answer(PROVISIONAL)],
        error=LLMTimeoutError("the pool missed the answer budget"),
        hold=gate.wait,
    )
    offline = Settings(**{**settings.model_dump(), "api_model": ""})
    with live_app(offline, monkeypatch, handles=[handle]) as app:
        submit(page, app.url)
        expect(page.locator(".entry-text")).to_contain_text("the lane that lost")

        gate.open()

        expect(page.locator(".entry-error")).to_be_visible()
        expect(page.get_by_role("button", name=f"Send “{WORD}” again")).to_be_visible()
        expect(page.locator(".working.pending")).to_have_count(0)
        expect(page.locator(".entry-card-status")).to_have_count(0)


def test_a_wording_the_judgement_refuses_is_never_shown_however_much_streamed(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The withhold gate outlives streaming: a complete article about a coinage reaches
    the server and still never reaches the page, because the judgement refused it."""
    handle = FakeHandle([answer("<b>an invented compound</b>", word="Löffelangst")])
    with live_app(
        settings,
        monkeypatch,
        handles=[handle],
        attestation='{"used": false, "where": ""}',
    ) as app:
        submit(page, app.url, "Löffelangst")
        expect(page.locator(".entry-card-status")).to_have_text("🚫 no card")
        expect(page.locator(".entry-notice")).to_contain_text("does not vouch")
        expect(page.locator(".entry-text")).to_have_count(0)
