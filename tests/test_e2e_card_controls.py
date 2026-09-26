"""The card's controls, driven through a real browser.

What is asserted here is what only a laid-out page can answer: where the row sits
relative to the analysis it acts on, that no browser player is taking the room the
row replaced, that taking an entry off the rail really empties the rail, where the
deeper article is when it starts to arrive, what the controls of an entry the
server has forgotten since do, and that the text can be selected on a card that
also moves under a drag.
"""

import re
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from e2e_app import WORD, Gate, answer, live_app, submit
from fakes import FakeDirectClient, FakeHandle
from playwright.sync_api import Page, expect

from echo_words.config import Settings

pytestmark = pytest.mark.e2e

ARTICLE = "<b>Schlüssel</b> — ключ"
# Taller than the window, so the deeper article under it starts out of sight.
LONG_ARTICLE = ARTICLE + "".join(f"<p>Beispiel {n}.</p>" for n in range(60))
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


def _stored_once_finished(page: Page) -> None:
    """Wait until the finished answer is in the browser's own database, which is all a
    restart leaves the page. A read of what was written, not a sleep."""
    deadline = time.monotonic() + 10
    while "detail_word" not in page.evaluate(_STORED_KEYS):
        if time.monotonic() > deadline:
            raise TimeoutError("the finished answer never reached the browser's database")
        page.wait_for_timeout(50)


def test_in_depth_brings_its_article_into_view_while_it_is_still_arriving(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The article is appended below an analysis that is often longer than the screen,
    so the press takes the reader down to it and they watch it being written."""
    gate = Gate()
    with live_app(
        settings,
        monkeypatch,
        handles=[FakeHandle([answer(LONG_ARTICLE)])],
        client=FakeDirectClient(["<p>Die ersten Zeilen.</p>"], hold=gate.wait),
    ) as app:
        submit(page, app.url)
        expect(page.locator(".delete-card")).to_be_visible()
        block = page.locator(".entry-detail-block")

        page.locator(".detail").click()

        expect(block).to_be_in_viewport()
        expect(block.locator(".entry-detail")).to_contain_text("Die ersten Zeilen.")
        expect(block.locator(".working")).to_be_visible()

        gate.open()
        expect(block.locator(".working")).to_have_count(0)
        expect(block).to_be_in_viewport()


def test_after_a_restart_the_article_still_comes_and_the_card_says_what_expired(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deploy restarts the server and empties it, while the page keeps the entry. The
    deeper article needs only what the page kept; deleting the card needs the note the
    server has forgotten, and the reader is told so in their own words."""
    with live_app(settings, monkeypatch, handles=[FakeHandle([answer(ARTICLE)])]) as first:
        submit(page, first.url)
        expect(page.locator(".delete-card")).to_be_visible()
        _stored_once_finished(page)
    port = urlsplit(first.url).port

    with live_app(
        settings,
        monkeypatch,
        port=port,
        client=FakeDirectClient(["<p>Der ganze Artikel.</p>"]),
    ) as second:
        page.reload()
        expect(page.locator(".entry-text")).to_contain_text("ключ")

        page.locator(".detail").click()
        expect(page.locator(".entry-detail")).to_contain_text("Der ganze Artikel.")
        assert WORD in second.broker.client.calls[0]["prompt"]

        page.locator(".delete-card").click()
        page.locator(".confirm-yes").click()
        expect(page.locator(".controls-expired")).to_have_text(
            "The server restarted after this answer, so its card can no longer be changed "
            "from here.",
        )
        expect(page.locator(".delete-card")).to_be_disabled()
        expect(page.get_by_text("request expired")).to_have_count(0)


def _settled(page: Page) -> dict:
    """Where the card stands once it has stopped moving. A switch places it to one side
    and slides it in a frame later, so a card with no animation yet may still be off."""
    deck = page.locator(".deck")
    expect(deck).to_have_attribute("style", re.compile(r"translateX\(0px\)"))
    deck.evaluate("(el) => Promise.all(el.getAnimations().map((a) => a.finished))")
    return deck.bounding_box()


# Where a piece of the analysis is drawn, found from its text rather than from the font
# a machine happens to have.
_DRAWN = """(el, piece) => {
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const at = node.data.indexOf(piece);
    if (at < 0) continue;
    const range = document.createRange();
    range.setStart(node, at);
    range.setEnd(node, at + piece.length);
    const box = range.getBoundingClientRect();
    return { x: box.x, y: box.y, width: box.width, height: box.height };
  }
  return null;
}"""

EXAMPLE = "Er steckt den Schlüssel ins Schloss und dreht ihn."


def test_the_text_gives_up_a_word_and_only_the_margin_swipes(
    each_engine_page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A word from an example is copied into a new request by selecting it, and a mouse
    selection is the same sideways drag as a swipe. So the card holds still under a drag
    across its text, gives up a word to a double click, and still moves under a drag
    along its margin."""
    page = each_engine_page
    second = "Schloss"
    with live_app(
        settings,
        monkeypatch,
        handles=[FakeHandle([answer(ARTICLE)]), FakeHandle([answer(EXAMPLE, second)])],
    ) as app:
        submit(page, app.url)
        expect(page.locator(".delete-card")).to_be_visible()
        page.get_by_placeholder("a word or a phrase").fill(second)
        page.get_by_role("button", name="Analyse").click()
        title = page.locator(".entry-title")
        analysis = page.locator(".entry-text")
        expect(title).to_have_text(second)
        expect(analysis).to_contain_text(EXAMPLE)
        _settled(page)

        line = analysis.evaluate(_DRAWN, EXAMPLE)
        across = line["y"] + line["height"] / 2
        page.mouse.move(line["x"] + line["width"] - 3, across)
        page.mouse.down()
        page.mouse.move(line["x"] + 3, across, steps=12)
        expect(page.locator(".deck")).to_have_attribute("style", re.compile(r"translateX\(0px\)"))
        page.mouse.up()
        expect(title).to_have_text(second)

        word = analysis.evaluate(_DRAWN, "Schlüssel")
        page.mouse.dblclick(word["x"] + word["width"] / 2, word["y"] + word["height"] / 2)
        assert page.evaluate("() => getSelection().toString()").strip() == "Schlüssel"

        # With text selected, WebKit may take a mouse drag from the margin for a drag of
        # that selection, and the card never hears the release.
        page.evaluate("() => getSelection().removeAllRanges()")
        deck = _settled(page)
        edge = deck["x"] + deck["width"] - 6
        middle = deck["y"] + deck["height"] / 2
        page.mouse.move(edge, middle)
        page.mouse.down()
        page.mouse.move(edge - 160, middle, steps=12)
        page.mouse.up()

        expect(title).to_have_text(WORD)
