"""The card's controls, driven through a real browser.

What is asserted here is what only a laid-out page can answer: where the row sits
relative to the analysis it acts on, that no browser player is taking the room the
row replaced, and that taking an entry off the rail really empties the rail.
"""

from pathlib import Path

import pytest
from e2e_app import WORD, answer, live_app, submit
from fakes import FakeHandle
from playwright.sync_api import Page, expect

from echo_words.config import Settings

pytestmark = pytest.mark.e2e

ARTICLE = "<b>Schlüssel</b> — ключ"
RAIL = '[role="tablist"][aria-label="Analysed words"] [role="tab"]'

# The rail the PWA restores itself from, read out of the browser's own database.
_STORED_KEYS = """async () => {
  const open = indexedDB.open("echo-words", 1);
  const db = await new Promise((resolve, reject) => {
    open.onsuccess = () => resolve(open.result);
    open.onerror = () => reject(open.error);
  });
  const saved = await new Promise((resolve, reject) => {
    const read = db.transaction("cache", "readonly").objectStore("cache").get("history");
    read.onsuccess = () => resolve(read.result);
    read.onerror = () => reject(read.error);
  });
  return (saved?.data ?? []).flatMap((entry) => Object.keys(entry));
}"""


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


def _one_second_of_silence(settings: Settings):
    """A recording the browser will actually play: MPEG-1 Layer III frames of zeroes,
    long enough that the state it puts the card in outlives one assertion."""
    frame = b"\xff\xfb\x90\x00" + bytes(413)

    async def recording(*_args: object, **_kwargs: object) -> Path:
        path = settings.data_dir / "audio" / f"pronunciation-{'a' * 20}.mp3"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(frame * 40)
        return path

    return recording


def test_a_recording_speaks_when_it_arrives_and_never_again_from_history(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recording is played when it arrives, if the card that owns it is still the one
    on screen. There is nothing to carry forward from that: a card restored by a reload
    has its recording already, so there is no arrival, and the history must hold no mark
    that could hand the moment out a second time."""
    with live_app(
        settings,
        monkeypatch,
        audio=_one_second_of_silence(settings),
        handles=[FakeHandle([answer(ARTICLE)])],
    ) as app:
        submit(page, app.url)
        expect(page.locator(".speak-word")).to_have_attribute("title", "Pause")

        page.reload()
        expect(page.locator(".entry-title")).to_have_text(WORD)
        expect(page.locator(".speak-word")).to_have_attribute("title", "Play")

        # The silence itself proves little here — a reloaded page has had no gesture
        # from the reader, and the browser would refuse the sound whatever the card
        # asked for. What has to hold is that nothing was written down to play from:
        # the restored entry carries no mark of having been fresh.
        assert "just_finished" not in page.evaluate(_STORED_KEYS)
