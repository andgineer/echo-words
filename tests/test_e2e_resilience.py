"""What the page survives when the connection, not the model, is what fails.

Both cases live only in the browser: one is the event stream dying mid-answer and the
page having to find out what it missed, the other is a word submitted with no network
at all. Neither the Python suite nor the component suite can reach them, because
neither has a browser whose connection can be taken away.
"""

import pytest
from e2e_app import WORD, Gate, answer, live_app, submit
from fakes import FakeHandle
from playwright.sync_api import Page, expect

from echo_words.config import Settings

pytestmark = pytest.mark.e2e

ARTICLE = "<b>the finished analysis</b>"
RECONNECT_TIMEOUT_MS = 15_000


def test_an_answer_finished_while_the_page_was_deaf_is_recovered_on_reconnect(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The event stream is the only way an answer reaches the page, and it dies with the
    connection. Everything published while it was down has to be recovered when it comes
    back, or the entry stays half-written on the screen with the work long since done."""
    gate = Gate()
    with live_app(
        settings,
        monkeypatch,
        handles=[FakeHandle([answer(ARTICLE)], hold=gate.wait)],
    ) as app:
        submit(page, app.url)
        expect(page.locator(".entry-text")).to_contain_text("the finished analysis")

        page.context.set_offline(True)
        gate.open()
        page.context.set_offline(False)

        expect(page.locator(".entry-card-status")).to_contain_text(
            "card",
            timeout=RECONNECT_TIMEOUT_MS,
        )
        expect(page.locator(".working.pending")).to_have_count(0)


def test_a_word_submitted_with_no_connection_is_sent_once_when_it_returns(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Offline the submission is kept rather than lost, and coming back online sends it.
    The pool is scripted with exactly one answer, so a resend that submitted the word
    twice would ask for a second and fail here rather than quietly double the card."""
    with live_app(settings, monkeypatch, handles=[FakeHandle([answer(ARTICLE)])]) as app:
        page.goto(app.url)
        page.context.set_offline(True)
        page.get_by_placeholder("a word or a phrase").fill(WORD)
        page.get_by_role("button", name="Analyse").click()
        expect(page.get_by_text("the word is saved and will be sent later")).to_be_visible()

        page.context.set_offline(False)

        expect(page.locator(".entry-text")).to_contain_text(
            "the finished analysis",
            timeout=RECONNECT_TIMEOUT_MS,
        )
        articles = len(app.broker.stream_calls) - len(app.broker.attestation_calls)
        assert articles == 1
