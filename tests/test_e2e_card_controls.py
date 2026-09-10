"""The card's controls, driven through a real browser.

What is asserted here is what only a laid-out page can answer: where the row sits
relative to the analysis it acts on, that no browser player is taking the room the
row replaced, and that taking an entry off the rail really empties the rail.
"""

import pytest
from e2e_app import WORD, answer, live_app, submit
from fakes import FakeHandle
from playwright.sync_api import Page, expect

from echo_words.config import Settings

pytestmark = pytest.mark.e2e

ARTICLE = "<b>Schlüssel</b> — ключ"
RAIL = '[role="tablist"][aria-label="Analysed words"] [role="tab"]'


def test_the_controls_stand_above_the_analysis_with_no_player_taking_the_room(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The row belongs to the whole card, so it is read before the analysis and never
    among the chips under it. The recording it drives has no visible player of its own."""
    with live_app(settings, monkeypatch, handles=[FakeHandle([answer(ARTICLE)])]) as app:
        submit(page, app.url)
        row = page.locator(".entry-actions")
        article = page.locator(".entry-text")
        expect(article).to_contain_text("ключ")
        expect(row).to_be_visible()

        assert row.bounding_box()["y"] < article.bounding_box()["y"]
        expect(page.locator("audio[controls]")).to_have_count(0)
        expect(page.locator(".entry-card-status")).to_have_count(0)


def test_the_question_before_deleting_opens_under_the_button_that_raised_it(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Asked at the foot of a card the article has made long, the question was nowhere
    near the finger that asked it. It opens under its own row, which stays put."""
    with live_app(settings, monkeypatch, handles=[FakeHandle([answer(ARTICLE)])]) as app:
        submit(page, app.url)
        delete = page.locator(".delete-card")
        expect(delete).to_have_text("Anki")

        delete.click()

        confirm = page.locator(".confirm")
        expect(confirm).to_be_visible()
        expect(page.locator(".entry-actions")).to_be_visible()
        assert confirm.bounding_box()["y"] > page.locator(".entry-actions").bounding_box()["y"]


def test_taking_an_entry_off_the_rail_empties_it_and_the_offer_puts_it_back(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cross removes nothing from Anki, so it asks nothing. What stands in for the
    question is the offer afterwards, and it has to reach the rail as well as the card."""
    with live_app(settings, monkeypatch, handles=[FakeHandle([answer(ARTICLE)])]) as app:
        submit(page, app.url)
        expect(page.locator(RAIL)).to_have_count(1)

        page.locator(".remove-entry").click()

        expect(page.locator(RAIL)).to_have_count(0)
        expect(page.locator(".entry-title")).to_have_count(0)
        expect(page.locator(".removed-text")).to_be_visible()

        page.locator(".undo-remove").click()

        expect(page.locator(RAIL)).to_have_count(1)
        expect(page.locator(".entry-title")).to_have_text(WORD)
